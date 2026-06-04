"""
OBJETIVO: Camara Reactiva con Activacion por Evento (Timbre) - MQTT Optimizado.
PROYECTO: VibraSight
"""

import cv2
import time
import json
import threading
import urllib.request
import numpy as np
import paho.mqtt.client as mqtt
from flask import Flask, Response

app = Flask(__name__)

# --- CONFIGURACION ---
MQTT_BROKER = "broker.emqx.io"
TOPIC_IA = "vibrasight/jorge_hazziel/ia"
TOPIC_COMANDO = "vibrasight/jorge_hazziel/comando"
URL_CAMARA = "http://192.168.100.124:8080/shot.jpg"

frame_procesado = None
lock_memoria = threading.Lock()

# Variables de control
ia_activada = False
tiempo_limite_ia = 0
persona_detectada_actualmente = False

# ==============================================================================
# CLIENTE MQTT UNIFICADO (Nivel Principal para no perder comandos)
# ==============================================================================
cliente_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def on_connect(client, userdata, flags, reason_code, properties=None):
    if not reason_code.is_failure:
        print("MQTT: Camara conectada al broker. Escuchando ordenes del puente...")
        client.subscribe(TOPIC_COMANDO)

def on_message(client, userdata, msg):
    global ia_activada, tiempo_limite_ia
    try:
        if msg.topic == TOPIC_COMANDO:
            data = json.loads(msg.payload.decode('utf-8'))
            if data.get("accion") == "escanear":
                print("⚡ ORDEN RECIBIDA: Despertando Inteligencia Artificial por 20 segundos...")
                ia_activada = True
                tiempo_limite_ia = time.time() + 20
    except Exception as e:
        print("Error al procesar orden MQTT:", e)

cliente_mqtt.on_connect = on_connect
cliente_mqtt.on_message = on_message
cliente_mqtt.connect(MQTT_BROKER, 1883, 60)
# Iniciar MQTT de forma asíncrona robusta desde el arranque
cliente_mqtt.loop_start() 

# ==============================================================================
# MOTOR DE IA Y DESCARGA DE VIDEO
# ==============================================================================
def motor_de_ia():
    global frame_procesado, ia_activada, tiempo_limite_ia, persona_detectada_actualmente
    
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    ultimo_cambio = 0

    print("Motor de IA en espera (Modo Ahorro de Energia).")

    while True:
        try:
            req = urllib.request.urlopen(URL_CAMARA, timeout=2.0)
            arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
            frame = cv2.imdecode(arr, -1)
            if frame is None: continue
        except: 
            time.sleep(0.5)
            continue

        # Lógica de ventana de tiempo para la IA
        if ia_activada:
            if time.time() > tiempo_limite_ia:
                # Se acabó el tiempo (pasaron los 20s), apagar IA
                ia_activada = False
                print("IA entrando en modo ahorro de energia (Standby).")
                if persona_detectada_actualmente:
                    persona_detectada_actualmente = False
                    cliente_mqtt.publish(TOPIC_IA, json.dumps({"presencia_ia": False}))
            else:
                # Escanear rostros porque recibimos la orden del timbre
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = np.ascontiguousarray(gray)
                rostros = face_cascade.detectMultiScale(gray, 1.2, 5, minSize=(40, 40))
                
                estado_ia = len(rostros) > 0
                
                # Enviar estado de confirmación al servidor puente
                if estado_ia != persona_detectada_actualmente:
                    tiempo_actual = time.time()
                    if tiempo_actual - ultimo_cambio > 1.5:
                        persona_detectada_actualmente = estado_ia
                        ultimo_cambio = tiempo_actual
                        cliente_mqtt.publish(TOPIC_IA, json.dumps({"presencia_ia": persona_detectada_actualmente}))
                        print(f"Estado IA enviado al puente: {persona_detectada_actualmente}")
                
                # Dibujar los recuadros verdes
                for (x, y, w, h) in rostros:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    cv2.putText(frame, "HUMANO CONFIRMADO", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # Actualizar buffer web para que la App siempre tenga video
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
        if ret:
            with lock_memoria:
                frame_procesado = buffer.tobytes()
        
        time.sleep(0.04)

# ==============================================================================
# SERVIDOR FLASK
# ==============================================================================
def despachar():
    while True:
        with lock_memoria:
            if frame_procesado:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_procesado + b'\r\n')
        time.sleep(0.04)

@app.route('/video')
def video_feed():
    return Response(despachar(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    threading.Thread(target=motor_de_ia, daemon=True).start()
    print("Servidor web escuchando en el puerto 5050...")
    app.run(host='0.0.0.0', port=5050, threaded=False)