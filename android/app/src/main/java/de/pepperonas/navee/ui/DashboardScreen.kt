package de.pepperonas.navee.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.pepperonas.navee.ble.ConnectionState
import de.pepperonas.navee.ble.ScooterState
import de.pepperonas.navee.ble.ScooterTelemetry
import de.pepperonas.navee.viewmodel.ScooterViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(viewModel: ScooterViewModel) {
    val connState by viewModel.connectionState.collectAsState()
    val deviceName by viewModel.deviceName.collectAsState()
    val state by viewModel.state.collectAsState()
    val telemetry by viewModel.telemetry.collectAsState()
    val serial by viewModel.serial.collectAsState()
    val firmware by viewModel.firmware.collectAsState()
    val pid by viewModel.pid.collectAsState()
    val maxSpeedOptions by viewModel.maxSpeedOptions.collectAsState()
    val authenticated by viewModel.authenticated.collectAsState()

    var showAutoLightDialog by remember { mutableStateOf(false) }
    var showInfoSheet by remember { mutableStateOf(false) }

    val context = LocalContext.current
    val prefs = remember { context.getSharedPreferences("navee_ui", android.content.Context.MODE_PRIVATE) }
    var autoLightHintDismissed by remember { mutableStateOf(prefs.getBoolean("auto_light_hint_ok", false)) }

    if (showAutoLightDialog) {
        AutoLightDialog(
            onDismiss = { understood ->
                if (understood) {
                    autoLightHintDismissed = true
                    prefs.edit().putBoolean("auto_light_hint_ok", true).apply()
                }
                showAutoLightDialog = false
            }
        )
    }

    if (showInfoSheet) {
        InfoSheet(onDismiss = { showInfoSheet = false })
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Navee ST3 Pro", fontWeight = FontWeight.Bold)
                        if (connState == ConnectionState.CONNECTED && deviceName != null) {
                            Text(
                                deviceName ?: "",
                                style = MaterialTheme.typography.bodySmall,
                                color = NaveeGreen
                            )
                        }
                    }
                },
                actions = {
                    if (connState == ConnectionState.CONNECTED) {
                        IconButton(onClick = { showInfoSheet = true }) {
                            Icon(Icons.Default.Info, "Info", tint = Color.Gray)
                        }
                    }
                    ConnectionButton(connState, viewModel)
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = NaveeDark
                )
            )
        },
        containerColor = NaveeDark
    ) { padding ->
        if (connState != ConnectionState.CONNECTED) {
            DisconnectedView(connState, Modifier.padding(padding), viewModel)
        } else {
            Column(
                modifier = Modifier
                    .padding(padding)
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Spacer(Modifier.height(4.dp))
                BatteryAndSpeedCard(telemetry, state)
                ControlsGrid(state, viewModel, onLightToggle = {
                    viewModel.toggleLight()
                    if (!autoLightHintDismissed && !state.autoHeadlight) {
                        showAutoLightDialog = true
                    }
                })
                SpeedModeCard(state, viewModel)
                MaxSpeedCard(state, maxSpeedOptions, viewModel)
                ErsCard(state, viewModel)
                InfoCard(serial, firmware, telemetry, pid, state, authenticated)
                Spacer(Modifier.height(16.dp))
            }
        }
    }
}

// --- Auto-Licht Hinweis-Dialog ---

