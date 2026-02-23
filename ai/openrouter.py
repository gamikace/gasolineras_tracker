# ai/openrouter.py
import aiohttp
import json
from config import OPENROUTER_CONFIG
from logger import logger
import asyncio
 
async def get_deepseek_response(prompt: str, image_url: str = None) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_CONFIG['key']}",
        "Content-Type": "application/json",
        "User-Agent": "gm-bot/1.0"
    }

    content = [{"type": "text", "text": prompt}]
    if image_url:
        # ✅ Si es solo base64, construir el data URI
        if not image_url.startswith("data:") and not image_url.startswith("http"):
            image_url = f"data:image/jpeg;base64,{image_url}"
        
        content.append({
            "type": "image_url", 
            "image_url": {"url": image_url}
        })

    messages = [{"role": "user", "content": content}]

    payload = {
        "messages": messages,
        "model": OPENROUTER_CONFIG["model"]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OPENROUTER_CONFIG["url"], headers=headers, json=payload, timeout=60) as response:
                data = await response.json()
                if response.status == 200 and data.get("choices"):
                    return data["choices"][0]["message"]["content"]
                logger.error("Respuesta inválida o vacía: %s", data)
                return ""
    except Exception as e:
        logger.error(f"Error en get_deepseek_response: {str(e)}")
        return ""

async def obtener_respuesta_con_reintentos(prompt, image_url=None, max_reintentos=2):
    """
    Obtiene respuesta con reintentos RÁPIDOS (sin bloquear el bot)
    Solo 2 intentos: inmediato y 3 segundos después
    """
    tiempos_espera = [0, 5]  # 0s, 3s
    for intento, espera in enumerate(tiempos_espera, start=1):
        if espera > 0:
            logger.info(f"⏳ Reintentando en {espera} segundos...")
            await asyncio.sleep(espera)

        respuesta = await get_deepseek_response(prompt, image_url)

        if respuesta and len(respuesta.strip()) > 10:
            return respuesta

        logger.warning(f"⚠️ Intento {intento} fallido. Respuesta: {respuesta[:100] if respuesta else 'vacía'}")
    
    logger.error("❌ Todos los intentos fallaron.")
    return ""
