"""
OBJETIVO: Prueba Estática de Pipeline Extremo a Extremo (IA + MQTT + Actuador Físico)
INTEGRANTES: Jorge Ivan Muñiz Samano, Hazziel Enrique Ramirez Vilches
PROYECTO: VibraSight
"""
import numpy as np  
import cv2
import face_recognition
import os
import time
import json
import threading
import paho.mqtt.client as mqtt

# --- CONFIGURACION DE RED MQTT ---
MQTT_BROKER = "broker.emqx.io"
TOPIC_SENSORES = "vibrasight/jorge_hazziel/sensores"
TOPIC_COMANDO_ESP32 = "vibrasight/jorge_hazziel/comando_esp32"

# --- VARIABLES DE CONTROL ---
ia_activada = False
tiempo_limite_ia = 0
bloqueo_zumbador = 0  # Evita saturar al ESP32 con miles de mensajes por segundo

# --- CONFIGURACION BIOMETRICA ---
CARPETA_ROSTROS = "rostros_registrados"
rostros_conocidos_encodings = []
rostros_conocidos_nombres = []

def cargar_base_datos_biometrica():
    global rostros_conocidos_encodings, rostros_conocidos_nombres
    print("Cargando rostros conocidos en memoria RAM...")
    if not os.path.exists(CARPETA_ROSTROS):
        os.makedirs(CARPETA_ROSTROS)
        return
    for archivo in os.listdir(CARPETA_ROSTROS):
        if archivo.lower().endswith((".jpg", ".jpeg", ".png")):
            ruta = os.path.join(CARPETA_ROSTROS, archivo)
            try:
                imagen_carga = face_recognition.load_image_file(ruta)
                encodings = face_recognition.face_encodings(imagen_carga)
                if len(encodings) > 0:
                    nombre_extraido = archivo.split('_')[0]
                    rostros_conocidos_encodings.append(encodings[0])
                    rostros_conocidos_nombres.append(nombre_extraido)
                    print(f"-> Rostro cargado: {nombre_extraido}")
            except Exception as e:
                print(f"Error al cargar {archivo}: {e}")

# ==============================================================================
# CLIENTE MQTT (ESCUCHA DEL TIMBRE FISICO)
# ==============================================================================
def on_connect(client, userdata, flags, reason_code, properties=None):
    print("\n[MQTT] Conectado exitosamente al broker.")
    print(f"[MQTT] Escuchando el timbre en el topico: {TOPIC_SENSORES}")
    client.subscribe(TOPIC_SENSORES)

def on_message(client, userdata, msg):
    global ia_activada, tiempo_limite_ia
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        # Detectamos si el ESP32 avisa que el timbre físico se presionó
        if payload.get("timbre_sonando") is True:
            print("\n[ALERTA] ¡Se ha pulsado el timbre fisico en la protoboard!")
            print("[IA] Despertando reconocimiento facial por 20 segundos...")
            ia_activada = True
            tiempo_limite_ia = time.time() + 20
    except Exception as e:
        print("Error al procesar mensaje MQTT:", e)

# Iniciar cliente MQTT en segundo plano
cliente_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
cliente_mqtt.on_connect = on_connect
cliente_mqtt.on_message = on_message
cliente_mqtt.connect(MQTT_BROKER, 1883, 60)
cliente_mqtt.loop_start()

# ==============================================================================
# EJECUCION DEL MOTOR VISUAL PRINCIPAL
# ==============================================================================
cargar_base_datos_biometrica()
camara = cv2.VideoCapture(0) # Abre la webcam de la Mac

if not camara.isOpened():
    print("Error: No se puede abrir la webcam de la Mac.")
    exit()

print("\n--- PIPELINE LISTO ---")
print("Presiona el botón físico en tu ESP32 para iniciar la demostración.")
print("Presiona la tecla 'q' en la ventana de video para cerrar el programa.")

while True:
    ret, frame = camara.read()
    if not ret: break

    # Si la IA está activa (porque tocaron el timbre) empezamos a procesar
    if ia_activada:
        if time.time() > tiempo_limite_ia:
            ia_activada = False
            print("\n[IA] Tiempo límite agotado. Entrando en modo ahorro de energia (Standby).")
        else:
            # Optimizar fotograma (Reducción a una cuarta parte)
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

            for face_location, face_encoding in zip(face_locations, face_encodings):
                matches = face_recognition.compare_faces(rostros_conocidos_encodings, face_encoding, tolerance=0.55)
                nombre_asignado = "Desconocido"
                color_caja = (0, 0, 255) # Rojo para peligro / desconocido

                if True in matches:
                    best_match_index = np.argmin(face_recognition.face_distance(rostros_conocidos_encodings, face_encoding))
                    if matches[best_match_index]:
                        nombre_asignado = rostros_conocidos_nombres[best_match_index]
                        color_caja = (0, 255, 0) # Verde para acceso seguro

                # ==========================================================
                # DISPARO DEL ACTUADOR FISICO (PIPELINE EXTREMO A EXTREMO)
                # ==========================================================

                if nombre_asignado == "Desconocido" and time.time() > bloqueo_zumbador:
                    print("¡IA detecto un DESCONOCIDO! Disparando comando al zumbador fisico...")
                    # Mandamos la orden directa al ESP32 por MQTT
                    cliente_mqtt.publish(TOPIC_COMANDO_ESP32, json.dumps({"zumbador": True}))
                    bloqueo_zumbador = time.time() + 3 # Bloqueo de 3 segundos para no saturar al ESP32

                # Dibujar recuadro en la ventana local de la Mac
                top, right, bottom, left = face_location
                top *= 4; right *= 4; bottom *= 4; left *= 4
                cv2.rectangle(frame, (left, top), (right, bottom), color_caja, 2)
                cv2.putText(frame, nombre_asignado.upper(), (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color_caja, 2)

    # Mostrar el estado en la pantalla de la Mac
    texto_estado = "IA ACCIONADA: ESCANEANDO" if ia_activada else "IA EN ESPERA"
    color_texto = (0, 255, 0) if ia_activada else (0, 165, 255)
    cv2.putText(frame, texto_estado, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_texto, 2)

    cv2.imshow("VibraSight", frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

camara.release()
cv2.destroyAllWindows()
cliente_mqtt.loop_stop()