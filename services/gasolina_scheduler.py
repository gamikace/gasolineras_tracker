import asyncio
import json
import os
from datetime import date
from logger import logger
from config import IS_PROD, DEV_CHAT_ID, ADHOC_CHAT_ID
from services.gasolina_scraper import (
    fetch_spain_cheapest,
    fetch_zaragoza_cheapest,
    fetch_top_stations,
    format_combined_telegram,
    format_cheapest_x,
)
from publishers.telegram_publisher import send_telegram_photo
from publishers.x_publisher import send_x_text_with_image, send_x_text

STATE_FILE     = "data/gasolina_state.json"
IMG_ZARAGOZA   = "data/image_zaragoza.jpg"
IMG_ESPAÑA     = "data/image_españa.jpg"


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_state(state: dict) -> None:
    os.makedirs("data", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _already_sent_today(state: dict, key: str) -> bool:
    return state.get(key) == date.today().isoformat()


def _mark_sent(state: dict, key: str) -> None:
    state[key] = date.today().isoformat()


async def run_gasolina_daily(ctx) -> None:
    app = ctx.application
    state = _load_state()
    chat_id = str(ADHOC_CHAT_ID if IS_PROD else DEV_CHAT_ID)

    print("entro")

    # ── 1. España más barata → X con imagen ──────────────────
    if not _already_sent_today(state, "spain_x"):
        try:
            spain_data = await fetch_spain_cheapest()
            if spain_data:
                text_x = await format_cheapest_x(spain_data, "España")
                if IS_PROD:
                    await send_x_text_with_image(text_x, IMG_ESPAÑA)
                else:
                    logger.info(f"[Gasolina/DEV] X España:\n{text_x}")
                _mark_sent(state, "spain_x")
        except Exception as e:
            logger.error(f"[Gasolina] Error España: {e}", exc_info=True)

    # ── 2. Zaragoza: mensaje combinado Telegram + X ───────────
    if not _already_sent_today(state, "zgza_combined"):
        try:
            zgza_data, top_data = await asyncio.gather(
                fetch_zaragoza_cheapest(),
                fetch_top_stations(),
            )
            if zgza_data:
                text_tg = format_combined_telegram(zgza_data, top_data, "Zaragoza")
                text_x  = await format_cheapest_x(zgza_data, "Zaragoza")

                await send_telegram_photo(app, chat_id, None, text_tg, IMG_ZARAGOZA)
                if IS_PROD:
                    await send_x_text(text_x)   # X sin imagen (ya tiene España con imagen)
                else:
                    logger.info(f"[Gasolina/DEV] X Zaragoza:\n{text_x}")

                _mark_sent(state, "zgza_combined")
        except Exception as e:
            logger.error(f"[Gasolina] Error Zaragoza: {e}", exc_info=True)

    _save_state(state)
