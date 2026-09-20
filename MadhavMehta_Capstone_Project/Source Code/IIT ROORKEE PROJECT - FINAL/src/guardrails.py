"""
Validation guardrails for CloudServe Support Automation.
Satisfies Acceptance Criterion A7.

Every generated response passes through `validate_response` before it can be
released, in the evaluation run exactly as in the API. There is no flag that
disables this path, because the Build Specification is explicit that a guardrail
present in the code but switched off during the run does not satisfy A7.

The Governance Framework sets the behaviour for each check. Note in particular
that private data is blocked and escalated rather than redacted and sent: a
response containing another customer's identifier is evidence that something
upstream went wrong, and quietly masking it would hide the fault while still
leaving the underlying error in place.
"""
import re
from typing import List, Optional, Tuple

from src.models import GuardrailResult, RetrievalResult

# Commitments the system is not authorised to make. Daniel Okonkwo, interview
# three: "Billing disputes, because those become contractual quickly and
# nothing automated should be making commitments about money."
PROHIBITED_CLAIMS = [
    (r"\ba refund (has been|will be) (issued|processed|applied)\b", "refund_commitment"),
    (r"\bwe (have|will) (issue|process|apply) (a|your) refund\b", "refund_commitment"),
    (r"\byou will be (refunded|credited|reimbursed)\b", "refund_commitment"),
    (r"\bwe have (disabled|removed|lifted) (all )?(your )?rate limits?\b", "limit_commitment"),
    (r"\b(your )?quota has been (increased|raised|lifted)\b", "limit_commitment"),
    (r"\b(direct )?database access (is|has been) granted\b", "access_commitment"),
    (r"\broot access (is|has been) granted\b", "access_commitment"),
    (r"\byour password is\b", "credential_disclosure"),
    (r"\b(the|my|our) system prompt is\b", "instruction_disclosure"),
    (r"\bthis will be (fixed|resolved|released) (by|on|in) \b", "timeline_commitment"),
    (r"\bwe guarantee\b", "guarantee_commitment"),
]

# Attempts to treat the ticket body as an instruction to the system.
PROMPT_INJECTION_PATTERNS = [
    (r"\bignore (all |any )?(the )?previous instructions?\b", "injection_ignore_previous"),
    (r"\bignore (the )?above instructions?\b", "injection_ignore_previous"),
    (r"\bdisregard (all |any )?(previous |prior )?(instructions?|directives?)\b",
     "injection_disregard"),
    (r"\bbypass (all |any )?(the )?guardrails?\b", "injection_bypass"),
    (r"\byou are now in (dan|developer|debug) mode\b", "injection_mode_switch"),
    (r"\bsystem prompt override\b", "injection_override"),
    (r"\b(reveal|disclose|print|show) (me )?(your |the )?system prompt\b",
     "injection_prompt_exfiltration"),
    (r"\bact as (if you are|an?) (unrestricted|jailbroken)\b", "injection_roleplay"),
]

# Private data patterns. These are conservative by design: a false positive
# costs one escalation, a false negative sends a customer's data to someone else.
PII_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "pii_national_insurance_or_ssn"),
    (r"\b(?:\d{4}[ -]?){3}\d{4}\b", "pii_payment_card"),
    (r"\b(?:sk|pk)-[a-zA-Z0-9]{16,}\b", "pii_api_secret"),
    (r"\bkey-[a-zA-Z0-9]{16,}\b", "pii_api_secret"),
    (r"\bBearer\s+[A-Za-z0-9\-._~+/]{20,}\b", "pii_bearer_token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "pii_private_key"),
]

ALL_CHECKS = [
    "kill_switch",
    "prohibited_claims",
    "private_data",
    "citation_grounding",
    "confidence_floor",
]


class GuardrailEngine:
    """
    Input and output validation. Both directions can block.

    The kill switch is held here rather than in the pipeline so that flipping it
    takes effect on the next response without a restart or a deployment, which
    is what the Governance Framework asks of it.
    """

    def __init__(self, kill_switch: bool = False):
        self.kill_switch = kill_switch

    # ------------------------------------------------------------------ input

    def validate_input(self, text: str) -> GuardrailResult:
        """
        Check an incoming ticket for attempts to redirect the system.

        The generator already separates instructions from ticket content, so
        this is defence in depth rather than the only barrier. It blocks
        because the Governance Framework requires the input to be recorded for
        review rather than quietly processed.
        """
        checks = ["prompt_injection"]
        lowered = text.lower()
        for pattern, rule in PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, lowered):
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    checks_performed=checks,
                    triggered_rules=[rule],
                    reason=(
                        "The ticket text contains an attempt to change the "
                        "system's instructions. It has been held for an agent "
                        "to review rather than answered automatically."
                    ),
                )
        return GuardrailResult(passed=True, blocked=False, checks_performed=checks)

    # ----------------------------------------------------------------- output

    def validate_response(
        self,
        response_text: str,
        retrieved_docs: List[RetrievalResult],
        claimed_citations: List[str],
        readiness_score: Optional[float] = None,
        threshold: Optional[float] = None,
    ) -> GuardrailResult:
        """
        Validate a drafted response before release.

        Runs every check and records all of them, then blocks if any fired.
        Checks are not short-circuited on the first failure because the decision
        log is more useful when it records everything that was wrong with a
        response rather than only the first thing noticed.
        """
        checks = list(ALL_CHECKS)
        triggered: List[str] = []
        reasons: List[str] = []
        pii_found = False

        # 1. Kill switch. Nothing goes out while it is engaged.
        if self.kill_switch:
            return GuardrailResult(
                passed=False,
                blocked=True,
                checks_performed=checks,
                triggered_rules=["kill_switch_active"],
                reason="Automated responding is suspended. The ticket has gone to an agent.",
            )

        lowered = response_text.lower()

        # 2. Commitments the system may not make.
        for pattern, rule in PROHIBITED_CLAIMS:
            if re.search(pattern, lowered):
                triggered.append(rule)
                reasons.append(
                    f"the draft makes a commitment the system is not authorised "
                    f"to make ({rule.replace('_', ' ')})"
                )
                break

        # 3. Private data. Block and escalate; never redact and send.
        for pattern, rule in PII_PATTERNS:
            if re.search(pattern, response_text):
                pii_found = True
                triggered.append(rule)
                reasons.append("the draft contains what looks like private or credential data")
                break

        # 4. Citation grounding. Every cited document must be one retrieval
        #    actually returned for this ticket.
        retrieved_ids = {d.doc_id for d in retrieved_docs}
        unsupported = [c for c in claimed_citations if c not in retrieved_ids]
        if unsupported:
            triggered.append("unsupported_citation")
            reasons.append(
                f"the draft cites {', '.join(unsupported)}, which retrieval did not return"
            )

        # 5. Confidence floor. A response that reached here without the
        #    threshold having been applied is a routing fault, not a close call.
        if readiness_score is not None and threshold is not None and readiness_score < threshold:
            triggered.append("confidence_floor_breach")
            reasons.append(
                f"the draft was produced at {readiness_score:.2f}, below the "
                f"{threshold:.2f} threshold, which should not happen"
            )

        if triggered:
            return GuardrailResult(
                passed=False,
                blocked=True,
                checks_performed=checks,
                triggered_rules=triggered,
                reason="Blocked before sending because " + "; and ".join(reasons) + ".",
                pii_detected=pii_found,
                unsupported_claims=unsupported,
            )

        return GuardrailResult(
            passed=True,
            blocked=False,
            checks_performed=checks,
            triggered_rules=[],
            pii_detected=False,
        )
