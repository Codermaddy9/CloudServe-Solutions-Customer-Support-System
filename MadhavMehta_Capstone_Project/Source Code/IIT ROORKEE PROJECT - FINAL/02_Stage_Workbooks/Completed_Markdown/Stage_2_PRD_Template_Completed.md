# Stage Two: Requirements — Product Requirements Document

**Product:** CloudServe support automation
**Author:** Madhav Mehta

---

## 1. Document control

| Field | Value |
|---|---|
| Version | **2.0** |
| Status | Revised after measurement; supersedes v1.0 |
| Previous version | 1.0 — routing on intent-classifier confidence at T = 0.80 |
| What changed in v2.0 | The routing signal and the threshold. See Stage 5. |
| Evidence base | Stage 1 workbook; `evaluation/discovery_analysis.py`; `evaluation/calibrate.py` |

Every requirement below carries a **Traceability** row naming the discovery
evidence that produced it. A requirement with no traceable origin is a
requirement somebody wanted rather than one the client needs.

---

## 2. The problem in one paragraph

CloudServe's support team is not short of answers — it is short of a way to find
them. 71.4% of incoming tickets are already answered in the 29 support articles
the company maintains, but only 43.8% are resolved at first contact, and 49.11%
of everything escalated to a Tier 2 engineer had a documented answer available.
Agents rebuild answers from memory because searching the documentation is
harder than rewriting it. The system required is one that finds and delivers
the existing answer, states plainly when there is not one, and hands the rest
to a person with the analysis already attached.

---

## 3. Who this is for

| User group | Size | What they need | Evidence |
|---|---|---|---|
| **Customers** | ~200 corporate accounts, 500+ tickets/week | A correct answer quickly, honestly labelled, with its source so they can verify it. Urgency respected: a failing deployment is not a pagination question | Ravi, interview five |
| **Tier 1 agents** | 6 | Not to spend most of each ticket searching. Not to apologise for an answer they did not write | Sofia, interview two |
| **Tier 2 engineers** | Small | Escalations that arrive with the thinking done: likely intent, sources, and what the system was unsure of | Daniel, interview three |
| **Head of Support** | 1 | Response time and FCR to move without new headcount; every decision explainable for the autumn compliance review | Marcus, interview one |
| **Technical writer** | 1 | To know which article produced an answer, so a wrong answer can be traced to a wrong article or a misread one | Ines, interview four |

---

## 4. Functional requirements

### FR-01 — Ingest all four channels into one representation

The system accepts tickets from email, live chat, documentation comments and
the community forum, and normalises them into a single internal representation
preserving the original text and the original channel. Missing fields, unusual
characters and empty bodies are handled without failing.

- **Acceptance:** a ticket from each channel is processed without channel-specific breakage; a ticket with no body, no id and no recognised channel still produces a result.
- **Traceability:** Stage 1 §2 — four channels, and docs_comment (15.6% of volume) is the worst-performing and was mentioned by nobody.
- **Implemented:** `src/ingestion.py` · **Tested:** `TestA2Ingestion` · **Criterion:** A2

### FR-02 — Classify intent and urgency with a numeric confidence

Every ticket receives an intent, an urgency and a numeric confidence in [0,1],
together with the alternatives considered. Where classification is impossible a
defined fallback is returned rather than an exception.

- **Acceptance:** class and confidence present on every ticket; alternatives recorded; empty input returns the fallback and is flagged as such.
- **Traceability:** Stage 1 §2 — 22 intents with none above 5.8%, so routing cannot be hand-coded per category. Stage 1 §3 — urgency matters because Ravi's failing deployment and pagination question share a queue.
- **Implemented:** `src/classifier.py` · **Tested:** `TestA3Classification` · **Criterion:** A3

### FR-03 — Retrieve from the reviewed corpus, and return nothing when nothing fits

Retrieval searches only Ines's 29 reviewed articles, returns ranked passages
with scores and identifiers that resolve to the real corpus, and applies a
relevance threshold — returning nothing rather than something irrelevant.

- **Acceptance:** returned ids resolve to real articles; results ranked by score; an irrelevant query returns an empty list.
- **Traceability:** Ines, interview four, on why keyword search fails. Daniel, interview three, on stale snippet files — which is why the corpus is restricted to reviewed articles and the system never learns from historic agent responses.
- **Implemented:** `src/retrieval.py` · **Tested:** `TestA4Retrieval` · **Criterion:** A4

### FR-04 — Route deterministically against a threshold determined from data

