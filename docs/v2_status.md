# V2 implementation status

V2 is a runnable clinical AI engineering demonstration. Its real-world clinical validity has not been established.

| Proposal capability | Implemented behavior | Remaining boundary |
| --- | --- | --- |
| Encounter and review windows | Explicit UTC retrieval/review bounds, seven-day limit, encounter ownership checks, stale/unknown timestamp labels | EHR-specific temporal/profile behavior requires integration testing |
| Longitudinal changes | Exact decimal deltas by terminology code and compatible UCUM unit; latest precise record on each side; ambiguous same-time values produce no trend | No disease scoring, clinical significance inference, or broad laboratory conversion ontology |
| Structured claims and evidence | Code-rendered claims with reference validation, raw-value re-extraction, quantity/change checks, resource version IDs, source JSON, and snapshot hashes | Template agreement does not establish EHR correctness or clinical completeness |
| Missingness | Per-resource manifest; distinguishes empty, unavailable, access denied, and outside-scope data; incomplete retrieval/timestamps withhold briefing | Server-side permissions can omit records without disclosing the omission |
| Optional AI | Bounded ranking of the complete verified claim set, controlled model input, invalid-response fallback, usage telemetry | No hosted ranking call or clinical salience benchmark is required for the offline demo |
| Review/handoff | Included/excluded claims, clinician-authored notes, draft/accepted revisions, optimistic concurrency, evidence hashes, saved run history | No autonomous chart writeback, prescribing, or named clinician identity federation |
| Worklist | Scoped synthetic/FHIR patient list, latest run and review state | Multi-user assignments and cross-organization tenancy require an identity/authorization design |
| SMART sandbox | Pinned discovery/endpoints, PKCE S256, browser-bound one-time state, encrypted access tokens, session expiry and launch context binding | Requires registered sandbox credentials and live provider testing; no token refresh or unverified ID-token identity |
| Operations | Durable jobs, idempotency, cancellation, leases/renewal, bounded recovery, transactional result/audit writes, redacted JSON logs, trace IDs, latency/tokens/configured cost estimates | Enterprise monitoring, alert routing, distributed tracing export and rate controls are deployment work |
| Releases | Locked dependencies, migrations, non-root multistage image, PostgreSQL/API/worker Compose, CI unit/evaluation/build and PostgreSQL job | Container build and live PostgreSQL execution require a running Docker environment |
| Evaluation | Versioned synthetic scenarios, expected changes and abstention, citation denominators, report comparison and nonzero failure exit | Clinician-adjudicated evaluation, calibration, and clinical benefit measurement remain future validation |
| Retention | Preview-first CLI, separate run/audit retention, expired session cleanup | Choose policy, schedule and storage/backup lifecycle for the intended deployment |

The original Streamlit app remains a separate legacy path. Its behavior is not upgraded merely by running v2 tests.

## Deliberate implementation choices

- SQLite and an embedded worker provide a no-key local demo; PostgreSQL and a separate worker are configured for the container topology.
- One fixed pipeline and optional model ranking keep unsupported narrative outside the released briefing. There is no autonomous agent loop.
- The server uses session principals to authorize every run, source lookup and review. Service API access requires an explicit patient allowlist. Demo access is intentionally synthetic and is disabled in FHIR mode.
- Raw FHIR content stays in the evidence store. Model inputs carry controlled labels and opaque IDs. Stronger privacy requirements still need deployment-specific assessment.
- Notes remain explicitly clinician-authored and unverified. Accepting a handoff records a review event; it is not an EHR signature or a clinical validation claim.
