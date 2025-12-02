import os
import re
import pymysql
import requests
from bs4 import BeautifulSoup
from flask import (
    Flask, render_template, jsonify
)
from dotenv import load_dotenv

# Cargar variables de entorno (Railway las pone automáticamente)
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia_esto")

# Configuración DB desde entorno o .env
DB_HOST = os.environ.get("DB_HOST")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME")

def get_db_conn():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
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
    # Busca patrón en el HTML (actualízalo según cambie la web del BCV)
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
                c.execute("INSERT INTO tasas_bcv (tasa) VALUES (%s)", (valor,))
                conn.commit()
    except Exception as e:
        print("Error guardando tasa:", e)
        return False
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

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/tasa_bcv/actualizar', methods=['POST'])
def actualizar_tasa():
    tasa = obtener_valor_dolar_bcv()
    if tasa:
        guardar_tasa(tasa)
        return jsonify({'tasa': tasa, 'ok': True})
    else:
        return jsonify({'error': 'No se pudo obtener el valor', 'ok': False}), 500

@app.route('/api/tasa_bcv', methods=['GET'])
def api_tasa():
    dato = obtener_tasa_actual()
    if dato:
        return jsonify({"tasa": dato['tasa'], "fecha": str(dato['fecha'])})
    else:
        return jsonify({'error': 'No hay tasa disponible'}), 404
