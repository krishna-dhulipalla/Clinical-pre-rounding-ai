from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from .models import Fact, FactType
from .normalization import normalize_unit

def parse_fhir_date(date_str: str) -> datetime:
    """Parses FHIR date strings which can be YYYY, YYYY-MM, or YYYY-MM-DDTHH:MM:SS."""
    if not date_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        if len(date_str) == 4:
            date_str += "-01-01"
        elif len(date_str) == 7:
            date_str += "-01"
        parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return datetime.min.replace(tzinfo=timezone.utc)

def flatten_observation(resource: Dict[str, Any]) -> Fact:
    patient_ref = resource.get("subject", {}).get("reference", "")
    patient_id = patient_ref.split("/")[-1] if "/" in patient_ref else patient_ref
    
    # Determine type (Lab vs Vital)
    categories = resource.get("category", [])
    fact_type = FactType.OTHER
    for cat in categories:
        for coding in cat.get("coding", []):
            code = coding.get("code", "")
            if code == "laboratory":
                fact_type = FactType.LAB
            elif code == "vital-signs":
                fact_type = FactType.VITAL

    # Get Name
    code_text = resource.get("code", {}).get("text")
    if not code_text:
        # Try finding a display name in codings
        codings = resource.get("code", {}).get("coding", [])
        if codings:
            code_text = codings[0].get("display", "Unknown Observation")
        else:
            code_text = "Unknown Observation"

    # Get Value
    value = "N/A"
    unit = None
    if "valueQuantity" in resource:
        vq = resource["valueQuantity"]
        raw_val = str(vq.get("value"))
        raw_unit = vq.get("unit") or vq.get("code")
        # Normalize
        value, unit = normalize_unit(raw_val, raw_unit)
        if vq.get("comparator"):
            value = f"{vq['comparator']} {value}"
    elif "valueString" in resource:
        value = resource["valueString"]

    timestamp = parse_fhir_date(
        resource.get("effectiveDateTime")
        or resource.get("effectivePeriod", {}).get("start")
        or resource.get("issued")
    )
    
    return Fact(
        patient_id=patient_id,
        timestamp=timestamp,
        type=fact_type,
        name=code_text,
        value=value,
        unit=unit,
        status=resource.get("status"),
        source_id=f"Observation/{resource.get('id')}"
    )

def flatten_medication_request(resource: Dict[str, Any]) -> Fact:
    patient_ref = resource.get("subject", {}).get("reference", "")
    patient_id = patient_ref.split("/")[-1] if "/" in patient_ref else patient_ref
    
    # Get Med Name
    med_name = "Unknown Medication"
    if "medicationCodeableConcept" in resource:
        codings = resource["medicationCodeableConcept"].get("coding", [])
        if codings:
            med_name = codings[0].get("display", "Unknown Medication")
        else:
            med_name = resource["medicationCodeableConcept"].get("text", "Unknown Medication")
            
    timestamp = parse_fhir_date(resource.get("authoredOn"))
    
    return Fact(
        patient_id=patient_id,
        timestamp=timestamp,
        type=FactType.MED_ORDER,
        name=med_name,
        value="Ordered", # Dosage instructions could be parsed here
        status=resource.get("status"),
        source_id=f"MedicationRequest/{resource.get('id')}"
    )

def flatten_encounter(resource: Dict[str, Any]) -> Fact:
    patient_ref = resource.get("subject", {}).get("reference", "")
    patient_id = patient_ref.split("/")[-1] if "/" in patient_ref else patient_ref
    
    timestamp = parse_fhir_date(resource.get("period", {}).get("start"))
    
    # Class/Type
    enc_class = resource.get("class", {})
    name = enc_class.get("display") or enc_class.get("code") or "Encounter"
    
    return Fact(
        patient_id=patient_id,
        timestamp=timestamp,
        type=FactType.ENCOUNTER,
        name=name,
        value="Encounter recorded",
        status=resource.get("status"),
        source_id=f"Encounter/{resource.get('id')}"
    )

def entry_to_facts(entry: Dict[str, Any]) -> List[Fact]:
    resource = entry.get("resource", {})
    r_type = resource.get("resourceType")
    
    if r_type == "Observation":
        # Panels such as blood pressure store individual values in component.
        facts = []
        if any(key.startswith("value") for key in resource) or not resource.get("component"):
            facts.append(flatten_observation(resource))
        for component in resource.get("component", []):
            component_resource = {
                key: value for key, value in resource.items()
                if not key.startswith("value") and key != "component"
            }
            component_resource.update(component)
            facts.append(flatten_observation(component_resource))
        return facts
    elif r_type == "MedicationRequest":
        return [flatten_medication_request(resource)]
    elif r_type == "Encounter":
        return [flatten_encounter(resource)]
    
    return []
