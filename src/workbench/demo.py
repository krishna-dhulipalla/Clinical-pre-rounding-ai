"""Synthetic fixtures with a fixed replay clock. No real patient data."""

from copy import deepcopy
from datetime import datetime, timezone

DEMO_CLOCK = datetime(2026, 10, 22, 14, tzinfo=timezone.utc)
PATIENTS = [
    {
        "id": "demo-avery",
        "name": "Avery Morgan",
        "room": "4W · 412",
        "age": 62,
        "focus": "Laboratory changes",
        "encounter_id": "enc-avery",
    },
    {
        "id": "demo-jordan",
        "name": "Jordan Lee",
        "room": "4W · 408",
        "age": 47,
        "focus": "Medication order review",
        "encounter_id": "enc-jordan",
    },
    {
        "id": "demo-riley",
        "name": "Riley Chen",
        "room": "4W · 415",
        "age": 73,
        "focus": "Data freshness review",
        "encounter_id": "enc-riley",
    },
]


def observation(patient, oid, code, name, value, unit, time, version="1", status="final", **extra):
    return {
        "resourceType": "Observation",
        "id": oid,
        "meta": {"versionId": version, "lastUpdated": time},
        "subject": {"reference": f"Patient/{patient['id']}"},
        "encounter": {"reference": f"Encounter/{patient['encounter_id']}"},
        "status": status,
        "category": [
            {"coding": [{"code": "laboratory" if code in {"2160-0", "718-7", "2951-2"} else "vital-signs"}]}
        ],
        "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": name}]},
        "effectiveDateTime": time,
        "valueQuantity": {"value": value, "system": "http://unitsofmeasure.org", "code": unit, "unit": unit},
        **extra,
    }


def resources_for(patient_id):
    patient = next((p for p in PATIENTS if p["id"] == patient_id), None)
    if patient is None:
        raise KeyError("Unknown synthetic patient")
    rows = [
        {
            "resourceType": "Patient",
            "id": patient_id,
            "name": [{"text": patient["name"]}],
            "meta": {"versionId": "1"},
        },
        {
            "resourceType": "Encounter",
            "id": patient["encounter_id"],
            "status": "in-progress",
            "meta": {"versionId": "1"},
            "subject": {"reference": f"Patient/{patient_id}"},
            "period": {"start": "2026-10-21T08:00:00Z"},
            "class": {"code": "IMP"},
        },
    ]
    old, current = (1.2, 1.8) if patient_id == "demo-avery" else (0.9, 0.9)
    rows += [
        observation(patient, "creat-before", "2160-0", "Creatinine", old, "mg/dL", "2026-10-21T18:00:00Z"),
        observation(
            patient, "creat-current", "2160-0", "Creatinine", current, "mg/dL", "2026-10-22T10:00:00Z"
        ),
        observation(patient, "hgb-before", "718-7", "Hemoglobin", 12.1, "g/dL", "2026-10-21T18:00:00Z"),
        observation(
            patient,
            "hgb-current",
            "718-7",
            "Hemoglobin",
            11.8,
            "g/dL",
            "2026-10-22T10:00:00Z",
            version="2",
            status="corrected",
        ),
        observation(patient, "hr-current", "8867-4", "Heart rate", 82, "/min", "2026-10-22T12:00:00Z"),
        observation(patient, "old-temp", "8310-5", "Body temperature", 37.1, "Cel", "2026-10-21T09:00:00Z"),
        observation(
            patient,
            "error-result",
            "2951-2",
            "Sodium",
            999,
            "mmol/L",
            "2026-10-22T09:00:00Z",
            status="entered-in-error",
        ),
        {
            "resourceType": "MedicationRequest",
            "id": "med-current",
            "meta": {"versionId": "1"},
            "status": "active",
            "intent": "order",
            "subject": {"reference": f"Patient/{patient_id}"},
            "encounter": {"reference": f"Encounter/{patient['encounter_id']}"},
            "authoredOn": "2026-10-22T08:00:00Z",
            "medicationCodeableConcept": {
                "text": "Synthetic medication order",
                "coding": [{"system": "urn:demo:medications", "code": "demo-med-1"}],
            },
            "dosageInstruction": [{"text": "Synthetic example only"}],
        },
    ]
    if patient_id == "demo-riley":
        rows = [r for r in rows if r.get("id") not in {"hr-current", "creat-current", "hgb-current"}]
        undated = observation(
            patient, "unknown-date", "8867-4", "Heart rate", 78, "/min", "2026-10-22T12:00:00Z"
        )
        undated.pop("effectiveDateTime")
        rows.append(undated)
    return deepcopy(rows)
