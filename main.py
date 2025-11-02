import config
from ontology import *
from pipeline import (
    get_webpage_content,
    extract_structured_data,
    ground_package,
    ingest_product_package,
    ingest_branch_package,
    create_inferred_relationships,
    clear_database,
    ingest_fake_data
)

def run_ingestion():
    """Executes the entire ingestion process."""
    
    # --- PHASE 0: SETUP ---
    clear_database()

    # --- PHASE 1: REAL DATA INGESTION ---
    print("\n" + "="*50 + "\nPHASE 1: STARTING REAL DATA INGESTION\n" + "="*50)

    # 1a. Process Product URLs
    for url in config.TARGET_URLS:
        print("\n" + "="*50 + f"\nProcessing PRODUCT URL: {url}\n" + "="*50)
        webpage_text = get_webpage_content(url)
        if webpage_text:
            # Step 1: LLM extracts the payload
            llm_data = extract_structured_data(text=webpage_text, schema_class=KnowledgeGraphData)
            
            if llm_data:
                # Step 2: Create metadata (Provenance & Versioning)
                provenance = ProvenanceModel(url=url, trust_score=config.get_trust_score(url))
                
                # Step 3: Bundle the extraction package
                package = ExtractionPackage[KnowledgeGraphData](metadata=provenance, data=llm_data)
                
                # --- STEP 3.5: GROUNDING ---
                grounded_package = ground_package(package)
                
                # Step 4: Pass the package to the Corroborator/Ingestor
                ingest_product_package(grounded_package) # Pass the FILTERED package

    # --- PHASE 1.5: FAKE DATA INJECTION (for Corroborator test) ---
    ingest_fake_data()

    # 1b. Process Branch URLs
    for url in config.FILIAL_URLS:
        print("\n" + "="*50 + f"\nProcessing BRANCH URL: {url}\n" + "="*50)
        webpage_text = get_webpage_content(url)
        if webpage_text:
            # Step 1: LLM extracts the payload
            llm_branch_data = extract_structured_data(text=webpage_text, schema_class=BranchData)
            
            if llm_branch_data:
                # Step 2: Create metadata
                provenance = ProvenanceModel(url=url, trust_score=config.get_trust_score(url))
                
                # Step 3: Bundle the package
                package = ExtractionPackage[BranchData](metadata=provenance, data=llm_branch_data)
                
                # --- STEP 3.5: GROUNDING ---
                grounded_package = ground_package(package)
                
                # Step 4: Pass the package to the Corroborator/Ingestor
                ingest_branch_package(grounded_package) # Pass the FILTERED package

    # --- PHASE 2: INFERENCE ---
    create_inferred_relationships()

    print("\n" + "="*50 + "\nINGESTION PROCESS COMPLETED.\n" + "="*50)

# This part allows the file to be run as a script
if __name__ == "__main__":
    run_ingestion()
