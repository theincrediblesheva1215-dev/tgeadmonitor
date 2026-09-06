"""Применение словарей и regex. Возвращает список совпадений и набор признаков."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.config.loader import AppConfig, Chat
from src.processing.extractor import SurfaceFeatures


@dataclass(frozen=True)
class Match:
    feature: str          # intent, product, size, amount, location, context, sell, ad, url, ...
    rule: str             # id правила
    text: str             # что именно совпало
    value: str | None = None  # нормализованное значение (название товара, локации, размер)


@dataclass
class MatchResult:
    matches: list[Match] = field(default_factory=list)
    features: set[str] = field(default_factory=set)
    products: list[str] = field(default_factory=list)   # имена товаров (уникальные, по порядку)
    product_ids: list[str] = field(default_factory=list)
    sizes: list[str] = field(default_factory=list)
    amounts: list[str] = field(default_factory=list)
    location: str | None = None
    location_from_chat: bool = False
    intent_texts: list[str] = field(default_factory=list)

    def add(self, feature: str, rule: str, text: str, value: str | None = None) -> None:
        m = Match(feature, rule, text.strip(), value)
        if m not in self.matches:
            self.matches.append(m)
        self.features.add(feature)


class Matcher:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self._delivery = re.compile(r"\bдоставк\w*")
        self._in_stock = re.compile(r"\bв\s+наличии\b")
        self._opt_roznica = re.compile(r"\bопт\w*\s+и\s+в\s+розниц\w*|\bопт\s*/\s*розниц\w*")

    # ---------- helpers ----------
    @staticmethod
    def _negated(norm: str, start: int) -> bool:
        prefix = norm[max(0, start - 3):start]
        return prefix.endswith("не ")

    @staticmethod
    def _joined_groups(m: re.Match) -> str:
        parts = [g.replace(",", ".") for g in m.groups() if g]
        return "x".join(parts) if parts else m.group(0)

    # ---------- main ----------
    def match(self, norm: str, orig: str, surface: SurfaceFeatures, chat: Chat | None) -> MatchResult:
        r = MatchResult()
        cfg = self.cfg

        # 1. Purchase intent (с учётом отрицания "не нужна")
        for rule in cfg.intents:
            for m in rule.regex.finditer(norm):
                if self._negated(norm, m.start()):
                    continue
                r.add("intent", rule.id, m.group(0))
                r.intent_texts.append(m.group(0))
                if rule.strong:
                    r.features.add("intent_strong")
                break

        # 2. Products + product-specific sizes
        for p in cfg.products:
            found = None
            for rx in p.patterns:
                found = rx.search(norm)
                if found:
                    break
            if not found:
                continue
            r.add("product", p.id, found.group(0), value=p.name)
            if p.name not in r.products:
                r.products.append(p.name)
                r.product_ids.append(p.id)
            for rx in p.size_patterns:
                sm = rx.search(norm)
                if sm:
                    val = self._joined_groups(sm)
                    r.add("size", f"{p.id}_size", sm.group(0), value=val)
                    if val not in r.sizes:
                        r.sizes.append(val)

        # 3. Generic sizes (40x20x2)
        for rx in cfg.size_patterns:
            for sm in rx.finditer(norm):
                val = self._joined_groups(sm)
                r.add("size", "size", sm.group(0), value=val)
                if val not in r.sizes:
                    r.sizes.insert(0, val)  # явный типоразмер важнее одиночного числа

        # 4. Amounts
        for rx in cfg.amount_patterns:
            for am in rx.finditer(norm):
                val = am.group(0)
                r.add("amount", "amount", val, value=val)
                if val not in r.amounts:
                    r.amounts.append(val)

        # 5. Locations (текст -> иначе fallback на локацию чата)
        for loc in cfg.locations:
            for rx in loc.patterns:
                lm = rx.search(norm)
                if lm:
                    r.add("location", loc.name, lm.group(0), value=loc.name)
                    if r.location is None:
                        r.location = loc.name
                    break
        if r.location is None and chat and chat.location:
            r.location = chat.location
            r.location_from_chat = True
            r.features.add("location_fallback")

        # 6. Construction context
        for rule in cfg.context_rules:
            cm = rule.regex.search(norm)
            if cm:
                r.add("context", rule.id, cm.group(0))

        # 7. Sell / noise
        for rule in cfg.sell_rules:
            sm = rule.regex.search(norm)
            if sm:
                r.add("sell", rule.id, sm.group(0))

        # 8. Question
        if surface.is_question:
            r.add("question", "question", "?")

        # 9. URL и рекламные признаки
        if surface.urls:
            r.add("url", "url", surface.urls[0])
        if len(r.product_ids) >= cfg.ad.many_products_threshold:
            r.add("many_products", "many_products", ", ".join(r.products))

        ad_flags: list[str] = []
        if surface.phones:
            ad_flags.append("phone")
        if surface.urls:
            ad_flags.append("url")
        if surface.usernames:
            ad_flags.append("username")
        if len(surface.prices) >= cfg.ad.price_count_threshold:
            ad_flags.append("prices")
        if "many_products" in r.features:
            ad_flags.append("many_products")
        if self._delivery.search(norm) and self._in_stock.search(norm):
            ad_flags.append("delivery+stock")
        if self._opt_roznica.search(norm):
            ad_flags.append("wholesale+retail")
        if surface.emoji_count >= cfg.ad.emoji_threshold:
            ad_flags.append("emoji")
        if surface.letters >= cfg.ad.caps_min_letters and surface.caps_ratio >= cfg.ad.caps_ratio_threshold:
            ad_flags.append("caps")
        if len(ad_flags) >= cfg.ad.min_features:
            r.add("ad", "ad", "+".join(ad_flags))

        return r