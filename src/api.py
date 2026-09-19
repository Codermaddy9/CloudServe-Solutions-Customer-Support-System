"""
FastAPI service for CloudServe Support Automation.

The API and the evaluation harness share one `SupportPipeline`, so a ticket
submitted here goes through exactly the same ingest, classification, retrieval,
routing, generation, validation and logging path that the unattended run uses.
There is no separate demonstration mode and no flag that relaxes the guardrails.
"""
import os
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from src.models import ProcessedTicketOutput
from src.pipeline import SupportPipeline
from src.router import DEFAULT_CONFIDENCE_THRESHOLD

app = FastAPI(
    title="CloudServe Support Automation",
    description=(
        "Ingests support tickets from four channels, classifies them, retrieves "
        "supporting documentation, decides whether to answer or escalate, drafts "
        "a cited answer, validates it before release, and logs every decision."
    ),
    version="2.0.0",
)

pipeline = SupportPipeline(
    confidence_threshold=float(
        os.getenv("CONFIDENCE_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD))
)


class TicketInput(BaseModel):
    """A ticket from any of the four channels. Only `body` is really required."""
    ticket_id: Optional[str] = None
    channel: str = "email"
    subject: str = ""
    body: str = ""
    received_at: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_tier: str = "standard"
    customer_region: Optional[str] = None
    language_fluency: Optional[str] = None


class KillSwitchRequest(BaseModel):
    active: bool
    operator: Optional[str] = None
    reason: Optional[str] = None


@app.get("/health")
def health() -> Dict[str, Any]:
    """Service health, plus the state of everything the pipeline depends on."""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "kill_switch_active": pipeline.guardrails.kill_switch,
        "confidence_threshold": pipeline.confidence_threshold,
        "corpus_chunks_indexed": len(pipeline.retriever.chunks),
        "classifier_trained": pipeline.classifier.is_trained,
        "readiness_model_trained": pipeline.readiness.is_trained,
        "model_provider_configured": pipeline.generator._provider_configured(),
    }


@app.post("/ingest", response_model=ProcessedTicketOutput)
def ingest(ticket: TicketInput) -> ProcessedTicketOutput:
    """
    Process one ticket end to end.

    Returns 200 in every case, including failure. A ticket that cannot be
    processed comes back as an escalation with the reason attached, because a
    500 would leave the caller with a ticket and no record of what happened to
    it, and A11 requires the system to degrade rather than stop.
    """
    return pipeline.process_ticket(ticket.model_dump())


@app.get("/metrics")
def metrics() -> Dict[str, Any]:
    """Decision log totals and reconciliation state."""
    total = pipeline.db.count_decisions()
    unique = pipeline.db.count_unique_tickets()
    return {
        "total_decisions_logged": total,
        "unique_tickets_logged": unique,
        "decisions_by_action": pipeline.db.count_by_action(),
        "tickets_logged_more_than_once": pipeline.db.tickets_with_multiple_decisions(),
    }


@app.post("/killswitch")
def killswitch(request: KillSwitchRequest) -> Dict[str, Any]:
    """
    Stop or resume automated responding.

    Takes effect on the next response with no restart and no deployment. While
    it is engaged every drafted response is blocked by the guardrail engine and
    the ticket goes to a human, so nothing is dropped.
    """
    pipeline.guardrails.kill_switch = request.active
    pipeline.db.log_decision(
        ticket_id="SYSTEM",
        stage="kill_switch",
        action_taken="block" if request.active else "auto_respond",
        reason=(f"Kill switch {'engaged' if request.active else 'released'} by "
                f"{request.operator or 'unidentified operator'}. "
                f"Reason given: {request.reason or 'none'}."),
        prediction_value="kill_switch",
        prediction_confidence=1.0,
    )
    return {
        "kill_switch_active": pipeline.guardrails.kill_switch,
        "effective": "immediately, on the next response",
        "tickets_in_flight": "complete their current step, then escalate rather than send",
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"CloudServe Support Automation API on http://127.0.0.1:{port}")
    print(f"Interactive documentation at http://127.0.0.1:{port}/docs")
    uvicorn.run("src.api:app", host="127.0.0.1", port=port, reload=False)
