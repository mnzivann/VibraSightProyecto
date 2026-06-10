"""
OBJETIVO: Gestion de Firebase, Telemetria Ambiental, Distancia, Dashboard y OLED.
INTEGRANTES: Jorge Ivan Muñiz Samano, Hazziel Enrique Ramirez Vilches
PROYECTO: VibraSight
"""

import machine
import time
import json
import network
import dht
import ssd1306  # Libreria necesaria para la pantalla OLED
from umqtt.simple import MQTTClient

# --- CONFIGURACION DE MQTT ---
MQTT_BROKER = "broker.emqx.io"
CLIENT_ID = "ESP32_VibraSight_Final"
TOPIC_SENSORES = b"vibrasight/jorge_hazziel/sensores"
TOPIC_COMANDO_ESP32 = b"vibrasight/jorge_hazziel/comando_esp32"

# --- ASIGNACION DE PINES ---
ENTRADA_LDR = 34
SALIDA_RELE = 26
ENTRADA_BOTON = 12
PIN_ZUMBADOR = 13
PIN_DHT = 15
PIN_TRIG = 14       # HC-SR04 Disparador
PIN_ECHO = 27       # HC-SR04 Receptor
PIN_SCL = 22        # Pantalla OLED
PIN_SDA = 21        # Pantalla OLED

# --- CONFIGURACION DE LOGICA DEL FOCO ---
MODO_ACTIVO_BAJO = True 
PUNTO_ENCENDIDO = 2850
PUNTO_APAGADO = 2950

# --- INICIALIZACION DE HARDWARE ---
sensor_foto = machine.ADC(machine.Pin(ENTRADA_LDR))
sensor_foto.atten(machine.ADC.ATTN_11DB)
sensor_foto.width(machine.ADC.WIDTH_12BIT)

actuador_rele = machine.Pin(SALIDA_RELE, machine.Pin.OUT)
btn_timbre = machine.Pin(ENTRADA_BOTON, machine.Pin.IN)
zumbador = machine.Pin(PIN_ZUMBADOR, machine.Pin.OUT)
sensor_ambiental = dht.DHT11(machine.Pin(PIN_DHT))

# Inicializacion del Ultrasónico
trig = machine.Pin(PIN_TRIG, machine.Pin.OUT)
echo = machine.Pin(PIN_ECHO, machine.Pin.IN)
trig.value(0)

# Inicializacion de Pantalla OLED
pantalla_disponible = False
try:
    i2c = machine.SoftI2C(scl=machine.Pin(PIN_SCL), sda=machine.Pin(PIN_SDA))
    oled = ssd1306.SSD1306_I2C(128, 64, i2c)
    oled.fill(0)
    oled.text("VibraSight", 24, 20)
    oled.text("Sistema Listo", 12, 40)
    oled.show()
    pantalla_disponible = True
except Exception as e:
    print("No se detecto pantalla OLED o hay error de I2C:", e)

# Estados iniciales
zumbador.value(0)
foco_activo = False

# Variables globales ambientales
temperatura_actual = 0.0
humedad_actual = 0.0
distancia_actual = 0.0

def gestionar_rele(estado):
    if MODO_ACTIVO_BAJO:
        actuador_rele.value(0 if estado else 1)
    else:
        actuador_rele.value(1 if estado else 0)

def medir_distancia():
    """Emite un pulso ultrasonico y calcula la distancia en cm."""
    trig.value(0)
    time.sleep_us(5)
    
    trig.value(1)
    time.sleep_us(10)
    trig.value(0)
    
    duracion_us = machine.time_pulse_us(echo, 1, 30000)
    
    if duracion_us > 0:
        distancia_cm = (duracion_us / 2) / 29.1
        return round(distancia_cm, 2)
    else:
        return -1.0 

