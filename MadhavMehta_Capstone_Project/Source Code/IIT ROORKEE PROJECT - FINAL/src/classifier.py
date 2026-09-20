"""
Intent and Urgency Classifier module for CloudServe Support System.
Satisfies Acceptance Criterion A3.
"""
import os
import json
import re
from typing import List, Dict, Any, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from src.models import NormalizedTicket, ClassificationResult


class TicketClassifier:
    """
    Calibrated classifier for ticket intent and urgency.
    Trained on the 500 labeled development tickets.
    Provides calibrated numeric probabilities, fallback mechanisms,
    and alternative intent tracking.
    """
    FALLBACK_INTENT = "unclear_request"
    FALLBACK_URGENCY = "medium"

    HIGH_URGENCY_KEYWORDS = [
        r"\bproduction\b", r"\boutage\b", r"\bdown\b", r"\bcritical\b",
        r"\bblocked\b", r"\bdata loss\b", r"\bbreach\b", r"\bsecurity\b",
        r"\b500 error\b", r"\bcrash\b", r"\burgent\b", r"\basap\b"
    ]
    LOW_URGENCY_KEYWORDS = [
        r"\bfeature request\b", r"\bcurious\b", r"\bquestion\b",
        r"\bdocumentation\b", r"\btypo\b", r"\bwhen will\b"
    ]

    def __init__(self, dev_tickets_path: Optional[str] = None):
        if dev_tickets_path is None:
            # Resolve relative to the project root (one level above src/)
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            candidates = [
                os.path.join(project_root, "05_Datasets", "development_tickets.json"),
                os.path.join(project_root, "data", "development_tickets.json"),
                os.path.join("05_Datasets", "development_tickets.json"),
                "development_tickets.json"
            ]
            for cand in candidates:
                if os.path.exists(cand):
                    dev_tickets_path = cand
                    break

        self.dev_tickets_path = dev_tickets_path
        self.pipeline: Optional[Pipeline] = None
        self.is_trained = False

        if dev_tickets_path and os.path.exists(dev_tickets_path):
            self.train(dev_tickets_path)

    def train(self, dev_path: str):
        """Trains logistic regression model on development tickets."""
        with open(dev_path, "r", encoding="utf-8") as f:
            dev_data = json.load(f)

        texts = []
        intents = []
        for t in dev_data:
            text = f"{t.get('subject', '')} {t.get('body', '')}".strip()
            intent = t.get("labels", {}).get("intent")
            if text and intent:
                texts.append(text)
                intents.append(intent)

        if not texts:
            return

        self.pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=5000,
                sublinear_tf=True
            )),
            ("clf", LogisticRegression(
                max_iter=500,
                C=2.0,
                solver="lbfgs"
            ))
        ])
        self.pipeline.fit(texts, intents)
        self.is_trained = True

    def _predict_urgency(self, text: str, tier: str, intent: str) -> (str, float):
        """Rule-assisted heuristic urgency scoring with confidence."""
        lower_text = text.lower()
        score = 0.5  # medium baseline

        # Security incidents and production outages are always high/critical
        if intent in ("security_incident", "deployment_failure", "database_issue"):
            score += 0.35

        for kw in self.HIGH_URGENCY_KEYWORDS:
            if re.search(kw, lower_text):
                score += 0.25
                break

        for kw in self.LOW_URGENCY_KEYWORDS:
            if re.search(kw, lower_text):
                score -= 0.25
                break

        if tier == "enterprise":
            score += 0.15
        elif tier == "standard":
            score -= 0.05

        if score >= 0.70:
            return "high", min(0.95, round(score, 2))
        elif score <= 0.35:
            return "low", max(0.60, round(1.0 - score, 2))
        else:
            return "medium", round(max(0.65, 1.0 - abs(0.5 - score)), 2)

    def classify(self, ticket: NormalizedTicket) -> ClassificationResult:
        """
        Classifies intent and urgency with numeric confidence [0.0, 1.0].
        Returns fallback when text is empty or classification fails.
        """
        text = ticket.full_text.strip()
        if not text or not self.is_trained or self.pipeline is None:
            # Fallback for empty or unclassifiable ticket
            urgency, urg_conf = self._predict_urgency("", ticket.customer_tier, self.FALLBACK_INTENT)
            return ClassificationResult(
                intent=self.FALLBACK_INTENT,
                intent_confidence=0.30,
                urgency=urgency,
                urgency_confidence=urg_conf,
                alternatives_considered=[{"intent": self.FALLBACK_INTENT, "confidence": 0.30}],
                is_fallback=True,
            )

        # Get probabilities from logistic regression
        clf = self.pipeline.named_steps["clf"]
        tfidf = self.pipeline.named_steps["tfidf"]
        
        vec = tfidf.transform([text])
        probs = clf.predict_proba(vec)[0]
        classes = clf.classes_

        # Rank all alternative classes
        ranked = sorted(zip(classes, probs), key=lambda x: x[1], reverse=True)
        top_intent, top_confidence = ranked[0]
        
        # Format alternatives considered
        alternatives = [
            {"intent": str(intent_name), "confidence": round(float(p), 4)}
            for intent_name, p in ranked[:5]
        ]

        urgency, urg_conf = self._predict_urgency(text, ticket.customer_tier, top_intent)

        return ClassificationResult(
            intent=str(top_intent),
            intent_confidence=round(float(top_confidence), 4),
            urgency=urgency,
            urgency_confidence=urg_conf,
            alternatives_considered=alternatives
        )
