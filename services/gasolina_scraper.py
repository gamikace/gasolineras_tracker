# services/gasolina_scraper.py
import asyncio
import re
import requests
from bs4 import BeautifulSoup
from datetime import date
from logger import logger
from twitter_text import parse_tweet
from services.x_selenium import optimize_recommendation_for_x

UA = "mi-scraper/1.0 (contacto: tu_email@dominio)"

# ── URLs ──────────────────────────────────────────────────────
URL_SPAIN   = "https://preciocombustible.es/"
URL_ZGZA    = "https://preciocombustible.es/zaragoza/zaragoza"
URLS_TOP    = {
    "Family Energy": "https://preciocombustible.es/zaragoza/zaragoza/11519-family-energy",
    "Bonarea":       "https://preciocombustible.es/zaragoza/zaragoza/13290-bonarea",
    "CostCo":        "https://preciocombustible.es/zaragoza/zaragoza/16078-costco",
    "GasExpress":    "https://preciocombustible.es/zaragoza/zaragoza/15376-gasexpress",
}

FUEL_ORDER = ["Gasolina 95 E5", "Gasolina 98 E5", "Gasoleo A", "Gasoleo Premium"]


def _get_html(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.text


def _parse_cheapest_block(html: str) -> dict[str, dict]:
    """
    Parsea el bloque uk-grid con los precios más baratos por tipo.
    Devuelve {tipo: {precio, estacion, direccion, url}}
    """
    soup = BeautifulSoup(html, "html.parser")
    results = {}

    for card in soup.select("div.cuadro-precios"):
        try:
            tipo_el = card.select_one("h2.uk-h4, h2.uk-h2")
            precio_el = card.select_one("[itemprop='price']") or card.select_one(".uk-h2")
            estacion_el = card.select_one(".uk-text-large")
            dir_el = card.select_one("span")
            link_el = card.select_one("a[href]")

            if not tipo_el or not precio_el:
                continue

            tipo = tipo_el.get_text(strip=True)
            raw  = precio_el.get("content") or precio_el.get_text(strip=True)
            raw  = raw.replace("\xa0", "").replace("€", "").replace(" ", "").strip()
            raw  = raw.replace(".", ",")
            precio = raw + " €"

            results[tipo] = {
                "precio": precio,
                "estacion": estacion_el.get_text(strip=True) if estacion_el else "",
                "direccion": dir_el.get_text(strip=True) if dir_el else "",
                "url": "https://preciocombustible.es" + link_el["href"] if link_el else "",
            }
        except Exception:
            continue

    return results

def _parse_station_block(html: str) -> dict[str, str]:
    """
    Parsea la página de una gasolinera concreta.
    Devuelve {tipo: precio}
    """
    soup = BeautifulSoup(html, "html.parser")
    results = {}

    for card in soup.select("div.cuadro-precios"):
        try:
            tipo_el = card.select_one("[itemprop='name'], h2.uk-h4")
            precio_el = card.select_one("[itemprop='price'], .uk-h2")
            if not tipo_el or not precio_el:
                continue
            tipo = tipo_el.get_text(strip=True)
            raw  = precio_el.get("content") or precio_el.get_text(strip=True)
            raw  = raw.replace("\xa0", "").replace("€", "").replace(" ", "").strip()
            raw  = raw.replace(".", ",")
            precio = raw + " €"
            results[tipo] = precio
        except Exception:
            continue

    return results

async def fetch_spain_cheapest() -> dict[str, dict]:
    """Precios más baratos a nivel España."""
    html = await asyncio.to_thread(_get_html, URL_SPAIN)
    return _parse_cheapest_block(html)

async def fetch_zaragoza_cheapest() -> dict[str, dict]:
    """Precios más baratos en Zaragoza ciudad."""
    html = await asyncio.to_thread(_get_html, URL_ZGZA)
    return _parse_cheapest_block(html)

async def fetch_top_stations() -> dict[str, dict[str, str]]:
    async def _fetch_one(name, url):
        try:
            html = await asyncio.to_thread(_get_html, url)
            return name, _parse_station_block(html)
        except Exception as e:
            logger.warning(f"[Gasolina] Error scraping {name}: {e}")
            return name, {}

    pairs = await asyncio.gather(*[_fetch_one(n, u) for n, u in URLS_TOP.items()])
    return dict(pairs)

# ── Formateadores de texto ────────────────────────────────────

def format_cheapest_telegram(data: dict, zona: str) -> str:
    hoy = date.today().strftime("%d/%m/%Y")
    lines = [f"⛽ <b>Gasolinera más barata {zona} — {hoy}</b>\n"]
    for tipo in FUEL_ORDER:
        if tipo not in data:
            continue
        d = data[tipo]
        lines.append(f"<b>{tipo}</b>: {d['precio']}")
        lines.append(f"  🏪 {d['estacion']}")
        if d.get("direccion"):
            lines.append(f"  📍 {d['direccion'][:60]}")
    return "\n".join(lines)


async def format_cheapest_x(data: dict, zona: str) -> str:
    hoy = date.today().strftime("%d/%m/%Y")
    header = f"⛽ Gasolinera más barata {zona} — {hoy}"
    hashtags = "\n\n#gasolina #chollos #ofertas"

    # Construir líneas de combustible
    fuel_lines = []
    for tipo in FUEL_ORDER:
        if tipo not in data:
            continue
        d = data[tipo]
        fuel_lines.append(f"{tipo}: {d['precio']} ({d['estacion']})")

    # Calcular espacio disponible para las líneas de combustible
    fixed = header + "\n\n" + hashtags
    fixed_weight = parse_tweet(fixed).weightedLength
    available = 280 - fixed_weight - 1  # -1 por el \n entre header y fuels

    fuels_text = "\n".join(fuel_lines)

    # Si no caben, recortar nombres de estación con LLM
    if parse_tweet(fuels_text).weightedLength > available:
        fuels_text = await optimize_recommendation_for_x(fuels_text, available)

    return header + "\n\n" + fuels_text + hashtags

def format_top4_telegram(data: dict[str, dict]) -> str:
    hoy = date.today().strftime("%d/%m/%Y")
    lines = [f"⛽ <b>Top gasolineras Zaragoza — {hoy}</b>\n"]
    for station, fuels in data.items():
        if not fuels:
            continue
        lines.append(f"<b>{station}</b>")
        for tipo in FUEL_ORDER:
            if tipo in fuels:
                lines.append(f"  {tipo}: {fuels[tipo]}")
    return "\n".join(lines)

def format_combined_telegram(
    cheapest_data: dict,
    top_data: dict,
    zona: str,
) -> str:
    """Telegram: más barata + top gasolineras en un solo mensaje."""
    hoy = date.today().strftime("%d/%m/%Y")
    lines = [f"⛽ <b>#Gasolina {zona} — {hoy}</b>\n"]

    # ── Más barata ────────────────────────────────────────────
    lines.append("🏆 <b>Más barata</b>")
    for tipo in FUEL_ORDER:
        if tipo not in cheapest_data:
            continue
        d = cheapest_data[tipo]
        lines.append(f"<b>{tipo}</b>: {d['precio']}")
        lines.append(f"  🏪 {d['estacion']}")
        if d.get("direccion"):
            lines.append(f"  📍 {d['direccion'][:60]}")

    lines.append("")

    # ── Top gasolineras ───────────────────────────────────────
    lines.append("📋 <b>Top gasolineras</b>")
    for station, fuels in top_data.items():
        if not fuels:
            continue
        lines.append(f"<b>{station}</b>")
        for tipo in FUEL_ORDER:
            if tipo in fuels:
                lines.append(f"  {tipo}: {fuels[tipo]}")

    return "\n".join(lines)
