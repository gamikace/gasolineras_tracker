# bot/app.py
from telegram import LinkPreviewOptions
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, Defaults, ContextTypes
from telegram.request import HTTPXRequest
from telegram.error import NetworkError
from config import API_TOKEN
from services.gasolina_scheduler import run_gasolina_daily, run_gasolina_update, run_gasolina_weekly_summary, run_gasolina_monthly_summary
from logger import logger
from datetime import time as dtime
import pytz


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the Errors, but ignore transient NetworkErrors to reduce noise."""
    if isinstance(context.error, NetworkError):
        return

    # Para otros errores, registrar en el log
    logger.error("Exception while handling an update:", exc_info=context.error)

def build_app() -> Application:
    request = HTTPXRequest(
        connection_pool_size=10, read_timeout=30.0,
        write_timeout=30.0, connect_timeout=30.0,
        pool_timeout=5.0, http_version="1.1"
    )
    defaults = Defaults(link_preview_options=LinkPreviewOptions(is_disabled=True))
    app = ApplicationBuilder().token(API_TOKEN).request(request).defaults(defaults).build()

    madrid = pytz.timezone("Europe/Madrid")

    # ── Job diario 10:10 — envío inicial ──────────────────────
    app.job_queue.run_daily(
        run_gasolina_daily,
        time=dtime(10, 10, tzinfo=madrid),
        name="gasolina_daily",
    )

    # ── Jobs horarios 11:00–09:00 — actualización caption ─────
    update_hours = list(range(11, 24)) + list(range(0, 10))  # 11→23 + 00→09
    for hour in update_hours:
        app.job_queue.run_daily(
            run_gasolina_update,
            time=dtime(hour, 10, tzinfo=madrid),
            name=f"gasolina_update_{hour:02d}",
        )

    # ── Resúmenes Estadísticos ────────────────────────────────
    # Resumen semanal: Domingos a las 20:00 (days=(6,) en python-telegram-bot, lunes=0, domingo=6)
    app.job_queue.run_daily(
        run_gasolina_weekly_summary,
        time=dtime(20, 0, tzinfo=madrid),
        days=(6,),
        name="gasolina_weekly_summary",
    )

    # Resumen mensual: Día 1 de cada mes a las 08:00
    # python-telegram-bot run_monthly está disponible en v20+ o ejecutamos daily y filtramos dentro del job
    # run_gasolina_monthly_summary ya filtra internamente si es día 1, así que lo ejecutamos a diario a las 08:00
    app.job_queue.run_daily(
        run_gasolina_monthly_summary,
        time=dtime(8, 0, tzinfo=madrid),
        name="gasolina_monthly_summary",
    )
    app.add_error_handler(error_handler)

    return app
