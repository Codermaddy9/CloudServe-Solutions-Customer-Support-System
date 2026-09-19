# Stage Four: Sprint Plan

**Author:** Madhav Mehta

---

## Section one: capacity

An individual project alongside other commitments. Realistic rather than
optimistic capacity, because a plan built on best-case hours produces a backlog
that is abandoned in week two.

| Week | Available hours | Committed to | Contingency held |
|---|---|---|---|
| One | 28 | Discovery, requirements, environment | 4 h |
| Two | 34 | Build, evaluation, revision | 6 h |
| Three | 26 | Governance, report, video, packaging | 5 h |
| **Total** | **88** | | **15 h (17%)** |

Contingency is held rather than allocated. Every previous estimate I have made
on a project of this shape has been optimistic by roughly a fifth, and the
effort log records whether that held again.

---

## Section two: the backlog

Owner is the author throughout; the column is retained because the workbook
asks for it and because "definition of done" is the part that actually matters.

| ID | Item | Est | Actual | Depends on | Definition of done |
|---|---|---|---|---|---|
| T-01 | Environment, dependency pins, repository skeleton | 3 h | 2 h | — | `pip install -r requirements.txt` succeeds from an empty venv |
| T-02 | Read all five transcripts; note claims to verify | 3 h | 4 h | — | Every claim that can be checked against data is written down as a question |
| T-03 | Discovery analysis script | 4 h | 6 h | T-01, T-02 | One command regenerates every figure in the workbook |
| T-04 | Stage 1 workbook | 5 h | 6 h | T-03 | Every row cites either a transcript or a computed figure |
| T-05 | PRD v1 | 4 h | 4 h | T-04 | Every requirement names its discovery evidence |
| T-06 | Ingestion, four channels | 3 h | 2 h | T-01 | A ticket from each channel normalises; malformed input does not raise |
| T-07 | Retrieval and chunking | 5 h | 8 h | T-06 | Ids resolve to real articles; an irrelevant query returns nothing |
| T-08 | Intent classifier | 4 h | 3 h | T-06 | Per-class precision and recall reported, not just accuracy |
| T-09 | Router and threshold | 4 h | 9 h | T-07, T-08 | Deterministic; threshold justified from data, not chosen |
| T-10 | Generation with citations | 4 h | 4 h | T-07 | Every citation resolves to a retrieved passage |
| T-11 | Guardrails, input and output | 4 h | 5 h | T-10 | A guardrail blocks a real attempt, and does not block an acceptable answer |
| T-12 | Decision log and reconciliation | 3 h | 4 h | T-09 | Logged decisions equal tickets processed, and the check can fail |
| T-13 | Evaluation harness | 4 h | 4 h | T-06..T-12 | `--input`/`--output`; a full unseen file processed with no intervention |
| T-14 | Metrics and report generation | 4 h | 6 h | T-13 | Every pass/fail computed from the value; none written by hand |
| T-15 | Calibration and threshold selection | 3 h | 7 h | T-08, T-09 | Calibration error measured; threshold selected against a stated cost model |
| T-16 | Test suite mapped to A1–A12 | 5 h | 6 h | all | One command; a failure names the criterion it broke |
| T-17 | PRD v2 and revision log | 3 h | 3 h | T-15 | At least one substantive change with its measured trigger |
| T-18 | Governance framework | 5 h | 5 h | T-12, T-14 | Risk register with owners; fairness audit with method and sample size |
| T-19 | README and architecture notes | 4 h | 5 h | all | Followed literally from an empty directory by someone else |
| T-20 | Report | 8 h | 9 h | all | Every claim carries how it was measured and on what |
| T-21 | Video | 6 h | — | T-19, T-20 | 18–22 min; live demo including an escalation and a guardrail firing |
| T-22 | Packaging and final checks | 3 h | — | all | Four folders, correct names, clean-checkout rehearsal passed |

---

## Section three: week two, day by day

Built to the Build Specification checkpoints, with the end-to-end run pulled to
day four rather than day five.

| Day | Target | Checked by |
|---|---|---|
| 1 | Ingest. A ticket from each channel normalises | Print the normalised object for one ticket per channel |
| 2 | Retrieval. Corpus indexed, passages traceable | Query a known question, confirm the right article comes back and a nonsense query returns nothing |
| 3 | Classification and routing. Confidence scored, threshold applied, every decision logged with a reason | Run 20 tickets and read the log end to end |
| 4 | **Full chain over the full validation set, unattended** | Start it, leave, return to a metrics report |
| 5 | Guardrails blocking; calibration; threshold re-derived | An engineered ticket blocks; calibration error measured |

**Why the run moved to day four.** The Build Specification puts it on day five.
Moving it one day earlier buys a whole day to react to what it says, and the
brief is explicit that the most common failure is discovering results too late
to act on them. It was the single best scheduling decision in the project: the
day-four run is what surfaced the calibration problem, and had it happened on
day five the threshold would have shipped uncorrected.

---

## Section four: week three, day by day

| Day | Target |
|---|---|
| 1 | Governance: risk register, fairness audit against the run, incident procedure, kill switch |
| 2 | CI; clean-checkout rehearsal from an empty directory on a different machine |
| 3 | Report sections 1–5 |
| 4 | Report sections 6–10; first video take |
| 5 | Second video take; packaging; final checklist |

---

## Section five: what gets dropped if time runs out

Decided in advance, in priority order, so that the decision is not made at
midnight on the last day.

| Priority | Item | Why it goes in this order |
|---|---|---|
| Dropped first | Tier 1 semantic retrieval benchmarking | The fallback is measured and works; the gap is an honest caveat rather than a defect |
| Second | Prometheus and Grafana monitoring | Nothing in A1–A12 requires it. The decision log already answers the operational questions |
| Third | Depth in the fairness audit beyond the three segments | Three segments satisfy the requirement; more would be better but is not load-bearing |
| Fourth | A second video take | Costs polish, not correctness |
| **Never dropped** | The unattended run, the decision log, the guardrails, the honest metrics | These are the gate and the difference between a working system and a demonstration |

In the event, the first three were dropped. Monitoring and the semantic
benchmark are both recorded as outstanding work rather than quietly omitted.

---

## Section six: daily check-in record

| Day | Planned | Actual | Carried |
|---|---|---|---|
| W1 D1 | Environment, read the brief | Done, plus transcripts | — |
| W1 D2 | Transcripts and analysis script | Script took longer; the by-intent answerability breakdown was worth the extra time | 2 h |
| W1 D3 | Stage 1 workbook | Done. The fluency finding contradicted Sofia and needed rechecking | 1 h |
| W1 D4–5 | PRD v1 | Done | — |
| W2 D1 | Ingest, retrieval | Ingest quick, retrieval slow — chunking strategy reworked twice | 3 h |
| W2 D2 | Classifier, router | Classifier quick. 100% accuracy looked wrong and needed investigating | — |
| W2 D3 | Generation, guardrails, logging | Done | — |
| W2 D4 | **Full unattended run** | **Ran. Surfaced the calibration problem.** | — |
| W2 D5 | Calibration, threshold, PRD v2 | Overran badly; the routing signal was replaced entirely | 5 h |
| W3 D1 | Governance | Done. The fairness audit found a 20-point tier gap | — |
| W3 D2 | Tests, clean checkout | The test suite found two real bugs | 2 h |
| W3 D3–5 | Report, video, packaging | In progress | — |

**The one that mattered.** W2 D4's run is the reason this project has a genuine
revision to report rather than an invented one. Everything that changed in
PRD v2 came out of that afternoon.
