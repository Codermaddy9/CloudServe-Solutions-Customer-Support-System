"""
Automation-readiness scoring for CloudServe Support Automation.

Why this module exists
----------------------
Version one of the requirements routed on the intent classifier's own
probability. Calibration measurement on development data (see
`evaluation/calibrate.py`) showed two things that made that untenable:

  1. The intent classifier is highly accurate out-of-fold but badly
     under-confident. Observed accuracy sat at or near 100% in every
     confidence band from 0.1 upward while stated confidence ranged from
     0.14 to 0.82, an expected calibration error of roughly 40 points
     against the Evaluation Framework's 5-point requirement. A threshold
     placed on that number does not mean what it appears to mean.

  2. Intent confidence is close to uninformative about whether a ticket
     *should* be automated. Sweeping it from 0.05 to 0.80 moved automation
     precision by under two points, because whether a ticket is answerable
     from the documentation is largely independent of how certain the
     classifier is about its topic.

This module therefore scores the question the router actually needs answered:
given this ticket's text, what is the probability that it can be resolved
without a human? The model is trained on the `expected_route` label and
wrapped in isotonic calibration so that a score of 0.7 corresponds to roughly
a 70% chance of being right.

Satisfies Acceptance Criterion A3 (numeric confidence that reflects the actual
probability of being correct) and A5 (a threshold determined from data).
"""
import os
import json
from typing import Any, Dict, List, Optional, Tuple

from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from src.models import NormalizedTicket

DEFAULT_SCORE_WHEN_UNTRAINED = 0.0


def _candidate_paths(filename: str) -> List[str]:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [
        os.path.join(project_root, "05_Datasets", filename),
        os.path.join(project_root, "data", filename),
        os.path.join("05_Datasets", filename),
        filename,
    ]


class AutomationReadinessScorer:
    """
    Calibrated estimate of the probability that a ticket can be safely
    resolved without human involvement.

    The score is deliberately separate from the intent classifier's
    probability. Intent tells the router *what* the ticket is about, which
    drives policy rules. This score tells the router *whether* an automated
    answer is likely to be adequate, which drives the threshold.
    """

    def __init__(self, dev_tickets_path: Optional[str] = None, calibration_folds: int = 3):
        self.calibration_folds = calibration_folds
        self.pipeline: Optional[Pipeline] = None
        self.is_trained = False
        self.training_size = 0

        if dev_tickets_path is None:
            for candidate in _candidate_paths("development_tickets.json"):
                if os.path.exists(candidate):
                    dev_tickets_path = candidate
                    break

        self.dev_tickets_path = dev_tickets_path
        if dev_tickets_path and os.path.exists(dev_tickets_path):
            try:
                self.train(dev_tickets_path)
            except Exception:
                # A scorer that cannot train degrades to "never confident",
                # which routes everything to a human. That is the safe failure
                # direction and keeps the pipeline running (A11).
                self.is_trained = False

    def train(self, dev_path: str) -> None:
        with open(dev_path, "r", encoding="utf-8") as fh:
            tickets = json.load(fh)

        texts: List[str] = []
        targets: List[int] = []
        for ticket in tickets:
            text = f"{ticket.get('subject', '')} {ticket.get('body', '')}".strip()
            route = ticket.get("labels", {}).get("expected_route")
            if not text or route is None:
                continue
            texts.append(text)
            targets.append(1 if route == "auto_respond" else 0)

        # Both classes must be present for calibration to be meaningful.
        if len(set(targets)) < 2 or len(texts) < self.calibration_folds * 4:
            return

        self.pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000, sublinear_tf=True)),
            ("clf", CalibratedClassifierCV(
                LogisticRegression(max_iter=1000, C=2.0, solver="lbfgs"),
                method="isotonic",
                cv=self.calibration_folds,
            )),
        ])
        self.pipeline.fit(texts, targets)
        self.is_trained = True
        self.training_size = len(texts)

    def score(self, ticket: NormalizedTicket) -> float:
        """
        Probability in [0, 1] that this ticket can be resolved automatically.

        Returns 0.0 when the model is unavailable or the ticket carries no
        text, so that an absent score is never mistaken for a high one. The
        Governance Framework requires exactly this: "a missing confidence
        score is not a high one".
        """
        text = ticket.full_text.strip()
        if not text or not self.is_trained or self.pipeline is None:
            return DEFAULT_SCORE_WHEN_UNTRAINED
        try:
            return round(float(self.pipeline.predict_proba([text])[0][1]), 4)
        except Exception:
            return DEFAULT_SCORE_WHEN_UNTRAINED
