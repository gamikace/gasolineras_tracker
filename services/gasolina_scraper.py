# services/gasolina_scraper.py
import asyncio
import re
import requests
from bs4 import BeautifulSoup
from datetime import date
from logger import logger
try:
    from twitter_text import parse_tweet
except ImportError:
    def parse_tweet(text):
        class Dummy:
            pass
        d = Dummy()
        d.weightedLength = len(text)
        return d
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

def _find_top_winners(top_data: dict) -> dict[str, set[str]]:
    """
    Devuelve {fuel_type: {station1, station2, ...}} con las gasolineras
    más baratas por tipo de combustible dentro del top.
    Soporta empates.
    """
    min_prices: dict[str, float] = {}
    winners: dict[str, set[str]] = {}

    def _parse(price_str: str) -> float:
        return float(price_str.replace("€", "").replace(",", ".").strip())

    # Primera pasada: encontrar precio mínimo por combustible
    for station, fuels in top_data.items():
        for fuel, price_str in fuels.items():
            try:
                price = _parse(price_str)
                if fuel not in min_prices or price < min_prices[fuel]:
                    min_prices[fuel] = price
            except ValueError:
                continue

    # Segunda pasada: marcar ganadores (con soporte de empate)
    for station, fuels in top_data.items():
        for fuel, price_str in fuels.items():
            try:
                price = _parse(price_str)
                if fuel in min_prices and price == min_prices[fuel]:
                    winners.setdefault(fuel, set()).add(station)
            except ValueError:
                continue

    return winners

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
    lines = [f"⛽ <b>Gasolinera más barata {zona} — {hoy}</b>\n"]  # ← zona, sin hora_str
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
    zgza_data, top_data, city,
    updated_at=None, has_changes=False,
    initial_snapshot=None,
) -> str:
    hoy = date.today().strftime("%d/%m/%Y")

    # Calcular trofeos dinámicamente
    winners = _find_top_winners(top_data)

    if updated_at:
        check = " ✅" if has_changes else ""
        hora_str = f"({updated_at}{check})"
    else:
        hora_str = "(10:05)"

    lines = [f"⛽️ <b>#Gasolina {city} — {hoy} {hora_str}</b>\n"]

    # ── Más barata ────────────────────────────────────────────
    lines.append("🏆 <b>Más barata</b>")
    for tipo in FUEL_ORDER:
        if tipo not in zgza_data:
            continue
        d = zgza_data[tipo]
        lines.append(f"<b>{tipo}</b>: {d['precio']}")
        lines.append(f"  🏪 {d['estacion']}")
        if d.get("direccion"):
            lines.append(f"  📍 {d['direccion'][:60]}")

    lines.append("")

    # ── Top gasolineras ───────────────────────────────────────
    lines.append("📋 <b>Top gasolineras</b>")
    for station, fuels in top_data.items():
        lines.append(f"\n⛽ <b>{station}</b>")
        for fuel in FUEL_ORDER:
            if fuel not in fuels:
                continue
            price = fuels[fuel]
            # Precio inicial si existe y es diferente
            initial_price = (initial_snapshot or {}).get("top", {}).get(station, {}).get(fuel)
            if initial_price and initial_price != price:
                price_display = f"{initial_price} → <b>{price}</b>"
            else:
                price_display = price

            if station in winners.get(fuel, set()):
                lines.append(f"  🏆 <b>{fuel}: {price_display}</b>")
            else:
                lines.append(f"  · {fuel}: {price_display}")

    return "\n".join(lines)
