"""
SQLite decision log for CloudServe Support Automation.
Satisfies Acceptance Criterion A8 and the Governance Framework's logging schema.

Marcus Adeyemi, interview one: "I have a compliance review in the autumn, so
whatever we do has to be explainable. I need to be able to say why it did what
it did." Every field below exists so that question can be answered months later
by somebody who was not there, including which prompt version and which
requirement produced the behaviour.
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# The full expected schema, as (column, SQL type). This list is the single
# source of truth: it is used both to create the table and to detect an older
# table that is missing columns.
EXPECTED_COLUMNS = [
    ("decision_id", "TEXT"),
    ("timestamp", "TEXT"),
    ("ticket_id", "TEXT"),
    ("stage", "TEXT"),
    ("input_summary", "TEXT"),
    ("channel", "TEXT"),
    ("customer_tier", "TEXT"),
    ("language_fluency", "TEXT"),
    ("model_name", "TEXT"),
    ("model_version", "TEXT"),
    ("prediction_value", "TEXT"),
    ("prediction_confidence", "REAL"),
    ("readiness_score", "REAL"),
    ("alternatives_json", "TEXT"),
    ("sources_used_json", "TEXT"),
    ("threshold_applied", "REAL"),
    ("action_taken", "TEXT"),
    ("reason", "TEXT"),
    ("guardrail_results_json", "TEXT"),
    ("prompt_version", "TEXT"),
    ("requirement_ids_json", "TEXT"),
    ("latency_ms", "REAL"),
    ("degraded", "INTEGER"),
    ("raw_json", "TEXT"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id            TEXT PRIMARY KEY,
    timestamp              TEXT NOT NULL,
    ticket_id              TEXT NOT NULL,
    stage                  TEXT NOT NULL,
    input_summary          TEXT,
    channel                TEXT,
    customer_tier          TEXT,
    language_fluency       TEXT,
    model_name             TEXT,
    model_version          TEXT,
    prediction_value       TEXT,
    prediction_confidence  REAL,
    readiness_score        REAL,
    alternatives_json      TEXT,
    sources_used_json      TEXT,
    threshold_applied      REAL,
    action_taken           TEXT NOT NULL,
    reason                 TEXT,
    guardrail_results_json TEXT,
    prompt_version         TEXT,
    requirement_ids_json   TEXT,
    latency_ms             REAL,
    degraded               INTEGER DEFAULT 0,
    raw_json               TEXT
);
CREATE INDEX IF NOT EXISTS idx_ticket_id ON decisions(ticket_id);
CREATE INDEX IF NOT EXISTS idx_action ON decisions(action_taken);
"""


