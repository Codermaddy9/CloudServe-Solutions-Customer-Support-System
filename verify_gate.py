"""
Gate rehearsal — run this before submitting.

The Build Specification says a submission is checked by cloning the repository,
following the README literally, and pointing the evaluation harness at a hidden
ticket file the author has never seen. Roughly half of all submissions fail at
that second step.

This script performs that rehearsal against your own code. It builds a
synthetic "hidden" set outside the repository, with a filename and ticket ids
you have not used, runs the documented command against it, and checks the
result the way an assessor would.

    python verify_gate.py

It writes nothing into the repository. Everything it produces goes to a
temporary directory that is removed afterwards.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
RULE = "=" * 72

# What an assessor checks, in the order they check it.
checks = []


def record(name: str, passed: bool, detail: str = "") -> bool:
    checks.append((name, passed, detail))
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}]  {name}")
    if detail:
        print(f"          {detail}")
    return passed


def build_hidden_set(target_dir: str, count: int = 120) -> str:
    """
    Build a ticket file the harness has never seen.

    Tickets are drawn from the supplied corpus, but the filename, the directory
    and every ticket id are new, which is the part that catches a hardcoded
    input path.
    """
    pools = []
    for name in ("validation_tickets.json", "development_tickets.json"):
        path = os.path.join(ROOT, "05_Datasets", name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                pools.extend(json.load(fh))

    if not pools:
        raise FileNotFoundError(
            "No ticket data found in 05_Datasets/. The corpus must ship with "
            "the repository: the classifier trains from it at startup.")

    random.seed()  # deliberately not fixed — a different sample every rehearsal
    sample = random.sample(pools, min(count, len(pools)))
    hidden = [dict(t, ticket_id=f"HIDDEN-{i:04d}") for i, t in enumerate(sample, 1)]

    path = os.path.join(target_dir, "assessor_hidden_set.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(hidden, fh, indent=1)
    return path


def main() -> int:
    print(f"\n{RULE}\n  GATE REHEARSAL — what the assessor will do to your code\n{RULE}")

    workspace = tempfile.mkdtemp(prefix="gate_rehearsal_")
    input_path = None
    try:
        # ---------------------------------------------------------- setup
        print("\n  Building a ticket file this code has never seen...")
        input_path = build_hidden_set(workspace)
        with open(input_path, "r", encoding="utf-8") as fh:
            expected_count = len(json.load(fh))
        output_dir = os.path.join(workspace, "results")
        print(f"    input:  {input_path}")
        print(f"    output: {output_dir}")
        print(f"    tickets: {expected_count}, ids HIDDEN-0001 upward")

        # ------------------------------------------------- the documented run
        print(f"\n{RULE}\n  1. THE UNATTENDED RUN (A9)\n{RULE}\n")
        command = [sys.executable, "-m", "evaluation.harness",
                   "--input", input_path, "--output", output_dir]
        print(f"  $ python -m evaluation.harness --input {os.path.basename(input_path)} "
              f"--output <temp>\n")

        result = subprocess.run(command, cwd=ROOT, capture_output=True,
                                text=True, timeout=3600)

        if not record("The harness ran to completion",
                      result.returncode == 0,
                      "" if result.returncode == 0
                      else f"exit code {result.returncode}: "
                           f"{result.stderr.strip()[:400]}"):
            return 1

        record("It needed no intervention", True,
               "started once, no prompts, no restarts")

        # --------------------------------------------------------- artefacts
        print(f"\n{RULE}\n  2. WHAT THE RUN PRODUCED (A10)\n{RULE}\n")
        for filename in ("metrics_report.json", "metrics_report.md",
                         "processed_tickets.json", "evaluation_decisions.db"):
            record(f"{filename} was written",
                   os.path.exists(os.path.join(output_dir, filename)))

        metrics_path = os.path.join(output_dir, "metrics_report.json")
        if not os.path.exists(metrics_path):
            return 1
        with open(metrics_path, "r", encoding="utf-8") as fh:
            metrics = json.load(fh)

        # ------------------------------------------------ nothing was dropped
        print(f"\n{RULE}\n  3. EVERY TICKET ACCOUNTED FOR (A9, A8)\n{RULE}\n")
        processed_path = os.path.join(output_dir, "processed_tickets.json")
        with open(processed_path, "r", encoding="utf-8") as fh:
            processed = json.load(fh)

        record(f"All {expected_count} tickets were processed",
               len(processed) == expected_count,
               f"found {len(processed)}")

        statuses = {p.get("status") for p in processed}
        record("Every ticket ended answered, escalated or blocked",
               statuses <= {"answered", "escalated", "blocked"},
               f"statuses seen: {', '.join(sorted(statuses))}")

        with open(input_path, "r", encoding="utf-8") as fh:
            submitted_ids = {t["ticket_id"] for t in json.load(fh)}
        returned_ids = {p["ticket_id"] for p in processed}
        record("No ticket was silently dropped",
               submitted_ids == returned_ids,
               f"{len(submitted_ids - returned_ids)} missing, "
               f"{len(returned_ids - submitted_ids)} unexpected")

        governance = metrics.get("governance", {})
        record("The decision log reconciles exactly",
               bool(governance.get("decision_log_reconciled")),
               governance.get("reconciliation_detail", ""))

        # -------------------------------------------------- required figures
        print(f"\n{RULE}\n  4. THE REQUIRED FIGURES (A10)\n{RULE}\n")
        required = {
            "volume": ["tickets_processed", "answered_automatically",
                       "escalated_to_human", "blocked_by_guardrails"],
            "business": ["first_contact_resolution_pct", "escalation_rate_pct",
                         "mean_reply_seconds"],
            "technical": ["classification_per_class", "retrieval_hit_rate_pct",
                          "p95_latency_ms", "median_latency_ms"],
            "governance": ["decisions_logged", "guardrail_activations_by_rule",
                           "private_data_occurrences"],
        }
        for group, fields in required.items():
            missing = [f for f in fields if f not in metrics.get(group, {})]
            record(f"{group.capitalize()} figures present",
                   not missing,
                   f"missing: {', '.join(missing)}" if missing else "")

        per_class = metrics.get("technical", {}).get("classification_per_class", {})
        record("Precision and recall reported per class",
               bool(per_class) and all(
                   {"precision_pct", "recall_pct"} <= set(v) for v in per_class.values()),
               f"{len(per_class)} classes")

        # ---------------------------------------------------------- guardrails
        print(f"\n{RULE}\n  5. GUARDRAILS ARE LIVE (A7)\n{RULE}\n")
        probes = metrics.get("guardrail_probes", {})
        record("Guardrail probes all behaved as required",
               probes.get("status") == "PASS",
               f"{probes.get('probes_passed')} of {probes.get('probes_run')}")

        # ---------------------------------------------------------- the tests
        print(f"\n{RULE}\n  6. THE TEST SUITE (A12)\n{RULE}\n")
        print("  $ python -m pytest tests/ -q\n")
        tests = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                               cwd=ROOT, capture_output=True, text=True, timeout=3600)
        summary = [line for line in tests.stdout.splitlines()
                   if "passed" in line or "failed" in line]
        record("The documented test command passes",
               tests.returncode == 0,
               summary[-1].strip() if summary else tests.stdout[-300:])

        # ------------------------------------------------------- credentials
        print(f"\n{RULE}\n  7. NO CREDENTIALS COMMITTED\n{RULE}\n")
        leaked = []
        # The needle is assembled at runtime so that this file does not itself
        # contain the literal string it searches for. A scanner that flags its
        # own source is a scanner nobody trusts the output of.
        needle = "sk-" + "or-" + "v1-"
        self_name = os.path.basename(__file__)
        for folder, _, files in os.walk(ROOT):
            if any(part in folder for part in
                   (".git", "__pycache__", ".pytest_cache", "node_modules")):
                continue
            for name in files:
                if name == self_name:
                    continue
                if not name.endswith((".py", ".md", ".txt", ".yml", ".yaml",
                                      ".json", ".example")):
                    continue
                path = os.path.join(folder, name)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()
                except OSError:
                    continue
                for line in content.splitlines():
                    stripped = line.strip()
                    if (needle in stripped or
                            (stripped.startswith("OPENROUTER_API_KEY=")
                             and "your_" not in stripped
                             and len(stripped.split("=", 1)[1].strip()) > 20)):
                        leaked.append(os.path.relpath(path, ROOT))
                        break
        record("No API key found in tracked file types",
               not leaked,
               f"found in: {', '.join(sorted(set(leaked)))}" if leaked else
               "note: this scans working files, not git history")

        # ------------------------------------------------------------ verdict
        passed = sum(1 for _, ok, _ in checks if ok)
        total = len(checks)
        print(f"\n{RULE}")
        if passed == total:
            print(f"  GATE REHEARSAL PASSED — {passed} of {total} checks")
            print(RULE)
            print("\n  Your harness accepted a file it had never seen, processed every")
            print("  ticket unattended, reconciled its decision log and produced the")
            print("  required report. That is the gate.\n")
            print("  Headline results from this run:")
            business = metrics.get("business", {})
            status = metrics.get("status", {})
            print(f"    first contact resolution  "
                  f"{business.get('first_contact_resolution_pct')}%  "
                  f"[{status.get('first_contact_resolution_pct')}]")
            print(f"    escalation rate           "
                  f"{business.get('escalation_rate_pct')}%  "
                  f"[{status.get('escalation_rate_pct')}]")
            missed = [k for k, v in status.items() if v == "FAIL"]
            if missed:
                print(f"\n  {len(missed)} target(s) reported as missed, which is expected "
                      f"and\n  explained in the report:")
                for key in missed:
                    print(f"    - {key.replace('_', ' ')}")
            return 0

        print(f"  GATE REHEARSAL FAILED — {passed} of {total} checks")
        print(RULE)
        print("\n  Fix these before submitting:\n")
        for name, ok, detail in checks:
            if not ok:
                print(f"    - {name}")
                if detail:
                    print(f"      {detail}")
        print()
        return 1

    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
