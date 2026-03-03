# services/x_selenium.py
"""
x_selenium.py - Publicador automatizado para X (Twitter)
"""
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from io import BytesIO
import json
import time
import os
from twitter_text import parse_tweet
from ai.openrouter import obtener_respuesta_con_reintentos
import asyncio
from selenium.common.exceptions import TimeoutException
from config import IS_PROD
from logger import logger

# ✅ Ruta absoluta basada en ubicación del archivo
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOKIES_FILE = os.path.join(BASE_DIR, "cookies.json")
GECKODRIVER_PATH = "/usr/local/bin/geckodriver"

MAX_LENGTH = 280

async def optimize_title_for_x(original_title: str, max_chars: int, max_attempts: int = 3) -> str:
    """
    Optimiza título para X usando SOLO el LLM con múltiples intentos.
    El hard_cut es solo para emergencias extremas (casi nunca se ejecuta).
    """
    if len(original_title) <= max_chars:
        return original_title
        
    # Intentar con el LLM múltiples veces con límites progresivamente más estrictos
    for attempt in range(1, max_attempts + 1):
        # Reducir agresivamente el límite para dar margen al LLM
        margin = 2 + (attempt - 1) * 3  # Intento 1: -2, Intento 2: -5, Intento 3: -8...
        adjusted_limit = max_chars - margin
        
        if adjusted_limit < 15:
            adjusted_limit = max_chars - 2  # Mínimo margen de 2 chars
        
        # Prompt con EJEMPLOS concretos
        prompt = f"""Reescribe el siguiente título de producto para que tenga EXACTAMENTE {adjusted_limit} caracteres o menos.

⚠️ CRÍTICO: Tu respuesta NO puede superar {adjusted_limit} caracteres (incluyendo espacios).

Ejemplos de cómo acortar:
- "Auriculares Inalámbricos Bluetooth 5.0 con Cancelación de Ruido" → "Auriculares BT 5.0 Cancelación Ruido"
- "Ratón Gaming RGB Programable 16000 DPI con Cable Trenzado" → "Ratón Gaming RGB 16000 DPI"
- "D-Link DGS-105GL Switch Gigabit 5 Puertos Negro 59W Full Duplex Metal" → "D-Link DGS-105GL Switch 5 Puertos"

Técnicas para acortar:
- Elimina palabras como: "con", "de", "para", "Full", "Metal", etc.
- Abrevia si es necesario: "Bluetooth" → "BT", "Inalámbrico" → "Wireless"
- Mantén: marca, modelo, característica principal

Título original ({len(original_title)} chars):
{original_title}

Responde SOLO con el título reescrito ({adjusted_limit} chars máx, sin comillas, sin puntos suspensivos):"""
        
        try:
            optimized = await asyncio.wait_for(
                obtener_respuesta_con_reintentos(prompt),
                timeout=30.0
            )
            
            # Limpiar respuesta agresivamente
            optimized = optimized.strip()
            optimized = optimized.strip('"').strip("'").strip('`')
            optimized = optimized.replace('\n', ' ').strip()
            
            # Validar longitud REAL
            actual_length = len(optimized)
            
            if actual_length <= max_chars:
                return optimized
            else:
                logger.warning(f"[X_LLM] ⚠️ Intento {attempt}/{max_attempts}: Excede ({actual_length} > {max_chars})")
                logger.warning(f"[X_LLM]    Respuesta: '{optimized}'")
                
                if attempt < max_attempts:
                    continue
                else:
                    # Último recurso: pedir al LLM que corte aún más
                    logger.error(f"[X_LLM] 😱 Agotados {max_attempts} intentos")
                    logger.error(f"[X_LLM] Usando último intento extremo...")
                    return await emergency_llm_cut(original_title, max_chars)
        
        except asyncio.TimeoutError:
            logger.error(f"[X_LLM] ⏱️ Timeout en intento {attempt}/{max_attempts}")
            if attempt < max_attempts:
                continue
            else:
                return await emergency_llm_cut(original_title, max_chars)
        
        except Exception as e:
            logger.error(f"[X_LLM] ❌ Error en intento {attempt}/{max_attempts}: {e}")
            if attempt < max_attempts:
                continue
            else:
                return await emergency_llm_cut(original_title, max_chars)
    
    # Fallback final (casi imposible de alcanzar)
    logger.critical(f"[X_LLM] 🚨 Fallback crítico activado")
    return await emergency_llm_cut(original_title, max_chars)


