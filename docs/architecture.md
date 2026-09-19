# Architecture and Design Decisions

This document records what the system is, the alternatives that were considered
at each decision point, and why the choice went the way it did. Where a decision
was later reversed by measurement, the reversal is recorded here rather than
tidied away.

---

## 1. The shape of the system

Six components in sequence, with three concerns cutting across all of them.

```
                ticket (email · chat · forum · docs comment)
                                  │
     ┌────────────────────────────▼────────────────────────────┐
     │  1. INGEST            src/ingestion.py                   │
     │     four channel shapes → one NormalizedTicket           │
     └────────────────────────────┬────────────────────────────┘
                                  │
     ┌────────────────────────────▼────────────────────────────┐
     │     INPUT VALIDATION  src/guardrails.py                  │──► blocked
     │     instruction-integrity check before anything else     │    to a human
     └────────────────────────────┬────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
  ┌───────────┐          ┌───────────────┐        ┌──────────────────┐
  │2. CLASSIFY│          │ 3. RETRIEVE   │        │ AUTOMATION       │
  │  intent   │          │ hybrid, three │        │ READINESS        │
  │  urgency  │          │ tiers, cited  │        │ calibrated score │
  └─────┬─────┘          └───────┬───────┘        └────────┬─────────┘
        └─────────────────────────┼─────────────────────────┘
                                  ▼
     ┌─────────────────────────────────────────────────────────┐
     │  4. ROUTE             src/router.py                      │
     │     policy → grounding → threshold, in that order        │
     └───────────────┬──────────────────────┬──────────────────┘
        auto_respond │                      │ escalate
                     ▼                      ▼
        ┌─────────────────────┐   ┌──────────────────────────┐
        │  5. GENERATE        │   │  handover brief:         │
        │  grounded + cited   │   │  likely intent, the      │
        │  src/generator.py   │   │  alternatives, sources   │
        └──────────┬──────────┘   │  with scores, and what   │
                   ▼              │  we were unsure about    │
        ┌─────────────────────┐   └────────────┬─────────────┘
        │  6. VALIDATE        │                │
        │  can block          ├── blocked ─────┤
        │  src/guardrails.py  │                │
        └──────────┬──────────┘                │
                   │ passed                    │
                   ▼                           ▼
     ┌─────────────────────────────────────────────────────────┐
     │  DECISION LOG — one record per ticket, every path        │
     │  src/db.py                                               │
     └─────────────────────────────────────────────────────────┘

Cross-cutting: decision logging on every path · guardrails on input and
output · graceful degradation at every external boundary.
```

### Layers

Separating these is what makes the system testable and what lets the model
provider or the vector store be swapped without rewriting what depends on them.

| Layer | Contents |
|---|---|
| Interface | `src/api.py`, `evaluation/harness.py`, `demo.py` |
| Domain | `ingestion`, `classifier`, `automation_readiness`, `retrieval`, `router`, `generator`, `guardrails`, orchestrated by `pipeline` |
| Persistence | `src/db.py` (SQLite decision log), generated metrics in `evaluation/results/` |

The decision log sits in the persistence layer beside the metrics rather than
being bolted on at the end, because every decision has to be reconstructable
months later and that requirement shapes the schema from day one. Marcus
Adeyemi has a compliance review in the autumn and said he needs to be able to
say why the system did what it did.

---

## 2. Decision: what the threshold is applied to

**Reversed during the build. This is the substantive PRD revision.**

### What v1 did

Route on the intent classifier's probability: auto-respond above 0.80,
escalate below.

### Why it was wrong

Two measurements on development data, both reproducible with
`python -m evaluation.calibrate`.

*The number was not calibrated.* Out-of-fold intent accuracy is 99.8%, but
observed accuracy sits at or near 100% in every confidence band from 0.1
upward while stated confidence ranges from 0.14 to 0.82. Expected calibration
error: **39.79 points**, against the Evaluation Framework's requirement of
five. With 22 near-uniform classes, logistic regression spreads probability
mass thinly and reports 0.08 for a prediction that is almost always right. A
threshold on that number does not mean what it appears to mean.

*The number was close to irrelevant to the decision.* Sweeping it from 0.05 to
0.80 moved automation precision by under two points. Whether a ticket can be
answered from documentation turns out to be largely independent of how certain
the classifier is about its topic — the discovery analysis shows
`answerable_from_docs` varying from 0% to 96% *across* intents, so the property
that matters is not captured by confidence in the intent at all.