The routing decision applies, in order: governance policy on intent, a veto
where a never-automate intent is a close runner-up, a grounding requirement,
the calibrated threshold, and an enterprise-urgency rule. The same input
produces the same decision and the same stated reason every time. The reason is
written in language a support manager could read.

- **Acceptance:** identical decision, score and reason on repeat; threshold recorded on every decision; a security incident escalates on policy regardless of confidence.
- **Traceability:** Sofia's own three escalation criteria (does not know / not confident enough / security) map directly onto these rules. Marcus: "I would rather it said nothing than said something wrong." Corpus: four intents flagged `must_not_auto_respond` at 100%.
- **Implemented:** `src/router.py` · **Tested:** `TestA5Routing` · **Criterion:** A5

### FR-05 — Generate grounded answers with resolvable citations, and disclose automation

Answers are grounded in retrieved passages with citations attached to claims.
The system states plainly when it does not know rather than filling the gap.
Ticket content is passed as data, never as instruction. Every automated reply
says that it was drafted automatically and names its sources.

- **Acceptance:** every citation resolves to a passage retrieval returned; invented document ids are discarded; the disclosure appears on every automated reply.
- **Traceability:** Ravi, interview five: "I calibrate how much I trust it… Hiding that would be the thing that annoys me." Ines: "I would want to know which article an answer came from."
- **Implemented:** `src/generator.py` · **Tested:** `TestA6Citations` · **Criterion:** A6

### FR-06 — Validate every response before release, with the power to block

Every generated response passes validation before it can be sent, in the
evaluation run exactly as in the API. The validator checks the kill switch,
unauthorised commitments, private data, citation grounding and the confidence
floor. It records what it checked whether or not anything fired. Private data
causes a block and an escalation; it is never redacted and sent.

- **Acceptance:** an engineered ticket is blocked rather than answered; an acceptable response is not blocked; checks recorded on every response.
- **Traceability:** Daniel: "nothing automated should be making commitments about money." Governance Framework §4. Marcus's stated failure condition.
- **Implemented:** `src/guardrails.py` · **Tested:** `TestA7Guardrails` · **Criterion:** A7

### FR-07 — Log every automated decision so it can be reconstructed later

One record per ticket on every path, including blocked tickets and internal
failures, carrying the input summary, prediction and confidence, alternatives,
sources used with scores, threshold applied, action, reason, guardrail results,
prompt version and requirement ids, plus the channel, tier and fluency needed
for the fairness audit.

- **Acceptance:** logged decisions, distinct tickets and tickets processed all reconcile exactly; the check detects both a gap and a duplicate.
- **Traceability:** Marcus: "I have a compliance review in the autumn… I need to be able to say why it did what it did." Governance Framework §1.
- **Implemented:** `src/db.py` · **Tested:** `TestA8DecisionLog` · **Criterion:** A8

### FR-08 — Process a full unseen ticket file unattended and report on it

A single documented command takes an input path and an output path, processes
every ticket in the file, drops none, logs every decision and produces a
metrics report with no further manual work.

- **Acceptance:** run against a file never seen before, with unfamiliar ids and length; every ticket produces an answer, an escalation or a block; report files appear.
- **Traceability:** Build Specification §4.
- **Implemented:** `evaluation/harness.py` · **Tested:** `TestA9A10UnattendedRun` · **Criteria:** A9, A10

### FR-09 — Escalations carry a handover brief

An escalated ticket carries the likely intent, the alternatives considered, the
retrieved articles with scores, a plain statement of why the system did not
answer, and an excerpt of what the customer wrote.

- **Acceptance:** every escalation has a brief naming the trigger and the sources.
- **Traceability:** Daniel, interview three: "I do not need it to be right. I need it to show its working." Currently escalations arrive as bare forwarded tickets.
- **Implemented:** `src/router.py` · **Tested:** `TestA5Routing::test_escalation_carries_the_brief_and_the_sources`

### FR-10 — Provide a kill switch

Automated responding can be stopped immediately, without a restart or a
deployment. While engaged, every response is blocked and the ticket goes to a
human; nothing is dropped. The operation is itself logged.

- **Acceptance:** engaging blocks; releasing resumes; both recorded.
- **Traceability:** Governance Framework §5.
- **Implemented:** `src/guardrails.py`, `POST /killswitch` · **Demonstrated:** `demo.py` scenario 6

---

## 5. Non-functional requirements