async def emergency_llm_cut(original_title: str, max_chars: int) -> str:
    """
    Último intento de emergencia con el LLM usando prompt ULTRA estricto.
    Solo se ejecuta si los 5 intentos normales fallan.
    """
    logger.warning(f"[X_LLM_EMERGENCY] 🆘 Último intento con límite ultra estricto")
    
    # Límite super conservador (90% del máximo)
    ultra_limit = int(max_chars * 0.9)
    
    prompt = f"""URGENTE: Acorta este título a MÁXIMO {ultra_limit} caracteres.

Título: {original_title}

Responde SOLO las primeras palabras clave (marca + modelo) sin nada más. Ejemplo: "D-Link DGS-105GL"
Máximo {ultra_limit} caracteres:"""
    
    try:
        result = await asyncio.wait_for(
            obtener_respuesta_con_reintentos(prompt),
            timeout=20.0
        )
        result = result.strip().strip('"').strip("'").strip()
        
        if len(result) <= max_chars:
            return result
        else:
            # Si incluso esto falla, cortar manualmente (SIN "...")
            logger.critical(f"[X_LLM_EMERGENCY] 😱 LLM falló incluso en emergencia")
            cut = result[:max_chars].rsplit(' ', 1)[0].rstrip('.,;:- ')
            logger.critical(f"[X_LLM_EMERGENCY] 🔪 Corte forzoso final: '{cut}'")
            return cut
    
    except Exception as e:
        logger.critical(f"[X_LLM_EMERGENCY] ❌ Error en emergencia: {e}")
        # Último último recurso
        cut = original_title[:max_chars].rsplit(' ', 1)[0].rstrip('.,;:- ')
        logger.critical(f"[X_LLM_EMERGENCY] 🔪 Corte directo: '{cut}'")
        return cut

def merchant_badge_for_x(merchant: str | None) -> str | None:
    if not merchant:
        return None
    m = merchant.strip().lower()
    mapping = {
        "amazon": "Amazon",
        "aliexpress": "AliExpress",
        "pccomponentes": "PcComp",
        "steam": "Steam",
        "epicgames": "EpicGames",
    }
    return mapping.get(m, merchant)

async def format_post_for_x(
    title: str,
    price: str | None = None,
    old_price: str | None = None,
    discount: str | None = None,
    recommendation: str | None = None,
    merchant: str | None = None,
    url: str | None = None,
    optimized_title: str | None = None,
) -> str:
    badge = merchant_badge_for_x(merchant)

    if not title:
        title = "Oferta disponible"

    if not url:
        fixed_lines = [title]
        if price:
            fixed_lines.append(f"✅ Ahora: {price}")
        if old_price:
            fixed_lines.append(f"❌ Antes: {old_price}")
        if discount:
            fixed_lines.append(f"🔥 {discount}")

        fixed_text = "\n".join(fixed_lines)
        fixed_weight = parse_tweet(fixed_text).weightedLength

        if recommendation:
            rec_prefix = "\n\n✅ Recomienda Ofertonacas: "
            available = MAX_LENGTH - fixed_weight - len(rec_prefix)
            if available > 10:
                recommendation = await optimize_recommendation_for_x(recommendation, available)
                fixed_lines.append("")
                fixed_lines.append(f"✅ Recomienda Ofertonacas: {recommendation}")

        return "\n".join(fixed_lines)

    # ── CON URL ───────────────────────────────────────────────
    url_part = f"\n\n🔗 {url}\n🖥 t.me/ofertonacas"
    hashtags = f"\n\n#{badge} #chollos #ofertas #deal" if badge else ""

    other_lines = ["\n"]
    if old_price:
        other_lines.append(f"❌ Antes: {old_price}")
    if price:
        other_lines.append(f"✅ Ahora: {price}")
    if discount:
        other_lines.append(f"🔥 Descuento: {discount}")

    base_text   = title + "\n".join(other_lines) + url_part + hashtags
    base_weight = parse_tweet(base_text).weightedLength

    if recommendation:
        rec_prefix = "\n\n¿Recomienda Ofertonacas?\n"
        available  = MAX_LENGTH - base_weight - len(rec_prefix)
        if available > 10:
            recommendation = await optimize_recommendation_for_x(recommendation, available)
            other_lines.append("")
            other_lines.append(f"¿Recomienda Ofertonacas?\n{recommendation}")

    final_text   = title + "\n".join(other_lines) + url_part + hashtags
    final_result = parse_tweet(final_text)

    if not final_result.valid:
        logger.error("[X] ⚠️ Post inválido según twitter-text")

    return final_text

