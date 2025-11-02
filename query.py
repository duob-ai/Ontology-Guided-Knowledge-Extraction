from neo4j import GraphDatabase
import config

def query_graph():
    """Runs comprehensive test queries against the graph to validate the entire data structure."""
    driver = GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD))
    
    with driver.session() as session:
        print("\n" + "="*50 + "\nRUNNING GRAPH QUERIES\n" + "="*50)

        # --- Query 1 ---
        print("\n--- Query 1: Overview of all *active* products with type and risk class ---")
        query1 = """
        MATCH (p:Product)-[r_p:FROM_SOURCE]->() WHERE r_p.is_active = true
        MATCH (pt:ProductType)<-[:HAS_PRODUCT_TYPE]-(p)-[:HAS_RISK_CLASS]->(s:RiskClass)
        RETURN p.name AS Product, pt.name AS Type, s.risk_class AS Risk
        ORDER BY Risk, Type, Product
        """
        result1 = session.run(query1)
        for record in result1: print(f"- {record['Product']} (Type: {record['Type']}, Risk: {record['Risk']})")

        # --- Query 2 ---
        print("\n--- Query 2: Which *active* employees work in which *active* branch? ---")
        query2 = """
        MATCH (m:Employee)-[r_m:FROM_SOURCE]->() WHERE r_m.is_active = true
        MATCH (f:Branch)-[r_f:FROM_SOURCE]->() WHERE r_f.is_active = true
        MATCH (m)-[:WORKS_IN]->(f)
        RETURN f.name AS Branch, collect(DISTINCT m.name) AS Employees
        ORDER BY Branch
        """
        result2 = session.run(query2)
        print("(This query now filters out 'stale' employees)")
        for record in result2:
            print(f"Branch '{record['Branch']}':")
            for employee in record['Employees']: print(f"  - {employee}")

        # --- Query 3 ---
        print("\n--- Query 3: Which *active* advisors can advise on *active* interest products? ---")
        query3 = """
        MATCH (m:Employee)-[r_m:FROM_SOURCE]->() WHERE r_m.is_active = true
        MATCH (p:Product)-[r_p:FROM_SOURCE]->() WHERE r_p.is_active = true
        MATCH (m)-[:ADVISES_ON]->(p) 
        RETURN m.name AS Advisor, p.name AS Product
        ORDER BY Advisor, Product
        """
        result3 = session.run(query3)
        for record in result3: print(f"- {record['Advisor']} can advise on '{record['Product']}'")

        # --- Query 4 ---
        print("\n--- Query 4: Who in Bispingen can *currently* help me with a secure 5-year investment? ---")
        query4 = """
        MATCH (p:Product)-[r_p:FROM_SOURCE]->() WHERE r_p.is_active = true
        MATCH (k:Condition)-[r_k:FROM_SOURCE]->() WHERE r_k.is_active = true
        MATCH (p)-[:HAS_CONDITION]->(k) 
        WHERE k.min_amount <= 60000 AND (k.max_amount IS NULL OR k.max_amount >= 60000) AND k.term_years = 5
        WITH p
        MATCH (p)-[:HAS_RISK_CLASS]->(s:RiskClass) 
        WHERE s.risk_class IN ['1', '2']
        MATCH (m:Employee)-[r_m:FROM_SOURCE]->() WHERE r_m.is_active = true
        MATCH (m)-[:ADVISES_ON]->(p) 
        MATCH (m)-[:WORKS_IN]->(f:Branch)
        WHERE f.name CONTAINS 'Bispingen'
        RETURN DISTINCT m.name AS ContactPerson, m.email AS Email
        """
        result4 = session.run(query4)
        print("Possible *active* contact persons in the Bispingen branch:")
        for record in result4: print(f"- {record['ContactPerson']} (Email: {record['Email']})")

        # --- Query 5 ---
        print("\n--- Query 5: In which *active* branches does Martin Zado work...? ---")
        employee_name = "Martin Zado"
        query5 = """
        CYPHER 25
        MATCH (m:Employee {name: $name})
        LET branches = COLLECT {
            MATCH (m)-[:WORKS_IN]->(f:Branch)
            MATCH (f)-[r_f:FROM_SOURCE]->() WHERE r_f.is_active = true
            RETURN f.name
        }
        LET advised_products_sk1 = COLLECT {
            MATCH (m)-[:ADVISES_ON]->(p:Product) 
            MATCH (p)-[r_p:FROM_SOURCE]->() WHERE r_p.is_active = true
            MATCH (p)-[:HAS_RISK_CLASS]->(s:RiskClass {risk_class: '1'})
            RETURN p.name
        }
        RETURN m.name AS Employee, m.email AS Email, m.phone AS Phone, branches, advised_products_sk1
        """
        try:
            result5 = session.run(query5, name=employee_name)
            record5 = result5.single() 
            if not record5: print(f"Employee '{employee_name}' not found.")
            else:
                print(f"Details for: {record5['Employee']}")
                print(f"  - Email: {record5['Email']}, Phone: {record5['Phone']}")
                print(f"  - Works in *active* branches: {record5['branches']}")
                print(f"  - Advises on *active* products (SK1): {record5['advised_products_sk1']}")
        except Exception as e: print(f"ERROR during Query 5: {e}")

        # --- Query 6 ---
        print("\n--- Query 6 (Debug): Where does the 'Bispingen Branch' fact come from (all versions)? ---")
        query6 = """
        MATCH (f:Branch)-[r:FROM_SOURCE]->(q:Source)
        WHERE f.name CONTAINS 'Bispingen'
        RETURN f.name AS Fact, q.url AS Source, r.retrieved_at AS Timestamp, r.is_active AS Active
        ORDER BY r.retrieved_at DESC
        """
        result6 = session.run(query6)
        for record in result6: print(f"- Fact: '{record['Fact']}' @ {record['Timestamp']} (Source: {record['Source']}) [Active: {record['Active']}]")
        
        # --- Query 7 ---
        print("\n--- Query 7 (Debug): What facts were *ever* extracted from the savings bond page? ---")
        query7 = """
        MATCH (n)-[r:FROM_SOURCE]->(q:Source)
        WHERE q.url CONTAINS 'sparbrief.html'
        RETURN labels(n) AS Type, COALESCE(n.name, n.key, n.question) AS NameOrKey, r.retrieved_at AS Timestamp, r.is_active AS Active
        ORDER BY Timestamp DESC, Type, NameOrKey
        """
        result7 = session.run(query7)
        print(f"Facts from savings bond page (newest first):")
        for record in result7: print(f"- [{record['Type'][0]}] {record['NameOrKey']} (Retrieved: {record['Timestamp']}) [Active: {record['Active']}]")
        
        # --- Query 8 ---
        print("\n--- Query 8 (Debug): What is the *evidence* for a branch named Bispingen? ---")
        query8 = """
        MATCH (f:Branch)-[r:FROM_SOURCE]->(q:Source)
        WHERE f.name CONTAINS 'Bispingen' AND r.name_evidence IS NOT NULL
        RETURN f.name AS FactValue, r.name_evidence AS FactEvidence, q.url AS Source, r.retrieved_at AS Timestamp, r.is_active AS Active
        ORDER BY r.retrieved_at DESC
        LIMIT 1
        """
        result8 = session.run(query8)
        record8 = result8.single()
        if record8: print(f"- Fact (found): '{record8['FactValue']}' (Newest from {record8['Timestamp']}) [Active: {record8['Active']}]\n  Evidence: '{record8['FactEvidence']}'")
        else: print("No evidence found for a branch named 'Bispingen'.")

        # --- Query 9 ---
        print("\n--- Query 9: 'How much interest for 30,000€ for 5 years?' ---")
        investment_amount = 30000
        investment_years = 5
        query9 = """
        MATCH (p:Product)-[:HAS_CONDITION]->(k:Condition)
        MATCH (k)-[r_k:FROM_SOURCE]->()
        WHERE r_k.is_active = true 
        
        AND k.min_amount <= $amount 
        AND (k.max_amount IS NULL OR k.max_amount >= $amount) 
        AND k.term_years = $years
        
        RETURN p.name AS Product, k.interest_rate AS InterestRate, k.type AS ConditionType
        """
        result9 = session.run(query9, amount=investment_amount, years=investment_years)
        print(f"Results for an *active* investment of {investment_amount}€ over {investment_years} years:")
        records9 = list(result9)
        if not records9: print("  -> No matching *active* conditions found.")
        else:
            for record in records9: print(f"  - Product: '{record['Product']}', Interest Rate: {record['InterestRate']} (Type: {record['ConditionType']})")

    driver.close()

# allow the file to be run as a script
if __name__ == "__main__":
    query_graph()
    
    
