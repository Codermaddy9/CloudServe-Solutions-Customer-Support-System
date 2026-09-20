# Confidence Calibration and Routing Threshold Selection

Measured on 500 development tickets with 5-fold out-of-fold scoring, so that no ticket is scored by a model that trained on it. The validation set is not used in this file.

## 1. Why the routing signal changed

Version one of the requirements thresholded on the intent classifier's own probability. Two measurements made that untenable.

### 1.1 The intent classifier is accurate but badly under-confident

Out-of-fold intent accuracy is **99.8%**, but its expected calibration error is **39.79 points** against the Evaluation Framework's 5-point requirement.

| Confidence band | n | Mean stated | Observed accuracy | Gap (pts) |
|---|---|---|---|---|
| 0.0-0.1 | 1 | 0.064 | 0.000 | +6.41 |
| 0.1-0.2 | 6 | 0.140 | 1.000 | -86.05 |
| 0.2-0.3 | 18 | 0.244 | 1.000 | -75.58 |
| 0.3-0.4 | 31 | 0.358 | 1.000 | -64.17 |
| 0.4-0.5 | 77 | 0.464 | 1.000 | -53.65 |
| 0.5-0.6 | 89 | 0.555 | 1.000 | -44.51 |
| 0.6-0.7 | 124 | 0.656 | 1.000 | -34.41 |
| 0.7-0.8 | 125 | 0.748 | 1.000 | -25.16 |
| 0.8-0.9 | 29 | 0.822 | 1.000 | -17.85 |

Observed accuracy sits at or near 1.000 in every populated band while stated confidence ranges from roughly 0.14 to 0.82. The classifier is right almost always and says so almost never. A threshold on that number does not mean what it appears to mean.

### 1.2 Intent confidence barely predicts whether a ticket should be automated

Sweeping the intent-confidence threshold across its usable range moves automation precision by under two points, because whether a ticket is answerable from documentation is largely independent of how certain the classifier is about its topic. The full sweep is in `calibration.json` under `legacy_intent_confidence_sweep`.

## 2. The replacement signal, and its calibration

`src/automation_readiness.py` scores the question the router actually needs answered: the probability that this ticket can be resolved without a human. It is trained on the `expected_route` label and wrapped in isotonic calibration.

Expected calibration error: **4.24 points**.

| Readiness band | n | Mean stated | Observed auto-respond rate | Gap (pts) |
|---|---|---|---|---|
| 0.0-0.1 | 69 | 0.021 | 0.058 | -3.74 |
| 0.1-0.2 | 17 | 0.144 | 0.176 | -3.21 |
| 0.2-0.3 | 11 | 0.250 | 0.091 | +15.91 |
| 0.3-0.4 | 14 | 0.352 | 0.429 | -7.65 |
| 0.4-0.5 | 11 | 0.444 | 0.545 | -10.13 |
| 0.5-0.6 | 19 | 0.564 | 0.737 | -17.28 |
| 0.6-0.7 | 55 | 0.657 | 0.727 | -7.04 |
| 0.7-0.8 | 184 | 0.765 | 0.761 | +0.38 |
| 0.8-0.9 | 102 | 0.846 | 0.794 | +5.17 |
| 0.9-1.0 | 18 | 0.944 | 0.889 | +5.55 |

## 3. The cost model behind the threshold

The threshold is a business trade-off, not a tuning parameter, so it is chosen against costs taken from the discovery transcripts rather than to make a headline figure look better.

| Outcome | Cost | Source |
|---|---|---|
| Ticket resolved automatically and correctly | 1.0 | baseline unit |
| Ticket escalated to a human | 4.0 | Marcus Adeyemi: an escalation "costs us roughly four times what a resolved one costs" |
| Ticket automated when it should not have been | 12.0 | not quantified by the client; treated as a parameter and tested below |

## 4. Threshold sweep

| Threshold | Automated | Escalated | Precision | Recall | Wrong | Unsafe | Cost / 100 |
|---|---|---|---|---|---|---|---|
| 0.05 | 82.4% | 17.6% | 75.24% | 99.68% | 102 | 0 | 377.2 |
| 0.10 | 81.6% | 18.4% | 75.25% | 98.71% | 101 | 0 | 377.4 |
| 0.15 | 80.8% | 19.2% | 75.25% | 97.75% | 100 | 0 | 377.6 |
| 0.20 | 80.4% | 19.6% | 75.62% | 97.75% | 98 | 0 | 374.4 |
| 0.25 | 80.0% | 20.0% | 76.0% | 97.75% | 96 | 0 | 371.2 |
| 0.30 | 79.4% | 20.6% | 76.32% | 97.43% | 94 | 0 | 368.6 |
| 0.35 | 78.6% | 21.4% | 76.84% | 97.11% | 91 | 0 | 364.4 |
| 0.40 | 77.2% | 22.8% | 76.94% | 95.5% | 89 | 0 | 364.2 |
| 0.45 **←** | 75.8% | 24.2% | 77.57% | 94.53% | 85 | 0 | 359.6 |
| 0.50 | 75.2% | 24.8% | 77.39% | 93.57% | 85 | 0 | 361.4 |
| 0.55 | 73.6% | 26.4% | 77.45% | 91.64% | 83 | 0 | 361.8 |
| 0.60 | 71.4% | 28.6% | 77.59% | 89.07% | 80 | 0 | 361.8 |
| 0.65 | 67.6% | 32.4% | 77.81% | 84.57% | 75 | 0 | 362.2 |
| 0.70 | 60.8% | 39.2% | 77.96% | 76.21% | 67 | 0 | 365.0 |
| 0.75 | 51.4% | 48.6% | 79.77% | 65.92% | 52 | 0 | 360.2 |
| 0.80 | 24.0% | 76.0% | 80.83% | 31.19% | 23 | 0 | 378.6 |
| 0.85 | 13.4% | 86.6% | 82.09% | 17.68% | 12 | 0 | 386.2 |
| 0.90 | 3.6% | 96.4% | 88.89% | 5.14% | 2 | 0 | 393.6 |
| 0.95 | 1.4% | 98.6% | 85.71% | 1.93% | 1 | 0 | 398.0 |

## 5. Selected threshold

**T = 0.45**, the cost-minimising point at which no ticket flagged `must_not_auto_respond` is automated.

At this threshold the development data projects automation of 75.8% of tickets, an escalation rate of 24.2%, automation precision of 77.57% and recall of 94.53%.

## 6. Sensitivity to the one figure we had to assume

The client quantified the cost of an escalation but not the cost of a wrong automated answer. The table below shows how the chosen threshold responds to that assumption across a wide range.

| Assumed cost of a wrong automation | Chosen T | Automated | Escalated | Precision |
|---|---|---|---|---|
| 4.0 | 0.05 | 82.4% | 17.6% | 75.24% |
| 8.0 | 0.45 | 75.8% | 24.2% | 77.57% |
| 12.0 | 0.45 | 75.8% | 24.2% | 77.57% |
| 20.0 | 0.9 | 3.6% | 96.4% | 88.89% |
| 40.0 | 0.95 | 1.4% | 98.6% | 85.71% |

## 7. What this analysis does not establish

Automation precision is measured against the corpus `expected_route` label, which encodes what a senior agent judged the right routing to be. It is a proxy for answer quality, not a measurement of it: a ticket automated against an `escalate` label has not necessarily received a wrong answer, only one the corpus would have preferred a human to give. The figure that does bear directly on harm is the count of automated tickets flagged `must_not_auto_respond`, which is zero at every threshold in the sweep because the never-automate policy rule, rather than the threshold, is what prevents them.
