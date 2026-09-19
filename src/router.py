"""
Deterministic Routing Module for CloudServe Support Automation.
Satisfies Acceptance Criterion A5.
"""
from typing import List, Optional
from src.models import NormalizedTicket, ClassificationResult, RetrievalResult, RoutingDecision


# Intents that CloudServe policy strictly prohibits auto-responding to
MUST_NOT_AUTO_RESPOND_INTENTS = {
    "compliance_request",
    "feature_request",
    "security_incident",
    "unclear_request"
}


class SupportRouter:
    """
    Applies deterministic routing policy based on confidence threshold,
    retrieval grounding, and governance risk rules.
    """
    def __init__(self, confidence_threshold: float = 0.80):
        self.confidence_threshold = confidence_threshold

    def route(
        self,
        ticket: NormalizedTicket,
        classification: ClassificationResult,
        retrieved_docs: List[RetrievalResult]
    ) -> RoutingDecision:
        """
        Deterministically decides whether to auto_respond or escalate.
        Run the same ticket twice: the decision and reasoning will be identical.
        """
        intent = classification.intent
        confidence = classification.intent_confidence
        urgency = classification.urgency
        tier = ticket.customer_tier
        suggested_doc_ids = [d.doc_id for d in retrieved_docs]

        # Rule 1: Mandatory governance escalation
        if intent in MUST_NOT_AUTO_RESPOND_INTENTS:
            return RoutingDecision(
                decision="escalate",
                confidence=confidence,
                reason=f"Policy requires manual handling: intent '{intent}' cannot be auto-responded.",
                draft_summary=self._generate_draft_summary(ticket, classification, retrieved_docs, "Governance Policy"),
                suggested_docs=suggested_doc_ids
            )

        # Rule 2: Low confidence below threshold
        if confidence < self.confidence_threshold:
            return RoutingDecision(
                decision="escalate",
                confidence=confidence,
                reason=f"Intent confidence ({confidence:.2f}) is below automation threshold ({self.confidence_threshold:.2f}).",
                draft_summary=self._generate_draft_summary(ticket, classification, retrieved_docs, "Low Confidence"),
                suggested_docs=suggested_doc_ids
            )

        # Rule 3: No knowledge base grounding
        if not retrieved_docs:
            return RoutingDecision(
                decision="escalate",
                confidence=confidence,
                reason="No matching documentation found to ground an automated answer.",
                draft_summary=self._generate_draft_summary(ticket, classification, retrieved_docs, "Missing Grounding"),
                suggested_docs=[]
            )

        # Rule 4: Critical enterprise production outages
        if tier == "enterprise" and urgency == "high" and intent in ("deployment_failure", "database_issue"):
            return RoutingDecision(
                decision="escalate",
                confidence=confidence,
                reason="High-urgency enterprise outage requires priority Tier-2 engineering review.",
                draft_summary=self._generate_draft_summary(ticket, classification, retrieved_docs, "Enterprise Urgent SLA"),
                suggested_docs=suggested_doc_ids
            )

        # Approved for automated resolution
        return RoutingDecision(
            decision="auto_respond",
            confidence=confidence,
            reason=f"High-confidence match ({confidence:.2f} >= {self.confidence_threshold:.2f}) with {len(retrieved_docs)} verified documentation source(s).",
            draft_summary=None,
            suggested_docs=suggested_doc_ids
        )

    def _generate_draft_summary(
        self,
        ticket: NormalizedTicket,
        classification: ClassificationResult,
        retrieved_docs: List[RetrievalResult],
        escalation_trigger: str
    ) -> str:
        """Generates structured context summary to assist the human support agent."""
        excerpt = ticket.body[:180].replace("\n", " ") + ("..." if len(ticket.body) > 180 else "")
        docs_str = ", ".join([f"{d.doc_id} ({d.title})" for d in retrieved_docs[:2]]) if retrieved_docs else "None"
        
        return (
            f"[ESCALATION BRIEF]\n"
            f"• Customer: {ticket.customer_name or ticket.customer_id or 'Unknown'} ({ticket.customer_tier.upper()})\n"
            f"• Channel: {ticket.channel.upper()} | Urgency: {classification.urgency.upper()}\n"
            f"• Issue Identified: {classification.intent.replace('_', ' ').title()} (Conf: {classification.intent_confidence:.2f})\n"
            f"• Trigger: {escalation_trigger}\n"
            f"• Suggested Docs: {docs_str}\n"
            f"• Summary: {excerpt}"
        )