@Composable
private fun AutoLightDialog(onDismiss: (Boolean) -> Unit) {
    var checked by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = { },
        containerColor = NaveeSurface,
        title = {
            Text(
                "Automatisches Licht aktiviert",
                fontWeight = FontWeight.Bold,
                fontSize = 18.sp
            )
        },
        text = {
            Column {
                Text(
                    "Wenn du das Frontlicht manuell ein- oder ausschaltest, wird die " +
                    "Automatikfunktion vorübergehend deaktiviert. Sie wird nach einem " +
                    "Neustart des Scooters wieder aktiviert.",
                    fontSize = 14.sp,
                    color = Color.Gray
                )
                Spacer(Modifier.height(16.dp))
                Text(
                    "Front- und Rücklicht werden gemeinsam über den Helligkeitssensor gesteuert.",
                    fontSize = 14.sp,
                    color = Color.Gray
                )
                Spacer(Modifier.height(16.dp))
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.clickable { checked = !checked }
                ) {
                    Checkbox(
                        checked = checked,
                        onCheckedChange = { checked = it },
                        colors = CheckboxDefaults.colors(checkedColor = NaveeGreen)
                    )
                    Spacer(Modifier.width(8.dp))
                    Text("Verstanden, nicht mehr anzeigen", fontSize = 14.sp)
                }
            }
        },
        confirmButton = {
            Button(
                onClick = { onDismiss(checked) },
                colors = ButtonDefaults.buttonColors(containerColor = NaveeGreen)
            ) {
                Text("OK", color = Color.Black, fontWeight = FontWeight.Bold)
            }
        }
    )
}

// --- Info Sheet ---

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun InfoSheet(onDismiss: () -> Unit) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = NaveeSurface
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 16.dp)
        ) {
            Text("Funktionsübersicht", fontWeight = FontWeight.Bold, fontSize = 20.sp)
            Spacer(Modifier.height(20.dp))

            InfoSection(Icons.Default.Lock, "Sperre", NaveeRed,
                "Sperrt/entsperrt den Scooter. Im gesperrten Zustand kann der " +
                "Scooter nicht gefahren werden und gibt bei Bewegung einen Alarm aus.")

            InfoSection(Icons.Default.Lightbulb, "Licht (Auto-Sensor)", NaveeOrange,
                "Steuert den automatischen Helligkeitssensor. Front- und Rücklicht " +
                "schalten sich je nach Umgebungshelligkeit automatisch ein/aus.\n\n" +
                "Hinweis: Manuelles Ein-/Ausschalten deaktiviert die Automatik " +
                "vorübergehend. Sie wird nach einem Neustart des Scooters wieder aktiviert.")

            InfoSection(Icons.Default.Speed, "Tempomat", NaveeBlue,
                "Aktiviert/deaktiviert die Geschwindigkeitsregelung (Cruise Control). " +
                "Hält die aktuelle Geschwindigkeit ohne Gas geben.")

            InfoSection(Icons.Default.Security, "TCS", NaveeGreen,
                "Traktionskontrolle (Traction Control System). Verhindert Schlupf " +
                "beim Beschleunigen auf nassem oder rutschigem Untergrund.")

            InfoSection(Icons.Default.VolumeUp, "Blinker-Ton", NaveeBlue,
                "Aktiviert/deaktiviert den akustischen Blinker-Sound beim Abbiegen.")

            HorizontalDivider(modifier = Modifier.padding(vertical = 12.dp), color = NaveeCard)

            InfoSection(null, "Fahrmodus (ECO/SPORT)", NaveeOrange,
                "ECO: Energiesparender Modus mit sanfter Beschleunigung.\n" +
                "SPORT: Volle Leistung mit stärkerer Beschleunigung.")

            InfoSection(null, "Max Speed", NaveeOrange,
                "Zeigt das Firmware-Geschwindigkeitslimit an (22 km/h für DE-Markt). " +
                "Dieses Limit ist firmware-seitig fest und kann nicht per BLE geändert werden.")

            InfoSection(null, "Energierückgewinnung (ERS)", NaveeGreen,
                "Stärke der Rekuperationsbremse:\n" +
                "  Niedrig (30) — schwache Bremswirkung, mehr Reichweite\n" +
                "  Mittel (60) — ausgewogen\n" +
                "  Hoch (90) — starke Bremswirkung, maximale Energierückgewinnung")

            Spacer(Modifier.height(32.dp))
        }
    }
}

