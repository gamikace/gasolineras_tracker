# bot/app.py
from telegram import LinkPreviewOptions
from telegram.ext import Application, ApplicationBuilder, Defaults
from telegram.request import HTTPXRequest
from config import API_TOKEN
from services.gasolina_scheduler import run_gasolina_daily, run_gasolina_update
from datetime import time as dtime
import pytz


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

    return app
