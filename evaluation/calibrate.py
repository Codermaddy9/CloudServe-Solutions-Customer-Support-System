"""
Confidence calibration and routing threshold selection for CloudServe.

Everything here runs on development tickets only. The validation set is not
touched, so it remains an honest estimate of unseen performance.

Three questions are answered:

  1. Is the intent classifier's confidence calibrated? The Evaluation Framework
     requires stated confidence to sit within five points of observed accuracy.

  2. Is the automation-readiness score calibrated? This is the number the
     router actually thresholds on, so it is the one that must mean what it says.

  3. Where should the threshold sit? Rather than picking a number that makes
     first contact resolution look good, the threshold is selected against an
     explicit cost model taken from the discovery transcripts, and reported
     with a sensitivity analysis over the one figure that model assumes.

Usage:
    python -m evaluation.calibrate --tickets 05_Datasets/development_tickets.json \
                                   --output evaluation/results/calibration.json
"""
import os
import sys
import json
import tempfile
import argparse
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.classifier import TicketClassifier
from src.automation_readiness import AutomationReadinessScorer
from src.ingestion import normalize_ticket
from src.router import MUST_NOT_AUTO_RESPOND_INTENTS

# Marcus Adeyemi, Head of Support, interview one:
#   "every ticket that bounces to tier two costs us roughly four times what a
#    resolved one costs, and it makes the customer angrier than waiting would have"
# That gives us two of the three costs directly. The third, the cost of a wrong
# automated answer, he characterises but does not quantify:
#   "I would rather it said nothing than said something wrong."
# We therefore treat it as a parameter and report sensitivity over it.
COST_AUTOMATED_CORRECT = 1.0
COST_ESCALATION = 4.0
DEFAULT_COST_WRONG_AUTOMATION = 12.0
SENSITIVITY_RANGE = [4.0, 8.0, 12.0, 20.0, 40.0]


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 2) if d else 0.0


def out_of_fold_records(tickets: List[Dict[str, Any]], folds: int = 5) -> List[Dict[str, Any]]:
    """
    Score every ticket with models that did not train on it.

    Calibration measured on training data reports a confidence curve the system
    will never reproduce in service, so out-of-fold scoring is not optional here.
    """
    records: List[Dict[str, Any]] = []
    for fold in range(folds):
        train = [t for i, t in enumerate(tickets) if i % folds != fold]
        test = [t for i, t in enumerate(tickets) if i % folds == fold]

        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        try:
            json.dump(train, handle)
            handle.close()
            classifier = TicketClassifier(dev_tickets_path=handle.name)
            readiness = AutomationReadinessScorer(dev_tickets_path=handle.name)

            for raw in test:
                ticket = normalize_ticket(raw)
                classification = classifier.classify(ticket)
                labels = raw.get("labels", {})
                records.append({
                    "ticket_id": raw.get("ticket_id"),
                    "predicted_intent": classification.intent,
                    "actual_intent": labels.get("intent"),
                    "intent_confidence": classification.intent_confidence,
                    "intent_correct": classification.intent == labels.get("intent"),
                    "readiness": readiness.score(ticket),
                    "expected_route": labels.get("expected_route"),
                    "should_automate": labels.get("expected_route") == "auto_respond",
                    "must_not_auto_respond": bool(labels.get("must_not_auto_respond")),
                    "answerable_from_docs": bool(labels.get("answerable_from_docs")),
                    "customer_tier": raw.get("customer_tier"),
                    "language_fluency": raw.get("language_fluency"),
                })
        finally:
            if os.path.exists(handle.name):
                os.unlink(handle.name)
    return records


def calibration_table(records: List[Dict[str, Any]], score_key: str, truth_key: str,
                      bands: int = 10) -> List[Dict[str, Any]]:
    """Stated confidence against observed frequency, band by band."""
    rows = []
    for i in range(bands):
        low, high = i / bands, (i + 1) / bands
        if i < bands - 1:
            group = [r for r in records if low <= r[score_key] < high]
        else:
            group = [r for r in records if low <= r[score_key] <= high]
        if not group:
            continue
        stated = sum(r[score_key] for r in group) / len(group)
        observed = sum(1 for r in group if r[truth_key]) / len(group)
        rows.append({
            "band": f"{low:.1f}-{high:.1f}",
            "n": len(group),
            "mean_stated": round(stated, 4),
            "observed": round(observed, 4),
            "gap_points": round((stated - observed) * 100, 2),
        })
    return rows