def mostrar_mensaje_oled(mensaje):
    """Muestra un mensaje en la OLED, haciendo saltos de linea si es muy largo."""
    if not pantalla_disponible: return
    
    oled.fill(0)
    oled.text("MENSAJE:", 0, 0)
    
    # Dividir el texto para que quepa en la pantalla (Max ~16 caracteres por linea)
    palabras = mensaje.split()
    lineas = []
    linea_actual = ""
    
    for palabra in palabras:
        if len(linea_actual) + len(palabra) + 1 <= 16:
            linea_actual += (palabra + " ")
        else:
            lineas.append(linea_actual)
            linea_actual = palabra + " "
    lineas.append(linea_actual)

    # Imprimir lineas en la pantallita (cada renglon baja 12 pixeles)
    y = 16
    for l in lineas[:4]: # Soporta maximo 4 renglones de mensaje
        oled.text(l.strip(), 0, y)
        y += 12
        
    oled.show()

# ==============================================================================
# GESTION DE CREDENCIALES Y CONEXION WI-FI
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
        print("Credenciales guardadas en la memoria del ESP32.")
    except Exception as e:
        print("Error al guardar credenciales:", e)



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
        print("Credenciales guardadas en la memoria del ESP32.")
    except Exception as e:
        print("Error al guardar credenciales:", e)

def conectar_wifi_interactivo():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    time.sleep(2) 
    if wlan.isconnected():
        wlan.disconnect()

    # 1. INTENTO DE CONEXIÓN AUTOMÁTICA
    credenciales = cargar_credenciales()
    if credenciales:
        ssid_guardado = credenciales.get('ssid')
        pass_guardado = credenciales.get('password')
        print(f"\nRed guardada detectada: '{ssid_guardado}'. Conectando automaticamente...")
        
        wlan.connect(ssid_guardado, pass_guardado)
        timeout = 15
        while not wlan.isconnected() and timeout > 0:
            print(".", end="")
            time.sleep(1)
            timeout -= 1
            
        if wlan.isconnected():
            print(f"\nConexion exitosa. IP: {wlan.ifconfig()[0]}")
            return # Termina la funcion y arranca el programa
        else:
            print("\nFallo la conexion automatica. El router puede estar apagado.")
            print("Iniciando escaneo manual de respaldo...")

    # 2. ESCANEO MANUAL (Solo se ejecuta si es la primera vez o falló la automática)
    print("\nEncendiendo radio Wi-Fi y escaneando redes cercanas...")
    time.sleep(1)
    redes_crudas = wlan.scan()
    redes_validas = []

    for red in redes_crudas:
        ssid = red[0].decode('utf-8')
        rssi = red[3]
        if len(ssid) > 0 and ssid not in [r['ssid'] for r in redes_validas]:
            redes_validas.append({'ssid': ssid, 'rssi': rssi})

    if not redes_validas:
        print("Error: No se detecto ninguna red 2.4GHz en el rango.")
        while True: pass

    print("\n--- REDES DISPONIBLES (2.4 GHz) ---")
    for i, red in enumerate(redes_validas):
        print(f"[{i + 1}] {red['ssid']} (Senal: {red['rssi']} dBm)")

    while not wlan.isconnected():
        try:
            seleccion = input("\nEscribe el numero de la red y presiona Enter: ")
            indice = int(seleccion) - 1
            if 0 <= indice < len(redes_validas):
                ssid_elegido = redes_validas[indice]['ssid']
                password = input(f"Ingresa la contrasena (deja en blanco si es red abierta): ")
                print(f"Negociando IP con {ssid_elegido}...")
                
                if password == "":
                    wlan.connect(ssid_elegido)
                else:
                    wlan.connect(ssid_elegido, password)
                    
                timeout = 20
                while not wlan.isconnected() and timeout > 0:
                    print(".", end="")
                    time.sleep(1)
                    timeout -= 1
                    
                if wlan.isconnected():
                    print(f"\nConexion exitosa. IP: {wlan.ifconfig()[0]}")
                    guardar_credenciales(ssid_elegido, password)
                    return
                else:
                    print("\nEl router rechazo la conexion. Intenta de nuevo.")
            else:
                print("Numero fuera de rango.")
        except ValueError:
            print("Entrada no valida.")
                  

