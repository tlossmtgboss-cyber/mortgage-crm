/**
 * PinnedFetchPlugin.swift
 * Perennia AI — Certificate-Pinned HTTP Plugin for Capacitor
 *
 * Routes API calls from JavaScript through a native URLSession with SPKI
 * certificate pinning, closing the WKWebView JS fetch() pinning gap.
 *
 * JS Usage:
 *   const result = await Capacitor.Plugins.PinnedFetch.request({
 *       url: "https://api.perenniaai.com/api/v1/leads/",
 *       method: "GET",
 *       headers: { "Authorization": "Bearer xxx" }
 *   });
 *   // result = { status: 200, data: {...}, headers: {...} }
 *
 * Registration: bridge?.registerPluginInstance(PinnedFetchPlugin())
 */

import Foundation
import Capacitor

@objc(PinnedFetchPlugin)
class PinnedFetchPlugin: CAPPlugin, CAPBridgedPlugin {

    let identifier = "PinnedFetchPlugin"
    let jsName = "PinnedFetch"
    let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "request", returnType: CAPPluginReturnPromise),
    ]

    /// Pinned URLSession using the app's CertificatePinning infrastructure.
    private lazy var pinnedSession: URLSession = createPinnedURLSession()

    // MARK: - Plugin Methods

    /// Execute an HTTP request through the certificate-pinned URLSession.
    ///
    /// Parameters (from JavaScript):
    ///   - url: String (required) — full URL
    ///   - method: String — HTTP method (default: "GET")
    ///   - headers: Object — HTTP headers
    ///   - body: String — request body (JSON string)
    ///   - timeout: Double — timeout in seconds (default: 30)
    ///
    /// Returns: { status: Int, data: Any, headers: Object }
    @objc func request(_ call: CAPPluginCall) {
        guard let urlString = call.getString("url"),
              let url = URL(string: urlString) else {
            call.reject("Missing or invalid 'url' parameter")
            return
        }

        // Only allow requests to pinned domains
        guard let host = url.host,
              isPinnedDomain(host) else {
            call.reject("Domain '\(url.host ?? "")' is not in the pinned domain list")
            return
        }

        let method = call.getString("method") ?? "GET"
        let headers = call.getObject("headers") ?? [:]
        let bodyString = call.getString("body")
        let timeout = call.getDouble("timeout") ?? 30

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = timeout

        // Apply headers
        for (key, value) in headers {
            if let stringValue = value as? String {
                request.setValue(stringValue, forHTTPHeaderField: key)
            }
        }

        // Apply body
        if let bodyString = bodyString, !bodyString.isEmpty {
            request.httpBody = bodyString.data(using: .utf8)
            // Set Content-Type if not already set
            if request.value(forHTTPHeaderField: "Content-Type") == nil {
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            }
        }

        // Execute through pinned session
        let task = pinnedSession.dataTask(with: request) { data, response, error in
            if let error = error {
                // Distinguish pinning failures from network errors
                let nsError = error as NSError
                if nsError.domain == NSURLErrorDomain &&
                   (nsError.code == NSURLErrorServerCertificateUntrusted ||
                    nsError.code == NSURLErrorSecureConnectionFailed ||
                    nsError.code == NSURLErrorCancelled) {
                    call.reject("Certificate pinning validation failed for \(host)", "PINNING_FAILURE")
                    return
                }
                call.reject("Network error: \(error.localizedDescription)", "NETWORK_ERROR")
                return
            }

            guard let httpResponse = response as? HTTPURLResponse else {
                call.reject("Invalid response", "INVALID_RESPONSE")
                return
            }

            // Parse response body
            var responseData: Any = NSNull()
            if let data = data, !data.isEmpty {
                if let json = try? JSONSerialization.jsonObject(with: data) {
                    responseData = json
                } else if let text = String(data: data, encoding: .utf8) {
                    responseData = text
                }
            }

            // Collect response headers
            var responseHeaders: [String: String] = [:]
            for (key, value) in httpResponse.allHeaderFields {
                responseHeaders["\(key)"] = "\(value)"
            }

            call.resolve([
                "status": httpResponse.statusCode,
                "data": responseData,
                "headers": responseHeaders
            ])
        }
        task.resume()
    }

    // MARK: - Helpers

    /// Check if a host is in the pinned domain list.
    private func isPinnedDomain(_ host: String) -> Bool {
        let pinnedDomains = CertificatePinningConfig.pinnedDomains
        // Check exact match
        if pinnedDomains[host] != nil { return true }
        // Check subdomain match (e.g., "sub.api.perenniaai.com" matches "api.perenniaai.com" if includeSubdomains)
        for (domain, config) in pinnedDomains {
            if config.includeSubdomains && host.hasSuffix(".\(domain)") {
                return true
            }
        }
        return false
    }
}
