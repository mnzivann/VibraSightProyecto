"""
OBJETIVO: Gestion de Firebase, Dashboard, MQTT y Capa de Abstracción de Hardware.
INTEGRANTES: Jorge Ivan Muñiz Samano, Hazziel Enrique Ramirez Vilches
PROYECTO: VibraSight
"""

import time
import json
import network
from umqtt.simple import MQTTClient

# Importamos nuestros módulos encapsulados
import sensores
import actuadores

# --- CONFIGURACION DE MQTT ---
MQTT_BROKER = "broker.emqx.io"
CLIENT_ID = "ESP32_VibraSight_Final"
TOPIC_SENSORES = b"vibrasight/jorge_hazziel/sensores"
TOPIC_COMANDO_ESP32 = b"vibrasight/jorge_hazziel/comando_esp32"

PUNTO_ENCENDIDO = 2850
PUNTO_APAGADO = 2950

foco_activo = False
temperatura_actual = 0.0
humedad_actual = 0.0
distancia_actual = 0.0

# Variable global para el control del radar desde la web
radar_activo = True 

# ==============================================================================
# GESTION DE CREDENCIALES Y CONEXION WI-FI AUTOMATICA
# ==============================================================================
def cargar_credenciales():
    try:
        with open('wifi.json', 'r') as archivo:
            return json.load(archivo)
    except Exception:
        return None

def guardar_credenciales(ssid, password):
    try:
        with open('wifi.json', 'w') as archivo:
            json.dump({'ssid': ssid, 'password': password}, archivo)
    except Exception as e:
        pass

def conectar_wifi_interactivo():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    time.sleep(2) 
    if wlan.isconnected(): wlan.disconnect()

    credenciales = cargar_credenciales()
    if credenciales:
        print(f"\nConectando a red guardada: '{credenciales.get('ssid')}'...")
        wlan.connect(credenciales.get('ssid'), credenciales.get('password'))
        timeout = 15
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
        if wlan.isconnected():
            print(f"Conexion exitosa. IP: {wlan.ifconfig()[0]}")
            return 
            
    print("\nIniciando escaneo manual...")
    redes_crudas = wlan.scan()
    redes_validas = []
    for red in redes_crudas:
        ssid = red[0].decode('utf-8')
        if len(ssid) > 0 and ssid not in [r['ssid'] for r in redes_validas]:
            redes_validas.append({'ssid': ssid})

    for i, red in enumerate(redes_validas):
        print(f"[{i + 1}] {red['ssid']}")

    while not wlan.isconnected():
        try:
            indice = int(input("\nNumero de red: ")) - 1
            ssid_elegido = redes_validas[indice]['ssid']
            password = input(f"Contrasena para {ssid_elegido}: ")
            wlan.connect(ssid_elegido, password)
            time.sleep(5)
            if wlan.isconnected():
                guardar_credenciales(ssid_elegido, password)
                print(f"Conexion exitosa. IP: {wlan.ifconfig()[0]}")
                return
        except Exception:
            pass

# ==============================================================================
# RECEPCION DE COMANDOS REMOTOS
# ==============================================================================
def recibir_comando(topic, msg):
    global radar_activo # <-- CRÍTICO: Permite modificar la variable global
    try:
        datos = json.loads(msg.decode('utf-8'))
        
        if "identidad_ia" in datos:
            nombre = datos["identidad_ia"]
            if nombre == "Desconocido":
                actuadores.mostrar_mensaje_oled("ALERTA: INTRUSO")
                actuadores.melodia_desconocido()
            else:
                actuadores.mostrar_mensaje_oled(f"ACCESO: {nombre}")
                actuadores.melodia_conocido()
                
        elif datos.get("zumbador") is True:
            actuadores.melodia_desconocido()
            
        if "mensaje_oled" in datos:
            actuadores.mostrar_mensaje_oled(datos["mensaje_oled"])
            
        # NUEVA LÓGICA: Recibir orden del radar
        if "radar" in datos:
            radar_activo = datos["radar"]
            if radar_activo:
                actuadores.mostrar_mensaje_oled("Radar: ACTIVO")
                print(">> COMANDO RECIBIDO: Radar ENCENDIDO")
            else:
                actuadores.mostrar_mensaje_oled("Radar: APAGADO")
                print(">> COMANDO RECIBIDO: Radar APAGADO")
            
    except Exception as e:
        print("Error comando remoto:", e)

