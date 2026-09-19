"""
Discovery analysis over the CloudServe development ticket corpus.

This script produces the quantitative evidence base for the Stage 1 Discovery
Workbook. It answers, from the data rather than from impression, the questions
the five stakeholder transcripts raise and disagree about.

Usage:
    python -m evaluation.discovery_analysis --tickets 05_Datasets/development_tickets.json \
                                            --docs 05_Datasets/documentation.json \
                                            --output evaluation/results/discovery_findings.json
"""
import os
import sys
import json
import argparse
import statistics
from collections import Counter, defaultdict
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 2) if denominator else 0.0


def _segment(tickets: List[Dict[str, Any]], key_fn) -> Dict[str, Dict[str, Any]]:
    """Group tickets by a key and summarise the historical outcomes of each group."""
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in tickets:
        groups[str(key_fn(t))].append(t)

    summary = {}
    for name, group in sorted(groups.items()):
        history = [t.get("history", {}) for t in group]
        csat = [h["csat_rating"] for h in history if h.get("csat_rating") is not None]
        res = [h["resolution_time_minutes"] for h in history
               if h.get("resolution_time_minutes") is not None]
        summary[name] = {
            "tickets": len(group),
            "share_of_total_pct": _pct(len(group), len(tickets)),
            "first_contact_resolution_pct": _pct(
                sum(1 for h in history if h.get("first_contact_resolution")), len(group)),
            "escalated_pct": _pct(sum(1 for h in history if h.get("escalated")), len(group)),
            "repeat_contact_pct": _pct(sum(1 for h in history if h.get("repeat_contact")), len(group)),
            "answerable_from_docs_pct": _pct(
                sum(1 for t in group if t["labels"].get("answerable_from_docs")), len(group)),
            "mean_csat": round(statistics.mean(csat), 2) if csat else None,
            "median_resolution_minutes": round(statistics.median(res), 1) if res else None,
        }
    return summary


def _spread(segment_summary: Dict[str, Dict[str, Any]], field: str) -> Dict[str, Any]:
    """Best-to-worst spread across segments, in percentage points."""
    values = {k: v[field] for k, v in segment_summary.items() if v.get(field) is not None}
    if not values:
        return {}
    best = max(values, key=values.get)
    worst = min(values, key=values.get)
    return {
        "best_segment": best,
        "best_value": values[best],
        "worst_segment": worst,
        "worst_value": values[worst],
        "spread_points": round(values[best] - values[worst], 2),
    }


