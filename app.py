from flask import Flask, jsonify
from flask_cors import CORS
import requests
import pandas as pd
import ta

app = Flask(__name__)
CORS(app)

@app.route('/', methods=['GET'])
def get_live_signal():
    try:
        # Petición a API pública de cotización SPOT en tiempo real para XAUUSD
        url = "https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=1m&limit=50"
        response = requests.get(url, timeout=5)
        data = response.json()

        if not isinstance(data, list) or len(data) < 20:
            return jsonify({"error": "No se pudieron obtener datos spot"}), 500

        # Crear DataFrame con precios de cierre SPOT
        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
        close_series = df['close'].astype(float)

        # Cálculo de Indicadores
        rsi_indicator = ta.momentum.RSIIndicator(close=close_series, window=14)
        rsi = round(float(rsi_indicator.rsi().iloc[-1]), 2)

        bb = ta.volatility.BollingerBands(close=close_series, window=20, window_dev=2)
        bbl = round(float(bb.bollinger_lband().iloc[-1]), 2)
        bbu = round(float(bb.bollinger_hband().iloc[-1]), 2)

        ema_indicator = ta.trend.EMAIndicator(close=close_series, window=9)
        ema = round(float(ema_indicator.ema_indicator().iloc[-1]), 2)

        price = round(float(close_series.iloc[-1]), 2)

        # Lógica de Análisis Profesional
        signal = "ESPERAR ⏳"
        if rsi < 30 and price <= bbl:
            signal = "COMPRA FUERTE 🚀"
        elif rsi < 40 and price > ema:
            signal = "COMPRA 📈"
        elif rsi > 70 and price >= bbu:
            signal = "VENTA FUERTE 🔻"
        elif rsi > 60 and price < ema:
            signal = "VENTA 📉"

        return jsonify({
            "price": price,
            "signal": signal,
            "rsi": rsi,
            "upper_band": bbu,
            "lower_band": bbl
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
