from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation

from .domain import EvidenceFact, RunRequest, digest


def event_time(resource):
    raw = (
        resource.get("effectiveDateTime")
        or resource.get("effectiveInstant")
        or resource.get("effectivePeriod", {}).get("start")
        or resource.get("authoredOn")
    )
    if not raw:
        return None, "unknown"
    # Date-only values cannot establish a precise review boundary.
    precision = "instant" if "T" in raw else "day" if len(raw) == 10 else "month" if len(raw) == 7 else "year"
    if resource.get("effectivePeriod"):
        precision = "period"
    try:
        padded = raw + ("-01-01" if len(raw) == 4 else "-01" if len(raw) == 7 else "")
        value = datetime.fromisoformat(padded.replace("Z", "+00:00"))
        if "T" in raw and value.tzinfo is None:
            return None, "unknown"
        return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc), precision
    except (ValueError, TypeError):
        return None, "unknown"


def concept_name(concept):
    coding = next((c for c in concept.get("coding", []) if c.get("system") == "http://loinc.org"), None)
    coding = coding or next(iter(concept.get("coding", [])), {})
    return concept.get("text") or coding.get("display") or coding.get(
        "code"
    ) or "Unlabeled measurement", coding


def decimal_text(value):
    result = format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")
    return "0" if result in {"-0", ""} else result


def extract_value(part):
    quantity = part.get("valueQuantity")
    if quantity is not None:
        unit = quantity.get("code") or quantity.get("unit")
        raw = quantity.get("value")
        numeric = None
        if raw is not None:
            try:
                number = Decimal(str(raw))
                if number.is_finite():
                    if unit in {"g/L", "gram/liter"}:
                        number, unit = number / 10, "g/dL"
                    elif unit in {"[degF]", "degF", "F"}:
                        number, unit = (
                            ((number - 32) * Decimal(5) / Decimal(9)).quantize(Decimal("0.1")),
                            "Cel",
                        )
                    numeric = decimal_text(number)
            except InvalidOperation:
                pass
        comparator = quantity.get("comparator")
        value = numeric if numeric is not None else "Value unavailable"
        return f"{comparator} {value}" if comparator else value, numeric, unit, comparator
    if "valueCodeableConcept" in part:
        return concept_name(part["valueCodeableConcept"])[0], None, None, None
    for key in ("valueString", "valueBoolean", "valueInteger", "valueDateTime", "valueTime"):
        if key in part:
            return str(part[key]), None, None, None
    if "valueRange" in part:
        interval = part["valueRange"]
        return (
            f"Range {interval.get('low', {}).get('value', '?')} to {interval.get('high', {}).get('value', '?')}",
            None,
            interval.get("low", {}).get("code"),
            None,
        )
    absent = part.get("dataAbsentReason")
    if absent:
        return f"Unavailable: {concept_name(absent)[0]}", None, None, None
    if any(key.startswith("value") for key in part):
        return "Unsupported structured value; inspect source", None, None, None
    return "Value unavailable", None, None, None


def resource_identity(resource):
    content_hash = digest(resource)
    version = str(resource.get("meta", {}).get("versionId") or f"content-{content_hash[:16]}")
    return f"{resource['resourceType']}/{resource['id']}/_history/{version}", version, content_hash


def normalize_resource(resource: dict, request: RunRequest) -> list[EvidenceFact]:
    key, version, content_hash = resource_identity(resource)
    timestamp, precision = event_time(resource)
    common = dict(
        resource_key=key,
        version=version,
        timestamp=timestamp,
        date_precision=precision,
        status=resource.get("status", "unknown"),
        resource_hash=content_hash,
        stale=bool(timestamp and request.as_of - timestamp > timedelta(hours=12)),
    )
    if resource["resourceType"] in {"MedicationRequest", "MedicationAdministration"}:
        concept = resource.get("medicationCodeableConcept", {})
        name, coding = concept_name(concept)
        if name == "Unlabeled measurement":
            name = (
                resource.get("medicationReference", {}).get("display")
                or "Medication reference; inspect source"
            )
        return [
            EvidenceFact(
                **common,
                evidence_id="ev_" + digest([key, "medication"])[:20],
                path="medicationCodeableConcept",
                kind=resource["resourceType"],
                name=name,
                value=resource.get("status", "unknown"),
                code_system=coding.get("system", ""),
                code=coding.get("code", ""),
            )
        ]
    parts = []
    if any(k.startswith("value") for k in resource) or not resource.get("component"):
        parts.append(("", resource))
    parts.extend(
        (f"component[{index}].", component) for index, component in enumerate(resource.get("component", []))
    )
    facts = []
    for prefix, part in parts:
        name, coding = concept_name(part.get("code", {}))
        value, numeric, unit, comparator = extract_value(part)
        value_key = next((k for k in part if k.startswith("value")), "dataAbsentReason")
        path = prefix + value_key
        facts.append(
            EvidenceFact(
                **common,
                evidence_id="ev_" + digest([key, path])[:20],
                path=path,
                kind="Observation",
                name=name,
                value=value,
                numeric_value=numeric,
                unit=unit,
                unit_system=part.get("valueQuantity", {}).get("system"),
                comparator=comparator,
                code_system=coding.get("system", ""),
                code=coding.get("code", ""),
            )
        )
    return facts


def safe_label(fact):
    """Only controlled labels/codes are included in model-facing ranking input."""
    known = {
        "2160-0": "Creatinine",
        "718-7": "Hemoglobin",
        "8867-4": "Heart rate",
        "8310-5": "Temperature",
        "2951-2": "Sodium",
    }
    if fact.code_system == "http://loinc.org" and fact.code in known:
        return known[fact.code]
    return fact.kind  # Free-text source labels never go to the hosted model.
