import requests
from typing import Dict, List, Optional, Any
import logging
from urllib.parse import quote, urljoin, urlsplit

logger = logging.getLogger(__name__)

class FHIRRequestError(RuntimeError):
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code

class FHIRClient:
    def __init__(self, base_url: str = "http://localhost:8080/fhir"):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Accept": "application/fhir+json"}
        self.timeout = (5, 30)

    def _get(self, resource_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Helper to perform GET requests."""
        return self._request(f"{self.base_url}/{resource_type}", params)

    def _request(self, url: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as e:
            status = e.response.status_code if e.response is not None else None
            logger.error("FHIR request failed (%s)", type(e).__name__)
            raise FHIRRequestError("FHIR retrieval failed. Check server availability and access.", status) from e
        except ValueError as e:
            raise FHIRRequestError("FHIR server returned invalid JSON.") from e
        if not isinstance(payload, dict):
            raise FHIRRequestError("FHIR server returned an invalid resource.")
        return payload

    def _search(self, resource_type: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Read every search page or fail explicitly; never summarize a partial fetch."""
        bundle = self._get(resource_type, params)
        resources = []
        visited = set()
        for _ in range(100):
            if bundle.get("resourceType") != "Bundle":
                raise FHIRRequestError("FHIR search did not return a Bundle.")
            for entry in bundle.get("entry", []):
                resource = entry.get("resource", {})
                if resource.get("resourceType") == "OperationOutcome":
                    if any(issue.get("severity") in ("fatal", "error") for issue in resource.get("issue", [])):
                        raise FHIRRequestError("FHIR search reported an error; retrieval is incomplete.")
                elif resource.get("resourceType") == resource_type:
                    resources.append(resource)
            next_link = next((link.get("url") for link in bundle.get("link", []) if link.get("relation") == "next"), None)
            if not next_link:
                return resources
            next_url = urljoin(self.base_url + "/", next_link)
            base, target = urlsplit(self.base_url), urlsplit(next_url)
            if (base.scheme, base.netloc) != (target.scheme, target.netloc):
                raise FHIRRequestError("FHIR pagination points to another server.")
            if next_url in visited:
                raise FHIRRequestError("FHIR pagination repeated a page; retrieval is incomplete.")
            visited.add(next_url)
            bundle = self._request(next_url)
        raise FHIRRequestError("FHIR search exceeded the page limit; narrow the query.")

    def get_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific Patient resource by ID."""
        try:
            patient = self._get(f"Patient/{quote(patient_id, safe='')}")
        except FHIRRequestError as e:
            if e.status_code == 404:
                return None
            raise
        if patient.get("resourceType") != "Patient":
            raise FHIRRequestError("FHIR read did not return a Patient.")
        return patient

    def search_encounters(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        Fetch Encounters for a patient.
        """
        params = {
            "subject": f"Patient/{patient_id}",
            "_sort": "-date",
            "_count": 50
        }
        return self._search("Encounter", params)

    def search_observations(self, patient_id: str, category: str = None) -> List[Dict[str, Any]]:
        """
        Fetch Observations (Labs, Vitals) for a patient.
        """
        params = {
            "subject": f"Patient/{patient_id}",
            "_sort": "-date",
            "_count": 100
        }
        if category:
            params["category"] = category
            
        return self._search("Observation", params)

    def search_medication_requests(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        Fetch MedicationRequests for a patient.
        """
        params = {
            "subject": f"Patient/{patient_id}",
            "_sort": "-authoredon",
            "_count": 50
        }
        return self._search("MedicationRequest", params)
