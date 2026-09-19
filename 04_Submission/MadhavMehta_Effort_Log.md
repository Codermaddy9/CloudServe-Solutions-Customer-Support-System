# Capstone Project Effort Log

**Student Name:** Madhav Mehta  
**Project Title:** CloudServe Support Automation & AI Escalation Engine  
**Duration:** August 31, 2026 – September 20, 2026 (3 Weeks)  
**Total Hours Logged:** 72 Hours  

---

## 1. Summary of Hours by Stage

| Stage | Target / Planned Hours | Actual Hours Worked | Variance & Rationale |
|---|---|---|---|
| **Stage 1: Discovery & Problem Framing** | 10 | 12 | +2 hrs: Deep dive into sample ticket logs to quantify true category distribution vs CloudServe's initial claims. |
| **Stage 2: PRD & Requirements Definition** | 8 | 10 | +2 hrs: Calibrating explicit operational thresholds (FCR ≥ 60%, Precision ≥ 90%, Zero Hallucination). |
| **Stage 3: Prompt Engineering & Guardrails** | 12 | 14 | +2 hrs: Iterative testing of prompt injection defenses and PII redact filters. |
| **Stage 4: Modular System Architecture & Coding** | 20 | 22 | +2 hrs: Refactoring retrieval fallback logic and SQLite decision logging schema. |
| **Stage 5: Evaluation, Verification & Documentation** | 15 | 14 | -1 hr: Automated test harness accelerated benchmark execution. |
| **Total** | **65 Hours** | **72 Hours** | **+7 Hours Total Variance** |

---

## 2. Granular Task & Daily Log

### Week 1: Discovery & System Framing (Aug 31 – Sep 6, 2026)

* **Mon, Aug 31 (Weekday)** — *1.5 Hours*
  * Task: Project Kickoff, repository setup, environment setup (`venv`, `.gitignore`).
  * Output: Initialized project structure and environment dependencies.

* **Tue, Sep 1 (Weekday)** — *1.0 Hour*
  * Task: Initial reading of `01_Build_Specification.docx` and business context.
  * Output: Identified key acceptance criteria A1 through A12.

* **Wed, Sep 2 (Weekday)** — *1.5 Hours*
  * Task: Exploration of raw datasets in `05_Datasets`.
  * Output: Extracted ticket category samples and evaluated noise levels in ticket text.

* **Thu, Sep 3 (Weekday)** — *1.0 Hour*
  * Task: Analysis of ticket category distributions.
  * Output: Discovered mismatch between customer expectations (simple FAQs) and operational reality (technical troubleshooting).

* **Fri, Sep 4 (Weekday)** — *1.0 Hour*
  * Task: Drafting initial findings for Stage 1 Discovery Workbook.
  * Output: Completed initial draft of Discovery findings.

* **Sat, Sep 5 (Weekend)** — *8.5 Hours*
  * Task: **Stage 1 Workbook Completion & PRD Framing**.
    * 09:00 - 12:30: Categorized sample ticket logs into automated vs. escalation workflows (3.5 hrs).
    * 13:30 - 16:30: Formulated non-functional requirements (FCR targets, latency constraints, compliance) (3.0 hrs).
    * 17:00 - 19:00: Completed `Stage_1_Discovery_Workbook` (2.0 hrs).
  * Output: Finalized Stage 1 Workbook; established empirical justification for 60% FCR goal.

* **Sun, Sep 6 (Weekend)** — *8.5 Hours*
  * Task: **Stage 2 PRD Specification & Architectural Draft**.
    * 09:00 - 12:30: Drafted technical specification for components: Ingestion, Classifier, Retrieval, Router, Generator, Guardrails (3.5 hrs).
    * 13:30 - 16:30: Designed DB schema for governance logging (`decision_logs` table in SQLite) (3.0 hrs).
    * 17:00 - 19:00: Completed `Stage_2_PRD_Template` (2.0 hrs).
  * Output: Finalized Stage 2 PRD document with detailed system requirements.

---

### Week 2: Design, Prompt Engineering & Modular Development (Sep 7 – Sep 13, 2026)

* **Mon, Sep 7 (Weekday)** — *1.5 Hours*
  * Task: Setup prompt library structure and initial system prompt templates.
  * Output: Created baseline prompts for generation and classification.

* **Tue, Sep 8 (Weekday)** — *1.0 Hour*
  * Task: Researching guardrail techniques for prompt injection and PII detection.
  * Output: Documented regex patterns for emails/SSNs/keys and adversarial injection heuristics.

