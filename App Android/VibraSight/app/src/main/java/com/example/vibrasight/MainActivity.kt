/*
OBJETIVO: Dashboard Profesional con Pestañas, Bitacora, Registro Permanente y Control OLED/IP.
INTEGRANTES: Jorge Ivan Muñiz Samano, Hazziel Enrique Ramirez Vilches
PROYECTO: VibraSight
*/

package com.example.vibrasight

import android.content.Context
import android.graphics.Bitmap
import android.os.Bundle
import android.util.Base64
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.Query
import com.google.firebase.firestore.SetOptions
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.io.ByteArrayOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// ==============================================================================
// 1. MODELOS DE DATOS VIBRASIGHT
// ==============================================================================
data class SensorData(
    val luz_detectada: Boolean = false,
    val timbre_sonando: Boolean = false,
    val presencia_ia: Boolean = false,
    val temperatura: Double = 0.0,
    val humedad: Double = 0.0,
    val distancia: Double = 0.0,
    val nombre_persona: String = ""
)

data class Alerta(
    val tipo: String = "",
    val descripcion: String = "",
    val timestamp: Date? = null
)

data class Persona(
    val nombre: String = "",
    val token: String = ""
)

// ==============================================================================
// 2. VIEWMODEL
// ==============================================================================
class VibraSightViewModel : ViewModel() {
    private val db = FirebaseFirestore.getInstance()

    private val _sensores = MutableStateFlow(SensorData())
    val sensores: StateFlow<SensorData> = _sensores

    private val _alertas = MutableStateFlow<List<Alerta>>(emptyList())
    val alertas: StateFlow<List<Alerta>> = _alertas

    private val _personas = MutableStateFlow<List<Persona>>(emptyList())
    val personas: StateFlow<List<Persona>> = _personas

    private val _zumbadorActivo = MutableStateFlow(true)
    val zumbadorActivo: StateFlow<Boolean> = _zumbadorActivo

    init {
        escucharSensores()
        escucharAlertas()
        escucharPersonasRegistradas()
        escucharConfiguracion()
    }

    private fun escucharSensores() {
        db.collection("sensores").document("lecturas_actuales")
            .addSnapshotListener { snapshot, _ ->
                if (snapshot != null && snapshot.exists()) {
                    snapshot.toObject(SensorData::class.java)?.let { _sensores.value = it }
                }
            }
    }

    private fun escucharAlertas() {
        db.collection("alertas").orderBy("timestamp", Query.Direction.DESCENDING).limit(20)
            .addSnapshotListener { snapshot, _ ->
                if (snapshot != null) {
                    _alertas.value = snapshot.documents.mapNotNull { it.toObject(Alerta::class.java) }
                }
            }
    }

    private fun escucharPersonasRegistradas() {
        db.collection("personas_registradas")
            .addSnapshotListener { snapshot, _ ->
                if (snapshot != null) {
                    _personas.value = snapshot.documents.mapNotNull { it.toObject(Persona::class.java) }
                }
            }
    }

    private fun escucharConfiguracion() {
        db.collection("configuracion").document("sistema")
            .addSnapshotListener { snapshot, _ ->
                if (snapshot != null && snapshot.exists()) {
                    _zumbadorActivo.value = snapshot.getBoolean("zumbador_habilitado") ?: true
                }
            }
    }

    fun toggleZumbador(habilitado: Boolean) {
        db.collection("configuracion").document("sistema")
            .set(mapOf("zumbador_habilitado" to habilitado))
    }
}

// ==============================================================================
// 3. UTILIDADES DE IMAGEN (COMPRESION BASE64)
// ==============================================================================
fun procesarBitmapABase64(bitmap: Bitmap): String? {
    return try {
        val ratio = bitmap.height.toFloat() / bitmap.width.toFloat()
        val scaledBitmap = Bitmap.createScaledBitmap(bitmap, 500, (500 * ratio).toInt(), true)
        val outputStream = ByteArrayOutputStream()
        scaledBitmap.compress(Bitmap.CompressFormat.JPEG, 75, outputStream)
        Base64.encodeToString(outputStream.toByteArray(), Base64.DEFAULT)
    } catch (e: Exception) {
        null
    }
}

// ==============================================================================
// 4. ACTIVIDAD PRINCIPAL
// ==============================================================================
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        FirebaseMessaging.getInstance().subscribeToTopic("alertas_vibrasight")
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    VibraSightApp()
                }
            }
        }
    }
}

