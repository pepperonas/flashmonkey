package de.pepperonas.navee.ble

import java.util.UUID

/**
 * Navee BLE protocol — corrected command mapping based on official APK decompilation.
 *
 * Frame format: 55 AA 00 <CMD> [LEN] [DATA...] <CHECKSUM> FE FD
 * Checksum = sum of all bytes (including 55 AA header) mod 256
 */
object NaveeProtocol {

    // BLE UUIDs
    val SERVICE_UUID: UUID = UUID.fromString("0000d0ff-3c17-d293-8e48-14fe2e4da212")
    val WRITE_CHAR_UUID: UUID = UUID.fromString("0000b002-0000-1000-8000-00805f9b34fb")
    val NOTIFY_CHAR_UUID: UUID = UUID.fromString("0000b003-0000-1000-8000-00805f9b34fb")
    val CCCD_UUID: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

    // --- Write commands (single byte parameter) ---
    const val CMD_UNBIND: Byte = 0x50
    const val CMD_LOCK: Byte = 0x51           // 0=unlock, 1=lock
    const val CMD_CRUISE: Byte = 0x52         // 0=off, 1=on (official mapping)
    const val CMD_ERS: Byte = 0x53            // Energy Recovery Strength (regen braking)
    const val CMD_MILEAGE_UNIT: Byte = 0x55   // 0=MPH, 1=KM
    const val CMD_MILEAGE_ALGO: Byte = 0x56   // Mileage algorithm
    const val CMD_SPEED_MODE: Byte = 0x58     // 3=ECO, 5=SPORT
    const val CMD_RESET_VEHICLE: Byte = 0x59  // Reset/restore vehicle
    const val CMD_TIRE_MAINT: Byte = 0x5A     // Tire maintenance (param=1)
    const val CMD_AMBIENT_LIGHT: Byte = 0x5E  // Ambient light
    const val CMD_PROXIMITY_KEY: Byte = 0x61  // Proximity key toggle
    const val CMD_STARTUP_SPEED: Byte = 0x6A  // Startup speed (0-5, 0.0-3.0 m/s)
    const val CMD_SPEED_LIMIT: Byte = 0x6B    // Custom speed limit (bit7=enable, bits0-6=km/h)
    const val CMD_WEATHER: Byte = 0x80.toByte() // Weather update

    // --- Write commands (multi-byte data) ---
    const val CMD_SET_PASSWORD: Byte = 0x63   // Set digit password (6 bytes)
    const val CMD_LIGHT_CTRL: Byte = 0x67     // Light control (variable length)
    const val CMD_MAX_SPEED: Byte = 0x6E      // Set max speed [0x01, km/h]
    const val CMD_SET_PARAMS: Byte = 0x6F     // Set scooter parameters (variable)

    // --- Read/status commands ---
    const val CMD_STATUS: Byte = 0x70         // Read vehicle settings (39 bytes response)
    const val CMD_TRIP_DATA: Byte = 0x71      // Read driving/trip data
    const val CMD_BATTERY: Byte = 0x72        // Read battery status (34+ bytes)
    const val CMD_FIRMWARE: Byte = 0x73       // Read firmware versions (16+ bytes)
    const val CMD_SERIAL: Byte = 0x74         // Read serial number (17 bytes)
    const val CMD_BATTERY_SN: Byte = 0x75     // Read battery serial number
    const val CMD_DRIVE_HISTORY: Byte = 0x76  // Read drive history
    const val CMD_BATTERY_EXTRA: Byte = 0x79  // Read battery extra info
    const val CMD_PASSWORD_STATUS: Byte = 0x7A // Read password & switch status

    // --- Auth commands ---
    const val CMD_AUTH: Byte = 0x30           // Auth challenge/identity
    const val CMD_AUTH_KEY: Byte = 0x31       // Encrypted response/key

    // --- Unsolicited telemetry ---
    const val CMD_TELEMETRY_90: Byte = 0x90.toByte()  // Home page telemetry (15+ bytes)
    const val CMD_TELEMETRY_91: Byte = 0x91.toByte()  // Realtime status v0 (9 bytes)
    const val CMD_TELEMETRY_92: Byte = 0x92.toByte()  // Realtime status v1 (14+ bytes)

