from telegram.error import TelegramError, BadRequest
from logger import logger


async def send_telegram_photo(app, chat_id, thread_id, text, image_path) -> int | None:
    kw = {"message_thread_id": thread_id} if thread_id else {}
    try:
        with open(image_path, "rb") as img:
            msg = await app.bot.send_photo(
                chat_id=chat_id,
                photo=img,
                caption=text,
                parse_mode="HTML",
                **kw,
            )
        logger.info(f"[Telegram] ✅ Foto enviada chat_id={chat_id}, message_id={msg.message_id}")
        return msg.message_id
    except FileNotFoundError:
        logger.error(f"[Telegram] ❌ Imagen no encontrada: {image_path}")
        return None
    except TelegramError as e:
        logger.error(f"[Telegram] ❌ Error enviando foto: {e}")
        return None


async def edit_telegram_caption(app, chat_id, message_id, new_text) -> bool:
    """Edita caption. Devuelve False si el mensaje no existe (no relanza)."""
    try:
        await app.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=new_text,
            parse_mode="HTML",
        )
        logger.info(f"[Telegram] ✅ Caption editado message_id={message_id}")
        return True
    except BadRequest as e:
        # Mensaje eliminado o inaccesible — error esperado, no crítico
        logger.warning(f"[Telegram] ⚠️ Mensaje {message_id} no encontrado: {e}")
        return False
    except TelegramError as e:
        logger.error(f"[Telegram] ❌ Error editando caption: {e}")
        return False


async def edit_or_resend_photo(
    app, chat_id, thread_id, message_id,
    new_text, image_path
) -> int | None:
    """
    Intenta editar el caption del mensaje existente.
    Si el mensaje no existe, reenvía la foto completa.
    Devuelve el message_id válido (nuevo o el mismo).
    """
    if message_id:
        edited = await edit_telegram_caption(app, chat_id, message_id, new_text)
        if edited:
            return message_id  # Mismo id, todo OK
        logger.info("[Telegram] 🔄 Fallback: reenviando foto por mensaje no encontrado...")

    # Reenvío completo
    new_id = await send_telegram_photo(app, chat_id, thread_id, new_text, image_path)
    return new_id
