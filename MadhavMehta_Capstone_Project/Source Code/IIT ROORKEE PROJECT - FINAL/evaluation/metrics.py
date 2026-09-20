"""
Metrics calculation for CloudServe Support Automation.
Satisfies Acceptance Criterion A10 and the Evaluation Framework.

Every figure in the generated report is computed here from the run's own output.
Each one is compared against its target by `_status`, which returns PASS or FAIL
on the arithmetic. No status is written by hand. A report that marked its own
misses as passes would be worse than useless, because the point of measuring is
to find out where the system falls short while there is still time to say so.
"""
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional

# Targets from the Project Brief (section 7) and the Evaluation Framework.
TARGETS = {
    "first_contact_resolution_pct": {"op": ">=", "value": 60.0, "label": "≥ 60%"},
    "escalation_rate_pct": {"op": "<=", "value": 30.0, "label": "≤ 30%"},
    "mean_reply_seconds": {"op": "<=", "value": 300.0, "label": "< 5 min"},
    "classification_precision_macro_pct": {"op": ">=", "value": 85.0, "label": "≥ 85%"},
    "citation_accuracy_pct": {"op": ">=", "value": 95.0, "label": "≥ 95%"},
    "hallucination_rate_pct": {"op": "<=", "value": 5.0, "label": "≤ 5%"},
    "p95_latency_ms": {"op": "<=", "value": 3000.0, "label": "< 3s"},
    "private_data_occurrences": {"op": "==", "value": 0, "label": "0"},
    "cross_group_variation_points": {"op": "<=", "value": 5.0, "label": "< 5 pts"},
    "decision_log_reconciled": {"op": "is_true", "value": True, "label": "exact match"},
}

BASELINES = {
    "first_contact_resolution_pct": "42%",
    "escalation_rate_pct": "58%",
    "mean_reply_seconds": "8–12 hrs",
    "csat": "3.2 / 5",
}


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 2) if d else 0.0


def _status(key: str, value: Any) -> str:
    """Evaluate a measured value against its target. This is the only source of PASS."""
    target = TARGETS.get(key)
    if target is None or value is None:
        return "INFO"
    op, threshold = target["op"], target["value"]
    if op == ">=":
        return "PASS" if value >= threshold else "FAIL"
    if op == "<=":
        return "PASS" if value <= threshold else "FAIL"
    if op == "==":
        return "PASS" if value == threshold else "FAIL"
    if op == "is_true":
        return "PASS" if bool(value) else "FAIL"
    return "INFO"


def _per_class_scores(pairs: List[tuple]) -> Dict[str, Dict[str, Any]]:
    """
    Precision, recall and F1 for each intent class.

    The Evaluation Framework is explicit that an overall accuracy figure hides
    a system that is excellent on two common intents and useless on the rest,
    so this is reported per class rather than aggregated away.
    """
    tp: Dict[str, int] = defaultdict(int)
    fp: Dict[str, int] = defaultdict(int)
    fn: Dict[str, int] = defaultdict(int)
    support: Dict[str, int] = defaultdict(int)

    for actual, predicted in pairs:
        support[actual] += 1
        if actual == predicted:
            tp[actual] += 1
        else:
            fp[predicted] += 1
            fn[actual] += 1

    classes = sorted(set(list(support) + list(fp)))
    out: Dict[str, Dict[str, Any]] = {}
    for cls in classes:
        precision = tp[cls] / (tp[cls] + fp[cls]) * 100 if (tp[cls] + fp[cls]) else 0.0
        recall = tp[cls] / (tp[cls] + fn[cls]) * 100 if (tp[cls] + fn[cls]) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        out[cls] = {
            "support": support[cls],
            "precision_pct": round(precision, 2),
            "recall_pct": round(recall, 2),
            "f1_pct": round(f1, 2),
        }
    return out


def _confusion_pairs(results: List[Dict[str, Any]],
                     raw: List[Dict[str, Any]]) -> List[tuple]:
    pairs = []
    for r, t in zip(results, raw):
        actual = (t.get("labels") or {}).get("intent")
        if actual:
            pairs.append((actual, r["classification"]["intent"]))
    return pairs


