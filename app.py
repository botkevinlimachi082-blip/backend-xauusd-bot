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

# ============================================================
# CONFIGURACIÓN
# ============================================================

TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY")

SYMBOL = "XAU/USD"
INTERVAL = "1min"
OUTPUT_SIZE = 100

# Actualizar como máximo cada 10 segundos
CACHE_TTL_SECONDS = 10

CACHE = {
    "data": None,
    "timestamp": 0
}


# ============================================================
# OBTENER DATOS REALES DE XAU/USD
# ============================================================

def fetch_candles():

    if not TWELVE_DATA_API_KEY:
        raise ValueError("No existe TWELVE_DATA_API_KEY en Render")

    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "outputsize": OUTPUT_SIZE,
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON"
    }

    response = requests.get(
        url,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    data = response.json()

    if "values" not in data:
        raise ValueError(
            f"Respuesta inesperada de Twelve Data: {data}"
        )

    df = pd.DataFrame(data["values"])

    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)

    # Twelve Data entrega las velas de más nueva a más antigua.
    # Las ponemos en orden cronológico.
    df = df.iloc[::-1].reset_index(drop=True)

    return df


# ============================================================
# INDICADORES
# ============================================================

def compute_indicators(df):

    close = df["close"]

    # RSI 14
    rsi = RSIIndicator(
        close=close,
        window=14
    )

    df["rsi"] = rsi.rsi()

    # Bollinger Bands 20 / 2
    bb = BollingerBands(
        close=close,
        window=20,
        window_dev=2
    )

    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()

    # EMA 9
    ema = EMAIndicator(
        close=close,
        window=9
    )

    df["ema9"] = ema.ema_indicator()

    return df


# ============================================================
# GENERAR SEÑAL
# ============================================================

def generate_signal(
    price,
    rsi,
    ema9,
    upper_band,
    lower_band
):

    # COMPRA FUERTE
    if rsi < 30 and price <= lower_band:
        return "COMPRA FUERTE 🚀"

    # VENTA FUERTE
    elif rsi > 70 and price >= upper_band:
        return "VENTA FUERTE 🔻"

    # COMPRA
    elif rsi < 40 and price > ema9:
        return "COMPRA 📈"

    # VENTA
    elif rsi > 60 and price < ema9:
        return "VENTA 📉"

    # SIN CONFIRMACIÓN
    else:
        return "ESPERAR ⏳"


# ============================================================
# OBTENER SEÑAL
# ============================================================

def get_signal_data():

    now = time.time()

    # Utilizar caché si todavía está vigente
    if (
        CACHE["data"] is not None
        and (now - CACHE["timestamp"]) < CACHE_TTL_SECONDS
    ):
        return CACHE["data"]

    # Obtener velas reales
    df = fetch_candles()

    # Calcular indicadores
    df = compute_indicators(df)

    # Última vela
    last = df.iloc[-1]

    price = round(float(last["close"]), 2)
    rsi = round(float(last["rsi"]), 2)
    upper_band = round(float(last["bb_upper"]), 2)
    lower_band = round(float(last["bb_lower"]), 2)
    ema9 = round(float(last["ema9"]), 2)

    # Generar señal
    signal = generate_signal(
        price,
        rsi,
        ema9,
        upper_band,
        lower_band
    )

    result = {
        "price": price,
        "signal": signal,
        "rsi": rsi,
        "upper_band": upper_band,
        "lower_band": lower_band,
        "ema9": ema9,
        "timeframe": "1min",
        "symbol": "XAU/USD"
    }

    # Guardar caché
    CACHE["data"] = result
    CACHE["timestamp"] = now

    return result


# ============================================================
# API PRINCIPAL
# ============================================================

@app.route("/", methods=["GET"])
def get_live_signal():

    try:

        data = get_signal_data()

        return jsonify(data)

    except Exception as e:

        logger.error(
            f"Error obteniendo señal: {e}"
        )

        # Si tenemos información anterior,
        # devolverla indicando que es información almacenada.
        if CACHE["data"] is not None:

            stale_data = CACHE["data"].copy()
            stale_data["status"] = "stale"

            return jsonify(stale_data), 200

        # No inventar precio ni indicadores.
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 503


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "status": "ok",
        "symbol": SYMBOL,
        "timeframe": INTERVAL
    })


# ============================================================
# EJECUTAR SERVIDOR
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
