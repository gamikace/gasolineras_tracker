# services/gasolina_scheduler.py
import asyncio
import json
import os
from datetime import date, datetime, timedelta
import pytz
import random

from logger import logger
from config import IS_PROD, DEV_CHAT_ID, ADHOC_CHAT_ID
from services.gasolina_scraper import (
    fetch_spain_cheapest,
    fetch_zaragoza_cheapest,
    fetch_top_stations,
    format_combined_telegram,
    format_cheapest_x,
)
from publishers.telegram_publisher import send_telegram_photo, edit_or_resend_photo, schedule_delayed_pin, unpin_telegram_message
from publishers.x_publisher import send_x_text_with_image, send_x_text


STATE_FILE   = "data/gasolina_state.json"
IMG_ZARAGOZA = "data/image_zaragoza.jpg"
IMG_ESPAÑA   = "data/image_españa.jpg"
MADRID_TZ    = pytz.timezone("Europe/Madrid")


# ── Estado ────────────────────────────────────────────────────

def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_state(state: dict) -> None:
    os.makedirs("data", exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, STATE_FILE)  # Atomic write — evita JSON corrupto
    except Exception as e:
        logger.error(f"[Gasolina] ❌ Error guardando estado: {e}")

def _today() -> str:
    return datetime.now(MADRID_TZ).date().isoformat()


def _already_sent_today(state: dict, key: str) -> bool:
    return state.get(key) == _today()


def _mark_sent(state: dict, key: str) -> None:
    state[key] = _today()


# ── Helpers de datos ──────────────────────────────────────────

def _normalize_price(price: str) -> str:
    """Normaliza precio: strip, espacios simples, € consistente."""
    return price.strip().replace("\u00a0", " ").replace("  ", " ")

def _serialize_data(zgza_data: dict, top_data: dict) -> dict:
    return {
        "zgza": {k: _normalize_price(v["precio"]) for k, v in zgza_data.items()},
        "top":  {
            station: {fuel: _normalize_price(price) for fuel, price in fuels.items()}
            for station, fuels in top_data.items()
        },
    }

def _data_changed(old: dict, new: dict) -> bool:
    """Compara si los precios han cambiado respecto al último snapshot."""
    return old != new


# ── Job 10:00 — envío diario ──────────────────────────────────

async def run_gasolina_daily(ctx) -> None:
    app   = ctx.application
    state = _load_state()
    chat_id = ADHOC_CHAT_ID if IS_PROD else DEV_CHAT_ID

    # ── 1. España → X con imagen ──────────────────────────────
    for attempt in range(1, 4):
        if _already_sent_today(state, "spain_x"):
            break
        try:
            logger.info(f"[Gasolina/Daily] España - Intento {attempt}")
            spain_data = await fetch_spain_cheapest()
            if spain_data:
                text_x = await format_cheapest_x(spain_data, "España")
                if IS_PROD:
                    await send_x_text_with_image(text_x, IMG_ESPAÑA)
                else:
                    logger.info(f"[Gasolina/DEV] X España:\n{text_x}")
                _mark_sent(state, "spain_x")
                _save_state(state)
                break
            else:
                logger.warning("[Gasolina/Daily] No hay datos de España, no se envía nada hoy.")
                break # Si no hay datos devueltos, no vale la pena reintentar, quizá el scraper falló al parsear pero no lanzó error.
        except Exception as e:
            logger.error(f"[Gasolina/Daily] Error España (Intento {attempt}): {e}")
            if attempt < 3:
                await asyncio.sleep(60 * 5) # 5 minutos de espera entre reintentos

    # ── 2. Zaragoza → Telegram (con imagen) + X ───────────────
    for attempt in range(1, 4):
        if _already_sent_today(state, "zgza_combined"):
            break
        try:
            logger.info(f"[Gasolina/Daily] Zaragoza - Intento {attempt}")
            zgza_data, top_data = await asyncio.gather(
                fetch_zaragoza_cheapest(),
                fetch_top_stations(),
            )
            if zgza_data:
                # Desfijar mensaje del día anterior antes de enviar el nuevo
                old_msg_id = state.get("zgza_message_id")
                if old_msg_id:
                    await unpin_telegram_message(app, chat_id, old_msg_id)

                text_tg = format_combined_telegram(zgza_data, top_data, "Zaragoza")
                text_x  = await format_cheapest_x(zgza_data, "Zaragoza")

                msg_id = await send_telegram_photo(app, chat_id, None, text_tg, IMG_ZARAGOZA)

                if IS_PROD:
                    await send_x_text(text_x)
                else:
                    logger.info(f"[Gasolina/DEV] X Zaragoza:\n{text_x}")

                # Programar el pin (no bloquea)
                if msg_id:
                    delay = random.choice([3, 4, 5])
                    schedule_delayed_pin(app, chat_id, msg_id, delay_hours=delay)

                _mark_sent(state, "zgza_combined")

                # Guardar message_id y snapshot de datos para updates horarios
                if msg_id:
                    state["zgza_message_id"]   = msg_id
                    state["zgza_message_date"]  = _today()
                    serialized = _serialize_data(zgza_data, top_data)
                    state["zgza_last_snapshot"] = serialized
                    state["zgza_initial_snapshot"] = serialized
                    _save_state(state)
                break
            else:
                logger.warning("[Gasolina/Daily] No hay datos de Zaragoza, no se envía nada hoy.")
                break # Evitamos bucle si el scraper devuelve null de manera válida
        except Exception as e:
            logger.error(f"[Gasolina/Daily] Error Zaragoza (Intento {attempt}): {e}")
            if attempt < 3:
                await asyncio.sleep(60 * 5) # 5 minutos de espera entre reintentos

    _save_state(state)


