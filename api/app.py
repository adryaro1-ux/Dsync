import os
import re
import pymysql
import requests
from bs4 import BeautifulSoup
from flask import (
    Flask, render_template, jsonify
)
from dotenv import load_dotenv
from urllib.parse import urlparse # <-- NUEVA LIBRERÍA PARA ANALIZAR LA URL

# Cargar variables de entorno (solo si no están en el entorno de Vercel)
load_dotenv()

# --- INICIALIZACIÓN DE FLASK (Necesaria para las rutas) ---
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia_esto")

# --- CONFIGURACIÓN DE CONEXIÓN AIVEN (Corregido) ---
# Vercel provee esta variable, que contiene Host, User, Pass, Port y DB
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_conn():
    """
    Analiza la DATABASE_URL de Aiven y establece la conexión MySQL con SSL/TLS.
    """
    if not DATABASE_URL:
        # Esto debería fallar si la variable no está configurada en Vercel
        raise ValueError("DATABASE_URL no está configurada en el entorno.")

    # 1. Analiza la URL completa
    url = urlparse(DATABASE_URL)

    # 2. Conexión a la base de datos (usando los componentes analizados)
    return pymysql.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database=url.path[1:], # Ignora el '/' inicial en '/defaultdb'
        port=url.port,
        cursorclass=pymysql.cursors.DictCursor,
        # Aiven requiere SSL/TLS, así que lo forzamos.
        ssl={'ssl': True}
    )

def obtener_valor_dolar_bcv():
    url_bcv = 'https://www.bcv.org.ve/'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        r = requests.get(url_bcv, headers=headers, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print("Error conexión BCV:", e)
        return None
    soup = BeautifulSoup(r.text, 'html.parser')
    # Busca patrón en el HTML
    match = re.search(r'USD[^0-9]*?([\d.,]+)', soup.get_text())
    if match:
        valor = match.group(1).replace(',', '.')
        try:
            return round(float(valor), 4)
        except Exception:
            return None
    return None

def guardar_tasa(valor):
    try:
        conn = get_db_conn()
        with conn:
            with conn.cursor() as c:
                # Asegúrate de que la tabla 'tasas_bcv' existe en Aiven
                c.execute("INSERT INTO tasas_bcv (tasa) VALUES (%s)", (valor,))
                conn.commit()
    except Exception as e:
        print("Error guardando tasa:", e)
        # Esto es clave para ver el error en Vercel
        raise e 
    return True

def obtener_tasa_actual():
    try:
        conn = get_db_conn()
        with conn:
            with conn.cursor() as c:
                c.execute("SELECT tasa, fecha FROM tasas_bcv ORDER BY fecha DESC LIMIT 1;")
                row = c.fetchone()
                return row if row else {}
    except Exception as e:
        print("Error consultando tasa:", e)
        return {}

# --- RUTAS DE FLASK ---

@app.route('/')
def home():
    # Esta ruta muestra el HTML si lo quieres usar
    return render_template('index.html')

@app.route('/api/tasa_bcv/actualizar', methods=['GET', 'POST'])
def actualizar_tasa():
    """
    Ruta clave que el Cron Job llamará para actualizar la base de datos.
    """
    try:
        tasa = obtener_valor_dolar_bcv()
        if tasa:
            guardar_tasa(tasa)
            print(f"Tasa actualizada con éxito: {tasa}")
            return jsonify({'tasa': tasa, 'ok': True})
        else:
            print("No se pudo obtener el valor del BCV")
            return jsonify({'error': 'No se pudo obtener el valor', 'ok': False}), 500
    except Exception as e:
        print(f"Fallo crítico en actualización: {e}")
        # Al devolver un 500, el error es visible en los logs de Vercel
        return jsonify({'error': str(e), 'ok': False}), 500

@app.route('/api/tasa_bcv', methods=['GET'])
def api_tasa():
    # Esta ruta se usa para consultar el dato más reciente
    dato = obtener_tasa_actual()
    if dato:
        return jsonify({"tasa": dato['tasa'], "fecha": str(dato['fecha'])})
    else:
        return jsonify({'error': 'No hay tasa disponible'}), 404