class DecisionDatabase:
    """
    Append-only audit log.

    `reset` exists because the evaluation harness starts each run from an empty
    log. Without it a second run into the same output directory would leave
    decision counts at twice the ticket count, and the A8 reconciliation check
    would be comparing against a total that includes a previous run.
    """

    def __init__(self, db_path: Optional[str] = None, reset: bool = False):
        if db_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(project_root, "storage", "decisions.db")
        self.db_path = db_path

        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)

        if reset and os.path.exists(db_path):
            os.remove(db_path)

        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """
        Create the table if it is absent, then bring an older one up to date.

        `CREATE TABLE IF NOT EXISTS` silently does nothing when a table already
        exists, even if that table has a different shape. A decision log written
        by an earlier version of this system therefore survives an upgrade with
        its old columns, and every insert against it fails.

        That is not hypothetical — it happened. Because the pipeline catches
        every exception (A11), the failure did not crash anything: it quietly
        routed every ticket down the degraded path with "table decisions has no
        column named channel" as the reason. A system designed never to fall
        over will hide a fault like this rather than announce it, which is why
        the migration below exists and why `schema_migrations_applied` is
        reported rather than performed silently.
        """
        self.schema_migrations_applied: List[str] = []
        with self._connect() as conn:
            conn.executescript(SCHEMA)

            existing = {row["name"] for row in
                        conn.execute("PRAGMA table_info(decisions)").fetchall()}
            for column, sql_type in EXPECTED_COLUMNS:
                if column not in existing:
                    # SQLite permits adding a nullable column to a populated
                    # table, so existing audit records are preserved rather than
                    # discarded. Losing a decision log to an upgrade would be a
                    # governance failure in its own right.
                    conn.execute(
                        f"ALTER TABLE decisions ADD COLUMN {column} {sql_type}")
                    self.schema_migrations_applied.append(column)
            conn.commit()

    def schema_is_current(self) -> bool:
        """True when the table on disk has every column this version writes."""
        with self._connect() as conn:
            existing = {row["name"] for row in
                        conn.execute("PRAGMA table_info(decisions)").fetchall()}
        return all(column in existing for column, _ in EXPECTED_COLUMNS)

    def log_decision(
        self,
        ticket_id: str,
        stage: str,
        action_taken: str,
        reason: str,
        prediction_value: str,
        prediction_confidence: float,
        readiness_score: float = 0.0,
        input_summary: str = "",
        model_name: str = "tfidf-logreg-classifier + isotonic-readiness",
        model_version: str = "2.0.0",
        alternatives: Optional[List[Dict[str, Any]]] = None,
        sources_used: Optional[List[Dict[str, Any]]] = None,
        threshold_applied: float = 0.0,
        guardrail_results: Optional[Dict[str, Any]] = None,
        prompt_version: str = "PR-02 v2.0",
        requirement_ids: Optional[List[str]] = None,
        channel: Optional[str] = None,
        customer_tier: Optional[str] = None,
        language_fluency: Optional[str] = None,
        latency_ms: float = 0.0,
        degraded: bool = False,
    ) -> str:
        """Write one audit record. Returns its identifier."""
        decision_id = f"DEC-{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat()

        record = {
            "decision_id": decision_id,
            "timestamp": timestamp,
            "ticket_id": ticket_id,
            "stage": stage,
            "input_summary": (input_summary or "")[:200],
            "model": {"name": model_name, "version": model_version},
            "prediction": {"value": prediction_value,
                           "confidence": round(prediction_confidence, 4)},
            "readiness_score": round(readiness_score, 4),
            "alternatives": alternatives or [],
            "sources_used": sources_used or [],
            "threshold_applied": threshold_applied,
            "action_taken": action_taken,
            "reason": reason,
            "guardrail_results": guardrail_results or {},
            "prompt_version": prompt_version,
            "requirement_ids": requirement_ids or [],
            "segment": {"channel": channel, "customer_tier": customer_tier,
                        "language_fluency": language_fluency},
            "latency_ms": latency_ms,
            "degraded": degraded,
        }

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO decisions (
                    decision_id, timestamp, ticket_id, stage, input_summary,
                    channel, customer_tier, language_fluency,
                    model_name, model_version, prediction_value, prediction_confidence,
                    readiness_score, alternatives_json, sources_used_json,
                    threshold_applied, action_taken, reason, guardrail_results_json,
                    prompt_version, requirement_ids_json, latency_ms, degraded, raw_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    decision_id, timestamp, ticket_id, stage, record["input_summary"],
                    channel, customer_tier, language_fluency,
                    model_name, model_version, prediction_value, prediction_confidence,
                    readiness_score,
                    json.dumps(record["alternatives"]),
                    json.dumps(record["sources_used"]),
                    threshold_applied, action_taken, reason,
                    json.dumps(record["guardrail_results"]),
                    prompt_version, json.dumps(record["requirement_ids"]),
                    latency_ms, 1 if degraded else 0,
                    json.dumps(record),
                ),
            )
            conn.commit()

        return decision_id

    # ---------------------------------------------------------------- queries

    def count_decisions(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]

    def count_unique_tickets(self) -> int:
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(DISTINCT ticket_id) FROM decisions").fetchone()[0]

    def count_by_action(self) -> Dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT action_taken, COUNT(*) c FROM decisions GROUP BY action_taken"
            ).fetchall()
        return {r["action_taken"]: r["c"] for r in rows}

    def tickets_with_multiple_decisions(self) -> int:
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM (SELECT ticket_id FROM decisions "
                "GROUP BY ticket_id HAVING COUNT(*) > 1)"
            ).fetchone()[0]

    def reconcile(self, tickets_processed_count: int) -> Dict[str, Any]:
        """
        Check the log against the run.

        Three things must hold for A8: one record per ticket, no ticket logged
        twice, and no ticket missing. Reporting only the distinct count would
        hide a duplicate, so the total is checked as well.
        """
        unique = self.count_unique_tickets()
        total = self.count_decisions()
        duplicates = self.tickets_with_multiple_decisions()

        reconciled = (
            unique == tickets_processed_count
            and total == tickets_processed_count
            and duplicates == 0
        )

        if reconciled:
            detail = (f"{total} decisions recorded for {tickets_processed_count} "
                      f"tickets, one each.")
        else:
            detail = (f"Expected {tickets_processed_count} decisions for "
                      f"{tickets_processed_count} tickets; found {total} decisions "
                      f"across {unique} distinct tickets "
                      f"({duplicates} ticket(s) logged more than once).")

        return {
            "reconciled": reconciled,
            "tickets_processed": tickets_processed_count,
            "unique_tickets_logged": unique,
            "total_decisions_logged": total,
            "tickets_logged_more_than_once": duplicates,
            "decisions_by_action": self.count_by_action(),
            "status": "PASS" if reconciled else "MISMATCH",
            "detail": detail,
        }
