"""
Unattended Evaluation Harness for CloudServe Support Automation.
Satisfies Acceptance Criteria A9 and A10.

Usage:
    python -m evaluation.harness --input 05_Datasets/validation_tickets.json --output evaluation/results/
"""
import os
import sys
import json
import argparse
import time
from typing import List, Dict, Any

# Ensure project root is in python path when executed directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.pipeline import SupportPipeline
from evaluation.metrics import calculate_metrics, generate_markdown_report


def run_evaluation(input_path: str, output_dir: str, threshold: float = 0.60):
    """
    Runs the full unattended evaluation on any ticket dataset provided via input_path.
    Generates outputs, logs decisions, and writes metric reports to output_dir.
    """
    print(f"==================================================")
    print(f"CloudServe Support Automation — Unattended Evaluation")
    print(f"Input file:  {input_path}")
    print(f"Output dir:  {output_dir}")
    print(f"Threshold:   {threshold}")
    print(f"==================================================")

    if not os.path.exists(input_path):
        print(f"ERROR: Input dataset not found at '{input_path}'", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    with open(input_path, "r", encoding="utf-8") as f:
        raw_tickets: List[Dict[str, Any]] = json.load(f)

    total = len(raw_tickets)
    print(f"[1/4] Loaded {total} tickets for processing.")

    # Initialize pipeline with fresh storage DB for this run
    db_path = os.path.join(output_dir, "evaluation_decisions.db")
    pipeline = SupportPipeline(
        db_path=db_path,
        confidence_threshold=threshold
    )

    print(f"[2/4] Processing all {total} tickets unattended...")
    processed_results = []
    start_time = time.time()

    for idx, raw_ticket in enumerate(raw_tickets, start=1):
        # Process each ticket without human intervention
        output = pipeline.process_ticket(raw_ticket)
        processed_results.append(output.model_dump())

        if idx % 20 == 0 or idx == total:
            print(f"      Processed {idx}/{total} tickets ({(idx/total)*100:.0f}%)")

    total_time = round(time.time() - start_time, 2)
    print(f"[3/4] Batch completed in {total_time}s ({round(total_time/total*1000, 1)}ms/ticket average).")

    # Reconcile database records against tickets processed (Criterion A8)
    reconciliation = pipeline.db.reconcile(total)
    print(f"      Decision Log Reconciliation: {reconciliation['status']} ({reconciliation['unique_tickets_logged']}/{total} tickets logged)")

    # Calculate Volume, Business, Technical, Governance metrics (Criterion A10)
    print(f"[4/4] Computing metrics and generating reports...")
    metrics = calculate_metrics(processed_results, raw_tickets, reconciliation)
    markdown_report = generate_markdown_report(metrics)

    # Save output artifacts
    processed_file = os.path.join(output_dir, "processed_tickets.json")
    metrics_file = os.path.join(output_dir, "metrics_report.json")
    report_file = os.path.join(output_dir, "metrics_report.md")

    with open(processed_file, "w", encoding="utf-8") as f:
        json.dump(processed_results, f, indent=2)

    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(markdown_report)

    print(f"\nResults successfully written to:")
    print(f"  • Processed tickets: {processed_file}")
    print(f"  • Metrics JSON:      {metrics_file}")
    print(f"  • Markdown Report:   {report_file}")
    print(f"\n" + "="*50)
    print(f"EVALUATION SUMMARY")
    print(f"="*50)
    print(f"• Total Tickets:          {metrics['volume']['total_tickets_processed']}")
    print(f"• First Contact Res (FCR): {metrics['business']['first_contact_resolution_rate_pct']}% (Target: ≥60%)")
    print(f"• Escalation Rate:        {metrics['business']['escalation_rate_pct']}% (Target: ≤35%)")
    print(f"• Classification Accuracy:{metrics['technical']['classification_accuracy_pct']}%")
    print(f"• Retrieval Hit Rate:     {metrics['technical']['retrieval_hit_rate_pct']}%")
    print(f"• Citation Accuracy:      {metrics['technical']['citation_accuracy_pct']}%")
    print(f"• Hallucination Rate:     {metrics['technical']['hallucination_rate_pct']}%")
    print(f"• Decisions Reconciled:   {metrics['governance']['reconciliation_status']}")
    print(f"="*50 + "\n")


def main():
    parser = argparse.ArgumentParser(description="CloudServe Unattended Evaluation Harness")
    parser.add_argument("--input", required=True, help="Path to input JSON tickets file")
    parser.add_argument("--output", required=True, help="Directory to save evaluation results")
    parser.add_argument("--threshold", type=float, default=0.60, help="Confidence threshold for auto-response")
    args = parser.parse_args()

    run_evaluation(input_path=args.input, output_dir=args.output, threshold=args.threshold)


if __name__ == "__main__":
    main()
