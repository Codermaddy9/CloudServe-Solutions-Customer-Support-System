"""
Data models and schemas for CloudServe Support Automation System.
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class NormalizedTicket(BaseModel):
    """
    Normalised internal representation for incoming tickets across all channels
    (email, chat, forum, web_form).
    Satisfies Acceptance Criterion A2.
    """
    ticket_id: str
    channel: str = Field(description="Normalized channel: email, chat, forum, web_form")
    subject: str = ""
    body: str = ""
    received_at: str = ""
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_tier: str = "standard"  # standard, business, enterprise
    customer_region: Optional[str] = None
    language_fluency: Optional[str] = None
    original_data: Dict[str, Any] = Field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """Combined subject and body for text analysis."""
        parts = []
        if self.subject:
            parts.append(self.subject)
        if self.body:
            parts.append(self.body)
        return "\n\n".join(parts).strip()


class ClassificationResult(BaseModel):
    """
    Intent and urgency classification with confidence and alternative considerations.
    Satisfies Acceptance Criterion A3.
    """
    intent: str
    intent_confidence: float = Field(ge=0.0, le=1.0)
    urgency: str  # low, medium, high, critical
    urgency_confidence: float = Field(ge=0.0, le=1.0)
    alternatives_considered: List[Dict[str, Any]] = Field(default_factory=list)


class DocumentChunk(BaseModel):
    """
    Chunked passage from knowledge base documentation.
    Satisfies Acceptance Criterion A4.
    """
    doc_id: str
    chunk_id: str
    title: str
    category: str
    applies_to: str = ""
    content: str


class RetrievalResult(BaseModel):
    """
    Retrieved document passage with similarity score and citation reference.
    Satisfies Acceptance Criterion A4.
    """
    doc_id: str
    chunk_id: str
    title: str
    score: float
    content: str


class RoutingDecision(BaseModel):
    """
    Routing outcome: either auto_respond or escalate.
    Satisfies Acceptance Criterion A5.
    """
    decision: str  # "auto_respond" or "escalate"
    confidence: float
    reason: str
    draft_summary: Optional[str] = None
    suggested_docs: List[str] = Field(default_factory=list)


class GuardrailResult(BaseModel):
    """
    Safety, PII, and citation validation checks.
    Satisfies Acceptance Criterion A7.
    """
    passed: bool = True
    blocked: bool = False
    triggered_rules: List[str] = Field(default_factory=list)
    reason: Optional[str] = None
    pii_detected: bool = False
    redacted_text: Optional[str] = None


class ProcessedTicketOutput(BaseModel):
    """
    Full output generated for an ingested ticket.
    Satisfies Acceptance Criteria A6, A7, A8, A9.
    """
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
