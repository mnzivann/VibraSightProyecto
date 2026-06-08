"""
OBJETIVO: Gestion de Firebase, Orquestacion Asincrona y Control Remoto.
INTEGRANTES: Jorge Ivan Muñiz Samano, Hazziel Enrique Ramirez Vilches
PROYECTO: VibraSight
"""

# ==============================================================================
# PARCHE DE BAJO NIVEL: Forzar IPv4 para mitigar NameResolutionError en macOS
# ==============================================================================
import socket
origen_getaddrinfo = socket.getaddrinfo
def forzar_ipv4(*args, **kwargs):
    respuestas = origen_getaddrinfo(*args, **kwargs)
    return [r for r in respuestas if r[0] == socket.AF_INET]
socket.getaddrinfo = forzar_ipv4
# ==============================================================================

import json
import threading
import firebase_admin
from firebase_admin import credentials, firestore, messaging
import paho.mqtt.client as mqtt

# --- CONFIGURACION ---
cred = credentials.Certificate("credenciales-firebase.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

MQTT_BROKER = "broker.emqx.io"
TOPIC_SENSORES = "vibrasight/jorge_hazziel/sensores"
TOPIC_IA = "vibrasight/jorge_hazziel/ia"
TOPIC_COMANDO_CAMARA = "vibrasight/jorge_hazziel/comando"
TOPIC_COMANDO_ESP32 = "vibrasight/jorge_hazziel/comando_esp32" # <-- NUEVO CANAL

# ==============================================================================
# TAREAS EN SEGUNDO PLANO (Evitan que el sistema se congele si falla el WiFi)
# ==============================================================================
def tarea_firebase_notificacion(titulo, cuerpo):
    try:
        mensaje = messaging.Message(
            notification=messaging.Notification(title=titulo, body=cuerpo),
            topic="alertas_vibrasight"
        )
        messaging.send(mensaje)
        print("FCM: Notificacion Push enviada con exito.")
    except Exception as e:
        print(f"Error de red al enviar FCM (Ignorado para evitar lag): {e}")

def tarea_firebase_base_datos(coleccion, documento, datos, merge_flag=False):
    try:
        if documento:
            db.collection(coleccion).document(documento).set(datos, merge=merge_flag)
        else:
            db.collection(coleccion).add(datos)
        print(f"Firestore: Datos sincronizados en la coleccion '{coleccion}'.")
    except Exception as e:
        print(f"Error de red al guardar en base de datos: {e}")

def registrar_alerta_asincrona(tipo, descripcion):
    alerta = {
        "tipo": str(tipo),
        "descripcion": str(descripcion),
        "timestamp": firestore.SERVER_TIMESTAMP
    }
    threading.Thread(target=tarea_firebase_base_datos, args=("alertas", None, alerta)).start()

# ==============================================================================
# ESCUCHA DE COMANDOS DESDE LA APP (CONTROL BIDIRECCIONAL)
# ==============================================================================
def escuchar_comandos_app():
    """Se suscribe a Firebase para escuchar cuando el usuario presiona el boton en la App."""
    def on_snapshot(doc_snapshot, changes, read_time):
        for doc in doc_snapshot:
            if doc.exists and doc.to_dict().get("activar_zumbador") is True:
                print("⚡ ORDEN REMOTA: Activando zumbador desde la App...")
                # 1. Mandar orden al ESP32 por MQTT
                cliente_mqtt.publish(TOPIC_COMANDO_ESP32, json.dumps({"zumbador": True}))
                # 2. Apagar el switch en Firebase para que no se quede pegado
                db.collection("comandos").document("app").update({"activar_zumbador": False})
                
    # La suscripcion corre en su propio hilo automaticamente gracias a firebase-admin
    print("Suscrito a comandos remotos de la App.")
    db.collection("comandos").document("app").on_snapshot(on_snapshot)

# ==============================================================================
# PROCESAMIENTO PRINCIPAL MQTT
# ==============================================================================
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        
        if msg.topic == TOPIC_SENSORES:
            if payload.get("timbre_sonando") is True:
                print("Evento: Timbre presionado. Activando IA de camara al instante...")
                client.publish(TOPIC_COMANDO_CAMARA, json.dumps({"accion": "escanear"}))
                threading.Thread(target=tarea_firebase_base_datos, args=("sensores", "lecturas_actuales", payload, True)).start()
                threading.Thread(target=tarea_firebase_notificacion, args=("VibraSight", "Alguien esta tocando la puerta.")).start()
                registrar_alerta_asincrona("Timbre", "Pulsador activado fisicamente.")

        elif msg.topic == TOPIC_IA:
            if payload.get("presencia_ia") is True:
                print("Evento: IA detectó presencia. Subiendo datos y activando alarma...")

                # la IA confirme un rostro, el servidor de Python le mande por MQTT
                # la orden al ESP32 para que suene el zumbador (como un aviso de "acceso denegado" o "rostro detectado").
                client.publish(TOPIC_COMANDO_ESP32, json.dumps({"zumbador": True}))
                
                threading.Thread(target=tarea_firebase_base_datos, args=("sensores", "lecturas_actuales", payload, True)).start()
                threading.Thread(target=tarea_firebase_notificacion, args=("IA Identificacion", "Se confirma persona en la puerta.")).start()
                registrar_alerta_asincrona("IA Confirmada", "Rostro identificado tras toque de timbre.")
                
    except Exception as e:
        print(f"Error procesando mensaje MQTT: {e}")

# --- INICIO ---
print("Iniciando Servidor Puente Asincrono con Blindaje de Red...")
cliente_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
cliente_mqtt.on_connect = lambda c, u, f, r, p: c.subscribe([(TOPIC_SENSORES, 0), (TOPIC_IA, 0)])
cliente_mqtt.on_message = on_message
cliente_mqtt.connect(MQTT_BROKER, 1883, 60)

# Iniciamos la escucha de Firebase justo antes de bloquear el hilo con MQTT
escuchar_comandos_app()
cliente_mqtt.loop_forever()