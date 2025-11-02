import requests
from bs4 import BeautifulSoup
from google import genai
import json
from neo4j import GraphDatabase, Session, Transaction
from typing import Optional, List, Type
import enum
from datetime import datetime

# Import our custom modules
import config
from ontology import *

# --- Client Initialization ---
client = genai.Client(api_key=config.GOOGLE_API_KEY)

# ==============================================================================
# 4.1 CRAWLER
# ==============================================================================
def get_webpage_content(url: str) -> Optional[str]:
    """Fetches the visible text from a webpage."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        for script in soup(["script", "style"]): script.extract()
        text = soup.get_text(separator=" ")
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        return text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching webpage {url}: {e}")
        return None

# ==============================================================================
# 4.2 EXTRACTOR
# ==============================================================================
def extract_structured_data(text: str, schema_class: Type[BaseModel]) -> Optional[BaseModel]:
    """Extracts knowledge from text using the Gemini API."""
    prompt = f"""
    Extract all relevant information from the following text and populate the provided data schema.
    IMPORTANT: The schema requires a `ProvableFact` object for many facts. 
    You must fill the `value` field (the fact) AND the `evidence` field (the text snippet from the source text
    that proves the fact).
    
    **Text to Analyze:**
    ---
    {text}
    ---
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema_class,
            }
        )
        if response.parsed is None:
            print("ERROR: The SDK could not parse the response into the Pydantic schema.")
            return None
        print(f"Model response for schema '{schema_class.__name__}' parsed successfully.")
        return response.parsed
    except Exception as e:
        print(f"An unexpected ERROR occurred during extraction: {e}")
        return None

