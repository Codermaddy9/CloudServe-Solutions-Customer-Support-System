"""
SQLite Decision Logger for CloudServe Support Automation.
Satisfies Acceptance Criterion A8 and Governance Framework.
"""
import os
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


class DecisionDatabase:
    """
    Persistent SQLite logger ensuring every automated decision is audited,
    persisted, and reconcilable against tickets processed.
    """
    def __init__(self, db_path: str = "storage/decisions.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates decisions table schema if not already present."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    ticket_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    input_summary TEXT,
                    model_name TEXT,
                    model_version TEXT,
                    prediction_value TEXT,
                    prediction_confidence REAL,
                    alternatives_json TEXT,
                    sources_used_json TEXT,
                    threshold_applied REAL,
                    action_taken TEXT NOT NULL,
                    reason TEXT,
                    guardrail_results_json TEXT,
                    prompt_version TEXT,
                    requirement_ids_json TEXT,
                    raw_json TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ticket_id ON decisions(ticket_id)")
            conn.commit()

    def log_decision(
        self,
        ticket_id: str,
        stage: str,
        action_taken: str,
        reason: str,
        prediction_value: str,
        prediction_confidence: float,
        input_summary: str = "",
        model_name: str = "CloudServe-Classifier/Retriever",
        model_version: str = "1.0.0",
        alternatives: Optional[List[Dict[str, Any]]] = None,
        sources_used: Optional[List[Dict[str, Any]]] = None,
        threshold_applied: float = 0.80,
        guardrail_results: Optional[Dict[str, Any]] = None,
        prompt_version: str = "PR-02 v1.3",
        requirement_ids: Optional[List[str]] = None
    ) -> str:
        """Records a single audit record into SQLite following governance schema."""
        decision_id = f"DEC-{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat()

        record = {
            "decision_id": decision_id,
            "timestamp": timestamp,
            "ticket_id": ticket_id,
            "stage": stage,
            "input_summary": input_summary[:200],
            "model": {"name": model_name, "version": model_version},
            "prediction": {"value": prediction_value, "confidence": round(prediction_confidence, 4)},
            "alternatives": alternatives or [],
            "sources_used": sources_used or [],
            "threshold_applied": threshold_applied,
            "action_taken": action_taken,
            "reason": reason,
            "guardrail_results": guardrail_results or {"status": "passed"},
            "prompt_version": prompt_version,
            "requirement_ids": requirement_ids or ["FR-01", "FR-02"]
        }

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO decisions (
                    decision_id, timestamp, ticket_id, stage, input_summary,
                    model_name, model_version, prediction_value, prediction_confidence,
                    alternatives_json, sources_used_json, threshold_applied,
                    action_taken, reason, guardrail_results_json, prompt_version,
                    requirement_ids_json, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                decision_id,
                timestamp,
                ticket_id,
                stage,
                record["input_summary"],
                model_name,
                model_version,
                prediction_value,
                prediction_confidence,
                json.dumps(record["alternatives"]),
                json.dumps(record["sources_used"]),
                threshold_applied,
                action_taken,
                reason,
                json.dumps(record["guardrail_results"]),
                prompt_version,
                json.dumps(record["requirement_ids"]),
                json.dumps(record)
            ))
            conn.commit()

        return decision_id

    def count_decisions(self) -> int:
        """Returns total decisions logged."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM decisions")
            return cursor.fetchone()[0]

    def count_unique_tickets(self) -> int:
        """Returns count of distinct tickets logged."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(DISTINCT ticket_id) FROM decisions")
            return cursor.fetchone()[0]

    def reconcile(self, tickets_processed_count: int) -> Dict[str, Any]:
        """
        Reconciles decisions against processed tickets.
        Checks Criterion A8 requirement that decisions reconcile with tickets processed.
        """
        unique_tickets = self.count_unique_tickets()
        total_decisions = self.count_decisions()
        reconciled = unique_tickets == tickets_processed_count

        return {
            "reconciled": reconciled,
            "tickets_processed": tickets_processed_count,
            "unique_tickets_logged": unique_tickets,
            "total_decisions_logged": total_decisions,
            "status": "PASS" if reconciled else "MISMATCH"
        }
