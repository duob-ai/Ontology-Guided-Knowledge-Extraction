import os
from google.colab import userdata

# --- API Keys ---
NEO4J_URI = userdata.get('NEO4J_URI')
NEO4J_USERNAME = userdata.get('NEO4J_USERNAME')
NEO4J_PASSWORD = userdata.get('NEO4J_PASSWORD')
GOOGLE_API_KEY = userdata.get('GOOGLE_API_KEY')

# --- Target URLs for webscraping ---
TARGET_URLS = [
    "https://www.vblh.de/privatkunden/geldanlage/sparbrief.html",
    "https://www.vblh.de/privatkunden/geldanlage/tagesgeld.html"
]

FILIAL_URLS = [
    "https://www.vblh.de/ueber-uns/filialen/bispingen.html",
    "https://www.vblh.de/ueber-uns/filialen/soltau.html"
]

# --- Corroborator Configuration ---
SOURCE_TRUST_SCORES = {
    "https://www.vblh.de/": 0.9,          # Trust scores for different types of sources
    "https://intern.vblh.de/": 0.95       
}

def get_trust_score(url: str) -> float:
    """Findet den passenden Trust Score für eine gegebene URL."""
    for domain, score in SOURCE_TRUST_SCORES.items():
        if url.startswith(domain):
            return score
    return 0.5 # some standard-Score
