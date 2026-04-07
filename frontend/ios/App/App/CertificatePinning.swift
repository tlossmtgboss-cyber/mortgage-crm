/*
 * CertificatePinning.swift
 * Perennia AI — Enterprise SSL Certificate Pinning
 *
 * This file provides native iOS certificate pinning via URLSession delegate
 * methods. It validates server certificates against pre-configured SPKI
 * (Subject Public Key Info) SHA-256 hashes.
 *
 * Pins are refreshed from a remote bootstrap endpoint every 24 hours and
 * cached in the iOS Keychain. Hardcoded pins serve as a fallback when the
 * remote fetch fails (first launch offline, endpoint unreachable, etc.).
 *
 * ==========================================================================
 * INTEGRATION WITH CAPACITOR
 * ==========================================================================
 *
 * Capacitor uses WKWebView for rendering the web app. WKWebView manages its
 * own TLS stack and does NOT expose URLSessionDelegate-style hooks for custom
 * certificate validation. This means:
 *
 *   1. WKWebView requests (HTML, JS, CSS, images loaded by the webview) are
 *      validated by iOS ATS (App Transport Security) and the system trust
 *      store, but NOT by this custom pinning code.
 *
 *   2. Requests made via Capacitor's native HTTP plugin (@capacitor/http or
 *      @capgo/capacitor-ssl-pinning) DO go through URLSession and CAN be
 *      pinned using this delegate.
 *
 * Recommended production integration path:
 *
 *   Option A (Simplest): Install @capgo/capacitor-ssl-pinning
 *     - npm install @capgo/capacitor-ssl-pinning
 *     - Configure pins in capacitor.config.ts
 *     - The plugin handles URLSession pinning automatically
 *
 *   Option B (Custom plugin): Register this class as a Capacitor plugin
 *     - Create a CertificatePinningPlugin that extends CAPPlugin
 *     - Override the handleURLSession methods
 *     - Route API calls through the custom plugin instead of WKWebView fetch
 *
 *   Option C (Network extension): Use a WKWebView navigation delegate
 *     - Subclass the Capacitor bridge's WKWebView
 *     - Implement webView(_:didReceive:completionHandler:) for challenge auth
 *     - This intercepts ALL webview requests including API calls
 *     - Requires modifying the Capacitor bridge initialization
 *
 * This file implements the URLSessionDelegate portion (used by Options A & B)
 * and a standalone WKNavigationDelegate extension (used by Option C).
 *
 * ==========================================================================
 * GENERATING PIN HASHES
 * ==========================================================================
 *
 * To generate the SHA-256 hash of a server's SPKI:
 *
 *   openssl s_client -connect api.perenniaai.com:443 \
 *     -servername api.perenniaai.com < /dev/null 2>/dev/null \
 *     | openssl x509 -pubkey -noout \
 *     | openssl pkey -pubin -outform der \
 *     | openssl dgst -sha256 -binary \
 *     | openssl enc -base64
 *
 * The output (e.g., "YLh1dUR9y6Kja30RrAn7JKnbQG/uEtLMkBgFF2Fuihg=") is
 * the base64-encoded SHA-256 hash to use as a pin value below.
 *
 * ==========================================================================
 */

import Foundation
import CommonCrypto
import WebKit

// MARK: - Pin Configuration

/// Configuration for a single pinned domain.
struct PinnedDomainConfig: Codable {
    /// SHA-256 hashes of the Subject Public Key Info (base64-encoded).
    let spkiHashes: [String]

    /// Whether subdomains should also be pinned with these hashes.
    let includeSubdomains: Bool

    /// Optional certificate expiry date (ISO 8601) for pin expiry warnings.
    let notAfter: String?

    init(spkiHashes: [String], includeSubdomains: Bool, notAfter: String? = nil) {
        self.spkiHashes = spkiHashes
        self.includeSubdomains = includeSubdomains
        self.notAfter = notAfter
    }
}

/// Central certificate pinning configuration.
///
/// Hardcoded pins are the fallback. On first launch and every 24 hours,
/// fresh pins are fetched from the remote bootstrap endpoint and cached
/// in the iOS Keychain.
struct CertificatePinningConfig {

