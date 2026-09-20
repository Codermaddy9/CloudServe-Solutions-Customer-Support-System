"""
Deterministic Routing Module for CloudServe Support Automation.
Satisfies Acceptance Criterion A5.

The router decides between answering automatically and escalating to a human.
It is deterministic by construction: every input to the decision is a value
computed upstream, there is no sampling, no clock and no randomness, so the
same ticket yields the same decision and the same stated reason every time.

The threshold is applied to the calibrated automation-readiness score rather
than to the intent classifier's probability. `evaluation/calibrate.py` records
why: the intent classifier's confidence carries an expected calibration error
of roughly 40 points and is close to uninformative about whether a ticket ought
to be automated at all. See `docs/architecture.md` section 4.
"""
from typing import List, Optional

from src.models import (
    ClassificationResult,
    NormalizedTicket,
    RetrievalResult,
    RoutingDecision,
)

# Intents CloudServe policy never permits an automated answer to.
#
# Derived from the development corpus rather than assumed: every ticket
# carrying these four intents is flagged `must_not_auto_respond` in the labels
# (26/26 compliance_request, 20/20 feature_request, 26/26 security_incident,
# 15/15 unclear_request). Daniel Okonkwo names the first and third of these
# directly in interview three. The figures are reproduced by
# `evaluation/discovery_analysis.py` under `never_automate_by_intent`.
MUST_NOT_AUTO_RESPOND_INTENTS = {
    "compliance_request",
    "feature_request",
    "security_incident",
    "unclear_request",
}

# Chosen by cost-minimisation over the development set; see
# evaluation/results/calibration.md section 5.
DEFAULT_CONFIDENCE_THRESHOLD = 0.45

# When a never-automate intent is the runner-up and sits this close to the top
# prediction, the classifier has not really distinguished between them and the
# ticket escalates.
#
# This exists because of a failure found in testing. "Could you add the ability
# to schedule recurring bulk exports?" was classified `billing_query` at 0.080
# with `feature_request` second at 0.067 — a gap of thirteen thousandths across
# twenty-two near-uniform classes. On the top prediction alone it would have
# been auto-answered, and a feature request has no documented answer to give:
# the corpus marks every one of them `answerable_from_docs: false`. Keying a
# safety rule to the single highest-scoring class assumes a separation the
# classifier does not provide on this kind of ticket.
NEVER_AUTOMATE_PROXIMITY = 0.80

# A retrieved passage below this similarity is treated as no grounding at all.
# Ines Varga's concern in interview four is that a wrong answer should be
# traceable to either a wrong article or a misread one; an answer grounded in a
# passage this weak is neither, so it is not sent.
MINIMUM_GROUNDING_SCORE = 0.12