### What replaced it

`src/automation_readiness.py`: a separate binary model trained on
`expected_route`, wrapped in isotonic calibration, answering the question the
router actually needs answered. Expected calibration error **4.24 points**,
inside the requirement.

Intent still drives policy — the never-automate rules — but no longer drives
the threshold.

### Alternatives considered

| Option | Why not |
|---|---|
| Recalibrate the intent classifier | Fixes the calibration problem but not the relevance problem. A well-calibrated estimate of the wrong quantity is still the wrong quantity. |
| Threshold on retrieval score | Tested. The top TF-IDF score separates answerable from non-answerable tickets poorly (means 0.255 against 0.222). It is a weak signal on its own. |
| Use the `answerable_from_docs` label directly | It is a label, not an observable. It does not exist at inference time on a ticket nobody has assessed. |
| Composite of intent and retrieval scores | Was described in the earlier report but never implemented, and the weights would have been chosen by hand. The calibrated model is one number with a measured meaning instead of two with invented weights. |

---

## 3. Decision: where the threshold sits

**T = 0.45**, chosen by minimising modelled cost rather than by tuning until a
headline number looked acceptable.

The costs come from the discovery interviews. Marcus Adeyemi: an escalation
"costs us roughly four times what a resolved one costs". So a correct
automation is 1 and an escalation is 4. The third cost — a wrong automated
answer — he characterises but does not quantify: "I would rather it said
nothing than said something wrong." It is therefore treated as a parameter,
set at 12, and published with a sensitivity analysis.

The hard constraint is that no threshold may automate a ticket the corpus flags
`must_not_auto_respond`. That constraint is satisfied at every threshold in the
sweep, because it is the never-automate policy rule rather than the threshold
that prevents them.

**What the sensitivity analysis shows, and why it matters:** the choice is
stable between assumed costs of 8 and 12, but at 20 the optimum jumps to 0.90
and automation collapses to 3.6%. The threshold is not robust to that
assumption, and CloudServe should be asked to put a figure on the cost of a
wrong answer rather than having one chosen for them.

---

## 4. Decision: retrieval

Three tiers, best available used, always reported.

| Tier | Method | Requires |
|---|---|---|
| 1 | Chroma + `all-MiniLM-L6-v2`, fused with TF-IDF | `chromadb`, `sentence-transformers`, a model download |
| 2 | Latent semantic indexing (truncated SVD) fused with TF-IDF | nothing extra |
| 3 | TF-IDF alone | nothing extra |

### Why hybrid rather than embeddings alone

Ines Varga's account is the argument for semantic retrieval: customers write
"my deployment keeps dying" and her article is called "resolving container
health check failures", and no keyword search connects them. But customers also
quote document ids, HTTP status codes and CLI flags, which dense vectors handle
poorly. Both signals are needed, so both rankings are computed and fused with
reciprocal rank fusion — which needs no normalisation between two scales that
are not comparable.

### Why tier 1 is not in `requirements.txt`

A1 is a pass-or-fail gate and it matters more than a retrieval refinement. A
clean-checkout run that dies because a large optional dependency would not
install would fail the gate for a reason unrelated to the system. Tier 1 is one
`pip install` away for anyone who wants it.

### The relevance gate, and a bug worth recording

Retrieval must return nothing rather than something irrelevant. An early
version of the fusion normalised fused scores to 0–1, which handed the best
candidate a perfect score *even when the query matched nothing at all* — a
query of pure gibberish came back with a confident top result. The `demo.py`
run caught it.

The gate now runs on raw similarity **before** fusion: a candidate must clear
the threshold on its own evidence, and fusion only orders what is already
admitted. Latent-semantic scores are deliberately excluded from admission,
because cosine similarity in a 128-dimensional projection is not on the same
scale as TF-IDF cosine and runs high even for meaningless input. LSA is a
projection of the TF-IDF matrix in any case, so it has no independent evidence
to offer about relevance — only about ordering.

### What measurement actually showed

All three tiers score identically on this corpus: 89.08% hit rate at 3, 85.15%
at 1, MRR 0.8711. Twenty-nine articles is too small for semantic matching to
show a benefit, and tier 2 cannot add information TF-IDF did not have. Only
tier 1 would genuinely test Ines's hypothesis, and it could not be benchmarked
in the development environment. This is recorded as outstanding work, not as a
result.

### Chunking