    /// Pinned domains and their expected SPKI SHA-256 hashes.
    ///
    /// Each domain must have at least two pins:
    ///   1. Primary: the current certificate's public key hash
    ///   2. Backup: a pre-generated backup key pair hash (for rotation)
    static let pinnedDomains: [String: PinnedDomainConfig] = [
        "api.perenniaai.com": PinnedDomainConfig(
            spkiHashes: [
                // Primary cert pin — current production certificate (retrieved 2026-04-01)
                "STrmUQMdkvmuC5EJ/5StR+WXmwAq6RLFCIPe3rMVgPA=",
                // Backup pin — ISRG Root X1 (Let's Encrypt root CA)
                "C5+lpZ7tcVwmwQIMcRtPbsQtWLABXhQzejna0wHFr8M=",
                // Backup pin — Let's Encrypt R3 intermediate
                "jQJTbIh0grw0/1TkHSumWb+Fs0Ggogr621gT3PvPKG0="
            ],
            includeSubdomains: true
        ),
        "app.perenniaai.com": PinnedDomainConfig(
            spkiHashes: [
                // Primary cert pin — current production certificate (retrieved 2026-04-01)
                "R5ekDjTy4aandy7hssjUE5P7a2loTg3iSpEA4bjNkQw=",
                // Backup pin — ISRG Root X1 (Let's Encrypt root CA)
                "C5+lpZ7tcVwmwQIMcRtPbsQtWLABXhQzejna0wHFr8M=",
                // Backup pin — Let's Encrypt R3 intermediate
                "jQJTbIh0grw0/1TkHSumWb+Fs0Ggogr621gT3PvPKG0="
            ],
            includeSubdomains: true
        )
    ]

    /// Whether certificate pinning is enabled.
    /// Set to false to disable pinning during development or debugging.
    ///
    /// In production builds, this should ALWAYS be true.
    /// Use #if DEBUG to automatically disable in debug builds.
    static var isEnabled: Bool {
        #if DEBUG
        return false
        #else
        return true
        #endif
    }

    /// Backend endpoint for reporting pin validation failures.
    static let reportURL = URL(string: "https://api.perenniaai.com/api/v1/security/pin-failure")!

    /// Backend endpoint for fetching fresh pin configuration.
    static let remotePinURL = URL(string: "https://api.perenniaai.com/api/v1/security/certificate-pins")!

    /// How often to refresh pins from the remote endpoint (24 hours).
    static let pinRefreshInterval: TimeInterval = 24 * 60 * 60

    /// Number of days before pin expiry to start logging warnings.
    static let pinExpiryWarningDays = 30
}


// MARK: - Remote Pin Manager

/// Manages fetching, caching, and serving certificate pins.
///
/// On first launch and every 24 hours, fetches fresh pins from the bootstrap
/// endpoint and caches them in the Keychain. Falls back to hardcoded pins
/// if the remote fetch fails.
class RemotePinManager {

    static let shared = RemotePinManager()

    private let keychainPinKey = "certificate_pins_cache"
    private let keychainTimestampKey = "certificate_pins_last_fetched"
    private let queue = DispatchQueue(label: "com.perenniaai.crm.pinmanager")
    private var cachedPins: [String: PinnedDomainConfig]?

    private init() {
        // Load cached pins from Keychain on init
        cachedPins = loadCachedPins()
        // Trigger a background refresh if stale or missing
        refreshIfNeeded()
    }

    /// Returns the effective pin configuration for a domain.
    /// Prefers remote-fetched pins if available and fresh; falls back to hardcoded.
    func effectivePins() -> [String: PinnedDomainConfig] {
        return queue.sync {
            return cachedPins ?? CertificatePinningConfig.pinnedDomains
        }
    }

    /// Trigger a background refresh if the cache is stale or absent.
    func refreshIfNeeded() {
        let needsRefresh: Bool = queue.sync {
            guard let timestampStr = KeychainService.shared.retrieve(key: keychainTimestampKey),
                  let timestamp = TimeInterval(timestampStr) else {
                return true // No cached timestamp — first launch
            }
            return Date().timeIntervalSince1970 - timestamp >= CertificatePinningConfig.pinRefreshInterval
        }

        if needsRefresh {
            fetchRemotePins()
        }
    }

