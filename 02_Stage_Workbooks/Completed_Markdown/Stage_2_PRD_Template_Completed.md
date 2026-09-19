# Stage 2: Product Requirements Document (PRD) — Completed

**Product Name:** CloudServe Support Automation & AI Escalation Engine  
**Author:** Madhav Mehta  
**Date:** September 6, 2026  
**Status:** Approved / Baseline  

---

## 1. Product Objectives & Target Metrics

The CloudServe AI Support Engine automates customer inquiry responses while providing high-precision risk mitigation through automatic human agent escalation.

### Target Performance Benchmarks (Acceptance Criteria Alignment)
- **First Contact Resolution (FCR):** $\ge 60\%$ on benchmark evaluation set.
- **Answer Precision:** $\ge 90\%$ on resolved automated tickets.
- **Hallucination Rate:** $0\%$ (Strictly zero ungrounded facts permitted).
- **Escalation Accuracy:** $100\%$ appropriate routing for technical/high-risk tickets.
- **Governance Auditability:** $100\%$ of routing decisions logged to audit database with confidence scores and reasoning.

---

## 2. Functional Requirements (FR)

| Req ID | Component | Requirement Description | Acceptance Criteria |
|---|---|---|---|
| **FR-01** | Ingestion | Normalize input text, trim whitespace, extract raw metadata, sanitize input format. | Accepts raw text/JSON payload; returns structured `TicketPayload`. |
| **FR-02** | Classifier | Predict ticket intent category (Billing, Account, Technical, Outage) with confidence score. | Output category + confidence score $[0.0, 1.0]$. |
| **FR-03** | Retrieval | Fetch top-K relevant knowledge base articles using TF-IDF / vector similarity scoring. | Returns context snippets + similarity score. |
| **FR-04** | Router | Evaluate confidence score against dynamic threshold ($T = 0.60$). If score $< T$, trigger escalation. | Routes to `AUTOMATE` or `ESCALATE` state deterministically. |
| **FR-05** | Generator | Synthesize customer response using retrieved context only via OpenRouter API / LLM. | Generates friendly, grounded markdown response. |
| **FR-06** | Guardrails | Check input/output for prompt injections, regex PII leakage (SSN, Email, Keys), and toxicity. | Redacts PII; blocks unsafe output, forcing human escalation. |
| **FR-07** | Governance DB | Persist all query metadata, routing decision, confidence score, and output to SQLite DB. | Insert row into `decision_logs` table per query. |

---

## 3. System Architecture & Component Diagram

```
[Customer Query]
       │
       ▼
[Ingestion Module] ──► (Input Sanitization)
       │
       ▼
[Guardrails Engine] ──► (PII Redaction & Injection Detection)
       │
       ▼
[Category Classifier] ──► (Confidence Scoring)
       │
       ▼
[Knowledge Retrieval (RAG)] ──► (Context Score Calculation)
       │
       ▼
[Decision Router] ──► (Confidence < 0.60?)
    ├── YES ──► [Escalation Workflow] ──► (Forward to Human Tier-2)
    └── NO  ──► [Generator Module]   ──► (Synthesize Response)
       │
       ▼
[Decision Database (SQLite)] ──► (Audit Trail Logging)
       │
       ▼
[Final Customer Output]
```

---

## 4. Non-Functional Requirements (NFR)

1. **Security:** No raw API keys or passwords stored in codebase or committed to Git (`.gitignore` enforced).
2. **Reliability & Fallbacks:** If OpenRouter API times out or fails, gracefully escalate ticket to human queue with error code `ERR_LLM_TIMEOUT`.
3. **Performance:** Pipeline execution time under 3 seconds per query.
4. **Reproducibility:** Test harness runnable via single command `pytest tests/` on clean environment.