# ==============================================================================
# EJECUCION PRINCIPAL
# ==============================================================================
actuadores.gestionar_rele(False)
conectar_wifi_interactivo()

cliente = MQTTClient(CLIENT_ID, MQTT_BROKER)
cliente.set_callback(recibir_comando)
cliente.connect()
cliente.subscribe(TOPIC_COMANDO_ESP32)
print("Sistema en linea. Escuchando telemetria y comandos...")
actuadores.limpiar_pantalla("Sistema Listo", 12, 25)

estado_anterior_timbre = False
estado_anterior_luz = False
ultimo_envio_periodico = time.time()

# Variables de la máquina de estados del Radar
angulo_radar = 0
direccion_radar = 1  
paso_radar = 30      
tiempo_ultimo_radar = time.ticks_ms()

while True:
    try:
        cliente.check_msg()

        # 1. Accion del timbre
        timbre_presionado = sensores.boton_presionado()
        if timbre_presionado:
            actuadores.limpiar_pantalla("Tocando...", 25, 25)
            actuadores.melodia_timbre()
            time.sleep(0.3)

        # 2. Control de LDR
        valor_crudo = sensores.nivel_luz()
        if not foco_activo and valor_crudo > PUNTO_APAGADO:
            actuadores.gestionar_rele(True)
            foco_activo = True
        elif foco_activo and valor_crudo < PUNTO_ENCENDIDO:
            actuadores.gestionar_rele(False)
            foco_activo = False
        luz_detectada_status = not foco_activo

        # ====================================================
        # 2.5 RADAR ULTRASÓNICO (CON CONTROL MANUAL)
        # ====================================================
        # Solo escanea si el usuario no lo ha apagado desde la web
        if radar_activo:
            tiempo_actual_ms = time.ticks_ms()
            
            # Cada 5 segundos (5000 ms), el radar hace un barrido
            if time.ticks_diff(tiempo_actual_ms, tiempo_ultimo_radar) > 5000:
                
                # 1. Calcular hacia dónde va a mirar ahora
                angulo_radar += (paso_radar * direccion_radar)
                
                if angulo_radar >= 180:
                    angulo_radar = 180
                    direccion_radar = -1 
                elif angulo_radar <= 0:
                    angulo_radar = 0
                    direccion_radar = 1  
                    
                # 2. Mover físicamente el cuello (Servomotor) y relajar energía
                print(f"[RADAR] Apuntando a {angulo_radar} grados...")
                actuadores.mover_servo_radar(angulo_radar)
                
                # 3. Tomar la lectura
                dist = sensores.medir_distancia()
                if dist != -1.0:
                    distancia_actual = dist
                    print(f"[RADAR] Distancia en {angulo_radar}° -> {distancia_actual} cm")
                    
                    if distancia_actual < 100.0:
                        print(f"[ALERTA] ¡Objeto detectado a {distancia_actual} cm en el ángulo {angulo_radar}°!")
                
                tiempo_ultimo_radar = time.ticks_ms()
        # ====================================================

        # 3. Logica de Transmision MQTT
        hubo_cambio = (timbre_presionado != estado_anterior_timbre) or (luz_detectada_status != estado_anterior_luz)
        tiempo_actual = time.time()
        
        if hubo_cambio or (tiempo_actual - ultimo_envio_periodico > 15):
            
            if (tiempo_actual - ultimo_envio_periodico > 15):
                temp, hum = sensores.medir_ambiente()
                if temp is not None:
                    temperatura_actual, humedad_actual = temp, hum
                
                ultimo_envio_periodico = tiempo_actual
            
            telemetria = {
                "luz_detectada": luz_detectada_status,
                "timbre_sonando": timbre_presionado,
                "temperatura": temperatura_actual,
                "humedad": humedad_actual,
                "distancia": distancia_actual
            }
            
            cliente.publish(TOPIC_SENSORES, json.dumps(telemetria))
            print("Telemetria:", json.dumps(telemetria))
            
            estado_anterior_timbre = timbre_presionado
            estado_anterior_luz = luz_detectada_status

        time.sleep_ms(50)

    except OSError:
        print("Reconectando MQTT...")
        try:
            cliente.connect()
            cliente.subscribe(TOPIC_COMANDO_ESP32)
        except:
            time.sleep(2)