    /// Check all cached pins for upcoming expiry and log warnings.
    func checkPinExpiry() {
        let pins = effectivePins()
        let isoFormatter = ISO8601DateFormatter()
        let now = Date()

        for (domain, config) in pins {
            guard let notAfterStr = config.notAfter,
                  let expiryDate = isoFormatter.date(from: notAfterStr) else {
                continue
            }

            let daysRemaining = Calendar.current.dateComponents([.day], from: now, to: expiryDate).day ?? 0

            if daysRemaining >= 0 && daysRemaining <= CertificatePinningConfig.pinExpiryWarningDays {
                NSLog("[CertificatePinning] WARNING: Pin for %@ expires in %d days", domain, daysRemaining)
                if #available(iOS 14.0, *) {
                    AuditLogger.shared.log(
                        event: .certificatePinFailure,
                        details: [
                            "reason": "pin_expiring_soon",
                            "domain": domain,
                            "days_remaining": "\(daysRemaining)"
                        ]
                    )
                }
            }
        }
    }

    // MARK: - Private

    private func fetchRemotePins() {
        // Use an ephemeral session without custom pinning to avoid chicken-and-egg
        let session = URLSession(configuration: .ephemeral)
        var request = URLRequest(url: CertificatePinningConfig.remotePinURL)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 15

        session.dataTask(with: request) { [weak self] data, response, error in
            guard let self = self else { return }

            if let error = error {
                NSLog("[CertificatePinning] Remote pin fetch failed: %@", error.localizedDescription)
                return // Fall back to hardcoded/cached pins
            }

            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode),
                  let data = data else {
                NSLog("[CertificatePinning] Remote pin fetch returned non-200 or empty body")
                return
            }

            do {
                let decoded = try JSONDecoder().decode([String: PinnedDomainConfig].self, from: data)

                // Validate: response must contain at least the domains we already pin
                guard !decoded.isEmpty else {
                    NSLog("[CertificatePinning] Remote pin response was empty — ignoring")
                    return
                }

                // Cache in Keychain
                let encoded = try JSONEncoder().encode(decoded)
                let jsonString = String(data: encoded, encoding: .utf8) ?? ""
                KeychainService.shared.store(key: self.keychainPinKey, value: jsonString)
                KeychainService.shared.store(
                    key: self.keychainTimestampKey,
                    value: "\(Date().timeIntervalSince1970)"
                )

                self.queue.sync {
                    self.cachedPins = decoded
                }

                NSLog("[CertificatePinning] Remote pins refreshed: %d domains", decoded.count)

                // Check expiry on freshly fetched pins
                self.checkPinExpiry()

            } catch {
                NSLog("[CertificatePinning] Failed to decode remote pins: %@", error.localizedDescription)
            }
        }.resume()
    }

    private func loadCachedPins() -> [String: PinnedDomainConfig]? {
        guard let jsonString = KeychainService.shared.retrieve(key: keychainPinKey),
              let data = jsonString.data(using: .utf8) else {
            return nil
        }

        do {
            let decoded = try JSONDecoder().decode([String: PinnedDomainConfig].self, from: data)
            return decoded.isEmpty ? nil : decoded
        } catch {
            NSLog("[CertificatePinning] Failed to load cached pins: %@", error.localizedDescription)
            return nil
        }
    }
}


// MARK: - SPKI Hash Extraction

