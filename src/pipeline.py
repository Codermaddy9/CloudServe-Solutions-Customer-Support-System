"""
Support Pipeline Coordinator for CloudServe Automation System.
Brings together Ingest, Classify, Retrieve, Route, Generate, Guardrail, and Log.
"""
import time
from typing import Dict, Any, Optional
from src.models import NormalizedTicket, ProcessedTicketOutput, GuardrailResult
from src.ingestion import normalize_ticket
from src.classifier import TicketClassifier
from src.retrieval import KnowledgeBaseRetriever
from src.router import SupportRouter
from src.generator import ResponseGenerator
from src.guardrails import GuardrailEngine
from src.db import DecisionDatabase


class SupportPipeline:
    """
    End-to-end processing pipeline for CloudServe tickets.
    """
    def __init__(
        self,
        docs_path: Optional[str] = None,
        dev_path: Optional[str] = None,
        db_path: str = "storage/decisions.db",
        confidence_threshold: float = 0.80,
        kill_switch: bool = False
    ):
        self.retriever = KnowledgeBaseRetriever(docs_path=docs_path)
        self.classifier = TicketClassifier(dev_tickets_path=dev_path)
        self.router = SupportRouter(confidence_threshold=confidence_threshold)
        self.generator = ResponseGenerator()
        self.guardrails = GuardrailEngine(kill_switch=kill_switch)
        self.db = DecisionDatabase(db_path=db_path)
        self.confidence_threshold = confidence_threshold

    def process_ticket(self, raw_ticket: Dict[str, Any]) -> ProcessedTicketOutput:
        """
        Executes complete pipeline on a single ticket.
        Never throws uncaught exceptions (Graceful handling A11).
        """
        t0 = time.time()
        
        try:
            # 1. Ingest & Normalize (A2)
            ticket = normalize_ticket(raw_ticket)

            # 2. Input Guardrail Check (A7)
            input_guard = self.guardrails.validate_input(ticket.full_text)
            if input_guard.blocked:
                latency = round((time.time() - t0) * 1000, 2)
                self.db.log_decision(
                    ticket_id=ticket.ticket_id,
                    stage="validation",
                    action_taken="block",
                    reason=input_guard.reason or "Blocked by input guardrail",
                    prediction_value="blocked_input",
                    prediction_confidence=1.0,
                    input_summary=ticket.full_text[:200],
                    guardrail_results={"input_check": "blocked", "rule": input_guard.triggered_rules}
                )
                return ProcessedTicketOutput(
                    ticket_id=ticket.ticket_id,
                    channel=ticket.channel,
                    status="blocked",
                    routing=self.router.route(ticket, self.classifier.classify(ticket), []),
                    classification=self.classifier.classify(ticket),
                    retrieval_hits=[],
                    citations=[],
                    final_response=f"Security Alert: {input_guard.reason}",
                    guardrails=input_guard,
                    latency_ms=latency
                )

            # 3. Classify Intent and Urgency (A3)
            classification = self.classifier.classify(ticket)

            # 4. Retrieve Knowledge Base Passages (A4)
            retrieval_hits = self.retriever.retrieve(ticket.full_text, top_k=3)

            # 5. Route Decision (A5)
            routing = self.router.route(ticket, classification, retrieval_hits)

            citations = []
            final_response = ""
            status = "answered"
            output_guard = GuardrailResult(passed=True, blocked=False)

            if routing.decision == "auto_respond":
                # 6. Generate Response Grounded in Retrieval (A6, A11)
                gen_text, gen_citations = self.generator.generate(ticket, retrieval_hits, classification)
                citations = gen_citations

                # 7. Output Guardrail Validation (A7)
                output_guard = self.guardrails.validate_response(gen_text, retrieval_hits, citations)
                if output_guard.blocked:
                    status = "blocked"
                    final_response = f"Response blocked by safety policy: {output_guard.reason}"
                elif output_guard.redacted_text:
                    final_response = output_guard.redacted_text
                else:
                    final_response = gen_text
            else:
                # Escalated
                status = "escalated"
                final_response = routing.draft_summary or f"Escalated to human support: {routing.reason}"
                citations = routing.suggested_docs

            latency = round((time.time() - t0) * 1000, 2)

            # 8. Persistent Decision Logging (A8)
            action_taken = "block" if status == "blocked" else routing.decision
            self.db.log_decision(
                ticket_id=ticket.ticket_id,
                stage="routing_and_generation",
                action_taken=action_taken,
                reason=output_guard.reason if status == "blocked" else routing.reason,
                prediction_value=classification.intent,
                prediction_confidence=classification.intent_confidence,
                input_summary=ticket.full_text[:200],
                alternatives=classification.alternatives_considered,
                sources_used=[{"doc_id": h.doc_id, "score": h.score} for h in retrieval_hits],
                threshold_applied=self.confidence_threshold,
                guardrail_results={
                    "passed": output_guard.passed,
                    "blocked": output_guard.blocked,
                    "triggered_rules": output_guard.triggered_rules,
                    "pii_detected": output_guard.pii_detected
                },
                prompt_version="PR-02 v1.3",
                requirement_ids=["FR-01", "FR-02", "FR-03", "FR-05"]
            )

            return ProcessedTicketOutput(
                ticket_id=ticket.ticket_id,
                channel=ticket.channel,
                status=status,
                routing=routing,
                classification=classification,
                retrieval_hits=retrieval_hits,
                citations=citations,
                final_response=final_response,
                guardrails=output_guard,
                latency_ms=latency
            )

        except Exception as e:
            # Acceptance Criterion A11: Failure handling without crashing
            latency = round((time.time() - t0) * 1000, 2)
            ticket_id = raw_ticket.get("ticket_id", "ERROR-TICKET") if isinstance(raw_ticket, dict) else "ERROR-TICKET"
            channel = raw_ticket.get("channel", "email") if isinstance(raw_ticket, dict) else "email"
            
            # Log failure decision
            self.db.log_decision(
                ticket_id=ticket_id,
                stage="fallback_recovery",
                action_taken="escalate",
                reason=f"Graceful degradation on exception: {str(e)}",
                prediction_value="system_exception_fallback",
                prediction_confidence=0.0,
                input_summary="Exception during processing"
            )
            
            from src.models import RoutingDecision, ClassificationResult
            return ProcessedTicketOutput(
                ticket_id=ticket_id,
                channel=channel,
                status="escalated",
                routing=RoutingDecision(
                    decision="escalate",
                    confidence=0.0,
                    reason=f"Graceful fallback to Tier-2 on exception: {str(e)}"
                ),
                classification=ClassificationResult(
                    intent="unclear_request",
                    intent_confidence=0.0,
                    urgency="medium",
                    urgency_confidence=0.5
                ),
                retrieval_hits=[],
                citations=[],
                final_response=f"Ticket has been escalated to Tier-2 engineering for manual review.",
                guardrails=GuardrailResult(passed=True, blocked=False),
                latency_ms=latency
            )
