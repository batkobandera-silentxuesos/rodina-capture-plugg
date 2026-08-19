import asyncio
import base64
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from config import BOT_TOKEN, CHAT_ID, GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPOSITORY, GITHUB_BRANCH, POLL_INTERVAL

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"
MOSCOW = ZoneInfo("Europe/Moscow")

dp = Dispatcher()


def load_state():
    if not STATE_FILE.exists():
        return set()
    try:
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_state(state):
    STATE_FILE.write_text(json.dumps(sorted(state), ensure_ascii=False), encoding="utf-8")


async def github_request(session, method, url):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "RodinaCaptureBot"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    async with session.request(method, url, headers=headers) as response:
        response.raise_for_status()
        return await response.json()


async def get_event_files(session):
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/contents/events?ref={GITHUB_BRANCH}"
    data = await github_request(session, "GET", url)
    return [item for item in data if item.get("type") == "file" and item.get("name", "").endswith(".json")]


async def get_event(session, url):
    data = await github_request(session, "GET", url)
    content = data.get("content", "").replace("\n", "")
    return json.loads(base64.b64decode(content).decode("utf-8"))


def format_event(event):
    start = datetime.strptime(
        f'{event["date"]} {event["time"]}',
        "%Y-%m-%d %H:%M:%S"
    ).replace(tzinfo=MOSCOW)

    registration_start = start + timedelta(minutes=5)
    registration_end = start + timedelta(minutes=10)
    end = start + timedelta(minutes=20)

    return (
        f'<b>🟠 ЗАХВАТ | #{int(event["territory"])}</b>\n\n'
        f'⏳\n'
        f'<b>├ Начало: {start:%H:%M:%S}</b>\n'
        f'<b>├ Регистрация: {registration_start:%H:%M:%S} - {registration_end:%H:%M:%S}</b>\n'
        f'<b>└ Конец: {end:%H:%M:%S}</b>\n\n'
        f'ℹ️\n'
        f'<b>└ Сервер: {event["server"]}</b>'
    )


async def send_event(bot, event):
    await bot.send_message(CHAT_ID, format_event(event), parse_mode=ParseMode.HTML)


async def monitor(bot):
    state = load_state()
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            try:
                files = await get_event_files(session)
                for file in sorted(files, key=lambda item: item["name"]):
                    event_id = file["name"]
                    if event_id in state:
                        continue
                    event = await get_event(session, file["url"])
                    await send_event(bot, event)
                    state.add(event_id)
                    save_state(state)
            except Exception:
                pass
            await asyncio.sleep(POLL_INTERVAL)


async def main():
    bot = Bot(BOT_TOKEN)
    try:
        await asyncio.gather(
            dp.start_polling(bot),
            monitor(bot)
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
