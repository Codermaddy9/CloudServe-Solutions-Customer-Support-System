"""
FastAPI Service for CloudServe Support Automation.
Exposes endpoints for ticket processing, health check, metrics, and kill switch.
"""
import os
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from src.pipeline import SupportPipeline
from src.models import ProcessedTicketOutput


app = FastAPI(
    title="CloudServe Support Automation API",
    description="Intelligent Customer Support Pipeline with Ingest, Classify, Retrieve, Route, Guardrails, and Logging",
    version="1.0.0"
)

# Global pipeline instance
pipeline = SupportPipeline()


class TicketInput(BaseModel):
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


@app.get("/health")
def health_check():
    """Health check endpoint confirming API service status."""
    return {
        "status": "healthy",
        "service": "CloudServe Support Automation",
        "version": "1.0.0",
        "kill_switch_active": pipeline.guardrails.kill_switch
    }


@app.post("/ingest", response_model=ProcessedTicketOutput)
def ingest_ticket(ticket: TicketInput):
    """
    Ingests, classifies, retrieves, routes, generates, and validates a ticket.
    Logs decision to SQLite.
    """
    try:
        raw_dict = ticket.model_dump()
        result = pipeline.process_ticket(raw_dict)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
def get_metrics_summary():
    """Returns total logged decisions and reconciliation status."""
    total_decisions = pipeline.db.count_decisions()
    unique_tickets = pipeline.db.count_unique_tickets()
    return {
        "total_decisions_logged": total_decisions,
        "unique_tickets_processed": unique_tickets,
        "reconciliation_status": "PASS" if total_decisions >= unique_tickets else "MISMATCH"
    }


@app.post("/killswitch")
def toggle_kill_switch(req: KillSwitchRequest):
    """Activates or deactivates emergency kill switch."""
    pipeline.guardrails.kill_switch = req.active
    return {
        "status": "updated",
        "kill_switch_active": pipeline.guardrails.kill_switch,
        "message": "Emergency kill switch toggled."
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"Starting CloudServe Support API on http://0.0.0.0:{port}")
    uvicorn.run("src.api:app", host="0.0.0.0", port=port, reload=False)
