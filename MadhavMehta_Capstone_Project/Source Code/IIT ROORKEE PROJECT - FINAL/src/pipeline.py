"""
Support pipeline coordinator for CloudServe Support Automation.

Sequences ingest, classify, retrieve, score, route, generate, validate and log.
Every path through this method writes exactly one decision record and returns a
`ProcessedTicketOutput`, which is what allows A8 reconciliation to be a real
check rather than a formality: logged decisions and processed tickets must come
out equal, and any path that took a decision without recording it would show up
immediately as a gap.
"""
import os
import time
from typing import Any, Dict, Optional

from src.automation_readiness import AutomationReadinessScorer
from src.classifier import TicketClassifier
from src.db import DecisionDatabase
from src.generator import ResponseGenerator
from src.guardrails import GuardrailEngine
from src.ingestion import normalize_ticket
from src.models import (
    ClassificationResult,
    GuardrailResult,
    ProcessedTicketOutput,
    RoutingDecision,
)
from src.retrieval import KnowledgeBaseRetriever
from src.router import DEFAULT_CONFIDENCE_THRESHOLD, SupportRouter

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB_PATH = os.path.join(_PROJECT_ROOT, "storage", "decisions.db")

PROMPT_VERSION = "PR-02 v2.0"
REQUIREMENT_IDS = ["FR-01", "FR-02", "FR-03", "FR-04", "FR-05", "FR-06", "FR-07"]


