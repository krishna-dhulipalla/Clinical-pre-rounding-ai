# Pre-Rounding Assistant - Project Overview

This is the original design brief, not an implementation status report. See
[current architecture](architecture.md) for implemented behavior and
[the v2 proposal](v2_proposal.md) for the recommended next version. In particular,
time-window filtering, enforced citations, raw evidence links, complete audit
traces, and production privacy controls described below are not implemented.

## Vision

A grounded, evidence-first clinical summarization system that connects to a local FHIR server, flattens patient data into a deterministic Fact Table, and uses an LLM strictly as a citation-backed summarizer. The goal is to reduce hallucination risks in healthcare AI by decoupling data retrieval/logic from text generation.

## Core Value Proposition

- **Evidence-First**: Every claim in the summary is cited with a link to the raw FHIR resource.
- **Deterministic Fact Table**: Logic for "what changed" is handled by code, not the LLM.
- **Safety**: Automated groundedness evaluation and human-in-the-loop feedback loops.
- **Privacy**: Edge-ready PHI redaction middleware.

## Key Features

1.  **Wide-Fetch Retrieval**: Fetches Labs, Vitals, Meds, and Encounters from FHIR (last 24-48h).
2.  **Canonical Fact Table**: Flattens nested FHIR JSON into a linear, normalized timeline of events.
3.  **Grounded Summarization**: LLM generates text referencing _only_ the Fact Table rows.
4.  **Evidence UI**: Split-screen view with Summary on left, Raw Evidence on right.
5.  **Audit Trails**: Full logging of retrieval, facts, prompts, and outputs to Postgres.
6.  **Continuous Eval**: "Mark Incorrect" feedback button and LLM-as-judge scoring.

## Technology Stack

- **Backend**: Python (FastAPI/Flask)
- **Database**: Postgres (Audit logs), HAPI FHIR (Patient Data)
- **LLM**: Local/Hosted LLM (e.g., Llama 3, GPT-4o via API)
- **Frontend**: Streamlit / React (Simple Evidence UI)
- **Infrastructure**: Docker (HAPI FHIR, Postgres, App containers)