| ID | Requirement | Target | Traceability | Status on the recorded run |
|---|---|---|---|---|
| NFR-01 | Response latency | p95 under 3s | Ravi: live chat customers leave | **5.42 ms** |
| NFR-02 | Degrade rather than stop when the provider fails | No crash on timeout, error status, malformed response, or no provider at all | Criterion A11; free-tier throttling is expected | Verified across six induced failure modes |
| NFR-03 | Run from a clean checkout on another machine | README followed literally | Criterion A1 | Verified from an empty directory |
| NFR-04 | No credential anywhere in the repository or its history | Zero | Brief §9 | `.env` git-ignored before the first commit; asserted by test |
| NFR-05 | Confidence calibrated | Stated within 5 points of observed | Evaluation Framework §3 | **4.24 points** on the readiness score |
| NFR-06 | Quality variation across customer groups | Under 5 points | Governance Framework §3; Ravi on renewals | **20.0 points — NOT MET.** See Stage 5 and the fairness audit |
| NFR-07 | Cost | Free tiers only | Brief §9 | Runs with no provider at all |
| NFR-08 | Tests run with one documented command | `python -m pytest tests/ -v` | Criterion A12 | 61 passing |

---

## 6. What is deliberately out of scope

| Out of scope | Why | Evidence |
|---|---|---|
| Automated answers to security incidents, compliance requests, feature requests and unclear tickets | All four are flagged `must_not_auto_respond` on 100% of their tickets; feature and unclear requests additionally have **0%** documented answers | Corpus; Daniel, interview three |
| Any commitment about refunds, credits, quotas or dates | Contractual; not the system's to make | Daniel, interview three |
| Learning from historic agent responses or private snippet files | Daniel: they contain answers "correct two years ago and not right since". Training on them would scale a mistake invisibly | Interview three |
| Multi-turn conversation | The queue is single-turn tickets; multi-turn would change the problem | Stage 1 §3 |
| Writing or editing documentation | Ines owns the corpus and its review cycle | Interview four |
| Replacing agents | 20% of volume consumes 32% of effort and must stay human. The goal is returning time, not removing people | Stage 1 §3 |

---

## 7. Assumptions and their consequences

| Assumption | If it is wrong | How exposed | Mitigation |
|---|---|---|---|
| 71.4% answerable holds on live traffic | The ceiling on automation is lower than projected | High | Answerability is measured on every run, so drift is visible |
| `expected_route` reflects what CloudServe would actually want | Automation precision is measured against the wrong target | **High** | Stated as a limitation in the report; the harm measure used instead is automated-but-flagged, which is zero |
| A wrong automated answer costs about 12× a resolved one | The threshold is wrong | **High** | Sensitivity published; at 20 the optimum moves to 0.90 |
| Agents respond to escalations at the historic median | Reply-time projection is wrong | Medium | Both figures reported separately, projection labelled as such |
| The synthetic corpus resembles real traffic | Classification figures collapse in production | **High** | Stated plainly; 100% precision is presented as a property of this data |
| Ines's articles stay current | Correct citations to stale advice | Medium | `doc_id` on every logged answer, so a bad article is traceable to every reply that used it |

---

## 8. Success measures

| Measure | Baseline | Target | Achieved | |
|---|---|---|---|---|
| First contact resolution | 43.8% | ≥ 60% | **75.0%** | Met |
| Escalation rate | 56.2% | ≤ 30% | **25.0%** | Met |
| Classification macro precision | — | ≥ 85% | **100%** | Met |
| Citation accuracy | — | ≥ 95% | **96.67%** | Met |
| Hallucination rate (proxy) | — | ≤ 5% | **0%** | Met |
| Latency p95 | — | < 3s | **5.42 ms** | Met |
| Private data occurrences | — | 0 | **0** | Met |
| Decision log reconciliation | — | exact | **80/80** | Met |
| Mean reply, whole queue | 8–12 hrs | < 5 min | **54.5 min** | **Not met** |
| Cross-group variation | — | < 5 pts | **20.0 pts** | **Not met** |

Two targets were not met and both are discussed in Stage 5 and in the report
rather than being left to be noticed.

---

## 9. Open questions

1. Which CSAT figure is current — the 3.2 Marcus reports or the 2.97 in the record?
2. What does a wrong automated answer cost CloudServe? The threshold depends on it and only a range has been assumed.
3. Who is accountable for an automated answer that proves wrong? Assumed to be the Head of Support.
4. Is `expected_route` CloudServe's genuine policy or one annotator's judgement? It is the target the system is optimised against.
5. Can the agents' private snippet files be recovered and reviewed? If so, the documented share may exceed 71.4%.
6. Should the resolution gap between customer tiers be closed, or is differentiated service intended? Ravi assumes the latter exists and objects to it widening.
