# Rounds — Clinical Change Intelligence Workbench

Rounds is an evidence-first clinical review application built on FHIR. It organizes patient records into encounter-specific briefings, highlights changes across a review window, and connects each statement to its supporting evidence. Clinicians can inspect source records, prepare handoffs, and retain a versioned review history.

The application combines a React/TypeScript workspace, a Python/FastAPI service, durable background jobs, and optional LLM prioritization. A Streamlit interface provides clinical summarization, evidence exploration, audit history, and feedback.

![Rounds workspace showing clinical changes and their supporting FHIR source records](docs/images/workbench-v2.png)

## Capabilities

- **Encounter-based review:** Explicit UTC review windows, comparable lab and vital changes, corrected-result handling, and data freshness indicators.
- **Traceable evidence:** Saved FHIR resource versions, value paths, content fingerprints, and source inspection alongside briefing statements.
- **Verified briefings:** Deterministic calculations and claim checks, with explicit abstention when required retrieval or event-time coverage is incomplete.
- **Clinician review:** Editable handoff selection, clinician-authored notes, draft and accepted revisions, and concurrency protection.
- **FHIR integration:** Scoped service access and SMART sandbox launch with PKCE, encrypted token storage, and patient/encounter context binding.
- **Evaluation and operations:** Reproducible synthetic scenarios, access events, job recovery, processing latency, token usage, and configurable model-cost estimates.

## Getting started

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node.js 22.14+.

```powershell
uv sync --frozen --extra dev
npm --prefix web ci
npm --prefix web run build
uv run python scripts/run_workbench.py serve
```

Open [localhost:8000](http://localhost:8000) and choose **Open synthetic workspace**. The local demonstration uses SQLite and bundled synthetic FHIR resources. Docker and an API key are optional.

Configuration is loaded from the repository's `.env`; process environment variables take precedence. See [.env.example](.env.example). The workbench uses `WORKBENCH_DATABASE_URL` and initializes its schema automatically in demo mode.

To use another port, set the matching browser origin:

```powershell
$env:WORKBENCH_PUBLIC_URL = "http://localhost:8012"
uv run python scripts/run_workbench.py serve --port 8012
```

## Review workflow

1. Select a patient, encounter, and review window.
2. Generate a briefing and review the recorded changes.
3. Open a statement's source to inspect its FHIR record, version, and value path.
4. Review retrieval coverage and any stale, corrected, or unavailable data.
5. Select statements for the handoff, add a clinician note, and save or accept the review.

Saved briefings and review revisions can be reopened after a restart. The synthetic workspace uses a fixed replay clock to keep demonstrations reproducible and includes scenarios for retrieval outages, access denial, and missing timestamps.

## AI and evidence verification

The workbench normalizes source evidence, computes compatible changes, and renders factual claims in code. An optional LLM prioritizes the complete claim set using opaque identifiers. Invalid, incomplete, or unsupported rankings fall back to the deterministic briefing.

Enable hosted prioritization through the environment:

```ini
WORKBENCH_HOSTED_LLM=true
OPENAI_API_KEY=your-key
WORKBENCH_MODEL=gpt-4o-mini
```

Model-facing ranking input contains controlled measurement labels, opaque claim IDs, claim types, and relative timing. It excludes raw FHIR JSON, free-text source labels, patient identifiers, resource IDs, and absolute dates. Clinician notes remain explicitly human-authored and are not automatically verified.

Optional `WORKBENCH_INPUT_USD_PER_MILLION` and `WORKBENCH_OUTPUT_USD_PER_MILLION` settings enable model-cost estimates using operator-supplied rates.

## Streamlit interface

The Streamlit interface uses the pipeline in `src/main.py` and the FHIR/PostgreSQL services in `docker-compose.yml`. Install `requirements.txt`, configure `.env`, then run:

```powershell
docker compose up -d
python scripts/init_db.py
python scripts/load_synthea.py
streamlit run src/ui/app.py
```

Its audit database is configured through `DATABASE_URL`. This interface uses prompt-based citations and basic regex redaction; deterministic claim verification and review snapshots are provided by the React workbench.

## Testing and evaluation

```powershell
uv run pytest -q
uv run ruff check src/workbench
uv run python scripts/run_workbench.py evaluate --output output/evaluation.json
```

Evaluation reports include scenario expectations, metric numerators and denominators, pipeline and dataset versions, and known limitations. Use `--baseline output/baseline.json` to compare reports. The evaluation command exits nonzero when an expected scenario fails.

Tests cover retrieval boundaries, quantities, source integrity, missing data, model fallback, job recovery, cancellation, review conflicts, authorization, SMART state/PKCE, retention, and the Streamlit pipeline. PostgreSQL integration tests require a disposable `WORKBENCH_TEST_POSTGRES_URL` ending in `_test`; CI provides this database.

## Deployment

```powershell
docker compose -f compose.v2.yml up --build -d
```

The workbench deployment starts PostgreSQL, a non-root API/web container, and a separate job worker. Ports bind to localhost, and the included credentials are intended for local synthetic use. Dependencies are locked in `uv.lock` and `web/package-lock.json`.

See [deployment and operations](docs/operations.md) for migrations, worker configuration, retention, backups, and rollback. See [SMART setup](docs/smart_on_fhir_setup.md) for sandbox registration and scoped FHIR access.

## Architecture

```text
web/                    React/TypeScript review workspace
src/workbench/          API, evidence processing, claim verification, jobs, and review
src/fhir/               FHIR HTTP client and paginated retrieval
src/ingestion/          Fact extraction and normalization for summarization
src/llm/                Summarization client and prompts
src/redaction/          Basic regex redaction
src/db/                 Summarization audit records and feedback
src/ui/                 Streamlit interface
migrations/             Workbench database migrations
data/                   Synthetic records and evaluation fixtures
tests/                  Application regression and integration checks
```

Read the [architecture documentation](docs/architecture.md) for data flow and verification boundaries.

## Scope and limitations

Rounds is intended for synthetic-data demonstrations and sandbox evaluation. Source agreement and passing engineering tests do not establish medical accuracy, clinical efficacy, regulatory approval, or readiness for patient care.

Named clinician identity federation, enterprise authorization, deployment-specific privacy controls, and clinical validation require additional work. Data minimization and basic regex redaction do not constitute complete de-identification. The application does not claim HIPAA compliance or autonomous clinical decision-making.