    // Speed modes
    const val SPEED_MODE_ECO: Byte = 0x03
    const val SPEED_MODE_SPORT: Byte = 0x05

    private val HEADER = byteArrayOf(0x55, 0xAA.toByte())
    private val FOOTER = byteArrayOf(0xFE.toByte(), 0xFD.toByte())

    fun buildFrame(cmd: Byte, data: ByteArray = byteArrayOf()): ByteArray {
        val body = if (data.isEmpty()) {
            byteArrayOf(0x00, cmd)
        } else {
            byteArrayOf(0x00, cmd) + byteArrayOf(data.size.toByte()) + data
        }
        val withHeader = HEADER + body
        val checksum = (withHeader.sumOf { it.toInt() and 0xFF } and 0xFF).toByte()
        return withHeader + checksum + FOOTER
    }

    // Read requests
    fun statusRequest() = buildFrame(CMD_STATUS)
    fun serialRequest() = buildFrame(CMD_SERIAL)
    fun firmwareRequest() = buildFrame(CMD_FIRMWARE)
    fun tripRequest() = buildFrame(CMD_DRIVE_HISTORY)
    fun batteryRequest() = buildFrame(CMD_BATTERY)
    fun batterySNRequest() = buildFrame(CMD_BATTERY_SN)
    fun batteryExtraRequest() = buildFrame(CMD_BATTERY_EXTRA)

    // Write commands
    fun setLock(locked: Boolean) = buildFrame(CMD_LOCK, byteArrayOf(if (locked) 0x01 else 0x00))
    fun setCruise(on: Boolean) = buildFrame(CMD_CRUISE, byteArrayOf(if (on) 0x01 else 0x00))
    fun setSpeedMode(mode: Byte) = buildFrame(CMD_SPEED_MODE, byteArrayOf(mode))
    fun setERS(level: Byte) = buildFrame(CMD_ERS, byteArrayOf(level))
    fun setAmbientLight(value: Byte) = buildFrame(CMD_AMBIENT_LIGHT, byteArrayOf(value))
    fun setProximityKey(on: Boolean) = buildFrame(CMD_PROXIMITY_KEY, byteArrayOf(if (on) 0x01 else 0x00))
    fun setStartupSpeed(level: Byte) = buildFrame(CMD_STARTUP_SPEED, byteArrayOf(level))

    /** Set max speed in absolute km/h. Data format: [0x01, speed_kmh]. */
    fun setMaxSpeed(kmh: Int) = buildFrame(CMD_MAX_SPEED, byteArrayOf(0x01, kmh.toByte()))

    /** Set custom speed limit. Bit 7 = enabled, bits 0-6 = speed in km/h. */
    fun setCustomSpeedLimit(kmh: Int, enabled: Boolean): ByteArray {
        val value = if (enabled) (0x80 or (kmh and 0x7F)) else 0x00
        return buildFrame(CMD_SPEED_LIMIT, byteArrayOf(value.toByte()))
    }

    /** Light control (multi-byte). */
    fun setLight(data: ByteArray) = buildFrame(CMD_LIGHT_CTRL, data)

    fun parseFrame(raw: ByteArray): ParsedFrame? {
        if (raw.size < 5) return null
        if (raw[0] != 0x55.toByte() || raw[1] != 0xAA.toByte()) return null
        if (raw[raw.size - 2] != 0xFE.toByte() || raw[raw.size - 1] != 0xFD.toByte()) return null

        val body = raw.copyOfRange(2, raw.size - 2)
        if (body.size < 2) return null

        val cmd = body[1]

        return if (body.size > 3) {
            val len = body[2].toInt() and 0xFF
            val data = if (body.size >= 3 + len) body.copyOfRange(3, 3 + len) else body.copyOfRange(3, body.size - 1)
            ParsedFrame(cmd, data)
        } else {
            ParsedFrame(cmd, byteArrayOf())
        }
    }

    /** Extract PID from BLE scan record bytes 6-8 (little-endian 16-bit). */
    fun extractPID(scanRecord: ByteArray?): Int? {
        if (scanRecord == null || scanRecord.size <= 8) return null
        val lo = scanRecord[6].toInt() and 0xFF
        val hi = scanRecord[7].toInt() and 0xFF
        return (hi shl 8) or lo
    }

