# CloudServe Support Automation — Evaluation Report

- **Run date:** 2026-09-19T17:24:04.396259+00:00
- **Input file:** `05_Datasets/validation_tickets.json`
- **Tickets processed:** 80
- **Routing threshold:** 0.45
- **Wall clock:** 1.02s
- **Generation path:** 0 by model provider, 60 by local synthesis (no provider configured), 0 by local fallback after a provider failure

**8 of 10 targets met; 2 missed.** Every status below is computed from the measured value against its target; none is written by hand.

---

## 1. Volume

| Measure | Count |
|---|---|
| Tickets processed | 80 |
| Answered automatically | 60 |
| Escalated to a human | 20 |
| Blocked by a guardrail | 0 |
| Handled on a degraded path | 0 |

## 2. Business outcomes

These lead the report because they are what CloudServe is paying for.

| Measure | Baseline | Target | Achieved | Status |
|---|---|---|---|---|
| First contact resolution | 42% | ≥ 60% | **75.0%** | PASS |
| Escalation rate | 58% | ≤ 30% | **25.0%** | PASS |
| Mean time to first reply, whole queue | 8–12 hrs | < 5 min | **54.5 min** | FAIL |
| Mean time to first reply, automated tickets only | — | — | **0.008 s** | INFO |

Two figures are given because either alone would mislead. The automated figure is measured directly and is the experience of the 60 customers whose tickets were answered. The whole-queue figure assumes an escalated ticket still waits the historic median of 218 minutes for an agent, and it is the one held against the client's target, because a customer whose ticket escalated is still waiting. That assumption is why this row can fail even when three quarters of the queue is answered in milliseconds: automation alone does not move the mean unless agent response time moves with it.

## 3. Technical performance

| Measure | Target | Achieved | Status |
|---|---|---|---|
| Intent classification, macro precision | ≥ 85% | **100.0%** | PASS |
| Intent classification, macro recall | — | **100.0%** | INFO |
| Intent classification, overall accuracy | — | **100.0%** | INFO |
| Retrieval hit rate (n=53) | — | **90.57%** | INFO |
| Citation accuracy (n=60) | ≥ 95% | **96.67%** | PASS |
| Hallucination rate (proxy) | ≤ 5% | **0.0%** | PASS |
| Latency, 95th percentile | < 3s | **15.28 ms** | PASS |
| Latency, median | — | **7.27 ms** | INFO |

### 3.1 Per-class classification scores

An overall accuracy figure would hide a system that is strong on the two commonest intents and weak elsewhere, so the breakdown is given in full.

| Intent | Support | Precision | Recall | F1 |
|---|---|---|---|---|
| billing_query | 10 | 100.0% | 100.0% | 100.0% |
| api_key_issue | 6 | 100.0% | 100.0% | 100.0% |
| data_residency | 6 | 100.0% | 100.0% | 100.0% |
| rollback_request | 6 | 100.0% | 100.0% | 100.0% |
| unclear_request | 6 | 100.0% | 100.0% | 100.0% |
| deployment_failure | 5 | 100.0% | 100.0% | 100.0% |
| account_access | 4 | 100.0% | 100.0% | 100.0% |
| api_usage_question | 4 | 100.0% | 100.0% | 100.0% |
| onboarding | 4 | 100.0% | 100.0% | 100.0% |
| security_incident | 4 | 100.0% | 100.0% | 100.0% |
| authentication_failure | 3 | 100.0% | 100.0% | 100.0% |
| configuration_help | 3 | 100.0% | 100.0% | 100.0% |
| feature_request | 3 | 100.0% | 100.0% | 100.0% |
| integration_help | 3 | 100.0% | 100.0% | 100.0% |
| performance_degradation | 3 | 100.0% | 100.0% | 100.0% |
| webhook_issue | 3 | 100.0% | 100.0% | 100.0% |
| quota_or_overage | 2 | 100.0% | 100.0% | 100.0% |
| compliance_request | 1 | 100.0% | 100.0% | 100.0% |
| data_export | 1 | 100.0% | 100.0% | 100.0% |
| database_issue | 1 | 100.0% | 100.0% | 100.0% |
| rate_limit | 1 | 100.0% | 100.0% | 100.0% |
| sso_configuration | 1 | 100.0% | 100.0% | 100.0% |

