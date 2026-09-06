"""Нормализация текста перед regex-анализом. Оригинал сохраняется отдельно (в pipeline)."""
from __future__ import annotations

import hashlib
import re

_YO = str.maketrans({"ё": "е", "Ё": "Е"})
_DASHES = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]")
# 40 х 20, 40Х20, 40×20, 40*20 -> 40x20 (только между цифрами)
_X_BETWEEN_DIGITS = re.compile(r"(?<=\d)\s*[xхХX×*]\s*(?=\d)")
# всё, что не буква/цифра/пробел и не . , / + - : пробел (убирает !?«»() emoji и пр.)
_JUNK = re.compile(r"[^\w\s.,/+\-]", re.UNICODE)
# точки и запятые, не стоящие между цифрами (1.5 и 1,5 сохраняем)
_PUNCT_NOT_DECIMAL = re.compile(r"(?<!\d)[.,]|[.,](?!\d)")
_MULTI_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    t = text.translate(_YO).lower()
    t = _DASHES.sub("-", t)
    t = _X_BETWEEN_DIGITS.sub("x", t)
    t = t.replace("_", " ")
    t = _JUNK.sub(" ", t)
    t = _PUNCT_NOT_DECIMAL.sub(" ", t)
    t = _MULTI_SPACE.sub(" ", t).strip()
    return t


def text_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
