/**
 * KeychainService.swift
 * Perennia AI — Secure Token & Credential Storage
 *
 * Replaces all UserDefaults-based token storage with iOS Keychain.
 * Supports shared access group for widget and share extension.
 *
 * Security properties:
 *   - kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly (survives lock, not backup)
 *   - Shared access group: group.com.perenniaai.crm
 *   - Thread-safe via serial dispatch queue
 *   - Automatic cleanup of legacy UserDefaults tokens on first use
 */

import Foundation
import Security
import os.log

// MARK: - KeychainService

final class KeychainService: @unchecked Sendable {

    // MARK: - Singleton

    static let shared = KeychainService()

    // MARK: - Constants

    static let sharedAccessGroup = "group.com.perenniaai.crm"
    private static let serviceName = "com.perenniaai.crm.keychain"

    private let log = OSLog(subsystem: "com.perenniaai.crm", category: "Keychain")
    private let queue = DispatchQueue(label: "com.perenniaai.crm.keychain.queue")

    // Well-known keys
    enum Key {
        static let accessToken = "access_token"
        static let refreshToken = "refresh_token"
        static let userEmail = "user_email"
        static let deviceId = "device_id"
        static let encryptionKey = "encryption_key"
    }

    // Legacy UserDefaults keys to migrate from
    private let legacyKeys = [
        "CapacitorStorage.token",
        "CapacitorStorage.access_token",
        "CapacitorStorage.auth_token",
        "CapacitorStorage.refresh_token"
    ]

    // MARK: - Init

    private init() {
        migrateLegacyTokens()
    }

    // MARK: - Public API

    /// Store a string value in the Keychain.
    /// - Parameters:
    ///   - key: The key to store under.
    ///   - value: The string value to store.
    ///   - shared: If true, uses the shared access group (visible to extensions).
    /// - Returns: True if stored successfully.
    @discardableResult
    func store(key: String, value: String, shared: Bool = false) -> Bool {
        guard let data = value.data(using: .utf8) else { return false }
        return storeData(key: key, data: data, shared: shared)
    }

    /// Store raw data in the Keychain.
    @discardableResult
    func storeData(key: String, data: Data, shared: Bool = false) -> Bool {
        return queue.sync {
            // Delete existing item first
            let deleteQuery = baseQuery(key: key, shared: shared)
            SecItemDelete(deleteQuery as CFDictionary)

            var addQuery = baseQuery(key: key, shared: shared)
            addQuery[kSecValueData as String] = data
            addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly

            let status = SecItemAdd(addQuery as CFDictionary, nil)
            if status != errSecSuccess {
                os_log(.error, log: log, "Keychain store failed for key %{public}@: %{public}d", key, status)
            }
            return status == errSecSuccess
        }
    }

    /// Retrieve a string value from the Keychain.
    func retrieve(key: String, shared: Bool = false) -> String? {
        guard let data = retrieveData(key: key, shared: shared) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    /// Retrieve raw data from the Keychain.
    func retrieveData(key: String, shared: Bool = false) -> Data? {
        return queue.sync {
            var query = baseQuery(key: key, shared: shared)
            query[kSecReturnData as String] = true
            query[kSecMatchLimit as String] = kSecMatchLimitOne

            var result: AnyObject?
            let status = SecItemCopyMatching(query as CFDictionary, &result)

            if status == errSecSuccess, let data = result as? Data {
                return data
            }
            return nil
        }
    }

    /// Delete a value from the Keychain.
    @discardableResult
    func delete(key: String, shared: Bool = false) -> Bool {
        return queue.sync {
            let query = baseQuery(key: key, shared: shared)
            let status = SecItemDelete(query as CFDictionary)
            return status == errSecSuccess || status == errSecItemNotFound
        }
    }

    /// Delete all Perennia keychain items (logout).
    func deleteAll() {
        queue.sync {
            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: Self.serviceName
            ]
            SecItemDelete(query as CFDictionary)

            // Also clear shared access group
            let sharedQuery: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: Self.serviceName,
                kSecAttrAccessGroup as String: Self.sharedAccessGroup
            ]
            SecItemDelete(sharedQuery as CFDictionary)

            os_log(.info, log: log, "All keychain items deleted")
        }
    }

    // MARK: - Convenience Properties

    /// The current auth token, stored securely in Keychain.
    /// Also synced to shared access group for widget/extension access.
    var authToken: String? {
        get { retrieve(key: Key.accessToken) ?? retrieve(key: Key.accessToken, shared: true) }
        set {
            if let token = newValue {
                store(key: Key.accessToken, value: token)
                store(key: Key.accessToken, value: token, shared: true)
            } else {
                delete(key: Key.accessToken)
                delete(key: Key.accessToken, shared: true)
            }
        }
    }

    /// The refresh token for session renewal.
    var refreshToken: String? {
        get { retrieve(key: Key.refreshToken) }
        set {
            if let token = newValue {
                store(key: Key.refreshToken, value: token)
            } else {
                delete(key: Key.refreshToken)
            }
        }
    }

    // MARK: - JWT Validation

    /// Check if the stored auth token is expired (with 60-second buffer).
    var isTokenExpired: Bool {
        guard let token = authToken else { return true }
        return Self.isJWTExpired(token, buffer: 60)
    }

    /// Parse JWT expiration without validating signature (client-side convenience only).
    static func isJWTExpired(_ jwt: String, buffer: TimeInterval = 60) -> Bool {
        let parts = jwt.split(separator: ".")
        guard parts.count >= 2 else { return true }

        var base64 = String(parts[1])
        // Pad to multiple of 4
        while base64.count % 4 != 0 { base64.append("=") }

        guard let data = Data(base64Encoded: base64),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let exp = json["exp"] as? TimeInterval else {
            return true
        }

        return Date().timeIntervalSince1970 >= (exp - buffer)
    }

    // MARK: - Private

    private func baseQuery(key: String, shared: Bool) -> [String: Any] {
        var query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: Self.serviceName,
            kSecAttrAccount as String: key
        ]
        if shared {
            query[kSecAttrAccessGroup as String] = Self.sharedAccessGroup
        }
        return query
    }

    /// One-time migration from legacy UserDefaults token storage.
    private func migrateLegacyTokens() {
        var migrated = false
        for legacyKey in legacyKeys {
            if let token = UserDefaults.standard.string(forKey: legacyKey), !token.isEmpty {
                if retrieve(key: Key.accessToken) == nil {
                    store(key: Key.accessToken, value: token)
                    store(key: Key.accessToken, value: token, shared: true)
                    migrated = true
                }
                // Clear legacy storage
                UserDefaults.standard.removeObject(forKey: legacyKey)
            }
        }
        if migrated {
            os_log(.info, log: log, "Migrated legacy tokens from UserDefaults to Keychain")
        }
    }
}
