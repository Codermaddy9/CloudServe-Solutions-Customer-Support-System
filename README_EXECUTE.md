# How to run and verify this submission

**CloudServe Support Automation** — Madhav Mehta
Forward Deployed AI Engineering Capstone

This file is for the assessor. It contains only what is needed to run the
system and check it against the twelve acceptance criteria. `README.md` has the
design rationale and the results.

---

## Requirements

Python **3.10 or later**. Nothing else.

No database to provision. No API key needed. No network access required at run
time. The system generates answers locally from the retrieved documentation
when no model provider is configured, and the full evaluation runs in that mode.

---

## The four commands

From a clean checkout, in the repository root:

```bash
# 1. Install
pip install -r requirements.txt

# 2. Verify everything at once  (recommended — see below)
python verify_gate.py

# 3. Run the unattended evaluation on any ticket file
python -m evaluation.harness --input 05_Datasets/validation_tickets.json --output evaluation/results/

# 4. Run the tests
python -m pytest tests/ -v
```

---

## Running against your own hidden ticket set

The harness takes the input and output paths as arguments. Nothing about the
filename, the directory, the ticket count or the ticket ids is assumed.

```bash
python -m evaluation.harness --input /any/path/to/your_hidden_set.json --output /any/output/folder/
```

The input may be a bare JSON list of tickets, or an object wrapping one under a
`tickets`, `data`, `items` or `records` key. Tickets with the `labels` block
removed are processed normally; the label-dependent metrics are simply omitted
rather than failing.

It writes four files into the output folder:

| File | Contents |
|---|---|
| `metrics_report.md` | Human-readable results, with pass/fail computed per target |
| `metrics_report.json` | The same figures as data |
| `processed_tickets.json` | Per-ticket decision, routing reason, sources and response |
| `evaluation_decisions.db` | SQLite audit log, one record per ticket |

---

## `verify_gate.py` — the fastest way to check everything

```bash
python verify_gate.py
```

This builds a 120-ticket file in a temporary directory outside the repository,
with a filename and ticket ids the code has never seen, runs the documented
harness command against it, and checks eighteen things. It writes nothing into
the repository and removes its temporary files afterwards. A different random
sample is drawn each time it runs.

**Expected result: `GATE REHEARSAL PASSED — 18 of 18 checks`**

It verifies: the run completes unattended; all four output files appear; every
ticket is processed with none dropped or duplicated; the decision log
reconciles exactly; the required volume, business, technical and governance
figures are present including per-class precision and recall; ten adversarial
guardrail probes all behave correctly; the test suite passes; and no API key
appears in the repository.

---

## The twelve acceptance criteria

The test suite is organised by criterion, so `python -m pytest tests/ -v` prints
them by name. Expect **65 tests passing**.

| # | Criterion | How to check it | Test class |
|---|---|---|---|
| A1 | Runs from a clean checkout | Follow this file | `TestA1DocumentedEntryPoints` |
| A2 | Four channels ingested and normalised | `python demo.py` scenarios 1–4 | `TestA2Ingestion` |
| A3 | Intent and urgency with numeric confidence | Any harness run | `TestA3Classification` |
| A4 | Retrieval returns real, identifiable passages | `demo.py` scenario 4 returns nothing for a query that matches nothing | `TestA4Retrieval` |
| A5 | Threshold applied; same input, same decision | `demo.py` scenario 5 runs one ticket twice | `TestA5Routing` |
| A6 | Citations resolve to retrieved passages | `processed_tickets.json`, compare `citations` against `retrieval_hits` | `TestA6Citations` |
| A7 | A guardrail blocks when triggered | `demo.py` scenario 3; probes in every harness run | `TestA7Guardrails` |
| A8 | Persistent decision log that reconciles | `metrics_report.md` §4 | `TestA8DecisionLog` |
| A9 | Full set processed in one unattended run | `verify_gate.py` | `TestA9A10UnattendedRun` |
| A10 | That run produces a metrics report | The four output files | `TestA9A10UnattendedRun` |
| A11 | Degrades without crashing | See "Inducing failures" below | `TestA11FailureHandling` |
| A12 | Tests run with one documented command | `python -m pytest tests/ -v` | `TestA12TestSuite` |

---

## Seeing individual behaviour

```bash
python demo.py
```

Six scenarios against the live pipeline: an automated answer with citations, a
security incident escalated on policy with a handover brief, a prompt injection
blocked, a query that matches nothing and is escalated rather than answered,
the same ticket run twice to show determinism, and the kill switch stopping and
resuming automated responding.

Each scenario states what it expects and compares that against what happened.
It will report a failure rather than printing a success line regardless.

**Expected: `6 of 6 scenarios behaved as expected`**

---

## Inducing failures (A11)

The system must degrade rather than stop. Each condition below is covered by a
test, and can also be induced by hand.

| Condition | How to induce it | Expected behaviour |
|---|---|---|
| Model provider unavailable | Run with no `.env` at all | Answers generated locally from retrieved passages; run completes |
| Provider times out or rate-limits | Set `OPENROUTER_API_KEY` to an invalid value | Falls back to local generation; reported as `local_fallback` in the metrics |
| No retrieval match | Submit a ticket of nonsense text | Retrieval returns nothing; ticket escalates rather than being answered |
| Malformed input | A ticket with no id, no body, or a non-object entry | Processed on the degraded path, logged, and escalated. Nothing is dropped |
| Corpus missing | Rename `05_Datasets/documentation.json` | Harness warns at startup; every ticket escalates for want of grounding |

---

## Optional

```bash
# REST API, then open http://127.0.0.1:8000/docs
python -m src.api

# The analysis behind the problem statement and the threshold
python -m evaluation.discovery_analysis
python -m evaluation.calibrate
python -m evaluation.compare_retrieval
```

`GET /health` reports which retrieval backend is live, whether each model
trained, and the threshold in force.

---

## Notes

**Retrieval has three tiers** and uses the best available, always reporting
which. Tier 1 is Chroma with `all-MiniLM-L6-v2`; tier 2 is a local latent
semantic index; tier 3 is TF-IDF. Tier 1 is deliberately **not** in
`requirements.txt`, so that a clean-checkout run cannot fail on a large
optional download. To enable it: `pip install chromadb sentence-transformers`.
All three measured identically on this corpus, which is reported in
`evaluation/results/retrieval_comparison.md`.

**The corpus must ship with the repository.** The classifier trains from
`05_Datasets/development_tickets.json` and retrieval indexes
`05_Datasets/documentation.json` at startup. Only the hidden ticket file comes
from the assessor.

**Two targets are reported as FAIL** in the metrics report, and this is
deliberate rather than an oversight. Mean reply time across the whole queue
cannot reach five minutes through automation alone, and cross-group resolution
variation by customer tier exceeds the five-point governance condition. Both
are analysed in §7 and §8 of the report.

**If `storage/decisions.db` exists from an older version**, it is migrated in
place on startup and the added columns are reported. Existing records are
preserved.

---

## Documents

| Path | What it is |
|---|---|
| `README.md` | Design rationale, architecture, results |
| `docs/architecture.md` | Every design decision and the alternatives considered |
| `04_Submission/MadhavMehta_Capstone_Report.md` | The project report |
| `04_Submission/MadhavMehta_Governance_Framework.md` | Risk register, fairness audit, incident procedure |
| `04_Submission/MadhavMehta_Effort_Log.md` | Hours by stage |
| `02_Stage_Workbooks/Completed_Markdown/` | Stages one to five |
| `evaluation/results/` | Generated evidence from the recorded run |
