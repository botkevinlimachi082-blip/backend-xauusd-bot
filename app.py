from flask import Flask, jsonify
from flask_cors import CORS
import random

app = Flask(__name__)
CORS(app)

@app.route('/', methods=['GET'])
def get_signal():
    precio_simulado = round(random.uniform(2620.00, 2680.00), 2)
    senales = ["COMPRA 🚀", "VENTA 🔻", "ESPERAR ⏳"]
    
    return jsonify({
        "price": precio_simulado,
        "signal": random.choice(senales)
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
  
