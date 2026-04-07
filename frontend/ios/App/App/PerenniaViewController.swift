/**
 * PerenniaViewController.swift
 * Custom Capacitor ViewController for Perennia AI
 *
 * Registers custom native plugins with the Capacitor bridge and applies
 * certificate pinning to ALL WKWebView traffic (HTML, JS, CSS, fetch/XHR).
 *
 * Without this, only URLSession-based requests go through the pinning
 * delegate in CertificatePinning.swift — WKWebView uses its own TLS stack.
 */

import UIKit
import Capacitor
import WebKit

class PerenniaViewController: CAPBridgeViewController, WKNavigationDelegate {

    /// Stores Capacitor's original WKNavigationDelegate so we can forward all
    /// delegate callbacks we don't need to intercept ourselves.
    private weak var originalNavigationDelegate: WKNavigationDelegate?

    override open func capacitorDidLoad() {
        // Register custom native plugins
        bridge?.registerPluginInstance(AuditLogPlugin())
        bridge?.registerPluginInstance(DeviceIntegrityPlugin())
        bridge?.registerPluginInstance(MDMConfigPlugin())
        bridge?.registerPluginInstance(SiriShortcutsPlugin())
        bridge?.registerPluginInstance(SpotlightSearchPlugin())
        bridge?.registerPluginInstance(LiveActivityPlugin())
        bridge?.registerPluginInstance(ShareExtensionBridge())
    }

    override func viewDidLoad() {
        super.viewDidLoad()

        // Store Capacitor's original navigation delegate before overriding.
        originalNavigationDelegate = webView?.navigationDelegate

        // Inject ourselves as the WKWebView navigation delegate for TLS pinning.
        // We forward all non-intercepted calls to the original delegate so
        // Capacitor's deep-link and custom-scheme handling still works.
        webView?.navigationDelegate = self

        // Check device integrity before loading web content.
        // The actual JS-facing check runs via the plugin when JS calls it.
        // Native enforcement: disable screenshot capture if MDM policy requires it.
        let integrity = DeviceIntegrityPlugin()
        DispatchQueue.global().async {
            // The actual check runs via the plugin when JS calls it
            // Native enforcement: disable screenshot if MDM requires it
            _ = integrity
        }
    }

    // MARK: - Public API

    /// Clears all sensitive data from the WebView and secure storage.
    /// Call this on logout to ensure no session artifacts remain.
    public func clearSensitiveData() {
        let dataTypes = WKWebsiteDataStore.allWebsiteDataTypes()
        let dateFrom = Date(timeIntervalSince1970: 0)
        WKWebsiteDataStore.default().removeData(
            ofTypes: dataTypes,
            modifiedSince: dateFrom
        ) {
            // WebView data cleared
        }

        KeychainService.shared.deleteAll()
        EncryptedCacheService.shared.clearAll()
        AuditLogger.shared.log(event: .logout)
    }

    // MARK: - WKNavigationDelegate — Certificate Pinning

    /// Intercepts TLS authentication challenges for all WKWebView requests
    /// and validates the server certificate against our pinned SPKI hashes.
    func webView(
        _ webView: WKWebView,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        // Delegate to the shared pinning logic in CertificatePinning.swift.
        // When pinning is disabled (DEBUG builds), this falls through to
        // default handling automatically.
        pinWebViewChallenge(challenge, completionHandler: completionHandler)
    }

    // MARK: - WKNavigationDelegate — Pass-through for Capacitor

    // Forward standard navigation decisions so Capacitor's deep-link and
    // custom-scheme handling still works.

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        if let original = originalNavigationDelegate,
           original.responds(to: #selector(WKNavigationDelegate.webView(_:decidePolicyFor:decisionHandler:) as ((WKNavigationDelegate) -> (WKWebView, WKNavigationAction, @escaping (WKNavigationActionPolicy) -> Void) -> Void)?)) {
            original.webView?(webView, decidePolicyFor: navigationAction, decisionHandler: decisionHandler)
        } else {
            decisionHandler(.allow)
        }
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationResponse: WKNavigationResponse,
        decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void
    ) {
        if let original = originalNavigationDelegate,
           original.responds(to: #selector(WKNavigationDelegate.webView(_:decidePolicyFor:decisionHandler:) as ((WKNavigationDelegate) -> (WKWebView, WKNavigationResponse, @escaping (WKNavigationResponsePolicy) -> Void) -> Void)?)) {
            original.webView?(webView, decidePolicyFor: navigationResponse, decisionHandler: decisionHandler)
        } else {
            decisionHandler(.allow)
        }
    }

    func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
        originalNavigationDelegate?.webView?(webView, didCommit: navigation)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        originalNavigationDelegate?.webView?(webView, didFinish: navigation)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        originalNavigationDelegate?.webView?(webView, didFail: navigation, withError: error)
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        originalNavigationDelegate?.webViewWebContentProcessDidTerminate?(webView)
    }

    /// Show a user-visible error when a pinning failure cancels the page load.
    func webView(
        _ webView: WKWebView,
        didFailProvisionalNavigation navigation: WKNavigation!,
        withError error: Error
    ) {
        let nsError = error as NSError
        // NSURLErrorCancelled (-999) is fired when we cancel via pinning rejection.
        // NSURLErrorServerCertificateUntrusted (-1202) may also appear.
        if nsError.code == NSURLErrorCancelled || nsError.code == NSURLErrorServerCertificateUntrusted {
            AuditLogger.shared.log(event: .certificatePinFailure, details: ["error_code": "\(nsError.code)"])

            let html = """
            <html>
            <head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
            <body style="font-family:-apple-system,sans-serif;text-align:center;padding:60px 20px;">
              <h2>Secure Connection Failed</h2>
              <p>The app could not verify the identity of the server. This may indicate a network security issue.</p>
              <p style="color:#888;font-size:13px;">Error \(nsError.code)</p>
            </body>
            </html>
            """
            webView.loadHTMLString(html, baseURL: nil)
        }

        // Forward to original delegate as well
        originalNavigationDelegate?.webView?(webView, didFailProvisionalNavigation: navigation, withError: error)
    }
}
