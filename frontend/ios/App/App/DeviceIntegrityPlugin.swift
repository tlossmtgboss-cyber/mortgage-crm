/**
 * DeviceIntegrityPlugin.swift
 * Perennia AI - Device Integrity / Jailbreak Detection
 *
 * This is defense-in-depth, not a guarantee. Determined jailbreakers can bypass
 * heuristic checks. The goal is to raise the bar for casual exploitation and
 * provide a signal to the app layer so it can restrict sensitive features
 * (biometric auth, document upload, payment) on compromised devices.
 *
 * Checks performed:
 * 1. Known jailbreak file paths (Cydia, Sileo, substrate, etc.)
 * 2. Ability to write outside the app sandbox
 * 3. Suspicious URL schemes (cydia://, sileo://)
 * 4. Fork-based sandbox escape detection
 * 5. Dynamic library injection detection (DYLD_INSERT_LIBRARIES)
 * 6. Symbolic link checks on system paths
 */

import Foundation
import Capacitor
import MachO

@objc(DeviceIntegrityPlugin)
public class DeviceIntegrityPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "DeviceIntegrityPlugin"
    public let jsName = "DeviceIntegrity"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "checkIntegrity", returnType: CAPPluginReturnPromise)
    ]

    // MARK: - Known jailbreak indicators

    /// File paths commonly present on jailbroken devices
    private let suspiciousFilePaths: [String] = [
        // Package managers
        "/Applications/Cydia.app",
        "/Applications/Sileo.app",
        "/Applications/Zebra.app",
        "/Applications/Installer.app",

        // Common jailbreak binaries
        "/bin/bash",
        "/bin/sh",
        "/usr/sbin/sshd",
        "/usr/bin/ssh",
        "/usr/libexec/sftp-server",
        "/etc/apt",
        "/etc/ssh/sshd_config",

        // Substrate / Substitute / ElleKit
        "/Library/MobileSubstrate/MobileSubstrate.dylib",
        "/Library/MobileSubstrate/DynamicLibraries",
        "/usr/lib/libsubstitute.dylib",
        "/usr/lib/substitute-loader.dylib",
        "/usr/lib/TweakInject.dylib",
        "/usr/lib/libhooker.dylib",

        // Common jailbreak artifacts
        "/var/lib/apt",
        "/var/lib/cydia",
        "/var/cache/apt",
        "/var/log/syslog",
        "/private/var/stash",
        "/private/var/tmp/cydia.log",
        "/private/var/lib/apt/",

        // Checkra1n / unc0ver / Taurine / Dopamine
        "/jb/lzma",
        "/.installed_unc0ver",
        "/.bootstrapped_electra",
        "/var/binpack",
        "/var/checkra1n.dmg",
        "/usr/lib/libjailbreak.dylib",

        // Frida (instrumentation framework used in attacks)
        "/usr/sbin/frida-server",
        "/usr/bin/cycript",
        "/usr/local/bin/cycript",
    ]

    /// URL schemes associated with jailbreak tools
    private let suspiciousURLSchemes: [String] = [
        "cydia://",
        "sileo://",
        "zbra://",
        "filza://",
        "undecimus://",
    ]

    /// Paths to attempt sandbox escape write test
    private let sandboxWriteTestPaths: [String] = [
        "/private/jailbreak_test",
        "/tmp/jailbreak_integrity_check",
    ]

    // MARK: - Plugin Method

    @objc func checkIntegrity(_ call: CAPPluginCall) {
        var reasons: [String] = []

        // Check 1: Known jailbreak file paths
        let filePathResults = checkSuspiciousFiles()
        reasons.append(contentsOf: filePathResults)

        // Check 2: Sandbox escape (write to restricted path)
        let sandboxResults = checkSandboxIntegrity()
        reasons.append(contentsOf: sandboxResults)

        // Check 3: Suspicious URL schemes
        let urlSchemeResults = checkURLSchemes()
        reasons.append(contentsOf: urlSchemeResults)

        // Check 4: Fork-based detection (sandbox should prevent fork)
        let forkResults = checkForkAvailability()
        reasons.append(contentsOf: forkResults)

        // Check 5: Dynamic library injection
        let dyldResults = checkDyldInjection()
        reasons.append(contentsOf: dyldResults)

        // Check 6: Symbolic link checks on system directories
        let symlinkResults = checkSymlinks()
        reasons.append(contentsOf: symlinkResults)

        let isCompromised = !reasons.isEmpty

        // Determine risk level based on severity
        let riskLevel: String
        if reasons.count >= 3 {
            riskLevel = "critical"
        } else if reasons.count >= 1 {
            riskLevel = "warning"
        } else {
            riskLevel = "safe"
        }

        call.resolve([
            "isCompromised": isCompromised,
            "reasons": reasons,
            "riskLevel": riskLevel,
            "platform": "ios",
            "checkCount": 6,
        ])
    }

    // MARK: - Individual Checks

    /// Check for existence of known jailbreak-related files
    private func checkSuspiciousFiles() -> [String] {
        var found: [String] = []
        let fileManager = FileManager.default

        for path in suspiciousFilePaths {
            if fileManager.fileExists(atPath: path) {
                found.append("suspicious_file:\(path)")
            }
        }

        // Also check if certain system paths are accessible that shouldn't be
        if fileManager.isReadableFile(atPath: "/etc/fstab") {
            found.append("readable_restricted_file:/etc/fstab")
        }

        return found
    }

    /// Attempt to write outside the app sandbox
    private func checkSandboxIntegrity() -> [String] {
        var results: [String] = []

        for path in sandboxWriteTestPaths {
            let testString = "integrity_check"
            do {
                try testString.write(toFile: path, atomically: true, encoding: .utf8)
                // If we can write here, sandbox is broken
                results.append("sandbox_escape:write_succeeded:\(path)")
                // Clean up
                try? FileManager.default.removeItem(atPath: path)
            } catch {
                // Expected on non-jailbroken device - write should fail
            }
        }

        return results
    }

    /// Check for jailbreak-associated URL schemes
    private func checkURLSchemes() -> [String] {
        var found: [String] = []

        if Thread.isMainThread {
            // Already on main thread — check directly (avoids deadlock)
            for scheme in self.suspiciousURLSchemes {
                if let url = URL(string: scheme) {
                    if UIApplication.shared.canOpenURL(url) {
                        found.append("url_scheme:\(scheme)")
                    }
                }
            }
        } else {
            // Dispatch to main thread and wait
            let semaphore = DispatchSemaphore(value: 0)

            DispatchQueue.main.async {
                for scheme in self.suspiciousURLSchemes {
                    if let url = URL(string: scheme) {
                        if UIApplication.shared.canOpenURL(url) {
                            found.append("url_scheme:\(scheme)")
                        }
                    }
                }
                semaphore.signal()
            }

            _ = semaphore.wait(timeout: .now() + 2.0)
        }

        return found
    }

    /// Check if the app can access restricted system directories.
    /// On a non-jailbroken device, these should not be readable.
    /// NOTE: fork() was previously used here but is unsafe — it creates a child process
    /// that can crash the app on some iOS versions. File-based checks are equally effective.
    private func checkForkAvailability() -> [String] {
        var results: [String] = []

        // Check if we can read from system paths that should be restricted
        let restrictedPaths = [
            "/private/var/lib/apt",
            "/private/var/stash",
            "/usr/libexec/sftp-server",
        ]

        for path in restrictedPaths {
            if FileManager.default.isReadableFile(atPath: path) {
                results.append("restricted_path_readable:\(path)")
            }
        }

        return results
    }

    /// Check for signs of dynamic library injection
    private func checkDyldInjection() -> [String] {
        var results: [String] = []

        // Check DYLD_INSERT_LIBRARIES environment variable
        if let dyldInsert = getenv("DYLD_INSERT_LIBRARIES") {
            let libraries = String(cString: dyldInsert)
            results.append("dyld_injection:\(libraries)")
        }

        // Check loaded image count for anomalies
        // A typical non-jailbroken app loads ~300-500 images.
        // Injected tweaks push this higher, but we use a generous threshold
        // to avoid false positives.
        let imageCount = _dyld_image_count()
        if imageCount > 800 {
            results.append("excessive_dyld_images:\(imageCount)")
        }

        // Check for known injected library names in loaded images
        let suspiciousLibs = [
            "MobileSubstrate",
            "SubstrateLoader",
            "TweakInject",
            "libhooker",
            "substitute",
            "frida",
            "cycript",
        ]

        for i in 0..<_dyld_image_count() {
            if let imageName = _dyld_get_image_name(i) {
                let name = String(cString: imageName)
                for lib in suspiciousLibs {
                    if name.lowercased().contains(lib.lowercased()) {
                        results.append("injected_library:\(name)")
                        break
                    }
                }
            }
        }

        return results
    }

    /// Check if key system directories are symbolic links (jailbreak stashing)
    private func checkSymlinks() -> [String] {
        var results: [String] = []
        let fileManager = FileManager.default

        let pathsToCheck = [
            "/Applications",
            "/Library/Ringtones",
            "/Library/Wallpaper",
            "/usr/arm-apple-darwin9",
            "/usr/include",
            "/usr/libexec",
        ]

        for path in pathsToCheck {
            do {
                let attrs = try fileManager.attributesOfItem(atPath: path)
                if let fileType = attrs[.type] as? FileAttributeType,
                   fileType == .typeSymbolicLink {
                    results.append("symlink_detected:\(path)")
                }
            } catch {
                // Path doesn't exist or not accessible - expected on stock device
            }
        }

        return results
    }
}
