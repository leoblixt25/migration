"""
telegram_bot.py
Polls Telegram for bot commands using native offset acknowledgment.
Run every 5 minutes by GitHub Actions.

How it works:
  - getUpdates returns only UNACKNOWLEDGED messages (Telegram tracks this server-side)
  - After processing each message, we acknowledge it by calling getUpdates with offset+1
  - No timestamp filtering needed — Telegram handles deduplication natively
  - Cannot miss messages, cannot replay messages

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
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def tg_request(method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read())
    if not result.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {result}")
    return result


def get_updates(offset: int = None) -> list:
    payload = {"timeout": 5, "limit": 100, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    result = tg_request("getUpdates", payload)
    updates = result.get("result", [])
    print(f"getUpdates → {len(updates)} update(s)")
    return updates


def acknowledge(update_id: int) -> None:
    """Tell Telegram we've processed this update. It will never be returned again."""
    tg_request("getUpdates", {"offset": update_id +
               1, "timeout": 0, "limit": 1})
    print(f"Acknowledged update_id={update_id}")


async def process_message(update_id: int, msg: dict) -> None:
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = (msg.get("text") or "").strip()
    print(f"  chat_id={chat_id} text={text!r}")

    # Security: ignore messages not from your own chat
    if chat_id != str(TELEGRAM_CHAT_ID):
        print(f"  → Ignoring (unknown chat)")
        return

    cmd = text.lower()

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


async def main() -> None:
    updates = get_updates()

    if not updates:
        print("No pending updates.")
        return

    for update in updates:
        update_id = update["update_id"]
        msg = update.get("message") or update.get("edited_message")

        print(f"\nProcessing update_id={update_id}")

        try:
            if msg:
                await process_message(update_id, msg)
        except Exception as e:
            import traceback
            traceback.print_exc()
            # Try to notify the user about the error
            chat_id = str((msg or {}).get(
                "chat", {}).get("id", TELEGRAM_CHAT_ID))
            try:
                send_telegram(
                    "⚠️ <b>Error during check</b>\n"
                    f"<code>{e}</code>\n\n"
                    f'👉 <a href="{BOOKING_URL}">Check manually</a>',
                    chat_id,
                )
            except Exception:
                pass
        finally:
            # ALWAYS acknowledge, even on error, so we don't get stuck in a loop
            acknowledge(update_id)

    print("\n✓ All updates processed.")


if __name__ == "__main__":
    print("Starting Telegram bot...")
    asyncio.run(main())
    print("Done.")
