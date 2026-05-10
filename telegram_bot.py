"""
telegram_bot.py
Polls Telegram for bot commands. Designed to be run every 5 minutes
by GitHub Actions. Only processes messages from the last 6 minutes
to avoid re-handling old commands across runs.

Supported commands:
  /check  — run an appointment check immediately and reply with the result
  /help   — show available commands
"""

import asyncio
import json
import os
import time
import urllib.request
from check_appointments import run_check, send_telegram, BOOKING_URL

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]   # your authorised chat ID
MAX_AGE_SECONDS = 1800   # ignore messages older than 30 minutes


def tg_api(method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
        print(
            f"Telegram API {method} returned ok={result.get('ok')} result_count={len(result.get('result', []))}")
        return result


def get_recent_updates() -> list:
    """Fetch updates from the last MAX_AGE_SECONDS only."""
    result = tg_api("getUpdates", {"timeout": 5, "limit": 50})
    print(
        f"Telegram getUpdates returned {len(result.get('result', []))} updates")
    now = time.time()
    recent = []
    for update in result.get("result", []):
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            continue
        age = now - msg.get("date", 0)
        chat_id = msg.get("chat", {}).get("id")
        print(
            f"update_id={update.get('update_id')} chat={chat_id} age={age:.1f}s text={msg.get('text')!r}"
        )
        if age > MAX_AGE_SECONDS:
            print("Ignoring old update")
            continue
        # Security: only accept commands from your own chat ID
        if str(chat_id) != str(TELEGRAM_CHAT_ID):
            print(f"Ignoring message from unknown chat: {chat_id}")
            continue
        recent.append(msg)
    print(f"Found {len(recent)} recent command(s) from authorized chat")
    return recent


async def handle_commands():
    updates = get_recent_updates()

    if not updates:
        print("No recent commands.")
        return

    for msg in updates:
        text = (msg.get("text") or "").strip().lower()
        chat_id = str(msg["chat"]["id"])
        print(f"Received: '{text}' from chat {chat_id}")

        if text.startswith("/check"):
            send_telegram(
                "🔍 Running appointment check... please wait.", chat_id)
            try:
                result = await run_check()
                if result["available"]:
                    send_telegram(
                        "✅ <b>Appointments may be available!</b>\n\n"
                        f'👉 <a href="{BOOKING_URL}">Book now</a>',
                        chat_id,
                    )
                else:
                    send_telegram(
                        "❌ No appointments available right now.\n"
                        "I'll keep checking daily and alert you when slots open.",
                        chat_id,
                    )
            except Exception as e:
                send_telegram(
                    f"⚠️ Check failed with error:\n<code>{e}</code>", chat_id)

        elif text.startswith("/help"):
            send_telegram(
                "🤖 <b>Available commands</b>\n\n"
                "/check — Check for passport appointment slots right now\n"
                "/help  — Show this message\n\n"
                "I also run an automatic check every day at 08:00 and "
                "will message you if slots become available.",
                chat_id,
            )

        else:
            send_telegram(
                f"Unknown command: <code>{text}</code>\nSend /help to see available commands.",
                chat_id,
            )


if __name__ == "__main__":
    asyncio.run(handle_commands())
