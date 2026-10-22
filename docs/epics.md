# Project Epics

Historical planning checklist; completion boxes have not been reconciled with
the implementation. See [current architecture](architecture.md) and the
[v2 proposal](v2_proposal.md) for current behavior and recommended priorities.

## 🟢 EPIC 1 — Core Infrastructure & FHIR Integration

**Goal**: Create a realistic healthcare data environment.

- [ ] Dockerize HAPI FHIR (R4)
- [ ] Load Synthea bundle
- [ ] Build Retrieval Layer (Patient, Encounter, Obs, Meds)
- [ ] API endpoints and testing

## 🟢 EPIC 2 — Temporal Fact Table Engine

**Goal**: Convert fragmented FHIR data into a unified timeline.

- [ ] Flatten FHIR resources to Facts (Labs, Vitals, Meds)
- [ ] implementations Temporal Logic (Sort/Group)
- [ ] Unit Normalization Engine
- [ ] Missing Data Detection

## 🟢 EPIC 3 — Grounded Summarization Pipeline

**Goal**: Build a safe, evidence-based clinical summarizer.

- [ ] Build RAG Pipeline (Fact Table -> LLM)
- [ ] Strict citation enforcement
- [ ] "Insufficient data" logic
- [ ] Safety Rules & No-Hallucination constraints

## 🟢 EPIC 4 — Evidence UI & Audit Logging

**Goal**: Create a usable interface and full traceability.

- [ ] UI with Patient Selector & Summary View
- [ ] Evidence Click Viewer (Raw JSON)
- [ ] Audit Logging System (Postgres)

## 🟢 EPIC 5 — Human-in-the-Loop Continuous Evaluation

**Goal**: Enable feedback-driven improvement.

- [ ] "Mark Incorrect" button
- [ ] Feedback capture system (Reason, Timestamp, Resource ID)
- [ ] Analytics dashboard

## 🟢 EPIC 6 — Edge-Ready PHI Redaction Middleware

**Goal**: Build privacy-first data protection.

- [ ] PHI Detection Engine (Regex/NER)
- [ ] Tokenization System
- [ ] Redaction logs

## 🟢 EPIC 7 — Advanced Groundedness & Automated Evaluation

**Goal**: Measure AI reliability quantitatively.

- [ ] LLM-as-judge scoring system
- [ ] Groundedness metrics
- [ ] Evaluation methodology

## 🟢 EPIC 8 — Production-Readiness Add-Ons

**Goal**: Industry-level AI engineering maturity.

- [ ] Observability (LangSmith/Arize)
- [ ] Security (Prompt Injection defense, OWASP)
- [ ] SMART on FHIR Integration
