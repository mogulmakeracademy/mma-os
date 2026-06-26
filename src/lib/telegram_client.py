"""Telegram bot send wrapper — single function: send_message()."""
from __future__ import annotations

import os

import httpx


def send_message(text: str, *, parse_mode: str = "HTML") -> dict:
    """Send a Telegram message to Antonio's configured chat."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4096],  # Telegram hard cap
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    with httpx.Client(timeout=15.0) as c:
        res = c.post(url, json=payload)
        res.raise_for_status()
        return res.json()