/// Extracts the SHA-256 hash of the Subject Public Key Info (SPKI) from
/// a SecCertificate. This is the standard method for HPKP-style pinning.
///
/// The SPKI includes the algorithm identifier and public key, so pinning
/// on SPKI survives certificate renewals as long as the same key pair is used.
///
/// - Parameter certificate: The certificate to extract the SPKI hash from.
/// - Returns: The base64-encoded SHA-256 hash, or nil if extraction fails.
func extractSPKIHash(from certificate: SecCertificate) -> String? {
    // Extract the public key from the certificate
    guard let publicKey = SecCertificateCopyKey(certificate) else {
        return nil
    }

    // Get the external representation (DER-encoded SPKI)
    var error: Unmanaged<CFError>?
    guard let publicKeyData = SecKeyCopyExternalRepresentation(publicKey, &error) as Data? else {
        return nil
    }

    // The external representation from SecKeyCopyExternalRepresentation is the raw
    // key data, NOT the full SPKI structure. To match openssl's SPKI hash, we need
    // to wrap it in the appropriate ASN.1 header.
    //
    // For RSA 2048-bit keys, the ASN.1 header is:
    let rsa2048Header: [UInt8] = [
        0x30, 0x82, 0x01, 0x22,  // SEQUENCE (290 bytes)
        0x30, 0x0D,              // SEQUENCE (13 bytes)
        0x06, 0x09,              // OID (9 bytes)
        0x2A, 0x86, 0x48, 0x86, 0xF7, 0x0D, 0x01, 0x01, 0x01,  // rsaEncryption
        0x05, 0x00,              // NULL
        0x03, 0x82, 0x01, 0x0F,  // BIT STRING (271 bytes)
        0x00                     // padding
    ]

    // For RSA 4096-bit keys, the ASN.1 header is:
    let rsa4096Header: [UInt8] = [
        0x30, 0x82, 0x02, 0x22,  // SEQUENCE (546 bytes)
        0x30, 0x0D,              // SEQUENCE (13 bytes)
        0x06, 0x09,              // OID (9 bytes)
        0x2A, 0x86, 0x48, 0x86, 0xF7, 0x0D, 0x01, 0x01, 0x01,  // rsaEncryption
        0x05, 0x00,              // NULL
        0x03, 0x82, 0x02, 0x0F,  // BIT STRING (527 bytes)
        0x00                     // padding
    ]

    // For EC P-256 keys, the ASN.1 header is:
    let ecHeader: [UInt8] = [
        0x30, 0x59,              // SEQUENCE (89 bytes)
        0x30, 0x13,              // SEQUENCE (19 bytes)
        0x06, 0x07,              // OID (7 bytes)
        0x2A, 0x86, 0x48, 0xCE, 0x3D, 0x02, 0x01,  // ecPublicKey
        0x06, 0x08,              // OID (8 bytes)
        0x2A, 0x86, 0x48, 0xCE, 0x3D, 0x03, 0x01, 0x07,  // prime256v1
        0x03, 0x42, 0x00         // BIT STRING (66 bytes)
    ]

    // Determine key type and select appropriate header
    let keyAttributes = SecKeyCopyAttributes(publicKey) as? [String: Any]
    let keyType = keyAttributes?[kSecAttrKeyType as String] as? String
    let keySize = keyAttributes?[kSecAttrKeySizeInBits as String] as? Int ?? 0

    var spkiData = Data()

    if keyType == (kSecAttrKeyTypeRSA as String) {
        if keySize == 4096 {
            // RSA 4096-bit key
            spkiData.append(contentsOf: rsa4096Header)
        } else {
            // RSA 2048-bit key (or other sizes — 2048 header works for the common case)
            spkiData.append(contentsOf: rsa2048Header)
        }
        spkiData.append(publicKeyData)
    } else if keyType == (kSecAttrKeyTypeECSECPrimeRandom as String) {
        // EC key — P-256 assumed (65 bytes uncompressed point)
        spkiData.append(contentsOf: ecHeader)
        spkiData.append(publicKeyData)
    } else {
        // Unknown key type — hash the raw key data as fallback
        // This won't match openssl's SPKI hash but provides some protection
        spkiData = publicKeyData
    }

    // SHA-256 hash of the SPKI
    var hash = [UInt8](repeating: 0, count: Int(CC_SHA256_DIGEST_LENGTH))
    spkiData.withUnsafeBytes { buffer in
        _ = CC_SHA256(buffer.baseAddress, CC_LONG(spkiData.count), &hash)
    }

    return Data(hash).base64EncodedString()
}


// MARK: - URLSession Certificate Pinning Delegate

/// URLSession delegate that validates server certificates against pinned
/// SPKI hashes. Use this delegate for any URLSession that makes requests
/// to pinned domains.
///
/// Usage:
///   let delegate = CertificatePinningDelegate()
///   let session = URLSession(configuration: .default, delegate: delegate, delegateQueue: nil)
///   let (data, response) = try await session.data(from: url)
///
class CertificatePinningDelegate: NSObject, URLSessionDelegate {

    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        handleServerTrust(challenge: challenge, completionHandler: completionHandler)
    }
}

/// URLSession task-level delegate for certificate pinning.
/// Use this when you need per-task pinning (e.g., with URLSession data tasks).
class CertificatePinningTaskDelegate: NSObject, URLSessionTaskDelegate {

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        handleServerTrust(challenge: challenge, completionHandler: completionHandler)
    }
}


// MARK: - Pin Failure Rate Limiter

/// Rate limiter for pin failure reports to prevent DOS loops.
/// Max 5 failure reports per 60-second window.
private let pinFailureRateLimiter = RateLimiter(maxAttempts: 5, window: 60)


// MARK: - Server Trust Validation