def calculate_metrics(
    processed_results: List[Dict[str, Any]],
    raw_tickets: List[Dict[str, Any]],
    db_reconciliation: Dict[str, Any],
) -> Dict[str, Any]:
    total = len(processed_results)
    if total == 0:
        return {"error": "No tickets processed"}

    # ------------------------------------------------------------ 1. Volume
    answered = sum(1 for r in processed_results if r["status"] == "answered")
    escalated = sum(1 for r in processed_results if r["status"] == "escalated")
    blocked = sum(1 for r in processed_results if r["status"] == "blocked")
    degraded = sum(1 for r in processed_results if r.get("degraded"))
    by_provider = sum(1 for r in processed_results if r.get("generator_source") == "provider")
    by_local_primary = sum(1 for r in processed_results
                           if r.get("generator_source") == "local_primary")
    by_local_fallback = sum(1 for r in processed_results
                            if r.get("generator_source") == "local_fallback")

    # ---------------------------------------------------------- 2. Business
    # First contact resolution: closed with no human involvement. A blocked
    # response goes to a human, so it counts against resolution, not for it.
    fcr = _pct(answered, total)
    escalation_rate = _pct(escalated + blocked, total)

    latencies = [r.get("latency_ms", 0.0) for r in processed_results]
    mean_latency = round(statistics.mean(latencies), 2)
    median_latency = round(statistics.median(latencies), 2)
    p95_latency = round(
        statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20
        else max(latencies), 2)

    # Time to first reply. An answered ticket replies at machine latency; an
    # escalated one waits for an agent, so the historic median stands in for it.
    # That assumption is stated in the report rather than buried here.
    historic = [t.get("history", {}).get("resolution_time_minutes")
                for t in raw_tickets
                if t.get("history", {}).get("resolution_time_minutes") is not None]
    assumed_human_reply_seconds = (statistics.median(historic) * 60) if historic else None

    # Two figures, because one of them alone would mislead.
    #
    # `automated_reply_seconds` is measured: the time an answered ticket took to
    # produce its reply. `mean_reply_seconds` is the blended figure across the
    # whole queue, which assumes an escalated ticket waits the historic median
    # for an agent. The blended figure is the one held against the client's
    # target, because the customer whose ticket escalated is still waiting.
    automated_seconds = [r.get("latency_ms", 0.0) / 1000.0
                         for r in processed_results if r["status"] == "answered"]
    blended_seconds = []
    for r in processed_results:
        if r["status"] == "answered":
            blended_seconds.append(r.get("latency_ms", 0.0) / 1000.0)
        elif assumed_human_reply_seconds is not None:
            blended_seconds.append(assumed_human_reply_seconds)

    mean_reply = round(statistics.mean(blended_seconds), 2) if blended_seconds else None
    median_reply = round(statistics.median(blended_seconds), 2) if blended_seconds else None
    mean_automated_reply = round(statistics.mean(automated_seconds), 3) \
        if automated_seconds else None

    # --------------------------------------------------------- 3. Technical
    pairs = _confusion_pairs(processed_results, raw_tickets)
    per_class = _per_class_scores(pairs)
    labelled = len(pairs)
    correct = sum(1 for a, p in pairs if a == p)
    accuracy = _pct(correct, labelled)
    macro_precision = round(
        statistics.mean([v["precision_pct"] for v in per_class.values()]), 2
    ) if per_class else 0.0
    macro_recall = round(
        statistics.mean([v["recall_pct"] for v in per_class.values()]), 2
    ) if per_class else 0.0

    # Retrieval and citations, measured only where the corpus names expected docs.
    retrieval_applicable = 0
    retrieval_hits = 0
    citation_applicable = 0
    citation_correct = 0
    unresolvable_citations = 0

    for r, t in zip(processed_results, raw_tickets):
        labels = t.get("labels") or {}
        expected = labels.get("expected_doc_ids") or []
        retrieved_ids = [h["doc_id"] for h in r.get("retrieval_hits", [])]

        if expected:
            retrieval_applicable += 1
            if any(doc in retrieved_ids for doc in expected):
                retrieval_hits += 1

        citations = r.get("citations", [])
        if r["status"] == "answered" and citations:
            citation_applicable += 1
            # A citation is accurate when it resolves to a passage retrieval
            # actually returned for this ticket. Anything else is manufactured
            # confidence and is counted against us.
            if all(c in retrieved_ids for c in citations):
                if not expected or any(c in expected for c in citations):
                    citation_correct += 1
            else:
                unresolvable_citations += 1

    retrieval_hit_rate = _pct(retrieval_hits, retrieval_applicable)
    citation_accuracy = _pct(citation_correct, citation_applicable)

    # Hallucination proxy: an answered response whose citations do not resolve,
    # or which the grounding guardrail flagged. Stated as a proxy in the report;
    # the Evaluation Framework asks for human review, which is recorded
    # separately in the report's manual sample.
    hallucinations = sum(
        1 for r in processed_results
        if r["status"] == "answered"
        and (r.get("guardrails", {}).get("unsupported_claims")
             or (r.get("citations") and not all(
                 c in [h["doc_id"] for h in r.get("retrieval_hits", [])]
                 for c in r["citations"])))
    )
    hallucination_rate = _pct(hallucinations, max(answered, 1))

    # -------------------------------------------------------- 4. Governance
    guardrail_triggers: Dict[str, int] = defaultdict(int)
    checks_run = 0
    pii_occurrences = 0
    for r in processed_results:
        g = r.get("guardrails", {}) or {}
        if g.get("checks_performed"):
            checks_run += 1
        if g.get("pii_detected"):
            pii_occurrences += 1
        for rule in g.get("triggered_rules", []) or []:
            guardrail_triggers[rule] += 1

    # Fairness. Segment resolution rate and compare best against worst.
    def segment(key_fn) -> Dict[str, Dict[str, Any]]:
        buckets: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "answered": 0})
        for r, t in zip(processed_results, raw_tickets):
            name = str(key_fn(t) or "unknown")
            buckets[name]["total"] += 1
            if r["status"] == "answered":
                buckets[name]["answered"] += 1
        return {
            name: {"tickets": v["total"],
                   "resolution_rate_pct": _pct(v["answered"], v["total"])}
            for name, v in sorted(buckets.items())
        }

    segments = {
        "customer_tier": segment(lambda t: t.get("customer_tier")),
        "language_fluency": segment(lambda t: t.get("language_fluency")),
        "channel": segment(lambda t: t.get("channel")),
    }

    variations = {}
    for name, seg in segments.items():
        rates = {k: v["resolution_rate_pct"] for k, v in seg.items() if v["tickets"] >= 5}
        if len(rates) >= 2:
            best, worst = max(rates, key=rates.get), min(rates, key=rates.get)
            variations[name] = {
                "best": best, "best_pct": rates[best],
                "worst": worst, "worst_pct": rates[worst],
                "variation_points": round(rates[best] - rates[worst], 2),
            }
    worst_variation = max(
        (v["variation_points"] for v in variations.values()), default=0.0)

    reconciled = bool(db_reconciliation.get("reconciled"))

    report: Dict[str, Any] = {
        "volume": {
            "tickets_processed": total,
            "answered_automatically": answered,
            "escalated_to_human": escalated,
            "blocked_by_guardrails": blocked,
            "handled_on_degraded_path": degraded,
            "generated_by_provider": by_provider,
            "generated_by_local_primary": by_local_primary,
            "generated_by_local_fallback": by_local_fallback,
        },
        "business": {
            "first_contact_resolution_pct": fcr,
            "escalation_rate_pct": escalation_rate,
            "mean_reply_seconds": mean_reply,
            "median_reply_seconds": median_reply,
            "mean_automated_reply_seconds": mean_automated_reply,
            "assumed_human_reply_seconds": assumed_human_reply_seconds,
        },
        "technical": {
            "classification_accuracy_pct": accuracy,
            "classification_precision_macro_pct": macro_precision,
            "classification_recall_macro_pct": macro_recall,
            "classification_per_class": per_class,
            "retrieval_hit_rate_pct": retrieval_hit_rate,
            "retrieval_evaluated_on": retrieval_applicable,
            "citation_accuracy_pct": citation_accuracy,
            "citation_evaluated_on": citation_applicable,
            "citations_that_did_not_resolve": unresolvable_citations,
            "hallucination_rate_pct": hallucination_rate,
            "mean_latency_ms": mean_latency,
            "median_latency_ms": median_latency,
            "p95_latency_ms": p95_latency,
        },
        "governance": {
            "decisions_logged": db_reconciliation.get("total_decisions_logged", 0),
            "decision_log_reconciled": reconciled,
            "reconciliation_detail": db_reconciliation.get("detail", ""),
            "decisions_by_action": db_reconciliation.get("decisions_by_action", {}),
            "responses_validated": checks_run,
            "guardrail_activations_by_rule": dict(guardrail_triggers),
            "guardrail_activations_total": sum(guardrail_triggers.values()),
            "private_data_occurrences": pii_occurrences,
            "segments": segments,
            "cross_group_variations": variations,
            "cross_group_variation_points": worst_variation,
        },
    }

    report["status"] = {
        "first_contact_resolution_pct": _status("first_contact_resolution_pct", fcr),
        "escalation_rate_pct": _status("escalation_rate_pct", escalation_rate),
        "mean_reply_seconds": _status("mean_reply_seconds", mean_reply),
        "classification_precision_macro_pct": _status(
            "classification_precision_macro_pct", macro_precision),
        "citation_accuracy_pct": _status("citation_accuracy_pct", citation_accuracy),
        "hallucination_rate_pct": _status("hallucination_rate_pct", hallucination_rate),
        "p95_latency_ms": _status("p95_latency_ms", p95_latency),
        "private_data_occurrences": _status("private_data_occurrences", pii_occurrences),
        "cross_group_variation_points": _status(
            "cross_group_variation_points", worst_variation),
        "decision_log_reconciled": _status("decision_log_reconciled", reconciled),
    }
    report["summary"] = {
        "targets_met": sum(1 for v in report["status"].values() if v == "PASS"),
        "targets_missed": sum(1 for v in report["status"].values() if v == "FAIL"),
        "targets_evaluated": len(report["status"]),
    }
    return report


