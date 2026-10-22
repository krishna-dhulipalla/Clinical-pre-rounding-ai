from copy import deepcopy
from typing import Protocol

from fhir.client import FHIRClient, FHIRRequestError
from .demo import resources_for
from .domain import RunRequest

REQUIRED_TYPES = ("Observation", "MedicationRequest", "MedicationAdministration")
NOT_QUERIED = ("Condition", "AllergyIntolerance", "DocumentReference")


class Source(Protocol):
    base_url: str

    def patient(self, patient_id: str) -> dict: ...
    def encounters(self, patient_id: str) -> list[dict]: ...
    def fetch(self, resource_type: str, request: RunRequest) -> list[dict]: ...


def reference_id(reference: str) -> str:
    return reference.split("/_history/")[0].rstrip("/").split("/")[-1]


def matches_reference(reference, resource_type, resource_id, base_url):
    target = reference.split("/_history/")[0].rstrip("/")
    expected = f"{resource_type}/{resource_id}"
    return target == expected or (
        base_url.startswith(("https://", "http://")) and target == f"{base_url.rstrip('/')}/{expected}"
    )


class DemoSource:
    base_url = "urn:demo"

    def patient(self, patient_id):
        return next(r for r in resources_for(patient_id) if r["resourceType"] == "Patient")

    def encounters(self, patient_id):
        return [r for r in resources_for(patient_id) if r["resourceType"] == "Encounter"]

    def fetch(self, resource_type, request):
        if request.scenario == "outage" and resource_type == "Observation":
            raise FHIRRequestError("Synthetic retrieval outage", 503)
        if request.scenario == "denied" and resource_type == "MedicationAdministration":
            raise FHIRRequestError("Synthetic access denial", 403)
        return deepcopy([r for r in resources_for(request.patient_id) if r["resourceType"] == resource_type])


class FHIRSource:
    def __init__(self, base_url: str, access_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.client = FHIRClient(base_url)
        if access_token:
            self.client.headers["Authorization"] = f"Bearer {access_token}"

    def patient(self, patient_id):
        patient = self.client.get_patient(patient_id)
        if not patient:
            raise FHIRRequestError("Patient not found", 404)
        return patient

    def encounters(self, patient_id):
        return self.client.search_encounters(patient_id)

    def fetch(self, resource_type, request):
        date_field = (
            "authoredon"
            if resource_type == "MedicationRequest"
            else "effective-time"
            if resource_type == "MedicationAdministration"
            else "date"
        )
        return self.client._search(
            resource_type,
            {
                "subject": f"Patient/{request.patient_id}",
                "context"
                if resource_type == "MedicationAdministration"
                else "encounter": f"Encounter/{request.encounter_id}",
                date_field: [f"ge{request.window_start.isoformat()}", f"le{request.as_of.isoformat()}"],
                "_count": 100,
            },
        )
