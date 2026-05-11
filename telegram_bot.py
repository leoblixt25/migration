"""
telegram_bot.py
Polls Telegram for bot commands. Designed to be run every 5 minutes
by GitHub Actions.

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
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
MAX_AGE_SECONDS = 600   # 10 min — covers GitHub Actions scheduling delays


def tg_api(method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
        print(
            f"Telegram API {method} → ok={result.get('ok')} count={len(result.get('result', []))}")
        return result


def get_updates() -> list:
    result = tg_api("getUpdates", {"timeout": 5, "limit": 50})
    return result.get("result", [])


def confirm_offset(update_id: int) -> None:
    """Tell Telegram we've seen everything up to and including update_id."""
    tg_api("getUpdates", {"offset": update_id + 1, "timeout": 0, "limit": 1})
    print(f"Confirmed offset past update_id={update_id}")


def get_pending_commands() -> list[tuple[int, dict]]:
    """
    Returns list of (update_id, message) for recent valid commands.

    Key rule: valid commands are NEVER confirmed here.
    Only junk (too old / wrong chat) that appears BEFORE the first valid
    command is confirmed — Telegram offsets are sequential so we can't
    skip past a valid command we haven't processed yet.
    """
    updates = get_updates()
    now = time.time()

    valid = []   # (update_id, msg) to process
    junk_ids = []  # update_ids safe to discard

    for update in updates:
        uid = update.get("update_id")
        msg = update.get("message") or update.get("edited_message")

        if not msg:
            junk_ids.append(uid)
            continue

        age = now - msg.get("date", 0)
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "")
        print(f"  update_id={uid} age={age:.0f}s chat={chat_id} text={text!r}")

        is_old = age > MAX_AGE_SECONDS
        is_wrong_chat = chat_id != str(TELEGRAM_CHAT_ID)

        if is_old or is_wrong_chat:
            reason = "too old" if is_old else "wrong chat"
            print(f"  → discard ({reason})")
            junk_ids.append(uid)
        else:
            print(f"  → valid command")
            valid.append((uid, msg))

    # Confirm junk that sits entirely before the first valid command.
    # We must not skip ahead of unprocessed valid commands.
    if junk_ids:
        if valid:
            first_valid_uid = valid[0][0]
            safe_junk = [j for j in junk_ids if j < first_valid_uid]
        else:
            safe_junk = junk_ids

        if safe_junk:
            confirm_offset(max(safe_junk))

    print(f"Pending valid commands: {len(valid)}")
    return valid


async def handle_commands() -> None:
    try:
        commands = get_pending_commands()

        if not commands:
            print("No commands to process.")
            return

        for uid, msg in commands:
            text = (msg.get("text") or "").strip().lower()
            chat_id = str(msg["chat"]["id"])
            print(f"\nProcessing update_id={uid}: '{text}' from {chat_id}")

            try:
                if text.startswith("/check"):
                    send_telegram(
                        "🔍 <b>Checking for appointments...</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        "🏛 Embassy of Sweden in Bangkok\n"
                        "📋 Swedish passport / ID document\n\n"
                        "⏳ This takes about 15 seconds, hang tight!",
                        chat_id,
                    )
                    result = await run_check()
                    print(f"Check result: available={result['available']}")

                    if result["available"]:
                        send_telegram(
                            "🇸🇪 <b>Passport Appointment Available!</b>\n"
                            "━━━━━━━━━━━━━━━━━━━━━━\n"
                            "🏛 Embassy of Sweden in Bangkok\n"
                            "📋 Swedish passport / ID document\n\n"
                            "⚡️ Slots may be open — act fast, they go quickly!\n\n"
                            f'👉 <a href="{BOOKING_URL}">Book your appointment now</a>',
                            chat_id,
                        )
                    else:
                        send_telegram(
                            "❌ <b>No appointments available</b>\n"
                            "━━━━━━━━━━━━━━━━━━━━━━\n"
                            "🏛 Embassy of Sweden in Bangkok\n"
                            "📋 Swedish passport / ID document\n\n"
                            "I'll keep checking daily at 08:00 and alert you the moment slots open.\n\n"
                            f'👉 <a href="{BOOKING_URL}">Check manually</a>',
                            chat_id,
                        )

                elif text.startswith("/help"):
                    send_telegram(
                        "🤖 <b>Passport Appointment Bot</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        "🏛 Embassy of Sweden in Bangkok\n"
                        "📋 Swedish passport / ID document\n\n"
                        "<b>Commands</b>\n"
                        "/check — Check for slots right now\n"
                        "/help  — Show this message\n\n"
                        "🕗 Automatic daily check runs at 08:00.\n"
                        "You'll be alerted immediately if slots open.\n\n"
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
                send_telegram(
                    "⚠️ <b>Check failed</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Error: <code>{e}</code>\n\n"
                    f'👉 <a href="{BOOKING_URL}">Check manually</a>',
                    chat_id,
                )

            # Confirm AFTER the command is fully handled
            confirm_offset(uid)

    except Exception as e:
        import traceback
        print(f"FATAL ERROR in handle_commands: {e}")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    print("Starting Telegram bot command handler...")
    asyncio.run(handle_commands())
    print("✓ Done")
