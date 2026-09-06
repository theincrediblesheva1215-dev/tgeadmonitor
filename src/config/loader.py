"""Загрузка и валидация YAML-конфигов. Все regex компилируются здесь, один раз при старте."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

FLAGS = re.IGNORECASE

KNOWN_FEATURES = {
    "intent", "intent_strong", "product", "size", "amount", "location",
    "location_fallback", "context", "question", "sell", "ad", "many_products", "url",
}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Rule:
    id: str
    regex: re.Pattern
    strong: bool = False


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    group: str
    patterns: tuple[re.Pattern, ...]
    size_patterns: tuple[re.Pattern, ...]


@dataclass(frozen=True)
class Location:
    name: str
    patterns: tuple[re.Pattern, ...]


@dataclass
class Chat:
    id: str
    name: str
    chat_id: int | None = None
    username: str | None = None
    location: str | None = None
    district: str | None = None
    kind: str | None = None
    enabled: bool = True
    priority: int = 1
    comment: str | None = None


@dataclass(frozen=True)
class AdSettings:
    min_features: int = 2
    many_products_threshold: int = 4
    price_count_threshold: int = 2
    emoji_threshold: int = 5
    caps_ratio_threshold: float = 0.5
    caps_min_letters: int = 20


@dataclass(frozen=True)
class HardRule:
    id: str
    all: tuple[str, ...]
    none: tuple[str, ...]


@dataclass(frozen=True)
class DedupSettings:
    window_days: int = 7
    fuzzy_threshold: int = 90
    same_user_fuzzy_threshold: int = 80
    max_candidates: int = 500


@dataclass(frozen=True)
class Scoring:
    weights: dict[str, int]
    notify_threshold: int
    potential_threshold: int
    lead_rules: tuple[HardRule, ...]
    not_lead_rules: tuple[HardRule, ...]
    dedup: DedupSettings


@dataclass
class AppConfig:
    chats: list[Chat]
    products: list[Product]
    context_rules: list[Rule]
    size_patterns: list[re.Pattern]
    amount_patterns: list[re.Pattern]
    intents: list[Rule]
    sell_rules: list[Rule]
    hard_exclusions: list[Rule]
    min_length: int
    ad: AdSettings
    locations: list[Location]
    scoring: Scoring

    def enabled_chats(self) -> list[Chat]:
        return [c for c in self.chats if c.enabled]


# ---------- helpers ----------

def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def _compile(pattern: str, where: str) -> re.Pattern:
    if not isinstance(pattern, str) or not pattern:
        raise ConfigError(f"{where}: pattern must be a non-empty string")
    try:
        return re.compile(pattern, FLAGS)
    except re.error as e:
        raise ConfigError(f"{where}: invalid regex {pattern!r}: {e}") from e


def _compile_list(patterns: list[str] | None, where: str) -> tuple[re.Pattern, ...]:
    return tuple(_compile(p, f"{where}[{i}]") for i, p in enumerate(patterns or []))


def _rules(items: list[dict] | None, where: str) -> list[Rule]:
    rules: list[Rule] = []
    seen: set[str] = set()
    for i, item in enumerate(items or []):
        rid = str(item.get("id") or f"{where}_{i}")
        if rid in seen:
            raise ConfigError(f"{where}: duplicate rule id {rid!r}")
        seen.add(rid)
        rules.append(Rule(id=rid, regex=_compile(item.get("pattern"), f"{where}.{rid}"),
                          strong=bool(item.get("strong", False))))
    return rules


def _hard_rules(items: list[dict] | None, where: str) -> tuple[HardRule, ...]:
    out = []
    for i, item in enumerate(items or []):
        rid = str(item.get("id") or f"{where}_{i}")
        all_ = tuple(item.get("all") or [])
        none = tuple(item.get("none") or [])
        for f in (*all_, *none):
            if f not in KNOWN_FEATURES:
                raise ConfigError(f"{where}.{rid}: unknown feature {f!r}")
        if not all_:
            raise ConfigError(f"{where}.{rid}: 'all' must not be empty")
        out.append(HardRule(id=rid, all=all_, none=none))
    return tuple(out)


# ---------- public ----------

def load_config(config_dir: Path) -> AppConfig:
    config_dir = Path(config_dir)

    chats_raw = _load_yaml(config_dir / "chats.yaml").get("chats") or []
    chats = []
    for i, c in enumerate(chats_raw):
        if not c.get("id"):
            raise ConfigError(f"chats.yaml[{i}]: 'id' is required")
        if c.get("chat_id") is None and not c.get("username"):
            raise ConfigError(f"chats.yaml[{c['id']}]: chat_id or username is required")
        chats.append(Chat(
            id=str(c["id"]), name=str(c.get("name") or c["id"]),
            chat_id=int(c["chat_id"]) if c.get("chat_id") is not None else None,
            username=(c.get("username") or None), location=c.get("location"),
            district=c.get("district"), kind=c.get("kind"),
            enabled=bool(c.get("enabled", True)), priority=int(c.get("priority", 1)),
            comment=c.get("comment"),
        ))

    prod_raw = _load_yaml(config_dir / "products.yaml")
    products = []
    for i, p in enumerate(prod_raw.get("products") or []):
        pid = p.get("id")
        if not pid:
            raise ConfigError(f"products.yaml[{i}]: 'id' is required")
        pats = _compile_list(p.get("patterns"), f"products.{pid}.patterns")
        if not pats:
            raise ConfigError(f"products.{pid}: 'patterns' must not be empty")
        products.append(Product(
            id=str(pid), name=str(p.get("name") or pid), group=str(p.get("group") or ""),
            patterns=pats, size_patterns=_compile_list(p.get("size_patterns"), f"products.{pid}.size_patterns"),
        ))
    context_rules = _rules(prod_raw.get("construction_context"), "construction_context")
    size_patterns = list(_compile_list(prod_raw.get("sizes"), "sizes"))
    amount_patterns = list(_compile_list(prod_raw.get("amounts"), "amounts"))

    intents = _rules(_load_yaml(config_dir / "intents.yaml").get("purchase_intents"), "purchase_intents")
    if not intents:
        raise ConfigError("intents.yaml: purchase_intents is empty")

    excl_raw = _load_yaml(config_dir / "exclusions.yaml")
    sell_rules = _rules(excl_raw.get("sell_intents"), "sell_intents")
    hard_raw = excl_raw.get("hard_exclusions") or {}
    hard_exclusions = _rules(hard_raw.get("patterns"), "hard_exclusions")
    min_length = int(hard_raw.get("min_length", 0))
    ad = AdSettings(**{k: v for k, v in (excl_raw.get("ad_features") or {}).items()
                       if k in AdSettings.__dataclass_fields__})

    locations = []
    for i, loc in enumerate(_load_yaml(config_dir / "locations.yaml").get("locations") or []):
        if not loc.get("name"):
            raise ConfigError(f"locations.yaml[{i}]: 'name' is required")
        pats = _compile_list(loc.get("patterns"), f"locations.{loc['name']}")
        if not pats:
            raise ConfigError(f"locations.{loc['name']}: 'patterns' must not be empty")
        locations.append(Location(name=str(loc["name"]), patterns=pats))

    sc_raw = _load_yaml(config_dir / "scoring.yaml")
    weights = {str(k): int(v) for k, v in (sc_raw.get("weights") or {}).items()}
    for k in weights:
        if k not in KNOWN_FEATURES:
            raise ConfigError(f"scoring.yaml: unknown weight key {k!r}")
    thresholds = sc_raw.get("thresholds") or {}
    hard = sc_raw.get("hard_rules") or {}
    scoring = Scoring(
        weights=weights,
        notify_threshold=int(thresholds.get("notify", 8)),
        potential_threshold=int(thresholds.get("potential", 5)),
        lead_rules=_hard_rules(hard.get("lead"), "hard_rules.lead"),
        not_lead_rules=_hard_rules(hard.get("not_lead"), "hard_rules.not_lead"),
        dedup=DedupSettings(**{k: v for k, v in (sc_raw.get("dedup") or {}).items()
                               if k in DedupSettings.__dataclass_fields__}),
    )

    return AppConfig(
        chats=chats, products=products, context_rules=context_rules,
        size_patterns=size_patterns, amount_patterns=amount_patterns,
        intents=intents, sell_rules=sell_rules, hard_exclusions=hard_exclusions,
        min_length=min_length, ad=ad, locations=locations, scoring=scoring,
    )