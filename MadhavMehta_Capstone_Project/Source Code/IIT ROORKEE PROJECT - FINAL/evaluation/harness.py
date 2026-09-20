"""
Unattended evaluation harness for CloudServe Support Automation.
Satisfies Acceptance Criteria A9 and A10.

The harness takes an input path and an output path as arguments. It is run
against a file it has never seen, so nothing about the input is assumed beyond
the documented ticket schema, and a record that does not match that schema is
processed on the degraded path rather than being allowed to end the run.

Usage:
    python -m evaluation.harness --input 05_Datasets/validation_tickets.json \
                                 --output evaluation/results/
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evaluation.guardrail_probes import render_markdown as render_probes
from evaluation.guardrail_probes import run_probes
from evaluation.metrics import calculate_metrics, generate_markdown_report
from src.db import DecisionDatabase
from src.pipeline import SupportPipeline
from src.router import DEFAULT_CONFIDENCE_THRESHOLD


def _load_tickets(path: str) -> List[Dict[str, Any]]:
    """
    Read the input file.

    Accepts either a bare list of tickets or an object wrapping one under a
    `tickets`, `data` or `items` key, because the hidden set's envelope is not
    something we get to see in advance.
    """
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("tickets", "data", "items", "records"):
            if isinstance(payload.get(key), list):
                return payload[key]
        raise ValueError(
            f"Input JSON object contained no ticket list under any of "
            f"'tickets', 'data', 'items', 'records'. Keys present: {list(payload)}"
        )
    raise ValueError(f"Input JSON must be a list or an object, got {type(payload).__name__}")


def run_evaluation(
    input_path: str,
    output_dir: str,
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    docs_path: str = None,
    dev_path: str = None,
) -> Dict[str, Any]:
    started_at = datetime.now(timezone.utc)

    print("=" * 62)
    print("CloudServe Support Automation — unattended evaluation")
    print("=" * 62)
    print(f"  Input:     {input_path}")
    print(f"  Output:    {output_dir}")
    print(f"  Threshold: {threshold}")
    print(f"  Started:   {started_at.isoformat()}")
    print("=" * 62)

    if not os.path.exists(input_path):
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return {"exit_code": 2}

    os.makedirs(output_dir, exist_ok=True)

    try:
        raw_tickets = _load_tickets(input_path)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not read tickets from {input_path}: {exc}", file=sys.stderr)
        return {"exit_code": 2}

    total = len(raw_tickets)
    if total == 0:
        print("ERROR: input file contained no tickets.", file=sys.stderr)
        return {"exit_code": 2}

    print(f"[1/4] Loaded {total} tickets.")

    # A fresh decision log per run. Without this a second run into the same
    # output directory would leave the log holding two runs' records and the
    # A8 reconciliation would be measured against an inflated total.
    db_path = os.path.join(output_dir, "evaluation_decisions.db")
    DecisionDatabase(db_path=db_path, reset=True)

    pipeline = SupportPipeline(
        docs_path=docs_path,
        dev_path=dev_path,
        db_path=db_path,
        confidence_threshold=threshold,
    )

    if not pipeline.retriever.chunks:
        print("WARNING: the documentation corpus is empty or could not be loaded. "
              "Every ticket will escalate for want of grounding.", file=sys.stderr)
    if not pipeline.classifier.is_trained:
        print("WARNING: the intent classifier could not be trained. Classification "
              "will fall back for every ticket.", file=sys.stderr)

    print(f"[2/4] Processing {total} tickets unattended...")
    results: List[Dict[str, Any]] = []
    start = time.time()

    for index, raw in enumerate(raw_tickets, start=1):
        try:
            output = pipeline.process_ticket(raw)
            results.append(output.model_dump())
        except Exception as exc:  # noqa: BLE001
            # process_ticket is written not to raise. If it somehow does, the
            # run still continues: A9 forbids a skipped or dropped ticket, and
            # one bad record must not cost us the other ninety-nine.
            print(f"      ticket {index} raised past the pipeline guard: "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
            results.append({
                "ticket_id": (raw.get("ticket_id") if isinstance(raw, dict)
                              else f"UNPARSEABLE-{index}"),
                "channel": "email",
                "status": "escalated",
                "routing": {"decision": "escalate", "confidence": 0.0,
                            "reason": f"Harness-level fallback: {exc}",
                            "threshold_applied": threshold, "readiness_score": 0.0},
                "classification": {"intent": "unclear_request", "intent_confidence": 0.0,
                                   "urgency": "medium", "urgency_confidence": 0.0,
                                   "alternatives_considered": [], "is_fallback": True},
                "retrieval_hits": [], "citations": [],
                "final_response": "Passed to an agent after a processing failure.",
                "guardrails": {"passed": True, "blocked": False, "checks_performed": [],
                               "triggered_rules": [], "pii_detected": False,
                               "unsupported_claims": []},
                "latency_ms": 0.0, "generator_source": "none", "degraded": True,
            })

        if index % 20 == 0 or index == total:
            print(f"      {index}/{total} ({index / total * 100:.0f}%)")

    duration = round(time.time() - start, 2)
    print(f"[3/4] Completed in {duration}s "
          f"({round(duration / total * 1000, 1)} ms/ticket).")

    reconciliation = pipeline.db.reconcile(total)
    print(f"      Decision log: {reconciliation['status']} — {reconciliation['detail']}")

    print("[4/4] Computing metrics and exercising guardrails...")
    metrics = calculate_metrics(results, raw_tickets, reconciliation)

    # Guardrail evidence. Run after reconciliation so that the probe tickets are
    # not counted against the ticket total, and against the same pipeline
    # instance so that a guardrail disabled for the run would be caught here.
    probe_report = run_probes(
        pipeline, probe_db_path=os.path.join(output_dir, "guardrail_probes.db"))
    metrics["guardrail_probes"] = probe_report
    print(f"      Guardrail probes: {probe_report['status']} "
          f"({probe_report['probes_passed']}/{probe_report['probes_run']})")

    context = {
        "run_started_at": started_at.isoformat(),
        "input_path": input_path,
        "threshold": threshold,
        "duration_seconds": duration,
        "tickets": total,
    }
    metrics["run_context"] = context
    markdown = generate_markdown_report(metrics, context, render_probes(probe_report))

    paths = {
        "processed": os.path.join(output_dir, "processed_tickets.json"),
        "metrics": os.path.join(output_dir, "metrics_report.json"),
        "report": os.path.join(output_dir, "metrics_report.md"),
    }
    with open(paths["processed"], "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    with open(paths["metrics"], "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)
    with open(paths["report"], "w", encoding="utf-8") as fh:
        fh.write(markdown)

    summary = metrics["summary"]
    status = metrics["status"]
    print()
    print("=" * 62)
    print("RESULT")
    print("=" * 62)
    print(f"  Tickets processed        {metrics['volume']['tickets_processed']}")
    print(f"  Answered automatically   {metrics['volume']['answered_automatically']}")
    print(f"  Escalated                {metrics['volume']['escalated_to_human']}")
    print(f"  Blocked by guardrails    {metrics['volume']['blocked_by_guardrails']}")
    print()
    for key, verdict in status.items():
        print(f"  [{verdict:4s}] {key}")
    print()
    print(f"  {summary['targets_met']} of {summary['targets_evaluated']} targets met, "
          f"{summary['targets_missed']} missed.")
    print("=" * 62)
    print(f"  Decisions:  {paths['processed']}")
    print(f"  Metrics:    {paths['metrics']}")
    print(f"  Report:     {paths['report']}")
    print(f"  Audit log:  {db_path}")
    print("=" * 62)

    # The run itself succeeded. A missed target is a finding to report, not a
    # failed run, so the exit code reflects whether the run completed rather
    # than whether the numbers were flattering.
    return {"exit_code": 0, "metrics": metrics}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CloudServe unattended evaluation harness")
    parser.add_argument("--input", required=True,
                        help="Path to the input JSON tickets file")
    parser.add_argument("--output", required=True,
                        help="Directory to write results into")
    parser.add_argument("--threshold", type=float,
                        default=float(os.getenv("CONFIDENCE_THRESHOLD",
                                                DEFAULT_CONFIDENCE_THRESHOLD)),
                        help="Automation-readiness threshold for auto-responding")
    parser.add_argument("--docs", default=None,
                        help="Override path to documentation.json")
    parser.add_argument("--dev", default=None,
                        help="Override path to development_tickets.json")
    args = parser.parse_args()

    outcome = run_evaluation(
        input_path=args.input,
        output_dir=args.output,
        threshold=args.threshold,
        docs_path=args.docs,
        dev_path=args.dev,
    )
    return outcome.get("exit_code", 0)


if __name__ == "__main__":
    sys.exit(main())
