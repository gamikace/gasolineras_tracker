import signal
import sys
from bot.app import build_app
import warnings
from telegram.warnings import PTBUserWarning
from telegram import Update
from config import IS_PROD, DEV_CHAT_ID, API_TOKEN, ADHOC_CHAT_ID, get_target_contexts
from logger import logger
import os
import subprocess
import time

warnings.filterwarnings(
    "ignore",
    message="If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message.",
    category=PTBUserWarning,
)

# ✅ Configurar display virtual para Selenium (X Publisher)
def setup_xvfb():
    """Inicia Xvfb si no hay DISPLAY disponible"""
    if 'DISPLAY' in os.environ:
        logger.info(f"✅ DISPLAY ya configurado: {os.environ['DISPLAY']}")
        return
    
    os.environ['DISPLAY'] = ':99'
    
    try:
        # Verificar si Xvfb ya está corriendo
        subprocess.run(
            ['pgrep', '-f', 'Xvfb.*:99'],
            check=True,
            capture_output=True,
            timeout=5
        )
    except subprocess.CalledProcessError:
        # Xvfb no está corriendo, iniciarlo
        try:
            subprocess.Popen(
                ['Xvfb', ':99', '-screen', '0', '1920x1080x24', '-ac', '+extension', 'GLX'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(3)  # Esperar a que Xvfb inicie
        except FileNotFoundError:
            logger.warning("⚠️ xvfb no está instalado. Instálalo con: sudo apt-get install xvfb")
        except Exception as e:
            logger.error(f"❌ Error iniciando Xvfb: {e}")
    except subprocess.TimeoutExpired:
        logger.warning("⚠️ Timeout verificando Xvfb")
    except Exception as e:
        logger.error(f"❌ Error configurando Xvfb: {e}")

def main():
    app = build_app()

    def signal_handler(sig, frame):
        print("\n🛑 Señal de parada recibida, cerrando bot...")
        app.stop_running()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    app.run_polling(allowed_updates=Update.ALL_TYPES)
    
if __name__ == "__main__":
    setup_xvfb()

    logger.info("="*60)
    logger.info("🚀 INICIANDO BOT")
    logger.info(f"IS_PROD: {IS_PROD}")
    logger.info(f"DEV_CHAT_ID: {DEV_CHAT_ID}")
    logger.info(f"TARGET_CONTEXTS: {get_target_contexts()}")
    logger.info(f"CHANNEL: {ADHOC_CHAT_ID}")
    logger.info(f"DISPLAY: {os.environ.get('DISPLAY', 'No configurado')}")
    logger.info("="*60)
    
    main()
