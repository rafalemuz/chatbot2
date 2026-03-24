from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
import csv
import io
 
app = Flask(__name__)
 
# Configuración de la base de datos SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///metapython.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
 
# Modelo de la tabla log
class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha_y_hora = db.Column(db.DateTime, default=datetime.utcnow)
    texto = db.Column(db.Text)
 
# Crear la tabla si no existe
with app.app_context():
    db.create_all()
 
# TOKEN de verificación
TOKEN_CHATCOURSE = "VALCODE"
 
# ----------------- FUNCIONES DE LOG -----------------
def agregar_mensaje_log(texto):
    try:
        nuevo_registro = Log(texto=texto)
        db.session.add(nuevo_registro)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print("Error guardando log:", e)
 
def limpiar_logs():
    try:
        num = Log.query.delete()
        db.session.commit()
        return num
    except Exception as e:
        db.session.rollback()
        return 0
 
# ----------------- RUTAS -----------------
@app.route('/')
def index():
    keyword = request.args.get('keyword', '').strip()
    if keyword:
        registros = Log.query.filter(Log.texto.contains(keyword)).order_by(Log.fecha_y_hora.desc()).all()
    else:
        registros = Log.query.order_by(Log.fecha_y_hora.desc()).all()
    return render_template('index.html', registros=registros, keyword=keyword)
 
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return verificar_token(request)
    if request.method == 'POST':
        return recibir_mensajes(request)
 
def verificar_token(req):
    token = req.args.get('hub.verify_token')
    challenge = req.args.get('hub.challenge')
    if challenge and token == TOKEN_CHATCOURSE:
        return challenge
    else:
        return jsonify({'error': 'Token inválido'}), 401
 
def recibir_mensajes(req):
    data = req.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON no recibido'}), 400
    texto = json.dumps(data, indent=2)
    agregar_mensaje_log(texto)
    return jsonify({'message': 'EVENT_RECEIVED'}), 200
 
@app.route('/limpiar')
def limpiar():
    num = limpiar_logs()
    return redirect(url_for('index'))
 
@app.route('/exportar')
def exportar():
    registros = Log.query.order_by(Log.fecha_y_hora.asc()).all()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID','Fecha','Texto'])
    for r in registros:
        cw.writerow([r.id, r.fecha_y_hora, r.texto])
    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    return send_file(output, mimetype='text/csv', as_attachment=True, attachment_filename='logs.csv')
 
# ----------------- MAIN -----------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)