@Composable
private fun InfoSection(icon: ImageVector?, title: String, color: Color, description: String) {
    Row(modifier = Modifier.padding(vertical = 8.dp)) {
        if (icon != null) {
            Icon(
                icon,
                contentDescription = null,
                modifier = Modifier.size(24.dp).padding(top = 2.dp),
                tint = color
            )
            Spacer(Modifier.width(12.dp))
        }
        Column(modifier = Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.Bold, fontSize = 15.sp, color = color)
            Spacer(Modifier.height(4.dp))
            Text(description, fontSize = 13.sp, color = Color.Gray, lineHeight = 18.sp)
        }
    }
}

// --- Standard UI Components ---

@Composable
private fun ConnectionButton(state: ConnectionState, viewModel: ScooterViewModel) {
    when (state) {
        ConnectionState.DISCONNECTED -> {
            IconButton(onClick = { viewModel.connect() }) {
                Icon(Icons.Default.BluetoothSearching, "Verbinden", tint = Color.Gray)
            }
        }
        ConnectionState.SCANNING, ConnectionState.CONNECTING -> {
            CircularProgressIndicator(
                modifier = Modifier.size(24.dp).padding(end = 8.dp),
                strokeWidth = 2.dp,
                color = NaveeOrange
            )
        }
        ConnectionState.CONNECTED -> {
            IconButton(onClick = { viewModel.disconnect() }) {
                Icon(Icons.Default.BluetoothConnected, "Verbunden", tint = NaveeGreen)
            }
        }
    }
}

@Composable
private fun DisconnectedView(state: ConnectionState, modifier: Modifier, viewModel: ScooterViewModel) {
    Column(
        modifier = modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            Icons.Default.ElectricScooter,
            contentDescription = null,
            modifier = Modifier.size(96.dp),
            tint = Color.Gray
        )
        Spacer(Modifier.height(24.dp))
        Text(
            when (state) {
                ConnectionState.SCANNING -> "Suche Navee ST3 Pro..."
                ConnectionState.CONNECTING -> "Verbinde..."
                else -> "Nicht verbunden"
            },
            style = MaterialTheme.typography.headlineSmall,
            color = Color.Gray
        )
        Spacer(Modifier.height(16.dp))
        if (state == ConnectionState.DISCONNECTED) {
            Button(
                onClick = { viewModel.connect() },
                colors = ButtonDefaults.buttonColors(containerColor = NaveeGreen)
            ) {
                Icon(Icons.Default.Bluetooth, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("Verbinden", color = Color.Black, fontWeight = FontWeight.Bold)
            }
        } else {
            CircularProgressIndicator(color = NaveeGreen)
        }
    }
}

@Composable
@Suppress("UNUSED_PARAMETER")
private fun BatteryAndSpeedCard(telemetry: ScooterTelemetry, state: ScooterState) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = NaveeCard)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(20.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                val batteryColor = when {
                    telemetry.battery > 50 -> NaveeGreen
                    telemetry.battery > 20 -> NaveeOrange
                    else -> NaveeRed
                }
                Text("${telemetry.battery}%", fontSize = 42.sp, fontWeight = FontWeight.Bold, color = batteryColor)
                Text("Akku", color = Color.Gray, fontSize = 14.sp)
            }
            HorizontalDivider(modifier = Modifier.height(60.dp).width(1.dp), color = Color.Gray.copy(alpha = 0.3f))
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text("${telemetry.speed / 10}.${telemetry.speed % 10}", fontSize = 42.sp, fontWeight = FontWeight.Bold, color = Color.White)
                Text("km/h", color = Color.Gray, fontSize = 14.sp)
            }
            HorizontalDivider(modifier = Modifier.height(60.dp).width(1.dp), color = Color.Gray.copy(alpha = 0.3f))
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    "${telemetry.remainRange}",
                    fontSize = 42.sp,
                    fontWeight = FontWeight.Bold,
                    color = when {
                        telemetry.remainRange > 30 -> NaveeGreen
                        telemetry.remainRange > 10 -> NaveeOrange
                        else -> NaveeRed
                    }
                )
                Text("km", color = Color.Gray, fontSize = 14.sp)
            }
        }
    }
}

