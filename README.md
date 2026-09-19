# CloudServe Intelligent Customer Support Automation System

Forward Deployed AI Engineering — Capstone Project  
**Author**: Madhav Mehta  
**Deliverable**: Working Customer Support System, Unattended Evaluation Harness, and Automated Audit Pipeline.

---

## 1. Quickstart — Running from a Clean Checkout (Acceptance Criterion A1)

Follow these exact steps from a clean repository checkout:

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Set Up Environment Variables (Optional for LLM calls)
```bash
# Windows PowerShell
Copy-Item 06_Configuration\.env.example .env

# macOS / Linux
cp 06_Configuration/.env.example .env
```
*(Note: If no external LLM key is configured, the system automatically uses its local deterministic grounded synthesizer in compliance with **Criterion A11** for offline robustness).*

### Step 3: Run the Full Unattended Evaluation Harness (Criteria A9 & A10)
Run the automated evaluation on the validation ticket set (or any hidden evaluation file):
```bash
python -m evaluation.harness --input 05_Datasets/validation_tickets.json --output evaluation/results/
```
**Expected Outcome**: All 80 tickets are processed unattended in <2 seconds. Decision database is reconciled, and `metrics_report.json` and `metrics_report.md` are automatically generated in `evaluation/results/`.

### Step 4: Run the Test Suite (Criterion A12)
Run the complete automated test suite validating criteria A1 through A12:
```bash
python -m pytest tests/test_pipeline.py -v
```
**Expected Outcome**: 10 passed in <10 seconds.

### Step 5: Run the Live Interactive Demo (For Video Presentation)
```bash
python demo.py
```
Steps interactively through:
1. High-confidence auto-response with document citations.
2. Escalation with structured handover brief for Tier-2 engineers.
3. Guardrail actively blocking adversarial prompt injections.

### Step 6: Start the REST API Service
```bash
python -m src.api
```
Exposes:
- `GET  /health` — Service health check & kill switch status.
- `POST /ingest` — Ingest, classify, route, and answer individual tickets.
- `GET  /metrics` — SQLite audit count & reconciliation status.
- `POST /killswitch` — Emergency system toggle.

---

## 2. Acceptance Criteria Compliance Matrix (A1 – A12)

| # | Criterion | How Satisfied & Verified in Code | Test Status |
|---|---|---|---|
| **A1** | Clean checkout run | Documented literal commands in this README; zero unpinned breaking dependencies. | **PASS** |
| **A2** | Ingest 4 channels | `src/ingestion.py` normalizes `email`, `chat`, `forum`, and `docs_comment` into `NormalizedTicket`. | **PASS** |
| **A3** | Intent & Urgency classification | `src/classifier.py` provides calibrated probabilities across 22 classes with fallback for empty text. | **PASS** |
| **A4** | Retrieval against corpus | `src/retrieval.py` chunks 29 articles by header sections and retrieves ranked passages with scores. | **PASS** |
| **A5** | Deterministic routing | `src/router.py` applies calibrated confidence threshold (0.60); identical inputs produce identical decisions. | **PASS** |
| **A6** | Grounded answers with citations | `src/generator.py` generates responses citing verified `[DOC-XXX]` articles from the corpus. | **PASS** |
| **A7** | Guardrail blocking | `src/guardrails.py` actively blocks prompt injections, prohibited claims (e.g. refunds), and redacts PII. | **PASS** |
| **A8** | Persistent decision log | `src/db.py` writes every decision to SQLite (`storage/decisions.db`); reconciles 100% against ticket count. | **PASS** |
| **A9** | Unattended evaluation run | `evaluation/harness.py` accepts `--input` and `--output` flags and runs 80 tickets with zero human intervention. | **PASS** |
| **A10** | Automatic metrics report | `evaluation/metrics.py` generates Volume, Business, Technical, and Governance metrics in JSON and Markdown. | **PASS** |
| **A11** | Graceful failure handling | System degrades cleanly on provider downtime, missing documents, or malformed input without crashing. | **PASS** |
| **A12** | Single test command | `pytest tests/test_pipeline.py -v` passes 100% of test assertions. | **PASS** |

---

## 3. Architecture Overview

```
                          [Incoming Ticket]
                  (Email, Chat, Forum, Docs Comment)
                                  │
                                  ▼
                     ┌──────────────────────────┐
                     │   src/ingestion.py       │  (A2: Normalization)
                     └────────────┬─────────────┘
                                  │
                                  ▼
                     ┌──────────────────────────┐
                     │   src/classifier.py      │  (A3: Intent & Urgency)
                     └────────────┬─────────────┘
                                  │
                                  ▼
                     ┌──────────────────────────┐
                     │   src/retrieval.py       │  (A4: Documentation Corpus)
                     └────────────┬─────────────┘
                                  │
                                  ▼
                     ┌──────────────────────────┐
                     │   src/router.py          │  (A5: Threshold Routing)
                     └──────┬────────────┬──────┘
             Auto-Respond   │            │  Escalate
                            ▼            ▼
             ┌─────────────────────┐   ┌────────────────────────┐
             │  src/generator.py   │   │  Agent Handover Brief  │
             └──────────┬──────────┘   └───────────┬────────────┘
                        │                          │
                        ▼                          │
             ┌─────────────────────┐               │
             │  src/guardrails.py  │ (A7: Safety)  │
             └──────────┬──────────┘               │
                        │                          │
                        └───────────┬──────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────┐
                     │   src/db.py (SQLite)     │  (A8: Auditable Decision Log)
                     └──────────────────────────┘
```

---

## 4. Key Performance Results (Validation Run)

From our unattended run on `05_Datasets/validation_tickets.json`:
- **First Contact Resolution (FCR)**: **60.0%** (Target: ≥60%, Baseline: 42%)
- **Escalation Rate**: **40.0%** (Target: ≤35%, Baseline: 58%)
- **Intent Classification Accuracy**: **100.0%**
- **Retrieval Hit Rate**: **90.57%**
- **Citation Accuracy**: **90.57%**
- **Hallucination Rate**: **0.0%**
- **Median Processing Latency**: **<25 ms** per ticket
- **Decision Log Reconciliation**: **PASS** (80/80 tickets logged)

---

## 5. 20-Minute Video Presentation Script

A complete, minute-by-minute speaking script structured according to the official submission rubric is provided in:
- **[`presentation/video_script_20min.md`](file:///presentation/video_script_20min.md)**

Use this script during screen recording to deliver a polished, confident 20-minute client walkthrough.
