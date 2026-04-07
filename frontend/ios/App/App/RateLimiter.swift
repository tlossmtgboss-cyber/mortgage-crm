/**
 * RateLimiter.swift
 * Perennia AI — Generic Rate Limiter
 *
 * Prevents abuse of voice commands, biometric prompts, API calls, etc.
 * Uses token bucket algorithm with configurable rate and burst.
 *
 * Usage:
 *   let limiter = RateLimiter(maxAttempts: 5, window: 60)
 *   guard limiter.tryAcquire(key: "voice_command") else { return }
 */

import Foundation
import os.log

final class RateLimiter: @unchecked Sendable {

    // MARK: - Presets

    /// Voice commands: max 10 per minute
    static let voiceCommand = RateLimiter(maxAttempts: 10, window: 60)

    /// Biometric prompts: max 5 per 30 seconds
    static let biometric = RateLimiter(maxAttempts: 5, window: 30)

    /// API calls per endpoint: max 30 per minute
    static let apiCall = RateLimiter(maxAttempts: 30, window: 60)

    /// Push notification processing: max 20 per 10 seconds
    static let pushNotification = RateLimiter(maxAttempts: 20, window: 10)

    /// Call initiation: max 3 per minute (safety)
    static let callInitiation = RateLimiter(maxAttempts: 3, window: 60)

    // MARK: - Properties

    private let maxAttempts: Int
    private let window: TimeInterval
    private var attempts: [String: [TimeInterval]] = [:]
    private let queue = DispatchQueue(label: "com.perenniaai.crm.ratelimiter")
    private let log = OSLog(subsystem: "com.perenniaai.crm", category: "RateLimiter")

    // MARK: - Init

    init(maxAttempts: Int, window: TimeInterval) {
        self.maxAttempts = maxAttempts
        self.window = window
    }

    // MARK: - Public API

    /// Try to acquire a rate limit token. Returns true if allowed, false if rate limited.
    func tryAcquire(key: String = "default") -> Bool {
        return queue.sync {
            let now = Date().timeIntervalSince1970
            let cutoff = now - window

            // Clean expired attempts
            var keyAttempts = attempts[key, default: []].filter { $0 > cutoff }

            if keyAttempts.count >= maxAttempts {
                os_log(.info, log: log, "Rate limited: %{public}@ (%d/%d in %.0fs)",
                       key, keyAttempts.count, maxAttempts, window)
                return false
            }

            keyAttempts.append(now)
            attempts[key] = keyAttempts
            return true
        }
    }

    /// Check remaining attempts without consuming one.
    func remaining(key: String = "default") -> Int {
        return queue.sync {
            let cutoff = Date().timeIntervalSince1970 - window
            let count = attempts[key, default: []].filter { $0 > cutoff }.count
            return max(0, maxAttempts - count)
        }
    }

    /// Reset rate limit for a key.
    func reset(key: String = "default") {
        queue.sync {
            attempts[key] = nil
        }
    }

    /// Reset all rate limits.
    func resetAll() {
        queue.sync {
            attempts.removeAll()
        }
    }
}
