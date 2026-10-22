# Proposed v2: Clinical Change Intelligence Workbench

Status: proposal, not implemented. The current project remains a synthetic-data summarization prototype.

## Product direction

Evolve the evidence-first foundation into a clinician review workspace answering: **What changed since the last review, what evidence supports it, and what information is unavailable?**

The output is a reviewable briefing and handoff draft. A clinician reviews, corrects, and accepts it. Diagnosis, prescribing, autonomous chart updates, and treatment recommendations are outside the initial scope.

The strongest showcase is an end-to-end demonstration of reliable clinical data processing, measurable AI behavior, and operational controls. Keep the FHIR adapter and fact-table concept; replace the single synchronous UI-to-model function with explicit retrieval, validation, generation, and review stages.

## Priority features

| Priority | Capability | User-facing behavior | Engineering evidence |
| --- | --- | --- | --- |
| P0 | Encounter and review windows | Select an encounter and see changes since a fixed review timestamp; stale/unknown dates are visible | Reproducible snapshots, UTC policy, temporal regression cases |
| P0 | Longitudinal change engine | Compare compatible lab/vital measurements with previous/current values, dates, and sources | Code-based deltas, code/unit compatibility checks, tests for corrected results and missing baselines |
| P0 | Structured evidence-backed claims | Open a summary statement to inspect its supporting resource version and values | Typed claims, source-ID validation, evidence checks; valid citations alone never establish clinical support |
| P0 | Incomplete-data state | Distinguish unavailable, not queried, access denied, empty, and stale data | Retrieval manifests, no silent partial success, abstention tests |
| P0 | Reproducible evaluation | Compare a candidate model/prompt with a baseline before deployment | Versioned synthetic cases, numerical fidelity, citation validity, temporal correctness, omissions, clinician-adjudicated samples |
| P1 | Review and handoff | Edit and accept a draft while preserving source evidence | Draft/reviewed states, actor identity, revision history, immutable evidence snapshots |
| P1 | SMART sandbox launch | Open in a patient/encounter context with scoped access | OAuth flow, context binding, token handling, authorization and patient-isolation tests |
| P1 | Runtime observability | Investigate failures without exposing raw patient data | Trace IDs, stage latency, failure rates, token/cost accounting, redacted logs |
| P1 | Reliable jobs and releases | Generation survives refreshes; repeated clicks do not duplicate work | Jobs, idempotency, bounded retries, cancellation, readiness checks, migrations, CI and rollback |
| P2 | Worklist and shift handoff | Review assigned patients with review status and freshness | Permission-scoped worklists, access events, explicit unresolved items |

These are proposed engineering targets, not claims of clinical performance. Clinical scoring rules and alert thresholds need a separately defined use case and clinical validation.

## Suggested architecture

```text
React review workspace
    -> FastAPI: authenticated user + patient/encounter context
    -> durable job worker
        -> FHIR adapter + retrieval manifest
        -> versioned evidence snapshot
        -> normalized facts + deterministic change engine
        -> structured model generation
        -> citation/quantity/temporal checks
        -> validated draft or explicit abstention
    -> PostgreSQL: snapshots, runs, claims, revisions, access events
    -> telemetry: redacted traces, errors, latency, cost

Versioned synthetic scenarios -> offline evaluation -> release comparison
```

Start with one model and a fixed pipeline. Add model routing or agent tool use only when evaluation demonstrates an advantage. FHIR resources and notes are untrusted input; they must not change system instructions or gain authority to trigger external actions.

Separate identity mapping from model-facing evidence IDs. Preserve useful relative timing while minimizing identifiers. Define what can leave the deployment boundary, who can access stored evidence, retention, and secret/token management before introducing real patient data.

SMART provides authorization and launch context; it does not itself implement all institutional access, audit, privacy, or session controls. Base integration on the [published SMART launch flow](https://hl7.org/fhir/smart-app-launch/STU2.2/app-launch.html) and [scopes/context specification](https://hl7.org/fhir/smart-app-launch/STU2.2/scopes-and-launch-context.html).

## Four build increments

1. **Reliable data foundation.** Encounter/time selection, codes and resource version IDs, retrieval manifests, complete observation value handling, and synthetic timeline fixtures. Demonstrate correct time windows and explicit missingness first.
2. **Verifiable briefing.** Deterministic changes, structured claims, clickable raw evidence, and output validation. Block unknown references and inconsistent quantities. Treat semantic support checks as fallible and surface uncertainty.
3. **Clinical review workflow.** Draft revisions, reviewer acceptance, handoff view, scoped access, SMART sandbox launch, and audited access. Preserve exactly which evidence supports each accepted revision.
4. **Operational proof.** Background jobs, migrations, containerized deployment, CI, observability, evaluation reports, failure injection, and rollback. Publish measured results with dataset descriptions and limitations.

## Portfolio demonstration

Seed several synthetic patients and use a fixed replay clock so the demonstration remains meaningful as dates change. Include a lab trend, medication-order change, corrected observation, stale data, and a failed upstream request. Label fixtures as synthetic rather than clinically representative.

Show this sequence in one short walkthrough:

1. Open the worklist and select a patient/encounter.
2. Review changes since the previous briefing, with both source values visible.
3. Open a summary claim and inspect supporting evidence.
4. Simulate a retrieval outage and show explicit incomplete-data status.
5. Correct and accept a handoff draft; inspect its revision and evidence snapshot.
6. Compare prompt/model evaluation reports and inspect known failures alongside latency and cost.

Report citation-reference validity, quantity agreement, retrieval completeness, abstention behavior, latency percentiles, cost per briefing, and correction frequency. Define each metric and denominator. Do not advertise zero hallucinations, time savings, or clinical benefit without supporting measurements.

## Smaller alternative

Keep Streamlit for v1.5: add encounter/time windows, deterministic change cards, clickable evidence, and an offline evaluation report first. Move to React/API/worker once the workflow and evaluation targets are clear. Evidence and demonstrated behavior matter more than the frontend framework.
