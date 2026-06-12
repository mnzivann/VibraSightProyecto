"""
OBJETIVO: Capa de Abstraccion de Hardware (HAL) - Modulo de control de actuadores (OLED, Servo, Buzzer, Rele).
INTEGRANTES: Jorge Ivan Muñiz Samano, Hazziel Enrique Ramirez Vilches
PROYECTO: VibraSight
"""

import machine
import time
import ssd1306

# --- ASIGNACION DE PINES (ACTUADORES) ---
SALIDA_RELE = 26
PIN_ZUMBADOR = 13
PIN_SCL = 22
PIN_SDA = 21
PIN_SERVO = 4  # <--- NUEVO PIN PARA EL SERVO

MODO_ACTIVO_BAJO = True 

# --- INICIALIZACION ---
actuador_rele = machine.Pin(SALIDA_RELE, machine.Pin.OUT)
zumbador = machine.PWM(machine.Pin(PIN_ZUMBADOR))
zumbador.duty(0)

# Inicialización del Servomotor (Frecuencia obligatoria de 50Hz)
servo = machine.PWM(machine.Pin(PIN_SERVO), freq=50)

pantalla_disponible = False
try:
    i2c = machine.SoftI2C(scl=machine.Pin(PIN_SCL), sda=machine.Pin(PIN_SDA))
    oled = ssd1306.SSD1306_I2C(128, 64, i2c)
    oled.fill(0)
    oled.text("VibraSight", 24, 20)
    oled.text("Cargando...", 24, 40)
    oled.show()
    pantalla_disponible = True
except Exception as e:
    print("No se detecto pantalla OLED:", e)

# --- FUNCIONES DE CONTROL (HAL) ---
def gestionar_rele(estado):
    """Enciende o apaga el foco respetando la lógica del relevador."""
    if MODO_ACTIVO_BAJO:
        actuador_rele.value(0 if estado else 1)
    else:
        actuador_rele.value(1 if estado else 0)

def mostrar_mensaje_oled(mensaje):
    """Formatea y ajusta el texto para que quepa en la pantalla."""
    if not pantalla_disponible: return
    oled.fill(0)
    oled.text("MENSAJE:", 0, 0)
    
    palabras = mensaje.split()
    lineas, linea_actual = [], ""
    for palabra in palabras:
        if len(linea_actual) + len(palabra) + 1 <= 16:
            linea_actual += (palabra + " ")
        else:
            lineas.append(linea_actual)
            linea_actual = palabra + " "
    lineas.append(linea_actual)

    y = 16
    for l in lineas[:4]: 
        oled.text(l.strip(), 0, y)
        y += 12
    oled.show()

def limpiar_pantalla(texto="", x=0, y=0):
    """Limpia la pantalla y opcionalmente pone un texto centrado."""
    if pantalla_disponible:
        oled.fill(0)
        if texto:
            oled.text(texto, x, y)
        oled.show()

# --- CONTROL DE MOTORES (HAL) ---
def mover_servo_radar(angulo):
    """Mueve el radar a una posición y corta la energía para evitar que el ESP32 se reinicie (Anti-Brownout)"""
    if angulo < 0: angulo = 0
    if angulo > 180: angulo = 180
    
    # 1. Mandamos el pulso para girar
    ciclo_trabajo = int(25 + (angulo / 180.0) * 100)
    servo.duty(ciclo_trabajo)
    
    # 2. Le damos tiempo para que físicamente llegue a esa posición
    time.sleep_ms(400) 
    
    # 3. TRUCO DE ENERGÍA: Apagamos el pulso de PWM. El motor se relaja
    # y deja de consumir corriente, salvando al ESP32 del apagón.
    servo.duty(0)

# --- MOTOR DE AUDIO (MELODIAS) ---
def tocar_notas(melodia):
    for frecuencia, duracion in melodia:
        if frecuencia == 0:
            zumbador.duty(0)
        else:
            zumbador.freq(frecuencia)
            zumbador.duty(512)
        time.sleep(duracion)
    zumbador.duty(0)

def melodia_timbre():
    print("Sonando: TIMBRE")
    tocar_notas([(2637, 0.12), (3135, 0.12), (4186, 0.25), (0, 0.08), (3135, 0.12), (4186, 0.40)])

def melodia_conocido():
    print("Sonando: ACCESO CONCEDIDO")
    tocar_notas([(2093, 0.10), (2637, 0.10), (3136, 0.10), (4186, 0.30)])

def melodia_desconocido():
    print("Sonando: ALARMA INTRUSO")
    tocar_notas([(4186, 0.15), (2960, 0.15), (4186, 0.15), (2960, 0.15), (4186, 0.15), (2960, 0.15)])