    data class ParsedFrame(val cmd: Byte, val data: ByteArray) {
        override fun equals(other: Any?): Boolean {
            if (this === other) return true
            if (other !is ParsedFrame) return false
            return cmd == other.cmd && data.contentEquals(other.data)
        }
        override fun hashCode() = 31 * cmd.hashCode() + data.contentHashCode()
    }
}

/**
 * Scooter state from CMD_STATUS (0x70) — 37 bytes.
 * Byte mapping verified against BT HCI capture of official Navee app.
 */
data class ScooterState(
    val speedMode: Int = 3,         // Byte 2: 03=ECO, 05=SPORT
    val locked: Boolean = false,    // Byte 3: 00=unlocked, 01=locked
    val cruiseOn: Boolean = false,  // Byte 4
    val ersLevel: Int = 0,          // Byte 6: ERS/speed percentage
    val headlightOn: Boolean = false, // Byte 9: verified via BT capture (0x57)
    val taillightOn: Boolean = false, // Byte 13: verified via BT capture (0x60)
    val startupSpeed: Int = 3,      // Byte 20
    val speedLimitEnabled: Boolean = false,
    val speedLimitKmh: Int = 0,
    val maxSpeed: Int = 0,          // Byte 26: firmware cap (0x16=22 for DE)
)

data class ScooterTelemetry(
    val battery: Int = 0,           // Byte 3: 0-100%
    val speed: Int = 0,             // Bytes 5-6: little-endian, /10 for km/h
    val temperature: Int = 0,       // Byte 7
    val totalDistance: Int = 0,     // Bytes 9-10: little-endian, /10 for km
)

/**
 * Parse 0x70 status response (37 bytes).
 * Byte mapping verified against BT HCI capture:
 *   Byte  2 = speedMode (03=ECO, 05=SPORT) — verified: changes with 0x58 command
 *   Byte  3 = lock (0/1) — verified: changes with 0x51 command
 *   Byte  4 = cruise — assumed from protocol position
 *   Byte  6 = ERS/speed setting (3C=60, 5A=90)
 *   Byte  9 = headlight (0/1) — verified: changes with 0x57 command
 *   Byte 13 = taillight (0/1) — verified: changes with 0x60 command
 *   Byte 20 = startup speed (0-5)
 *   Byte 26 = max speed firmware cap (22 km/h for DE market)
 */
fun parseStatus(data: ByteArray): ScooterState? {
    if (data.size < 10) return null
    return ScooterState(
        speedMode = data[2].toInt() and 0xFF,
        locked = data[3] == 0x01.toByte(),
        cruiseOn = if (data.size > 4) data[4] == 0x01.toByte() else false,
        ersLevel = if (data.size > 6) data[6].toInt() and 0xFF else 0,
        headlightOn = if (data.size > 9) data[9] == 0x01.toByte() else false,
        taillightOn = if (data.size > 13) data[13] == 0x01.toByte() else false,
        startupSpeed = if (data.size > 20) data[20].toInt() and 0xFF else 3,
        speedLimitEnabled = data.size > 20 && (data[20].toInt() and 0x80) != 0,
        speedLimitKmh = if (data.size > 20) data[20].toInt() and 0x7F else 0,
        maxSpeed = if (data.size > 26) data[26].toInt() and 0xFF else 0,
    )
}

/**
 * Parse 0x90 telemetry.
 * Verified against BT capture: data[3]=battery%, data[5:6]=speed, data[7]=temp, data[9:10]=odo
 */
fun parseTelemetry(data: ByteArray): ScooterTelemetry? {
    if (data.size < 11) return null
    return ScooterTelemetry(
        battery = data[3].toInt() and 0xFF,
        speed = (data[5].toInt() and 0xFF) or ((data[6].toInt() and 0xFF) shl 8),
        temperature = data[7].toInt() and 0xFF,
        totalDistance = (data[9].toInt() and 0xFF) or ((data[10].toInt() and 0xFF) shl 8),
    )
}
