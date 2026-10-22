# Current architecture

This describes the implemented prototype. Proposed capabilities are in [v2_proposal.md](v2_proposal.md).

```text
Streamlit patient selection
  -> run_pipeline(patient_id)
  -> FHIR Patient read
  -> paginated Encounter / Observation / MedicationRequest searches
  -> supported fields converted to Facts
  -> UTC timestamp sorting and retrieval-coverage warning
  -> Markdown fact table
  -> basic regex redaction
  -> OpenAI summary request
  -> PostgreSQL audit insert
  -> summary + evidence + demo heuristic findings + feedback UI
```

## Retrieval and facts

`src/fhir/client.py` uses request timeouts and follows search Bundle `next` links. HTTP failures, malformed responses, pagination loops, cross-server page links, and page-limit exhaustion raise errors. A patient read returning HTTP 404 is handled separately from a service failure. The patient picker lists the first 100 results.

`src/ingestion/converter.py` flattens encounters, observations, observation components, and medication requests. Supported quantities are normalized, quantity comparators are retained, and timestamps are converted to UTC for sorting. Date-only values are treated as midnight UTC; partial years/months use the beginning of the period. Missing or invalid dates use a minimum UTC sentinel. This is a sorting convention, not a claim of precise event time.

`src/ingestion/engine.py` combines lab, vital, medication-order, and encounter facts. It does not filter by encounter or time window and does not retrieve administrations. Its system warning therefore describes unknown administration coverage rather than asserting that no medication was administered.

## Inference and evidence

The model receives a Markdown fact table after basic regex redaction. Prompts request citations and factual summaries; there is no output schema or deterministic claim verifier. API failures, empty responses, refusals, and truncated completions produce errors instead of summary text.

The UI displays source tokens and normalized fact records. It does not fetch raw source JSON or resolve citation clicks. Triage is a separate set of unvalidated demo rules with unit guards; missing retrieval coverage is shown as information, not as a critical clinical measurement.

## Persistence and evaluation

An audit record contains a UUID, timestamp, patient ID, original facts, generated summary, model name, and optional feedback. It does not store a complete request trace, prompt version, resource versions, or a signed review event. An audit insert failure is surfaced to the user; it does not block viewing the generated summary in this prototype.

The offline evaluation script reads recent audits and applies basic regex redaction before asking an LLM judge for a score and explanation. It does not store evaluation results or gate releases.

## Verification boundary

Regression tests use mocked upstream services, an in-memory SQLite audit store, and Streamlit's app test harness. PostgreSQL retains native UUID/JSONB types through SQLAlchemy. Tests do not establish live HAPI compatibility, PostgreSQL behavior, model quality, or clinical validity; these require separate integration and evaluation work.

## Protocol references

- [FHIR R4 search pagination](https://hl7.org/fhir/R4/http.html#paging): search results expose links to further pages.
- [FHIR R4 Observation](https://hl7.org/fhir/R4/observation.html): observations can carry component measurements.
- [SMART App Launch 2.2](https://hl7.org/fhir/smart-app-launch/STU2.2/app-launch.html): authorization and launch context for future EHR integration; not implemented here.
