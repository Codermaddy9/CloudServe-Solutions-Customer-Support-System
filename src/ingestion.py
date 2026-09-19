"""
Ingestion and normalization module for CloudServe Support Automation.
Satisfies Acceptance Criterion A2.
"""
from typing import Dict, Any, Union
import html
import unicodedata
from src.models import NormalizedTicket


CHANNEL_MAPPINGS = {
    "email": "email",
    "mail": "email",
    "chat": "chat",
    "live_chat": "chat",
    "forum": "forum",
    "community": "forum",
    "community_forum": "forum",
    "docs_comment": "docs_comment",
    "documentation_comment": "docs_comment",
    "doc_comment": "docs_comment",
    "web_form": "forum",  # Map web form/portal to forum or standard channel
    "portal": "forum"
}


def sanitize_text(text: Any) -> str:
    """Sanitizes text, normalizes unicode, handles unusual characters."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    
    # Unescape HTML entities if any
    text = html.unescape(text)
    
    # Normalize unicode to NFKC
    text = unicodedata.normalize("NFKC", text)
    
    # Strip null bytes and non-printable control characters (except newline, tab, carriage return)
    cleaned_chars = [
        c for c in text
        if c in ("\n", "\r", "\t") or (unicodedata.category(c)[0] != "C")
    ]
    return "".join(cleaned_chars).strip()


def normalize_ticket(raw_ticket: Union[Dict[str, Any], Any]) -> NormalizedTicket:
    """
    Normalizes a ticket from any of the four channels into a unified NormalizedTicket.
    Handles missing fields, unusual characters, and empty bodies without crashing.
    """
    if not isinstance(raw_ticket, dict):
        # Fallback if raw object has attribute access or is malformed
        raw_ticket = getattr(raw_ticket, "__dict__", {})

    ticket_id = str(raw_ticket.get("ticket_id") or "UNKNOWN-TICKET")
    
    # Channel normalization
    raw_channel = str(raw_ticket.get("channel", "email")).lower().strip()
    normalized_channel = CHANNEL_MAPPINGS.get(raw_channel, "email")
    
    subject = sanitize_text(raw_ticket.get("subject", ""))
    body = sanitize_text(raw_ticket.get("body", ""))
    received_at = str(raw_ticket.get("received_at", ""))
    
    customer_id = raw_ticket.get("customer_id")
    customer_name = raw_ticket.get("customer_name")
    
    # Customer tier normalization
    customer_tier = str(raw_ticket.get("customer_tier", "standard")).lower().strip()
    if customer_tier not in ("standard", "business", "enterprise"):
        customer_tier = "standard"
        
    customer_region = raw_ticket.get("customer_region")
    language_fluency = raw_ticket.get("language_fluency")

    return NormalizedTicket(
        ticket_id=ticket_id,
        channel=normalized_channel,
        subject=subject,
        body=body,
        received_at=received_at,
        customer_id=customer_id,
        customer_name=customer_name,
        customer_tier=customer_tier,
        customer_region=customer_region,
        language_fluency=language_fluency,
        original_data=raw_ticket
    )
