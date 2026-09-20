"""
Ingestion and normalisation for CloudServe Support Automation.
Satisfies Acceptance Criterion A2.

Four channels arrive in four shapes. This module flattens them into one
`NormalizedTicket` and keeps the original text and the original channel string,
because both matter downstream: the channel drives urgency expectations (Ravi
Menon waits differently for a pagination question than for a failing deploy)
and the original text is what the decision log has to be able to show.

Nothing in here raises. A malformed ticket produces a normalised object with
empty fields rather than an exception, so that one bad record in a file of a
hundred cannot end an unattended run.
"""
import html
import unicodedata
from typing import Any, Dict, Union

from src.models import NormalizedTicket

# Channel spellings seen across the four sources, mapped to the four canonical
# values. Unrecognised channels are preserved on `original_channel` and treated
# as email, which is the most permissive shape.
CHANNEL_MAPPINGS = {
    "email": "email",
    "mail": "email",
    "e-mail": "email",
    "chat": "chat",
    "live_chat": "chat",
    "livechat": "chat",
    "forum": "forum",
    "community": "forum",
    "community_forum": "forum",
    "docs_comment": "docs_comment",
    "documentation_comment": "docs_comment",
    "doc_comment": "docs_comment",
    "docs": "docs_comment",
}

CANONICAL_CHANNELS = {"email", "chat", "forum", "docs_comment"}
VALID_TIERS = {"standard", "business", "enterprise"}

# Bodies above this length are truncated before analysis. The longest genuine
# ticket in the development corpus is far below it; anything larger is a paste
# accident or an attack, and unbounded text would make latency unpredictable.
MAX_BODY_CHARS = 20_000


def sanitize_text(value: Any) -> str:
    """
    Normalise text from any channel.

    Unescapes HTML entities (forum and docs comments arrive encoded), applies
    NFKC normalisation so that visually identical characters compare equal, and
    strips control characters other than newline, tab and carriage return.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)

    value = html.unescape(value)
    value = unicodedata.normalize("NFKC", value)
    value = "".join(
        ch for ch in value
        if ch in ("\n", "\r", "\t") or unicodedata.category(ch)[0] != "C"
    )
    return value.strip()


def normalize_ticket(raw_ticket: Union[Dict[str, Any], Any]) -> NormalizedTicket:
    """
    Produce one internal representation from a ticket in any supported shape.

    Handles missing fields, unusual characters and empty bodies without failing,
    as A2 requires.
    """
    if not isinstance(raw_ticket, dict):
        raw_ticket = getattr(raw_ticket, "__dict__", {}) or {}

    ticket_id = str(raw_ticket.get("ticket_id") or "UNKNOWN-TICKET")

    raw_channel = str(raw_ticket.get("channel") or "email").lower().strip()
    channel = CHANNEL_MAPPINGS.get(raw_channel)
    if channel is None:
        channel = raw_channel if raw_channel in CANONICAL_CHANNELS else "email"

    subject = sanitize_text(raw_ticket.get("subject"))
    body = sanitize_text(raw_ticket.get("body"))
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS]

    tier = str(raw_ticket.get("customer_tier") or "standard").lower().strip()
    if tier not in VALID_TIERS:
        tier = "standard"

    def _optional(field: str):
        value = raw_ticket.get(field)
        return str(value) if value not in (None, "") else None

    return NormalizedTicket(
        ticket_id=ticket_id,
        channel=channel,
        original_channel=raw_channel,
        subject=subject,
        body=body,
        received_at=str(raw_ticket.get("received_at") or ""),
        customer_id=_optional("customer_id"),
        customer_name=_optional("customer_name"),
        customer_tier=tier,
        customer_region=_optional("customer_region"),
        language_fluency=_optional("language_fluency"),
        original_data=raw_ticket,
    )