# ==============================================================================
# RECEPCION DE COMANDOS REMOTOS
# ==============================================================================
def recibir_comando(topic, msg):
    try:
        datos = json.loads(msg.decode('utf-8'))
        
        if datos.get("zumbador") is True:
            print("Orden remota: Activando zumbador desde la App")
            zumbador.value(1)
            time.sleep(2)
            zumbador.value(0)
            
        if "mensaje_oled" in datos:
            texto = datos["mensaje_oled"]
            print("Orden remota: Mostrando mensaje en OLED ->", texto)
            mostrar_mensaje_oled(texto)
            
    except Exception as e:
        print("Error procesando comando remoto:", e)

# ==============================================================================
# EJECUCION PRINCIPAL
# ==============================================================================
gestionar_rele(False)
conectar_wifi_interactivo()

cliente = MQTTClient(CLIENT_ID, MQTT_BROKER)
cliente.set_callback(recibir_comando)
cliente.connect()
cliente.subscribe(TOPIC_COMANDO_ESP32)
print("Sistema en linea. Escuchando telemetria y comandos...")

estado_anterior_timbre = False
estado_anterior_luz = False
ultimo_envio_periodico = time.time()

while True:
    try:
        cliente.check_msg()

        # 1. Accion inmediata del timbre fisico
        timbre_presionado = bool(btn_timbre.value())
        if timbre_presionado:
            zumbador.value(1)
            # Limpiar la pantalla cuando tocan el timbre para que el mensaje anterior no se quede pegado
            if pantalla_disponible:
                oled.fill(0)
                oled.text("Tocando...", 25, 25)
                oled.show()
        else:
            zumbador.value(0)

        # 2. Control automatico de iluminacion (LDR)
        valor_crudo = sensor_foto.read()
        
        if not foco_activo and valor_crudo > PUNTO_APAGADO:
            gestionar_rele(True)
            foco_activo = True
            print("Oscuridad detectada")
        elif foco_activo and valor_crudo < PUNTO_ENCENDIDO:
            gestionar_rele(False)
            foco_activo = False
            print("Luz detectada")

        luz_detectada_status = not foco_activo

        # 3. Logica de transmision inteligente
        hubo_cambio = (timbre_presionado != estado_anterior_timbre) or (luz_detectada_status != estado_anterior_luz)
        tiempo_actual = time.time()
        
        if hubo_cambio or (tiempo_actual - ultimo_envio_periodico > 15):
            
            # Lecturas lentas (DHT11 y Ultrasónico) procesadas solo cada 15 segundos
            if (tiempo_actual - ultimo_envio_periodico > 15):
                try:
                    sensor_ambiental.measure()
                    temperatura_actual = sensor_ambiental.temperature()
                    humedad_actual = sensor_ambiental.humidity()
                except Exception:
                    pass
                
                # Medir distancia
                lectura_dist = medir_distancia()
                if lectura_dist != -1.0:
                    distancia_actual = lectura_dist
                    
                ultimo_envio_periodico = tiempo_actual
            
            telemetria = {
                "luz_detectada": luz_detectada_status,
                "timbre_sonando": timbre_presionado,
                "temperatura": temperatura_actual,
                "humedad": humedad_actual,
                "distancia": distancia_actual
            }
            
            cliente.publish(TOPIC_SENSORES, json.dumps(telemetria))
            print("Telemetria enviada:", json.dumps(telemetria))
            
            estado_anterior_timbre = timbre_presionado
            estado_anterior_luz = luz_detectada_status

        time.sleep_ms(50)

    except OSError:
        print("Error de comunicacion MQTT. Intentando reconectar...")
        try:
            cliente.connect()
            cliente.subscribe(TOPIC_COMANDO_ESP32)
        except:
            time.sleep(2)