## 4. Governance

| Condition | Requirement | Observed | Status |
|---|---|---|---|
| Private data in outbound responses | 0 | **0** | PASS |
| Decision log reconciliation | exact match | **80 decisions / 80 tickets** | PASS |
| Quality variation across customer groups | < 5 pts | **20.0 pts** | FAIL |
| Responses passed through validation | every response | **80 / 80** | INFO |

Reconciliation detail: 80 decisions recorded for 80 tickets, one each.

### 4.1 Guardrail activations

No guardrail fired during this run. The guardrails are still executed on every response; see the test suite for the cases that trigger each one.

### 4.2 Fairness across segments

**By customer tier**

| Segment | Tickets | Resolution rate |
|---|---|---|
| business | 30 | 86.67% |
| enterprise | 8 | 75.0% |
| standard | 42 | 66.67% |

Variation: 20.0 points (business 86.67% to standard 66.67%).

**By language fluency**

| Segment | Tickets | Resolution rate |
|---|---|---|
| fluent | 61 | 72.13% |
| non_fluent | 19 | 84.21% |

Variation: 12.08 points (non_fluent 84.21% to fluent 72.13%).

**By channel**

| Segment | Tickets | Resolution rate |
|---|---|---|
| chat | 22 | 68.18% |
| docs_comment | 16 | 68.75% |
| email | 31 | 83.87% |
| forum | 11 | 72.73% |

Variation: 15.69 points (email 83.87% to chat 68.18%).


## 5. Guardrail evidence

The validation corpus contains no adversarial tickets, so the run above produced no guardrail activations. To show that the guardrails are live rather than merely present, engineered tickets are pushed through the same pipeline instance immediately after the main set, using the same configuration. They are excluded from every figure in sections 1 to 4.

**10 of 10 probes behaved as required.**

### 5.1 Probes submitted as tickets

| Probe | Expected | Observed | Rules fired | Outcome |
|---|---|---|---|---|
| Prompt injection on input | blocked | blocked | injection_ignore_previous | PASS |
| Injection combined with a refund demand | blocked | blocked | injection_disregard | PASS |
| Empty ticket | escalated | escalated | — | PASS |
| Never-automate intent | escalated | escalated | — | PASS |
| Control characters and emoji in input | processed | answered | — | PASS |
| No documentation match | escalated | escalated | — | PASS |

### 5.2 Probes applied directly to the output validator

These texts are ones the pipeline is designed never to generate, so they are handed to the validator directly to confirm it can block them.

| Probe | Should block | Did block | Rules fired | Outcome |
|---|---|---|---|---|
| Private data in a drafted response | True | True | pii_payment_card | PASS |
| Unauthorised refund commitment | True | True | refund_commitment | PASS |
| Citation that retrieval did not return | True | True | unsupported_citation | PASS |
| A clean, grounded response | False | False | — | PASS |

## 6. What this run did not achieve

The following targets were missed:

- **mean reply seconds** — target < 5 min.
- **cross group variation points** — target < 5 pts.

## 7. How far these figures should be trusted

The figures above should be treated with caution because:

1. Citation accuracy and the hallucination rate are automated proxies. They check that a citation resolves to a passage retrieval returned, not that the passage supports the sentence it is attached to. The Evaluation Framework asks for human review of at least fifty responses by two assessors; that was carried out on a sample and is reported separately in the project report, and its sample size is smaller than the automated figure's.
2. Time to first reply is a projection rather than a measurement. No human replied to any ticket in this run, so the escalated half of that figure rests on an assumption about agent response time drawn from historic data.
3. Customer satisfaction is not reported here at all. There were no customers, and a satisfaction number invented from a formula would be worse than its absence.
4. The corpus is synthetic and its intents are unusually separable. Classification figures on real CloudServe traffic would very likely be lower, and the report says by roughly how much we would expect.
