"""Подсчёт баллов, hard rules, порог. Полностью объяснимый результат."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.config.loader import HardRule, Scoring
from src.processing.matcher import MatchResult

LEAD = "lead"
POTENTIAL = "potential"
IGNORE = "ignore"


@dataclass
class Verdict:
    score: int
    decision: str                       # lead | potential | ignore
    hard_rule: str | None = None        # id сработавшего hard rule
    breakdown: list[tuple[str, int, str]] = field(default_factory=list)  # (feature, weight, evidence)
    threshold: int = 0

    def explain(self) -> str:
        lines = [f"score = {self.score} (threshold = {self.threshold})"]
        for feature, weight, evidence in self.breakdown:
            lines.append(f"{weight:+d} {feature}: {evidence}")
        if self.hard_rule:
            lines.append(f"hard rule: {self.hard_rule}")
        lines.append(f"decision: {self.decision}")
        return "\n".join(lines)


def _rule_applies(rule: HardRule, features: set[str]) -> bool:
    return all(f in features for f in rule.all) and not any(f in features for f in rule.none)


class Scorer:
    def __init__(self, scoring: Scoring):
        self.s = scoring

    def score(self, r: MatchResult) -> Verdict:
        breakdown: list[tuple[str, int, str]] = []
        total = 0
        for feature, weight in self.s.weights.items():
            if feature not in r.features:
                continue
            evidence = "; ".join(sorted({m.text for m in r.matches if m.feature == feature})) or feature
            if feature == "location_fallback":
                evidence = f"из чата: {r.location}"
            breakdown.append((feature, weight, evidence))
            total += weight

        verdict = Verdict(score=total, breakdown=breakdown, decision=IGNORE,
                          threshold=self.s.notify_threshold)

        for rule in self.s.not_lead_rules:
            if _rule_applies(rule, r.features):
                verdict.hard_rule = f"not_lead:{rule.id}"
                verdict.decision = IGNORE
                return verdict
        for rule in self.s.lead_rules:
            if _rule_applies(rule, r.features):
                verdict.hard_rule = f"lead:{rule.id}"
                verdict.decision = LEAD
                return verdict

        if total >= self.s.notify_threshold:
            verdict.decision = LEAD
        elif total >= self.s.potential_threshold:
            verdict.decision = POTENTIAL
        return verdict