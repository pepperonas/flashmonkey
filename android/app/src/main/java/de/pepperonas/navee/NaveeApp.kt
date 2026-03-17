package de.pepperonas.navee

import android.app.Application
import de.pepperonas.navee.ble.NaveeAuth

class NaveeApp : Application() {
    override fun onCreate() {
        super.onCreate()
        NaveeAuth.init(this)

        // Seed credentials on first run (extracted from BT capture)
        if (!NaveeAuth.hasCredentials()) {
            NaveeAuth.saveCredentials(
                context = this,
                deviceIdHex = "REDACTED_DEVICE_ID",
                postAuthParamsHex = "REDACTED_POST_AUTH"
            )
        }
    }
}
