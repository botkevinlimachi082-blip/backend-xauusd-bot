import os
import math
import requests
from datetime import datetime, timezone

from flask import Flask, jsonify
from flask_cors import CORS


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)
CORS(app)


# ============================================================
# CONFIGURACIÓN
# ============================================================

TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")

SYMBOL = "XAU/USD"
INTERVAL = "1min"

# Velas para el análisis
OUTPUTSIZE = 200

# Stop Loss basado en ATR
ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 1.5

# Take Profit basado en relación Riesgo/Beneficio
TP1_RR = 1.5
TP2_RR = 2.5


# ============================================================
# OBTENER VELAS
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

    response = requests.get(
        url,
        params=params,
        timeout=15
    )

    if response.status_code != 200:
        raise Exception(
            f"Error HTTP Twelve Data: {response.status_code}"
        )

    data = response.json()

    if data.get("status") == "error":
        raise Exception(
            data.get(
                "message",
                "Error desconocido de Twelve Data"
            )
        )

    values = data.get("values")

    if not values:
        raise Exception(
            "No se recibieron velas de XAU/USD."
        )

    # Twelve Data normalmente entrega
    # desde la vela más reciente hacia atrás.
    values = list(reversed(values))

    candles = []

    for candle in values:
        try:
            candles.append({
                "datetime": candle["datetime"],
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"])
            })
        except Exception:
            continue

    if len(candles) < 50:
        raise Exception(
            "No hay suficientes velas para analizar."
        )

    return candles


# ============================================================
# EMA
# ============================================================

def ema(values, period):
    """
    Calcula EMA.
    """

    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    ema_value = sum(
        values[:period]
    ) / period

    for price in values[period:]:
        ema_value = (
            (price - ema_value) * multiplier
        ) + ema_value

    return ema_value


# ============================================================
# RSI
# ============================================================

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

    avg_gain = sum(
        gains[:period]
    ) / period

    avg_loss = sum(
        losses[:period]
    ) / period

    for i in range(period, len(gains)):

        avg_gain = (
            (
                avg_gain * (period - 1)
            ) + gains[i]
        ) / period

        avg_loss = (
            (
                avg_loss * (period - 1)
            ) + losses[i]
        ) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (
        100 / (1 + rs)
    )


# ============================================================
# BANDAS DE BOLLINGER
# ============================================================

def bollinger(
    values,
    period=20,
    deviation=2
):
    """
    Calcula Bandas de Bollinger.
    """

    if len(values) < period:
        return None, None, None

    recent = values[-period:]

    middle = sum(recent) / period

    variance = sum(
        (x - middle) ** 2
        for x in recent
    ) / period

    std = math.sqrt(variance)

    upper = middle + (
        deviation * std
    )

    lower = middle - (
        deviation * std
    )

    return middle, upper, lower


# ============================================================
# ATR
# ============================================================

