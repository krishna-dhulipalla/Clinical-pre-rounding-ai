import os
import requests
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

FHIR_SERVER_URL = os.getenv("FHIR_SERVER_URL") or os.getenv("FHIR_BASE_URL", "http://localhost:8080/fhir")

def load_bundle(file_path: Path):
    """
    Loads a FHIR Bundle (JSON) into the HAPI FHIR server.
    """
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return

    try:
        with open(file_path, "r", encoding='utf-8') as f:
            bundle = json.load(f)
        
        # Ensure it is a transaction or batch bundle
        if bundle.get("resourceType") != "Bundle":
            logger.error(f"File {file_path.name} is not a FHIR Bundle.")
            return

        # POST to the base URL (HAPI FHIR handles the transaction)
        headers = {"Content-Type": "application/fhir+json"}
        response = requests.post(FHIR_SERVER_URL, json=bundle, headers=headers, timeout=(5, 60))
        
        if response.status_code in [200, 201]:
            logger.info(f"Successfully loaded bundle: {file_path.name}")
        else:
            logger.error(f"Failed to load bundle {file_path.name}. Status: {response.status_code}, Response: {response.text[:200]}")

    except Exception as e:
        logger.error(f"Error processing {file_path.name}: {e}")

def main():
    """
    Traverses a data directory and loads all .json files as FHIR Bundles.
    """
    data_dir = ROOT / "data"
    if not data_dir.exists():
        logger.warning(f"Data directory '{data_dir}' not found. Please create it and place Synthea bundles there.")
        return

    json_files = list(data_dir.glob("*.json"))
    if not json_files:
        logger.warning(f"No .json files found in '{data_dir}'.")
        return

    logger.info(f"Found {len(json_files)} FHIR bundles to load...")
    for json_file in json_files:
        load_bundle(json_file)

if __name__ == "__main__":
    main()