@Composable
private fun ControlsGrid(state: ScooterState, viewModel: ScooterViewModel, onLightToggle: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            ToggleCard(
                modifier = Modifier.weight(1f),
                icon = if (state.locked) Icons.Default.Lock else Icons.Default.LockOpen,
                label = if (state.locked) "Gesperrt" else "Entsperrt",
                active = state.locked, activeColor = NaveeRed,
                onClick = { viewModel.toggleLock() }
            )
            ToggleCard(
                modifier = Modifier.weight(1f),
                icon = Icons.Default.Lightbulb,
                label = "Licht",
                active = state.autoHeadlight, activeColor = NaveeOrange,
                onClick = onLightToggle
            )
        }
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            ToggleCard(
                modifier = Modifier.weight(1f),
                icon = Icons.Default.Speed,
                label = "Tempomat",
                active = state.cruiseOn, activeColor = NaveeBlue,
                onClick = { viewModel.toggleCruise() }
            )
            ToggleCard(
                modifier = Modifier.weight(1f),
                icon = Icons.Default.Security,
                label = "TCS",
                active = state.tcsOn, activeColor = NaveeGreen,
                onClick = { viewModel.toggleTcs() }
            )
        }
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            ToggleCard(
                modifier = Modifier.weight(1f),
                icon = Icons.Default.VolumeUp,
                label = "Blinker-Ton",
                active = state.turnSound, activeColor = NaveeBlue,
                onClick = { viewModel.toggleTurnSound() }
            )
            Spacer(Modifier.weight(1f))
        }
    }
}

@Composable
private fun ToggleCard(modifier: Modifier, icon: ImageVector, label: String, active: Boolean, activeColor: Color, onClick: () -> Unit) {
    val bgColor by animateColorAsState(if (active) activeColor.copy(alpha = 0.15f) else NaveeCard, animationSpec = tween(300))
    val borderColor by animateColorAsState(if (active) activeColor else Color.Transparent, animationSpec = tween(300))

    Card(
        onClick = onClick,
        modifier = modifier.height(100.dp).border(1.5.dp, borderColor, RoundedCornerShape(16.dp)),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = bgColor)
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(12.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(icon, contentDescription = label, modifier = Modifier.size(32.dp), tint = if (active) activeColor else Color.Gray)
            Spacer(Modifier.height(8.dp))
            Text(label, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = if (active) Color.White else Color.Gray)
        }
    }
}

@Composable
private fun SpeedModeCard(state: ScooterState, viewModel: ScooterViewModel) {
    Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = NaveeCard)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("Fahrmodus", fontWeight = FontWeight.Bold, fontSize = 16.sp)
            Spacer(Modifier.height(12.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                ModeButton(Modifier.weight(1f), "ECO", state.speedMode == 3, NaveeGreen) { viewModel.setSpeedMode(eco = true) }
                ModeButton(Modifier.weight(1f), "SPORT", state.speedMode == 5, NaveeOrange) { viewModel.setSpeedMode(eco = false) }
            }
        }
    }
}

