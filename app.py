from flask import Flask, jsonify
from flask_cors import CORS
import yfinance as yf
import pandas_ta as ta

app = Flask(__name__)
CORS(app)

@app.route('/', methods=['GET'])
def get_live_signal():
    try:
        # Descargar velas en tiempo real de XAUUSD (GC=F / Gold Futures)
        df = yf.download(tickers='GC=F', period='1d', interval='1m')

        if df.empty or len(df) < 20:
            return jsonify({"error": "No se pudieron obtener datos del mercado"}), 500

        # Corregir formato de columnas si yfinance devuelve MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Calcular Indicadores Técnicos Profesionales
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        bb = ta.bbands(df['Close'], length=20, std=2)
        df['BBL'] = bb['BBL_20_2.0'] # Banda Inferior
        df['BBU'] = bb['BBU_20_2.0'] # Banda Superior

        df['EMA_9'] = ta.ema(df['Close'], length=9)

        # Obtener los valores de la última vela cerrada
        last_row = df.iloc[-1]
        price = round(float(last_row['Close']), 2)
        rsi = round(float(last_row['RSI']), 2)
        bbl = round(float(last_row['BBL']), 2)
        bbu = round(float(last_row['BBU']), 2)
        ema = round(float(last_row['EMA_9']), 2)

        # Lógica de Análisis Profesional
        signal = "ESPERAR ⏳"
        
        # Condición de COMPRA: Sobrevendido en RSI + Precio por debajo de Banda Inferior de Bollinger
        if rsi < 30 and price <= bbl:
            signal = "COMPRA FUERTE 🚀"
        elif rsi < 40 and price > ema:
            signal = "COMPRA 📈"

        # Condición de VENTA: Sobrecomprado en RSI + Precio por encima de Banda Superior de Bollinger
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
