# CloudServe Support Automation

**Forward Deployed AI Engineering — Capstone Project**
Madhav Mehta

A support automation system for CloudServe Solutions. It ingests tickets from
four channels, classifies them, retrieves the supporting documentation, decides
whether it can answer or whether a person should, drafts a cited answer,
validates that answer before anything is sent, and records every decision it
took in a form that can be audited months later.

---

## 1. Running it from a clean checkout

Written for someone who has never seen this project. Every command below was
run from an empty directory on a machine other than the author's.

### Requirements

Python 3.10 or later. Nothing else. No database to provision, no API key
required, no network access needed at run time.

### Step 1 — install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2 — configure (optional)

The system runs with no configuration at all. If you want it to draft answers
through a language model rather than locally, copy the template and add a key:

```bash
cp .env.example .env          # macOS / Linux
Copy-Item .env.example .env   # Windows PowerShell
```

Without a key the system generates answers locally from the retrieved
documentation. That is a supported operating mode, not a degraded one, and the
full evaluation below runs in it. See section 4.

### Step 3 — run the unattended evaluation

```bash
python -m evaluation.harness --input 05_Datasets/validation_tickets.json --output evaluation/results/
```

`--input` and `--output` are required arguments. Point `--input` at any file of
tickets in the documented schema; nothing about the filename or the ticket ids
is assumed.

Expect: 80 tickets processed in under a second, a decision log that reconciles
exactly, and `metrics_report.json` and `metrics_report.md` written to the
output directory without further work.

### Step 4 — run the tests

```bash
python -m pytest tests/ -v
```

Expect 65 tests passing, organised by acceptance criterion.

### Step 5 — rehearse the gate (recommended before submitting)

```bash
python verify_gate.py
```

Builds a ticket file this code has never seen — new directory, new filename,
new ticket ids — runs the documented command against it, and checks the result
the way an assessor would: every ticket accounted for, decision log reconciled,
required figures present, guardrails live, tests passing, no credentials. It
writes nothing into the repository.

Expect **18 of 18 checks passed**.

### Step 6 — see it work on individual tickets (optional)

```bash
python demo.py
```

Walks through an auto-answered ticket, an escalation with its handover brief,
and a guardrail blocking an attack.

### Step 7 — start the API (optional)

```bash
python -m src.api
```

Then open <http://127.0.0.1:8000/docs>.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Service state, threshold, whether each model loaded |
| `POST /ingest` | Process one ticket end to end |
| `GET /metrics` | Decision log totals and reconciliation |
| `POST /killswitch` | Stop or resume automated responding immediately |

### Analysis scripts (optional, not needed for the gate)

```bash
python -m evaluation.discovery_analysis    # the evidence behind the problem statement
python -m evaluation.calibrate             # confidence calibration and threshold selection
python -m evaluation.compare_retrieval     # lexical against hybrid retrieval
```

---

## 2. Acceptance criteria

Each criterion maps to the code that implements it and the tests that check it.
Run `python -m pytest tests/ -v` to see them evaluated by name.

| # | Criterion | Where it lives | Tests |
|---|---|---|---|
| **A1** | Runs from a clean checkout using the documented commands | This README; `requirements.txt` pins only what is needed | `TestA1DocumentedEntryPoints` |
| **A2** | All four channels ingested and normalised into one representation | `src/ingestion.py` | `TestA2Ingestion` |
| **A3** | Intent and urgency classified with a numeric confidence | `src/classifier.py`, `src/automation_readiness.py` | `TestA3Classification` |
| **A4** | Retrieval returns identifiable passages from the real corpus | `src/retrieval.py` | `TestA4Retrieval` |
| **A5** | Routing applies a threshold; same input, same decision | `src/router.py` | `TestA5Routing` |
| **A6** | Citations resolve to passages actually retrieved | `src/generator.py` | `TestA6Citations` |
| **A7** | At least one guardrail can block, and does | `src/guardrails.py` | `TestA7Guardrails` |
| **A8** | Every decision written to a persistent log that reconciles | `src/db.py` | `TestA8DecisionLog`, `TestSchemaMigration` |
| **A9** | Full set processed in a single unattended run | `evaluation/harness.py` | `TestA9A10UnattendedRun` |
| **A10** | That run produces a metrics report with no further work | `evaluation/metrics.py` | `TestA9A10UnattendedRun` |
| **A11** | Failure handled without crashing | Throughout; `src/pipeline.py` is the backstop | `TestA11FailureHandling` |
| **A12** | Tests run with a single documented command | `python -m pytest tests/ -v` | `TestA12TestSuite` |

---

## 3. What the system does, and why

CloudServe asked for a chatbot. The discovery evidence says the problem is not
that answers are missing.

**71.4% of tickets are answerable from CloudServe's own documentation, but only
43.8% were resolved on first contact** — a 27.6 point gap between the answers
that exist and the answers that reach customers. Nearly half of everything
escalated to a Tier 2 engineer already had a documented answer. Sofia Restrepo
put it at "seven out of ten" in her interview; the data says 71.4%, and she was
right. Ines Varga, who wrote the articles, knows the support team barely uses
them and knows why: her titles and customers' phrasings do not meet in a
keyword search.

