"""
OBJETIVO: Gestion de Firebase, Orquestacion Asincrona, Telemetria Ambiental y Biometria.
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
import base64
import os
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
TOPIC_COMANDO_ESP32 = "vibrasight/jorge_hazziel/comando_esp32"

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
# ESCUCHA DE COMANDOS Y REGISTROS DESDE LA APP (CONTROL BIDIRECCIONAL)
# ==============================================================================
def escuchar_comandos_app():
    """Se suscribe a Firebase para escuchar cuando el usuario presiona el boton en la App."""
    def on_snapshot(doc_snapshot, changes, read_time):
        for doc in doc_snapshot:
            if doc.exists and doc.to_dict().get("activar_zumbador") is True:
                print("ORDEN REMOTA: Activando zumbador desde la App...")
                cliente_mqtt.publish(TOPIC_COMANDO_ESP32, json.dumps({"zumbador": True}))
                db.collection("comandos").document("app").update({"activar_zumbador": False})
                
    print("Suscrito a comandos remotos de la App.")
    db.collection("comandos").document("app").on_snapshot(on_snapshot)

def escuchar_registros_biometricos():
    """Vigila la coleccion 'registro_biometrico' para descargar nuevas fotos enviadas por la App."""
    def on_snapshot(doc_snapshot, changes, read_time):
        for change in changes:
            if change.type.name == 'ADDED':
                doc = change.document.to_dict()
                nombre = doc.get("nombre")
                token = doc.get("token")
                img_b64 = doc.get("imagen_base64")
                
                if nombre and token and img_b64:
                    print(f"Descargando nuevo rostro desde la App: {nombre}")
                    try:
                        # 1. Decodificar la imagen
                        img_data = base64.b64decode(img_b64)
                        
                        # 2. Asegurar que la carpeta existe
                        carpeta = "rostros_registrados"
                        if not os.path.exists(carpeta):
                            os.makedirs(carpeta)
                            
                        # 3. Guardar el archivo fisico
                        ruta_archivo = os.path.join(carpeta, f"{nombre}_{token}.jpg")
                        with open(ruta_archivo, "wb") as f:
                            f.write(img_data)
                            
                        print(f"Rostro guardado en: {ruta_archivo}")
                        
                        # 4. Ordenarle al servidor de camara que recargue la RAM
                        cliente_mqtt.publish(TOPIC_COMANDO_CAMARA, json.dumps({"accion": "recargar_biometria"}))
                        
                        # ====================================================================
                        # NUEVO: Guardar el registro permanente en Firestore para la pestaña de la App
                        # ====================================================================
                        db.collection("personas_registradas").add({
                            "nombre": nombre,
                            "token": token
                        })
                        print(f"Registro permanente creado en Firestore para {nombre}.")
                        
                        # 5. Borrar el documento de Firebase para no gastar almacenamiento
                        db.collection("registro_biometrico").document(change.document.id).delete()
                        
                    except Exception as e:
                        print(f"Error al guardar registro biometrico: {e}")

    print("Suscrito a registros biometricos remotos.")
    db.collection("registro_biometrico").on_snapshot(on_snapshot)
    
# ==============================================================================
# PROCESAMIENTO PRINCIPAL MQTT
# ==============================================================================
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        
        if msg.topic == TOPIC_SENSORES:
            distancia_actual = payload.get("distancia", "N/A")
            print(f"Telemetria recibida (Distancia: {distancia_actual} cm). Sincronizando con la nube...")
            
            threading.Thread(target=tarea_firebase_base_datos, args=("sensores", "lecturas_actuales", payload, True)).start()
            
            if payload.get("timbre_sonando") is True:
                print("Evento: Timbre presionado. Activando IA de camara al instante...")
                client.publish(TOPIC_COMANDO_CAMARA, json.dumps({"accion": "escanear"}))
                threading.Thread(target=tarea_firebase_notificacion, args=("VibraSight", "Alguien esta tocando la puerta.")).start()
                registrar_alerta_asincrona("Timbre", "Pulsador activado fisicamente.")

        elif msg.topic == TOPIC_IA:
            if payload.get("presencia_ia") is True:
                nombre = payload.get("nombre_persona", "Desconocido")
                print(f"Evento: IA identifico a {nombre}. Subiendo datos...")
                
                if nombre == "Desconocido":
                    client.publish(TOPIC_COMANDO_ESP32, json.dumps({"zumbador": True}))
                
                threading.Thread(target=tarea_firebase_base_datos, args=("sensores", "lecturas_actuales", payload, True)).start()
                
                titulo = "Alerta de Seguridad" if nombre == "Desconocido" else "Notificacion de Acceso"
                cuerpo = f"Se ha detectado a: {nombre} en la puerta."
                threading.Thread(target=tarea_firebase_notificacion, args=(titulo, cuerpo)).start()
                
                registrar_alerta_asincrona("Escaneo Facial", f"Rostro procesado: {nombre}")
                
    except Exception as e:
        print(f"Error procesando mensaje MQTT: {e}")

# --- INICIO ---
print("Iniciando Servidor Puente Asincrono con Blindaje de Red y Biometria...")
cliente_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
cliente_mqtt.on_connect = lambda c, u, f, r, p: c.subscribe([(TOPIC_SENSORES, 0), (TOPIC_IA, 0)])
cliente_mqtt.on_message = on_message
cliente_mqtt.connect(MQTT_BROKER, 1883, 60)

escuchar_comandos_app()
escuchar_registros_biometricos()
cliente_mqtt.loop_forever()