"""
OBJETIVO: Capa de Abstraccion de Hardware (HAL) - Modulo de lectura de sensores (LDR, Ultrasonico, DHT11, Timbre).
INTEGRANTES: Jorge Ivan Muñiz Samano, Hazziel Enrique Ramirez Vilches
PROYECTO: VibraSight
"""

import machine
import time
import dht

# --- ASIGNACION DE PINES (SENSORES) ---
ENTRADA_LDR = 34
ENTRADA_BOTON = 12
PIN_DHT = 15
PIN_TRIG = 14
PIN_ECHO = 27

# --- INICIALIZACION ---
sensor_foto = machine.ADC(machine.Pin(ENTRADA_LDR))
sensor_foto.atten(machine.ADC.ATTN_11DB)
sensor_foto.width(machine.ADC.WIDTH_12BIT)

btn_timbre = machine.Pin(ENTRADA_BOTON, machine.Pin.IN)
sensor_ambiental = dht.DHT11(machine.Pin(PIN_DHT))

trig = machine.Pin(PIN_TRIG, machine.Pin.OUT)
echo = machine.Pin(PIN_ECHO, machine.Pin.IN)
trig.value(0)

# --- FUNCIONES DE LECTURA (HAL) ---
def boton_presionado():
    """Devuelve True si el timbre físico está presionado."""
    return bool(btn_timbre.value())

def nivel_luz():
    """Devuelve el valor crudo del ADC para la fotorresistencia."""
    return sensor_foto.read()

def medir_distancia():
    """Calcula la distancia en cm usando el ultrasónico."""
    trig.value(0)
    time.sleep_us(5)
    trig.value(1)
    time.sleep_us(10)
    trig.value(0)
    
    duracion_us = machine.time_pulse_us(echo, 1, 30000)
    if duracion_us > 0:
        return round((duracion_us / 2) / 29.1, 2)
    return -1.0 

def medir_ambiente():
    """Devuelve una tupla (temperatura, humedad)."""
    try:
        sensor_ambiental.measure()
        return sensor_ambiental.temperature(), sensor_ambiental.humidity()
    except Exception:
        return None, None