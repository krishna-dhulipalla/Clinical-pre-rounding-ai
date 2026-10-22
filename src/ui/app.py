import os
import sys
from datetime import datetime

import streamlit as st

# Add src to path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.database import SessionLocal
from db.feedback import submit_feedback
from db.models import AuditLog
from fhir.client import FHIRClient, FHIRRequestError
from ui.triage import _classify_fact
from html import escape
from main import get_fhir_base_url, run_pipeline


def _safe_iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _type_counts(facts):
    counts = {}
    for fact in facts:
        counts[fact.type.value] = counts.get(fact.type.value, 0) + 1
    return counts


def _build_annotated_fact(fact, idx):
    severity, reason = _classify_fact(fact)
    return {
        "idx": idx,
        "fact": fact,
        "severity": severity,
        "reason": reason,
        "label": f"{idx + 1}. {severity.upper()} | {fact.type.value} | {fact.name} | {fact.timestamp.strftime('%Y-%m-%d %H:%M')}",
    }


def _severity_rank(severity):
    return {"critical": 0, "high": 1, "normal": 2, "info": 3}.get(severity, 4)


@st.cache_data(ttl=30)
def _fetch_patient_choices(fhir_base_url):
    client = FHIRClient(base_url=fhir_base_url)
    bundle = client._get("Patient", params={"_count": 100})
    entries = bundle.get("entry", [])
    choices = []
    seen = set()

    for entry in entries:
        resource = entry.get("resource", {})
        patient_id = resource.get("id")
        if not patient_id or patient_id in seen:
            continue
        seen.add(patient_id)

        name = "Unknown"
        names = resource.get("name", [])
        if names:
            family = names[0].get("family", "")
            given = " ".join(names[0].get("given", []))
            merged = f"{given} {family}".strip()
            if merged:
                name = merged

        birth_date = resource.get("birthDate", "")
        label = f"{patient_id} | {name}"
        if birth_date:
            label += f" | DOB {birth_date}"

        choices.append({"id": patient_id, "label": label})

    return choices


st.set_page_config(page_title="Pre-Rounding Assistant", layout="wide")

st.markdown(
    """
<style>
/* Scoped variables for our custom cards */
.custom-card-text {
  color: #142b45 !important;
}
.custom-card-muted {
  color: #3c5574 !important;
}

/* Force light background only if we really want to enforce a specific look, 
   but it's safer to respect theme. 
   If we keep the gradient, we must ensure text is dark. */
.stApp {
  background: radial-gradient(circle at top left, #e9f4ff 0%, #f8fbff 40%, #eef3fb 100%);
  /* Ensure global text is readable on this light background */
  color: #142b45;
}

/* Targets for our custom cards */
.header-card {
  background: #ffffff;
  border: 1px solid #dce9ff;
  border-radius: 14px;
  padding: 1rem 1.2rem;
  box-shadow: 0 4px 6px rgba(0,0,0,0.05);
}
.header-card h2 {
  color: #0f2745 !important;
  margin: 0;
}
.header-card p {
  color: #2d4b6d !important;
  margin: 0.35rem 0 0 0;
}

.triage-card {
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #dce2ef;
  padding: 1rem;
  min-height: 180px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.02);
}
.triage-card b {
    color: #0f2745;
    font-size: 1.1em;
}
.triage-critical {
  border-left: 6px solid #c62828;
}
.triage-high {
  border-left: 6px solid #ef6c00;
}
.triage-dq {
  border-left: 6px solid #1565c0;
}

.kpi-card {
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #dce2ef;
  padding: 0.8rem;
  text-align: center;
  box-shadow: 0 2px 4px rgba(0,0,0,0.02);
}
.kpi-card b {
    color: #3c5574;
    font-size: 0.85em;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.kpi-value {
    color: #0f2745;
    font-size: 1.4em;
    font-weight: 700;
    margin-top: 0.2rem;
}

/* Badges */
.badge {
  display: inline-block;
  border-radius: 4px;
  padding: 0.2rem 0.6rem;
  font-size: 0.75rem;
  font-weight: 600;
}
.badge-critical { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
.badge-high { background: #ffedd5; color: #9a3412; border: 1px solid #fed7aa; }
.badge-normal { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
.badge-info { background: #e0f2fe; color: #075985; border: 1px solid #bae6fd; }
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="header-card">
  <h2>🏥 Pre-Rounding Assistant</h2>
  <p>Grounded, citation-based clinical summaries from FHIR facts.</p>
</div>
""",
    unsafe_allow_html=True,
)

