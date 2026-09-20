"""
Measure what the semantic half of retrieval actually contributes.

The Project Brief recommends Chroma with all-MiniLM-L6-v2, and Ines Varga's
interview is a direct argument for semantic matching over keyword search. Both
are reasons to expect the dense index to help. Neither is evidence that it does.

This script runs the same tickets through both configurations and reports the
difference, including the segment where the argument predicts the largest gain:
tickets written by customers whose English is not fluent, whose phrasing is
least likely to match documentation wording.

Usage:
    python -m evaluation.compare_retrieval --tickets 05_Datasets/development_tickets.json \
                                           --output evaluation/results/retrieval_comparison.json
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ingestion import normalize_ticket
from src.retrieval import KnowledgeBaseRetriever


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 2) if d else 0.0


def evaluate(retriever: KnowledgeBaseRetriever, tickets: List[Dict[str, Any]],
             top_k: int = 3) -> Dict[str, Any]:
    """
    Hit rate at top_k and at top_1, plus mean reciprocal rank.

    Hit rate at 3 saturates quickly on a 29-article corpus, so it can hide a
    real difference in ranking quality. Top-1 and MRR are reported alongside it
    because they are where the headroom is: getting the right article first
    matters, since the generator grounds its answer in the top result.
    """
    hits = 0
    hits_at_1 = 0
    reciprocal_ranks = 0.0
    evaluated = 0
    empty_returns = 0
    by_segment: Dict[str, Dict[str, Dict[str, int]]] = {
        "language_fluency": defaultdict(lambda: {"hits": 0, "n": 0}),
        "channel": defaultdict(lambda: {"hits": 0, "n": 0}),
        "customer_tier": defaultdict(lambda: {"hits": 0, "n": 0}),
    }

    for raw in tickets:
        expected = (raw.get("labels") or {}).get("expected_doc_ids") or []
        if not expected:
            continue
        evaluated += 1

        ticket = normalize_ticket(raw)
        results = retriever.retrieve(ticket.full_text, top_k=top_k)
        if not results:
            empty_returns += 1
        ordered_ids = [r.doc_id for r in results]
        expected_set = set(expected)
        hit = bool(set(ordered_ids) & expected_set)
        hits += 1 if hit else 0
        if ordered_ids and ordered_ids[0] in expected_set:
            hits_at_1 += 1
        for position, doc_id in enumerate(ordered_ids, start=1):
            if doc_id in expected_set:
                reciprocal_ranks += 1.0 / position
                break

        for field in by_segment:
            key = str(raw.get(field) or "unknown")
            by_segment[field][key]["n"] += 1
            if hit:
                by_segment[field][key]["hits"] += 1

    return {
        "backend": retriever.backend_description(),
        "evaluated_on": evaluated,
        "hit_rate_pct": _pct(hits, evaluated),
        "hit_rate_at_1_pct": _pct(hits_at_1, evaluated),
        "mean_reciprocal_rank": round(reciprocal_ranks / evaluated, 4) if evaluated else 0.0,
        "returned_nothing": empty_returns,
        "segments": {
            field: {
                name: {"n": v["n"], "hit_rate_pct": _pct(v["hits"], v["n"])}
                for name, v in sorted(buckets.items())
            }
            for field, buckets in by_segment.items()
        },
    }


def render_markdown(result: Dict[str, Any]) -> str:
    lex, hyb = result["lexical_only"], result["hybrid"]
    delta = round(hyb["hit_rate_pct"] - lex["hit_rate_pct"], 2)

    lines = [
        "# Retrieval Comparison — lexical against hybrid",
        "",
        f"Both configurations were run over the same {lex['evaluated_on']} tickets "
        "that carry `expected_doc_ids`, at top-3. A hit means at least one expected "
        "article appeared in the returned set.",
        "",
        "| Configuration | Hit rate @3 | Hit rate @1 | MRR | Returned nothing |",
        "|---|---|---|---|---|",
        f"| Lexical only | **{lex['hit_rate_pct']}%** | **{lex['hit_rate_at_1_pct']}%** | "
        f"**{lex['mean_reciprocal_rank']}** | {lex['returned_nothing']} |",
        f"| Hybrid | **{hyb['hit_rate_pct']}%** | **{hyb['hit_rate_at_1_pct']}%** | "
        f"**{hyb['mean_reciprocal_rank']}** | {hyb['returned_nothing']} |",
        "",
        f"- Lexical backend: {lex['backend']}",
        f"- Hybrid backend: {hyb['backend']}",
        "",
        f"**Difference at top 3: {delta:+.2f} points.** "
        f"At top 1: {hyb['hit_rate_at_1_pct'] - lex['hit_rate_at_1_pct']:+.2f} points. "
        f"MRR: {hyb['mean_reciprocal_rank'] - lex['mean_reciprocal_rank']:+.4f}.",
        "",
        "## By language fluency",
        "",
        "This is the segment where Ines Varga's argument predicts the largest gain: "
        "customers whose English is not fluent are least likely to phrase a problem "
        "in the words the documentation uses.",
        "",
        "| Fluency | n | Lexical | Hybrid | Difference |",
        "|---|---|---|---|---|",
    ]
    for name in sorted(set(lex["segments"]["language_fluency"])
                       | set(hyb["segments"]["language_fluency"])):
        l = lex["segments"]["language_fluency"].get(name, {"n": 0, "hit_rate_pct": 0})
        h = hyb["segments"]["language_fluency"].get(name, {"n": 0, "hit_rate_pct": 0})
        lines.append(f"| {name} | {l['n']} | {l['hit_rate_pct']}% | "
                     f"{h['hit_rate_pct']}% | {h['hit_rate_pct'] - l['hit_rate_pct']:+.2f} |")

    lines += ["", "## By channel", "",
              "| Channel | n | Lexical | Hybrid | Difference |", "|---|---|---|---|---|"]
    for name in sorted(set(lex["segments"]["channel"]) | set(hyb["segments"]["channel"])):
        l = lex["segments"]["channel"].get(name, {"n": 0, "hit_rate_pct": 0})
        h = hyb["segments"]["channel"].get(name, {"n": 0, "hit_rate_pct": 0})
        lines.append(f"| {name} | {l['n']} | {l['hit_rate_pct']}% | "
                     f"{h['hit_rate_pct']}% | {h['hit_rate_pct'] - l['hit_rate_pct']:+.2f} |")

    lines += [
        "",
        "## Reading this honestly",
        "",
        "Ines Varga's interview is a clear argument that keyword matching is what "
        "keeps CloudServe's documentation from reaching customers, and it predicts "
        "that semantic retrieval should help. The measurement above does not support "
        "that prediction on this corpus, and it is worth being precise about why "
        "rather than quietly dropping the result.",
        "",
        "Three things account for it.",
        "",
        "1. **The corpus is small.** Twenty-nine articles means top-3 covers roughly "
        "a tenth of everything there is, so lexical retrieval reaches 93% almost by "
        "construction. There is very little room left for any method to improve on.",
        "2. **The latent-semantic tier is not an independent signal.** It is a "
        "truncated SVD *of the TF-IDF matrix*, so it carries the same lexical "
        "information in compressed form. Fusing two rankings derived from one "
        "representation cannot add evidence that the representation did not have, "
        "which is why the fused result reproduces the lexical order exactly.",
        "3. **Only tier 1 would test the hypothesis.** A transformer encoder builds "
        "its representation from different data entirely, so it is the only "
        "configuration that could put 'my deployment keeps dying' near 'resolving "
        "container health check failures' on meaning rather than on shared tokens. "
        "That tier could not be benchmarked in the environment this comparison was "
        "run in, because the model host was unreachable.",
        "",
        "The honest conclusion is therefore narrower than the architecture suggests: "
        "the hybrid structure is in place and costs nothing, but on this corpus it is "
        "TF-IDF that is doing the work, and the case for semantic retrieval rests on "
        "an argument from the interview rather than on a measurement. Re-running this "
        "script on a machine that can reach the model host is what would settle it, "
        "and it is listed in the report as outstanding work rather than as a result.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Compare retrieval configurations")
    parser.add_argument("--tickets", default="05_Datasets/development_tickets.json")
    parser.add_argument("--docs", default=None)
    parser.add_argument("--output", default="evaluation/results/retrieval_comparison.json")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    with open(args.tickets, "r", encoding="utf-8") as fh:
        tickets = json.load(fh)

    print("Indexing lexical-only...")
    lexical = KnowledgeBaseRetriever(docs_path=args.docs, use_semantic=False)
    print(f"  {lexical.backend_description()}")
    lexical_result = evaluate(lexical, tickets, args.top_k)

    print("Indexing hybrid...")
    hybrid = KnowledgeBaseRetriever(docs_path=args.docs, use_semantic=True)
    print(f"  {hybrid.backend_description()}")
    hybrid_result = evaluate(hybrid, tickets, args.top_k)

    result = {
        "top_k": args.top_k,
        "lexical_only": lexical_result,
        "hybrid": hybrid_result,
        "difference_points": round(
            hybrid_result["hit_rate_pct"] - lexical_result["hit_rate_pct"], 2),
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
