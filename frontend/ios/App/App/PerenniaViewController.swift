/**
 * PerenniaViewController.swift
 * Custom Capacitor ViewController for Perennia AI
 *
 * Registers custom native plugins with the Capacitor bridge.
 *
 * Certificate pinning for WKWebView is only enabled in Release builds.
 * In DEBUG builds, Capacitor's default navigation delegate is left intact
 * to avoid interfering with local loading via capacitor://localhost.
 */

import UIKit
import Capacitor
import WebKit

class PerenniaViewController: CAPBridgeViewController {

    override open func capacitorDidLoad() {
        // Register custom native plugins
        bridge?.registerPluginInstance(AuditLogPlugin())
        bridge?.registerPluginInstance(DeviceIntegrityPlugin())
        bridge?.registerPluginInstance(MDMConfigPlugin())
        bridge?.registerPluginInstance(SiriShortcutsPlugin())
        bridge?.registerPluginInstance(SpotlightSearchPlugin())
        bridge?.registerPluginInstance(LiveActivityPlugin())
        bridge?.registerPluginInstance(ShareExtensionBridge())
        bridge?.registerPluginInstance(PinnedFetchPlugin())
        bridge?.registerPluginInstance(SensitiveScreenPlugin())

        // Provide the Capacitor bridge to PushNotificationRouter for deep link navigation
        if #available(iOS 13.0, *) {
            PushNotificationRouter.shared.bridge = bridge
        }
    }

    override func viewDidLoad() {
        super.viewDidLoad()

        #if !DEBUG
        // In Release builds, install certificate pinning on the WebView.
        // We create a dedicated pinning delegate that forwards all other
        // calls back to Capacitor's original delegate safely.
        let pinningDelegate = PinningNavigationDelegate(
            original: webView?.navigationDelegate
        )
        webView?.navigationDelegate = pinningDelegate
        // Retain the delegate (webView.navigationDelegate is weak)
        objc_setAssociatedObject(self, &AssociatedKeys.pinningDelegate, pinningDelegate, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
        #endif
    }

    // MARK: - Public API

    /// Clears all sensitive data from the WebView and secure storage.
    /// The completion handler fires after WebView data removal finishes,
    /// ensuring all async cleanup is done before the caller proceeds.
    public func clearSensitiveData(completion: (() -> Void)? = nil) {
        let group = DispatchGroup()
        group.enter()

        let dataTypes = WKWebsiteDataStore.allWebsiteDataTypes()
        WKWebsiteDataStore.default().removeData(
            ofTypes: dataTypes,
            modifiedSince: Date(timeIntervalSince1970: 0)
        ) {
            group.leave()
        }

        KeychainService.shared.deleteAll()
        EncryptedCacheService.shared.clearAll()
        AuditLogger.shared.log(event: .logout)

        group.notify(queue: .main) {
            completion?()
        }
    }
}

// MARK: - Associated Object Key

private struct AssociatedKeys {
    static var pinningDelegate = 0
}

// MARK: - Pinning Navigation Delegate (Release only)

/// A WKNavigationDelegate that intercepts TLS challenges for certificate
/// pinning while forwarding everything else to Capacitor's original delegate.
///
/// Unlike making the ViewController itself the delegate, this class uses
/// NSObject message forwarding so any delegate method Capacitor implements
/// is automatically forwarded — no risk of swallowing completion handlers.
private class PinningNavigationDelegate: NSObject, WKNavigationDelegate {

    private weak var original: WKNavigationDelegate?

    init(original: WKNavigationDelegate?) {
        self.original = original
        super.init()
    }

    // MARK: - Certificate Pinning

    func webView(
        _ webView: WKWebView,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        pinWebViewChallenge(challenge, completionHandler: completionHandler)
    }

    // MARK: - Safe Forwarding

    // For methods with completion handlers, we MUST always call the handler.
    // Check if the original implements the method; if not, call handler directly.

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        if let original = original {
            original.webView?(webView, decidePolicyFor: navigationAction, decisionHandler: decisionHandler)
                ?? decisionHandler(.allow)
        } else {
            decisionHandler(.allow)
        }
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationResponse: WKNavigationResponse,
        decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void
    ) {
        if let original = original {
            original.webView?(webView, decidePolicyFor: navigationResponse, decisionHandler: decisionHandler)
                ?? decisionHandler(.allow)
        } else {
            decisionHandler(.allow)
        }
    }

    // Methods without completion handlers — safe to forward with optional chaining.

    func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
        original?.webView?(webView, didCommit: navigation)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        original?.webView?(webView, didFinish: navigation)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        original?.webView?(webView, didFail: navigation, withError: error)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let nsError = error as NSError
        if nsError.code == NSURLErrorCancelled || nsError.code == NSURLErrorServerCertificateUntrusted {
            AuditLogger.shared.log(event: .certificatePinFailure, details: ["error_code": "\(nsError.code)"])
        }
        original?.webView?(webView, didFailProvisionalNavigation: navigation, withError: error)
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        original?.webViewWebContentProcessDidTerminate?(webView)
    }
}
