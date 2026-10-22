# V2 architecture

## Execution path

```text
React review workspace (same origin)
  -> session principal / scoped service API principal
  -> FastAPI creates idempotent durable run
  -> database-backed worker claims run and renews its lease
  -> patient + encounter ownership checks
  -> scoped Observation / MedicationRequest / MedicationAdministration retrieval
  -> retrieval coverage manifest
  -> normalized versioned evidence snapshot
  -> exact deterministic changes and claim templates
  -> optional LLM ranking of the complete verified claim set
  -> evidence/quantity/change/template verification
  -> snapshot + completion event committed transactionally
  -> draft / accepted clinician review revisions
```

The default synthetic topology uses SQLite plus an embedded worker. `compose.v2.yml` uses PostgreSQL, an API/web container and a separate worker. The original Streamlit pipeline is separate and retains its v1 limitations.

## Evidence and time

Every run binds to a patient, encounter, UTC window start, review boundary and as-of time. The service rejects naive timestamps, invalid ordering and windows longer than seven days. The source adapter requests server-side time/context filters; local checks enforce boundaries again. Medication administrations use the FHIR R4 `context` field/search parameter.

Evidence IDs identify a resource version and a value path. Resources with no version ID use a content-fingerprint identifier. Source JSON is saved once in the snapshot; quantities and component values are extracted into typed facts. Comparators remain explicit. Controlled mass/temperature conversions preserve numeric meaning; general analyte-dependent conversion is not attempted.

Changes require precise timestamps, terminology codes, canonical UCUM units, and an unambiguous latest value on each side of the boundary. Comparators and ambiguous same-time measurements do not produce trends. Entered-in-error/cancelled/draft resources are excluded. Conflicting versions for the same resource fail the run rather than being double-counted.

This is a bounded extraction implementation, not a universal FHIR processor. Unsupported observation value structures are visible as requiring source inspection. Medication orders are described by authored time and status; historical medication reconciliation, dosage interpretation, long-running administrations and clinical significance require additional domain work.

## Verification boundary

Claims are constructed by code. The verifier re-extracts facts from saved source JSON, verifies content hashes, recomputes deltas, re-renders claim templates, validates references and rejects omitted/modified claims. A fingerprint binds review revisions to the saved snapshot.

The model receives controlled labels, opaque claim IDs, claim types and relative timing. It returns an ordering of all candidate IDs. Unknown IDs, duplicates, omissions, malformed output, refusal or incomplete output use the full deterministic fallback. Model output never replaces the claim text or supplies a clinical quantity.

These checks establish agreement with supported extracted evidence. They do not establish that source records are medically correct, that every relevant source was available, or that a briefing is clinically adequate.

## Coverage and abstention

Each queried resource type records retrieved count, exclusions, stale facts, unknown dates and a state: available, empty, unavailable or access denied. Conditions, allergies and documents are explicitly marked not queried. Required retrieval failures or unknown/imprecise event times withhold generated claims; partial evidence remains inspectable. Empty search results mean no records were returned in scope, not that a clinical event never occurred.

## Identity, review and persistence

Demo sessions have a synthetic reviewer identity and only bundled synthetic patients. FHIR mode disables demo login. Service API principals use a random configured token plus explicit patient allowlist. SMART sessions use browser-bound one-time state, PKCE, pinned endpoints, server-side encrypted bearer tokens, expiry and returned patient/encounter context. No unverified ID-token identity is treated as a named clinician.

Runs and evidence lookups require the owning principal and authorized patient/encounter context. Review acceptance requires a complete nonempty briefing. Exclusions require a clinician note. Notes are clearly clinician-authored and unverified. Optimistic revision checks prevent lost updates; original evidence and review revisions are append-only through application updates.

V2 tables are separate from the legacy audit table. Migrations are versioned in `migrations/`; maintenance previews retention deletion before applying it. See [operations](operations.md) for storage, backup, deployment and validation boundaries.

## Evaluation and references

`data/evaluation/cases.json` defines versioned synthetic expectations. `workbench.evaluation` compares exact changes and completion/abstention states, verifies references, emits explicit denominators and supports report-artifact comparison. Hosted model prioritization and clinician-adjudicated quality are outside this fixture score.

Protocol references: [FHIR R4 Observation](https://hl7.org/fhir/R4/observation.html), [FHIR R4 pagination](https://hl7.org/fhir/R4/http.html#paging), [MedicationAdministration context/time](https://hl7.org/fhir/R4/medicationadministration.html#search), and [SMART App Launch 2.2](https://hl7.org/fhir/smart-app-launch/STU2.2/app-launch.html).
