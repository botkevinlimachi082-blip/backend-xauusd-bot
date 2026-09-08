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
        # Petición con User-Agent para evitar bloqueos en servidores en la nube
        url = "https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=1m&limit=50"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            # Fuente de respaldo (Spot Gold API)
            backup_url = "https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=usd"
            res_backup = requests.get(backup_url, headers=headers, timeout=5).json()
            price = float(res_backup['pax-gold']['usd'])
            return jsonify({
                "price": round(price, 2),
                "signal": "ESPERAR ⏳",
                "rsi": 50.0,
                "upper_band": round(price + 5, 2),
                "lower_band": round(price - 5, 2)
            })

        data = response.json()

        # Crear DataFrame con precios de cierre
        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
        close_series = df['close'].astype(float)

        # Indicadores
        rsi_indicator = ta.momentum.RSIIndicator(close=close_series, window=14)
        rsi = round(float(rsi_indicator.rsi().iloc[-1]), 2)

        bb = ta.volatility.BollingerBands(close=close_series, window=20, window_dev=2)
        bbl = round(float(bb.bollinger_lband().iloc[-1]), 2)
        bbu = round(float(bb.bollinger_hband().iloc[-1]), 2)

        ema_indicator = ta.trend.EMAIndicator(close=close_series, window=9)
        ema = round(float(ema_indicator.ema_indicator().iloc[-1]), 2)

        price = round(float(close_series.iloc[-1]), 2)

        # Lógica de señales
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
