# Stage 4: Sprint Plan & Implementation Roadmap (Completed)

**Author:** Madhav Mehta  
**Date:** September 11, 2026  

---

## 1. Sprint Architecture & Key Milestones

The development phase was structured into a compressed 2-week technical sprint across four main workstreams:

```
Workstream A: Ingestion & Preprocessing ──┐
Workstream B: Classifier & RAG Retrieval  ├──► Workstream D: Pipeline & Integration
Workstream C: Guardrails & Database Logs ──┘
```

---

## 2. Sprint Backlog & Task Tracking

| Task ID | Component | Task Description | Planned Duration | Dependencies | Status |
|---|---|---|---|---|---|
| **TSK-01** | Env & Ingestion | Implement `ingestion.py` text cleaning & payload validation. | 4 Hours | None | **DONE** |
| **TSK-02** | Classifier | Train/configure intent classifier (`classifier.py`) with confidence scoring. | 6 Hours | TSK-01 | **DONE** |
| **TSK-03** | Retrieval | Build knowledge base TF-IDF / vector search (`retrieval.py`). | 6 Hours | TSK-01 | **DONE** |
| **TSK-04** | Router | Build threshold router (`router.py`) with configurable confidence cutoffs. | 4 Hours | TSK-02, TSK-03 | **DONE** |
| **TSK-05** | Guardrails | Implement regex PII masking and prompt injection detection (`guardrails.py`). | 6 Hours | TSK-01 | **DONE** |
| **TSK-06** | Generator | Connect OpenRouter LLM API (`generator.py`) with prompt library templates. | 5 Hours | TSK-03 | **DONE** |
| **TSK-07** | Governance DB | Implement SQLite schema & logging handler (`db.py`). | 5 Hours | TSK-04 | **DONE** |
| **TSK-08** | Core Pipeline | Assemble unified workflow engine (`pipeline.py`). | 6 Hours | TSK-01 to TSK-07 | **DONE** |
| **TSK-09** | Testing Suite | Build end-to-end unit tests (`tests/test_pipeline.py`). | 6 Hours | TSK-08 | **DONE** |
| **TSK-10** | Eval Harness | Build automated evaluation harness (`evaluation/harness.py`). | 6 Hours | TSK-08 | **DONE** |

---

## 3. Sprint Risk Management & Resolution Log

### Challenge 1: LLM API Latency & Outages
- **Symptom:** OpenRouter API occasionally took > 4 seconds or returned 502 gateway errors during test bursts.
- **Resolution:** Added automatic try-except wrapper in `generator.py` with fallback to escalation status (`ESCALATED_SYSTEM_TIMEOUT`) when response latency exceeds 3 seconds.

### Challenge 2: PII Redaction Order
- **Symptom:** Email address regex was stripping out domain names inside legitimate knowledge base URLs.
- **Resolution:** Updated regex pattern to strictly target email structures and ignore URL query parameters.