async def optimize_recommendation_for_x(
    recommendation: str,
    available_chars: int,
    max_attempts: int = 3,
) -> str:
    if not recommendation or len(recommendation) <= available_chars:
        return recommendation

    for attempt in range(1, max_attempts + 1):
        margin = 2 + (attempt - 1) * 3
        adjusted_limit = max(10, available_chars - margin)

        prompt = f"""Tienes un texto que debes acortar.

        ⚠️ CRÍTICO: La respuesta NO puede superar {adjusted_limit} caracteres.

        Técnicas:
        - Elimina adjetivos superfluos
        - Usa frases más cortas pero conserva el mensaje clave
        - No uses puntos suspensivos al final

        Texto original ({len(recommendation)} chars):
        {recommendation}

        Responde SOLO con el texto acortado ({adjusted_limit} chars máx, sin comillas):"""

        try:
            result = await asyncio.wait_for(
                obtener_respuesta_con_reintentos(prompt),
                timeout=30.0,
            )
            result = result.strip().strip('"').strip("'").strip('`').replace('\n', ' ').strip()

            if len(result) <= available_chars:
                return result
            else:
                logger.warning(f"[X_LLM] ⚠️ Intento {attempt}: Excede ({len(result)} > {available_chars})")
                if attempt == max_attempts:
                    cut = result[:available_chars].rsplit(' ', 1)[0].rstrip('.,;:- ')
                    return cut

        except asyncio.TimeoutError:
            logger.error(f"[X_LLM] ⏱️ Timeout intento {attempt}")
            if attempt == max_attempts:
                return recommendation[:available_chars].rsplit(' ', 1)[0]

        except Exception as e:
            logger.error(f"[X_LLM] ❌ Error intento {attempt}: {e}")
            if attempt == max_attempts:
                return recommendation[:available_chars].rsplit(' ', 1)[0]

    return recommendation[:available_chars].rsplit(' ', 1)[0]