if "results" not in st.session_state:
    st.session_state["results"] = None
if "last_run_at" not in st.session_state:
    st.session_state["last_run_at"] = None

with st.sidebar:
    st.subheader("Run Settings")
    history_limit = st.slider("Audit history rows", min_value=5, max_value=50, value=10, step=5)
    flagged_only_default = st.checkbox("Default to flagged findings", value=True)

    st.caption("Environment")
    has_openai_key = bool(os.getenv("OPENAI_API_KEY"))
    fhir_base = get_fhir_base_url()
    db_url_set = bool(os.getenv("DATABASE_URL"))
    st.write(f"OpenAI key: {'Available' if has_openai_key else 'Missing'}")
    st.write(f"FHIR base: `{fhir_base}`")
    st.write(f"Database URL: {'Available' if db_url_set else 'Missing (using default)'}")

    col_refresh, _ = st.columns([1, 1])
    with col_refresh:
        if st.button("Refresh Patients", use_container_width=True):
            _fetch_patient_choices.clear()

    try:
        patient_choices = _fetch_patient_choices(fhir_base)
    except FHIRRequestError as exc:
        st.error(str(exc))
        patient_choices = []
    patient_label_by_id = {item["id"]: item["label"] for item in patient_choices}

    if patient_choices:
        patient_ids = [item["id"] for item in patient_choices]
        default_id = st.session_state.get("selected_patient_id", patient_ids[0])
        default_index = patient_ids.index(default_id) if default_id in patient_ids else 0

        selected_patient_id = st.selectbox(
            "Patient ID",
            options=patient_ids,
            index=default_index,
            format_func=lambda pid: patient_label_by_id.get(pid, pid),
        )
        st.session_state["selected_patient_id"] = selected_patient_id
        patient_id = selected_patient_id
    else:
        st.warning("No patients found in FHIR. Run `python scripts/load_synthea.py`, then click Refresh Patients.")
        patient_id = st.text_input("Patient ID (manual)", value="")

    if st.session_state.get("results_patient_id") != patient_id:
        st.session_state["results"] = None
        st.session_state["last_run_at"] = None

    if st.button("Generate Summary", type="primary", use_container_width=True):
        if not patient_id:
            st.error("Select a valid patient ID first.")
            st.stop()
        with st.spinner("Fetching patient data, building fact table, and generating summary..."):
            st.session_state["results_patient_id"] = patient_id
            try:
                st.session_state["results"] = run_pipeline(patient_id)
                st.session_state["last_run_at"] = datetime.utcnow()
            except Exception as exc:
                st.session_state["results"] = {"error": str(exc)}

res = st.session_state["results"]
if not res:
    st.info("Select a patient ID and click Generate Summary.")
    st.stop()

if "error" in res:
    st.error(res["error"])
    if patient_choices:
        st.info("Available patient IDs: " + ", ".join([item["id"] for item in patient_choices]))
    st.stop()

facts = res["facts_raw"]
if res.get("audit_warning"):
    st.warning(res["audit_warning"])
annotated_facts = [_build_annotated_fact(fact, idx) for idx, fact in enumerate(facts)]
critical_facts = [item for item in annotated_facts if item["severity"] == "critical"]
high_facts = [item for item in annotated_facts if item["severity"] == "high"]
warning_facts = [item for item in annotated_facts if item["fact"].type.value == "OTHER" and "warning" in item["fact"].name.lower()]
flagged_count = len(critical_facts) + len(high_facts)
counts = _type_counts(facts)