def atr(candles, period=14):
    """
    Calcula ATR usando True Range.
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

    atr_value = sum(
        true_ranges[:period]
    ) / period

    for tr in true_ranges[period:]:

        atr_value = (
            (
                atr_value * (period - 1)
            ) + tr
        ) / period

    return atr_value


# ============================================================
# REDONDEAR
# ============================================================

def redondear(valor):

    if valor is None:
        return None

    return round(
        float(valor),
        2
    )


# ============================================================
# GENERAR SEÑAL
# ============================================================

def analizar(candles):

    closes = [
        candle["close"]
        for candle in candles
    ]

    precio = closes[-1]

    # --------------------------------------------------------
    # INDICADORES
    # --------------------------------------------------------

    ema9 = ema(
        closes,
        9
    )

    ema21 = ema(
        closes,
        21
    )

    rsi_value = rsi(
        closes,
        14
    )

    bb_middle, bb_upper, bb_lower = bollinger(
        closes,
        20,
        2
    )

    atr_value = atr(
        candles,
        ATR_PERIOD
    )

    if (
        ema9 is None
        or ema21 is None
        or rsi_value is None
        or bb_upper is None
        or bb_lower is None
        or atr_value is None
    ):
        raise Exception(
            "No se pudieron calcular todos los indicadores."
        )

    # ========================================================
    # SISTEMA DE PUNTOS
    # ========================================================

    buy_points = 0
    sell_points = 0

    razones_compra = []
    razones_venta = []

    # --------------------------------------------------------
    # 1. EMA 9 VS EMA 21
    # --------------------------------------------------------

    if ema9 > ema21:

        buy_points += 2

        razones_compra.append(
            "EMA 9 por encima de EMA 21"
        )

    elif ema9 < ema21:

        sell_points += 2

        razones_venta.append(
            "EMA 9 por debajo de EMA 21"
        )

    # --------------------------------------------------------
    # 2. PRECIO VS EMA 9
    # --------------------------------------------------------

    if precio > ema9:

        buy_points += 1

        razones_compra.append(
            "Precio sobre EMA 9"
        )

    elif precio < ema9:

        sell_points += 1

        razones_venta.append(
            "Precio bajo EMA 9"
        )

    # --------------------------------------------------------
    # 3. RSI
    # --------------------------------------------------------

    if 50 <= rsi_value <= 70:

        buy_points += 2

        razones_compra.append(
            "RSI favorable para compra"
        )

    elif 30 <= rsi_value < 50:

        sell_points += 1

        razones_venta.append(
            "RSI muestra debilidad"
        )

    elif rsi_value < 30:

        buy_points += 2

        razones_compra.append(
            "RSI en sobreventa"
        )

    elif rsi_value > 70:

        sell_points += 2

        razones_venta.append(
            "RSI en sobrecompra"
        )

    # --------------------------------------------------------
    # 4. BOLLINGER
    # --------------------------------------------------------

    if precio <= bb_lower:

        buy_points += 2

        razones_compra.append(
            "Precio cerca de banda inferior"
        )

    elif precio >= bb_upper:

        sell_points += 2

        razones_venta.append(
            "Precio cerca de banda superior"
        )

    # --------------------------------------------------------
    # 5. PRECIO VS EMA 21
    # --------------------------------------------------------

    if precio > ema21:

        buy_points += 1

        razones_compra.append(
            "Precio sobre EMA 21"
        )

    else:

        sell_points += 1

        razones_venta.append(
            "Precio bajo EMA 21"
        )

    # ========================================================
    # DIFERENCIA
    # ========================================================

    diferencia = (
        buy_points - sell_points
    )

    total_points = (
        buy_points + sell_points
    )

    # ========================================================
    # SEÑAL
    # ========================================================

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
    # TENDENCIA
    # ========================================================

    if ema9 > ema21:

        trend = "ALCISTA 🟢"

    elif ema9 < ema21:

        trend = "BAJISTA 🔴"

    else:

        trend = "NEUTRAL 🟡"

    # ========================================================
    # CONFIANZA
    # ========================================================

    # Máximo teórico del sistema:
    # EMA = 2
    # Precio EMA9 = 1
    # RSI = 2
    # Bollinger = 2
    # EMA21 = 1
    # Total = 8

    max_possible = 8

    if direction == "BUY":

        confidence = (
            50
            + (diferencia / max_possible) * 50
        )

    elif direction == "SELL":

        confidence = (
            50
            + (abs(diferencia) / max_possible) * 50
        )

    else:

        confidence = 50

    confidence = max(
        50,
        min(
            99,
            confidence
        )
    )

    # ========================================================
    # STOP LOSS / TAKE PROFIT
    # ========================================================

    risk_distance = (
        atr_value * ATR_SL_MULTIPLIER
    )

    if direction == "BUY":

        entry_price = precio

        stop_loss = (
            entry_price - risk_distance
        )

        take_profit_1 = (
            entry_price
            + (risk_distance * TP1_RR)
        )

        take_profit_2 = (
            entry_price
            + (risk_distance * TP2_RR)
        )

    elif direction == "SELL":

        entry_price = precio

        stop_loss = (
            entry_price + risk_distance
        )

        take_profit_1 = (
            entry_price
            - (risk_distance * TP1_RR)
        )

        take_profit_2 = (
            entry_price
            - (risk_distance * TP2_RR)
        )

    else:

        entry_price = precio

        stop_loss = None
        take_profit_1 = None
        take_profit_2 = None

    # ========================================================
    # RIESGO / BENEFICIO
    # ========================================================

    risk_reward_tp1 = TP1_RR
    risk_reward_tp2 = TP2_RR

    # ========================================================
    # MOMENTO DE LA VELA
    # ========================================================

    candle_time = candles[-1]["datetime"]

    # ========================================================
    # RESULTADO
    # ========================================================

    return {

        # ----------------------------------------------------
        # IDENTIFICACIÓN
        # ----------------------------------------------------

        "symbol": SYMBOL,

        "timeframe": INTERVAL,

        "platform": "MetaTrader 5",

        "data_source": "Twelve Data",

        # ----------------------------------------------------
        # PRECIO
        # ----------------------------------------------------

        "price": redondear(
            precio
        ),

        "entry_price": redondear(
            entry_price
        ),

        # ----------------------------------------------------
        # SEÑAL
        # ----------------------------------------------------

        "signal": signal,

        "direction": direction,

        "trend": trend,

        "confidence": redondear(
            confidence
        ),

        # ----------------------------------------------------
        # PUNTOS
        # ----------------------------------------------------

        "buy_points": buy_points,

        "sell_points": sell_points,

        "difference": diferencia,

        "total_points": total_points,

        # ----------------------------------------------------
        # INDICADORES
        # ----------------------------------------------------

        "ema9": redondear(
            ema9
        ),

        "ema21": redondear(
            ema21
        ),

        "rsi": redondear(
            rsi_value
        ),

        "atr": redondear(
            atr_value
        ),

        "upper_band": redondear(
            bb_upper
        ),

        "middle_band": redondear(
            bb_middle
        ),

        "lower_band": redondear(
            bb_lower
        ),

        # ----------------------------------------------------
        # RIESGO
        # ----------------------------------------------------

        "risk_distance": redondear(
            risk_distance
        ),

        "stop_loss": (
            redondear(stop_loss)
            if stop_loss is not None
            else None
        ),

        # ----------------------------------------------------
        # TAKE PROFITS
        # ----------------------------------------------------

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

        "tp1_rr": risk_reward_tp1,

        "tp2_rr": risk_reward_tp2,

        # ----------------------------------------------------
        # RAZONES
        # ----------------------------------------------------

        "reasons_buy": razones_compra,

        "reasons_sell": razones_venta,

        # ----------------------------------------------------
        # TIEMPO
        # ----------------------------------------------------

        "candle_time": candle_time,

        "time": datetime.now(
            timezone.utc
        ).isoformat()
    }


# ============================================================
# RUTA PRINCIPAL
# ============================================================

@app.route("/", methods=["GET"])
def home():

    try:

        candles = obtener_velas()

        resultado = analizar(
            candles
        )

        resultado["api_status"] = "connected"

        return jsonify(
            resultado
        )

    except Exception as error:

        return jsonify({

            "api_status": "error",

            "symbol": SYMBOL,

            "timeframe": INTERVAL,

            "signal": "ERROR",

            "message": str(error)

        }), 500


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({

        "status": "ok",

        "service": "XAUUSD Signal API",

        "symbol": SYMBOL,

        "timeframe": INTERVAL

    })


# ============================================================
# RENDER
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(

        host="0.0.0.0",

        port=port
            )            
