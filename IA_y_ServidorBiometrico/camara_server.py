"""
OBJETIVO: Camara Reactiva con Validacion Biometrica y Control de Acceso.
INTEGRANTES: Jorge Ivan Muñiz Samano, Hazziel Enrique Ramirez Vilches
PROYECTO: VibraSight
"""

import os
import cv2
import time
import json
import threading
import urllib.request
import numpy as np
import paho.mqtt.client as mqtt
from flask import Flask, Response
import face_recognition

app = Flask(__name__)

# --- CONFIGURACION DE RED ---
MQTT_BROKER = "broker.emqx.io"
TOPIC_IA = "vibrasight/jorge_hazziel/ia"
TOPIC_COMANDO = "vibrasight/jorge_hazziel/comando"
URL_CAMARA = "http://10.156.0.17:8080/video"

# --- MEMORIA COMPARTIDA ---
frame_procesado = None
lock_memoria = threading.Lock()

# --- VARIABLES DE CONTROL IA ---
ia_activada = False
tiempo_limite_ia = 0
persona_detectada_actualmente = False
nombre_detectado_actualmente = ""

# --- CONFIGURACION BIOMETRICA ---
CARPETA_ROSTROS = "rostros_registrados"
rostros_conocidos_encodings = []
rostros_conocidos_nombres = []

def cargar_base_datos_biometrica():
    """Carga las imagenes locales, extrae el mapa vectorial y el token/nombre."""
    global rostros_conocidos_encodings, rostros_conocidos_nombres
    
    # Limpiar RAM por si es una recarga en vivo
    rostros_conocidos_encodings.clear()
    rostros_conocidos_nombres.clear()
    
    print("Cargando base de datos de rostros biometricos en memoria RAM...")
    
    if not os.path.exists(CARPETA_ROSTROS):
        os.makedirs(CARPETA_ROSTROS)
        print(f"ADVERTENCIA: Se creo la carpeta '{CARPETA_ROSTROS}'.")
        return

    archivos = os.listdir(CARPETA_ROSTROS)
    if not archivos:
        print(f"ADVERTENCIA: La carpeta '{CARPETA_ROSTROS}' esta vacia. Todos seran detectados como Desconocido.")
        
    for archivo in archivos:
        if archivo.lower().endswith((".jpg", ".jpeg", ".png")):
            ruta = os.path.join(CARPETA_ROSTROS, archivo)
            try:
                imagen_carga = face_recognition.load_image_file(ruta)
                encodings = face_recognition.face_encodings(imagen_carga)
                
                if len(encodings) > 0:
                    nombre_extraido = archivo.split('_')[0]
                    rostros_conocidos_encodings.append(encodings[0])
                    rostros_conocidos_nombres.append(nombre_extraido)
                    print(f"Rostro registrado exitosamente: {nombre_extraido} (Archivo: {archivo})")
                else:
                    print(f"Error: No se detecto un rostro claro en el archivo {archivo}.")
            except Exception as e:
                print(f"Error al cargar la imagen {archivo}: {e}")
                
    print(f"Total de identidades validadas: {len(rostros_conocidos_nombres)}")

# ==============================================================================
# CLIENTE MQTT UNIFICADO
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
                print("ORDEN RECIBIDA: Despertando Inteligencia Artificial por 20 segundos...")
                ia_activada = True
                tiempo_limite_ia = time.time() + 20
                
            elif data.get("accion") == "recargar_biometria":
                print("ORDEN RECIBIDA: Nuevo rostro detectado, recargando base de datos en RAM...")
                cargar_base_datos_biometrica()
                
    except Exception as e:
        print("Error al procesar orden MQTT:", e)

cliente_mqtt.on_connect = on_connect
cliente_mqtt.on_message = on_message
cliente_mqtt.connect(MQTT_BROKER, 1883, 60)
cliente_mqtt.loop_start() 

# ==============================================================================
# MOTOR DE IA Y DESCARGA DE VIDEO
# ==============================================================================
def motor_de_ia():
    global frame_procesado, ia_activada, tiempo_limite_ia
    global persona_detectada_actualmente, nombre_detectado_actualmente
    
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

        if ia_activada:
            if time.time() > tiempo_limite_ia:
                ia_activada = False
                print("IA entrando en modo ahorro de energia (Standby).")
                if persona_detectada_actualmente:
                    persona_detectada_actualmente = False
                    nombre_detectado_actualmente = ""
                    cliente_mqtt.publish(TOPIC_IA, json.dumps({"presencia_ia": False, "nombre_persona": ""}))
            else:
                small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
                rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                
                face_locations = face_recognition.face_locations(rgb_small_frame)
                face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
                
                estado_ia = len(face_locations) > 0
                nombre_en_cuadro = "Desconocido"

                for face_encoding, face_location in zip(face_encodings, face_locations):
                    matches = face_recognition.compare_faces(rostros_conocidos_encodings, face_encoding, tolerance=0.55)
                    nombre_asignado = "Desconocido"

                    if True in matches:
                        face_distances = face_recognition.face_distance(rostros_conocidos_encodings, face_encoding)
                        best_match_index = np.argmin(face_distances)
                        if matches[best_match_index]:
                            nombre_asignado = rostros_conocidos_nombres[best_match_index]
                    
                    nombre_en_cuadro = nombre_asignado

                    top, right, bottom, left = face_location
                    top *= 4
                    right *= 4
                    bottom *= 4
                    left *= 4

                    color_caja = (0, 0, 255) if nombre_asignado == "Desconocido" else (0, 255, 0)
                    cv2.rectangle(frame, (left, top), (right, bottom), color_caja, 2)
                    cv2.putText(frame, nombre_asignado.upper(), (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color_caja, 2)

                if (estado_ia != persona_detectada_actualmente) or (estado_ia and nombre_en_cuadro != nombre_detectado_actualmente):
                    tiempo_actual = time.time()
                    if tiempo_actual - ultimo_cambio > 2.0:
                        persona_detectada_actualmente = estado_ia
                        nombre_detectado_actualmente = nombre_en_cuadro
                        ultimo_cambio = tiempo_actual
                        
                        payload = {
                            "presencia_ia": persona_detectada_actualmente,
                            "nombre_persona": nombre_detectado_actualmente
                        }
                        cliente_mqtt.publish(TOPIC_IA, json.dumps(payload))
                        print(f"Identidad evaluada enviada al puente: {nombre_detectado_actualmente}")

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
    cargar_base_datos_biometrica()
    threading.Thread(target=motor_de_ia, daemon=True).start()
    print("Servidor web escuchando en el puerto 5050...")
    app.run(host='0.0.0.0', port=5050, threaded=True)