Split on Markdown H2 headings, plus one whole-article chunk for topical
matching. Support articles are written as Symptoms / Common causes /
Resolution, so a heading boundary is a real semantic boundary and a resolution
section retrieved alone is still intelligible. Every chunk carries its
`doc_id`, so a citation always resolves to a real article — which is what lets
Ines tell whether a wrong answer came from a wrong article or a misread one.

---

## 5. Decision: guardrails block rather than redact

The Governance Framework is explicit that private data should be blocked and
escalated, never redacted and sent. The earlier implementation redacted API
keys and sent the response anyway.

Redaction hides the fault while leaving it in place. A response containing
another customer's identifier means something upstream went wrong; masking the
identifier and sending the reply removes the evidence and keeps the defect.

Guardrails run on every response in the evaluation harness exactly as in the
API. There is no flag that disables them, because the Build Specification is
explicit that a guardrail present but switched off does not satisfy A7.

Checks are not short-circuited on the first failure. The decision log is more
useful when it records everything wrong with a response than only the first
thing noticed.

### Proving they are live

The validation corpus contains no adversarial tickets, so a run over it
produces zero guardrail activations — which proves nothing either way. After
each run the harness pushes ten engineered probes through the *same pipeline
instance*, so a guardrail disabled for the run would be caught. Probe decisions
go to a separate audit log, because six synthetic records in the run's own log
would be indistinguishable from the duplicate-logging fault that A8
reconciliation exists to catch.

---

## 6. Decision: the classifier's runner-up can veto automation

Found in testing. "Could you add the ability to schedule recurring bulk
exports?" classified as `billing_query` at 0.080, with `feature_request` second
at 0.067 — a gap of thirteen thousandths across 22 near-uniform classes. On the
top prediction alone it would have been auto-answered, and a feature request
has no documented answer to give: the corpus marks every one of them
`answerable_from_docs: false`.

Keying a safety rule to the single highest-scoring class assumes a separation
the classifier does not provide. So when a never-automate intent scores within
20% of the top prediction, the ticket escalates and the recorded reason says
the system could not tell the two apart.

---

## 7. Decision: the decision log schema

One record per ticket on every path, including blocked ones and internal
failures. This is what makes reconciliation a real check: `reconcile()` verifies
that total decisions, distinct tickets and the ticket count all agree, so a
duplicate is caught as well as a gap. Counting only distinct tickets would hide
a double-logged ticket.

Beyond the Governance Framework's minimum record, each row also carries the
channel, customer tier and language fluency. Those three make the fairness
audit a query against the log rather than a separate exercise, which is what
keeps it from being something nobody runs again.

`prompt_version` and `requirement_ids` are recorded because the question after
an incident is always "was this behaviour intended?", and only those two fields
can answer it.

---

## 8. Decision: honesty mechanisms in the reporting

The evaluation reporter computes every pass or fail from the measured value
against its target, through a single `_status()` function. No verdict is
written by hand anywhere.

This is a deliberate correction. The previous implementation had `PASS` typed
literally into every row of the markdown table regardless of the value, which
reported a 17.86-point fairness variation against a five-point requirement as a
pass. `test_status_flags_are_computed_not_hardcoded` feeds the reporter a
deliberately terrible result and fails if anything comes back PASS.

Similarly, `demo.py` states what each scenario expects, compares that against
the live result, and reports honestly when the system does not comply, rather
than printing a success line unconditionally.

Customer satisfaction is not reported at all. There were no customers, and the
earlier implementation's `4.4 if fcr >= 50 else 3.8` was a number invented by
formula and presented as a measurement.

---

## 9. Known weaknesses

| Weakness | Consequence | What would fix it |
|---|---|---|
| Cross-group variation of 20 points by customer tier | Standard-tier customers resolved at 66.67% against 86.67% for business tier, against a five-point requirement | Segment-aware threshold calibration; see the fairness audit |
| Citation accuracy is an automated proxy | Confirms a citation resolves to a retrieved passage, not that the passage supports the sentence | Human review at scale; a sample was done, the full set was not |
| Tier 1 retrieval unbenchmarked | The case for semantic retrieval rests on an interview, not a measurement | Run `compare_retrieval` where the model host is reachable |
| Threshold sensitive to an unquantified cost | At an assumed cost of 20 the optimum jumps to 0.90 | Ask CloudServe to put a figure on a wrong answer |
| Corpus is synthetic and separable | 100% classification precision will not survive contact with real traffic | Re-measure on real tickets before deployment |
