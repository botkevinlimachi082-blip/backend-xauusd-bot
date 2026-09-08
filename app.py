from flask import Flask, jsonify
from flask_cors import CORS
import pandas as pd
import yfinance as yf
import ta

app = Flask(__name__)
CORS(app)

@app.route('/', methods=['GET'])
def get_live_signal():
    try:
        # Descargar datos de XAUUSD (GC=F)
        df = yf.download(tickers='GC=F', period='1d', interval='1m')

        if df.empty or len(df) < 20:
            return jsonify({"error": "Sin datos suficientes del mercado"}), 500

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Cálculo de Indicadores con la librería 'ta'
        close_series = df['Close'].squeeze()
        
        # RSI (14)
        rsi_indicator = ta.momentum.RSIIndicator(close=close_series, window=14)
        df['RSI'] = rsi_indicator.rsi()

        # Bollinger Bands (20, 2)
        bb = ta.volatility.BollingerBands(close=close_series, window=20, window_dev=2)
        df['BBL'] = bb.bollinger_lband()
        df['BBU'] = bb.bollinger_hband()

        # EMA (9)
        ema_indicator = ta.trend.EMAIndicator(close=close_series, window=9)
        df['EMA_9'] = ema_indicator.ema_indicator()

        # Valores de la última vela
        last_row = df.iloc[-1]
        price = round(float(last_row['Close']), 2)
        rsi = round(float(last_row['RSI']), 2)
        bbl = round(float(last_row['BBL']), 2)
        bbu = round(float(last_row['BBU']), 2)
        ema = round(float(last_row['EMA_9']), 2)

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
