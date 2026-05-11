"""
telegram_bot.py — Render deployment version
Runs as a persistent long-polling loop. Responds to commands within seconds.

Commands:
  /check  — run an appointment check and reply with result
  /help   — show available commands
"""

import asyncio
import json
import os
import urllib.request
from check_appointments import run_check, send_telegram, BOOKING_URL

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]


def tg_request(method: str, payload: dict) -> dict:
    url  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        result = json.loads(resp.read())
    if not result.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {result}")
    return result


def get_updates(offset: int = None) -> list:
    payload = {"timeout": 30, "limit": 100, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    result = tg_request("getUpdates", payload)
    return result.get("result", [])


async def process_message(msg: dict) -> None:
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text    = (msg.get("text") or "").strip()
    cmd     = text.lower()

    if chat_id != str(TELEGRAM_CHAT_ID):
        print(f"Ignored message from unknown chat: {chat_id}")
        return

    print(f"Command: {text!r} from {chat_id}")

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


async def poll_loop() -> None:
    """Long-polling loop — runs forever on Render."""
    offset = None
    print("Bot started. Listening for commands...")

    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                uid = update["update_id"]
                offset = uid + 1  # advance offset so this update is never seen again
                msg = update.get("message") or update.get("edited_message")
                if msg:
                    try:
                        await process_message(msg)
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        chat_id = str(msg.get("chat", {}).get("id", TELEGRAM_CHAT_ID))
                        try:
                            send_telegram(
                                "⚠️ <b>Error during check</b>\n"
                                f"<code>{e}</code>\n\n"
                                f'👉 <a href="{BOOKING_URL}">Check manually</a>',
                                chat_id,
                            )
                        except Exception:
                            pass
        except Exception as e:
            print(f"Polling error: {e} — retrying in 5s")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(poll_loop())
