# publishers/x_publisher.py
import asyncio
import requests
from logger import logger
from services.x_selenium import post_to_x, format_post_for_x

async def send_x_notification(
    title: str, summary: str, platform: str,
    external_url: str, image_url: str | None,
) -> bool:
    text = await format_post_for_x(
        title=title,
        recommendation=summary or "🎁 Juego gratis por tiempo limitado",
        merchant=platform,
        url=external_url,
    )
    image_bytes = None
    if image_url:
        try:
            image_bytes = await asyncio.to_thread(_download_bytes, image_url)
        except Exception as e:
            logger.warning(f"[X] No se pudo descargar imagen: {e}")

    return await _post_x(text, image_bytes, title)

async def send_x_text(text: str) -> bool:
    """Publica texto plano en X sin imagen. Usado para gasolina."""
    return await _post_x(text, None, text[:30])

async def _post_x(text: str, image_bytes: bytes | None, label: str) -> bool:
    ok = await asyncio.to_thread(post_to_x, text=text, image_bytes=image_bytes, headless=True)
    if ok:
        logger.info(f"[X] ✅ Publicado: {label[:50]}")
    else:
        logger.error(f"[X] ❌ Falló publicación: {label[:50]}")
    return ok

def _download_bytes(url: str) -> bytes:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content

async def send_x_text_with_image(text: str, image_path: str) -> bool:
    """Publica texto + imagen local en X. Usado para gasolina."""
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
    except FileNotFoundError:
        logger.error(f"[X] ❌ Imagen no encontrada: {image_path}")
        image_bytes = None

    return await _post_x(text, image_bytes, text[:30])
