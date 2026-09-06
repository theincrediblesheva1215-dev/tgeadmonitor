"""Отправка уведомлений через Bot API + приём feedback-кнопок (long polling). Только aiohttp."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from src.metrics import Metrics
from src.storage.database import Database

log = logging.getLogger("notifier")

FEEDBACK = {"lead": ("confirmed", "✅ Отмечено как лид"), "notlead": ("rejected", "❌ Отмечено: не лид")}


class BotApiError(Exception):
    pass


class Notifier:
    def __init__(self, token: str, owner_chat_id: int, db: Database, metrics: Metrics,
                 retry_interval: float = 5.0, max_attempts: int = 50):
        self.base = f"https://api.telegram.org/bot{token}/"
        self.owner = owner_chat_id
        self.db = db
        self.metrics = metrics
        self.retry_interval = retry_interval
        self.max_attempts = max_attempts
        self._session: aiohttp.ClientSession | None = None
        self._offset = 0
        self._wakeup = asyncio.Event()

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        me = await self.api("getMe")
        log.info("Bot authorized as @%s", me.get("username"))

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    def wakeup(self) -> None:
        """Сигнал pipeline: появилось новое pending-уведомление."""
        self._wakeup.set()

    # ---------- Bot API ----------
    async def api(self, method: str, **params: Any) -> Any:
        assert self._session is not None
        payload = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                   for k, v in params.items() if v is not None}
        async with self._session.post(self.base + method, data=payload) as resp:
            data = await resp.json(content_type=None)
        if not data.get("ok"):
            raise BotApiError(f"{method}: {data.get('description')} (code {data.get('error_code')})")
        return data["result"]

    # ---------- pending queue ----------
    async def run_sender(self) -> None:
        """Пытается отправить все pending-уведомления; при недоступности Bot API повторяет."""
        while True:
            try:
                rows = self.db.pending_notifications(self.max_attempts)
                for row in rows:
                    await self._send_row(row)
            except Exception:
                log.exception("Sender loop error")
            self._wakeup.clear()
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=self.retry_interval)
            except asyncio.TimeoutError:
                pass

    async def _send_row(self, row: Any) -> None:
        payload = json.loads(row["payload"])
        try:
            result = await self.api("sendMessage", chat_id=self.owner, text=payload["text"],
                                    parse_mode="HTML", disable_web_page_preview=True,
                                    reply_markup=payload.get("reply_markup"))
        except (aiohttp.ClientError, asyncio.TimeoutError, BotApiError) as e:
            final = row["attempts"] + 1 >= self.max_attempts
            self.db.mark_notification_failed(int(row["id"]), str(e), final=final)
            self.metrics.inc("notification_failed")
            log.warning("NOTIFICATION_FAILED lead_id=%s attempt=%s error=%s", row["lead_id"], row["attempts"] + 1, e)
            return
        self.db.mark_notification_sent(int(row["id"]))
        self.db.set_lead_notified(int(row["lead_id"]), result.get("message_id"))
        self.metrics.inc("notifications_sent")
        log.info("NOTIFICATION_SENT lead_id=%s bot_message_id=%s", row["lead_id"], result.get("message_id"))

    # ---------- feedback ----------
    async def run_polling(self) -> None:
        while True:
            try:
                updates = await self.api("getUpdates", offset=self._offset, timeout=50,
                                         allowed_updates=["callback_query", "message"])
                for upd in updates:
                    self._offset = upd["update_id"] + 1
                    await self._handle_update(upd)
            except (aiohttp.ClientError, asyncio.TimeoutError, BotApiError) as e:
                log.warning("Polling error: %s", e)
                await asyncio.sleep(self.retry_interval)
            except Exception:
                log.exception("Polling loop error")
                await asyncio.sleep(self.retry_interval)

    async def _handle_update(self, upd: dict) -> None:
        cb = upd.get("callback_query")
        if cb:
            await self._handle_callback(cb)
            return
        msg = upd.get("message")
        if msg and msg.get("chat", {}).get("id") == self.owner and (msg.get("text") or "").startswith("/stats"):
            stats = self.db.stats()
            stats.update(self.metrics.snapshot())
            text = "<pre>" + json.dumps(stats, ensure_ascii=False, indent=1)[:3900] + "</pre>"
            await self.api("sendMessage", chat_id=self.owner, text=text, parse_mode="HTML")

    async def _handle_callback(self, cb: dict) -> None:
        cb_id = cb["id"]
        if cb.get("from", {}).get("id") != self.owner:
            await self.api("answerCallbackQuery", callback_query_id=cb_id, text="Нет доступа")
            return
        data = cb.get("data") or ""
        action, _, lead_id = data.partition(":")
        if action not in FEEDBACK or not lead_id.isdigit():
            await self.api("answerCallbackQuery", callback_query_id=cb_id)
            return
        status, label = FEEDBACK[action]
        ok = self.db.set_feedback(int(lead_id), status)
        self.metrics.inc("true_positive" if status == "confirmed" else "false_positive")
        log.info("FEEDBACK lead_id=%s status=%s", lead_id, status)
        await self.api("answerCallbackQuery", callback_query_id=cb_id, text=label if ok else "Лид не найден")
        message = cb.get("message")
        if message and ok:
            markup = message.get("reply_markup") or {}
            rows = [r for r in markup.get("inline_keyboard", []) if not any("callback_data" in b for b in r)]
            rows.append([{"text": label, "callback_data": "noop:0"}])
            try:
                await self.api("editMessageReplyMarkup", chat_id=message["chat"]["id"],
                               message_id=message["message_id"], reply_markup={"inline_keyboard": rows})
            except BotApiError as e:
                log.debug("editMessageReplyMarkup: %s", e)