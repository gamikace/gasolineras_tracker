from telegram import LinkPreviewOptions
from telegram.ext import Application, ApplicationBuilder, Defaults
from telegram.request import HTTPXRequest
from config import API_TOKEN
from services.gasolina_scheduler import run_gasolina_daily
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
    app.job_queue.run_daily(
        run_gasolina_daily,
        time=dtime(10, 0, tzinfo=madrid),
        name="gasolina_daily"
    )

    return app
