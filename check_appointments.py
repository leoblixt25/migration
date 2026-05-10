"""
check_appointments.py
Core appointment-check logic. Can be imported or run directly.
"""

import asyncio
import json
import os
import urllib.request
from playwright.async_api import async_playwright

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

BOOKING_URL = (
    "https://www.migrationsverket.se/ansokanbokning/valjtyp"
    "?3&enhet=U0095&sprak=en&callback=https:/www.swedenabroad.se"
)
NO_AVAILABILITY_TEXT = "At the moment, there are no available time slots."


def send_telegram(message: str, chat_id: str = None) -> None:
    """Send a Telegram message. Uses TELEGRAM_CHAT_ID if chat_id not provided."""
    try:
        target = chat_id or TELEGRAM_CHAT_ID
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": target,
            "text": message,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"Telegram → {resp.status}")
    except Exception as e:
        print(f"ERROR sending Telegram message: {e}")
        import traceback
        traceback.print_exc()


async def run_check() -> dict:
    """
    Navigates the booking form and returns:
      { "available": bool, "page_text": str }
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )

        print(f"Opening: {BOOKING_URL}")
        await page.goto(BOOKING_URL, wait_until="networkidle", timeout=30_000)

        # Find the dropdown that contains passport options
        selects = page.locator("select")
        count = await selects.count()
        passport_select = None
        for i in range(count):
            if "pass" in (await selects.nth(i).inner_html()).lower():
                passport_select = selects.nth(i)
                break
        if passport_select is None:
            raise RuntimeError("Could not find the reason dropdown")

        await passport_select.select_option(label="apply for Swedish passport or id document")
        await page.wait_for_timeout(1000)
        try:
            await page.wait_for_response(
                lambda resp: "viseringstyp.border" in resp.url and resp.status == 200,
                timeout=10_000,
            )
        except Exception:
            pass

        # Set persons = 1
        try:
            antal = page.locator("select").filter(has_text="1")
            if await antal.count() > 0:
                await antal.first.select_option(value="1")
                await page.wait_for_timeout(500)
        except Exception:
            pass

        # Tick confirmation checkbox
        cb = page.locator("input[type='checkbox']")
        if await cb.count() > 0 and not await cb.is_checked():
            await cb.check()
            await page.wait_for_timeout(500)

        # Click continue / next
        await page.locator(
            "input[value='Fortsätt'], input[value='Next'], button:has-text('Fortsätt'), button:has-text('Next')"
        ).first.click()
        await page.wait_for_load_state("networkidle", timeout=30_000)
        await page.wait_for_timeout(1000)

        page_text = await page.inner_text("body")
        still_on_selection_page = (
            await page.locator(
                "select:has-text('ansöka om svenskt pass/id-handlingar'),"
                "select:has-text('apply for Swedish passport or id document')"
            ).count()
        ) > 0
        await browser.close()

    if still_on_selection_page:
        available = False
        print("Still on selection page after submit; assuming no availability.")
    else:
        available = NO_AVAILABILITY_TEXT not in page_text

    print(f"Available: {available}")
    print(f"Page snippet: {page_text[:300]}")
    return {"available": available, "page_text": page_text}


async def main():
    result = await run_check()
    if result["available"]:
        send_telegram(
            "🇸🇪 <b>Passport Appointment Available!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🏛 Embassy of Sweden in Bangkok\n"
            "📋 Reason: Swedish passport / ID document\n\n"
            "⚡️ Slots may be open — act fast, they go quickly!\n\n"
            f'👉 <a href="{BOOKING_URL}">Book your appointment now</a>'
        )
    else:
        print("No appointments — no alert sent.")


if __name__ == "__main__":
    asyncio.run(main())
