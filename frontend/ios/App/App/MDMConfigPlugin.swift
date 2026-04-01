import Foundation
import Capacitor
import SystemConfiguration.CaptiveNetwork
import LocalAuthentication
import UIKit

/// Native Capacitor plugin for reading MDM (Mobile Device Management) managed
/// app configuration from UserDefaults on iOS.
///
/// MDM servers push configuration payloads to managed devices which are
/// written to `UserDefaults.standard` under the `com.apple.configuration.managed`
/// key. This plugin reads those values and returns them to the JavaScript layer.
///
/// Registration: The plugin is registered via `capacitorDidLoad()` in a custom
/// ViewController, or auto-discovered by Capacitor's plugin loading.
@objc(MDMConfigPlugin)
public class MDMConfigPlugin: CAPPlugin, CAPBridgedPlugin {

    // MARK: - CAPBridgedPlugin conformance

    public let identifier = "MDMConfigPlugin"
    public let jsName = "MDMConfig"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "getManagedConfig", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "isManagedDevice", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getCurrentNetworkSSID", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "checkBiometricAvailability", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getDeviceInfo", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "setScreenshotPrevention", returnType: CAPPluginReturnPromise)
    ]

    // MARK: - MDM configuration keys

    /// The UserDefaults key where MDM-pushed managed app configuration lives.
    private static let managedConfigKey = "com.apple.configuration.managed"

    /// Keys we expect from the MDM profile. Used for validation and filtering.
    private static let expectedKeys: Set<String> = [
        "com.perenniaai.crm.server_url",
        "com.perenniaai.crm.organization_id",
        "com.perenniaai.crm.sso_provider",
        "com.perenniaai.crm.sso_domain",
        "com.perenniaai.crm.features_disabled",
        "com.perenniaai.crm.require_biometric",
        "com.perenniaai.crm.session_timeout",
        "com.perenniaai.crm.allow_screenshots",
        "com.perenniaai.crm.min_os_version",
        "com.perenniaai.crm.allowed_networks"
    ]

    // MARK: - Screenshot prevention

    private var screenshotPreventionField: UITextField?

    // MARK: - Plugin methods

    /// Read the full managed app configuration dictionary from UserDefaults.
    ///
    /// MDM profiles push key-value pairs into `UserDefaults.standard` under
    /// the `com.apple.configuration.managed` dictionary. This method reads
    /// that dictionary and returns all Perennia-namespaced keys.
    ///
    /// Returns: `{ config: { "com.perenniaai.crm.server_url": "...", ... } }`
    @objc func getManagedConfig(_ call: CAPPluginCall) {
        let defaults = UserDefaults.standard

        // The managed configuration dictionary pushed by MDM
        guard let managedConfig = defaults.dictionary(forKey: MDMConfigPlugin.managedConfigKey) else {
            // No managed configuration present — device may not be enrolled
            // Also check for individual keys directly in UserDefaults as some
            // MDM solutions write keys at the top level
            let fallbackConfig = readFallbackConfig(from: defaults)
            call.resolve(["config": fallbackConfig])
            return
        }

        // Filter to only Perennia keys and serialize for JavaScript
        var filtered: [String: Any] = [:]
        for (key, value) in managedConfig {
            if MDMConfigPlugin.expectedKeys.contains(key) {
                filtered[key] = serializeValue(value)
            }
        }

        call.resolve(["config": filtered])
    }

    /// Check whether the device has MDM managed configuration present.
    ///
    /// Returns: `{ managed: true/false, enrollmentInfo: { ... } }`
    @objc func isManagedDevice(_ call: CAPPluginCall) {
        let defaults = UserDefaults.standard

        // Primary check: managed config dictionary exists
        let hasManagedConfig = defaults.dictionary(forKey: MDMConfigPlugin.managedConfigKey) != nil

        // Secondary check: any Perennia keys exist at top level
        let hasFallbackKeys = MDMConfigPlugin.expectedKeys.contains { key in
            defaults.object(forKey: key) != nil
        }

        // Tertiary check: device supervision status via profile
        let isSupervised = checkDeviceSupervision()

        let managed = hasManagedConfig || hasFallbackKeys

        var enrollmentInfo: [String: Any] = [
            "hasManagedConfig": hasManagedConfig,
            "hasFallbackKeys": hasFallbackKeys,
            "isSupervised": isSupervised
        ]

        // Include MDM profile identifier if available
        if let profileId = defaults.string(forKey: "com.apple.configuration.managed.profileIdentifier") {
            enrollmentInfo["profileIdentifier"] = profileId
        }

        call.resolve([
            "managed": managed,
            "enrollmentInfo": enrollmentInfo
        ])
    }

    /// Get the SSID of the currently connected WiFi network.
    /// Used for network restriction compliance checks.
    ///
    /// Returns: `{ ssid: "NetworkName" }` or `{ ssid: null }` if unavailable.
    @objc func getCurrentNetworkSSID(_ call: CAPPluginCall) {
        let ssid = fetchCurrentSSID()
        if let ssid = ssid {
            call.resolve(["ssid": ssid])
        } else {
            call.resolve(["ssid": NSNull()])
        }
    }

    /// Check whether biometric authentication (Face ID / Touch ID) is
    /// available on this device.
    ///
    /// Returns: `{ available: true/false, biometryType: "faceID"|"touchID"|"none", error: "..." }`
    @objc func checkBiometricAvailability(_ call: CAPPluginCall) {
        let context = LAContext()
        var error: NSError?
        let canEvaluate = context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error)

        var biometryType = "none"
        if #available(iOS 11.0, *) {
            switch context.biometryType {
            case .faceID:
                biometryType = "faceID"
            case .touchID:
                biometryType = "touchID"
            case .opticID:
                biometryType = "opticID"
            @unknown default:
                biometryType = "unknown"
            }
        }

        var result: [String: Any] = [
            "available": canEvaluate,
            "biometryType": biometryType
        ]

        if let error = error {
            result["error"] = error.localizedDescription
        }

        call.resolve(result)
    }

    /// Return basic device information for compliance checks.
    ///
    /// Returns: `{ osVersion: "17.4.1", model: "iPhone", deviceModel: "iPhone" }`
    @objc func getDeviceInfo(_ call: CAPPluginCall) {
        let device = UIDevice.current

        call.resolve([
            "osVersion": device.systemVersion,
            "model": device.model,
            "deviceModel": device.model,
            "systemName": device.systemName,
            "identifierForVendor": device.identifierForVendor?.uuidString ?? ""
        ])
    }

    /// Enable or disable screenshot/screen recording prevention.
    /// Uses a secure UITextField overlay technique to prevent screen capture.
    ///
    /// Parameters: `{ enabled: true/false }`
    @objc func setScreenshotPrevention(_ call: CAPPluginCall) {
        let enabled = call.getBool("enabled") ?? false

        DispatchQueue.main.async { [weak self] in
            guard let self = self else {
                call.reject("Plugin instance deallocated")
                return
            }

            if enabled {
                self.enableScreenshotPrevention()
            } else {
                self.disableScreenshotPrevention()
            }

            call.resolve(["enabled": enabled])
        }
    }

    // MARK: - Private helpers

    /// Read Perennia keys directly from UserDefaults top level.
    /// Some MDM solutions (particularly simpler ones) write keys directly
    /// rather than under the managed config dictionary.
    private func readFallbackConfig(from defaults: UserDefaults) -> [String: Any] {
        var config: [String: Any] = [:]
        for key in MDMConfigPlugin.expectedKeys {
            if let value = defaults.object(forKey: key) {
                config[key] = serializeValue(value)
            }
        }
        return config
    }

    /// Convert a value to a JSON-safe type that can cross the native/JS bridge.
    private func serializeValue(_ value: Any) -> Any {
        switch value {
        case let string as String:
            return string
        case let number as NSNumber:
            // NSNumber wraps both booleans and numbers; check the type encoding
            if CFGetTypeID(number) == CFBooleanGetTypeID() {
                return number.boolValue
            }
            return number
        case let array as [Any]:
            return array.map { serializeValue($0) }
        case let dict as [String: Any]:
            return dict.mapValues { serializeValue($0) }
        default:
            return String(describing: value)
        }
    }

    /// Check if the device appears to be supervised (DEP enrolled).
    private func checkDeviceSupervision() -> Bool {
        // There is no public API for checking supervision status directly.
        // We use a heuristic: check for the presence of configuration profiles
        // that are typically only present on supervised devices.
        let defaults = UserDefaults.standard
        let hasManaged = defaults.dictionary(forKey: MDMConfigPlugin.managedConfigKey) != nil
        let hasRestrictions = defaults.dictionary(forKey: "com.apple.configuration.managed.restrictions") != nil
        return hasManaged || hasRestrictions
    }

    /// Fetch the current WiFi SSID using CaptiveNetwork API.
    private func fetchCurrentSSID() -> String? {
        // NEHotspotNetwork is preferred on iOS 14+ but requires entitlement.
        // Fall back to CNCopyCurrentNetworkInfo for broader compatibility.
        guard let interfaces = CNCopySupportedInterfaces() as? [String] else {
            return nil
        }

        for interface in interfaces {
            guard let info = CNCopyCurrentNetworkInfo(interface as CFString) as? [String: Any] else {
                continue
            }
            if let ssid = info[kCNNetworkInfoKeySSID as String] as? String, !ssid.isEmpty {
                return ssid
            }
        }

        return nil
    }

    /// Enable screenshot prevention using a secure text field overlay.
    /// iOS marks UITextField with isSecureTextEntry as protected content,
    /// which causes screen capture/recording to show a blank area.
    private func enableScreenshotPrevention() {
        guard screenshotPreventionField == nil else { return }

        guard let window = self.bridge?.webView?.window else { return }

        let field = UITextField()
        field.isSecureTextEntry = true
        field.isUserInteractionEnabled = false
        field.frame = window.bounds
        field.autoresizingMask = [.flexibleWidth, .flexibleHeight]

        window.addSubview(field)
        // Move to back so it does not interfere with touch events
        window.sendSubviewToBack(field)

        // The secure text field's layer makes the window content
        // appear blank in screenshots and screen recordings
        if let secureLayer = field.layer.sublayers?.first {
            secureLayer.frame = window.bounds
            window.layer.superlayer?.addSublayer(secureLayer)
        }

        screenshotPreventionField = field
    }

    /// Remove the screenshot prevention overlay.
    private func disableScreenshotPrevention() {
        screenshotPreventionField?.removeFromSuperview()
        screenshotPreventionField = nil
    }
}
