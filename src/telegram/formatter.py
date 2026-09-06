"""Формирование текста и кнопок уведомления. HTML parse_mode."""
from __future__ import annotations

import html

from src.storage.models import LeadRecord

MAX_TEXT = 700


def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=False)


def build_notification(lead: LeadRecord, chat_name: str) -> dict:
    m = lead.message
    text = m.text if len(m.text) <= MAX_TEXT else m.text[:MAX_TEXT] + "…"

    author = _esc(m.first_name) or "—"
    if m.user_id:
        author = f'<a href="tg://user?id={m.user_id}">{author}</a>'
    username = f"@{m.username}" if m.username else ""

    found = "\n".join(f"{_esc(f)}: {_esc(t)}" for f, t in lead.found)

    lines = [
        "🔥 <b>Новый потенциальный лид</b>",
        "",
        f"📦 {_esc(lead.product) or '— (строительный контекст)'}",
        f"📍 {_esc(lead.location) or '—'}",
        f"📊 Score: {lead.score}",
        "",
        "💬 <b>Сообщение:</b>",
        f"<i>{_esc(text)}</i>",
        "",
        f"👤 {author} {_esc(username)}".rstrip(),
        "",
        f"🏘 Чат: {_esc(chat_name)}",
        "",
        "🔎 <b>Найдено:</b>",
        found or "—",
    ]

    row1 = []
    if m.message_url:
        row1.append({"text": "Открыть сообщение", "url": m.message_url})
    if m.username:
        row1.append({"text": "Написать автору", "url": f"https://t.me/{m.username}"})
    row2 = [
        {"text": "✅ Лид", "callback_data": f"lead:{lead.lead_id}"},
        {"text": "❌ Не лид", "callback_data": f"notlead:{lead.lead_id}"},
    ]
    keyboard = [r for r in (row1, row2) if r]

    return {"text": "\n".join(lines), "reply_markup": {"inline_keyboard": keyboard}}