class SupportRouter:
    """
    Applies the routing policy: hard governance rules first, then grounding,
    then the calibrated threshold.

    Order matters and is deliberate. A security incident is escalated because
    of what it is, not because the model happened to be unsure about it, and
    the recorded reason should say so.
    """

    def __init__(self, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD):
        self.confidence_threshold = confidence_threshold

    def route(
        self,
        ticket: NormalizedTicket,
        classification: ClassificationResult,
        retrieved_docs: List[RetrievalResult],
        readiness_score: Optional[float] = None,
    ) -> RoutingDecision:
        """
        Decide between `auto_respond` and `escalate`.

        `readiness_score` is the calibrated probability that this ticket can be
        resolved without a human. When it is absent the router treats it as
        zero and escalates: the Governance Framework is explicit that a missing
        confidence score is not a high one.
        """
        intent = classification.intent
        urgency = classification.urgency
        tier = ticket.customer_tier
        score = 0.0 if readiness_score is None else float(readiness_score)
        suggested_doc_ids = [d.doc_id for d in retrieved_docs]

        grounded = [d for d in retrieved_docs if d.score >= MINIMUM_GROUNDING_SCORE]

        # Rule 1 — governance policy. Certain intents never receive an
        # automated answer regardless of how confident the system is.
        if intent in MUST_NOT_AUTO_RESPOND_INTENTS:
            return self._escalate(
                ticket, classification, retrieved_docs, score,
                trigger="Governance policy",
                reason=(
                    f"CloudServe policy requires a human to handle "
                    f"'{intent.replace('_', ' ')}' tickets. This one was not "
                    f"considered for an automated answer."
                ),
                suggested_docs=suggested_doc_ids,
            )

        # Rule 1b — a never-automate intent was a close runner-up. The
        # classifier did not really separate the two, so a human decides.
        contender = self._close_never_automate_contender(classification)
        if contender:
            name, score = contender
            return self._escalate(
                ticket, classification, retrieved_docs, score,
                trigger="Possible policy intent",
                reason=(
                    f"This reads as '{intent.replace('_', ' ')}', but "
                    f"'{name.replace('_', ' ')}' scored almost as highly, and that "
                    f"category always goes to a person. The system could not tell "
                    f"the two apart confidently enough to answer it."
                ),
                suggested_docs=suggested_doc_ids,
            )

        # Rule 2 — no grounding. Retrieval found nothing it can stand behind,
        # so there is nothing to write an answer from.
        if not grounded:
            return self._escalate(
                ticket, classification, retrieved_docs, score,
                trigger="No documentation match",
                reason=(
                    "No support article matched this ticket closely enough to "
                    "base an answer on, so it has gone to an agent rather than "
                    "being answered from a weak match."
                ),
                suggested_docs=suggested_doc_ids,
            )

        # Rule 3 — the calibrated threshold.
        if score < self.confidence_threshold:
            return self._escalate(
                ticket, classification, retrieved_docs, score,
                trigger="Below automation threshold",
                reason=(
                    f"The system put the chance of resolving this without a "
                    f"person at {score:.0%}, below the {self.confidence_threshold:.0%} "
                    f"level CloudServe set for answering automatically."
                ),
                suggested_docs=suggested_doc_ids,
            )

        # Rule 4 — high-urgency enterprise infrastructure work. These carry a
        # different service agreement and the corpus shows enterprise tickets
        # already receive the slowest handling; an automated answer that turns
        # out to be wrong is most expensive here.
        if tier == "enterprise" and urgency == "high" and intent in (
            "deployment_failure", "database_issue", "performance_degradation"
        ):
            return self._escalate(
                ticket, classification, retrieved_docs, score,
                trigger="Enterprise priority",
                reason=(
                    "An urgent infrastructure problem on an enterprise account "
                    "goes straight to a Tier 2 engineer, with the draft answer "
                    "and sources attached."
                ),
                suggested_docs=suggested_doc_ids,
            )

        return RoutingDecision(
            decision="auto_respond",
            confidence=round(score, 4),
            reason=(
                f"The system put the chance of resolving this without a person "
                f"at {score:.0%}, at or above the {self.confidence_threshold:.0%} "
                f"level, and found {len(grounded)} supporting "
                f"article{'s' if len(grounded) != 1 else ''} to answer from."
            ),
            draft_summary=None,
            suggested_docs=suggested_doc_ids,
            threshold_applied=self.confidence_threshold,
            readiness_score=round(score, 4),
        )

    @staticmethod
    def _close_never_automate_contender(classification: ClassificationResult):
        """
        Return (intent, confidence) when a never-automate intent scored close
        enough to the top prediction to count as undistinguished from it.
        """
        alternatives = classification.alternatives_considered or []
        if len(alternatives) < 2:
            return None
        top = classification.intent_confidence
        if top <= 0:
            return None
        for alternative in alternatives[1:]:
            name = alternative.get("intent")
            score = float(alternative.get("confidence", 0.0))
            if name in MUST_NOT_AUTO_RESPOND_INTENTS and score >= top * NEVER_AUTOMATE_PROXIMITY:
                return name, score
        return None

    def _escalate(
        self,
        ticket: NormalizedTicket,
        classification: ClassificationResult,
        retrieved_docs: List[RetrievalResult],
        score: float,
        trigger: str,
        reason: str,
        suggested_docs: List[str],
    ) -> RoutingDecision:
        return RoutingDecision(
            decision="escalate",
            confidence=round(score, 4),
            reason=reason,
            draft_summary=self._generate_draft_summary(
                ticket, classification, retrieved_docs, trigger, reason),
            suggested_docs=suggested_docs,
            threshold_applied=self.confidence_threshold,
            readiness_score=round(score, 4),
            escalation_trigger=trigger,
        )

    def _generate_draft_summary(
        self,
        ticket: NormalizedTicket,
        classification: ClassificationResult,
        retrieved_docs: List[RetrievalResult],
        escalation_trigger: str,
        reason: str,
    ) -> str:
        """
        Build the handover brief that travels with an escalation.

        Daniel Okonkwo, interview three: "If an escalation arrived saying here
        is the ticket, here is what I think it is about, here is the
        documentation that seemed relevant, and here is specifically what I was
        not confident about, I would be twice as fast. I do not need it to be
        right. I need it to show its working."

        That last sentence is why the uncertainty line is present and why the
        alternatives the classifier considered are included rather than only
        the option it chose.
        """
        excerpt = ticket.body[:180].replace("\n", " ")
        if len(ticket.body) > 180:
            excerpt += "..."

        if retrieved_docs:
            docs_str = "\n".join(
                f"    - {d.doc_id} — {d.title} (match {d.score:.2f})"
                for d in retrieved_docs[:3]
            )
        else:
            docs_str = "    - None found"

        alternatives = classification.alternatives_considered[1:3]
        if alternatives:
            alt_str = ", ".join(
                f"{a['intent'].replace('_', ' ')} ({a['confidence']:.0%})"
                for a in alternatives
            )
        else:
            alt_str = "none close"

        return (
            f"ESCALATION BRIEF\n"
            f"  Customer:     {ticket.customer_name or ticket.customer_id or 'Unknown'} "
            f"({ticket.customer_tier})\n"
            f"  Channel:      {ticket.channel}   Urgency: {classification.urgency}\n"
            f"  Looks like:   {classification.intent.replace('_', ' ')}\n"
            f"  Also considered: {alt_str}\n"
            f"  Why you have it: {escalation_trigger} — {reason}\n"
            f"  Documentation that may help:\n{docs_str}\n"
            f"  Customer wrote: {excerpt}"
        )
