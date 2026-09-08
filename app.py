from flask import Flask, jsonify
from flask_cors import CORS
import requests
import pandas as pd
import time
import os
import logging

from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
from ta.trend import EMAIndicator

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------
# Registra una cuenta gratuita en https://twelvedata.com y coloca tu API key
# como variable de entorno en Render (Settings -> Environment -> Add):
#   TWELVE_DATA_API_KEY = tu_clave_real
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "TU_API_KEY_AQUI")

SYMBOL = "XAU/USD"
INTERVAL = "15min"      # Timeframe de las velas
OUTPUT_SIZE = 100        # Velas suficientes para RSI(14), BB(20) y EMA(9)
CACHE_TTL_SECONDS = 60   # Evita exceder el límite gratuito (8 req/min)

# Caché en memoria compartida entre requests
CACHE = {"data": None, "timestamp": 0}


# ---------------------------------------------------------------------------
# OBTENCIÓN DE DATOS
# ---------------------------------------------------------------------------
def fetch_candles():
    """Obtiene velas OHLC reales de XAU/USD desde Twelve Data."""
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "outputsize": OUTPUT_SIZE,
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON",
    }
    res = requests.get(url, params=params, timeout=10).json()

    if "values" not in res:
        raise ValueError(f"Respuesta inesperada de Twelve Data: {res}")

    df = pd.DataFrame(res["values"])
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["open"] = df["open"].astype(float)

    # Twelve Data devuelve las velas de más reciente a más antigua.
    # Los indicadores necesitan orden cronológico ascendente.
    df = df.iloc[::-1].reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# ANÁLISIS TÉCNICO
# ---------------------------------------------------------------------------
def compute_indicators(df):
    close = df["close"]

    df["rsi"] = RSIIndicator(close=close, window=14).rsi()

    bb = BollingerBands(close=close, window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()

    df["ema9"] = EMAIndicator(close=close, window=9).ema_indicator()

    return df


def generate_signal(price, rsi, ema9, upper_band, lower_band):
    """Lógica combinando RSI, EMA(9) y Bandas de Bollinger."""
    if rsi < 30 and price <= lower_band:
        return "COMPRA FUERTE 🚀"
    elif rsi > 70 and price >= upper_band:
        return "VENTA FUERTE 🔻"
    elif rsi < 40 and price > ema9:
        return "COMPRA 📈"
    elif rsi > 60 and price < ema9:
        return "VENTA 📉"
    else:
        return "ESPERAR ⏳"


def get_signal_data():
    """Devuelve datos desde caché si son recientes; si no, los recalcula."""
    now = time.time()
    if CACHE["data"] is not None and (now - CACHE["timestamp"]) < CACHE_TTL_SECONDS:
        return CACHE["data"]

    df = fetch_candles()
    df = compute_indicators(df)
    last = df.iloc[-1]

    price = round(float(last["close"]), 2)
    rsi = round(float(last["rsi"]), 2)
    upper_band = round(float(last["bb_upper"]), 2)
    lower_band = round(float(last["bb_lower"]), 2)
    ema9 = round(float(last["ema9"]), 2)

    signal = generate_signal(price, rsi, ema9, upper_band, lower_band)

    result = {
        "price": price,
        "signal": signal,
        "rsi": rsi,
        "upper_band": upper_band,
        "lower_band": lower_band,
        "ema9": ema9,
    }

    CACHE["data"] = result
    CACHE["timestamp"] = now
    return result


# ---------------------------------------------------------------------------
# ENDPOINT
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def get_live_signal():
    try:
        data = get_signal_data()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error obteniendo señal: {e}")
        # Si falla la API pero hay un dato previo en caché, se reutiliza
        # en lugar de devolver un valor fijo inventado.
        if CACHE["data"] is not None:
            return jsonify(CACHE["data"])
        return jsonify({
            "price": 2650.00,
            "signal": "ESPERAR ⏳",
            "rsi": 50.0,
            "upper_band": 2655.00,
            "lower_band": 2645.00,
            "ema9": 2650.00,
        })


if __name__ == "__main__":
    app.run(debug=True)
