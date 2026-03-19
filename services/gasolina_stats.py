import sqlite3
from datetime import datetime, timedelta
import os
from .gasolina_db import DB_FILE

FUEL_ORDER = ["Gasolina 95 E5", "Gasolina 98 E5", "Gasoleo A", "Gasoleo Premium"]

def obtener_estadisticas_periodo(dias: int):
    """
    Obtiene las estadísticas de los últimos `dias` días.
    """
    if not os.path.exists(DB_FILE):
        return None

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    fecha_inicio = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")

    stats = {
        "picos": {},
        "variacion": {},
        "mas_barata_tiempo": {},
        "mas_cara_tiempo": {},
        "dias_baratos": {}
    }

    # 1. Picos más altos y bajos por combustible
    for fuel in FUEL_ORDER:
        c.execute('''
            SELECT estacion, MAX(precio) as precio_max, date
            FROM precios_top
            WHERE tipo_combustible = ? AND date >= ?
        ''', (fuel, fecha_inicio))
        row_max = c.fetchone()

        c.execute('''
            SELECT estacion, MIN(precio) as precio_min, date
            FROM precios_top
            WHERE tipo_combustible = ? AND date >= ?
        ''', (fuel, fecha_inicio))
        row_min = c.fetchone()

        if row_max and row_max['precio_max'] is not None and row_min and row_min['precio_min'] is not None:
            stats["picos"][fuel] = {
                "max": {"estacion": row_max["estacion"], "precio": row_max["precio_max"], "fecha": row_max["date"]},
                "min": {"estacion": row_min["estacion"], "precio": row_min["precio_min"], "fecha": row_min["date"]}
            }

    # 2. Gasolinera con mayor variación de precio (por combustible)
    for fuel in FUEL_ORDER:
        c.execute('''
            SELECT estacion, (MAX(precio) - MIN(precio)) as variacion
            FROM precios_top
            WHERE tipo_combustible = ? AND date >= ?
            GROUP BY estacion
            ORDER BY variacion DESC
            LIMIT 1
        ''', (fuel, fecha_inicio))
        row = c.fetchone()
        if row and row['variacion'] is not None and row['variacion'] > 0:
            stats["variacion"][fuel] = {"estacion": row["estacion"], "variacion": round(row["variacion"], 3)}

    # 3. Gasolinera que ha estado más barata/cara durante más tiempo (por combustible)
    # Contamos cuántos días cada gasolinera tuvo el precio mínimo/máximo diario
    for fuel in FUEL_ORDER:
        # Días en los que cada gasolinera fue la más barata
        c.execute('''
            SELECT estacion, COUNT(*) as dias_minimo FROM (
                SELECT date, estacion, MIN(precio) OVER (PARTITION BY date) as min_diario, precio
                FROM precios_top
                WHERE tipo_combustible = ? AND date >= ?
            ) sub WHERE precio = min_diario
            GROUP BY estacion
            ORDER BY dias_minimo DESC
            LIMIT 1
        ''', (fuel, fecha_inicio))
        row_min = c.fetchone()
        if row_min and row_min["dias_minimo"] > 0:
             stats["mas_barata_tiempo"][fuel] = {"estacion": row_min["estacion"], "dias": row_min["dias_minimo"]}

        # Días en los que cada gasolinera fue la más cara
        c.execute('''
            SELECT estacion, COUNT(*) as dias_maximo FROM (
                SELECT date, estacion, MAX(precio) OVER (PARTITION BY date) as max_diario, precio
                FROM precios_top
                WHERE tipo_combustible = ? AND date >= ?
            ) sub WHERE precio = max_diario
            GROUP BY estacion
            ORDER BY dias_maximo DESC
            LIMIT 1
        ''', (fuel, fecha_inicio))
        row_max = c.fetchone()
        if row_max and row_max["dias_maximo"] > 0:
             stats["mas_cara_tiempo"][fuel] = {"estacion": row_max["estacion"], "dias": row_max["dias_maximo"]}

    # 4. Día de la semana más barato por combustible
    # Promedio del precio mínimo de cada día de la semana
    for fuel in FUEL_ORDER:
        # SQLite: strftime('%w', date) -> 0 (Domingo) - 6 (Sábado)
        c.execute('''
            SELECT strftime('%w', date) as dia_semana, AVG(precio) as precio_medio
            FROM (
                SELECT date, MIN(precio) as precio
                FROM precios_top
                WHERE tipo_combustible = ? AND date >= ?
                GROUP BY date
            )
            GROUP BY dia_semana
            ORDER BY precio_medio ASC
            LIMIT 1
        ''', (fuel, fecha_inicio))
        row = c.fetchone()
        if row:
            dias_nombre = {
                "0": "Domingo", "1": "Lunes", "2": "Martes",
                "3": "Miércoles", "4": "Jueves", "5": "Viernes", "6": "Sábado"
            }
            dia_str = str(row["dia_semana"])
            stats["dias_baratos"][fuel] = {"dia": dias_nombre.get(dia_str, dia_str), "precio_medio": round(row["precio_medio"], 3)}

    conn.close()
    return stats

def formato_estadisticas_telegram(stats: dict, periodo_nombre: str) -> str:
    if not stats:
        return f"⛽ <b>No hay datos suficientes para el resumen {periodo_nombre.lower()}.</b>"

    lines = [f"📊 <b>Resumen {periodo_nombre} de Gasolineras TOP</b>\n"]

    if stats["picos"]:
        lines.append("📈 <b>Picos de Precio</b>")
        for fuel in FUEL_ORDER:
            if fuel in stats["picos"]:
                p = stats["picos"][fuel]
                lines.append(f"<b>{fuel}</b>:")
                lines.append(f"  🔴 Max: {p['max']['precio']}€ en {p['max']['estacion']} ({p['max']['fecha']})")
                lines.append(f"  🟢 Min: {p['min']['precio']}€ en {p['min']['estacion']} ({p['min']['fecha']})")
        lines.append("")

    if stats["dias_baratos"]:
        lines.append("📅 <b>Mejores Días Promedio para Comprar</b>")
        for fuel in FUEL_ORDER:
            if fuel in stats["dias_baratos"]:
                d = stats["dias_baratos"][fuel]
                lines.append(f"  · <b>{fuel}</b>: {d['dia']} (~{d['precio_medio']}€)")
        lines.append("")

    if stats["variacion"]:
        lines.append("🎢 <b>Mayor Variación de Precio</b>")
        for fuel in FUEL_ORDER:
             if fuel in stats["variacion"]:
                 v = stats["variacion"][fuel]
                 lines.append(f"  · <b>{fuel}</b>: {v['estacion']} (varió {v['variacion']}€)")
        lines.append("")

    if stats["mas_barata_tiempo"] or stats["mas_cara_tiempo"]:
        lines.append("⏳ <b>Récords de Permanencia</b>")
        for fuel in FUEL_ORDER:
            if fuel in stats["mas_barata_tiempo"]:
                 b = stats["mas_barata_tiempo"][fuel]
                 lines.append(f"  · Más días barata (<b>{fuel}</b>): {b['estacion']} ({b['dias']} días)")
            if fuel in stats["mas_cara_tiempo"]:
                 c = stats["mas_cara_tiempo"][fuel]
                 lines.append(f"  · Más días cara (<b>{fuel}</b>): {c['estacion']} ({c['dias']} días)")

    return "\n".join(lines)