kpi_cols = st.columns(5)
kpi_cols[0].markdown(f"<div class='kpi-card'><b>Patient</b><div class='kpi-value'>{escape(res['patient_name'])}</div></div>", unsafe_allow_html=True)
kpi_cols[1].markdown(f"<div class='kpi-card'><b>Total Facts</b><div class='kpi-value'>{len(facts)}</div></div>", unsafe_allow_html=True)
kpi_cols[2].markdown(f"<div class='kpi-card'><b>Flagged Findings</b><div class='kpi-value'>{flagged_count}</div></div>", unsafe_allow_html=True)
kpi_cols[3].markdown(f"<div class='kpi-card'><b>Data Quality Warnings</b><div class='kpi-value'>{len(warning_facts)}</div></div>", unsafe_allow_html=True)
kpi_cols[4].markdown(f"<div class='kpi-card'><b>Audit ID</b><div style='font-size:0.9em; margin-top:0.4rem; overflow-wrap:break-word;'>{res.get('audit_id') or 'N/A'}</div></div>", unsafe_allow_html=True)

if st.session_state.get("last_run_at"):
    st.caption(f"Last generated at UTC: {_safe_iso(st.session_state['last_run_at'])}")

st.subheader("Triage Board")
triage_cols = st.columns(3)
with triage_cols[0]:
    st.markdown(
        f"<div class='triage-card triage-critical'><b>Critical Findings ({len(critical_facts)})</b></div>",
        unsafe_allow_html=True,
    )
    if critical_facts:
        for item in critical_facts[:6]:
            f = item["fact"]
            st.markdown(f"- `{f.type.value}` {f.name}: {f.value} {f.unit or ''} ({item['reason']}) [{f.source_id}]")
    else:
        st.caption("No critical findings detected by heuristics.")

with triage_cols[1]:
    st.markdown(
        f"<div class='triage-card triage-high'><b>High Priority Findings ({len(high_facts)})</b></div>",
        unsafe_allow_html=True,
    )
    if high_facts:
        for item in high_facts[:6]:
            f = item["fact"]
            st.markdown(f"- `{f.type.value}` {f.name}: {f.value} {f.unit or ''} ({item['reason']}) [{f.source_id}]")
    else:
        st.caption("No high-priority findings detected by heuristics.")

with triage_cols[2]:
    st.markdown(
        f"<div class='triage-card triage-dq'><b>Data Quality / System Warnings ({len(warning_facts)})</b></div>",
        unsafe_allow_html=True,
    )
    if warning_facts:
        for item in warning_facts[:6]:
            f = item["fact"]
            st.markdown(f"- {f.value} [{f.source_id}]")
    else:
        st.caption("No ingestion warnings for this run.")

with st.expander("Heuristic note"):
    st.write(
        "Severity labels are rule-based heuristics for quick triage. They are not diagnosis or final clinical judgment."
    )

tabs = st.tabs(["Summary", "Evidence Explorer", "Fact Timeline", "Audit and Feedback"])

with tabs[0]:
    st.subheader("Clinical Summary")
    st.markdown(res["summary"] or "No summary was generated.")

    if critical_facts or high_facts:
        st.markdown("### Priority Findings Snapshot")
        for item in sorted(critical_facts + high_facts, key=lambda x: (_severity_rank(x["severity"]), x["idx"]))[:10]:
            f = item["fact"]
            st.markdown(f"- `{item['severity'].upper()}` {f.name}: {f.value} {f.unit or ''} ({item['reason']}) [{f.source_id}]")
    else:
        st.caption("No priority findings detected by heuristic rules.")

    with st.expander("Fact Table Sent to LLM (after regex redaction)"):
        st.code(res["llm_facts_markdown"], language="markdown")