def analyse(tickets: List[Dict[str, Any]], docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(tickets)
    history = [t.get("history", {}) for t in tickets]
    labels = [t.get("labels", {}) for t in tickets]

    csat_all = [h["csat_rating"] for h in history if h.get("csat_rating") is not None]
    res_all = [h["resolution_time_minutes"] for h in history
               if h.get("resolution_time_minutes") is not None]

    answerable = sum(1 for l in labels if l.get("answerable_from_docs"))
    fcr = sum(1 for h in history if h.get("first_contact_resolution"))
    escalated = sum(1 for h in history if h.get("escalated"))

    # --- The central finding: answers exist but are not being delivered -------
    # Tickets that were answerable from the documentation but still escalated.
    answerable_but_escalated = [
        t for t in tickets
        if t["labels"].get("answerable_from_docs") and t["history"].get("escalated")
    ]
    # Tickets that escalated at all, and how many of those were documented.
    escalated_tickets = [t for t in tickets if t["history"].get("escalated")]
    documented_share_of_escalations = _pct(len(answerable_but_escalated), len(escalated_tickets))

    # --- Effort distribution -------------------------------------------------
    # Effort is approximated by total resolution minutes attributable to an intent,
    # which is the only effort signal the dataset carries.
    effort_by_intent: Dict[str, int] = defaultdict(int)
    volume_by_intent: Dict[str, int] = defaultdict(int)
    for t in tickets:
        intent = t["labels"]["intent"]
        volume_by_intent[intent] += 1
        effort_by_intent[intent] += t["history"].get("resolution_time_minutes", 0) or 0
    total_effort = sum(effort_by_intent.values())
    effort_table = {
        intent: {
            "tickets": volume_by_intent[intent],
            "share_of_volume_pct": _pct(volume_by_intent[intent], total),
            "total_minutes": effort_by_intent[intent],
            "share_of_effort_pct": _pct(effort_by_intent[intent], total_effort),
            "mean_minutes_per_ticket": round(
                effort_by_intent[intent] / volume_by_intent[intent], 1),
            "answerable_from_docs_pct": _pct(
                sum(1 for t in tickets
                    if t["labels"]["intent"] == intent
                    and t["labels"].get("answerable_from_docs")),
                volume_by_intent[intent]),
        }
        for intent in sorted(volume_by_intent, key=lambda i: -effort_by_intent[i])
    }

    # --- Documentation coverage ---------------------------------------------
    corpus_ids = {d["doc_id"] for d in docs}
    cited_ids = Counter()
    for l in labels:
        for d in l.get("expected_doc_ids", []) or []:
            cited_ids[d] += 1
    unreferenced = sorted(corpus_ids - set(cited_ids))
    dangling = sorted(set(cited_ids) - corpus_ids)

    # --- Intents that policy should never automate ---------------------------
    never_automate = defaultdict(lambda: [0, 0])
    for t in tickets:
        intent = t["labels"]["intent"]
        never_automate[intent][1] += 1
        if t["labels"].get("must_not_auto_respond"):
            never_automate[intent][0] += 1
    must_not_table = {
        intent: {
            "flagged": flagged,
            "tickets": count,
            "flagged_pct": _pct(flagged, count),
        }
        for intent, (flagged, count) in sorted(
            never_automate.items(), key=lambda kv: -kv[1][0] / kv[1][1])
        if flagged
    }

    return {
        "corpus": {
            "tickets_analysed": total,
            "documentation_articles": len(docs),
            "documentation_articles_never_cited_as_expected": unreferenced,
            "expected_doc_ids_not_present_in_corpus": dangling,
        },
        "headline": {
            "answerable_from_documentation_pct": _pct(answerable, total),
            "historic_first_contact_resolution_pct": _pct(fcr, total),
            "delivery_gap_points": round(_pct(answerable, total) - _pct(fcr, total), 2),
            "historic_escalation_pct": _pct(escalated, total),
            "escalations_that_were_documented_pct": documented_share_of_escalations,
            "mean_csat": round(statistics.mean(csat_all), 2) if csat_all else None,
            "median_resolution_minutes": round(statistics.median(res_all), 1) if res_all else None,
            "mean_resolution_minutes": round(statistics.mean(res_all), 1) if res_all else None,
            "repeat_contact_pct": _pct(sum(1 for h in history if h.get("repeat_contact")), total),
        },
        "distribution": {
            "by_channel": dict(Counter(t["channel"] for t in tickets).most_common()),
            "by_intent": dict(Counter(l["intent"] for l in labels).most_common()),
            "by_urgency": dict(Counter(l["urgency"] for l in labels).most_common()),
            "by_expected_route": dict(Counter(l["expected_route"] for l in labels).most_common()),
            "by_tier": dict(Counter(t["customer_tier"] for t in tickets).most_common()),
            "by_language_fluency": dict(
                Counter(t.get("language_fluency") for t in tickets).most_common()),
            "by_region": dict(Counter(t.get("customer_region") for t in tickets).most_common()),
        },
        "segments": {
            "by_channel": _segment(tickets, lambda t: t["channel"]),
            "by_tier": _segment(tickets, lambda t: t["customer_tier"]),
            "by_language_fluency": _segment(tickets, lambda t: t.get("language_fluency")),
            "by_urgency": _segment(tickets, lambda t: t["labels"]["urgency"]),
            "by_region": _segment(tickets, lambda t: t.get("customer_region")),
        },
        "fairness_baseline": {
            "tier_fcr": _spread(_segment(tickets, lambda t: t["customer_tier"]),
                                "first_contact_resolution_pct"),
            "fluency_fcr": _spread(_segment(tickets, lambda t: t.get("language_fluency")),
                                   "first_contact_resolution_pct"),
            "fluency_csat": _spread(_segment(tickets, lambda t: t.get("language_fluency")),
                                    "mean_csat"),
        },
        "effort_by_intent": effort_table,
        "never_automate_by_intent": must_not_table,
    }


def render_markdown(f: Dict[str, Any]) -> str:
    h = f["headline"]
    lines = [
        "# Discovery Analysis — CloudServe Support Corpus",
        "",
        f"Computed from {f['corpus']['tickets_analysed']} development tickets and "
        f"{f['corpus']['documentation_articles']} knowledge base articles. "
        "Every figure in this file is produced by `evaluation/discovery_analysis.py` "
        "and can be regenerated by re-running it.",
        "",
        "## 1. The headline finding",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Tickets answerable from existing documentation | **{h['answerable_from_documentation_pct']}%** |",
        f"| Tickets actually resolved on first contact | **{h['historic_first_contact_resolution_pct']}%** |",
        f"| **Delivery gap** (answerable minus resolved) | **{h['delivery_gap_points']} points** |",
        f"| Historic escalation rate | {h['historic_escalation_pct']}% |",
        f"| Escalations whose answer was already documented | {h['escalations_that_were_documented_pct']}% |",
        f"| Mean CSAT | {h['mean_csat']} / 5 |",
        f"| Median time to resolution | {h['median_resolution_minutes']} minutes |",
        f"| Repeat contacts within the week | {h['repeat_contact_pct']}% |",
        "",
        "## 2. Outcomes by customer tier",
        "",
        "| Tier | Tickets | FCR | Escalated | Mean CSAT | Median mins |",
        "|---|---|---|---|---|---|",
    ]
    for name, s in f["segments"]["by_tier"].items():
        lines.append(
            f"| {name} | {s['tickets']} | {s['first_contact_resolution_pct']}% | "
            f"{s['escalated_pct']}% | {s['mean_csat']} | {s['median_resolution_minutes']} |")

    lines += [
        "",
        "## 3. Outcomes by language fluency",
        "",
        "| Fluency | Tickets | FCR | Escalated | Mean CSAT | Median mins |",
        "|---|---|---|---|---|---|",
    ]
    for name, s in f["segments"]["by_language_fluency"].items():
        lines.append(
            f"| {name} | {s['tickets']} | {s['first_contact_resolution_pct']}% | "
            f"{s['escalated_pct']}% | {s['mean_csat']} | {s['median_resolution_minutes']} |")

    lines += [
        "",
        "## 4. Outcomes by channel",
        "",
        "| Channel | Tickets | Share | FCR | Answerable from docs | Median mins |",
        "|---|---|---|---|---|---|",
    ]
    for name, s in f["segments"]["by_channel"].items():
        lines.append(
            f"| {name} | {s['tickets']} | {s['share_of_total_pct']}% | "
            f"{s['first_contact_resolution_pct']}% | {s['answerable_from_docs_pct']}% | "
            f"{s['median_resolution_minutes']} |")

    lines += [
        "",
        "## 5. Where the effort goes",
        "",
        "Effort is approximated by total recorded resolution minutes per intent, which is "
        "the only effort signal the corpus carries. Intents are ordered by share of effort.",
        "",
        "| Intent | Share of volume | Share of effort | Mean mins/ticket | Answerable from docs |",
        "|---|---|---|---|---|",
    ]
    for name, s in f["effort_by_intent"].items():
        lines.append(
            f"| {name} | {s['share_of_volume_pct']}% | {s['share_of_effort_pct']}% | "
            f"{s['mean_minutes_per_ticket']} | {s['answerable_from_docs_pct']}% |")

    lines += [
        "",
        "## 6. Intents the corpus flags as never-automate",
        "",
        "| Intent | Flagged must_not_auto_respond | Of tickets | Share |",
        "|---|---|---|---|",
    ]
    for name, s in f["never_automate_by_intent"].items():
        lines.append(f"| {name} | {s['flagged']} | {s['tickets']} | {s['flagged_pct']}% |")

    lines += [
        "",
        "## 7. Documentation coverage",
        "",
        f"- Articles in corpus: {f['corpus']['documentation_articles']}",
        f"- Articles never named as an expected source: "
        f"{len(f['corpus']['documentation_articles_never_cited_as_expected'])} "
        f"({', '.join(f['corpus']['documentation_articles_never_cited_as_expected']) or 'none'})",
        f"- Expected doc ids with no matching article: "
        f"{len(f['corpus']['expected_doc_ids_not_present_in_corpus'])}",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="CloudServe discovery analysis")
    parser.add_argument("--tickets", default="05_Datasets/development_tickets.json")
    parser.add_argument("--docs", default="05_Datasets/documentation.json")
    parser.add_argument("--output", default="evaluation/results/discovery_findings.json")
    args = parser.parse_args()

    with open(args.tickets, "r", encoding="utf-8") as fh:
        tickets = json.load(fh)
    with open(args.docs, "r", encoding="utf-8") as fh:
        docs = json.load(fh)

    findings = analyse(tickets, docs)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(findings, fh, indent=2)

    md_path = os.path.splitext(args.output)[0] + ".md"
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(findings))

    print(render_markdown(findings))
    print(f"\nWritten to {args.output} and {md_path}")


if __name__ == "__main__":
    main()
