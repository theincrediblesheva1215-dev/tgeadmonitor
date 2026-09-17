import asyncio
import json
import os
import random
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    InviteRequestSentError,
    RPCError,
    UserAlreadyParticipantError,
)
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import (
    CheckChatInviteRequest,
    ImportChatInviteRequest,
)
from telethon.utils import get_peer_id


CONFIG_PATH = Path("/app/config/chats.yaml")
OUTPUT_PATH = Path("/app/data/chats.generated.yaml")
STATE_PATH = Path("/app/data/join_missing_state.json")

# Conservative pacing:
# 4-6 minutes after every real JOIN request.
JOIN_DELAY_MIN = 240
JOIN_DELAY_MAX = 360

# Additional 15-20 minute pause after every 4 JOIN requests.
LONG_COOLDOWN_EVERY = 4
LONG_COOLDOWN_MIN = 900
LONG_COOLDOWN_MAX = 1200


SOURCES = [
    ("rostov_obyavlenia_chat", "https://t.me/rostov_obyavlenia_chat", "Ростовская область", None, "объявления", 2),
    ("rostov_obyavlenia", "https://t.me/Rostov_obyavlenia", "Ростовская область", None, "объявления", 2),
    ("rostov_don_market", "https://t.me/rostovDonMarket", "Ростов-на-Дону", None, "барахолка", 2),
    ("rostov_baraholka_reklama", "https://t.me/rostovnadonu_baraholka", "Ростов-на-Дону", None, "барахолка", 2),
    ("barakholka_rostov_bataysk", "https://t.me/barakholka_rostovv", "Ростовская область", None, "барахолка", 2),
    ("bolshaya_baraholka_rostova", "https://t.me/brostov", "Ростов-на-Дону", None, "барахолка", 2),
    ("rostovnadonubaraholka", "https://t.me/rostovnadonubaraholka", "Ростов-на-Дону", None, "барахолка", 2),
    ("barakholka_rostov", "https://t.me/barakholka_rostov", "Ростов-на-Дону", None, "барахолка", 2),
    ("rostov_topchat", "https://t.me/rostov_topchat", "Ростов-на-Дону", None, "городской чат", 2),
    ("privet_rostov_chat", "https://t.me/privet_rostov_chat", "Ростов-на-Дону", None, "городской чат", 2),

    ("stroyrostov_don", "https://t.me/stroyrostov_Don", "Ростов-на-Дону", None, "стройка", 3),
    ("chat_rostova_builders", "https://t.me/chat_rostova", "Ростов-на-Дону", None, "стройка", 3),
    ("stroitelstvo_rostov", "https://t.me/stroitelstvo_rostov", "Ростовская область", None, "стройка", 3),
    ("stroykaremontrnd", "https://t.me/stroykaremontrnd", "Ростов-на-Дону", None, "стройка", 3),
    ("gruzoperevozky_rostov", "https://t.me/gruzoperevozky_rostov", "Ростовская область", None, "грузоперевозки", 1),

    ("levencovka_rnd", "https://t.me/levencovka_rnd", "Ростов-на-Дону", None, "соседи", 2),
    ("suvorovskiy_news", "https://t.me/suvorovskiy_news", "Ростов-на-Дону", None, "соседи", 2),
    ("suvorovskii18_rnd", "https://t.me/suvorovskii18_rnd", "Ростов-на-Дону", None, "ЖК", 2),
    ("krasniyaksai", "https://t.me/krasniyaksai", "Ростов-на-Дону", None, "соседи", 3),
    ("chatvoenvednews", "https://t.me/chatvoenvednews", "Ростов-на-Дону", None, "соседи", 2),
    ("tsentralnyzhk", "https://t.me/tsentralnyzhk", "Ростов-на-Дону", None, "ЖК", 2),
    ("jk_veresaevo_16lit", "https://t.me/jk_veresaevo_16lit", "Ростов-на-Дону", None, "ЖК", 2),
    ("veresaevo_5_2_rnd", "https://t.me/veresaevo_5_2_rnd", "Ростов-на-Дону", None, "ЖК", 2),
    ("jketalon", "https://t.me/jketalon", "Ростов-на-Дону", None, "ЖК", 2),
    ("zkserdcerostova2", "https://t.me/zkserdcerostova2", "Ростов-на-Дону", None, "ЖК", 3),
    ("zhkskypark", "https://t.me/zhkskypark", "Ростов-на-Дону", None, "ЖК", 3),
    ("jk_donskaya_sloboda", "https://t.me/jk_donskaya_sloboda", "Ростов-на-Дону", None, "ЖК", 2),
    ("rostov_aleksandrovka", "https://t.me/rostov_aleksandrovka", "Ростов-на-Дону", None, "районный чат", 2),
    ("rost_rab", "https://t.me/rost_rab", "Ростов-на-Дону", None, "районный чат", 2),
    ("otkrita_vakansiya", "https://t.me/otkrita_vakansiya", "Ростовская область", None, "работа", 1),

    ("aksay_chat", "https://t.me/aksay_chat", "Аксай", "Аксайский район", "городской чат", 3),
    ("aksay_avito_chat", "https://t.me/aksay_avito_chat", "Аксай", "Аксайский район", "объявления", 3),
    ("aksay_forum", "https://t.me/aksay_forum", "Аксай", "Аксайский район", "городской чат", 3),
    ("aksay_mama", "https://t.me/aksay_mama", "Аксай", "Аксайский район", "локальный чат", 2),

    ("aksay_rabota", "https://t.me/%2B581C-EOkiyQ2NDE6", "Аксай", "Аксайский район", "работа", 1),
    ("aksay_samocvety", "https://t.me/%2B3vIlMADcEZ5mMWUy", "Аксай", "Аксайский район", "ЖК", 2),
    ("noviy_aksay_atmosfera", "https://t.me/%2BbUkjpAIIGg4xZjgy", "Аксай", "Аксайский район", "ЖК", 2),
    ("aksay_vishneviy_sad", "https://t.me/%2Bq-dBtzX6brw2NWNi", "Аксай", "Аксайский район", "ЖК", 2),

    ("bataysk_chat", "https://t.me/%2BOpOk5q9Ba6gwN2Yy", "Батайск", None, "городской чат", 3),
    ("builders_rostov_bataysk", "https://t.me/%2Bnl4yq8KHjfo5MzMy", "Батайск", None, "стройка", 3),
    ("bataysk_ads", "https://t.me/%2B_Jy5u0-warRhOTUy", "Батайск", None, "объявления", 2),
    ("bataysk_realty", "https://t.me/%2BbZIueZx_Pm1kNzEy", "Батайск", None, "недвижимость", 1),
    ("bataysk_auto", "https://t.me/%2BC0CjWu8IdsYxYzky", "Батайск", None, "авто", 1),
    ("bataysk_lost_found", "https://t.me/%2B2KQIxziGi65kMjQy", "Батайск", None, "локальный чат", 1),
    ("bataysk_centr_gaydara", "https://t.me/%2ByW-Cn9WiFsI5MGMy", "Батайск", None, "районный чат", 3),
    ("bataysk_koysug_zapadniy", "https://t.me/%2BXqZsnetZuCQ3YTRi", "Батайск", None, "районный чат", 3),
    ("bataysk_severniy", "https://t.me/%2BO0ntO1CyHBAyYjBi", "Батайск", None, "районный чат", 2),
    ("bataysk_rdvs_nalivnaya", "https://t.me/%2B4_eSxg_4IFdmZDMy", "Батайск", None, "районный чат", 2),
    ("bataysk_baraholka_realty", "https://t.me/%2BCuV-JX8WRMM2M2U6", "Батайск", None, "барахолка", 2),

    ("azov_ros", "https://t.me/azov_ros", "Азов", "Азовский район", "городской чат", 2),
    ("priaz_barakholka", "https://t.me/priaz_barakholka", "Азовский район", "Азовский район", "барахолка", 3),
    ("priaz_chat", "https://t.me/priaz_chat", "Азовский район", "Азовский район", "городской чат", 3),
    ("obyavleniya_myasniki", "https://t.me/obyavleniya_myasniki", "Мясниковский район", "Мясниковский район", "объявления", 3),
    ("chaltyr_myasnikovsky", "https://t.me/chaltyr_myasnikovsky", "Чалтырь", "Мясниковский район", "городской чат", 2),
    ("krasny_krym", "https://t.me/krasny_krym", "Красный Крым", "Мясниковский район", "локальный чат", 3),
    ("novocherkassk61rus", "https://t.me/novocherkassk61rus", "Новочеркасск", None, "объявления", 2),
]