with tabs[1]:
    st.subheader("Evidence Explorer")
    all_types = sorted({item["fact"].type.value for item in annotated_facts})
    all_severities = ["critical", "high", "normal", "info"]

    selected_types = st.multiselect("Filter by fact type", options=all_types, default=all_types)
    selected_severities = st.multiselect("Filter by severity", options=all_severities, default=all_severities)
    flagged_only = st.checkbox("Show only flagged findings", value=flagged_only_default)
    keyword = st.text_input("Search in fact name/value")

    filtered = []
    for item in annotated_facts:
        fact = item["fact"]
        if fact.type.value not in selected_types:
            continue
        if item["severity"] not in selected_severities:
            continue
        haystack = f"{fact.name} {fact.value}".lower()
        if keyword and keyword.lower() not in haystack:
            continue
        if flagged_only and item["severity"] not in ["critical", "high"]:
            continue
        filtered.append(item)

    filtered.sort(key=lambda x: (_severity_rank(x["severity"]), x["idx"]))

    st.caption(f"Showing {len(filtered)} of {len(annotated_facts)} facts")
    if filtered:
        labels = [item["label"] for item in filtered]
        selected_label = st.selectbox("Select fact", options=labels)
        selected_idx = labels.index(selected_label)
        selected = filtered[selected_idx]
        fact = selected["fact"]
        severity = selected["severity"]
        reason = selected["reason"]

        st.markdown(
            f"Severity: <span class='badge badge-{severity}'>{severity.upper()}</span> | Rationale: {reason}",
            unsafe_allow_html=True,
        )

        st.info(f"Citation token: [[{fact.source_id}]]")
        st.json(
            {
                "patient_id": fact.patient_id,
                "timestamp": _safe_iso(fact.timestamp),
                "type": fact.type.value,
                "name": fact.name,
                "value": fact.value,
                "unit": fact.unit,
                "status": fact.status,
                "source_id": fact.source_id,
            }
        )

        st.markdown("### Filtered Fact List")
        st.dataframe(
            [
                {
                    "severity": item["severity"],
                    "timestamp": _safe_iso(item["fact"].timestamp),
                    "type": item["fact"].type.value,
                    "name": item["fact"].name,
                    "value": item["fact"].value,
                    "unit": item["fact"].unit,
                    "reason": item["reason"],
                    "source_id": item["fact"].source_id,
                }
                for item in filtered
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("No facts match the selected filters.")

with tabs[2]:
    st.subheader("Fact Timeline")
    rows = []
    timeline_severity = st.selectbox(
        "Timeline severity filter", ["all", "critical", "high", "normal", "info"], index=0, key="timeline_severity"
    )

    for item in annotated_facts:
        if timeline_severity != "all" and item["severity"] != timeline_severity:
            continue
        fact = item["fact"]
        rows.append(
            {
                "severity": item["severity"],
                "reason": item["reason"],
                "timestamp": _safe_iso(fact.timestamp),
                "type": fact.type.value,
                "name": fact.name,
                "value": fact.value,
                "unit": fact.unit,
                "status": fact.status,
                "source_id": fact.source_id,
            }
        )
    rows.sort(key=lambda row: row["timestamp"], reverse=True)
    st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander("Type breakdown"):
        st.json(counts)

with tabs[3]:
    st.subheader("Feedback")
    audit_id = res.get("audit_id")
    if not audit_id:
        st.warning("No audit ID found for this run. Feedback cannot be attached.")
    else:
        feedback_choice = st.radio(
            "How accurate is this summary?",
            options=["Accurate", "Incorrect"],
            horizontal=True,
            key=f"feedback_choice_{audit_id}",
        )
        reason = st.text_area(
            "Reason / notes",
            value="",
            key=f"feedback_reason_{audit_id}",
            placeholder="Describe what was wrong or missing.",
        )
        if st.button("Submit Feedback", key=f"submit_feedback_{audit_id}"):
            score = 1 if feedback_choice == "Accurate" else 0
            text = reason.strip() if reason.strip() else ("Good" if score == 1 else "Incorrect")
            if submit_feedback(audit_id, score, text):
                st.success("Feedback saved.")
            else:
                st.error("Failed to save feedback.")

    st.divider()
    st.subheader("Recent Audit Logs")
    db = SessionLocal()
    try:
        logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(history_limit).all()
    except Exception:
        st.warning("Audit history is unavailable. Check the database connection and run scripts/init_db.py.")
        logs = []
    finally:
        db.close()

    history_rows = []
    for log in logs:
        history_rows.append(
            {
                "timestamp": _safe_iso(log.timestamp),
                "audit_id": str(log.id),
                "patient_id": log.patient_id,
                "model": log.llm_model,
                "feedback_score": log.feedback_score,
                "feedback_text": log.feedback_text,
            }
        )
    st.dataframe(history_rows, use_container_width=True, hide_index=True)