# ==============================================================================
# 4.3 GROUNDER
# ==============================================================================
def is_fact_grounded(fact: str, evidence: str) -> bool:
    """Checks with a 'lightweight' LLM if a fact is supported by an evidence snippet."""
    prompt = f"""
    Verify if the following fact can be inferred from the provided text snippet.
    The fact must be explicitly mentioned or directly logically derivable.
    
    Fact to verify:
    "{fact}"

    Can this fact be derived from the following snippet?:
    "{evidence}"
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": GrounderResponse,
            }
        )
        if response.parsed:
            return response.parsed.is_grounded
        else:
            print(f"GROUNDER WARNING: Could not parse response. Defaulting to 'False'.")
            return False
    except Exception as e:
        print(f"GROUNDER ERROR: {e}. Defaulting to 'False'.")
        return False

def _ground_model_recursive(model_instance: BaseModel):
    """Recursively iterates through a Pydantic model and nullifies any ungrounded facts."""
    if model_instance is None: return
    
    # Use .model_fields for Pydantic v2+
    for field_name, field_obj in model_instance.model_fields.items():
        field_value = getattr(model_instance, field_name)
        if field_value is None: continue

        if isinstance(field_value, ProvableFact):
            if not field_value.value or not field_value.evidence:
                print(f"--- ⚠️ GROUNDING SKIPPED: Empty value/evidence for {field_name}. Removing.")
                setattr(model_instance, field_name, None)
                continue
            
            is_grounded = is_fact_grounded(field_value.value, field_value.evidence)
            if not is_grounded:
                print(f"--- ❌ GROUNDING FAILED: Fact '{field_value.value}' (for field '{field_name}') will be removed.")
                setattr(model_instance, field_name, None)
            else:
                print(f"--- ✅ GROUNDING PASSED: Fact '{field_value.value}' (for field '{field_name}')")
        
        elif isinstance(field_value, BaseModel):
            _ground_model_recursive(field_value)
        elif isinstance(field_value, list):
            for item in field_value:
                if isinstance(item, BaseModel):
                    _ground_model_recursive(item)
                            
def ground_package(package: ExtractionPackage) -> ExtractionPackage:
    """Takes an ExtractionPackage and validates all ProvableFact instances within it."""
    print("\n" + "="*30 + f"\n🔬 STARTING GROUNDING PROCESS for {package.metadata.url}\n" + "="*30)
    _ground_model_recursive(package.data)
    print(f"🔬 GROUNDING PROCESS for {package.metadata.url} COMPLETED.")
    return package

# ==============================================================================
# 4.4 INGESTOR & CORROBORATOR
# ==============================================================================
def get_node_props(model: BaseModel) -> dict:
    """Converts a Pydantic model into a flat dictionary of VALUES for Neo4j node properties."""
    props = {}
    if model is None: return props
    # Use .model_fields.items() for Pydantic v2+
    for field_name, field_info in model.model_fields.items():
        field_value = getattr(model, field_name)
        if isinstance(field_value, ProvableFact):
            if field_value.value is not None: props[field_name] = field_value.value
        elif isinstance(field_value, enum.Enum):
             props[field_name] = field_value.value
        elif isinstance(field_value, (str, int, float, bool)) or field_value is None:
            props[field_name] = field_value
    return props

def get_rel_props(model: BaseModel) -> dict:
    """Converts a Pydantic model into a flat dictionary of EVIDENCE snippets for Neo4j relationship properties."""
    props = {}
    if model is None: return props
    for field_name, field_info in model.model_fields.items():
        field_value = getattr(model, field_name)
        if isinstance(field_value, ProvableFact):
            if field_value.evidence is not None: props[f"{field_name}_evidence"] = field_value.evidence
    return props

def _tx_corroborate_and_ingest(
    tx: Transaction, 
    node_label: str, 
    node_key: str, 
    node_key_value: str, 
    new_node_props: dict, 
    new_rel_props: dict,
    meta: ProvenanceModel
):
    """Executes the Corroborator logic (Model B) in a single transaction."""
    
    new_rel_props['retrieved_at'] = meta.retrieved_at
    new_rel_props['trust_score'] = meta.trust_score

    query_find_old = f"""
    MATCH (n:{node_label} {{{node_key}: $key_value}})-[r_alt:FROM_SOURCE {{is_active: true}}]->(q_alt:Source)
    WHERE q_alt.url <> $url
    RETURN r_alt.retrieved_at AS old_ts, r_alt.trust_score AS old_trust
    """
    result = tx.run(query_find_old, key_value=node_key_value, url=meta.url)
    old_fact = result.single()

    is_candidate_winner = False
    if not old_fact:
        is_candidate_winner = True 
    else:
        if meta.retrieved_at > old_fact['old_ts']: is_candidate_winner = True
        elif meta.retrieved_at == old_fact['old_ts']:
            if meta.trust_score >= old_fact['old_trust']: is_candidate_winner = True
            else: is_candidate_winner = False
        else: is_candidate_winner = False

    tx.run(f"MERGE (q:Source {{url: $url}}) MERGE (n:{node_label} {{{node_key}: $key_value}})", 
           url=meta.url, key_value=node_key_value)
    
    if is_candidate_winner:
        print(f"--- 🏆 CORROBORATOR: NEW wins for {node_key_value}")
        tx.run(f"""
        MATCH (n:{node_label} {{{node_key}: $key_value}})
        OPTIONAL MATCH (n)-[r_alt:FROM_SOURCE {{is_active: true}}]->()
        SET n = $node_props, r_alt.is_active = false
        """, key_value=node_key_value, node_props=new_node_props)
        
        new_rel_props['is_active'] = True
        tx.run(f"""
        MATCH (n:{node_label} {{{node_key}: $key_value}}) MATCH (q:Source {{url: $url}})
        MERGE (n)-[r_new:FROM_SOURCE]->(q) SET r_new = $rel_props
        """, key_value=node_key_value, url=meta.url, rel_props=new_rel_props)
    else:
        print(f"--- 🛡️ CORROBORATOR: OLD wins for {node_key_value}")
        new_rel_props['is_active'] = False
        tx.run(f"""
        MATCH (n:{node_label} {{{node_key}: $key_value}}) MATCH (q:Source {{url: $url}})
        MERGE (n)-[r_new:FROM_SOURCE]->(q) SET r_new = $rel_props
        """, key_value=node_key_value, url=meta.url, rel_props=new_rel_props)

def _tx_ingest_product_package(tx: Transaction, package: ExtractionPackage[KnowledgeGraphData]):
    """Executes the entire product ingestion in a single transaction."""
    data = package.data
    meta = package.metadata
    
    print(f"--- ⏳ STALENESS-CHECK: Deactivating old Product-facts from {meta.url}...")
    tx.run("MATCH (n:Product|Condition|FAQ)-[r:FROM_SOURCE {is_active: true}]->(q:Source {url: $url}) SET r.is_active = false", url=meta.url)
    
    if not data.product or not data.product.name: return 
    product_name = data.product.name.value
    print(f"Processing Product: {product_name} from {meta.url}")
    product_node_props = get_node_props(data.product)
    product_node_props['name'] = product_name
    _tx_corroborate_and_ingest(tx, "Product", "name", product_name, product_node_props, get_rel_props(data.product), meta)

    if data.product_type and data.product_type.name:
        type_name = data.product_type.name.value
        tx.run("MATCH (p:Product {name: $p_name}) MERGE (pt:ProductType {name: $t_name}) MERGE (p)-[:HAS_PRODUCT_TYPE]->(pt)", p_name=product_name, t_name=type_name)

    if data.risk_class and data.risk_class.risk_class:
        class_value = data.risk_class.risk_class.value 
        tx.run("MATCH (p:Product {name: $p_name}) MERGE (s:RiskClass {risk_class: $c_value}) MERGE (p)-[:HAS_RISK_CLASS]->(s)", p_name=product_name, c_value=class_value)

    if data.conditions:
        for condition in data.conditions:
            if condition is None or condition.interest_rate is None: continue 
            key = f"{product_name}_{condition.min_amount}_{condition.term_years}"
            condition_node_props = get_node_props(condition)
            condition_node_props['key'] = key
            _tx_corroborate_and_ingest(tx, "Condition", "key", key, condition_node_props, get_rel_props(condition), meta)
            tx.run("MATCH (p:Product {name: $p_name}), (k:Condition {key: $key}) MERGE (p)-[:HAS_CONDITION]->(k)", p_name=product_name, key=key)

    if data.faqs:
        for faq in data.faqs:
            if faq is None or faq.question is None: continue 
            question_value = faq.question.value
            faq_node_props = get_node_props(faq)
            faq_node_props['question'] = question_value
            _tx_corroborate_and_ingest(tx, "FAQ", "question", question_value, faq_node_props, get_rel_props(faq), meta)
            tx.run("MATCH (p:Product {name: $p_name}), (f:FAQ {question: $q_value}) MERGE (p)-[:HAS_FAQ]->(f)", p_name=product_name, q_value=question_value)

def _tx_ingest_branch_package(tx: Transaction, package: ExtractionPackage[BranchData]):
    """Executes the entire branch ingestion in a single transaction."""
    data = package.data
    meta = package.metadata

    print(f"--- ⏳ STALENESS-CHECK: Deactivating old Branch-facts from {meta.url}...")
    # KORREKTUR: This is NOT an f-string. Use single curly braces.
    tx.run("MATCH (n:Branch|Employee)-[r:FROM_SOURCE {is_active: true}]->(q:Source {url: $url}) SET r.is_active = false", url=meta.url)
    
    if not data.branch or not data.branch.name: return
    branch_name = data.branch.name.value
    print(f"Processing Branch: {branch_name} from {meta.url}")
    branch_node_props = get_node_props(data.branch)
    branch_node_props['name'] = branch_name
    _tx_corroborate_and_ingest(tx, "Branch", "name", branch_name, branch_node_props, get_rel_props(data.branch), meta)

    if data.branch.employees:
        for employee in data.branch.employees:
            if employee is None or employee.name is None: continue 
            employee_name = employee.name.value
            print(f"-- Processing Employee: {employee_name}")
            employee_node_props = get_node_props(employee)
            employee_node_props['name'] = employee_name
            _tx_corroborate_and_ingest(tx, "Employee", "name", employee_name, employee_node_props, get_rel_props(employee), meta)
            tx.run("MATCH (m:Employee {name: $m_name}), (f:Branch {name: $f_name}) MERGE (m)-[:WORKS_IN]->(f)", m_name=employee_name, f_name=branch_name)
            if employee.role_type:
                role_type_name = employee.role_type.value
                tx.run("MATCH (m:Employee {name: $m_name}) MERGE (st:RoleType {name: $r_name}) MERGE (m)-[:HAS_ROLE_TYPE]->(st)", m_name=employee_name, r_name=role_type_name)

def ingest_product_package(package: ExtractionPackage[KnowledgeGraphData]):
    """Manager function: Writes a product package in a single transaction."""
    driver = GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD))
    with driver.session() as session:
        session.execute_write(_tx_ingest_product_package, package)
    print(f"Ingestion transaction for Product package completed.")

def ingest_branch_package(package: ExtractionPackage[BranchData]):
    """Manager function: Writes a branch package in a single transaction."""
    driver = GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD))
    with driver.session() as session:
        session.execute_write(_tx_ingest_branch_package, package)
    print(f"Ingestion transaction for Branch package completed.")

# ==============================================================================
# 4.5 INFERENCE
# ==============================================================================
def create_inferred_relationships():
    """Creates inferred relationships ONLY between active nodes."""
    driver = GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD))
    with driver.session() as session:
        print("\n" + "="*50 + "\nPHASE 2: CREATE INFERRED RELATIONSHIPS\n" + "="*50)
        
        print("Deleting all old :ADVISES_ON relationships...")
        session.run("MATCH ()-[r:ADVISES_ON]->() DETACH DELETE r")

        cypher_query = """
        MATCH (m:Employee)-[r_m:FROM_SOURCE]->() WHERE r_m.is_active = true
        MATCH (m)-[:HAS_ROLE_TYPE]->(:RoleType {name: 'Advisor'})
        MATCH (p:Product)-[r_p:FROM_SOURCE]->() WHERE r_p.is_active = true
        MATCH (p)-[:HAS_PRODUCT_TYPE]->(:ProductType {name: 'InterestProduct'})
        MERGE (m)-[r:ADVISES_ON]->(p)
        RETURN count(r) AS new_relationship_count
        """
        
        print("Creating new relationships between *active* Advisors and *active* InterestProducts...")
        result = session.run(cypher_query)
        summary = result.single()
        if summary:
            print(f"--> {summary['new_relationship_count']} new :ADVISES_ON relationships created.")
    driver.close()

# ==============================================================================
# HELPERS
# ==============================================================================
def clear_database():
    """Empties the entire Neo4j database."""
    print("Clearing the Neo4j database before starting...")
    driver = GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD))
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
    print("Database cleared.")

def ingest_fake_data():
    """
    Ingests a single FAKE condition to test the Corroborator logic.
    """
    print("\n" + "="*50 + "\n🔬 TEST: Ingesting FAKE Corroborator Data\n" + "="*50)

    # 1. Define some Fake Data
    fake_url = "https://intern.vblh.de/sparbrief"
    fake_time_str = "2025-10-02T15:24:42.019052" # set date in the future or past to test corroborator outcomes
    fake_key = "Volksbank Sparbrief_5000_6"
    fake_product_name = "Volksbank Sparbrief"
    
    # 2. Create Pydantic Models
    try:
        fake_time = datetime.fromisoformat(fake_time_str)
        fake_trust = config.get_trust_score(fake_url)
        
        fake_meta = ProvenanceModel(
            url=fake_url,
            retrieved_at=fake_time,
            trust_score=fake_trust
        )
        
        fake_condition = ConditionModel(
            type=ProvableFact(value="Savings Bond", evidence="Fake Entry"),
            min_amount=5000,
            max_amount=49999,
            term_years=6,
            interest_rate=ProvableFact(value="2.50%", evidence="Fake Entry: 2.50% (internal)")
        )
        
        # 3. Get Node/Rel Properties
        node_props = get_node_props(fake_condition)
        node_props['key'] = fake_key
        rel_props = get_rel_props(fake_condition)

        # 4. Open a DB session and call the Corroborator directly
        driver = GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD))
        with driver.session() as session:
            
            # Deactivate old facts from this FAKE source first
            # KORREKTUR: {{is_active: true}} -> {is_active: true}
            session.run("""
                MATCH (n:Condition)-[r:FROM_SOURCE {is_active: true}]->(q:Source {url: $url})
                SET r.is_active = false
            """, url=fake_url)
            
            # Call the Corroborator transaction
            session.execute_write(
                _tx_corroborate_and_ingest,
                "Condition",     
                "key",           
                fake_key,       
                node_props,     
                rel_props,       
                fake_meta        
            )
            
            # 5. Link the (now active) condition to the product
            session.run("""
                MATCH (p:Product {name: $product_name})
                MATCH (k:Condition {key: $key})
                MERGE (p)-[:HAS_CONDITION]->(k)
            """, product_name=fake_product_name, key=fake_key)
            
        print(f"🔬 TEST: Fake condition '{fake_key}' for source '{fake_url}' ingested successfully.")
        
    except Exception as e:
        print(f"🔬 TEST ERROR while ingesting fake data: {e}")