@Composable
private fun MaxSpeedCard(state: ScooterState, options: List<Int>, viewModel: ScooterViewModel) {
    // Manueller Slider-Wert, initialisiert aus aktuellem State
    var sliderValue by remember(state.maxSpeed) {
        mutableStateOf(if (state.maxSpeed > 0) state.maxSpeed.toFloat() else 20f)
    }

    Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = NaveeCard)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("Max Speed", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                if (state.maxSpeed > 0) Text("Aktuell: ${state.maxSpeed} km/h", fontSize = 13.sp, color = NaveeOrange, fontWeight = FontWeight.Medium)
            }
            Spacer(Modifier.height(12.dp))
            options.chunked(4).forEach { row ->
                Row(modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    row.forEach { kmh ->
                        ModeButton(Modifier.weight(1f), "$kmh", state.maxSpeed == kmh, if (kmh > 25) NaveeOrange else NaveeBlue) { viewModel.setMaxSpeed(kmh) }
                    }
                    repeat(4 - row.size) { Spacer(Modifier.weight(1f)) }
                }
            }

            // === DEBUG: Manueller Slider ===
            Spacer(Modifier.height(8.dp))
            HorizontalDivider(color = Color.Gray.copy(alpha = 0.3f))
            Spacer(Modifier.height(12.dp))

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("DEBUG: Manuell", fontWeight = FontWeight.Bold, fontSize = 14.sp, color = NaveeOrange)
                Text("${sliderValue.toInt()} km/h", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = NaveeOrange)
            }
            Spacer(Modifier.height(4.dp))
            Slider(
                value = sliderValue,
                onValueChange = { sliderValue = it },
                valueRange = 5f..60f,
                steps = 54,  // 5..60 = 55 Werte, 54 Steps
                colors = SliderDefaults.colors(
                    thumbColor = NaveeOrange,
                    activeTrackColor = NaveeOrange,
                    inactiveTrackColor = Color.Gray.copy(alpha = 0.3f)
                )
            )
            Spacer(Modifier.height(4.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = { viewModel.setMaxSpeed(sliderValue.toInt()) },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = NaveeOrange)
                ) {
                    Text("Senden (${sliderValue.toInt()} km/h)", fontSize = 13.sp)
                }
            }

            Spacer(Modifier.height(8.dp))
            Text("km/h — Werte > 20 nur auf Privatgelände", fontSize = 11.sp, color = Color.Gray.copy(alpha = 0.6f))
            Text("Slider: beliebiger Wert 5-60 km/h (BLE CMD 0x6E)", fontSize = 10.sp, color = Color.Gray.copy(alpha = 0.5f))
        }
    }
}

@Composable
private fun ErsCard(state: ScooterState, viewModel: ScooterViewModel) {
    Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = NaveeCard)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("Energierückgewinnung", fontWeight = FontWeight.Bold, fontSize = 16.sp)
            Spacer(Modifier.height(12.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                listOf(30 to "Niedrig", 60 to "Mittel", 90 to "Hoch").forEach { (level, label) ->
                    ModeButton(Modifier.weight(1f), label, state.ersLevel == level, NaveeGreen) { viewModel.setErsLevel(level) }
                }
            }
        }
    }
}

@Composable
private fun ModeButton(modifier: Modifier, label: String, selected: Boolean, color: Color, onClick: () -> Unit) {
    val bgColor by animateColorAsState(if (selected) color else Color.Transparent, animationSpec = tween(300))
    Box(
        modifier = modifier.height(44.dp).clip(RoundedCornerShape(12.dp)).background(bgColor)
            .border(1.dp, if (selected) Color.Transparent else Color.Gray.copy(alpha = 0.3f), RoundedCornerShape(12.dp))
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        Text(label, fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal, fontSize = 14.sp, color = if (selected) Color.Black else Color.Gray)
    }
}

@Composable
private fun InfoCard(serial: String, firmware: String, telemetry: ScooterTelemetry, pid: Int?, state: ScooterState, authenticated: Boolean) {
    Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = NaveeCard)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("Info", fontWeight = FontWeight.Bold, fontSize = 16.sp)
            Spacer(Modifier.height(12.dp))
            InfoRow("Auth", if (authenticated) "OK" else "Nicht authentifiziert")
            if (pid != null) InfoRow("PID", "$pid")
            if (serial.isNotEmpty()) InfoRow("Seriennummer", serial)
            if (firmware.isNotEmpty()) InfoRow("Firmware", firmware)
            if (state.maxSpeed > 0) InfoRow("Max Speed (FW)", "${state.maxSpeed} km/h")
            if (telemetry.totalMileage > 0) InfoRow("Gesamtstrecke", "${telemetry.totalMileage} km")
            if (telemetry.batteryVoltage > 0) InfoRow("Spannung", String.format("%.1f V", telemetry.batteryVoltage / 1000.0))
            InfoRow("Modus", if (state.speedMode == 5) "SPORT" else "ECO")
            InfoRow("ERS Level", "${state.ersLevel}")
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = Color.Gray, fontSize = 14.sp)
        Text(value, fontSize = 14.sp, fontWeight = FontWeight.Medium)
    }
}