# We already saw Telegram accept join requests for these.
# They must NOT be re-requested on every run.
KNOWN_PENDING = {
    "rostov_obyavlenia_chat",
    "rostov_don_market",
    "privet_rostov_chat",
    "aksay_samocvety",
    "noviy_aksay_atmosfera",
    "aksay_vishneviy_sad",
    "bataysk_lost_found",
    "chatvoenvednews",
}


class StopRun(Exception):
    pass


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def parse_link(url):
    value = unquote(urlparse(url).path.strip("/"))

    if value.startswith("+"):
        return "private", value[1:]

    return "public", value


def load_config():
    if not CONFIG_PATH.exists():
        return []

    raw = CONFIG_PATH.read_text(encoding="utf-8-sig")
    data = yaml.safe_load(raw) or {}

    return data.get("chats") or []


def load_state():
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    else:
        state = {}

    state.setdefault("pending", [])
    state.setdefault("invalid", [])
    state.setdefault("errors", {})
    state.setdefault("last_flood_wait", None)

    state["pending"] = sorted(
        set(state["pending"]) | KNOWN_PENDING
    )

    return state


def save_state(state):
    STATE_PATH.write_text(
        json.dumps(
            state,
            indent=2,
            ensure_ascii=True,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def save_generated(entries):
    OUTPUT_PATH.write_text(
        "# Telegram monitoring sources.\n"
        "# Generated by join_missing_chats.py.\n"
        + yaml.safe_dump(
            {"chats": entries},
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )


def save_progress(entries, state):
    save_generated(entries)
    save_state(state)


def make_entry(source, entity):
    sid, url, location, district, source_kind, priority = source

    item = {
        "id": sid,
        "chat_id": get_peer_id(entity),
    }

    username = getattr(entity, "username", None)

    if username:
        item["username"] = username

    item["name"] = getattr(entity, "title", None) or sid
    item["location"] = location

    if district:
        item["district"] = district

    item["kind"] = source_kind
    item["enabled"] = True
    item["priority"] = priority
    item["comment"] = f"auto-imported from {url}"

    return item


def merge_entry(entries, new_item):
    result = []

    for old in entries:
        if old.get("id") == new_item["id"]:
            continue

        if (
            old.get("chat_id") is not None
            and old.get("chat_id") == new_item["chat_id"]
        ):
            continue

        result.append(old)

    result.append(new_item)

    return result


def extract_joined_entity(result):
    """
    Supports both:
      old-style result.chats
      ChatInviteJoinResultOk -> result.updates.chats
    """

    candidates = [
        result,
        getattr(result, "updates", None),
    ]

    for candidate in candidates:
        if candidate is None:
            continue

        chats = getattr(candidate, "chats", None)

        if chats:
            return chats[0]

    return None


async def get_dialogs(client):
    dialogs = await client.get_dialogs(limit=None)

    by_id = {}
    by_username = {}

    for dialog in dialogs:
        entity = dialog.entity
        peer_id = get_peer_id(entity)

        by_id[peer_id] = entity

        username = getattr(entity, "username", None)

        if username:
            by_username[username.lower()] = entity

    return by_id, by_username


async def cooldown(join_count):
    delay = random.randint(
        JOIN_DELAY_MIN,
        JOIN_DELAY_MAX,
    )

    print(f"COOLDOWN_SECONDS={delay}")
    await asyncio.sleep(delay)

    if (
        join_count > 0
        and join_count % LONG_COOLDOWN_EVERY == 0
    ):
        delay = random.randint(
            LONG_COOLDOWN_MIN,
            LONG_COOLDOWN_MAX,
        )

        print(f"LONG_COOLDOWN_SECONDS={delay}")
        await asyncio.sleep(delay)


async def main():
    entries = load_config()
    state = load_state()

    save_progress(entries, state)

    config_ids = {
        item.get("id")
        for item in entries
        if item.get("id")
    }

    client = TelegramClient(
        StringSession(os.environ["SESSION"]),
        int(os.environ["API_ID"]),
        os.environ["API_HASH"],
    )

    # Do not let Telethon silently sleep on FloodWait.
    client.flood_sleep_threshold = 0

    await client.connect()

    if not await client.is_user_authorized():
        raise RuntimeError("SESSION_NOT_AUTHORIZED")

    me = await client.get_me()

    print(
        f"AUTHORIZED user_id={me.id} "
        f"username={me.username or '-'}"
    )

    print(f"CONFIG_ENTRIES={len(entries)}")

    join_count = 0
    added = 0
    pending_count = 0
    skipped = 0
    errors = 0

    async def tg_call(label, callback):
        try:
            return await callback()

        except FloodWaitError as exc:
            state["last_flood_wait"] = {
                "seconds": exc.seconds,
                "operation": label,
                "at": utcnow(),
            }

            save_progress(entries, state)

            print()
            print(f"FLOOD_WAIT_SECONDS={exc.seconds}")
            print(f"FLOOD_WAIT_OPERATION={label}")
            print("PROGRESS_SAVED=1")
            print("STOP_REASON=FLOOD_WAIT")

            raise StopRun()

    try:
        dialog_by_id, dialog_by_username = await get_dialogs(client)

        # ------------------------------------------------------------
        # Reconcile config against chats that account already has.
        # This needs no JOIN requests.
        # ------------------------------------------------------------

        for source in SOURCES:
            sid, url, *_ = source

            if sid in config_ids:
                continue

            link_type, target = parse_link(url)

            if link_type != "public":
                continue

            entity = dialog_by_username.get(target.lower())

            if entity is None:
                continue

            item = make_entry(source, entity)
            entries = merge_entry(entries, item)

            config_ids.add(sid)
            added += 1

            save_progress(entries, state)

            print(
                f"RECOVERED_EXISTING source={sid} "
                f"chat_id={item['chat_id']}"
            )

        # ------------------------------------------------------------
        # Process all sources.
        # Already configured entries are skipped.
        # ------------------------------------------------------------

        total = len(SOURCES)

        for index, source in enumerate(SOURCES, 1):
            sid, url, *_ = source

            print()
            print(f"SOURCE={index}/{total} id={sid}")

            if sid in config_ids:
                print("STATUS=ALREADY_IN_CONFIG")
                skipped += 1
                continue

            link_type, target = parse_link(url)

            # --------------------------------------------------------
            # Previously pending request.
            # Public: do not send JoinChannelRequest again.
            # Private: CheckChatInviteRequest may tell us that the
            # request has meanwhile been approved.
            # --------------------------------------------------------

            if sid in state["pending"]:
                if link_type == "public":
                    print("STATUS=PENDING_APPROVAL")
                    pending_count += 1
                    continue

                try:
                    info = await tg_call(
                        f"check_pending:{sid}",
                        lambda: client(
                            CheckChatInviteRequest(target)
                        ),
                    )

                    entity = getattr(info, "chat", None)

                    if entity is not None:
                        item = make_entry(source, entity)
                        entries = merge_entry(entries, item)

                        config_ids.add(sid)
                        state["pending"] = [
                            x
                            for x in state["pending"]
                            if x != sid
                        ]

                        added += 1
                        save_progress(entries, state)

                        print(
                            f"STATUS=PENDING_APPROVED "
                            f"chat_id={item['chat_id']}"
                        )

                    else:
                        print("STATUS=PENDING_APPROVAL")
                        pending_count += 1

                except StopRun:
                    raise

                except (
                    InviteHashExpiredError,
                    InviteHashInvalidError,
                ) as exc:
                    print(
                        f"STATUS=INVALID_INVITE "
                        f"error={type(exc).__name__}"
                    )

                    state["invalid"] = sorted(
                        set(state["invalid"]) | {sid}
                    )

                    state["pending"] = [
                        x
                        for x in state["pending"]
                        if x != sid
                    ]

                    save_progress(entries, state)

                except Exception as exc:
                    print(
                        f"STATUS=PENDING_CHECK_ERROR "
                        f"error={type(exc).__name__}"
                    )

                    state["errors"][sid] = {
                        "type": type(exc).__name__,
                        "text": str(exc),
                        "at": utcnow(),
                    }

                    save_progress(entries, state)

                continue

            if sid in state["invalid"]:
                print("STATUS=SKIP_INVALID_INVITE")
                skipped += 1
                continue

            # --------------------------------------------------------
            # PUBLIC CHAT
            # --------------------------------------------------------

            if link_type == "public":
                try:
                    entity = await tg_call(
                        f"resolve:{sid}",
                        lambda: client.get_entity(target),
                    )

                except StopRun:
                    raise

                except Exception as exc:
                    errors += 1

                    print(
                        f"STATUS=RESOLVE_ERROR "
                        f"error={type(exc).__name__}"
                    )

                    state["errors"][sid] = {
                        "type": type(exc).__name__,
                        "text": str(exc),
                        "at": utcnow(),
                    }

                    save_progress(entries, state)
                    continue

                peer_id = get_peer_id(entity)

                # We may already be a member even if username wasn't
                # present in the first dialog map.
                if peer_id in dialog_by_id:
                    item = make_entry(source, entity)
                    entries = merge_entry(entries, item)

                    config_ids.add(sid)
                    added += 1
                    save_progress(entries, state)

                    print(
                        f"STATUS=RECOVERED_EXISTING "
                        f"chat_id={peer_id}"
                    )

                    continue

                join_count += 1

                try:
                    await tg_call(
                        f"join_public:{sid}",
                        lambda: client(
                            JoinChannelRequest(entity)
                        ),
                    )

                    item = make_entry(source, entity)
                    entries = merge_entry(entries, item)

                    config_ids.add(sid)
                    dialog_by_id[peer_id] = entity

                    username = getattr(
                        entity,
                        "username",
                        None,
                    )

                    if username:
                        dialog_by_username[
                            username.lower()
                        ] = entity

                    added += 1
                    save_progress(entries, state)

                    print(
                        f"STATUS=JOINED "
                        f"chat_id={peer_id}"
                    )

                except InviteRequestSentError:
                    state["pending"] = sorted(
                        set(state["pending"]) | {sid}
                    )

                    pending_count += 1
                    save_progress(entries, state)

                    print("STATUS=PENDING_APPROVAL")

                except UserAlreadyParticipantError:
                    item = make_entry(source, entity)
                    entries = merge_entry(entries, item)

                    config_ids.add(sid)
                    added += 1
                    save_progress(entries, state)

                    print(
                        f"STATUS=ALREADY_MEMBER "
                        f"chat_id={peer_id}"
                    )

                except StopRun:
                    raise

                except RPCError as exc:
                    errors += 1

                    print(
                        f"STATUS=RPC_ERROR "
                        f"error={type(exc).__name__}"
                    )

                    state["errors"][sid] = {
                        "type": type(exc).__name__,
                        "text": str(exc),
                        "at": utcnow(),
                    }

                    save_progress(entries, state)

                except Exception as exc:
                    errors += 1

                    print(
                        f"STATUS=ERROR "
                        f"error={type(exc).__name__}"
                    )

                    state["errors"][sid] = {
                        "type": type(exc).__name__,
                        "text": str(exc),
                        "at": utcnow(),
                    }

                    save_progress(entries, state)

                await cooldown(join_count)
                continue

            # --------------------------------------------------------
            # PRIVATE INVITE
            # --------------------------------------------------------

            try:
                info = await tg_call(
                    f"check_private:{sid}",
                    lambda: client(
                        CheckChatInviteRequest(target)
                    ),
                )

                existing_entity = getattr(
                    info,
                    "chat",
                    None,
                )

                if existing_entity is not None:
                    item = make_entry(
                        source,
                        existing_entity,
                    )

                    entries = merge_entry(
                        entries,
                        item,
                    )

                    config_ids.add(sid)
                    added += 1

                    save_progress(entries, state)

                    print(
                        f"STATUS=ALREADY_MEMBER "
                        f"chat_id={item['chat_id']}"
                    )

                    continue

            except StopRun:
                raise

            except (
                InviteHashExpiredError,
                InviteHashInvalidError,
            ) as exc:
                print(
                    f"STATUS=INVALID_INVITE "
                    f"error={type(exc).__name__}"
                )

                state["invalid"] = sorted(
                    set(state["invalid"]) | {sid}
                )

                save_progress(entries, state)
                continue

            except Exception as exc:
                # A failed CHECK is not enough reason to discard
                # the source. We can still attempt the actual import.
                print(
                    f"STATUS=CHECK_WARNING "
                    f"error={type(exc).__name__}"
                )

            before_by_id, _ = await get_dialogs(client)
            before_ids = set(before_by_id)

            join_count += 1

            try:
                result = await tg_call(
                    f"join_private:{sid}",
                    lambda: client(
                        ImportChatInviteRequest(target)
                    ),
                )

                # Correct handling for ChatInviteJoinResultOk:
                # result.updates.chats
                entity = extract_joined_entity(result)

                # Fallback if Telegram/Telethon changes response shape.
                if entity is None:
                    await asyncio.sleep(2)

                    after_by_id, _ = await get_dialogs(client)

                    new_ids = (
                        set(after_by_id)
                        - before_ids
                    )

                    if len(new_ids) == 1:
                        entity = after_by_id[
                            next(iter(new_ids))
                        ]

                if entity is None:
                    print(
                        "STATUS=JOINED_BUT_ENTITY_UNKNOWN"
                    )

                    state["errors"][sid] = {
                        "type": "JoinedButEntityUnknown",
                        "text": (
                            "Join succeeded but entity "
                            "could not be identified"
                        ),
                        "at": utcnow(),
                    }

                    save_progress(entries, state)

                else:
                    item = make_entry(source, entity)
                    entries = merge_entry(entries, item)

                    config_ids.add(sid)
                    added += 1

                    save_progress(entries, state)

                    print(
                        f"STATUS=JOINED "
                        f"chat_id={item['chat_id']}"
                    )

            except InviteRequestSentError:
                state["pending"] = sorted(
                    set(state["pending"]) | {sid}
                )

                pending_count += 1
                save_progress(entries, state)

                print("STATUS=PENDING_APPROVAL")

            except UserAlreadyParticipantError:
                try:
                    info = await tg_call(
                        f"resolve_existing_private:{sid}",
                        lambda: client(
                            CheckChatInviteRequest(
                                target
                            )
                        ),
                    )

                    entity = getattr(
                        info,
                        "chat",
                        None,
                    )

                    if entity is not None:
                        item = make_entry(
                            source,
                            entity,
                        )

                        entries = merge_entry(
                            entries,
                            item,
                        )

                        config_ids.add(sid)
                        added += 1

                        save_progress(
                            entries,
                            state,
                        )

                        print(
                            f"STATUS=ALREADY_MEMBER "
                            f"chat_id={item['chat_id']}"
                        )

                    else:
                        print(
                            "STATUS=ALREADY_MEMBER_"
                            "ENTITY_UNKNOWN"
                        )

                except StopRun:
                    raise

                except Exception as exc:
                    errors += 1

                    print(
                        f"STATUS=RESOLVE_ERROR "
                        f"error={type(exc).__name__}"
                    )

            except (
                InviteHashExpiredError,
                InviteHashInvalidError,
            ) as exc:
                state["invalid"] = sorted(
                    set(state["invalid"]) | {sid}
                )

                save_progress(entries, state)

                print(
                    f"STATUS=INVALID_INVITE "
                    f"error={type(exc).__name__}"
                )

            except StopRun:
                raise

            except RPCError as exc:
                errors += 1

                state["errors"][sid] = {
                    "type": type(exc).__name__,
                    "text": str(exc),
                    "at": utcnow(),
                }

                save_progress(entries, state)

                print(
                    f"STATUS=RPC_ERROR "
                    f"error={type(exc).__name__}"
                )

            except Exception as exc:
                errors += 1

                state["errors"][sid] = {
                    "type": type(exc).__name__,
                    "text": str(exc),
                    "at": utcnow(),
                }

                save_progress(entries, state)

                print(
                    f"STATUS=ERROR "
                    f"error={type(exc).__name__}"
                )

            await cooldown(join_count)

    except StopRun:
        pass

    except BaseException:
        print()
        print("FATAL_EXCEPTION=1")
        traceback.print_exc()

    finally:
        save_progress(entries, state)

        try:
            await client.disconnect()
        except Exception:
            pass

    print()
    print("=" * 60)
    print(f"CONFIG_ENTRIES={len(entries)}")
    print(f"ADDED_THIS_RUN={added}")
    print(f"JOIN_REQUESTS={join_count}")
    print(f"PENDING_THIS_RUN={pending_count}")
    print(f"SKIPPED={skipped}")
    print(f"ERRORS={errors}")
    print(f"PENDING_TOTAL={len(state['pending'])}")
    print(f"INVALID_TOTAL={len(state['invalid'])}")
    print(f"OUTPUT={OUTPUT_PATH}")
    print(f"STATE={STATE_PATH}")

    if state["last_flood_wait"]:
        print(
            "LAST_FLOOD_WAIT_SECONDS="
            f"{state['last_flood_wait']['seconds']}"
        )


if __name__ == "__main__":
    asyncio.run(main())