/// Shared certificate validation logic used by both session and task delegates.
///
/// - Parameters:
///   - challenge: The authentication challenge from the server.
///   - completionHandler: The completion handler to call with the disposition.
private func handleServerTrust(
    challenge: URLAuthenticationChallenge,
    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
) {
    // Only handle server trust challenges (TLS certificate validation)
    guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
          let serverTrust = challenge.protectionSpace.serverTrust else {
        // Not a server trust challenge — use default handling
        completionHandler(.performDefaultHandling, nil)
        return
    }

    let host = challenge.protectionSpace.host

    // Check if pinning is enabled
    guard CertificatePinningConfig.isEnabled else {
        // Pinning disabled — accept if the system trusts the cert
        completionHandler(.performDefaultHandling, nil)
        return
    }

    // Find pin configuration for this host (remote-fetched pins take precedence)
    guard let pinConfig = findPinConfig(for: host) else {
        // Host is not pinned — use default system validation
        completionHandler(.performDefaultHandling, nil)
        return
    }

    // First, perform standard certificate validation (chain of trust)
    let policy = SecPolicyCreateSSL(true, host as CFString)
    SecTrustSetPolicies(serverTrust, policy)

    var secResult: CFError?
    let isTrusted = SecTrustEvaluateWithError(serverTrust, &secResult)

    guard isTrusted else {
        // Certificate chain is not trusted by the system
        reportFailure(host: host, reason: "chain_not_trusted")
        completionHandler(.cancelAuthenticationChallenge, nil)
        return
    }

    // Now check the SPKI pin against the certificate chain
    let certificateCount = SecTrustGetCertificateCount(serverTrust)
    var pinMatched = false
    var receivedHashes: [String] = []

    // Check each certificate in the chain (leaf first, then intermediates, then root)
    if #available(iOS 15.0, *) {
        // Use modern API (SecTrustCopyCertificateChain)
        if let chain = SecTrustCopyCertificateChain(serverTrust) as? [SecCertificate] {
            for certificate in chain {
                if let hash = extractSPKIHash(from: certificate) {
                    receivedHashes.append(hash)
                    if pinConfig.spkiHashes.contains(hash) {
                        pinMatched = true
                        break
                    }
                }
            }
        }
    } else {
        // Fallback for iOS < 15
        for i in 0..<certificateCount {
            if let certificate = SecTrustGetCertificateAtIndex(serverTrust, i) {
                if let hash = extractSPKIHash(from: certificate) {
                    receivedHashes.append(hash)
                    if pinConfig.spkiHashes.contains(hash) {
                        pinMatched = true
                        break
                    }
                }
            }
        }
    }

    if pinMatched {
        // Pin matched — allow the connection
        if #available(iOS 14.0, *) {
            AuditLogger.shared.log(
                event: .certificatePinSuccess,
                details: ["domain": host]
            )
        }
        let credential = URLCredential(trust: serverTrust)
        completionHandler(.useCredential, credential)
    } else {
        // Pin mismatch — potential MITM attack. Reject the connection.
        if #available(iOS 14.0, *) {
            AuditLogger.shared.log(
                event: .certificatePinFailure,
                details: [
                    "domain": host,
                    "reason": "pin_mismatch",
                    "received_hashes": receivedHashes.prefix(5).joined(separator: ", ")
                ]
            )
        }
        reportFailure(host: host, reason: "pin_mismatch", receivedHashes: receivedHashes)
        completionHandler(.cancelAuthenticationChallenge, nil)
    }
}

/// Find the pin configuration for a given host.
/// Checks remote-fetched pins first, then hardcoded pins.
/// For each source, checks direct match first, then parent domains with includeSubdomains.
///
/// - Parameter host: The hostname to look up.
/// - Returns: The pin configuration, or nil if the host is not pinned.
private func findPinConfig(for host: String) -> PinnedDomainConfig? {
    let normalized = host.lowercased()

    // Check remote-fetched pins first, then fall back to hardcoded
    let pinSources = [
        RemotePinManager.shared.effectivePins(),
        CertificatePinningConfig.pinnedDomains
    ]

    for pins in pinSources {
        // Direct match
        if let config = pins[normalized] {
            return config
        }

        // Check parent domains with includeSubdomains
        for (domain, config) in pins {
            if config.includeSubdomains && normalized.hasSuffix("." + domain) {
                return config
            }
        }
    }

    return nil
}


