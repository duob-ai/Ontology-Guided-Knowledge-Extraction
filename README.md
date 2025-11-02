ODKE+-Inspired Knowledge Graph Pipeline
This repository contains a production-grade, end-to-end pipeline for ontology-guided knowledge extraction (KGE). The architecture is heavily inspired by the "ODKE+: Ontology-Guided Open-Domain Knowledge Extraction with LLMs" paper by Khorshidi et al. (Apple, 2025) .

This proof-of-concept implements the core components of the ODKE+ system—including a Grounder and Corroborator —using a modern Python stack: Google Gemini, Pydantic, and Neo4j.




Key Features
This pipeline mimics the key components described in the ODKE+ paper  to ensure data is fresh, accurate, and trustworthy.

Ontology-Guided Extraction: Uses Pydantic models (our "ontology") to guide and enforce the schema of the LLM's structured output.

LLM-based Grounding: Implements a "lightweight Grounder" using a second, high-speed LLM (Gemini Flash) to verify each extracted fact against its source evidence, reducing hallucinations.



Data Corroboration: A sophisticated ingestion process that resolves conflicts between multiple sources using a "Freshness > Trust" scoring algorithm.


Staleness & Deletion Handling: A "Staleness Check" runs before each ingestion, automatically deactivating facts that are no longer present at the source (solving the "deleted employee" problem).

Atomic Ingestion: All database writes (deactivation, corroboration, and activation) are wrapped in a single, atomic Neo4j transaction for data integrity.

Inference Layer: Automatically cleans and rebuilds inferred relationships (e.g., :ADVISES_ON) based only on the currently active nodes in the graph.

Architecture & Pipeline Flow
The entire process is orchestrated in main.py and follows this data flow:

Crawl (pipeline.get_webpage_content): A target URL is provided.

Extract (pipeline.extract_structured_data): The webpage text is sent to Gemini Pro (LLM 1), which is forced to return a JSON object matching our Pydantic ontology.

Ground (pipeline.ground_package): The extracted package is passed to a "Grounder" module. This module iterates over every ProvableFact and uses Gemini Flash (LLM 2) to validate that the value is supported by the evidence. Ungrounded facts are removed.

Ingest & Corroborate (pipeline.ingest_..._package): The "clean" package is passed to the ingestion transaction. a. Staleness Check: All facts from this specific source are set to is_active = false. b. Corroborate: For each new fact, the system checks for an active competitor from a different source. c. Score & Write: The Corroborator applies a "Freshness > Trust" algorithm to determine the winner. The winning fact's data is written to the node (e.g., Condition.interest_rate) and its FROM_SOURCE relationship is set to is_active = true.

Infer (pipeline.create_inferred_relationships): All old inferred relationships (:ADVISES_ON) are deleted and rebuilt from scratch, connecting only the active nodes.

A Modern Approach to "Ontology-Guiding"

The ODKE+ paper describes a system for generating "ontology snippets" to be injected directly into the LLM prompt.

This project implements a modern alternative:

We use the native response_schema feature of the Google Gemini API. By passing our Pydantic models (from ontology.py) directly to the API, we delegate the task of schema enforcement to the API layer. This achieves the same goal of "ontology-guided" extraction  with extremely high reliability and removes the need for complex prompt engineering, as the API guarantees a valid Pydantic object as output.


Tech Stack
Python 3.10+

Google Gemini (Pro & Flash): For Extraction and Grounding.

Pydantic: For defining the ontology (ontology.py).

Neo4j: As the graph database backend.

BeautifulSoup4: For web crawling.

How to Run
1. Setup & Installation

Clone the repository:

Bash
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name
Install dependencies:

Bash
pip install -r requirements.txt
Set up your environment:

Create a .env file in the root directory. You can copy the template:

Bash
cp .env.example .env
Edit the .env file and add your API keys for Neo4j and Google AI Studio.

Ensure your Neo4j database is running and accessible.

2. Run the Pipeline

Execute the main orchestration script. This will clear the database, crawl all sources, and run the full ETL pipeline.

Bash
python main.py

3. Validate the Results

After the ingestion is complete, run the query script to see the final state of the graph and test the logic.

Bash
python query.py
You can observe the Corroborator logic in action by inspecting the output of Query 7 and Query 9. The "Volksbank Sparbrief_5000_6" condition will show is_active: false for the public website and is_active: true for the fake internal source (which had a higher trust score). The final query for an investment (Query 9) will correctly return the 2.50% interest rate from the "winner" fact.

Project Structure
├── .env.example        # Template for environment variables
├── .gitignore          # Hides secret .env file
├── requirements.txt    # Project dependencies
|
├── config.py           # API Keys, Target URLs, Trust Scores
├── ontology.py         # All Pydantic models and schemas (The "Ontology")
├── pipeline.py         # Core logic: Crawl, Extract, Ground, Ingest, Infer
├── main.py             # Main script to orchestrate and run the pipeline
└── query.py            # Test queries to validate the graph state

Acknowledgments
This project is a proof-of-concept implementation based on the architecture described in the following paper. All credit for the core architectural concepts (Grounder, Corroborator, Staleness Checks) belongs to the original authors.

Khorshidi, S., Nikfarjam, A., Shankar, S., Sang, Y., Govind, Y., Jang, H., Kasgari, A., McClimans, A., Soliman, M., Konda, V., Fakhry, A., & Qi, X. (2025). ODKE+: Ontology-Guided Open-Domain Knowledge Extraction with LLMs. [arXiv:2509.04696 [cs.CL]].