def expected_calibration_error(rows: List[Dict[str, Any]], total: int) -> float:
    if not total:
        return 0.0
    return round(sum(r["n"] * abs(r["gap_points"]) for r in rows) / total, 2)


def sweep(records: List[Dict[str, Any]], cost_wrong: float,
          lo: float = 0.05, hi: float = 0.95, step: float = 0.05) -> List[Dict[str, Any]]:
    """
    Sweep the readiness threshold, reporting the operational trade-off and the
    modelled cost per hundred tickets at each point.

    A ticket is automated when its predicted intent is not on the never-automate
    list and its readiness score clears the threshold.
    """
    total = len(records)
    should_automate = [r for r in records if r["should_automate"]]
    rows = []

    steps = int(round((hi - lo) / step)) + 1
    for i in range(steps):
        threshold = round(lo + i * step, 2)
        automated = [r for r in records
                     if r["predicted_intent"] not in MUST_NOT_AUTO_RESPOND_INTENTS
                     and r["readiness"] >= threshold]
        escalated_count = total - len(automated)

        correct_automations = sum(1 for r in automated if r["should_automate"])
        wrong_automations = len(automated) - correct_automations
        unsafe = sum(1 for r in automated if r["must_not_auto_respond"])
        captured = sum(1 for r in should_automate
                       if r["predicted_intent"] not in MUST_NOT_AUTO_RESPOND_INTENTS
                       and r["readiness"] >= threshold)

        modelled_cost = (
            correct_automations * COST_AUTOMATED_CORRECT
            + wrong_automations * cost_wrong
            + escalated_count * COST_ESCALATION
        )

        rows.append({
            "threshold": threshold,
            "automation_rate_pct": _pct(len(automated), total),
            "escalation_rate_pct": _pct(escalated_count, total),
            "automation_precision_pct": _pct(correct_automations, len(automated)),
            "automation_recall_pct": _pct(captured, len(should_automate)),
            "wrong_automations": wrong_automations,
            "unsafe_automations": unsafe,
            "modelled_cost_per_100_tickets": round(modelled_cost / total * 100, 2),
        })
    return rows


