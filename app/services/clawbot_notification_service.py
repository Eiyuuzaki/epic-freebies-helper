# -*- coding: utf-8 -*-
"""
ClawBot (WeChat ilink bot) notification service.

Delivers the Epic claim summary through the ilink bot sendmessage API — the
same channel used by every other automation in this household. Enabled when
both ``CLAWBOT_TOKEN`` and ``CLAWBOT_USERID`` are configured.

Success semantics: the API returns ``{"message_id": ...}`` with no ``ret``
field on success; failures return ``{"ret": -2, ...}`` without message_id.
Judge success as ``message_id present or ret == 0`` — never ``ret == 0`` alone.
"""

import asyncio
import json
import os
import random

import httpx
from loguru import logger

from services.epic_collection_summary_service import CollectionSummary
from services.wxpush_notification_service import build_wxpush_content, build_wxpush_title

ILINK_ENDPOINT = "https://ilinkai.weixin.qq.com/ilink/bot/sendmessage"


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def clawbot_notifications_enabled() -> bool:
    return bool(_env("CLAWBOT_TOKEN") and _env("CLAWBOT_USERID"))


async def send_collection_summary_to_clawbot(
    summary: CollectionSummary, *, account_label: str | None = None
) -> None:
    if not clawbot_notifications_enabled():
        logger.debug("ClawBot notification is not configured; skipping delivery")
        return

    try:
        text = build_wxpush_title(summary) + "\n" + build_wxpush_content(
            summary, account_label=account_label
        )
        token = _env("CLAWBOT_TOKEN")
        userid = _env("CLAWBOT_USERID")
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": str(random.randint(10**9, 2**31)),
            "iLink-App-Id": "bot",
            "iLink-App-ClientVersion": "132611",
            "Authorization": f"Bearer {token}",
        }
        msg = {
            "from_user_id": "",
            "to_user_id": userid,
            "client_id": f"epic-freebies-{random.randint(10**9, 10**10)}",
            "message_type": 2,
            "message_state": 2,
            "item_list": [{"type": 1, "text_item": {"text": text}}],
        }
        context_token = _env("CLAWBOT_CONTEXT_TOKEN")
        if context_token:
            msg["context_token"] = context_token
        body = {
            "msg": msg,
            "base_info": {
                "channel_version": "2.4.3",
                "bot_agent": "epic-freebies-helper/1.0",
            },
        }
        # httpx is async here; the ilink call is a plain POST so run it inline.
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.post(ILINK_ENDPOINT, content=json.dumps(body), headers=headers)
            response.raise_for_status()
            payload = response.json()
        ok = bool(payload.get("message_id")) or payload.get("ret", 0) == 0
        if ok:
            logger.info("ClawBot notification delivered")
        else:
            logger.warning("ClawBot notification rejected | ret={}", payload.get("ret"))
    except httpx.HTTPStatusError as err:
        logger.warning("ClawBot notification failed | status={}", err.response.status_code)
    except httpx.HTTPError as err:
        logger.warning("ClawBot notification failed | {}", err)
    except Exception as err:  # notification must never break the claim task
        logger.warning("ClawBot notification failed | {}", err)


def send_collection_summary_to_clawbot_sync(
    summary: CollectionSummary, *, account_label: str | None = None
) -> None:
    asyncio.run(send_collection_summary_to_clawbot(summary, account_label=account_label))
