"""Поверхностные признаки, извлекаемые из ОРИГИНАЛЬНОГО текста (телефоны, URL, CAPS, emoji...)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PHONE = re.compile(r"(?:\+7|\b8|\b7)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b")
URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w\-]+\.(?:ru|com|рф|net|org|su|shop|site|store|pro|online)\b", re.I)
USERNAME = re.compile(r"(?<![\w/])@[A-Za-z_]\w{3,}")
PRICE = re.compile(r"\d[\d\s]*(?:[.,]\d+)?\s*(?:руб\w*|р\.|₽|р/|руб/|тыс\.?\s*руб|т\.р\.)", re.I)
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\u203C\u2049\u2705\u274C]")
LETTERS = re.compile(r"[A-Za-zА-Яа-яЁё]")
UPPER = re.compile(r"[A-ZА-ЯЁ]")
QUESTION_START = re.compile(r"^(?:подскажите|посоветуйте|кто|где|у кого|есть ли|может кто|никто не|а кто|ребят[а]?\s+кто)\b")


@dataclass
class SurfaceFeatures:
    phones: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    usernames: list[str] = field(default_factory=list)
    prices: list[str] = field(default_factory=list)
    emoji_count: int = 0
    caps_ratio: float = 0.0
    letters: int = 0
    is_question: bool = False


def extract_surface(original: str, normalized: str) -> SurfaceFeatures:
    letters = LETTERS.findall(original)
    upper = UPPER.findall(original)
    caps_ratio = len(upper) / len(letters) if letters else 0.0
    return SurfaceFeatures(
        phones=PHONE.findall(original),
        urls=URL.findall(original),
        usernames=USERNAME.findall(original),
        prices=PRICE.findall(original),
        emoji_count=len(EMOJI.findall(original)),
        caps_ratio=caps_ratio,
        letters=len(letters),
        is_question=("?" in original) or bool(QUESTION_START.search(normalized)),
    )