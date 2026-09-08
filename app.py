import os
import math
import requests
from datetime import datetime, timezone

from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ============================================================
# CONFIGURACIÓN
# ============================================================

TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")

SYMBOL = "XAU/USD"
INTERVAL = "1min"

# Número de velas utilizadas para el análisis
OUTPUTSIZE = 200

# Riesgo aproximado basado en ATR
ATR_SL_MULTIPLIER = 1.5

# Relación riesgo/beneficio
TP1_RR = 1.5
TP2_RR = 2.5


# ============================================================
# FUNCIONES
# ============================================================

def obtener_velas():
    """
    Obtiene velas de XAU/USD desde Twelve Data.
    """

    if not TWELVE_DATA_API_KEY:
        raise Exception(
            "Falta TWELVE_DATA_API_KEY en las variables de entorno de Render."
        )

    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "outputsize": OUTPUTSIZE,
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON"
    }

    response = requests.get(url, params=params, timeout=15)

    if response.status_code != 200:
        raise Exception(
            f"Error HTTP Twelve Data: {response.status_code}"
        )

    data = response.json()

    if "status" in data and data["status"] == "error":
        raise Exception(
            data.get("message", "Error desconocido de Twelve Data")
        )

    values = data.get("values")

    if not values:
        raise Exception("No se recibieron velas de XAU/USD.")

    # Twelve Data normalmente entrega de más reciente a más antiguo.
    values = list(reversed(values))

    candles = []

    for candle in values:
        try:
            candles.append({
                "datetime": candle["datetime"],
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
            })
        except Exception:
            continue

    if len(candles) < 50:
        raise Exception("No hay suficientes velas para analizar.")

    return candles


def ema(values, period):
    """
    Calcula EMA.
    """

    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    ema_value = sum(values[:period]) / period

    for price in values[period:]:
        ema_value = (
            (price - ema_value) * multiplier
        ) + ema_value

    return ema_value


def rsi(values, period=14):
    """
    Calcula RSI.
    """

    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def bollinger(values, period=20, deviation=2):
    """
    Calcula Bandas de Bollinger.
    """

    if len(values) < period:
        return None, None, None

    recent = values[-period:]

    middle = sum(recent) / period

    variance = sum(
        (x - middle) ** 2 for x in recent
    ) / period

    std = math.sqrt(variance)

    upper = middle + deviation * std
    lower = middle - deviation * std

    return middle, upper, lower


def atr(candles, period=14):
    """
    Calcula ATR.
    """

    if len(candles) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(candles)):

        high = candles[i]["high"]
        low = candles[i]["low"]
        previous_close = candles[i - 1]["close"]

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    atr_value = sum(true_ranges[:period]) / period

    for tr in true_ranges[period:]:
        atr_value = (
            (atr_value * (period - 1)) + tr
        ) / period

    return atr_value


def redondear(valor):
    return round(float(valor), 2)


# ============================================================
# GENERADOR DE SEÑAL
# ============================================================

