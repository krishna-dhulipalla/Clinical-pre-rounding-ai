"""Demo heuristics; these rules have not been clinically validated."""

def _to_float(value):
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _contains_any(text, candidates):
    lowered = (text or "").lower()
    return any(token in lowered for token in candidates)


def _classify_fact(fact):
    name = (fact.name or "").lower()
    value = _to_float(fact.value)
    fact_type = fact.type.value

    if fact_type == "OTHER" and "warning" in name:
        return "info", "Data quality warning"

    if value is None:
        return "info", "No numeric rule for this value"

    # Thresholds below only apply to their stated units. Unknown units need review.
    unit = (fact.unit or "").strip().lower()
    supported_units = set()
    if fact_type == "LAB":
        if _contains_any(name, ["hemoglobin", "hgb"]):
            supported_units = {"g/dl"}
        elif "glucose" in name or "creatinine" in name:
            supported_units = {"mg/dl"}
        elif "potassium" in name or "sodium" in name:
            supported_units = {"mmol/l", "meq/l"}
        elif _contains_any(name, ["white blood cell", "wbc"]):
            supported_units = {"10*3/ul", "10^3/ul", "10*9/l", "10^9/l", "k/ul"}
    elif fact_type == "VITAL":
        if _contains_any(name, ["temperature", "temp"]):
            supported_units = {"cel", "c", "celsius", "degf", "f", "fahrenheit"}
        elif _contains_any(name, ["oxygen saturation", "spo2", "o2 sat"]):
            supported_units = {"%"}
        elif _contains_any(name, ["systolic", "diastolic"]):
            supported_units = {"mmhg", "mm[hg]"}
        elif _contains_any(name, ["heart rate", "pulse rate", "respiratory rate", "respiration"]) or name.strip() in {"hr", "rr", "pulse"}:
            supported_units = {"/min", "beats/min", "bpm", "breaths/min"}
    if not supported_units or unit not in supported_units:
        return "info", "No demo rule for this measurement and unit"

    if fact_type == "LAB":
        if _contains_any(name, ["hemoglobin", "hgb"]):
            if value < 8:
                return "critical", "Hemoglobin critically low"
            if value < 10:
                return "high", "Hemoglobin below expected range"
        if "glucose" in name:
            if value < 54 or value > 300:
                return "critical", "Glucose in critical range"
            if value < 70 or value > 180:
                return "high", "Glucose out of target range"
        if "potassium" in name:
            if value < 2.8 or value > 6.0:
                return "critical", "Potassium in critical range"
            if value < 3.2 or value > 5.5:
                return "high", "Potassium out of target range"
        if "sodium" in name:
            if value < 125 or value > 155:
                return "critical", "Sodium in critical range"
            if value < 130 or value > 150:
                return "high", "Sodium out of target range"
        if "creatinine" in name and value >= 3.0:
            return "high", "Creatinine elevated"
        if _contains_any(name, ["white blood cell", "wbc"]) and value >= 20:
            return "high", "WBC elevated"

    if fact_type == "VITAL":
        if _contains_any(name, ["temperature", "temp"]):
            temp_c = value
            unit = (fact.unit or "").lower()
            if unit in ["degf", "f", "fahrenheit"]:
                temp_c = (value - 32) * 5.0 / 9.0
            if temp_c >= 39.0 or temp_c < 35.0:
                return "critical", "Temperature in critical range"
            if temp_c >= 38.0:
                return "high", "Fever range temperature"
        if _contains_any(name, ["heart rate", "pulse rate"]) or name.strip() in {"hr", "pulse"}:
            if value >= 130 or value < 40:
                return "critical", "Heart rate in critical range"
            if value >= 110 or value < 50:
                return "high", "Heart rate outside normal range"
        if _contains_any(name, ["respiratory rate", "respiration"]) or name.strip() == "rr":
            if value >= 30 or value < 8:
                return "critical", "Respiratory rate in critical range"
            if value >= 24 or value < 10:
                return "high", "Respiratory rate outside normal range"
        if _contains_any(name, ["oxygen saturation", "spo2", "o2 sat"]):
            if value < 88:
                return "critical", "Oxygen saturation in critical range"
            if value < 92:
                return "high", "Oxygen saturation below target"
        if "systolic" in name:
            if value >= 180 or value < 80:
                return "critical", "Systolic pressure in critical range"
            if value >= 160 or value < 90:
                return "high", "Systolic pressure outside normal range"
        if "diastolic" in name:
            if value >= 120 or value < 50:
                return "critical", "Diastolic pressure in critical range"
            if value >= 100 or value < 60:
                return "high", "Diastolic pressure outside normal range"

    return "normal", "No active heuristic trigger"