def post_to_x(text: str, image_bytes: bytes = None, headless: bool = True) -> bool:
    """
    Publica un post en X con texto e imagen opcional.
    Maneja overlays y elementos que bloquean el click.
    """
    if not IS_PROD:
        logger.info("[X] 🛑 Modo DEV (IS_PROD=False): Saltando publicación en X")
        return True

    driver = None
    temp_image_path = None
    
    try:     
        # Configurar Firefox
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        if headless:
            options.add_argument("--headless")
        
        service = Service(GECKODRIVER_PATH)
        driver = webdriver.Firefox(service=service, options=options)
        wait = WebDriverWait(driver, 30)
        
        # 1️⃣ Abrir X
        driver.get("https://x.com")
        time.sleep(2)
        
        # 2️⃣ Cargar cookies
        if not os.path.exists(COOKIES_FILE):
            logger.error(f"[X] ⚠️ Cookies no encontradas en {COOKIES_FILE}")
            return False
        
        with open(COOKIES_FILE) as f:
            cookies = json.load(f)
        
        for c in cookies:
            c.pop("sameSite", None)
            driver.add_cookie(c)
        
        
        # 3️⃣ Ir al home logueado
        driver.get("https://x.com/home")
        time.sleep(4)

        current_url = driver.current_url
        if "/login" in current_url or "/i/flow/login" in current_url:
            logger.error("[X] ❌ Sesión inválida: X redirigió a login (%s)", current_url)
            return False
        
        # Cerrar posibles modals
        try:
            close_btns = driver.find_elements(By.CSS_SELECTOR, "[aria-label*='Close'], [aria-label*='Cerrar']")
            if close_btns:
                for btn in close_btns:
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(0.5)
        except:
            pass
        
        # 4️⃣ Detectar textarea del composer
        composer_selectors = [
            "div[data-testid='tweetTextarea_0']",
            "div[data-testid='tweetTextarea_1']",
            "div[role='textbox'][data-testid*='tweetTextarea']",
            "div[role='textbox'][contenteditable='true']",
        ]

        tweet_box = None
        for selector in composer_selectors:
            try:
                tweet_box = WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                break
            except TimeoutException:
                logger.debug("[X] Composer no encontrado con selector: %s", selector)

        if tweet_box is None:
            logger.warning("[X] ⚠️ No aparece composer en /home, probando /compose/post...")
            driver.get("https://x.com/compose/post")
            time.sleep(3)

            for selector in composer_selectors:
                try:
                    tweet_box = WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    break
                except TimeoutException:
                    logger.debug("[X] Composer no encontrado en /compose/post con selector: %s", selector)

        if tweet_box is None:
            raise TimeoutException("No se encontró el composer de X en /home ni /compose/post")
        
        # Scroll y click
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tweet_box)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", tweet_box)
        time.sleep(1)
        
        # Enviar texto
        tweet_box.send_keys(text)
        
        # 5️⃣ Subir imagen si existe
        if image_bytes:
            temp_image_path = f"/dev/shm/x_temp_{int(time.time())}.jpg"
            
            try:
                with open(temp_image_path, "wb") as f:
                    f.write(image_bytes)
            except OSError as e:
                logger.error(f"[X] ❌ Error escribiendo en /dev/shm: {e}")
                temp_image_path = f"/tmp/x_temp_{int(time.time())}.jpg"
                with open(temp_image_path, "wb") as f:
                    f.write(image_bytes)
                        
            try:
                # Esperar a que el input esté presente
                file_input = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "input[data-testid='fileInput']")
                    )
                )
                
                # ✅ CAMBIO 2: NO manipular visibilidad, enviar directamente
                # X permite send_keys sin hacer el input visible
                file_input.send_keys(temp_image_path)
                
                # ✅ CAMBIO 3: Esperar más tiempo y buscar el botón "Eliminar contenido multimedia"
                wait_upload = WebDriverWait(driver, 30)
                
                # Buscar el botón de eliminar que aparece cuando la imagen está cargada
                try:
                    wait_upload.until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "button[aria-label*='Eliminar contenido multimedia'], button[aria-label*='Remove media']")
                        )
                    )
                    
                except TimeoutException:
                    # Fallback: buscar por el contenedor de la imagen
                    logger.warning("[X] ⚠️ No se encontró botón 'Eliminar', buscando preview...")
                    try:
                        # Buscar el preview de la imagen
                        wait_upload.until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, "div[data-testid='attachments'] img")
                            )
                        )
                    except TimeoutException:
                        logger.error("[X] ❌ Timeout: la imagen no se cargó en 30s")
                        
                        # Guardar HTML para debug
                        debug_html_path = f"x_upload_timeout_{int(time.time())}.html"
                        with open(debug_html_path, "w", encoding="utf-8") as f:
                            f.write(driver.page_source)
                        logger.error(f"[X] 🔍 HTML guardado para análisis: {debug_html_path}")
                        
                        # Continuar de todas formas (puede que se haya cargado)
                        logger.warning("[X] ⚠️ Continuando sin confirmación visual...")
                
                # Espera adicional para que la UI se estabilice
                time.sleep(2)
                
            except TimeoutException:
                logger.error("[X] ❌ No se encontró el input[data-testid='fileInput']")
                return False
            except Exception as e:
                logger.error(f"[X] ❌ Error subiendo imagen: {e}", exc_info=True)
                return False

        # 6️⃣ Publicar
        post_btn = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "[data-testid='tweetButtonInline']")
            )
        )
        
        # Scroll al botón y click con JS
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", post_btn)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", post_btn)
                
        time.sleep(3)
        return True
        
    except Exception as e:
        logger.error(f"[X Publisher] ❌ Error publicando en X: {e}", exc_info=True)
        
        # Debug: guardar screenshot y HTML
        if driver:
            try:
                driver.save_screenshot("x_error.png")
                with open("x_error.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
            except:
                pass
        
        return False
        
    finally:
        # Cleanup
        if driver:
            driver.quit()
        
        if temp_image_path:
            try:
                if os.path.exists(temp_image_path):
                    os.remove(temp_image_path)
                    logger.debug(f"[X] 🗑️ Eliminado temp: {temp_image_path}")
            except Exception as e:
                logger.warning(f"[X] ⚠️ No se pudo eliminar temp: {e}")
