# Módulo de Inteligencia Artificial y Orquestación IoT

Esta carpeta contiene el núcleo de procesamiento biométrico y conectividad del proyecto **VibraSight**. Está dividida en dos scripts principales que operan de manera asíncrona para garantizar la fluidez de la red y el ahorro de energía.

## Scripts Documentados

1. **`camara_server.py` (Motor de Visión Artificial):** Servidor Flask que intercepta el flujo de video en vivo (MJPEG). Contiene la lógica matemática para identificar rostros, encuadrar sujetos y transmitir fotogramas a la aplicación móvil. Implementa una arquitectura "Event-Driven", manteniéndose en modo de suspensión hasta recibir un trigger físico del ESP32.
2. **`servidor_puente.py` (Middleware IoT):** Orquestador bidireccional. Traduce las lecturas MQTT del microcontrolador hacia la base de datos NoSQL (Firestore) y transmite las órdenes manuales de la aplicación móvil (como la activación del zumbador o mensajes OLED) hacia el protocolo MQTT del hardware.

## Modelo Utilizado (Reconocimiento Facial)

Para la validación biométrica no se utilizó un simple clasificador Haar Cascade, sino una red neuronal profunda pre-entrenada, gestionada a través de la librería `face_recognition` (basada en el motor de C++ `dlib`).

* **Detección de Rostros (Localización):** Se utiliza el modelo **HOG (Histogram of Oriented Gradients)** combinado con un clasificador lineal (SVM) para encontrar la estructura de un rostro humano en el fotograma, logrando alta velocidad en CPUs estándar.
* **Extracción de Características y Validación:** Una vez localizado el rostro, el encuadre se pasa por una **Red Neuronal Convolucional (ResNet)** con 29 capas convolucionales. 
* **Vectores de 128 Dimensiones:** El modelo transforma las características físicas del rostro capturado en la puerta en un mapa vectorial de 128 medidas únicas. Posteriormente, calcula la distancia euclidiana entre este mapa y los rostros almacenados en la carpeta temporal (`rostros_registrados`), aplicando una tolerancia de `0.55` para emitir un veredicto de coincidencia.