def analizar(candles):

    closes = [c["close"] for c in candles]

    precio = closes[-1]

    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)

    rsi_value = rsi(closes, 14)

    bb_middle, bb_upper, bb_lower = bollinger(
        closes,
        20,
        2
    )

    atr_value = atr(candles, 14)

    if (
        ema9 is None
        or ema21 is None
        or rsi_value is None
        or bb_upper is None
        or bb_lower is None
        or atr_value is None
    ):
        raise Exception("No se pudieron calcular todos los indicadores.")

    # ========================================================
    # SISTEMA DE PUNTOS
    # ========================================================

    buy_points = 0
    sell_points = 0

    razones_compra = []
    razones_venta = []

    # --------------------------------------------------------
    # EMA 9 vs EMA 21
    # --------------------------------------------------------

    if ema9 > ema21:
        buy_points += 2
        razones_compra.append("EMA 9 > EMA 21")

    elif ema9 < ema21:
        sell_points += 2
        razones_venta.append("EMA 9 < EMA 21")

    # --------------------------------------------------------
    # PRECIO VS EMA 9
    # --------------------------------------------------------

    if precio > ema9:
        buy_points += 1
        razones_compra.append("Precio sobre EMA 9")

    elif precio < ema9:
        sell_points += 1
        razones_venta.append("Precio bajo EMA 9")

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    if 50 <= rsi_value <= 70:
        buy_points += 2
        razones_compra.append("RSI favorable para compra")

    elif 30 <= rsi_value < 50:
        sell_points += 1
        razones_venta.append("RSI débil")

    elif rsi_value < 30:
        buy_points += 2
        razones_compra.append("RSI sobreventa")

    elif rsi_value > 70:
        sell_points += 2
        razones_venta.append("RSI sobrecompra")

    # --------------------------------------------------------
    # BANDAS DE BOLLINGER
    # --------------------------------------------------------

    if precio <= bb_lower:
        buy_points += 2
        razones_compra.append("Precio cerca de banda inferior")

    elif precio >= bb_upper:
        sell_points += 2
        razones_venta.append("Precio cerca de banda superior")

    # --------------------------------------------------------
    # DISTANCIA A EMA 21
    # --------------------------------------------------------

    if precio > ema21:
        buy_points += 1
    else:
        sell_points += 1

    # ========================================================
    # DECISIÓN
    # ========================================================

    diferencia = buy_points - sell_points

    total_points = max(
        buy_points + sell_points,
        1
    )

    if diferencia >= 5:
        signal = "COMPRA FUERTE 🟢"
        direction = "BUY"

    elif diferencia >= 2:
        signal = "COMPRA 🟢"
        direction = "BUY"

    elif diferencia <= -5:
        signal = "VENTA FUERTE 🔴"
        direction = "SELL"

    elif diferencia <= -2:
        signal = "VENTA 🔴"
        direction = "SELL"

    else:
        signal = "ESPERAR ⏳"
        direction = "WAIT"

    # ========================================================
    # CONFIANZA
    # ========================================================

    max_possible = 9

    if direction == "BUY":
        confidence = 50 + (diferencia / max_possible) * 50

    elif direction == "SELL":
        confidence = 50 + (abs(diferencia) / max_possible) * 50

    else:
        confidence = 50

    confidence = max(
        50,
        min(99, confidence)
    )

    # ========================================================
    # STOP LOSS / TAKE PROFIT
    # ========================================================

    risk_distance = atr_value * ATR_SL_MULTIPLIER

    if direction == "BUY":

        stop_loss = precio - risk_distance

        take_profit_1 = precio + (
            risk_distance * TP1_RR
        )

        take_profit_2 = precio + (
            risk_distance * TP2_RR
        )

    elif direction == "SELL":

        stop_loss = precio + risk_distance

        take_profit_1 = precio - (
            risk_distance * TP1_RR
        )

        take_profit_2 = precio - (
            risk_distance * TP2_RR
        )

    else:

        stop_loss = None
        take_profit_1 = None
        take_profit_2 = None

    # ========================================================
    # RESULTADO
    # ========================================================

    return {
        "symbol": "XAU/USD",
        "timeframe": "1min",

        "price": redondear(precio),

        "signal": signal,
        "direction": direction,

        "confidence": redondear(confidence),

        "ema9": redondear(ema9),
        "ema21": redondear(ema21),

        "rsi": redondear(rsi_value),

        "upper_band": redondear(bb_upper),
        "middle_band": redondear(bb_middle),
        "lower_band": redondear(bb_lower),

        "atr": redondear(atr_value),

        "stop_loss": (
            redondear(stop_loss)
            if stop_loss is not None
            else None
        ),

        "take_profit_1": (
            redondear(take_profit_1)
            if take_profit_1 is not None
            else None
        ),

        "take_profit_2": (
            redondear(take_profit_2)
            if take_profit_2 is not None
            else None
        ),

        "buy_points": buy_points,
        "sell_points": sell_points,

        "reasons_buy": razones_compra,
        "reasons_sell": razones_venta,

        "time": datetime.now(
            timezone.utc
        ).isoformat()
    }


# ============================================================
# API
# ============================================================

@app.route("/", methods=["GET"])
def home():

    try:

        candles = obtener_velas()

        resultado = analizar(candles)

        resultado["api_status"] = "connected"

        return jsonify(resultado)

    except Exception as error:

        return jsonify({
            "api_status": "error",
            "symbol": "XAU/USD",
            "timeframe": "1min",
            "signal": "ERROR",
            "message": str(error)
        }), 500


@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "status": "ok",
        "service": "XAUUSD Signal API"
    })


# ============================================================
# RENDER
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
