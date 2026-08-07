"""Монитор сообщества VK: новые сообщения и комментарии → в Telegram.

Сообщения читаются токеном сообщества, комментарии — пользовательским: на
`wall.*` VK групповой токен не пускает («method is unavailable with group auth»).

Long Poll в настройках сообщества выключен, поэтому просто опрашиваем по таймеру —
для наших объёмов разницы нет, а включать ничего не надо.

Состояние (какие id уже видели) лежит в JSON рядом с базой: отдельная таблица
ради двух чисел не нужна.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import requests

from .. import config
from . import notify

log = logging.getLogger(__name__)

API = "https://api.vk.com/method"
V = "5.199"
STATE = config.DATA_DIR / "vk_monitor.json"
WALL_POSTS = 5          # сколько последних постов проверять на новые комментарии
DRAFT_LIMIT = 3         # больше черновиков за прогон не генерим — это лишние токены


def configured() -> bool:
    return bool(config.VK_TOKEN and config.VK_GROUP_ID)


def _gid() -> str:
    return str(config.VK_GROUP_ID).lstrip("-")


def _call(method: str, token: str, **params):
    params.update({"access_token": token, "v": V})
    r = requests.get(f"{API}/{method}", params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"{method}: {data['error'].get('error_msg')}")
    return data["response"]


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def _name(user_id: int) -> str:
    if user_id <= 0:                       # сообщение от имени сообщества
        return "сообщество"
    try:
        u = _call("users.get", config.VK_TOKEN, user_ids=user_id)[0]
        return f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
    except Exception:
        return f"id{user_id}"


def _draft(question: str) -> Optional[str]:
    """Черновик ответа от Claude. Без диагнозов и обещаний — только по составу."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        r = client.messages.create(
            model=config.CLAUDE_MODEL, max_tokens=400,
            system=(
                "Ты отвечаешь от лица бренда БАДов POWERELIX в сообществе VK. "
                "Пиши коротко (2-4 предложения), по-русски, вежливо и по делу. "
                "НЕЛЬЗЯ: ставить диагнозы, обещать лечение, советовать при болезнях. "
                "Если вопрос про заболевание, приём лекарств, беременность или ГВ — "
                "коротко ответь по составу и отправь к врачу. "
                "Если не хватает данных о продукте — так и напиши, не выдумывай цифры."),
            messages=[{"role": "user", "content": f"Вопрос клиента:\n{question}"}])
        return "".join(b.text for b in r.content if b.type == "text").strip()
    except Exception as e:
        log.warning("черновик ответа не собрался: %s", e)
        return None


def _check_messages(st: dict, drafts_left: int) -> tuple[list[str], int]:
    """Новые входящие сообщения в диалогах сообщества."""
    out, seen = [], int(st.get("last_msg_id", 0))
    top = seen
    convs = _call("messages.getConversations", config.VK_TOKEN,
                  group_id=_gid(), count=20)["items"]
    for c in convs:
        lm = c.get("last_message") or {}
        mid = int(lm.get("id", 0))
        top = max(top, mid)
        if lm.get("out") or mid <= seen:    # наше же сообщение или уже видели
            continue
        peer = c["conversation"]["peer"]["id"]
        text = (lm.get("text") or "").strip() or "(вложение без текста)"
        msg = (f"<b>VK · новое сообщение</b>\n{_name(lm.get('from_id', peer))}\n\n"
               f"{text}\n\nhttps://vk.com/gim{_gid()}?sel={peer}")
        if drafts_left > 0:
            d = _draft(text)
            if d:
                msg += f"\n\n<b>Черновик ответа:</b>\n{d}"
                drafts_left -= 1
        out.append(msg)
    if top > seen:
        st["last_msg_id"] = top
    return out, drafts_left


def _check_comments(st: dict, drafts_left: int) -> tuple[list[str], int]:
    """Новые комментарии под последними постами сообщества."""
    if not config.VK_USER_TOKEN:
        return [], drafts_left
    out, seen = [], int(st.get("last_comment_id", 0))
    top = seen
    posts = _call("wall.get", config.VK_USER_TOKEN,
                  owner_id="-" + _gid(), count=WALL_POSTS)["items"]
    for p in posts:
        if not p.get("comments", {}).get("count"):
            continue
        items = _call("wall.getComments", config.VK_USER_TOKEN,
                      owner_id="-" + _gid(), post_id=p["id"],
                      count=20, sort="desc")["items"]
        for c in items:
            cid = int(c.get("id", 0))
            top = max(top, cid)
            if cid <= seen or int(c.get("from_id", 0)) < 0:   # свой же ответ
                continue
            text = (c.get("text") or "").strip() or "(вложение без текста)"
            msg = (f"<b>VK · новый комментарий</b>\n{_name(c.get('from_id', 0))}\n\n"
                   f"{text}\n\nhttps://vk.com/wall-{_gid()}_{p['id']}?reply={cid}")
            if drafts_left > 0:
                d = _draft(text)
                if d:
                    msg += f"\n\n<b>Черновик ответа:</b>\n{d}"
                    drafts_left -= 1
            out.append(msg)
    if top > seen:
        st["last_comment_id"] = top
    return out, drafts_left


def check(notify_tg: bool = True) -> int:
    """Один проход. Возвращает число новых сообщений и комментариев."""
    if not configured():
        return 0
    st = _load()
    first_run = not st                       # на первом запуске только запоминаем «дно»
    msgs, left = _check_messages(st, 0 if first_run else DRAFT_LIMIT)
    cmts, _ = _check_comments(st, left)
    _save(st)
    if first_run:
        log.info("vk_monitor: первый запуск — запомнил текущее состояние, "
                 "уведомления пойдут со следующего прохода")
        return 0
    items = msgs + cmts
    if notify_tg and notify.configured():
        for m in items:
            notify.send(m, thread=config.TG_THREAD_VK)   # своя тема сообщества
    if items:
        log.info("vk_monitor: новых сообщений %d, комментариев %d", len(msgs), len(cmts))
    return len(items)


def pending() -> list[dict]:
    """Диалоги, где последнее слово за клиентом — то есть без ответа."""
    if not configured():
        return []
    convs = _call("messages.getConversations", config.VK_TOKEN,
                  group_id=_gid(), count=50)["items"]
    res = []
    for c in convs:
        lm = c.get("last_message") or {}
        if lm.get("out"):
            continue
        peer = c["conversation"]["peer"]["id"]
        res.append({"peer": peer, "date": lm.get("date"),
                    "text": (lm.get("text") or "").strip(),
                    "url": f"https://vk.com/gim{_gid()}?sel={peer}"})
    return res
