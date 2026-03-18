package de.pepperonas.navee

import android.app.Application
import de.pepperonas.navee.ble.NaveeAuth

class NaveeApp : Application() {
    override fun onCreate() {
        super.onCreate()
        NaveeAuth.init(this)

        // Credentials müssen beim ersten Start manuell gesetzt werden.
        // Device-ID und Post-Auth-Params aus BT-Capture extrahieren
        // und über die App-Einstellungen oder ein Setup-Screen eingeben.
        // Siehe docs/AUTHENTICATION.md für Details.
    }
}
