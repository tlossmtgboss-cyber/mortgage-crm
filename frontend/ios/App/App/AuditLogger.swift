/**
 * AuditLogger.swift
 * Perennia AI — Encrypted Security Audit Trail
 *
 * Persistent, encrypted audit log for SOC 2 Type II and GLBA compliance.
 * Every security-relevant event (auth, biometric, integrity, data access)
 * is logged locally with timestamps and synced to the backend in batches.
 *
 * Storage: Encrypted JSON file in app documents directory.
 * Retention: 90 days local, synced to backend for long-term storage.
 * Capacity: Max 10,000 entries, oldest evicted first.
 */

import Foundation
import os.log
import CryptoKit

// MARK: - AuditLogger

@available(iOS 14.0, *)
final class AuditLogger: @unchecked Sendable {

    // MARK: - Singleton

    static let shared = AuditLogger()

    // MARK: - Event Types

    enum EventType: String, Codable {
        // Authentication
        case authAttempt = "auth.attempt"
        case authSuccess = "auth.success"
        case authFailure = "auth.failure"
        case tokenRefresh = "auth.token_refresh"
        case sessionStart = "auth.session_start"
        case sessionEnd = "auth.session_end"
        case logout = "auth.logout"

        // Biometric
        case biometricPrompt = "biometric.prompt"
        case biometricSuccess = "biometric.success"
        case biometricFailure = "biometric.failure"

        // Device Security
        case deviceIntegrityCheck = "security.integrity_check"
        case deviceCompromised = "security.device_compromised"
        case certificatePinFailure = "security.pin_failure"
        case certificatePinSuccess = "security.pin_success"
        case securityViolation = "security.violation"

        // Data Access
        case dataAccess = "data.access"
        case documentView = "data.document_view"
        case documentUpload = "data.document_upload"
        case piiViewed = "data.pii_viewed"
        case dataExport = "data.export"

        // Feature Access
        case featureAccess = "feature.access"
        case featureBlocked = "feature.blocked"

        // CarPlay
        case carplayConnected = "carplay.connected"
        case carplayDisconnected = "carplay.disconnected"
        case carplayCallInitiated = "carplay.call_initiated"

        // App Lifecycle
        case appForeground = "app.foreground"
        case appBackground = "app.background"
        case appTerminated = "app.terminated"
    }

    // MARK: - Audit Entry

    struct AuditEntry: Codable {
        let id: String
        let timestamp: TimeInterval
        let event: EventType
        let details: [String: String]
        let deviceInfo: DeviceInfo
        let synced: Bool
        let previousHash: String
        let hash: String

        struct DeviceInfo: Codable {
            let model: String
            let osVersion: String
            let appVersion: String
        }
    }

    // MARK: - Properties

    private let log = OSLog(subsystem: "com.perenniaai.crm", category: "AuditLog")
    private let queue = DispatchQueue(label: "com.perenniaai.crm.audit.queue")
    private let maxEntries = 10_000
    private let retentionDays = 90
    private let batchSyncSize = 50

    private var entries: [AuditEntry] = []
    private var deviceInfo: AuditEntry.DeviceInfo
    private var foregroundSyncTimer: Timer?

    // MARK: - Hash Chain (Tamper Evidence)

    /// Genesis hash used as previousHash for the first entry in the chain.
    private static let genesisHash = String(repeating: "0", count: 64)

    /// The hash of the most recent entry, used as previousHash for the next entry.
    /// Initialized to genesis hash; reconstructed from persisted logs on load.
    private var lastEntryHash: String = AuditLogger.genesisHash

    /// Compute SHA-256 hash of an audit entry's content (before encryption).
    /// The entry dict must include all fields EXCEPT "hash" itself, since the hash
    /// is computed over the entry content including previousHash.
    private func computeEntryHash(entry: [String: Any]) -> String {
        guard let data = try? JSONSerialization.data(
            withJSONObject: entry,
            options: [.sortedKeys]
        ) else {
            os_log(.error, log: self.log, "Hash computation failed: could not serialize entry")
            return ""
        }
        let digest = SHA256.hash(data: data)
        return digest.compactMap { String(format: "%02x", $0) }.joined()
    }

    /// Build a dictionary representation of an entry for hashing.
    /// Includes all immutable fields except "hash" (which is what we are computing).
    /// Note: "synced" is excluded because it is mutable operational state — marking an
    /// entry as synced must not invalidate the hash chain.
    private func entryDictForHashing(
        id: String,
        timestamp: TimeInterval,
        event: String,
        details: [String: String],
        deviceModel: String,
        deviceOS: String,
        appVersion: String,
        previousHash: String
    ) -> [String: Any] {
        return [
            "id": id,
            "timestamp": timestamp,
            "event": event,
            "details": details,
            "deviceInfo": [
                "model": deviceModel,
                "osVersion": deviceOS,
                "appVersion": appVersion
            ],
            "previousHash": previousHash
        ]
    }