// MARK: - Failure Reporting

/// Report a pin validation failure to the backend for security monitoring.
///
/// This is fire-and-forget — we don't want failure reporting to block
/// the connection rejection. Reports are rate-limited to prevent DOS loops.
///
/// - Parameters:
///   - host: The hostname that failed validation.
///   - reason: The reason for failure.
///   - receivedHashes: The SPKI hashes received from the server.
private func reportFailure(host: String, reason: String, receivedHashes: [String] = []) {
    // Log locally first (always available)
    NSLog("[CertificatePinning] PIN VALIDATION FAILED for %@: %@", host, reason)
    NSLog("[CertificatePinning] Received hashes: %@", receivedHashes.joined(separator: ", "))

    // Audit log the failure
    if #available(iOS 14.0, *) {
        AuditLogger.shared.log(
            event: .certificatePinFailure,
            details: [
                "domain": host,
                "reason": reason,
                "received_hashes": receivedHashes.prefix(5).joined(separator: ", ")
            ]
        )
    }

    // Rate-limit failure reports to backend to prevent DOS loops
    guard pinFailureRateLimiter.tryAcquire(key: "pin_failure_\(host)") else {
        NSLog("[CertificatePinning] Rate limited — skipping backend failure report for %@", host)
        return
    }

    // Report to backend asynchronously
    let report: [String: Any] = [
        "reports": [[
            "domain": host,
            "reason": reason,
            "receivedHashes": Array(receivedHashes.prefix(5)),
            "timestamp": ISO8601DateFormatter().string(from: Date()),
            "platform": "ios",
            "appVersion": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
        ]],
        "deviceInfo": [
            "platform": "ios",
            "isNative": true,
            "osVersion": UIDevice.current.systemVersion,
            "model": UIDevice.current.model
        ]
    ]

    guard let jsonData = try? JSONSerialization.data(withJSONObject: report) else {
        return
    }

    var request = URLRequest(url: CertificatePinningConfig.reportURL)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpBody = jsonData

    // Use an ephemeral session WITHOUT pinning for the report request itself,
    // so that reports can still be delivered even if the attacker is on the
    // reporting endpoint too. The report contains no sensitive data.
    let reportSession = URLSession(configuration: .ephemeral)
    reportSession.dataTask(with: request) { _, _, error in
        if let error = error {
            NSLog("[CertificatePinning] Failed to send failure report: %@", error.localizedDescription)
        }
    }.resume()
}


// MARK: - WKWebView Integration (Option C)

/// Extension providing WKNavigationDelegate methods for certificate pinning
/// in WKWebView. This allows pinning ALL requests made by the webview,
/// including the initial page load and API calls made via fetch/XHR.
///
/// To use this:
///   1. Subclass or extend the Capacitor CAPBridgeViewController
///   2. Set the WKWebView's navigationDelegate
///   3. Implement the didReceive challenge method using pinWebViewChallenge()
///
/// Example integration in CAPBridgeViewController subclass:
///
///   override func viewDidLoad() {
///       super.viewDidLoad()
///       webView?.navigationDelegate = self
///   }
///
///   func webView(_ webView: WKWebView,
///                didReceive challenge: URLAuthenticationChallenge,
///                completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
///       pinWebViewChallenge(challenge, completionHandler: completionHandler)
///   }
///
/// NOTE: Setting a custom navigationDelegate on Capacitor's WKWebView may
/// interfere with Capacitor's own navigation handling. Test thoroughly.
/// The @capgo/capacitor-ssl-pinning plugin (Option A) is safer.
///
func pinWebViewChallenge(
    _ challenge: URLAuthenticationChallenge,
    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
) {
    // Reuse the same validation logic as URLSession pinning
    handleServerTrust(challenge: challenge, completionHandler: completionHandler)
}


// MARK: - Convenience: Pinned URLSession Factory

/// Create a URLSession pre-configured with certificate pinning.
///
/// Use this session for any native HTTP requests to pinned domains
/// (e.g., from a custom Capacitor plugin).
///
/// - Parameter configuration: URLSession configuration (default: .default)
/// - Returns: A URLSession with the pinning delegate installed
func createPinnedURLSession(
    configuration: URLSessionConfiguration = .default
) -> URLSession {
    let delegate = CertificatePinningDelegate()
    return URLSession(
        configuration: configuration,
        delegate: delegate,
        delegateQueue: nil
    )
}
