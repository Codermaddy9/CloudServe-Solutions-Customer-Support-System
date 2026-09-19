"""
Safety, PII, and Hallucination Guardrails for CloudServe Support Automation.
Satisfies Acceptance Criterion A7.
"""
import re
from typing import List, Optional
from src.models import GuardrailResult, RetrievalResult


PROHIBITED_CLAIMS = [
    r"a refund has been issued",
    r"refund has been processed",
    r"your password is",
    r"we have disabled (all )?rate limits",
    r"direct database access is granted",
    r"root access has been granted",
    r"system prompt is"
]

PROMPT_INJECTION_PATTERNS = [
    r"ignore (all )?previous instructions",
    r"ignore above instructions",
    r"disregard previous directives",
    r"bypass (all )?guardrails",
    r"you are now in dan mode",
    r"system prompt override"
]

SSN_REGEX = r"\b\d{3}-\d{2}-\d{4}\b"
CREDIT_CARD_REGEX = r"\b(?:\d{4}[ -]?){3}\d{4}\b"
SECRET_KEY_REGEX = r"\b(?:sk-[a-zA-Z0-9]{20,}|key-[a-zA-Z0-9]{16,})\b"


class GuardrailEngine:
    """
    Validates inputs and generated outputs before release.
    Capable of actively blocking unsafe responses and redacting PII.
    """
    def __init__(self, kill_switch: bool = False):
        self.kill_switch = kill_switch

    def validate_input(self, text: str) -> GuardrailResult:
        """Checks incoming customer ticket for prompt injection or abusive attacks."""
        lower = text.lower()
        for pattern in PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, lower):
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    triggered_rules=["prompt_injection_detected"],
                    reason="Input contains adversarial prompt injection attempt."
                )
        return GuardrailResult(passed=True, blocked=False)

    def validate_response(
        self,
        response_text: str,
        retrieved_docs: List[RetrievalResult],
        claimed_citations: List[str]
    ) -> GuardrailResult:
        """
        Validates response text before delivery.
        Checks for:
        1. Kill switch activation
        2. Prohibited / hallucinated business claims
        3. PII / sensitive data leaks (SSN, credit card, exposed API keys)
        4. Citations not present in retrieved knowledge base passages
        """
        if self.kill_switch:
            return GuardrailResult(
                passed=False,
                blocked=True,
                triggered_rules=["kill_switch_active"],
                reason="System kill switch is active. All automated outputs suspended."
            )

        triggered_rules = []
        lower_resp = response_text.lower()

        # 1. Check for prohibited unsafe claims (hallucinations)
        for pat in PROHIBITED_CLAIMS:
            if re.search(pat, lower_resp):
                triggered_rules.append("prohibited_claim_detected")
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    triggered_rules=triggered_rules,
                    reason=f"Blocked: Generated text contains prohibited unsupported claim matching pattern '{pat}'."
                )

        # 2. Check for PII / credentials in output
        pii_detected = False
        redacted = response_text

        if re.search(SSN_REGEX, response_text):
            triggered_rules.append("pii_ssn_detected")
            pii_detected = True
            redacted = re.sub(SSN_REGEX, "[REDACTED-SSN]", redacted)

        if re.search(CREDIT_CARD_REGEX, response_text):
            triggered_rules.append("pii_credit_card_detected")
            pii_detected = True
            redacted = re.sub(CREDIT_CARD_REGEX, "[REDACTED-CARD]", redacted)

        if re.search(SECRET_KEY_REGEX, response_text):
            triggered_rules.append("sensitive_api_key_detected")
            pii_detected = True
            redacted = re.sub(SECRET_KEY_REGEX, "[REDACTED-KEY]", redacted)

        # 3. Check citation grounding
        retrieved_doc_ids = set(d.doc_id for d in retrieved_docs)
        for cite in claimed_citations:
            if cite not in retrieved_doc_ids:
                triggered_rules.append("unsupported_citation")
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    triggered_rules=triggered_rules,
                    reason=f"Blocked: Cited document {cite} was not in the verified retrieval set."
                )

        # If severe PII was exposed (like credit card or SSN), block the response
        if "pii_ssn_detected" in triggered_rules or "pii_credit_card_detected" in triggered_rules:
            return GuardrailResult(
                passed=False,
                blocked=True,
                triggered_rules=triggered_rules,
                reason="Blocked: Response contained sensitive personal financial/identity data.",
                pii_detected=True,
                redacted_text=redacted
            )

        return GuardrailResult(
            passed=True,
            blocked=False,
            triggered_rules=triggered_rules,
            pii_detected=pii_detected,
            redacted_text=redacted if pii_detected else None
        )
