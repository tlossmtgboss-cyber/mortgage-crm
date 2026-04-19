/**
 * EncryptedCacheService.swift
 * Perennia AI — AES-GCM Encrypted Persistent Cache
 *
 * All cached data (dashboard, tasks, contacts, pipeline) is encrypted at rest
 * using CryptoKit AES-GCM. The encryption key is stored in the iOS Keychain.
 *
 * Supports both app-private and shared (App Group) containers for widget/extension access.
 *
 * Compliance: GLBA requires encryption of NPI at rest. This service ensures
 * all cached financial data meets that requirement.
 */

import Foundation
import os.log

#if canImport(CryptoKit)
import CryptoKit
#endif

// MARK: - EncryptedCacheService

@available(iOS 14.0, *)
final class EncryptedCacheService: @unchecked Sendable {

    // MARK: - Singleton

    static let shared = EncryptedCacheService()

    // MARK: - Properties

    private let log = OSLog(subsystem: "com.perenniaai.crm", category: "EncryptedCache")
    private let queue = DispatchQueue(label: "com.perenniaai.crm.cache.queue")
    private let keychain = KeychainService.shared
    private let maxCacheSize = 100 // Max entries before eviction

    /// UserDefaults for app-private cache.
    private let appDefaults = UserDefaults.standard

    /// UserDefaults for shared cache (widget, extension).
    private let sharedDefaults: UserDefaults? = UserDefaults(suiteName: KeychainService.sharedAccessGroup)

    // MARK: - Public API

    /// Store an encodable value encrypted in the cache.
    func store<T: Encodable>(key: String, value: T, shared: Bool = false) {
        queue.sync {
            do {
                let data = try JSONEncoder().encode(value)
                let encrypted = try encrypt(data)
                let wrapper = CacheEntry(
                    data: encrypted,
                    timestamp: Date().timeIntervalSince1970
                )
                let encoded = try JSONEncoder().encode(wrapper)
                defaults(shared: shared).set(encoded, forKey: cacheKey(key))
            } catch {
                os_log(.error, log: log, "Cache store failed for %{public}@: %{public}@", key, error.localizedDescription)
            }
        }
    }

    /// Retrieve and decrypt a cached value.
    func retrieve<T: Decodable>(key: String, type: T.Type, maxAge: TimeInterval? = nil, shared: Bool = false) -> T? {
        return queue.sync {
            guard let encoded = defaults(shared: shared).data(forKey: cacheKey(key)) else { return nil }
            do {
                let wrapper = try JSONDecoder().decode(CacheEntry.self, from: encoded)

                // Check TTL
                if let maxAge = maxAge {
                    let age = Date().timeIntervalSince1970 - wrapper.timestamp
                    if age > maxAge { return nil }
                }

                let decrypted = try decrypt(wrapper.data)
                return try JSONDecoder().decode(T.self, from: decrypted)
            } catch {
                os_log(.error, log: log, "Cache retrieve failed for %{public}@: %{public}@", key, error.localizedDescription)
                return nil
            }
        }
    }

    /// Check if a cached value exists and is not expired.
    func has(key: String, maxAge: TimeInterval? = nil, shared: Bool = false) -> Bool {
        return queue.sync {
            guard let encoded = defaults(shared: shared).data(forKey: cacheKey(key)) else { return false }
            guard let maxAge = maxAge else { return true }
            do {
                let wrapper = try JSONDecoder().decode(CacheEntry.self, from: encoded)
                return (Date().timeIntervalSince1970 - wrapper.timestamp) <= maxAge
            } catch {
                return false
            }
        }
    }

    /// Delete a cached value.
    func delete(key: String, shared: Bool = false) {
        queue.sync {
            defaults(shared: shared).removeObject(forKey: cacheKey(key))
        }
    }

    /// Clear all encrypted cache entries.
    func clearAll(shared: Bool = false) {
        queue.sync {
            let d = defaults(shared: shared)
            let prefix = "com.perenniaai.cache."
            for key in d.dictionaryRepresentation().keys where key.hasPrefix(prefix) {
                d.removeObject(forKey: key)
            }
            os_log(.info, log: log, "All encrypted cache entries cleared (shared: %{public}@)", shared ? "yes" : "no")
        }
    }

    // MARK: - Encryption

    private func encrypt(_ data: Data) throws -> Data {
        let key = try getOrCreateKey()
        let sealedBox = try AES.GCM.seal(data, using: key)
        guard let combined = sealedBox.combined else {
            throw EncryptedCacheError.encryptionFailed
        }
        return combined
    }

    private func decrypt(_ data: Data) throws -> Data {
        let key = try getOrCreateKey()
        let sealedBox = try AES.GCM.SealedBox(combined: data)
        return try AES.GCM.open(sealedBox, using: key)
    }

    private func getOrCreateKey() throws -> SymmetricKey {
        // Try to load existing key from Keychain
        if let keyData = keychain.retrieveData(key: KeychainService.Key.encryptionKey) {
            return SymmetricKey(data: keyData)
        }

        // Generate new key and store in Keychain
        let key = SymmetricKey(size: .bits256)
        let keyData = key.withUnsafeBytes { Data($0) }
        guard keychain.storeData(key: KeychainService.Key.encryptionKey, data: keyData) else {
            throw EncryptedCacheError.keyStorageFailed
        }

        os_log(.info, log: log, "Generated new AES-256 encryption key")
        return key
    }

    // MARK: - Helpers

    private func cacheKey(_ key: String) -> String {
        return "com.perenniaai.cache.\(key)"
    }

    private func defaults(shared: Bool) -> UserDefaults {
        return shared ? (sharedDefaults ?? appDefaults) : appDefaults
    }

    // MARK: - Types

    private struct CacheEntry: Codable {
        let data: Data
        let timestamp: TimeInterval
    }

    enum EncryptedCacheError: Error, LocalizedError {
        case encryptionFailed
        case decryptionFailed
        case keyStorageFailed
        case keyNotFound

        var errorDescription: String? {
            switch self {
            case .encryptionFailed: return "Failed to encrypt cache data"
            case .decryptionFailed: return "Failed to decrypt cache data"
            case .keyStorageFailed: return "Failed to store encryption key in Keychain"
            case .keyNotFound: return "Encryption key not found"
            }
        }
    }
}

// MARK: - Well-Known Cache Keys
//
// These mirror the keys used by BackgroundSyncManager to store data in
// the encrypted cache. Other consumers (widgets, extensions) should use
// these constants when reading cached data from the shared container.

extension EncryptedCacheService {
    enum CacheKey {
        static let dashboard = "carplay_dashboard_cache"
        static let tasks = "carplay_tasks_cache"
        static let contacts = "carplay_contacts_cache"
        static let rateAlerts = "carplay_rate_alerts_cache"
        static let voiceCalls = "carplay_voice_calls_cache"
        static let lastSync = "carplay_last_sync"
        static let widgetData = "widget_data"
    }
}
