from telegram.error import TelegramError, BadRequest
from logger import logger
import asyncio

_pending_pin_tasks: set = set()

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

async def unpin_telegram_message(app, chat_id, message_id) -> bool:
    """Desfija un mensaje en el chat."""
    try:
        await app.bot.unpin_chat_message(
            chat_id=chat_id,
            message_id=message_id,
        )
        logger.info(f"[Telegram] 📌 Mensaje {message_id} desfijado en chat_id={chat_id}")
        return True
    except BadRequest as e:
        logger.warning(f"[Telegram] ⚠️ No se pudo desfijar {message_id} (puede estar ya desfijado o eliminado): {e}")
        return False
    except TelegramError as e:
        logger.error(f"[Telegram] ❌ Error desfijando mensaje {message_id}: {e}")
        return False

async def pin_telegram_message(app, chat_id, message_id, disable_notification: bool = True) -> bool:
    """Fija un mensaje en el chat. disable_notification=True evita el aviso al grupo."""
    try:
        await app.bot.pin_chat_message(
            chat_id=chat_id,
            message_id=message_id,
            disable_notification=disable_notification,
        )
        logger.info(f"[Telegram] 📌 Mensaje {message_id} fijado en chat_id={chat_id}")
        return True
    except TelegramError as e:
        logger.error(f"[Telegram] ❌ Error fijando mensaje {message_id}: {e}")
        return False

async def _delayed_pin_task(app, chat_id, message_id, delay_seconds: int):
    """Coroutine interna: espera el delay y ejecuta el pin."""
    horas = delay_seconds // 3600
    logger.info(f"[Telegram] ⏳ Pin de message_id={message_id} programado en {horas}h")
    await asyncio.sleep(delay_seconds)
    await pin_telegram_message(app, chat_id, message_id)


def schedule_delayed_pin(app, chat_id, message_id, delay_hours: int = 3):
    """
    Programa el pin de un mensaje tras `delay_hours` horas.
    No bloquea — lanza un asyncio.Task en segundo plano.
    Valores válidos sugeridos: 3, 4 o 5 horas.
    """
    task = asyncio.create_task(
        _delayed_pin_task(app, chat_id, message_id, delay_hours * 3600)
    )
    # Guardamos referencia para evitar que el GC destruya la task antes de ejecutarse
    _pending_pin_tasks.add(task)
    task.add_done_callback(_pending_pin_tasks.discard)
    logger.info(f"[Telegram] 🕐 Task de pin creada — message_id={message_id}, delay={delay_hours}h")
    return task
