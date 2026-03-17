package de.pepperonas.navee.viewmodel

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.pepperonas.navee.ble.*
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

class ScooterViewModel(app: Application) : AndroidViewModel(app) {

    companion object {
        private const val TAG = "ScooterVM"

        fun getMaxSpeedOptionsForPID(pid: Int?): List<Int> = when (pid) {
            2509 -> listOf(25, 30, 35, 40)
            2511, 2516 -> listOf(25, 32, 45, 50)
            2547 -> listOf(25, 32, 40, 50, 60)
            2585 -> listOf(25, 32, 40, 50, 70)
            2544 -> listOf(25, 30, 35, 40, 45, 50, 55, 60)
            2449 -> listOf(25, 30, 35, 40, 45, 50, 55, 60, 65)
            2416, 2443, 2529 -> listOf(25, 32, 45, 50)
            2611, 2612, 2643 -> listOf(25, 32)
            2402, 2403, 2418 -> listOf(25, 32)
            else -> listOf(20, 25, 30, 32, 35, 40)
        }
    }

    val ble = NaveeBleManager(app.applicationContext)

    val connectionState = ble.connectionState
    val deviceName = ble.deviceName
    val pid = ble.pid

    private val _state = MutableStateFlow(ScooterState())
    val state: StateFlow<ScooterState> = _state

    private val _telemetry = MutableStateFlow(ScooterTelemetry())
    val telemetry: StateFlow<ScooterTelemetry> = _telemetry

    private val _serial = MutableStateFlow("")
    val serial: StateFlow<String> = _serial

    private val _firmware = MutableStateFlow("")
    val firmware: StateFlow<String> = _firmware

    private val _authenticated = MutableStateFlow(false)
    val authenticated: StateFlow<Boolean> = _authenticated

    private var pollingJob: Job? = null

    val maxSpeedOptions: StateFlow<List<Int>> = pid.map { pid ->
        getMaxSpeedOptionsForPID(pid)
    }.stateIn(viewModelScope, SharingStarted.Eagerly, listOf(25, 32, 40))

    init {
        NaveeAuth.init(app.applicationContext)

        viewModelScope.launch {
            ble.incomingFrames.collect { frame ->
                handleFrame(frame)
            }
        }

        viewModelScope.launch {
            ble.connectionState.collect { connState ->
                when (connState) {
                    ConnectionState.CONNECTED -> {
                        _authenticated.value = false
                        pollingJob?.cancel()
                        startAuthThenPoll()
                    }
                    ConnectionState.DISCONNECTED -> {
                        _authenticated.value = false
                        pollingJob?.cancel()
                        delay(3000)
                        if (ble.connectionState.value == ConnectionState.DISCONNECTED) {
                            ble.startScan()
                        }
                    }
                    else -> {}
                }
            }
        }
    }

    fun connect() = ble.startScan()
    fun disconnect() = ble.disconnect()

    fun toggleLock() {
        ble.send(NaveeProtocol.setLock(!_state.value.locked))
        requestStatus()
    }

    fun toggleCruise() {
        ble.send(NaveeProtocol.setCruise(!_state.value.cruiseOn))
        requestStatus()
    }

    fun toggleTaillight() {
        val on = !_state.value.taillightOn
        ble.send(NaveeProtocol.buildFrame(0x60, byteArrayOf(if (on) 0x01 else 0x00)))
        requestStatus()
    }

    fun toggleHeadlight() {
        val on = !_state.value.headlightOn
        ble.send(NaveeProtocol.buildFrame(0x57, byteArrayOf(if (on) 0x01 else 0x00)))
        requestStatus()
    }

    fun setSpeedMode(eco: Boolean) {
        val mode = if (eco) NaveeProtocol.SPEED_MODE_ECO else NaveeProtocol.SPEED_MODE_SPORT
        ble.send(NaveeProtocol.setSpeedMode(mode))
        requestStatus()
    }

    fun setMaxSpeed(kmh: Int) {
        ble.send(NaveeProtocol.setMaxSpeed(kmh))
        requestStatus()
    }

    fun setCustomSpeedLimit(kmh: Int, enabled: Boolean) {
        ble.send(NaveeProtocol.setCustomSpeedLimit(kmh, enabled))
        requestStatus()
    }

    fun setErsLevel(level: Int) {
        ble.send(NaveeProtocol.setERS(level.toByte()))
        requestStatus()
    }

    fun setStartupSpeed(level: Int) {
        ble.send(NaveeProtocol.setStartupSpeed(level.toByte()))
        requestStatus()
    }

    private fun requestStatus() {
        viewModelScope.launch {
            delay(100)
            ble.send(NaveeProtocol.statusRequest())
        }
    }

    private fun startAuthThenPoll() {
        viewModelScope.launch {
            if (NaveeAuth.hasCredentials()) {
                Log.i(TAG, "Starting authentication...")
                val authFrame = NaveeAuth.buildAuthRequest()
                if (authFrame != null) {
                    ble.send(authFrame)
                    delay(5000)
                    if (!_authenticated.value) {
                        Log.w(TAG, "Auth timeout — polling without auth")
                        startPolling()
                    }
                    return@launch
                }
            }
            Log.w(TAG, "No auth credentials — polling without auth")
            startPolling()
        }
    }

    private fun startPolling() {
        pollingJob?.cancel()
        pollingJob = viewModelScope.launch {
            ble.send(NaveeProtocol.serialRequest())
            delay(200)
            ble.send(NaveeProtocol.firmwareRequest())
            delay(200)
            ble.send(NaveeProtocol.statusRequest())
            delay(200)
            ble.send(NaveeProtocol.batteryRequest())

            while (ble.connectionState.value == ConnectionState.CONNECTED) {
                delay(2000)
                ble.send(NaveeProtocol.statusRequest())
            }
        }
    }

    private fun handleFrame(frame: NaveeProtocol.ParsedFrame) {
        when (frame.cmd) {
            NaveeProtocol.CMD_AUTH -> {
                Log.i(TAG, "AUTH response: ${frame.data.joinToString(" ") { "%02X".format(it) }}")
                val success = frame.data.isNotEmpty() && frame.data[0] == 0x00.toByte()
                if (success) {
                    _authenticated.value = true
                    Log.i(TAG, "AUTH SUCCESS")
                    NaveeAuth.buildPostAuthParams()?.let { ble.send(it) }
                    viewModelScope.launch {
                        delay(200)
                        startPolling()
                    }
                } else {
                    Log.e(TAG, "AUTH FAILED: error=${frame.data.getOrNull(0)?.toInt()?.and(0xFF)}")
                    startPolling()
                }
            }
            NaveeProtocol.CMD_STATUS -> {
                parseStatus(frame.data)?.let { _state.value = it }
            }
            NaveeProtocol.CMD_TELEMETRY_90 -> {
                parseTelemetry(frame.data)?.let { _telemetry.value = it }
            }
            NaveeProtocol.CMD_SERIAL -> {
                _serial.value = frame.data.drop(1)
                    .takeWhile { it != 0x00.toByte() }
                    .toByteArray()
                    .toString(Charsets.US_ASCII)
            }
            NaveeProtocol.CMD_FIRMWARE -> {
                _firmware.value = frame.data.drop(1)
                    .takeWhile { it != 0x00.toByte() }
                    .toByteArray()
                    .toString(Charsets.US_ASCII)
            }
            else -> {}
        }
    }

    override fun onCleared() {
        super.onCleared()
        ble.disconnect()
    }
}
