// 1. Importar SDK de Firebase
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.1/firebase-app.js";
import { getFirestore, doc, onSnapshot, collection, query, orderBy, limit, setDoc, addDoc } 
    from "https://www.gstatic.com/firebasejs/10.8.1/firebase-firestore.js";

// ==========================================
// SISTEMA DE NOTIFICACIONES WEB NATIVAS
// ==========================================
let notificacionesActivas = false;

// Pedir permiso al navegador al cargar la página
if ("Notification" in window) {
    Notification.requestPermission().then(permission => {
        if (permission === "granted") {
            notificacionesActivas = true;
            console.log("Notificaciones web habilitadas.");
        }
    });
}

function lanzarNotificacion(titulo, cuerpo) {
    if (notificacionesActivas) {
        new Notification(titulo, {
            body: cuerpo,
            icon: "https://cdn-icons-png.flaticon.com/512/1157/1157000.png" 
        });
    }
}

// Variables de memoria para no hacer spam de notificaciones
let memoriaTimbre = false;
let memoriaIA = "";
// ==========================================

// 🚨 CONFIGURACIÓN DE FIREBASE 🚨
const firebaseConfig = {
    apiKey: "AIzaSyBtYefc7frbVjoQbO-l4hHXZ4b4eASETn8",
    authDomain: "sistemasprog-d434f.firebaseapp.com",
    projectId: "sistemasprog-d434f",
    storageBucket: "sistemasprog-d434f.firebasestorage.app",
    messagingSenderId: "197432860991",
    appId: "1:197432860991:web:c67aba077163a070efb38a"
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

// 2. Control de Pestañas
window.switchTab = function(tabId) {
    document.querySelectorAll('.content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    
    // Necesitamos pasar el evento manualmente o seleccionarlo de otra forma porque estamos en un módulo
    if(event) {
        event.currentTarget.classList.add('active');
    } else {
        // Fallback si event no está disponible
        document.querySelector(`.tab[onclick="switchTab('${tabId}')"]`).classList.add('active');
    }
    
    // Mostrar u ocultar el botón flotante (FAB)
    document.getElementById('btnNuevoRegistro').style.display = (tabId === 'registros') ? 'flex' : 'none';
}

// 3. Configuración de IP Local para el Video
let ipMac = localStorage.getItem("ip_mac") || "192.168.100.122";
const cargarVideo = () => {
    document.getElementById("videoFeed").src = `http://${ipMac}:5050/video?rand=${new Date().getTime()}`;
};
cargarVideo();

window.configurarIP = function() {
    let nuevaIP = prompt("Ingresa la dirección IP de tu Mac:", ipMac);
    if (nuevaIP) {
        ipMac = nuevaIP.trim();
        localStorage.setItem("ip_mac", ipMac);
        cargarVideo();
        alert("IP Actualizada");
    }
}

// 4. Escuchar Sensores (Monitor)
onSnapshot(doc(db, "sensores", "lecturas_actuales"), (docSnap) => {
    if (docSnap.exists()) {
        const data = docSnap.data();
        
        // Saludo
        document.getElementById("saludo").innerText = data.luz_detectada ? "¡Buenos días!" : "¡Buenas noches!";
        
        // Estado del Sistema
        document.getElementById("val-temp").innerText = `${data.temperatura} C | ${data.humedad}%`;
        document.getElementById("val-dist").innerText = `${data.distancia} cm`;
        document.getElementById("val-ia").innerText = data.presencia_ia ? data.nombre_persona : "Despejado";

        // Alertas Visuales (Timbre y Presencia)
        const bannerTimbre = document.getElementById("alertaTimbre");
        const bannerPresencia = document.getElementById("alertaPresencia");
        
        bannerTimbre.style.display = data.timbre_sonando ? "block" : "none";
        
        if (data.presencia_ia && !data.timbre_sonando) {
            bannerPresencia.style.display = "block";
            document.getElementById("nombrePresencia").innerText = data.nombre_persona.toUpperCase();
            bannerPresencia.style.backgroundColor = (data.nombre_persona === "Desconocido") ? "var(--error)" : "var(--success)";
        } else {
            bannerPresencia.style.display = "none";
        }

        // --- LÓGICA DE NOTIFICACIONES PUSH WEB ---
        // 1. Detectar Timbre
        if (data.timbre_sonando && !memoriaTimbre) {
            lanzarNotificacion("¡Ding Dong!", "Alguien está tocando la puerta principal.");
        }
        memoriaTimbre = data.timbre_sonando;

        // 2. Detectar Rostros (Conocidos / Desconocidos)
        if (data.presencia_ia) {
            if (data.nombre_persona !== memoriaIA) {
                if (data.nombre_persona === "Desconocido") {
                    lanzarNotificacion("ALERTA DE SEGURIDAD", "Se ha detectado un rostro no reconocido en la puerta.");
                } else {
                    lanzarNotificacion("Acceso Reconocido", `${data.nombre_persona.toUpperCase()} está en la puerta.`);
                }
            }
        }
        memoriaIA = data.presencia_ia ? data.nombre_persona : "";
    }
});

// 5. Intercomunicador OLED
document.getElementById("btnOled").addEventListener("click", () => {
    const mensaje = document.getElementById("inputOled").value;
    if (mensaje.trim() !== "") {
        setDoc(doc(db, "comandos", "app"), { mensaje_oled: mensaje.trim() }, { merge: true });
        document.getElementById("inputOled").value = "";
        alert("Mensaje enviado a la OLED");
    }
});

// 6. Zumbador y Radar Automático
const checkZumbador = document.getElementById("checkZumbador");
const checkRadar = document.getElementById("checkRadar");

onSnapshot(doc(db, "configuracion", "sistema"), (docSnap) => {
    if (docSnap.exists()) {
        const data = docSnap.data();
        checkZumbador.checked = data.zumbador_habilitado !== false;
        checkRadar.checked = data.radar_habilitado !== false;
    }
});

checkZumbador.addEventListener("change", (e) => {
    setDoc(doc(db, "configuracion", "sistema"), { zumbador_habilitado: e.target.checked }, { merge: true });
});

checkRadar.addEventListener("change", (e) => {
    const activado = e.target.checked;
    setDoc(doc(db, "configuracion", "sistema"), { radar_habilitado: activado }, { merge: true });
    setDoc(doc(db, "comandos", "app"), { radar_movimiento: activado }, { merge: true });
});

// 7. Bitácora de Alertas
const qAlertas = query(collection(db, "alertas"), orderBy("timestamp", "desc"), limit(20));
onSnapshot(qAlertas, (snapshot) => {
    const contenedor = document.getElementById("listaAlertas");
    contenedor.innerHTML = "";
    snapshot.forEach((docSnap) => {
        const alerta = docSnap.data();
        if(alerta.tipo.includes("Timbre") || alerta.tipo.includes("Escaneo Facial")) {
            const fecha = alerta.timestamp ? alerta.timestamp.toDate().toLocaleString() : "Hora desconocida";
            contenedor.innerHTML += `
                <div class="card">
                    <div class="card-title">${alerta.descripcion}</div>
                    <div style="font-size: 0.8rem; color: gray;">Fecha: ${fecha}</div>
                </div>
            `;
        }
    });
});

// 8. Registros (Personas Autorizadas)
onSnapshot(collection(db, "personas_registradas"), (snapshot) => {
    const contenedor = document.getElementById("listaPersonas");
    contenedor.innerHTML = "";
    snapshot.forEach((docSnap) => {
        const persona = docSnap.data();
        contenedor.innerHTML += `
            <div class="card row-between" style="background-color: #e3f2fd;">
                <div class="card-title" style="margin:0;">${persona.nombre.toUpperCase()}</div>
                <div style="font-size: 0.8rem; color: gray;">ID: ${persona.token}</div>
            </div>
        `;
    });
});

// 9. Registrar Nuevo Rostro (Convertir a Base64)
document.getElementById("btnNuevoRegistro").addEventListener("click", () => {
    document.getElementById("dialogoRegistro").style.display = "block";
});

document.getElementById("btnGuardarRostro").addEventListener("click", () => {
    const nombre = document.getElementById("nuevoNombre").value;
    const inputFoto = document.getElementById("nuevaFoto");

    if (nombre && inputFoto.files.length > 0) {
        const archivo = inputFoto.files[0];
        const reader = new FileReader();

        reader.onloadend = function () {
            const base64String = reader.result.split(',')[1];
            const tokenBase = "Token" + Math.floor(1000 + Math.random() * 9000);

            addDoc(collection(db, "registro_biometrico"), {
                nombre: nombre.trim(),
                token: tokenBase,
                imagen_base64: base64String
            }).then(() => {
                alert("Enviando rostro al servidor IA...");
                document.getElementById("dialogoRegistro").style.display = "none";
                document.getElementById("nuevoNombre").value = "";
                inputFoto.value = "";
            });
        };
        reader.readAsDataURL(archivo);
    } else {
        alert("Por favor ingresa un nombre y captura una foto.");
    }
});