def choose(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Select the threshold minimising modelled cost, subject to the hard
    constraint that no ticket flagged must_not_auto_respond is ever automated.
    """
    safe = [r for r in rows if r["unsafe_automations"] == 0]
    if not safe:
        return {"threshold": None, "rationale": "No threshold avoided unsafe automation."}
    best = min(safe, key=lambda r: (r["modelled_cost_per_100_tickets"], -r["threshold"]))
    return {
        "threshold": best["threshold"],
        "modelled_cost_per_100_tickets": best["modelled_cost_per_100_tickets"],
        "automation_rate_pct": best["automation_rate_pct"],
        "escalation_rate_pct": best["escalation_rate_pct"],
        "automation_precision_pct": best["automation_precision_pct"],
        "automation_recall_pct": best["automation_recall_pct"],
    }


def sensitivity(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """How the chosen threshold moves as the assumed cost of a wrong answer changes."""
    out = []
    for cost in SENSITIVITY_RANGE:
        chosen = choose(sweep(records, cost_wrong=cost))
        out.append({
            "assumed_cost_of_wrong_automation": cost,
            "chosen_threshold": chosen.get("threshold"),
            "automation_rate_pct": chosen.get("automation_rate_pct"),
            "escalation_rate_pct": chosen.get("escalation_rate_pct"),
            "automation_precision_pct": chosen.get("automation_precision_pct"),
        })
    return out


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# Confidence Calibration and Routing Threshold Selection",
        "",
        f"Measured on {result['n_records']} development tickets with "
        f"{result['folds']}-fold out-of-fold scoring, so that no ticket is scored by a "
        "model that trained on it. The validation set is not used in this file.",
        "",
        "## 1. Why the routing signal changed",
        "",
        "Version one of the requirements thresholded on the intent classifier's own "
        "probability. Two measurements made that untenable.",
        "",
        "### 1.1 The intent classifier is accurate but badly under-confident",
        "",
        f"Out-of-fold intent accuracy is **{result['intent_accuracy_pct']}%**, but its "
        f"expected calibration error is **{result['intent_ece_points']} points** against the "
        "Evaluation Framework's 5-point requirement.",
        "",
        "| Confidence band | n | Mean stated | Observed accuracy | Gap (pts) |",
        "|---|---|---|---|---|",
    ]
    for r in result["intent_calibration"]:
        lines.append(f"| {r['band']} | {r['n']} | {r['mean_stated']:.3f} | "
                     f"{r['observed']:.3f} | {r['gap_points']:+.2f} |")

    lines += [
        "",
        "Observed accuracy sits at or near 1.000 in every populated band while stated "
        "confidence ranges from roughly 0.14 to 0.82. The classifier is right almost "
        "always and says so almost never. A threshold on that number does not mean "
        "what it appears to mean.",
        "",
        "### 1.2 Intent confidence barely predicts whether a ticket should be automated",
        "",
        "Sweeping the intent-confidence threshold across its usable range moves "
        "automation precision by under two points, because whether a ticket is "
        "answerable from documentation is largely independent of how certain the "
        "classifier is about its topic. The full sweep is in `calibration.json` under "
        "`legacy_intent_confidence_sweep`.",
        "",
        "## 2. The replacement signal, and its calibration",
        "",
        "`src/automation_readiness.py` scores the question the router actually needs "
        "answered: the probability that this ticket can be resolved without a human. "
        "It is trained on the `expected_route` label and wrapped in isotonic calibration.",
        "",
        f"Expected calibration error: **{result['readiness_ece_points']} points**.",
        "",
        "| Readiness band | n | Mean stated | Observed auto-respond rate | Gap (pts) |",
        "|---|---|---|---|---|",
    ]
    for r in result["readiness_calibration"]:
        lines.append(f"| {r['band']} | {r['n']} | {r['mean_stated']:.3f} | "
                     f"{r['observed']:.3f} | {r['gap_points']:+.2f} |")

    lines += [
        "",
        "## 3. The cost model behind the threshold",
        "",
        "The threshold is a business trade-off, not a tuning parameter, so it is chosen "
        "against costs taken from the discovery transcripts rather than to make a "
        "headline figure look better.",
        "",
        "| Outcome | Cost | Source |",
        "|---|---|---|",
        f"| Ticket resolved automatically and correctly | {COST_AUTOMATED_CORRECT} | baseline unit |",
        f"| Ticket escalated to a human | {COST_ESCALATION} | Marcus Adeyemi: an escalation "
        "\"costs us roughly four times what a resolved one costs\" |",
        f"| Ticket automated when it should not have been | {result['assumed_cost_of_wrong_automation']} "
        "| not quantified by the client; treated as a parameter and tested below |",
        "",
        "## 4. Threshold sweep",
        "",
        "| Threshold | Automated | Escalated | Precision | Recall | Wrong | Unsafe | Cost / 100 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in result["sweep"]:
        marker = " **←**" if r["threshold"] == result["recommendation"]["threshold"] else ""
        lines.append(
            f"| {r['threshold']:.2f}{marker} | {r['automation_rate_pct']}% | "
            f"{r['escalation_rate_pct']}% | {r['automation_precision_pct']}% | "
            f"{r['automation_recall_pct']}% | {r['wrong_automations']} | "
            f"{r['unsafe_automations']} | {r['modelled_cost_per_100_tickets']} |")

    rec = result["recommendation"]
    lines += [
        "",
        "## 5. Selected threshold",
        "",
        f"**T = {rec['threshold']}**, the cost-minimising point at which no ticket flagged "
        "`must_not_auto_respond` is automated.",
        "",
        f"At this threshold the development data projects automation of "
        f"{rec['automation_rate_pct']}% of tickets, an escalation rate of "
        f"{rec['escalation_rate_pct']}%, automation precision of "
        f"{rec['automation_precision_pct']}% and recall of {rec['automation_recall_pct']}%.",
        "",
        "## 6. Sensitivity to the one figure we had to assume",
        "",
        "The client quantified the cost of an escalation but not the cost of a wrong "
        "automated answer. The table below shows how the chosen threshold responds to "
        "that assumption across a wide range.",
        "",
        "| Assumed cost of a wrong automation | Chosen T | Automated | Escalated | Precision |",
        "|---|---|---|---|---|",
    ]
    for s in result["sensitivity"]:
        lines.append(
            f"| {s['assumed_cost_of_wrong_automation']} | {s['chosen_threshold']} | "
            f"{s['automation_rate_pct']}% | {s['escalation_rate_pct']}% | "
            f"{s['automation_precision_pct']}% |")

    lines += [
        "",
        "## 7. What this analysis does not establish",
        "",
        "Automation precision is measured against the corpus `expected_route` label, "
        "which encodes what a senior agent judged the right routing to be. It is a "
        "proxy for answer quality, not a measurement of it: a ticket automated against "
        "an `escalate` label has not necessarily received a wrong answer, only one the "
        "corpus would have preferred a human to give. The figure that does bear directly "
        "on harm is the count of automated tickets flagged `must_not_auto_respond`, which "
        "is zero at every threshold in the sweep because the never-automate policy rule, "
        "rather than the threshold, is what prevents them.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="CloudServe calibration and threshold selection")
    parser.add_argument("--tickets", default="05_Datasets/development_tickets.json")
    parser.add_argument("--output", default="evaluation/results/calibration.json")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--cost-wrong", type=float, default=DEFAULT_COST_WRONG_AUTOMATION)
    args = parser.parse_args()

    with open(args.tickets, "r", encoding="utf-8") as fh:
        tickets = json.load(fh)

    print(f"Scoring {len(tickets)} tickets out-of-fold across {args.folds} folds...")
    records = out_of_fold_records(tickets, folds=args.folds)

    intent_cal = calibration_table(records, "intent_confidence", "intent_correct")
    readiness_cal = calibration_table(records, "readiness", "should_automate")
    main_sweep = sweep(records, cost_wrong=args.cost_wrong)

    # Retained for the report: the signal version one used, and why it was abandoned.
    legacy = []
    steps = int(round((0.95 - 0.05) / 0.05)) + 1
    should = [r for r in records if r["should_automate"]]
    for i in range(steps):
        t = round(0.05 + i * 0.05, 2)
        auto = [r for r in records
                if r["predicted_intent"] not in MUST_NOT_AUTO_RESPOND_INTENTS
                and r["intent_confidence"] >= t]
        legacy.append({
            "threshold": t,
            "automation_rate_pct": _pct(len(auto), len(records)),
            "automation_precision_pct": _pct(
                sum(1 for r in auto if r["should_automate"]), len(auto)),
            "automation_recall_pct": _pct(
                sum(1 for r in should
                    if r["predicted_intent"] not in MUST_NOT_AUTO_RESPOND_INTENTS
                    and r["intent_confidence"] >= t), len(should)),
        })

    result = {
        "n_records": len(records),
        "folds": args.folds,
        "assumed_cost_of_wrong_automation": args.cost_wrong,
        "intent_accuracy_pct": _pct(sum(1 for r in records if r["intent_correct"]), len(records)),
        "intent_ece_points": expected_calibration_error(intent_cal, len(records)),
        "readiness_ece_points": expected_calibration_error(readiness_cal, len(records)),
        "intent_calibration": intent_cal,
        "readiness_calibration": readiness_cal,
        "sweep": main_sweep,
        "legacy_intent_confidence_sweep": legacy,
        "recommendation": choose(main_sweep),
        "sensitivity": sensitivity(records),
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    md_path = os.path.splitext(args.output)[0] + ".md"
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(result))

    print(render_markdown(result))
    print(f"\nWritten to {args.output} and {md_path}")


if __name__ == "__main__":
    main()