# ── Job horario — actualizar caption ─────────────────────────

async def run_gasolina_update(ctx) -> None:
    """
    Se ejecuta cada hora (11:00 → 09:00 del día siguiente).
    Edita el caption del post de Telegram con datos frescos.
    Siempre actualiza la hora; los datos solo si cambiaron.
    """
    app     = ctx.application
    state   = _load_state()
    chat_id = ADHOC_CHAT_ID if IS_PROD else DEV_CHAT_ID

    msg_id       = state.get("zgza_message_id")
    msg_date     = state.get("zgza_message_date")
    last_snapshot = state.get("zgza_last_snapshot", {})
    initial_snapshot = state.get("zgza_initial_snapshot", {})

    now_madrid = datetime.now(MADRID_TZ)
    hora_str   = now_madrid.strftime("%H:%M")

    # El post diario es a las 10:10.
    # Antes de las 10:00 (por ejemplo en el job de las 00:10 a 09:10), el post válido es el de ayer.
    # A partir de las 10:00, solo es válido el post de hoy.
    is_before_10am = now_madrid.hour < 10

    if is_before_10am:
        # Entre medianoche y las 09:59, se admite un post que se haya publicado ayer.
        valid_date = (now_madrid - timedelta(days=1)).date().isoformat()
    else:
        # A partir de las 10:00, tiene que ser el post de hoy
        valid_date = _today()

    if not msg_id or msg_date != valid_date:
        logger.info(f"[Gasolina/Update] Sin post activo de la jornada (esperado={valid_date}, actual={msg_date}), nada que editar.")
        return

    try:
        zgza_data, top_data = await asyncio.gather(
            fetch_zaragoza_cheapest(),
            fetch_top_stations(),
        )

        if not zgza_data:
            logger.warning("[Gasolina/Update] Sin datos scrapeados, skip.")
            return

        new_snapshot = _serialize_data(zgza_data, top_data)

        logger.debug(f"[Gasolina/Update] OLD snapshot: {json.dumps(last_snapshot, ensure_ascii=False)}")
        logger.debug(f"[Gasolina/Update] NEW snapshot: {json.dumps(new_snapshot, ensure_ascii=False)}")

        changed      = _data_changed(last_snapshot, new_snapshot)

        if changed:
            logger.info(f"[Gasolina/Update] ✅ Precios cambiaron — actualizando caption ({hora_str})")
            state["zgza_last_snapshot"] = new_snapshot
        else:
            logger.info(f"[Gasolina/Update] ℹ️ Sin cambios en precios — solo actualizando hora ({hora_str})")

        # Siempre regenerar el caption con la hora actualizada
        # (datos frescos si cambiaron, último snapshot si no)
        data_to_render = zgza_data if changed else _snapshot_to_render(last_snapshot, zgza_data)
        top_to_render  = top_data  if changed else _snapshot_top_to_render(last_snapshot, top_data)

        new_caption = format_combined_telegram(
            data_to_render, top_to_render, "Zaragoza",
            updated_at=hora_str,
            has_changes=changed,
            initial_snapshot=initial_snapshot,
        )

        valid_msg_id = await edit_or_resend_photo(
            app, chat_id,
            thread_id=None,
            message_id=msg_id,
            new_text=new_caption,
            image_path=IMG_ZARAGOZA,
        )

        if valid_msg_id and valid_msg_id != msg_id:
            # El mensaje fue reenviado → actualizar el id en estado
            logger.info(f"[Gasolina/Update] 🔄 Nuevo message_id: {msg_id} → {valid_msg_id}")
            state["zgza_message_id"] = valid_msg_id
            state["zgza_message_date"] = _today()

        _save_state(state)

    except Exception as e:
        logger.error(f"[Gasolina/Update] Error: {e}", exc_info=True)


def _snapshot_to_render(snapshot: dict, fresh_data: dict) -> dict:
    """
    Si no hubo cambios, devuelve los datos originales del scrape fresco
    (que tienen la estructura completa con estacion/direccion/url).
    Si el snapshot no tiene cambios los datos frescos son iguales, así que
    simplemente usamos fresh_data directamente.
    """
    return fresh_data if fresh_data else snapshot.get("zgza", {})

def _snapshot_top_to_render(snapshot: dict, fresh_top: dict) -> dict:
    return fresh_top
