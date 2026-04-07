/**
 * SpotlightHandler.swift
 * Perennia AI — Spotlight Deep Link Handler
 *
 * Handles tap events when a user selects a Spotlight search result indexed
 * by SpotlightIndexer. Parses the CSSearchableItem activity, determines
 * the item type and ID, then navigates the Capacitor WebView to the
 * appropriate page in the React SPA.
 *
 * Flow:
 *   1. User taps a Spotlight result (lead, loan, or task)
 *   2. iOS calls application(_:continue:restorationHandler:) in AppDelegate
 *   3. AppDelegate forwards to SpotlightHandler.handleActivity(_:bridge:)
 *   4. SpotlightHandler parses the unique identifier (e.g., "lead_42")
 *   5. SpotlightHandler injects a JavaScript navigation call into the WebView
 *   6. The React app navigates to /leads/42, /loans/42, or /tasks/42
 *
 * The handler also posts a local NotificationCenter notification so that
 * native code can observe Spotlight navigation events if needed.
 */

import Foundation
import CoreSpotlight
import UIKit
import Capacitor

// MARK: - Notification Names

extension Notification.Name {
    /// Posted when a Spotlight result is tapped and the app should navigate.
    /// The userInfo contains "type" (String) and "id" (Int).
    static let spotlightItemSelected = Notification.Name("com.perenniaai.crm.spotlightItemSelected")
}

// MARK: - SpotlightHandler

/// Handles deep linking from iOS Spotlight search results into the Capacitor app.
///
/// Usage from AppDelegate:
///
///     func application(_ application: UIApplication,
///                      continue userActivity: NSUserActivity,
///                      restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void) -> Bool {
///         if SpotlightHandler.handleActivity(userActivity, bridge: bridge) {
///             return true
///         }
///         return ApplicationDelegateProxy.shared.application(application, continue: userActivity, restorationHandler: restorationHandler)
///     }
///
enum SpotlightHandler {

    // MARK: - Route Mapping

    /// Maps item type prefixes to their corresponding SPA route paths.
    private static let routeMap: [String: String] = [
        "lead": "/leads",
        "loan": "/loans",
        "task": "/tasks"
    ]

    // MARK: - Public API

    /// Handle a Spotlight continuation activity.
    ///
    /// - Parameters:
    ///   - activity: The NSUserActivity from the Spotlight tap
    ///   - bridge: The Capacitor bridge instance (optional; if nil, uses notification only)
    /// - Returns: `true` if this was a Spotlight activity that was handled, `false` otherwise
    @discardableResult
    static func handleActivity(_ activity: NSUserActivity, bridge: CAPBridgeProtocol?) -> Bool {
        // Only handle Spotlight search continuation activities
        guard activity.activityType == CSSearchableItemActionType else {
            return false
        }

        // Extract the unique identifier that was set during indexing
        guard let identifier = activity.userInfo?[CSSearchableItemActivityIdentifier] as? String else {
            NSLog("[SpotlightHandler] Spotlight activity missing identifier")
            return false
        }

        NSLog("[SpotlightHandler] Handling Spotlight tap for: %@", identifier)

        // Parse the identifier (format: "type_id", e.g., "lead_42")
        guard let parsed = parseIdentifier(identifier) else {
            NSLog("[SpotlightHandler] Could not parse identifier: %@", identifier)
            return false
        }

        let (type, id) = parsed

        // Post a notification so any native observer can react
        NotificationCenter.default.post(
            name: .spotlightItemSelected,
            object: nil,
            userInfo: ["type": type, "id": id, "identifier": identifier]
        )

        // Navigate the WebView to the item's page
        navigateToItem(type: type, id: id, bridge: bridge)

        return true
    }

    /// Navigate the Capacitor WebView to a specific item page.
    ///
    /// - Parameters:
    ///   - type: The item type ("lead", "loan", or "task")
    ///   - id: The item's integer ID
    ///   - bridge: The Capacitor bridge to execute JavaScript on
    static func navigateToItem(type: String, id: Int, bridge: CAPBridgeProtocol?) {
        guard let routeBase = routeMap[type] else {
            NSLog("[SpotlightHandler] Unknown item type: %@", type)
            return
        }

        let route = "\(routeBase)/\(id)"
        NSLog("[SpotlightHandler] Navigating to: %@", route)

        // Execute JavaScript to navigate within the React SPA.
        // Uses window.location.hash for hash-router apps, or
        // window.dispatchEvent with a custom event that the React app listens for.
        // We try both approaches: direct history push and a custom event.
        let js = """
        (function() {
            var route = '\(route)';
            // Method 1: Push state for BrowserRouter / MemoryRouter
            if (window.history && window.history.pushState) {
                window.history.pushState({}, '', route);
                window.dispatchEvent(new PopStateEvent('popstate'));
            }
            // Method 2: Custom event for the React app to handle
            window.dispatchEvent(new CustomEvent('spotlightNavigation', {
                detail: { type: '\(type)', id: \(id), route: route }
            }));
        })();
        """

        DispatchQueue.main.async {
            if let bridge = bridge {
                bridge.webView?.evaluateJavaScript(js) { _, error in
                    if let error = error {
                        NSLog("[SpotlightHandler] JS navigation error: %@", error.localizedDescription)
                    }
                }
            } else {
                NSLog("[SpotlightHandler] No bridge available — posted notification only")
            }
        }
    }

    // MARK: - Parsing

    /// Parse a Spotlight unique identifier into its type and ID components.
    ///
    /// Expected format: "type_id" where type is "lead", "loan", or "task"
    /// and id is a positive integer.
    ///
    /// - Parameter identifier: The CSSearchableItem uniqueIdentifier
    /// - Returns: A tuple of (type, id) or nil if parsing fails
    static func parseIdentifier(_ identifier: String) -> (type: String, id: Int)? {
        // Find the last underscore to split on (handles potential underscores in type names)
        guard let underscoreIndex = identifier.lastIndex(of: "_") else {
            return nil
        }

        let type = String(identifier[identifier.startIndex..<underscoreIndex])
        let idString = String(identifier[identifier.index(after: underscoreIndex)...])

        guard let id = Int(idString), id > 0 else {
            return nil
        }

        // Validate type is one we recognize
        guard routeMap[type] != nil else {
            return nil
        }

        return (type: type, id: id)
    }
}