So this is a delivery problem, not an answer-shortage problem, and the system
is built to close that specific gap. `python -m evaluation.discovery_analysis`
regenerates every figure above.

```
                    ticket (email · chat · forum · docs comment)
                                      │
                         ┌────────────▼────────────┐
                         │  ingest & normalise     │  A2
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │  input validation       │  A7 ── blocked ─┐
                         └────────────┬────────────┘                 │
                                      │                              │
                  ┌───────────────────┼───────────────────┐          │
                  ▼                   ▼                   ▼          │
          ┌───────────────┐  ┌────────────────┐  ┌────────────────┐  │
          │ classify      │  │ retrieve       │  │ score          │  │
          │ intent+urgency│  │ hybrid, cited  │  │ automation     │  │
          │      A3       │  │      A4        │  │ readiness  A3  │  │
          └───────┬───────┘  └────────┬───────┘  └────────┬───────┘  │
                  └───────────────────┼───────────────────┘          │
                                      ▼                              │
                         ┌─────────────────────────┐                 │
                         │  route                  │  A5             │
                         └───┬─────────────────┬───┘                 │
                 auto_respond│                 │escalate             │
                             ▼                 ▼                     │
                   ┌──────────────┐   ┌──────────────────┐           │
                   │ generate  A6 │   │ handover brief   │           │
                   │ cited answer │   │ + sources + what │           │
                   └───────┬──────┘   │ we were unsure of│           │
                           ▼          └────────┬─────────┘           │
                  ┌──────────────┐             │                     │
                  │ validate  A7 ├── blocked ──┼─────────────────────┤
                  └───────┬──────┘             │                     │
                          │ passed             │                     │
                          ▼                    ▼                     ▼
                  ┌───────────────────────────────────────────────────┐
                  │  decision log — one record per ticket, always  A8 │
                  └───────────────────────────────────────────────────┘
```

Three decisions are worth explaining, because each came out of the evidence
rather than out of the architecture diagram.

**Escalation carries a brief, not just the ticket.** Daniel Okonkwo said
escalations reach him as a bare forwarded ticket with no note of what was
already tried, and that he would be twice as fast with context: "I do not need
it to be right. I need it to show its working." Every escalation therefore
carries the likely intent, the alternatives considered, the retrieved articles
with their scores, and a plain statement of why the system did not answer.

**The threshold is applied to a purpose-built score, not to intent
confidence.** Version one thresholded on the intent classifier's probability.
Measurement killed that: see section 5.

**Every automated reply says it is automated.** Ravi Menon: "I calibrate how
much I trust it. If I know a person wrote it I will act without checking. If I
know a machine drafted it I will verify first. Hiding that would be the thing
that annoys me."

---

## 4. Retrieval, and what Chroma is doing here

Retrieval has three tiers. The system uses the best one available on the
machine it is running on and always reports which, via `GET /health` and in
every evaluation report.

| Tier | Method | Needs |
|---|---|---|
| 1 | Chroma + `all-MiniLM-L6-v2` embeddings, fused with TF-IDF | `chromadb`, `sentence-transformers`, one model download |
| 2 | Latent semantic indexing (truncated SVD) fused with TF-IDF | nothing beyond `requirements.txt` |
| 3 | TF-IDF alone | nothing |

`requirements.txt` deliberately does **not** install tier 1. A clean-checkout
run must not fail because a large optional dependency would not install on the
assessor's machine, and A1 matters more than a retrieval refinement. To enable
tier 1: `pip install chromadb sentence-transformers`.

Lexical and dense rankings are combined by reciprocal rank fusion, which needs
no score normalisation between two scales that are not comparable.

**The honest result:** all three tiers score identically on this corpus —
89.08% hit rate at 3, 85.15% at 1, MRR 0.8711. Twenty-nine articles is too
small a corpus for semantic matching to show a benefit, and the tier 2 index is
derived from the TF-IDF matrix so it cannot add information TF-IDF did not
have. Only tier 1 would genuinely test Ines's hypothesis, and it could not be
benchmarked in the environment this was developed in. Run
`python -m evaluation.compare_retrieval` with tier 1 installed to settle it.

---

## 5. The routing threshold, and why it changed

Requirements v1 routed on the intent classifier's confidence. Two measurements
on development data made that untenable:

- The classifier is **99.8% accurate out-of-fold but badly under-confident**.
  Observed accuracy was at or near 100% in every confidence band from 0.1
  upward, while stated confidence ranged from 0.14 to 0.82 — an expected
  calibration error of **39.79 points** against the Evaluation Framework's
  5-point requirement. A threshold on that number does not mean what it appears
  to mean.
- Sweeping it across its usable range moved automation precision by **under two
  points**. Whether a ticket is answerable from documentation turns out to be
  largely independent of how sure the classifier is about its topic.

`src/automation_readiness.py` replaces it with a calibrated model of the
question the router actually needs answered: the probability that this ticket
can be resolved without a person. Its expected calibration error is **4.24
points**, inside the requirement.

