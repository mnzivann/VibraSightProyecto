/*
OBJETIVO: Dashboard Estable con Control Bidireccional.
INTEGRANTES: Jorge Ivan Muñiz Samano, Hazziel Enrique Ramirez Vilches
PROYECTO: VibraSight
*/

package com.example.vibrasight

import android.os.Bundle
import android.util.Log
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.Query
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

// ==============================================================================
// 1. MODELOS DE DATOS VIBRASIGHT
// ==============================================================================
data class SensorData(
    val luz_detectada: Boolean = false,
    val timbre_sonando: Boolean = false,
    val presencia_ia: Boolean = false
)

data class Alerta(
    val tipo: String = "",
    val descripcion: String = ""
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

    init {
        escucharSensores()
        escucharAlertas()
    }

    private fun escucharSensores() {
        db.collection("sensores").document("lecturas_actuales")
            .addSnapshotListener { snapshot, _ ->
                if (snapshot != null && snapshot.exists()) {
                    snapshot.toObject(SensorData::class.java)?.let {
                        _sensores.value = it
                    }
                }
            }
    }

    private fun escucharAlertas() {
        db.collection("alertas")
            .orderBy("timestamp", Query.Direction.DESCENDING)
            .limit(5)
            .addSnapshotListener { snapshot, _ ->
                if (snapshot != null) {
                    _alertas.value = snapshot.documents.mapNotNull { it.toObject(Alerta::class.java) }
                }
            }
    }
}

// ==============================================================================
// 3. ACTIVIDAD PRINCIPAL
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
// 4. INTERFAZ GRÁFICA OPTIMIZADA
// ==============================================================================
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VibraSightApp(viewModel: VibraSightViewModel = viewModel()) {
    val sensores by viewModel.sensores.collectAsState()
    val alertas by viewModel.alertas.collectAsState()
    val context = LocalContext.current

    val reproductorVideo = remember {
        WebView(context).apply {
            webViewClient = WebViewClient()
            settings.javaScriptEnabled = true
            settings.loadWithOverviewMode = true
            settings.useWideViewPort = true
            settings.cacheMode = android.webkit.WebSettings.LOAD_NO_CACHE
            loadUrl("http://192.168.213.140:5050/video")
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("VibraSight Dashboard") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                    titleContentColor = MaterialTheme.colorScheme.primary
                )
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
        ) {

            // --- SECCIÓN DE BANNERS DINÁMICOS (FUERA DE LA LISTA SCROLLABLE) ---
            if (sensores.timbre_sonando) {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primary)
                ) {
                    Row(modifier = Modifier.padding(20.dp).fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                        Text("ALGUIEN TOCANDO EL TIMBRE", style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onPrimary)
                    }
                }
            }

            if (sensores.presencia_ia && !sensores.timbre_sonando) {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 16.dp),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFE67E22))
                ) {
                    Row(modifier = Modifier.padding(20.dp).fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                        Text("IA DETECTA PRESENCIA", style = MaterialTheme.typography.titleLarge, color = Color.White)
                    }
                }
            }

            // --- SECCIÓN DE CONTENIDO FIJO CON SCROLL ---
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {

                // 1. REPRODUCCIÓN DE VIDEO LOCAL
                item {
                    Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            Text("Camara IA (Servidor Local)", style = MaterialTheme.typography.titleMedium)
                            Spacer(modifier = Modifier.height(8.dp))

                            AndroidView(
                                factory = { reproductorVideo },
                                modifier = Modifier.fillMaxWidth().height(200.dp)
                            )
                        }
                    }
                }

                // 2. MONITOREO DE SENSORES HARDWARE
                item {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text("Estado del Sistema", style = MaterialTheme.typography.titleMedium)
                            Spacer(modifier = Modifier.height(8.dp))
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("Luz Ambiental:")
                                Text(text = if (sensores.luz_detectada) "Dia" else "Noche")
                            }
                            Spacer(modifier = Modifier.height(4.dp))
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("Motor IA:")
                                Text(text = if (sensores.presencia_ia) "Humano detectado" else "Despejado")
                            }
                        }
                    }
                }

                // 3. CONTROL REMOTO BIDIRECCIONAL
                item {
                    Button(
                        onClick = {
                            val db = FirebaseFirestore.getInstance()

                            // Mandar la orden al puente en Firebase
                            db.collection("comandos").document("app").set(mapOf("activar_zumbador" to true))

                            // Guardar el evento en el historial de alertas
                            val alertaRemota = hashMapOf(
                                "tipo" to "Alarma Remota",
                                "descripcion" to "Zumbador activado manualmente desde el dashboard.",
                                "timestamp" to com.google.firebase.firestore.FieldValue.serverTimestamp()
                            )
                            db.collection("alertas").add(alertaRemota)
                        },
                        modifier = Modifier.fillMaxWidth().height(50.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)
                    ) {
                        Text("ACTIVAR ALARMA REMOTA")
                    }
                }

                // 4. HISTORIAL DE ALERTAS ASINCRONAS
                item {
                    Text("Historial de Alertas", style = MaterialTheme.typography.titleMedium)
                }

                items(alertas) { alerta ->
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)
                    ) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            Text(alerta.tipo, style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onErrorContainer)
                            Text(alerta.descripcion, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onErrorContainer)
                        }
                    }
                }
            }
        }
    }
}