class SupportPipeline:
    """End-to-end processing for one ticket at a time."""

    def __init__(
        self,
        docs_path: Optional[str] = None,
        dev_path: Optional[str] = None,
        db_path: Optional[str] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        kill_switch: bool = False,
        retrieval_top_k: int = 3,
    ):
        self.retriever = KnowledgeBaseRetriever(docs_path=docs_path)
        self.classifier = TicketClassifier(dev_tickets_path=dev_path)
        self.readiness = AutomationReadinessScorer(dev_tickets_path=dev_path)
        self.router = SupportRouter(confidence_threshold=confidence_threshold)
        self.generator = ResponseGenerator()
        self.guardrails = GuardrailEngine(kill_switch=kill_switch)
        self.db = DecisionDatabase(db_path=db_path or _DEFAULT_DB_PATH)
        self.confidence_threshold = confidence_threshold
        self.retrieval_top_k = retrieval_top_k

    def process_ticket(self, raw_ticket: Dict[str, Any]) -> ProcessedTicketOutput:
        """
        Run one ticket through the pipeline.

        Never raises. Acceptance Criterion A11 requires the system to degrade
        and continue rather than stop, and A9 requires an unattended run over a
        file we have never seen, so a single malformed record must not be able
        to end the run.
        """
        started = time.time()

        try:
            # 1. Ingest and normalise (A2)
            ticket = normalize_ticket(raw_ticket)

            # 2. Input validation (A7)
            input_guard = self.guardrails.validate_input(ticket.full_text)

            # 3. Classify (A3)
            classification = self.classifier.classify(ticket)

            if input_guard.blocked:
                return self._finish(
                    ticket=ticket,
                    status="blocked",
                    classification=classification,
                    retrieval_hits=[],
                    routing=RoutingDecision(
                        decision="escalate",
                        confidence=0.0,
                        reason=input_guard.reason or "Blocked by input validation.",
                        threshold_applied=self.confidence_threshold,
                        escalation_trigger="Input validation",
                        draft_summary=(
                            "ESCALATION BRIEF\n"
                            f"  Customer:     {ticket.customer_name or ticket.customer_id or 'Unknown'} "
                            f"({ticket.customer_tier})\n"
                            f"  Channel:      {ticket.channel}\n"
                            "  Why you have it: Input validation — the ticket text tries to "
                            "change the system's instructions.\n"
                            f"  Customer wrote: {ticket.body[:180]}"
                        ),
                    ),
                    citations=[],
                    response=(
                        "This ticket has been held for an agent to review before any "
                        "automated reply is sent."
                    ),
                    guard=input_guard,
                    started=started,
                    generator_source="none",
                )

            # 4. Retrieve (A4)
            retrieval_hits = self.retriever.retrieve(
                ticket.full_text, top_k=self.retrieval_top_k)

            # 5. Score automation readiness, then route (A5)
            readiness_score = self.readiness.score(ticket)
            routing = self.router.route(
                ticket, classification, retrieval_hits, readiness_score=readiness_score)

            if routing.decision != "auto_respond":
                return self._finish(
                    ticket=ticket,
                    status="escalated",
                    classification=classification,
                    retrieval_hits=retrieval_hits,
                    routing=routing,
                    citations=routing.suggested_docs,
                    response=routing.draft_summary or routing.reason,
                    guard=GuardrailResult(passed=True, blocked=False,
                                          checks_performed=["not_applicable_escalated"]),
                    started=started,
                    generator_source="none",
                )

            # 6. Generate a grounded answer (A6)
            generated, citations, source = self.generator.generate(
                ticket, retrieval_hits, classification)

            # 7. Validate before release (A7)
            output_guard = self.guardrails.validate_response(
                generated,
                retrieval_hits,
                citations,
                readiness_score=readiness_score,
                threshold=self.confidence_threshold,
            )

            if output_guard.blocked:
                return self._finish(
                    ticket=ticket,
                    status="blocked",
                    classification=classification,
                    retrieval_hits=retrieval_hits,
                    routing=routing,
                    citations=citations,
                    response=(
                        "The drafted reply was withheld and the ticket sent to an "
                        f"agent. {output_guard.reason}"
                    ),
                    guard=output_guard,
                    started=started,
                    generator_source=source,
                )

            return self._finish(
                ticket=ticket,
                status="answered",
                classification=classification,
                retrieval_hits=retrieval_hits,
                routing=routing,
                citations=citations,
                response=generated,
                guard=output_guard,
                started=started,
                generator_source=source,
                degraded=(source == "local_fallback"),
            )

        except Exception as exc:  # noqa: BLE001 — A11 requires no escape hatch
            return self._finish_exception(raw_ticket, exc, started)

    # ------------------------------------------------------------------ internals

    def _finish(
        self,
        ticket,
        status: str,
        classification: ClassificationResult,
        retrieval_hits,
        routing: RoutingDecision,
        citations,
        response: str,
        guard: GuardrailResult,
        started: float,
        generator_source: str,
        degraded: bool = False,
    ) -> ProcessedTicketOutput:
        """Write the decision record and assemble the output. One record per ticket."""
        latency = round((time.time() - started) * 1000, 2)
        action = "block" if status == "blocked" else routing.decision

        self.db.log_decision(
            ticket_id=ticket.ticket_id,
            stage="routing_and_generation",
            action_taken=action,
            reason=guard.reason if status == "blocked" else routing.reason,
            prediction_value=classification.intent,
            prediction_confidence=classification.intent_confidence,
            readiness_score=routing.readiness_score,
            input_summary=ticket.full_text[:200],
            alternatives=classification.alternatives_considered,
            sources_used=[{"doc_id": h.doc_id, "chunk_id": h.chunk_id, "score": h.score}
                          for h in retrieval_hits],
            threshold_applied=self.confidence_threshold,
            guardrail_results={
                "passed": guard.passed,
                "blocked": guard.blocked,
                "checks_performed": guard.checks_performed,
                "triggered_rules": guard.triggered_rules,
                "pii_detected": guard.pii_detected,
            },
            prompt_version=PROMPT_VERSION,
            requirement_ids=REQUIREMENT_IDS,
            channel=ticket.channel,
            customer_tier=ticket.customer_tier,
            language_fluency=ticket.language_fluency,
            latency_ms=latency,
            degraded=degraded,
        )

        return ProcessedTicketOutput(
            ticket_id=ticket.ticket_id,
            channel=ticket.channel,
            status=status,
            routing=routing,
            classification=classification,
            retrieval_hits=retrieval_hits,
            citations=citations,
            final_response=response,
            guardrails=guard,
            latency_ms=latency,
            generator_source=generator_source,
            degraded=degraded,
        )

    def _finish_exception(self, raw_ticket: Any, exc: Exception,
                          started: float) -> ProcessedTicketOutput:
        """
        Last-resort handler (A11).

        Something unanticipated went wrong. The ticket still produces a logged
        decision and an escalation rather than disappearing, because A9 requires
        that no ticket is silently dropped.
        """
        latency = round((time.time() - started) * 1000, 2)
        if isinstance(raw_ticket, dict):
            ticket_id = str(raw_ticket.get("ticket_id") or "UNKNOWN-TICKET")
            channel = str(raw_ticket.get("channel") or "email")
            tier = str(raw_ticket.get("customer_tier") or "standard")
        else:
            ticket_id, channel, tier = "UNKNOWN-TICKET", "email", "standard"

        detail = f"{type(exc).__name__}: {exc}"

        try:
            self.db.log_decision(
                ticket_id=ticket_id,
                stage="fallback_recovery",
                action_taken="escalate",
                reason=f"Handled on the degraded path after an internal error. {detail}",
                prediction_value="system_exception_fallback",
                prediction_confidence=0.0,
                readiness_score=0.0,
                input_summary="Exception raised during processing",
                threshold_applied=self.confidence_threshold,
                guardrail_results={"passed": True, "blocked": False,
                                   "checks_performed": ["not_applicable_exception"],
                                   "triggered_rules": [], "pii_detected": False},
                prompt_version=PROMPT_VERSION,
                requirement_ids=REQUIREMENT_IDS,
                channel=channel,
                customer_tier=tier,
                latency_ms=latency,
                degraded=True,
            )
        except Exception:  # noqa: BLE001 — logging must not turn into a second failure
            pass

        return ProcessedTicketOutput(
            ticket_id=ticket_id,
            channel=channel,
            status="escalated",
            routing=RoutingDecision(
                decision="escalate",
                confidence=0.0,
                reason=f"Sent to an agent after an internal error. {detail}",
                threshold_applied=self.confidence_threshold,
                escalation_trigger="Internal error",
                draft_summary=(
                    "ESCALATION BRIEF\n"
                    "  Why you have it: Internal error — the system could not process "
                    f"this ticket automatically ({detail}).\n"
                    "  No automated analysis is available for this one."
                ),
            ),
            classification=ClassificationResult(
                intent="unclear_request",
                intent_confidence=0.0,
                urgency="medium",
                urgency_confidence=0.0,
                is_fallback=True,
            ),
            retrieval_hits=[],
            citations=[],
            final_response="This ticket has been passed to an agent for manual review.",
            guardrails=GuardrailResult(passed=True, blocked=False,
                                       checks_performed=["not_applicable_exception"]),
            latency_ms=latency,
            generator_source="none",
            degraded=True,
        )