The threshold, **T = 0.45**, is chosen by minimising modelled cost using
figures from the discovery interviews — Marcus Adeyemi's "an escalation costs
us roughly four times what a resolved one costs" — subject to never automating
a ticket the corpus flags as must-not-automate. The one cost the client did not
quantify is treated as a parameter with a published sensitivity analysis. See
`evaluation/results/calibration.md`.

---

## 6. Results

From the run recorded in `evaluation/results/`, over 80 validation tickets.
**Eight of ten targets met, two missed.** The missed ones are reported here
rather than left to be noticed.

| Measure | Baseline | Target | Achieved | |
|---|---|---|---|---|
| First contact resolution | 42% | ≥ 60% | **75.0%** | PASS |
| Escalation rate | 58% | ≤ 30% | **25.0%** | PASS |
| Classification macro precision | — | ≥ 85% | **100%** | PASS |
| Hallucination rate (proxy) | — | ≤ 5% | **0%** | PASS |
| Latency p95 | — | < 3s | **5.42 ms** | PASS |
| Private data in responses | — | 0 | **0** | PASS |
| Decision log reconciliation | — | exact | **80 / 80** | PASS |
| Citation accuracy | — | ≥ 95% | **96.67%** | PASS |
| Cross-group variation | — | < 5 pts | **20.0 pts** | **FAIL** |
| Mean reply, whole queue | 8–12 hrs | < 5 min | **54.5 min** | **FAIL** |

On the two misses:

**Cross-group variation, 20.0 points.** Standard-tier customers are resolved
at 66.67% against 86.67% for business tier. This is the most serious finding in
the run. It is not a deliberate tier rule — the router does not read customer
tier except for enterprise urgency — so it is an emergent effect of what
standard-tier customers write about. Ravi Menon specifically warned that
widening the gap between plans "will come up at renewal", and on this evidence
the system widens it. The fairness audit in the governance framework sets out
what would have to change.

**Mean reply time, 54.5 minutes.** Automated replies land in 5 milliseconds.
The blended figure assumes escalated tickets still wait the historic median of
218 minutes for an agent. Automation alone does not move the mean below five
minutes unless agent response time moves with it, and saying so is more useful
to CloudServe than reporting only the flattering half.

Guardrails fired zero times on the validation corpus, which contains no
adversarial tickets. Because zero activations is not evidence either way, the
harness pushes ten engineered probes through the same pipeline instance after
each run; **10 of 10 behaved as required**.

---

## 7. Repository layout

```
├── src/
│   ├── ingestion.py             normalise four channels into one shape      A2
│   ├── classifier.py            intent and urgency with confidence          A3
│   ├── automation_readiness.py  calibrated "can this be automated?" score   A3/A5
│   ├── retrieval.py             three-tier hybrid retrieval                 A4
│   ├── router.py                policy rules, grounding, threshold          A5
│   ├── generator.py             grounded generation with citations          A6
│   ├── guardrails.py            input and output validation that blocks     A7
│   ├── db.py                    SQLite decision log and reconciliation      A8
│   ├── pipeline.py              sequences all of the above                  A9
│   └── api.py                   FastAPI service
├── evaluation/
│   ├── harness.py               unattended run, --input / --output          A9
│   ├── metrics.py               metrics and computed pass/fail              A10
│   ├── guardrail_probes.py      adversarial probes run after each run       A7
│   ├── discovery_analysis.py    the evidence behind the problem statement
│   ├── calibrate.py             calibration and threshold selection
│   ├── compare_retrieval.py     lexical against hybrid
│   └── results/                 generated artefacts
├── tests/test_acceptance_criteria.py   65 tests, grouped by criterion
├── prompts/                     versioned prompt library
├── docs/architecture.md         design decisions and alternatives
├── 02_Stage_Workbooks/Completed_Markdown/   stages one to five
├── 04_Submission/               report, effort log, governance framework
└── 05_Datasets/                 supplied corpus
```

---

## 8. Attribution and AI tool use

Third-party libraries are listed in `requirements.txt` and used under their own
licences. `scikit-learn` provides TF-IDF, logistic regression, isotonic
calibration and truncated SVD; `pydantic` and `FastAPI` provide the models and
the service; `chromadb` and `sentence-transformers` are optional.

Reciprocal rank fusion follows Cormack, Clarke and Büttcher (2009); the
constant k=60 is theirs and is not tuned here.

Anthropic Claude was used as a pair-programming assistant. Section 10 of
`04_Submission/MadhavMehta_Capstone_Report.md` states exactly where, and where
its output was overridden.

---

## 9. Known limitations

- Citation accuracy and hallucination rate are automated proxies. They check
  that a citation resolves to a retrieved passage, not that the passage
  supports the sentence it is attached to.
- Customer satisfaction is not reported. There were no customers, and a number
  produced by formula would be worse than its absence.
- The corpus is synthetic and unusually separable. 100% classification
  precision is a property of this data, not a claim about production traffic.
- The hidden evaluation set was run once. The date is recorded in the report.
- Tier 1 retrieval has not been benchmarked; see section 4.