// ==============================================================================
// 5. INTERFAZ GRAFICA CON TABS Y CONTROL DINAMICO
// ==============================================================================
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VibraSightApp(viewModel: VibraSightViewModel = viewModel()) {
    val sensores by viewModel.sensores.collectAsState()
    val alertas by viewModel.alertas.collectAsState()
    val personas by viewModel.personas.collectAsState()
    val zumbadorActivo by viewModel.zumbadorActivo.collectAsState()

    val context = LocalContext.current

    // Configuración de Memoria Local para la IP
    val sharedPref = context.getSharedPreferences("VibraSightPrefs", Context.MODE_PRIVATE)
    var ipMac by remember { mutableStateOf(sharedPref.getString("ip_mac", "192.168.100.122") ?: "192.168.100.122") }

    var mostrarDialogoRegistro by remember { mutableStateOf(false) }
    var mostrarDialogoConfig by remember { mutableStateOf(false) }
    var tabIndex by remember { mutableStateOf(0) }
    val tabs = listOf("Monitor", "Bitácora", "Registros")

    val formatoFecha = SimpleDateFormat("dd/MM/yyyy HH:mm:ss", Locale.getDefault())

    Scaffold(
        topBar = {
            Column {
                TopAppBar(
                    title = {
                        Text(
                            text = if (sensores.luz_detectada) "¡Buenos días!" else "¡Buenas noches!",
                            fontWeight = FontWeight.Bold
                        )
                    },
                    actions = {
                        IconButton(onClick = { mostrarDialogoConfig = true }) {
                            Icon(imageVector = Icons.Filled.Settings, contentDescription = "Configuración IP")
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
                )
                TabRow(selectedTabIndex = tabIndex) {
                    tabs.forEachIndexed { index, title ->
                        Tab(
                            text = { Text(title) },
                            selected = tabIndex == index,
                            onClick = { tabIndex = index }
                        )
                    }
                }
            }
        },
        floatingActionButton = {
            if (tabIndex == 2) {
                FloatingActionButton(onClick = { mostrarDialogoRegistro = true }) {
                    Icon(imageVector = Icons.Filled.Add, contentDescription = "Registrar Persona")
                }
            }
        }
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp)) {

            // ==============================================================
            // TAB 0: MONITOR PRINCIPAL
            // ==============================================================
            if (tabIndex == 0) {
                Column(modifier = Modifier.fillMaxSize()) {
                    if (sensores.timbre_sonando) {
                        Card(modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primary)) {
                            Row(modifier = Modifier.padding(20.dp).fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                                Text("ALGUIEN TOCANDO EL TIMBRE", style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onPrimary)
                            }
                        }
                    }

                    if (sensores.presencia_ia && !sensores.timbre_sonando) {
                        val colorFondo = if (sensores.nombre_persona == "Desconocido") Color.Red else Color(0xFF27AE60)
                        Card(modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp), colors = CardDefaults.cardColors(containerColor = colorFondo)) {
                            Row(modifier = Modifier.padding(20.dp).fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                                Text("PRESENCIA: ${sensores.nombre_persona.uppercase()}", style = MaterialTheme.typography.titleLarge, color = Color.White)
                            }
                        }
                    }

                    LazyColumn(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                        // 1. REPRODUCTOR DE VIDEO REACTIVO A LA IP
                        item {
                            Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                                Column(modifier = Modifier.padding(12.dp)) {
                                    Text("Camara IA (Servidor Local)", style = MaterialTheme.typography.titleMedium)
                                    Spacer(modifier = Modifier.height(8.dp))
                                    AndroidView(
                                        modifier = Modifier.fillMaxWidth().height(200.dp),
                                        factory = { ctx ->
                                            WebView(ctx).apply {
                                                webViewClient = WebViewClient()
                                                settings.javaScriptEnabled = true
                                                settings.loadWithOverviewMode = true
                                                settings.useWideViewPort = true
                                                settings.cacheMode = android.webkit.WebSettings.LOAD_NO_CACHE
                                                settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
                                            }
                                        },
                                        // Update se llama automáticamente si ipMac cambia
                                        update = { webView ->
                                            val urlVideo = "http://${ipMac}:5050/video?rand=${System.currentTimeMillis()}"
                                            val htmlData = """
                                                <html>
                                                <body style="margin:0;padding:0;background-color:#1e1e1e;display:flex;justify-content:center;align-items:center;">
                                                    <img src="$urlVideo" width="100%" height="100%" style="object-fit:contain;"/>
                                                </body>
                                                </html>
                                            """.trimIndent()
                                            webView.loadDataWithBaseURL("http://$ipMac:5050", htmlData, "text/html", "UTF-8", null)
                                        }
                                    )
                                }
                            }
                        }

                        // 2. ESTADO DEL SISTEMA
                        item {
                            Card(modifier = Modifier.fillMaxWidth()) {
                                Column(modifier = Modifier.padding(16.dp)) {
                                    Text("Estado del Sistema", style = MaterialTheme.typography.titleMedium)
                                    Spacer(modifier = Modifier.height(8.dp))
                                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text("Temp / Humedad:"); Text("${sensores.temperatura} C | ${sensores.humedad}%") }
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text("Distancia (Radar):"); Text("${sensores.distancia} cm") }
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text("Identidad IA:"); Text(if (sensores.presencia_ia) sensores.nombre_persona else "Despejado") }
                                }
                            }
                        }

                        // 3. CONTROL DE PANTALLA OLED
                        item {
                            var mensajeOled by remember { mutableStateOf("") }
                            Card(modifier = Modifier.fillMaxWidth()) {
                                Column(modifier = Modifier.padding(16.dp)) {
                                    Text("Intercomunicador (Pantalla OLED)", style = MaterialTheme.typography.titleMedium)
                                    Text("Escribe un mensaje para mostrar en la puerta", style = MaterialTheme.typography.bodySmall, color = Color.Gray)
                                    Spacer(modifier = Modifier.height(8.dp))
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        OutlinedTextField(
                                            value = mensajeOled,
                                            onValueChange = { mensajeOled = it },
                                            modifier = Modifier.weight(1f),
                                            label = { Text("Mensaje...") },
                                            singleLine = true
                                        )
                                        Spacer(modifier = Modifier.width(8.dp))
                                        IconButton(
                                            onClick = {
                                                if (mensajeOled.isNotBlank()) {
                                                    // Guardar con merge para no borrar otros comandos (como el zumbador)
                                                    FirebaseFirestore.getInstance().collection("comandos").document("app")
                                                        .set(mapOf("mensaje_oled" to mensajeOled.trim()), SetOptions.merge())
                                                    Toast.makeText(context, "Mensaje enviado a la OLED", Toast.LENGTH_SHORT).show()
                                                    mensajeOled = ""
                                                }
                                            },
                                            colors = IconButtonDefaults.iconButtonColors(containerColor = MaterialTheme.colorScheme.primary)
                                        ) {
                                            Icon(imageVector = Icons.Filled.Send, contentDescription = "Enviar a OLED", tint = MaterialTheme.colorScheme.onPrimary)
                                        }
                                    }
                                }
                            }
                        }

                        // 4. CONTROL DE ZUMBADOR
                        item {
                            Card(modifier = Modifier.fillMaxWidth()) {
                                Row(
                                    modifier = Modifier.padding(16.dp).fillMaxWidth(),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Column {
                                        Text("Zumbador Automático", style = MaterialTheme.typography.titleMedium)
                                        Text("Sonar al detectar timbre/desconocidos", style = MaterialTheme.typography.bodySmall)
                                    }
                                    Switch(
                                        checked = zumbadorActivo,
                                        onCheckedChange = { viewModel.toggleZumbador(it) }
                                    )
                                }
                            }
                        }
                    }
                }
            }

            // ==============================================================
            // TAB 1: BITÁCORA DE TIMBRE
            // ==============================================================
            if (tabIndex == 1) {
                LazyColumn(modifier = Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    val bitacoraTimbre = alertas.filter { it.tipo.contains("Timbre") || it.tipo.contains("Escaneo Facial") }

                    if (bitacoraTimbre.isEmpty()) {
                        item { Text("No hay registros recientes.", modifier = Modifier.padding(16.dp)) }
                    }

                    items(bitacoraTimbre) { alerta ->
                        Card(modifier = Modifier.fillMaxWidth()) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Text(alerta.descripcion, style = MaterialTheme.typography.titleMedium)
                                Spacer(modifier = Modifier.height(4.dp))
                                val fechaStr = alerta.timestamp?.let { formatoFecha.format(it) } ?: "Hora desconocida"
                                Text("Fecha: $fechaStr", style = MaterialTheme.typography.bodySmall, color = Color.Gray)
                            }
                        }
                    }
                }
            }

            // ==============================================================
            // TAB 2: PERSONAS REGISTRADAS
            // ==============================================================
            if (tabIndex == 2) {
                LazyColumn(modifier = Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    if (personas.isEmpty()) {
                        item { Text("No hay personas registradas en el sistema.", modifier = Modifier.padding(16.dp)) }
                    }

                    items(personas) { persona ->
                        Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                            Row(modifier = Modifier.padding(16.dp).fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text(persona.nombre.uppercase(), style = MaterialTheme.typography.titleMedium)
                                Text("ID: ${persona.token}", style = MaterialTheme.typography.labelSmall)
                            }
                        }
                    }
                }
            }
        }

        // ==============================================================================
        // DIALOGO DE CONFIGURACION (IP)
        // ==============================================================================
        if (mostrarDialogoConfig) {
            var tempIp by remember { mutableStateOf(ipMac) }

            AlertDialog(
                onDismissRequest = { mostrarDialogoConfig = false },
                title = { Text("Configuración de Red") },
                text = {
                    Column {
                        Text("Ingresa la dirección IP local de la computadora (Mac) que ejecuta el servidor de cámara Python.", style = MaterialTheme.typography.bodySmall)
                        Spacer(modifier = Modifier.height(10.dp))
                        OutlinedTextField(
                            value = tempIp,
                            onValueChange = { tempIp = it },
                            label = { Text("Dirección IPv4") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                },
                confirmButton = {
                    Button(onClick = {
                        if (tempIp.isNotBlank()) {
                            ipMac = tempIp.trim()
                            sharedPref.edit().putString("ip_mac", ipMac).apply()
                            Toast.makeText(context, "IP Actualizada", Toast.LENGTH_SHORT).show()
                            mostrarDialogoConfig = false
                        }
                    }) { Text("Guardar IP") }
                },
                dismissButton = {
                    TextButton(onClick = { mostrarDialogoConfig = false }) { Text("Cancelar") }
                }
            )
        }

        // ==============================================================================
        // DIALOGO DE REGISTRO BIOMETRICO
        // ==============================================================================
        if (mostrarDialogoRegistro) {
            var nombre by remember { mutableStateOf("") }
            var imageBitmap by remember { mutableStateOf<Bitmap?>(null) }

            val cameraLauncher = rememberLauncherForActivityResult(
                contract = ActivityResultContracts.TakePicturePreview()
            ) { bitmap: Bitmap? -> imageBitmap = bitmap }

            AlertDialog(
                onDismissRequest = { mostrarDialogoRegistro = false },
                title = { Text("Registrar Rostro") },
                text = {
                    Column(modifier = Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                        OutlinedTextField(
                            value = nombre,
                            onValueChange = { nombre = it },
                            label = { Text("Nombre de la Persona") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(16.dp))

                        Button(
                            onClick = { cameraLauncher.launch(null) },
                            modifier = Modifier.fillMaxWidth(),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (imageBitmap == null) MaterialTheme.colorScheme.primary else Color(0xFF27AE60)
                            )
                        ) {
                            Icon(imageVector = Icons.Filled.CameraAlt, contentDescription = "Camara")
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(if (imageBitmap == null) "Capturar Foto" else "Foto Guardada ✓")
                        }
                    }
                },
                confirmButton = {
                    Button(onClick = {
                        if (nombre.isNotBlank() && imageBitmap != null) {
                            val db = FirebaseFirestore.getInstance()
                            val tokenBase = "Token" + (1000..9999).random()
                            val base64Img = procesarBitmapABase64(imageBitmap!!)

                            if (base64Img != null) {
                                val registroIA = hashMapOf("nombre" to nombre.trim(), "token" to tokenBase, "imagen_base64" to base64Img)
                                db.collection("registro_biometrico").add(registroIA)
                                Toast.makeText(context, "Enviando rostro al servidor IA...", Toast.LENGTH_SHORT).show()
                                mostrarDialogoRegistro = false
                            }
                        } else {
                            Toast.makeText(context, "Ingresa un nombre y toma una foto", Toast.LENGTH_SHORT).show()
                        }
                    }) { Text("Guardar") }
                },
                dismissButton = {
                    TextButton(onClick = { mostrarDialogoRegistro = false }) { Text("Cancelar") }
                }
            )
        }
    }
    
}