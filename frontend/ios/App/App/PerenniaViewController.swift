/**
 * PerenniaViewController.swift
 * Custom Capacitor ViewController for Perennia AI
 *
 * Registers custom native plugins with the Capacitor bridge.
 * Add new plugin registrations to capacitorDidLoad().
 */

import UIKit
import Capacitor

class PerenniaViewController: CAPBridgeViewController {

    override open func capacitorDidLoad() {
        // Register custom native plugins
        bridge?.registerPluginInstance(DeviceIntegrityPlugin())
        bridge?.registerPluginInstance(MDMConfigPlugin())
    }
}
