"""
OBJETIVO: Gestion de Firebase y Dashboard de usuario.
INTEGRANTES: Jorge Ivan Muñiz Samano, Hazziel Enrique Ramirez Vilches
PROYECTO: VibraSight
"""

import machine
import time
import json
import network
from umqtt.simple import MQTTClient

# --- CONFIGURACION DE MQTT ---
MQTT_BROKER = "broker.emqx.io"
CLIENT_ID = "ESP32_VibraSight_Final"
TOPIC_SENSORES = b"vibrasight/jorge_hazziel/sensores"
TOPIC_COMANDO_ESP32 = b"vibrasight/jorge_hazziel/comando_esp32" # Nuevo canal para recibir ordenes de la App

# --- ASIGNACION DE PINES ---
ENTRADA_LDR = 34
SALIDA_RELE = 26
ENTRADA_BOTON = 12  # Pulsador con resistencia Pull-Down
PIN_ZUMBADOR = 13   # Zumbador activo

# --- CONFIGURACION DE LOGICA DEL FOCO ---
MODO_ACTIVO_BAJO = True 
PUNTO_ENCENDIDO = 1600
PUNTO_APAGADO = 2200

# --- INICIALIZACION DE HARDWARE ---
sensor_foto = machine.ADC(machine.Pin(ENTRADA_LDR))
sensor_foto.atten(machine.ADC.ATTN_11DB)
sensor_foto.width(machine.ADC.WIDTH_12BIT)

actuador_rele = machine.Pin(SALIDA_RELE, machine.Pin.OUT)
btn_timbre = machine.Pin(ENTRADA_BOTON, machine.Pin.IN)
zumbador = machine.Pin(PIN_ZUMBADOR, machine.Pin.OUT)

# Estados iniciales
zumbador.value(0)
foco_activo = False

def gestionar_rele(estado):
    if MODO_ACTIVO_BAJO:
        actuador_rele.value(0 if estado else 1)
    else:
        actuador_rele.value(1 if estado else 0)

def obtener_lectura_limpia(n=5):
    val = 0
    for _ in range(n):
        val += sensor_foto.read()
        time.sleep_ms(5)
    return val // n

# ==============================================================================
# GESTION DE CREDENCIALES Y CONEXION WI-FI
# ==============================================================================
def cargar_credenciales():
    """Intenta leer el archivo local con las credenciales guardadas."""
    try:
        with open('wifi.json', 'r') as archivo:
            return json.load(archivo)
    except Exception:
        return None

def guardar_credenciales(ssid, password):
    """Guarda las credenciales exitosas en la memoria flash."""
    try:
        with open('wifi.json', 'w') as archivo:
            json.dump({'ssid': ssid, 'password': password}, archivo)
        print("Credenciales guardadas en la memoria del ESP32.")
    except Exception as e:
        print("Error al guardar credenciales:", e)

def conectar_wifi_interactivo():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    # Pausa de seguridad para que la antena del ESP32 se energice correctamente
    time.sleep(2) 
    
    if wlan.isconnected():
        wlan.disconnect()

    # 1. Verificacion de memoria flash con opcion a omitir
    credenciales = cargar_credenciales()
    if credenciales:
        ssid_guardado = credenciales.get('ssid')
        pass_guardado = credenciales.get('password')
        print(f"\nRed guardada detectada en memoria: '{ssid_guardado}'")
        
        opcion = input("Deseas conectar a esta red? (s/n): ").strip().lower()
        
        if opcion == 's' or opcion == 'si':
            print(f"Intentando conectar a: '{ssid_guardado}'...")
            wlan.connect(ssid_guardado, pass_guardado)
            timeout = 15
            while not wlan.isconnected() and timeout > 0:
                print(".", end="")
                time.sleep(1)
                timeout -= 1
                
            if wlan.isconnected():
                print(f"\nConexion automatica exitosa. IP: {wlan.ifconfig()[0]}")
                return
            else:
                print("\nFallo la conexion a la red guardada. Iniciando escaneo manual...")
        else:
            print("Omitiendo red guardada. Iniciando escaneo manual...")

    # 2. Escaneo manual interactivo
    print("\nEncendiendo radio Wi-Fi y escaneando redes cercanas...")
    time.sleep(1) # Segunda pausa de seguridad antes del escaneo
    
    redes_crudas = wlan.scan()
    redes_validas = []

    for red in redes_crudas:
        ssid = red[0].decode('utf-8')
        rssi = red[3]
        # Solo agregamos redes que tengan un nombre visible (evita redes ocultas vacias)
        if len(ssid) > 0 and ssid not in [r['ssid'] for r in redes_validas]:
            redes_validas.append({'ssid': ssid, 'rssi': rssi})

    if not redes_validas:
        print("Error: No se detecto ninguna red 2.4GHz en el rango. Revisa la antena o acerca el router.")
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
                print(f"Has seleccionado: '{ssid_elegido}'")
                
                password = input(f"Ingresa la contrasena (deja en blanco si es red abierta): ")
                print(f"Negociando IP con {ssid_elegido}... (Espera hasta 20 segundos)")
                
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
                    print("\nEl router rechazo la conexion (Contrasena incorrecta o router lejos). Intenta de nuevo.")
            else:
                print("Numero fuera de rango.")
        except ValueError:
            print("Entrada no valida.")

