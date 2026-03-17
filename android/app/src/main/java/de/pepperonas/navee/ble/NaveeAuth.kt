package de.pepperonas.navee.ble

import android.content.Context
import android.util.Log
import javax.crypto.Cipher
import javax.crypto.spec.SecretKeySpec

/**
 * Navee BLE authentication.
 * Device-ID und Post-Auth-Params werden in SharedPreferences gespeichert,
 * nicht im Quellcode.
 */
object NaveeAuth {

    private const val TAG = "NaveeAuth"
    private const val PREFS_NAME = "navee_auth"
    private const val KEY_DEVICE_ID = "device_id"
    private const val KEY_POST_AUTH_PARAMS = "post_auth_params"

    private val KEYS: Array<ByteArray> = arrayOf(
        byteArrayOf(
            0xA0.toByte(), 0xA1.toByte(), 0xA2.toByte(), 0xA3.toByte(),
            0xA4.toByte(), 0xA5.toByte(), 0xA6.toByte(), 0xA7.toByte(),
            0xA8.toByte(), 0xA9.toByte(), 0xAA.toByte(), 0xAB.toByte(),
            0xAC.toByte(), 0xAD.toByte(), 0xAE.toByte(), 0xAF.toByte()
        ),
        byteArrayOf(
            0x44, 0x6D, 0x10, 0x72, 0x6D, 0xBE.toByte(), 0x05, 0xF6.toByte(),
            0x62, 0xDF.toByte(), 0xAA.toByte(), 0xF0.toByte(), 0x13, 0x27, 0x30, 0x3F
        ),
        byteArrayOf(
            0xA2.toByte(), 0x85.toByte(), 0xCC.toByte(), 0xEC.toByte(),
            0x81.toByte(), 0x4F, 0xE9.toByte(), 0x61,
            0x74, 0x29, 0x95.toByte(), 0xE8.toByte(),
            0xEB.toByte(), 0xA9.toByte(), 0x22, 0x47
        ),
        byteArrayOf(
            0x3F, 0xEE.toByte(), 0x80.toByte(), 0xFF.toByte(),
            0x9A.toByte(), 0xDF.toByte(), 0x5C, 0xF5.toByte(),
            0x42, 0xEA.toByte(), 0xAC.toByte(), 0x93.toByte(),
            0x28, 0x1F, 0xE5.toByte(), 0x29
        ),
        byteArrayOf(
            0x4E, 0xB4.toByte(), 0xD4.toByte(), 0x64,
            0xD6.toByte(), 0xEF.toByte(), 0x53, 0xED.toByte(),
            0x6C, 0xE9.toByte(), 0x45, 0x58,
            0xDE.toByte(), 0x9A.toByte(), 0x5E, 0xE3.toByte()
        ),
    )

    var selectedKeyIndex: Int = 1
        private set

    private var deviceId: ByteArray? = null
    private var postAuthParams: ByteArray? = null

    /** Load credentials from SharedPreferences. */
    fun init(context: Context) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        deviceId = prefs.getString(KEY_DEVICE_ID, null)?.hexToByteArray()
        postAuthParams = prefs.getString(KEY_POST_AUTH_PARAMS, null)?.hexToByteArray()
        Log.i(TAG, "Loaded credentials: hasDeviceId=${deviceId != null}, hasPostAuth=${postAuthParams != null}")
    }

    /** Save credentials to SharedPreferences. */
    fun saveCredentials(context: Context, deviceIdHex: String, postAuthParamsHex: String) {
        deviceId = deviceIdHex.hexToByteArray()
        postAuthParams = postAuthParamsHex.hexToByteArray()
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit()
            .putString(KEY_DEVICE_ID, deviceIdHex)
            .putString(KEY_POST_AUTH_PARAMS, postAuthParamsHex)
            .apply()
        Log.i(TAG, "Credentials saved")
    }

    fun hasCredentials(): Boolean = deviceId != null

    fun buildAuthRequest(): ByteArray? {
        val id = deviceId ?: run {
            Log.e(TAG, "No device ID configured — set via saveCredentials()")
            return null
        }
        selectedKeyIndex = 1
        val data = byteArrayOf(selectedKeyIndex.toByte(), 0x00) + id.copyOf(6) + byteArrayOf(0x00)
        Log.i(TAG, "Auth request: keyIndex=$selectedKeyIndex")
        return NaveeProtocol.buildFrame(NaveeProtocol.CMD_AUTH, data)
    }

    fun buildPostAuthParams(): ByteArray? {
        val params = postAuthParams ?: return null
        return NaveeProtocol.buildFrame(NaveeProtocol.CMD_SET_PARAMS, params)
    }

    fun processAuthResponse(data: ByteArray): ByteArray? {
        if (data.isEmpty()) return null
        val errorCode = data[0].toInt() and 0xFF
        if (errorCode != 0) {
            Log.e(TAG, "Auth error code: $errorCode")
        }
        val challenge = data.copyOfRange(1, data.size)
        if (challenge.isEmpty()) return null
        val decrypted = decryptChallenge(challenge) ?: return null
        return NaveeProtocol.buildFrame(NaveeProtocol.CMD_AUTH_KEY, decrypted)
    }

    private fun decryptChallenge(encrypted: ByteArray): ByteArray? {
        val key = KEYS[selectedKeyIndex]
        return when {
            encrypted.size == 16 -> aesDecrypt(encrypted, key)
            encrypted.size > 16 -> if (encrypted[0] == 0x00.toByte()) {
                xorDecrypt(encrypted.copyOfRange(1, encrypted.size), key)
            } else {
                aesDecrypt(encrypted.copyOf(16), key)
            }
            else -> {
                val padded = ByteArray(16)
                encrypted.copyInto(padded)
                aesDecrypt(padded, key)
            }
        }
    }

    private fun aesDecrypt(data: ByteArray, key: ByteArray): ByteArray? = try {
        val cipher = Cipher.getInstance("AES/ECB/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"))
        cipher.doFinal(data)
    } catch (e: Exception) {
        Log.e(TAG, "AES decrypt failed: ${e.message}")
        null
    }

    private fun xorDecrypt(data: ByteArray, key: ByteArray) = ByteArray(data.size) { i ->
        (data[i].toInt() xor key[i % key.size].toInt()).toByte()
    }

    private fun String.hexToByteArray(): ByteArray =
        chunked(2).map { it.toInt(16).toByte() }.toByteArray()
}
