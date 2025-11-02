# Ontology-Guided Knowledge Extraction (ODKE+ Inspired)

This repository contains an end-to-end pipeline for knowledge extraction, inspired by the "ODKE+: Ontology-Guided Open-Domain Knowledge Extraction with LLMs" paper by Khorshidi et al. (Apple, 2025): https://arxiv.org%2Fpdf%2F2509.04696

This PoC implements the core ODKE+ architecture:
* **Ontology-Guided Extraction:** Uses Pydantic and Gemini's `response_schema` feature as a modern alternative to "ontology snippets" described in the paper.
* **LLM-based Grounder:** A second, lightweight LLM validates extracted facts against their source evidence to prevent hallucinations.
* **Corroborator:** A robust ingestion process that resolves conflicts using a "Freshness > Trust" scoring algorithm.
* **Staleness Handling:** Automatically deactivates facts that are no longer found at the source.
* **Inference Layer:** Rebuilds inferred relationships based *only* on the currently active facts.

## Tech Stack

* **Python 3.10+**
* **Google Gemini (Pro & Flash):** For Extraction and Grounding
* **Pydantic:** For Ontology definition
* **Neo4j:** Graph Database
* **BeautifulSoup4:** Web Crawler

## How to Run

### 1. Setup

1.  Clone the repository and navigate into the directory:
    ```bash
    git clone [https://github.com/your-username/your-repo-name.git](https://github.com/your-username/your-repo-name.git)
    cd your-repo-name
    ```
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Create your `.env` file from the example:
    ```bash
    cp .env.example .env
    ```
4.  Edit the `.env` file and add your **Neo4j** and **Google AI Studio** API keys.

### 2. Run the Pipeline

Execute the main script. This will clear the database, crawl all sources, and run the full ETL (Extract, Transform, Load) pipeline.

```bash
python main.py
```

### 3. Validate the Results

Run the query script to validate the final state of the graph. This script demonstrates how the Corroborator correctly handled conflicts (e.g., the fake internal data overriding the public web data).

```bash
python query.py
```

**You can also view the created Knowledge Graph in the NEO4J console:**
<img width="513" height="430" alt="Bildschirmfoto 2025-11-02 um 21 00 57" src="https://github.com/user-attachments/assets/ce184726-cb79-4a48-8401-4f8d0ab7dce9" />


### Acknowledgments
This project is a PoC implementation based on the architecture described in the ODKE+ paper. All credit for the core architectural concepts belongs to the original authors.
Khorshidi, S., et al. (2025). ODKE+: Ontology-Guided Open-Domain Knowledge Extraction with LLMs. [arXiv:2509.04696 [cs.CL]].
