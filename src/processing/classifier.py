"""Чистая функция классификации: текст -> результат. Без БД и Telegram, используется и в tools/tests."""
from __future__ import annotations

from dataclasses import dataclass

from src.config.loader import AppConfig, Chat
from src.processing.extractor import SurfaceFeatures, extract_surface
from src.processing.matcher import Matcher, MatchResult
from src.processing.normalizer import normalize, text_hash
from src.processing.scorer import Scorer, Verdict


@dataclass
class Classification:
    original: str
    normalized: str
    hash: str
    surface: SurfaceFeatures
    matches: MatchResult
    verdict: Verdict
    hard_excluded: str | None = None   # причина жёсткого исключения, если было

    @property
    def is_lead(self) -> bool:
        return self.verdict.decision == "lead"


class Classifier:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.matcher = Matcher(cfg)
        self.scorer = Scorer(cfg.scoring)

    def hard_exclusion(self, original: str, normalized: str) -> str | None:
        if len(normalized) < self.cfg.min_length:
            return "too_short"
        for rule in self.cfg.hard_exclusions:
            if rule.regex.search(original) or rule.regex.search(normalized):
                return rule.id
        return None

    def classify(self, original: str, chat: Chat | None = None) -> Classification:
        normalized = normalize(original)
        surface = extract_surface(original, normalized)
        excluded = self.hard_exclusion(original, normalized)
        if excluded:
            matches = MatchResult()
            verdict = Verdict(score=0, decision="ignore", hard_rule=f"excluded:{excluded}",
                              threshold=self.cfg.scoring.notify_threshold)
        else:
            matches = self.matcher.match(normalized, original, surface, chat)
            verdict = self.scorer.score(matches)
        return Classification(original=original, normalized=normalized, hash=text_hash(normalized),
                              surface=surface, matches=matches, verdict=verdict, hard_excluded=excluded)