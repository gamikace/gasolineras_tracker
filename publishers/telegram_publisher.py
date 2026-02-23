# publishers/telegram_publisher.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from logger import logger

async def send_telegram_plain(
    app, chat_id: str, thread_id: int | None, text: str
) -> bool:
    """Envía texto HTML sin botones. Usado para gasolina y otros informes."""
    return await _send(app, chat_id, thread_id, text)

async def _send(app, chat_id, thread_id, text, image_url=None, markup=None) -> bool:
    kw = {"message_thread_id": thread_id} if thread_id else {}
    try:
        if image_url:
            await app.bot.send_photo(
                chat_id=chat_id, photo=image_url,
                caption=text, parse_mode="HTML",
                reply_markup=markup, **kw,
            )
        else:
            await app.bot.send_message(
                chat_id=chat_id, text=text,
                parse_mode="HTML", reply_markup=markup, **kw,
            )
        logger.info(f"[Telegram] ✅ Enviado a chat_id={chat_id}")
        return True
    except TelegramError as e:
        logger.error(f"[Telegram] ❌ Error: {e}")
        return False

async def send_telegram_photo(
    app, chat_id: str, thread_id: int | None,
    text: str, image_path: str,
) -> bool:
    """Envía mensaje con imagen local."""
    kw = {"message_thread_id": thread_id} if thread_id else {}
    try:
        with open(image_path, "rb") as img:
            await app.bot.send_photo(
                chat_id=chat_id,
                photo=img,
                caption=text,
                parse_mode="HTML",
                **kw,
            )
        logger.info(f"[Telegram] ✅ Foto enviada a chat_id={chat_id}")
        return True
    except FileNotFoundError:
        logger.error(f"[Telegram] ❌ Imagen no encontrada: {image_path}")
        return False
    except TelegramError as e:
        logger.error(f"[Telegram] ❌ Error: {e}")
        return False
