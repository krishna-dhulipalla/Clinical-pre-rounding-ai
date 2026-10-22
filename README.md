# Pre-Rounding Assistant

A clinical summarization prototype that turns FHIR R4 records into a cited patient summary, with an evidence explorer, audit history, and clinician feedback.

The current app uses Python, Streamlit, PostgreSQL, a HAPI FHIR server, and an OpenAI model. It is intended for demonstrations with synthetic records. Citations and regex redaction are useful controls, but do not establish clinical accuracy, complete de-identification, or production readiness.

## What it does

1. Select a patient from the local FHIR server.
2. Retrieve encounters, laboratory observations, vital signs, and medication requests, following search pagination.
3. Flatten supported fields into timestamped facts, including observation components such as systolic and diastolic blood pressure.
4. Apply basic regex redaction and ask an LLM to summarize the facts with source citation tokens.
5. Display the summary, fact timeline, heuristic findings, and searchable evidence.
6. Store facts and the summary in an audit table and accept accurate/incorrect feedback.

Model failures and incomplete retrieval are surfaced as errors. Audit failures are displayed separately. Selecting a different patient clears the previous summary.

## Run locally

Prerequisites: Python 3.10+, Docker Compose, and an OpenAI API key.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`:

```ini
OPENAI_API_KEY=your-key
DATABASE_URL=postgresql://admin:admin@localhost:5432/fhir_rag_audit
FHIR_BASE_URL=http://localhost:8080/fhir
```

The app and scripts load the repository's `.env`; existing process environment variables take precedence.

```powershell
docker compose up -d
```

Wait for PostgreSQL and HAPI FHIR to accept connections, then initialize the audit table and load the included synthetic bundle:

```powershell
python scripts/init_db.py
python scripts/load_synthea.py
streamlit run src/ui/app.py
```

Open [the local app](http://localhost:8501).

## Verification and evaluation

```powershell
python -m pytest tests/ -q
python scripts/run_eval.py
```

Tests use mocked FHIR/model responses and an isolated in-memory database. They do not require API calls, Docker, or an application database. They exercise retrieval failures, pagination, date handling, observation components, generation failures, audit/feedback, regex redaction, unit-aware demo heuristics, and patient switching in Streamlit.

The evaluation script sends recent stored facts and summaries through basic regex redaction to a hosted LLM judge. Use synthetic data only. Its scores are advisory and are not an independent clinical validation.

## Current limits

- Retrieval has no encounter or 24–48-hour filter. Old records can appear; no freshness guarantee is made.
- Only a subset of FHIR fields and resource types is supported. Medication administrations, diagnoses, allergies, notes, and dosage extraction are not implemented.
- Citation tokens are requested through prompting. Their existence and whether they support each claim are not automatically enforced; tokens are not clickable evidence links yet.
- Evidence Explorer shows normalized facts, rather than the original FHIR resource JSON.
- Triage thresholds are unvalidated demo heuristics. Unsupported units are marked for review instead of being compared with incompatible thresholds.
- Regex redaction handles a known full name, selected date formats, and selected phone formats. It preserves citation IDs, does not fully de-identify records, and does not implement a general MRN/PHI detector. Redacting dates also limits temporal interpretation.
- Audit records contain original facts, patient IDs, and generated text. Authentication, role-based access, encryption policy, retention controls, and deployment monitoring are not implemented.
- SMART on FHIR is a future integration, described only in a setup sketch. The local FHIR server has no application authorization.

## Project layout

```text
src/
  fhir/          FHIR HTTP client and paginated searches
  ingestion/     Fact models, conversion, unit normalization, timeline assembly
  redaction/     Basic regex redaction
  llm/           Model client and summarization prompts
  db/            Audit persistence and feedback
  eval/          LLM judge
  ui/            Streamlit app and demo triage rules
  main.py        Summarization pipeline
scripts/         Database initialization, synthetic-data loader, offline evaluation
tests/           Isolated regression tests
data/            Sample synthetic FHIR bundle
docs/            Architecture and proposed next version
```

See [current architecture](docs/architecture.md) and the [proposed v2: Clinical Change Intelligence Workbench](docs/v2_proposal.md) for the next development direction.
