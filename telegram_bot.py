"""
telegram_bot.py
Polls Telegram for bot commands. Run every 5 minutes by GitHub Actions.

Commands:
  /check  — run an appointment check and reply with result
  /help   — show available commands
"""

import asyncio
import json
import os
import time
import urllib.request
from check_appointments import run_check, send_telegram, BOOKING_URL

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
MAX_AGE_SECONDS = 600  # 10 min window — safely longer than the 5-min cron interval


def tg_api(method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
    print(f"Telegram {method} → ok={result.get('ok')}")
    return result


def get_recent_updates() -> list:
    """
    Fetch all pending updates, acknowledge ALL of them (so they never pile up),
    and return only the ones that are recent + from the authorised chat.
    """
    result = tg_api("getUpdates", {"timeout": 5, "limit": 100})
    updates = result.get("result", [])
    now = time.time()
    recent = []
    max_id = None

    for update in updates:
        uid = update.get("update_id")
        if max_id is None or uid > max_id:
            max_id = uid

        msg = update.get("message") or update.get("edited_message")
        if not msg:
            continue

        age = now - msg.get("date", 0)
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "")
        print(f"  update_id={uid} age={age:.0f}s chat={chat_id} text={text!r}")

        if age > MAX_AGE_SECONDS:
            print("  → too old, skipping")
            continue

        if chat_id != str(TELEGRAM_CHAT_ID):
            print(f"  → wrong chat, skipping")
            continue

        print("  → queued for processing")
        recent.append(msg)

    # Acknowledge everything so the queue stays clean
    if max_id is not None:
        tg_api("getUpdates", {"offset": max_id + 1, "timeout": 0, "limit": 1})
        print(f"Acknowledged all updates through {max_id}")

    print(f"Found {len(recent)} command(s) to process")
    return recent


async def handle_commands() -> None:
    updates = get_recent_updates()

    if not updates:
        print("No commands to process.")
        return

    for msg in updates:
        chat_id = str(msg["chat"]["id"])
        text = (msg.get("text") or "").strip()
        cmd = text.lower()
        print(f"\nHandling: {text!r} from {chat_id}")

        try:
            if cmd.startswith("/check"):
                send_telegram(
                    "🔍 <b>Checking for appointments...</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "🏛 Embassy of Sweden in Bangkok\n"
                    "📋 Swedish passport / ID document\n\n"
                    "⏳ This takes ~15 seconds, hang tight!",
                    chat_id,
                )
                result = await run_check()
                if result["available"]:
                    send_telegram(
                        "🇸🇪 <b>Passport Appointment Available!</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        "🏛 Embassy of Sweden in Bangkok\n"
                        "📋 Swedish passport / ID document\n\n"
                        "⚡️ Slots may be open — act fast!\n\n"
                        f'👉 <a href="{BOOKING_URL}">Book your appointment now</a>',
                        chat_id,
                    )
                else:
                    send_telegram(
                        "❌ <b>No appointments available</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        "🏛 Embassy of Sweden in Bangkok\n"
                        "📋 Swedish passport / ID document\n\n"
                        "I'll alert you automatically when slots open.\n\n"
                        f'👉 <a href="{BOOKING_URL}">Check manually</a>',
                        chat_id,
                    )

            elif cmd.startswith("/help"):
                send_telegram(
                    "🤖 <b>Passport Appointment Bot</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "🏛 Embassy of Sweden in Bangkok\n"
                    "📋 Swedish passport / ID document\n\n"
                    "<b>Commands</b>\n"
                    "/check — Check for slots right now\n"
                    "/help  — Show this message\n\n"
                    "🕗 Auto-check runs daily at 08:00.\n\n"
                    f'👉 <a href="{BOOKING_URL}">Booking page</a>',
                    chat_id,
                )

            else:
                send_telegram(
                    f"❓ Unknown command: <code>{text}</code>\n\n"
                    "Send /help to see available commands.",
                    chat_id,
                )

        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                send_telegram(
                    "⚠️ <b>Error during check</b>\n"
                    f"<code>{e}</code>\n\n"
                    f'👉 <a href="{BOOKING_URL}">Check manually</a>',
                    chat_id,
                )
            except Exception:
                pass


if __name__ == "__main__":
    print("Starting Telegram bot...")
    asyncio.run(handle_commands())
    print("Done.")
