# VibraSight: Sistema Multimodal de Acceso Inteligente

**Objetivo:** Gestion de Firebase, Orquestacion Asincrona, Telemetria Ambiental, Biometria y Capa de Abstraccion de Hardware (HAL).
**Integrantes:** Jorge Ivan Muñiz Samano, Hazziel Enrique Ramirez Vilches
**Proyecto:** VibraSight

---

## Descripcion del Proyecto
VibraSight es un ecosistema IoT de seguridad perimetral. Integra telemetria ambiental, vigilancia por radar ultrasonico y reconocimiento facial impulsado por Inteligencia Artificial (Edge Computing). El sistema se comunica de manera bidireccional (Full-Duplex) mediante MQTT y Firebase Firestore, permitiendo monitoreo y control en tiempo real desde un Dashboard Web reactivo.

## Estructura del Repositorio
El proyecto esta dividido estricta y modularmente en tres subsistemas principales:

- `/HAL`: Codigo MicroPython para el microcontrolador ESP32. Contiene la logica de abstraccion para sensores y actuadores.
- `/Servidor`: Scripts en Python para la orquestacion de red, el puente MQTT-Firebase y el motor de Inteligencia Artificial local.
- `/Interfaz`: Frontend web (HTML/CSS/JS) para el centro de control y visualizacion de telemetria en tiempo real.

## Requisitos Previos
- Python 3.9 o superior.
- Thonny IDE (o esptool) para transferir archivos al ESP32.
- Cuenta de Firebase con Firestore activado y credenciales descargadas.
- Broker MQTT publico (broker.emqx.io).

## Instalacion y Despliegue

### 1. Configuracion del Servidor y Motor de IA
Navega a la carpeta del servidor e instala todas las dependencias necesarias de Python:
```bash
cd Servidor
pip install -r requirements.txt

Nota: Asegurate de colocar el archivo `credenciales-firebase.json` dentro de esta carpeta antes de ejecutar el servidor.

### 2. Despliegue de la Capa Fisica (ESP32)
1. Conecta el ESP32 a la computadora.
2. Utiliza Thonny para subir el contenido de la carpeta `/HAL` al microcontrolador.
3. Configura las credenciales de red editando el archivo `wifi.json` para conectar la placa a la misma red local que el servidor principal.

### 3. Ejecucion del Sistema
Para inicializar el ecosistema completo, levanta los servicios en el siguiente orden desde la raiz del proyecto:

**Terminal 1 (Motor de IA y Streaming de Video):**
```bash
cd Servidor
python camara_server.py

**Terminal 2 (Puente Asincrono MQTT - Firebase):**
```bash
cd Servidor
python servidor_puente.py

**Terminal 3 (Dashboard Web):** Para evitar bloqueos de CORS y permitir el acceso desde dispositivos moviles en la misma red, levanta un servidor HTTP local:
```bash
cd Interfaz
python -m http.server 8000
```
Finalmente, abre tu navegador web y dirigete a http://localhost:8000 (o utiliza la direccion IP local de la maquina host para acceder desde tu dispositivo movil).