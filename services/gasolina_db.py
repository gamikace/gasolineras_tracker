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
                # Normalizar precio a float
                precio = float(precio_str.replace("€", "").replace(",", ".").strip())

                # Comprobar si ya existe para esta fecha, estacion y tipo
                c.execute('''
                    SELECT id FROM precios_top
                    WHERE date = ? AND estacion = ? AND tipo_combustible = ?
                ''', (date_str, estacion, tipo))

                row = c.fetchone()
                if row:
                    # Actualizar
                    c.execute('''
                        UPDATE precios_top SET precio = ?, timestamp = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (precio, row[0]))
                else:
                    # Insertar
                    c.execute('''
                        INSERT INTO precios_top (date, estacion, tipo_combustible, precio)
                        VALUES (?, ?, ?, ?)
                    ''', (date_str, estacion, tipo, precio))

            except ValueError:
                continue

    conn.commit()
    conn.close()
