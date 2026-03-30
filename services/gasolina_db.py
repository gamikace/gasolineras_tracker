import sqlite3
import os
from datetime import datetime

DB_FILE = "data/gasolina_history.db"

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS precios_top (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            date TEXT,
            estacion TEXT,
            tipo_combustible TEXT,
            precio REAL
        )
    ''')
    # Deduplicar filas existentes antes de crear el índice único (migración segura)
    c.execute('''
        DELETE FROM precios_top
        WHERE id NOT IN (
            SELECT MIN(id) FROM precios_top
            GROUP BY date, estacion, tipo_combustible
        )
    ''')
    # Índice compuesto para las consultas de estadísticas (filtro por combustible + rango de fechas)
    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_precios_fuel_date
        ON precios_top(tipo_combustible, date)
    ''')
    # Índice único para upserts eficientes sin SELECT previo
    c.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_precios_unique
        ON precios_top(date, estacion, tipo_combustible)
    ''')
    conn.commit()
    conn.close()

def insert_precios_top(date_str: str, top_data: dict):
    """
    Inserta o actualiza (si ya existe para esa fecha) los precios de las gasolineras top.
    top_data: {estacion: {tipo: precio_str}}
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    for estacion, fuels in top_data.items():
        for tipo, precio_str in fuels.items():
            try:
                precio = float(precio_str.replace("€", "").replace(",", ".").strip())
                c.execute('''
                    INSERT INTO precios_top (date, estacion, tipo_combustible, precio)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(date, estacion, tipo_combustible)
                    DO UPDATE SET precio = excluded.precio, timestamp = CURRENT_TIMESTAMP
                ''', (date_str, estacion, tipo, precio))
            except ValueError:
                continue

    conn.commit()
    conn.close()