# ==============================================================================
# RECEPCION DE COMANDOS REMOTOS (NUEVO)
# ==============================================================================
def recibir_comando(topic, msg):
    """Callback que se ejecuta cuando el puente de Python manda una orden al ESP32."""
    try:
        datos = json.loads(msg.decode('utf-8'))
        if datos.get("zumbador") is True:
            print("Orden remota: Activando zumbador desde la App (Firebase -> Python -> MQTT)")
            zumbador.value(1)
            time.sleep(2) # El zumbador suena por 2 segundos a modo de alarma
            zumbador.value(0)
    except Exception as e:
        print("Error procesando comando remoto:", e)

# ==============================================================================
# EJECUCION PRINCIPAL
# ==============================================================================
gestionar_rele(False)

conectar_wifi_interactivo()

cliente = MQTTClient(CLIENT_ID, MQTT_BROKER)
cliente.set_callback(recibir_comando) # Configuramos la funcion de escucha antes de conectar
cliente.connect()
cliente.subscribe(TOPIC_COMANDO_ESP32) # Nos suscribimos al canal de comandos
print("Sistema unificado de VibraSight en linea. Escuchando telemetria y comandos...")

# Variables para control de estados (Edge Detection) y evitar saturacion MQTT
estado_anterior_timbre = False
estado_anterior_luz = False
ultimo_envio_periodico = time.time()

while True:
    try:
        # 0. Revisar si hay mensajes entrantes desde la nube (Control Remoto)
        cliente.check_msg()

        # 1. Accion inmediata del timbre fisico
        timbre_presionado = bool(btn_timbre.value())
        if timbre_presionado:
            zumbador.value(1)
        else:
            zumbador.value(0)

        # 2. Control automatico de iluminacion (LDR)
        nivel_luz = obtener_lectura_limpia(5)
        
        if not foco_activo and nivel_luz > PUNTO_APAGADO:
            gestionar_rele(True)
            foco_activo = True
            print("Oscuridad detectada -> Foco ON | Valor:", nivel_luz)
        elif foco_activo and nivel_luz < PUNTO_ENCENDIDO:
            gestionar_rele(False)
            foco_activo = False
            print("Luz detectada -> Foco OFF | Valor:", nivel_luz)

        luz_detectada_status = not foco_activo

        # 3. Logica de transmision inteligente (Envio por evento o tiempo limite)
        hubo_cambio = (timbre_presionado != estado_anterior_timbre) or (luz_detectada_status != estado_anterior_luz)
        tiempo_actual = time.time()
        
        if hubo_cambio or (tiempo_actual - ultimo_envio_periodico > 15):
            telemetria = {
                "luz_detectada": luz_detectada_status,
                "timbre_sonando": timbre_presionado
            }
            
            cliente.publish(TOPIC_SENSORES, json.dumps(telemetria))
            
            estado_anterior_timbre = timbre_presionado
            estado_anterior_luz = luz_detectada_status
            ultimo_envio_periodico = tiempo_actual

        # Ciclo rapido de lectura (50ms)
        time.sleep_ms(50)

    except OSError:
        print("Error de comunicacion MQTT. Intentando reconectar...")
        try:
            cliente.connect()
            cliente.subscribe(TOPIC_COMANDO_ESP32) # Es importante volver a suscribirse si se cae la conexion
        except:
            time.sleep(2)