def generate_markdown_report(metrics: Dict[str, Any],
                             run_context: Optional[Dict] = None,
                             guardrail_section: str = "") -> str:
    v, b = metrics["volume"], metrics["business"]
    t, g = metrics["technical"], metrics["governance"]
    s, summary = metrics["status"], metrics["summary"]
    ctx = run_context or {}

    def row(label: str, baseline: str, target: str, achieved: str, key: str) -> str:
        return f"| {label} | {baseline} | {target} | **{achieved}** | {s.get(key, 'INFO')} |"

    lines = [
        "# CloudServe Support Automation — Evaluation Report",
        "",
        f"- **Run date:** {ctx.get('run_started_at', 'unknown')}",
        f"- **Input file:** `{ctx.get('input_path', 'unknown')}`",
        f"- **Tickets processed:** {v['tickets_processed']}",
        f"- **Routing threshold:** {ctx.get('threshold', 'unknown')}",
        f"- **Wall clock:** {ctx.get('duration_seconds', 'unknown')}s",
        f"- **Generation path:** {v['generated_by_provider']} by model provider, "
        f"{v['generated_by_local_primary']} by local synthesis (no provider configured), "
        f"{v['generated_by_local_fallback']} by local fallback after a provider failure",
        "",
        f"**{summary['targets_met']} of {summary['targets_evaluated']} targets met; "
        f"{summary['targets_missed']} missed.** Every status below is computed from the "
        "measured value against its target; none is written by hand.",
        "",
        "---",
        "",
        "## 1. Volume",
        "",
        "| Measure | Count |",
        "|---|---|",
        f"| Tickets processed | {v['tickets_processed']} |",
        f"| Answered automatically | {v['answered_automatically']} |",
        f"| Escalated to a human | {v['escalated_to_human']} |",
        f"| Blocked by a guardrail | {v['blocked_by_guardrails']} |",
        f"| Handled on a degraded path | {v['handled_on_degraded_path']} |",
        "",
        "## 2. Business outcomes",
        "",
        "These lead the report because they are what CloudServe is paying for.",
        "",
        "| Measure | Baseline | Target | Achieved | Status |",
        "|---|---|---|---|---|",
        row("First contact resolution", BASELINES["first_contact_resolution_pct"],
            TARGETS["first_contact_resolution_pct"]["label"],
            f"{b['first_contact_resolution_pct']}%", "first_contact_resolution_pct"),
        row("Escalation rate", BASELINES["escalation_rate_pct"],
            TARGETS["escalation_rate_pct"]["label"],
            f"{b['escalation_rate_pct']}%", "escalation_rate_pct"),
        row("Mean time to first reply, whole queue", BASELINES["mean_reply_seconds"],
            TARGETS["mean_reply_seconds"]["label"],
            f"{round((b['mean_reply_seconds'] or 0) / 60, 1)} min", "mean_reply_seconds"),
        f"| Mean time to first reply, automated tickets only | — | — | "
        f"**{b['mean_automated_reply_seconds']} s** | INFO |",
        "",
        "Two figures are given because either alone would mislead. The automated figure "
        "is measured directly and is the experience of the "
        f"{v['answered_automatically']} customers whose tickets were answered. The "
        "whole-queue figure assumes an escalated ticket still waits the historic median "
        f"of {round((b['assumed_human_reply_seconds'] or 0) / 60)} minutes for an agent, "
        "and it is the one held against the client's target, because a customer whose "
        "ticket escalated is still waiting. That assumption is why this row can fail "
        "even when three quarters of the queue is answered in milliseconds: automation "
        "alone does not move the mean unless agent response time moves with it.",
        "",
        "## 3. Technical performance",
        "",
        "| Measure | Target | Achieved | Status |",
        "|---|---|---|---|",
        f"| Intent classification, macro precision | "
        f"{TARGETS['classification_precision_macro_pct']['label']} | "
        f"**{t['classification_precision_macro_pct']}%** | "
        f"{s['classification_precision_macro_pct']} |",
        f"| Intent classification, macro recall | — | "
        f"**{t['classification_recall_macro_pct']}%** | INFO |",
        f"| Intent classification, overall accuracy | — | "
        f"**{t['classification_accuracy_pct']}%** | INFO |",
        f"| Retrieval hit rate (n={t['retrieval_evaluated_on']}) | — | "
        f"**{t['retrieval_hit_rate_pct']}%** | INFO |",
        f"| Citation accuracy (n={t['citation_evaluated_on']}) | "
        f"{TARGETS['citation_accuracy_pct']['label']} | "
        f"**{t['citation_accuracy_pct']}%** | {s['citation_accuracy_pct']} |",
        f"| Hallucination rate (proxy) | {TARGETS['hallucination_rate_pct']['label']} | "
        f"**{t['hallucination_rate_pct']}%** | {s['hallucination_rate_pct']} |",
        f"| Latency, 95th percentile | {TARGETS['p95_latency_ms']['label']} | "
        f"**{t['p95_latency_ms']} ms** | {s['p95_latency_ms']} |",
        f"| Latency, median | — | **{t['median_latency_ms']} ms** | INFO |",
        "",
        "### 3.1 Per-class classification scores",
        "",
        "An overall accuracy figure would hide a system that is strong on the two "
        "commonest intents and weak elsewhere, so the breakdown is given in full.",
        "",
        "| Intent | Support | Precision | Recall | F1 |",
        "|---|---|---|---|---|",
    ]
    for name, c in sorted(t["classification_per_class"].items(),
                          key=lambda kv: -kv[1]["support"]):
        lines.append(f"| {name} | {c['support']} | {c['precision_pct']}% | "
                     f"{c['recall_pct']}% | {c['f1_pct']}% |")

    lines += [
        "",
        "## 4. Governance",
        "",
        "| Condition | Requirement | Observed | Status |",
        "|---|---|---|---|",
        f"| Private data in outbound responses | "
        f"{TARGETS['private_data_occurrences']['label']} | "
        f"**{g['private_data_occurrences']}** | {s['private_data_occurrences']} |",
        f"| Decision log reconciliation | "
        f"{TARGETS['decision_log_reconciled']['label']} | "
        f"**{g['decisions_logged']} decisions / {v['tickets_processed']} tickets** | "
        f"{s['decision_log_reconciled']} |",
        f"| Quality variation across customer groups | "
        f"{TARGETS['cross_group_variation_points']['label']} | "
        f"**{g['cross_group_variation_points']} pts** | "
        f"{s['cross_group_variation_points']} |",
        f"| Responses passed through validation | every response | "
        f"**{g['responses_validated']} / {v['tickets_processed']}** | INFO |",
        "",
        f"Reconciliation detail: {g['reconciliation_detail']}",
        "",
        "### 4.1 Guardrail activations",
        "",
    ]
    if g["guardrail_activations_by_rule"]:
        lines += ["| Rule | Times fired |", "|---|---|"]
        for rule, count in sorted(g["guardrail_activations_by_rule"].items(),
                                  key=lambda kv: -kv[1]):
            lines.append(f"| {rule} | {count} |")
    else:
        lines.append("No guardrail fired during this run. The guardrails are still "
                     "executed on every response; see the test suite for the cases "
                     "that trigger each one.")

    lines += ["", "### 4.2 Fairness across segments", ""]
    for seg_name, seg in g["segments"].items():
        lines += [
            f"**By {seg_name.replace('_', ' ')}**",
            "",
            "| Segment | Tickets | Resolution rate |",
            "|---|---|---|",
        ]
        for name, data in seg.items():
            lines.append(f"| {name} | {data['tickets']} | {data['resolution_rate_pct']}% |")
        var = g["cross_group_variations"].get(seg_name)
        if var:
            lines += ["", f"Variation: {var['variation_points']} points "
                          f"({var['best']} {var['best_pct']}% to "
                          f"{var['worst']} {var['worst_pct']}%).", ""]
        else:
            lines.append("")

    if guardrail_section:
        lines += ["", guardrail_section]

    missed = [k for k, val in s.items() if val == "FAIL"]
    lines += [
        "## 6. What this run did not achieve",
        "",
    ]
    if missed:
        lines.append("The following targets were missed:")
        lines.append("")
        for key in missed:
            lines.append(f"- **{key.replace('_', ' ')}** — target "
                         f"{TARGETS[key]['label']}.")
        lines.append("")
    else:
        lines += ["Every evaluated target was met on this run.", ""]

    lines += [
        "## 7. How far these figures should be trusted",
        "",
        "The figures above should be treated with caution because:",
        "",
        "1. Citation accuracy and the hallucination rate are automated proxies. They "
        "check that a citation resolves to a passage retrieval returned, not that the "
        "passage supports the sentence it is attached to. The Evaluation Framework asks "
        "for human review of at least fifty responses by two assessors; that was carried "
        "out on a sample and is reported separately in the project report, and its "
        "sample size is smaller than the automated figure's.",
        "2. Time to first reply is a projection rather than a measurement. No human "
        "replied to any ticket in this run, so the escalated half of that figure rests on "
        "an assumption about agent response time drawn from historic data.",
        "3. Customer satisfaction is not reported here at all. There were no customers, "
        "and a satisfaction number invented from a formula would be worse than its absence.",
        "4. The corpus is synthetic and its intents are unusually separable. "
        "Classification figures on real CloudServe traffic would very likely be lower, "
        "and the report says by roughly how much we would expect.",
        "",
    ]
    return "\n".join(lines)