    /// Reconstruct lastEntryHash from the most recent persisted entry.
    private func reconstructLastHash() {
        if let lastEntry = entries.last, !lastEntry.hash.isEmpty {
            lastEntryHash = lastEntry.hash
        } else {
            lastEntryHash = AuditLogger.genesisHash
        }
    }

    /// Verify the integrity of the entire hash chain.
    /// Returns (true, nil) if the chain is intact, or (false, brokenIndex) if
    /// a tampered or corrupted entry is found.
    ///
    /// Note: After eviction (max capacity or expiry purge), the first remaining
    /// entry's previousHash will reference an evicted entry. The verifier trusts
    /// the first entry's previousHash and validates the chain from there onward.
    func verifyChainIntegrity() -> (valid: Bool, brokenAt: Int?) {
        return queue.sync {
            guard !entries.isEmpty else { return (true, nil) }

            // Trust the first entry's previousHash as the chain anchor
            // (it may reference an evicted entry or the genesis hash).
            var previousHash = entries[0].previousHash

            for (index, entry) in entries.enumerated() {
                // 1. Check previousHash linkage
                if entry.previousHash != previousHash {
                    os_log(.error, log: self.log,
                           "Hash chain broken at index %d: previousHash mismatch", index)
                    return (false, index)
                }

                // 2. Recompute hash and compare
                let dict = entryDictForHashing(
                    id: entry.id,
                    timestamp: entry.timestamp,
                    event: entry.event.rawValue,
                    details: entry.details,
                    deviceModel: entry.deviceInfo.model,
                    deviceOS: entry.deviceInfo.osVersion,
                    appVersion: entry.deviceInfo.appVersion,
                    previousHash: entry.previousHash
                )
                let recomputedHash = computeEntryHash(entry: dict)

                if recomputedHash.isEmpty || recomputedHash != entry.hash {
                    os_log(.error, log: self.log,
                           "Hash chain broken at index %d: hash mismatch", index)
                    return (false, index)
                }

                previousHash = entry.hash
            }

            return (true, nil)
        }
    }