* **Wed, Sep 9 (Weekday)** — *1.5 Hours*
  * Task: Iterative prompt tuning against edge-case queries.
  * Output: Refined generation prompts to enforce strict context-only answers (Zero Hallucination).

* **Thu, Sep 10 (Weekday)** — *1.0 Hour*
  * Task: Drafting Prompt Library Workbook (`Stage 3`).
  * Output: Documented prompt version history and guardrail failure modes.

* **Fri, Sep 11 (Weekday)** — *1.0 Hour*
  * Task: Sprint Planning for core coding phase (`Stage 4`).
  * Output: Created `Stage_4_Sprint_Plan` detailing task breakdowns and milestone deadlines.

* **Sat, Sep 12 (Weekend)** — *9.5 Hours*
  * Task: **Stage 3 & 4 Execution — Core Engine Implementation**.
    * 09:00 - 13:00: Built `src/ingestion.py`, `src/classifier.py`, and `src/retrieval.py` (4.0 hrs).
    * 14:00 - 17:30: Implemented `src/router.py` confidence scoring and `src/guardrails.py` PII/injection filters (3.5 hrs).
    * 18:00 - 20:00: Built `src/generator.py` with OpenRouter API integration and fallback handling (2.0 hrs).
  * Output: Functional modular pipeline prototype.

* **Sun, Sep 13 (Weekend)** — *9.0 Hours*
  * Task: **Governance Logging & Pipeline Orchestration**.
    * 09:00 - 12:30: Implemented `src/db.py` SQLite logger for decision tracking and audit compliance (3.5 hrs).
    * 13:30 - 17:00: Integrated full workflow in `src/pipeline.py` and FastAPI service `src/api.py` (3.5 hrs).
    * 17:30 - 19:30: Built `demo.py` interactive terminal interface for live demonstration (2.0 hrs).
  * Output: End-to-end runnable support automation system.

---

### Week 3: Evaluation, Governance, Documentation & Final Presentation (Sep 14 – Sep 20, 2026)

* **Mon, Sep 14 (Weekday)** — *1.5 Hours*
  * Task: Initial execution of evaluation harness against test dataset.
  * Output: Identified issue with initial confidence threshold (0.80) causing high escalation rate (77.5%).

* **Tue, Sep 15 (Weekday)** — *1.5 Hours*
  * Task: Threshold recalibration and bug fixes in classification routing.
  * Output: Recalibrated confidence threshold to 0.60; achieved target FCR (60%).

* **Wed, Sep 16 (Weekday)** — *1.5 Hours*
  * Task: Formulated automated test suite (`tests/test_pipeline.py`).
  * Output: Created tests covering acceptance criteria A1 through A12 (100% pass rate).

* **Thu, Sep 17 (Weekday)** — *1.5 Hours*
  * Task: Stage 5 PRD Revision Log & Evaluation Summary.
  * Output: Documented threshold revision rationale in `Stage_5_PRD_Revision_Log`.

* **Fri, Sep 18 (Weekday)** — *2.0 Hours*
  * Task: Scripting the 20-minute video presentation (`presentation/video_script_20min.md`).
  * Output: Completed structured presentation script with exact timing cues.

* **Sat, Sep 19 (Weekend)** — *9.0 Hours*
  * Task: **Capstone Report & Final Submission Preparation**.
    * 09:00 - 13:00: Drafted Capstone Report Sections 1 through 5 (Executive Summary to Architecture) (4.0 hrs).
    * 14:00 - 17:30: Drafted Capstone Report Sections 6 through 10 (Implementation to Conclusions) (3.5 hrs).
    * 18:00 - 19:30: Verified repository cleanliness, removed secrets, double-checked `.gitignore` (1.5 hrs).
  * Output: Completed comprehensive Capstone Report document.

* **Sun, Sep 20 (Weekend)** — *5.0 Hours*
  * Task: **Final Quality Check & Packaging**.
    * 09:00 - 11:30: Final video recording run-through and verification against submission criteria (2.5 hrs).
    * 11:30 - 14:00: Final repository checkout test, PDF export, and packaging into `MadhavMehta_Capstone_Submission.zip` (2.5 hrs).
  * Output: Final submission package ready for submission.

---

## 3. Self-Reflection & Key Takeaways

1. **Threshold Calibration Risk:** The biggest challenge encountered was threshold setting. Setting the confidence threshold too high (0.80) severely degraded FCR. Calibrating it to 0.60 backed by empirical evaluation allowed meeting the business goal of 60% FCR while maintaining zero hallucinations.
2. **Governance First:** Building audit logging (`db.py`) into the pipeline from day one made troubleshooting and verification seamless during evaluation.
