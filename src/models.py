"""
Data models and schemas for CloudServe Support Automation System.

One normalised representation flows through the whole pipeline. Channel-specific
detail is preserved on the ticket but never leaks into the components downstream
of ingestion, which is the failure mode the Project Brief warns about.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NormalizedTicket(BaseModel):
    """
    Normalised internal representation for incoming tickets across all four
    channels (email, chat, forum, docs_comment).
    Satisfies Acceptance Criterion A2.
    """
    ticket_id: str
    channel: str = Field(description="Normalised channel: email, chat, forum, docs_comment")
    original_channel: str = Field(default="", description="Channel string as received")
    subject: str = ""
    body: str = ""
    received_at: str = ""
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_tier: str = "standard"
    customer_region: Optional[str] = None
    language_fluency: Optional[str] = None
    original_data: Dict[str, Any] = Field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """Combined subject and body for text analysis."""
        parts = [p for p in (self.subject, self.body) if p]
        return "\n\n".join(parts).strip()


class ClassificationResult(BaseModel):
    """
    Intent and urgency with numeric confidence and the alternatives considered.
    Satisfies Acceptance Criterion A3.
    """
    intent: str
    intent_confidence: float = Field(ge=0.0, le=1.0)
    urgency: str  # low, medium, high
    urgency_confidence: float = Field(ge=0.0, le=1.0)
    alternatives_considered: List[Dict[str, Any]] = Field(default_factory=list)
    is_fallback: bool = Field(
        default=False,
        description="True when classification could not be performed and a defined "
                    "fallback was returned instead of raising.",
    )


class DocumentChunk(BaseModel):
    """A chunked passage from the knowledge base corpus."""
    doc_id: str
    chunk_id: str
    title: str
    category: str
    applies_to: str = ""
    content: str


class RetrievalResult(BaseModel):
    """
    A retrieved passage with its similarity score and an identifier that
    resolves back to the real corpus, so citations can be verified.
    Satisfies Acceptance Criterion A4.
    """
    doc_id: str
    chunk_id: str
    title: str
    score: float
    content: str


class RoutingDecision(BaseModel):
    """
    The routing outcome and, importantly, the reason for it in language a
    support manager could read.
    Satisfies Acceptance Criterion A5.
    """
    decision: str  # "auto_respond" or "escalate"
    confidence: float
    reason: str
    draft_summary: Optional[str] = None
    suggested_docs: List[str] = Field(default_factory=list)
    threshold_applied: float = 0.0
    readiness_score: float = 0.0
    escalation_trigger: Optional[str] = None


class GuardrailResult(BaseModel):
    """
    The outcome of a validation pass over a response.

    `checks_performed` is recorded whether or not anything fired, because the
    Build Specification requires the validator to record what it checked as
    well as what it found.
    Satisfies Acceptance Criterion A7.
    """
    passed: bool = True
    blocked: bool = False
    checks_performed: List[str] = Field(default_factory=list)
    triggered_rules: List[str] = Field(default_factory=list)
    reason: Optional[str] = None
    pii_detected: bool = False
    unsupported_claims: List[str] = Field(default_factory=list)


class ProcessedTicketOutput(BaseModel):
    """Full output for one ingested ticket."""
    ticket_id: str
    channel: str
    status: str  # "answered", "escalated", "blocked"
    routing: RoutingDecision
    classification: ClassificationResult
    retrieval_hits: List[RetrievalResult] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
    final_response: str
    guardrails: GuardrailResult
    latency_ms: float = 0.0
    generator_source: str = Field(
        default="none",
        description="Which generation path produced the text: 'provider', "
                    "'local_fallback', or 'none' for escalations and blocks.",
    )
    degraded: bool = Field(
        default=False,
        description="True when the ticket was handled on a degraded path, for "
                    "example after a provider failure or an internal exception.",
    )