    private var logFileURL: URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return docs.appendingPathComponent("audit_log.enc")
    }

    // MARK: - Init

    private init() {
        let device = UIDevice.current
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
        self.deviceInfo = AuditEntry.DeviceInfo(
            model: device.model,
            osVersion: device.systemVersion,
            appVersion: version
        )
        loadEntries()
        purgeExpired()
    }

    // MARK: - Public API

    /// Log a security event with hash chain linkage for tamper evidence.
    func log(event: EventType, details: [String: String] = [:]) {
        queue.async { [weak self] in
            guard let self = self else { return }

            let entryId = UUID().uuidString
            let entryTimestamp = Date().timeIntervalSince1970
            let previousHash = self.lastEntryHash

            // Build dict for hashing (all immutable fields except "hash" itself)
            let dictForHash = self.entryDictForHashing(
                id: entryId,
                timestamp: entryTimestamp,
                event: event.rawValue,
                details: details,
                deviceModel: self.deviceInfo.model,
                deviceOS: self.deviceInfo.osVersion,
                appVersion: self.deviceInfo.appVersion,
                previousHash: previousHash
            )

            // Compute SHA-256 hash BEFORE encryption
            let entryHash = self.computeEntryHash(entry: dictForHash)

            let entry = AuditEntry(
                id: entryId,
                timestamp: entryTimestamp,
                event: event,
                details: details,
                deviceInfo: self.deviceInfo,
                synced: false,
                previousHash: previousHash,
                hash: entryHash
            )

            self.entries.append(entry)
            self.lastEntryHash = entryHash

            // Enforce max size — if eviction happens, reconstruct hash from new oldest
            if self.entries.count > self.maxEntries {
                self.entries.removeFirst(self.entries.count - self.maxEntries)
                // Note: eviction breaks the chain at the start, which is expected.
                // The chain from the oldest remaining entry onward stays intact.
            }

            self.saveEntries()

            os_log(.info, log: self.log, "Audit: %{public}@ %{public}@",
                   event.rawValue,
                   details.isEmpty ? "" : details.description)
        }
    }

    /// Get recent log entries (for diagnostic display).
    func getRecentLogs(limit: Int = 50) -> [AuditEntry] {
        return queue.sync {
            Array(entries.suffix(limit))
        }
    }

    /// Get count of unsynced entries.
    var unsyncedCount: Int {
        return queue.sync { entries.filter { !$0.synced }.count }
    }

    /// Sync unsynced entries to backend. Returns count synced.
    func syncToBackend() async -> Int {
        let unsyncedEntries: [AuditEntry] = queue.sync {
            Array(entries.filter { !$0.synced }.prefix(batchSyncSize))
        }

        guard !unsyncedEntries.isEmpty else { return 0 }
        guard let token = KeychainService.shared.authToken else { return 0 }

        do {
            var request = URLRequest(url: URL(string: "\(APIConfig.apiBaseURL)/api/v1/security/audit-log")!)
            request.httpMethod = "POST"
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")

            let payload = try JSONEncoder().encode(["entries": unsyncedEntries])
            request.httpBody = payload

            let (_, response) = try await CertificatePinning.pinnedSession.data(for: request)

            if let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) {
                // Mark as synced
                let syncedIds = Set(unsyncedEntries.map { $0.id })
                queue.sync {
                    entries = entries.map { entry in
                        if syncedIds.contains(entry.id) {
                            return AuditEntry(
                                id: entry.id,
                                timestamp: entry.timestamp,
                                event: entry.event,
                                details: entry.details,
                                deviceInfo: entry.deviceInfo,
                                synced: true,
                                previousHash: entry.previousHash,
                                hash: entry.hash
                            )
                        }
                        return entry
                    }
                    saveEntries()
                }
                return unsyncedEntries.count
            }
        } catch {
            os_log(.error, log: log, "Audit sync failed: %{public}@", error.localizedDescription)
        }
        return 0
    }

    /// Start a repeating timer that syncs audit logs to the backend while the app is in the foreground.
    /// This prevents data loss if the app crashes before backgrounding — a SOC 2 compliance requirement.
    /// - Parameter interval: Sync interval in seconds (default 300 = 5 minutes).
    func startForegroundSync(interval: TimeInterval = 300) {
        stopForegroundSync()
        foregroundSyncTimer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            Task { await self.syncToBackend() }
        }
        RunLoop.main.add(foregroundSyncTimer!, forMode: .common)
    }

    /// Stop the foreground periodic sync timer.
    func stopForegroundSync() {
        foregroundSyncTimer?.invalidate()
        foregroundSyncTimer = nil
    }

    /// Clear all entries (on account deletion or compliance request).
    func clearAll() {
        queue.sync {
            entries.removeAll()
            lastEntryHash = AuditLogger.genesisHash
            saveEntries()
        }
    }

    // MARK: - Persistence (Encrypted)

    private func saveEntries() {
        do {
            let data = try JSONEncoder().encode(entries)
            let encrypted = try EncryptedCacheService.shared.encrypt(plaintext: data)
            try encrypted.write(to: logFileURL, options: [.atomic, .completeFileProtection])
        } catch {
            os_log(.error, log: log, "Failed to save audit log: %{public}@", error.localizedDescription)
        }
    }

    private func loadEntries() {
        guard FileManager.default.fileExists(atPath: logFileURL.path) else { return }
        do {
            let encrypted = try Data(contentsOf: logFileURL)
            let decrypted = try EncryptedCacheService.shared.decrypt(ciphertext: encrypted)
            entries = try JSONDecoder().decode([AuditEntry].self, from: decrypted)
            reconstructLastHash()
        } catch {
            os_log(.error, log: log, "Failed to load audit log: %{public}@", error.localizedDescription)
            entries = []
            lastEntryHash = AuditLogger.genesisHash
        }
    }

    private func purgeExpired() {
        let cutoff = Date().timeIntervalSince1970 - Double(retentionDays * 86400)
        let before = entries.count
        entries.removeAll { $0.timestamp < cutoff }
        if entries.count < before {
            reconstructLastHash()
            saveEntries()
            os_log(.info, log: log, "Purged %d expired audit entries", before - entries.count)
        }
    }
}

// MARK: - EncryptedCacheService extension for raw encrypt/decrypt

@available(iOS 14.0, *)
extension EncryptedCacheService {
    /// Encrypt raw data (used by AuditLogger for file-level encryption).
    func encrypt(plaintext: Data) throws -> Data {
        let key = try getOrCreateKeyPublic()
        let sealedBox = try CryptoKit.AES.GCM.seal(plaintext, using: key)
        guard let combined = sealedBox.combined else {
            throw EncryptedCacheError.encryptionFailed
        }
        return combined
    }

    /// Decrypt raw data.
    func decrypt(ciphertext: Data) throws -> Data {
        let key = try getOrCreateKeyPublic()
        let sealedBox = try CryptoKit.AES.GCM.SealedBox(combined: ciphertext)
        return try CryptoKit.AES.GCM.open(sealedBox, using: key)
    }

    /// Public accessor for the encryption key (used by AuditLogger).
    func getOrCreateKeyPublic() throws -> CryptoKit.SymmetricKey {
        if let keyData = KeychainService.shared.retrieveData(key: KeychainService.Key.encryptionKey) {
            return CryptoKit.SymmetricKey(data: keyData)
        }
        let key = CryptoKit.SymmetricKey(size: .bits256)
        let keyData = key.withUnsafeBytes { Data($0) }
        guard KeychainService.shared.storeData(key: KeychainService.Key.encryptionKey, data: keyData) else {
            throw EncryptedCacheError.keyStorageFailed
        }
        return key
    }
}

// MARK: - AuditLogPlugin
// The Capacitor plugin bridge (AuditLogPlugin) has been extracted to
// AuditLogPlugin.swift for better code organization.
