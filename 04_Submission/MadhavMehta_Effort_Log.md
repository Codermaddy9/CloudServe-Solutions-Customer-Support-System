# Effort Log

**Name:** Madhav Mehta
**Project:** CloudServe Support Automation

---

## 1. Summary of hours by stage

| Stage | Estimated | Actual | Variance |
|---|---|---|---|
| 1 — Discovery | 12 | 16 | +4 (+33%) |
| 2 — Requirements | 6 | 6 | 0 |
| 3 — Prompt library | 4 | 3 | −1 (−25%) |
| 4 — Sprint plan | 2 | 2 | 0 |
| 5 — Build | 27 | 35 | **+8 (+30%)** |
| 5 — Evaluation and revision | 10 | 17 | **+7 (+70%)** |
| 6 — Governance | 5 | 5 | 0 |
| 6 — Report, video, packaging | 17 | 15 | −2 |
| **Total** | **83** | **99** | **+16 (+19%)** |

---

## 2. Week one

| Day | Task | Hours | Notes |
|---|---|---|---|
| 1 | Read the brief, Build Specification, Submission Guide | 3.0 | Longer than expected. The A9 warning about hardcoded input paths shaped the harness design from the start |
| 1 | Environment, dependency pins, repo skeleton | 2.0 | Under estimate |
| 2 | Read all five transcripts, twice | 2.5 | Second pass was where the disagreements became visible |
| 2 | Discovery analysis script | 4.0 | Estimated 2. The by-intent answerability breakdown was not planned and turned out to matter |
| 2 | First pass at the ticket data | 1.5 | 71.4% answerable against 43.8% resolved. Stopped and re-ran it because I thought I had made an error |
| 3 | Stage 1 workbook, sections 1–3 | 4.0 | |
| 3 | Re-checking the fluency finding | 1.0 | Sofia's account contradicted by the data. Checked three ways before accepting it |
| 4 | Stage 1 workbook, sections 4–6, problem statement | 3.5 | Problem statement rewritten four times to remove technical vocabulary |
| 4 | PRD v1 | 3.0 | |
| 5 | PRD v1 finished, architecture sketch, risk first pass | 3.0 | |
| 5 | Prompt library draft | 2.0 | |
| | **Week one total** | **29.5** | Estimated 24 |

---

## 3. Week two

| Day | Task | Hours | Notes |
|---|---|---|---|
| 1 | Sprint plan | 2.0 | |
| 1 | Ingestion, four channels | 2.0 | Under estimate; the schema is consistent |
| 1 | Retrieval, first attempt | 3.0 | Whole-document chunks. Poor |
| 2 | Retrieval, chunking reworked twice | 5.0 | Estimated 2 for the whole thing. Section-based chunking plus a whole-article chunk was the third attempt |
| 2 | Intent classifier | 3.0 | Quick. 99.8% out-of-fold looked wrong and I spent an hour confirming there was no leakage |
| 3 | Router v1, threshold 0.80 | 3.0 | Threshold taken from the brief's illustrative figure. I did not derive it, which was the mistake |
| 3 | Generation with citations | 4.0 | |
| 3 | Decision log and reconciliation | 4.0 | Estimated 3. Making the reconciliation able to detect duplicates as well as gaps took the extra hour |
| 4 | Guardrails, input and output | 5.0 | |
| 4 | Evaluation harness | 4.0 | On estimate |
| 4 | **First full unattended run** | 1.0 | **Ran clean. The day that paid for itself** |
| 5 | Calibration table, as the Evaluation Framework asks | 2.0 | Expected a formality. Found a 39.79-point error |
| 5 | Investigating, then threshold sweep | 3.0 | Discovered intent confidence barely moved automation precision |
| 5 | Automation-readiness model, router rewrite | 5.0 | Unplanned. This is the revision |
| 5 | Cost-based threshold selection and sensitivity | 2.0 | Unplanned |
| | **Week two total** | **48.0** | Estimated 37 |

---

## 4. Week three

| Day | Task | Hours | Notes |
|---|---|---|---|
| 1 | PRD v2 and Stage 5 revision log | 3.0 | |
| 1 | Governance framework | 5.0 | On estimate. The fairness audit found the 20-point tier gap |
| 2 | Test suite mapped to A1–A12 | 6.0 | Estimated 5. Found two real bugs: the classifier never set its fallback flag, and a feature request was being auto-answered |
| 2 | Runner-up veto rule, fixing both bugs | 2.0 | Unplanned |
| 2 | Clean-checkout rehearsal | 1.5 | From an empty directory. Two README steps were wrong |
| 3 | Retrieval hybrid and comparison script | 3.0 | Result was that it makes no measurable difference, which is worth reporting |
| 3 | Demo rewritten to check itself | 1.5 | Immediately caught the score-normalisation bug that broke A4 |
| 3 | Fixing the relevance gate | 1.5 | Unplanned. Found by the demo, not by a test |
| 4 | README and architecture notes | 5.0 | |
| 4 | Report, sections 1–6 | 5.0 | |
| 5 | Report, sections 7–11 | 4.0 | |
| 5 | Effort log, packaging, final checks | 2.0 | |
| 5 | Video | — | Pending |
| | **Week three total** | **39.5** | Estimated 30 |

---

## 5. Estimates against reality

| Where I was wrong | By how much | Why |
|---|---|---|
| Evaluation and revision | **+70%** | I estimated the *running* of an evaluation and not the *acting* on it. The calibration finding cost ten hours nobody planned for, and it was the most valuable ten hours in the project |
| Retrieval | +150% on the component | Chunking strategy is a design decision, and I had estimated it as a configuration choice |
| Discovery analysis | +100% | Every question answered produced two more worth asking |
| Testing | +20%, plus 3.5 h of unplanned fixes | Correct estimate for writing the tests. What I had not budgeted for was the tests finding real bugs, which in hindsight is the point of writing them |
| Prompt library | −25% | Over-estimated. Only three components use a prompt at all; the rest is deterministic code |
| Report | −12% | The material was already written up in the workbooks |

**Overall: 19% over.** The pattern is consistent — everything involving
*discovering something* ran over, and everything involving *writing down what I
already knew* ran on or under. I would now estimate any task whose output is a
finding at roughly double, and any task whose output is a document at par.

---

## 6. Where the time went unexpectedly

**The ten hours that were not in any plan** were spent between Thursday
afternoon and Friday of week two, after the calibration table showed the
routing signal was off by 39.79 points. Replacing the signal, rebuilding the
router, deriving a threshold from a cost model and rewriting the requirements
were all unplanned, and they are the substance of what this submission has to
show. Had the full run happened on day five as the Build Specification
suggests, there would have been no time to act on it and the project would have
shipped a threshold on a meaningless number.

**The 3.5 unplanned hours in week three** were bug fixes surfaced by the test
suite and by the demonstration script. Two of the three bugs — the
never-automate rule defeated by a near-uniform classifier, and the score
normalisation that made a gibberish query return a confident result — would
have been invisible in a demonstration on hand-picked tickets. The one that
broke A4 was caught by making the demo check its own output rather than print a
success line.

---

## 7. Declaration

This log was filled in as the work was done, at least every second day. The
variances are uneven and one stage ran 70% over, which is what an honest record
of this kind looks like.

**Madhav Mehta**
