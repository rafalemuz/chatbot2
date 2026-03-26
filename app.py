from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json, csv, io, os, hmac, hashlib, requests

# IA
from openai import OpenAI

app = Flask(__name__)

# ---------------- CONFIG ----------------
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///metapython.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ---------------- IA ----------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------------- WHATSAPP ----------------
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# ---------------- SEGURIDAD ----------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "CHATCOURSE")
APP_SECRET = os.getenv("APP_SECRET", "")

# ---------------- MODELO ----------------
class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha_y_hora = db.Column(db.DateTime, default=datetime.utcnow)
    texto = db.Column(db.Text)

with app.app_context():
    db.create_all()

# ---------------- SEGURIDAD META ----------------
def verificar_firma(req):
    if not APP_SECRET:
        return True

    signature = req.headers.get("X-Hub-Signature-256")
    if not signature:
        return False

    try:
        sha_name, signature = signature.split('=')
    except:
        return False

    mac = hmac.new(
        APP_SECRET.encode(),
        msg=req.get_data(),
        digestmod=hashlib.sha256
    )

    return hmac.compare_digest(mac.hexdigest(), signature)

# ---------------- LOG ----------------
def agregar_mensaje_log(texto):
    try:
        db.session.add(Log(texto=texto))
        db.session.commit()
    except:
        db.session.rollback()

# ---------------- IA RESPUESTA ----------------
def responder_con_ia(mensaje):
    catalogo = """
    Catálogo:
    1. Playera - $200
    2. Zapatos - $500
    3. Gorra - $150
    """

    prompt = f"""
    Eres un vendedor experto por WhatsApp.

    OBJETIVO:
    - Vender productos
    - Responder dudas
    - Guiar al cliente a comprar

    {catalogo}

    Cliente: {mensaje}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        print("Error IA:", e)
        return "Hubo un error, intenta nuevamente."

# ---------------- DETECTAR COMPRA ----------------
def detectar_compra(texto):
    palabras = ["comprar", "quiero", "pagar", "ordenar"]
    return any(p in texto.lower() for p in palabras)

# ---------------- GENERAR PEDIDO ----------------
def generar_pedido(numero):
    mensaje = "✅ Pedido generado.\nTotal: $200\nGracias por tu compra 🎉"
    enviar_respuesta(numero, mensaje)

# ---------------- ENVIAR WHATSAPP ----------------
def enviar_respuesta(numero, mensaje):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("Faltan credenciales WhatsApp")
        return

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": mensaje}
    }

    try:
        requests.post(url, headers=headers, json=payload)
    except Exception as e:
        print("Error enviando:", e)

# ---------------- WEBHOOK ----------------
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        if token == VERIFY_TOKEN:
            return challenge
        return "Error", 403

    if not verificar_firma(request):
        return jsonify({'error': 'Firma inválida'}), 403

    return recibir_mensajes(request)

# ---------------- PROCESAMIENTO ----------------
def recibir_mensajes(req):

    if req.content_length and req.content_length > 1024 * 1024:
        return jsonify({'error': 'Payload muy grande'}), 413

    data = req.get_json(silent=True)

    if not data:
        return jsonify({'error': 'JSON no recibido'}), 400

    agregar_mensaje_log(json.dumps(data, indent=2))

    try:
        entry = data.get("entry", [])

        for e in entry:
            for change in e.get("changes", []):
                value = change.get("value", {})
                mensajes = value.get("messages", [])

                for msg in mensajes:
                    numero = msg.get("from")

                    if msg.get("type") == "text":
                        texto = msg["text"]["body"]

                        # 🧠 IA
                        respuesta = responder_con_ia(texto)

                        # 💰 Detectar compra
                        if detectar_compra(texto):
                            generar_pedido(numero)
                        else:
                            enviar_respuesta(numero, respuesta)

    except Exception as e:
        print("Error:", e)

    return jsonify({'message': 'EVENT_RECEIVED'}), 200

# ---------------- PANEL ----------------
@app.route('/')
def index():
    registros = Log.query.order_by(Log.fecha_y_hora.desc()).all()
    return render_template('index.html', registros=registros)

# ---------------- EXPORTAR ----------------
@app.route('/exportar')
def exportar():
    registros = Log.query.all()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID','Fecha','Texto'])

    for r in registros:
        cw.writerow([r.id, r.fecha_y_hora, r.texto])

    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)

    return send_file(output, mimetype='text/csv', as_attachment=True, download_name='logs.csv')

# ---------------- RUN ----------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))