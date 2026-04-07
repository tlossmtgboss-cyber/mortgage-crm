/**
 * SiriShortcutsPlugin.swift
 * Perennia AI - Siri Shortcuts Integration
 *
 * Donates NSUserActivity instances to Siri when the user performs key actions
 * (viewing the pipeline, contacting a client, managing tasks). Siri learns
 * usage patterns and surfaces these as suggested shortcuts on the lock screen,
 * in Spotlight, and via "Hey Siri" voice invocation.
 *
 * Activity types declared in Info.plist:
 *   - com.perenniaai.crm.viewProperty   (pipeline / property views)
 *   - com.perenniaai.crm.contactClient   (client communication)
 *   - com.perenniaai.crm.manageTask      (task management)
 *
 * Registration: The plugin must be registered in PerenniaViewController.capacitorDidLoad():
 *   bridge?.registerPluginInstance(SiriShortcutsPlugin())
 *
 * JavaScript bridge name: "SiriShortcuts"
 */

import Foundation
import Capacitor
import CoreSpotlight
import Intents

@objc(SiriShortcutsPlugin)
public class SiriShortcutsPlugin: CAPPlugin, CAPBridgedPlugin {

    // MARK: - CAPBridgedPlugin conformance

    public let identifier = "SiriShortcutsPlugin"
    public let jsName = "SiriShortcuts"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "donateActivity", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "clearDonations", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getSuggestedActions", returnType: CAPPluginReturnPromise)
    ]

    // MARK: - Activity type constants

    private static let activityTypeViewProperty = "com.perenniaai.crm.viewProperty"
    private static let activityTypeContactClient = "com.perenniaai.crm.contactClient"
    private static let activityTypeManageTask = "com.perenniaai.crm.manageTask"

    private static let validActivityTypes: Set<String> = [
        activityTypeViewProperty,
        activityTypeContactClient,
        activityTypeManageTask
    ]

    // MARK: - Route mapping (activity type -> web app path)

    /// Maps activity types to the default web app route to open when Siri
    /// launches the app for that activity. Individual donations can override
    /// with a `route` key in userInfo.
    private static let defaultRoutes: [String: String] = [
        activityTypeViewProperty: "/leads",
        activityTypeContactClient: "/leads",
        activityTypeManageTask: "/tasks"
    ]

    // MARK: - Usage tracking for suggestions

    /// Simple in-memory frequency tracker. Counts how many times each
    /// activity type has been donated this session. Persisted to UserDefaults
    /// so suggestions survive app restarts.
    private static let usageDefaultsKey = "com.perenniaai.crm.siriShortcutUsage"

    /// Tracks per-activity-type donation counts for suggestion ranking.
    private var usageCounts: [String: Int] = [:]

    /// Tracks the most recently contacted client names for personalized suggestions.
    private var recentClients: [String] = []
    private static let recentClientsKey = "com.perenniaai.crm.siriRecentClients"
    private static let maxRecentClients = 5

    // MARK: - Lifecycle

    override public func load() {
        loadUsageData()
        loadRecentClients()
    }

    // MARK: - Plugin Methods

    /// Donate a user activity to Siri.
    ///
    /// Parameters (from JavaScript):
    ///   - type: String — one of the NSUserActivityTypes from Info.plist
    ///   - title: String — the shortcut title shown to the user
    ///   - description: String? — optional subtitle / description
    ///   - userInfo: Object? — arbitrary key-value pairs passed back on invocation
    ///   - route: String? — the web app route to navigate to (e.g., "/leads/123")
    ///
    /// Returns: { donated: true }
    @objc func donateActivity(_ call: CAPPluginCall) {
        guard let activityType = call.getString("type") else {
            call.reject("Missing required parameter: type")
            return
        }

        guard SiriShortcutsPlugin.validActivityTypes.contains(activityType) else {
            call.reject("Invalid activity type: \(activityType). Must be one of: \(SiriShortcutsPlugin.validActivityTypes)")
            return
        }

        guard let title = call.getString("title") else {
            call.reject("Missing required parameter: title")
            return
        }

        let description = call.getString("description") ?? ""
        let route = call.getString("route") ?? SiriShortcutsPlugin.defaultRoutes[activityType] ?? "/"
        let userInfoRaw = call.getObject("userInfo") ?? [:]

        // Build userInfo dictionary, injecting the route for later retrieval
        var userInfo: [String: Any] = [:]
        for (key, value) in userInfoRaw {
            userInfo[key] = value
        }
        userInfo["route"] = route

        // Create NSUserActivity
        let activity = NSUserActivity(activityType: activityType)
        activity.title = title
        activity.isEligibleForSearch = true
        activity.isEligibleForPrediction = true
        activity.persistentIdentifier = NSUserActivityPersistentIdentifier(activityType + "." + route)
        activity.userInfo = userInfo

        // Set a suggested invocation phrase for Siri
        activity.suggestedInvocationPhrase = title

        // Add CoreSpotlight attributes for richer Spotlight integration
        let attributes = CSSearchableItemAttributeSet(contentType: .content)
        attributes.title = title
        attributes.contentDescription = description
        attributes.keywords = buildKeywords(for: activityType, title: title)
        activity.contentAttributeSet = attributes

        // Track usage for suggestion ranking
        incrementUsage(for: activityType)

        // Track client name for contact activities
        if activityType == SiriShortcutsPlugin.activityTypeContactClient {
            if let clientName = userInfoRaw["clientName"] as? String, !clientName.isEmpty {
                trackRecentClient(clientName)
            }
        }

        // Donate the activity. Setting it as the current activity on the
        // view controller triggers Siri's learning pipeline.
        DispatchQueue.main.async { [weak self] in
            self?.bridge?.viewController?.userActivity = activity
            activity.becomeCurrent()

            call.resolve(["donated": true])
        }
    }

    /// Clear all donated Siri shortcut activities.
    ///
    /// Returns: { cleared: true }
    @objc func clearDonations(_ call: CAPPluginCall) {
        NSUserActivity.deleteSavedUserActivities(
            withPersistentIdentifiers: [],
            completionHandler: { [weak self] in
                // Reset usage tracking
                self?.usageCounts = [:]
                self?.recentClients = []
                self?.saveUsageData()
                self?.saveRecentClients()

                // Clear Spotlight index for our bundle
                CSSearchableIndex.default().deleteAllSearchableItems { error in
                    if let error = error {
                        print("[SiriShortcuts] Warning: Failed to clear Spotlight index: \(error.localizedDescription)")
                    }
                }

                call.resolve(["cleared": true])
            }
        )
    }

    /// Return suggested shortcuts based on observed usage patterns.
    /// The frontend can display these in a settings or shortcuts management page.
    ///
    /// Returns: { suggestions: [{ type, title, description, route, frequency }] }
    @objc func getSuggestedActions(_ call: CAPPluginCall) {
        var suggestions: [[String: Any]] = []

        // Sort activity types by frequency (most donated first)
        let sorted = usageCounts.sorted { $0.value > $1.value }

        for (activityType, count) in sorted {
            let suggestion = buildSuggestion(for: activityType, frequency: count)
            suggestions.append(suggestion)
        }

        // If user frequently contacts specific clients, suggest those
        for clientName in recentClients.prefix(3) {
            suggestions.append([
                "type": SiriShortcutsPlugin.activityTypeContactClient,
                "title": "Call \(clientName)",
                "description": "Contact \(clientName) in Perennia AI",
                "route": "/leads",
                "frequency": 0,
                "isPersonalized": true
            ])
        }

        // If pipeline is checked often (>= 3 times), suggest morning check
        if let pipelineCount = usageCounts[SiriShortcutsPlugin.activityTypeViewProperty],
           pipelineCount >= 3 {
            suggestions.append([
                "type": SiriShortcutsPlugin.activityTypeViewProperty,
                "title": "Morning Pipeline Check",
                "description": "Review your mortgage pipeline status",
                "route": "/leads",
                "frequency": pipelineCount,
                "isPersonalized": true
            ])
        }

        call.resolve(["suggestions": suggestions])
    }

    // MARK: - Siri Invocation Handling

    /// Called by the AppDelegate when the app is launched or continued via a
    /// Siri shortcut (NSUserActivity). Routes the user to the correct page
    /// in the Capacitor web view.
    ///
    /// Call this from AppDelegate.application(_:continue:restorationHandler:)
    /// or from a NotificationCenter observer.
    public func handleUserActivity(_ userActivity: NSUserActivity) {
        guard SiriShortcutsPlugin.validActivityTypes.contains(userActivity.activityType) else {
            return
        }

        let route: String
        if let userInfoRoute = userActivity.userInfo?["route"] as? String {
            route = userInfoRoute
        } else {
            route = SiriShortcutsPlugin.defaultRoutes[userActivity.activityType] ?? "/"
        }

        // Navigate the Capacitor web view to the target route
        navigateWebView(to: route)

        // Notify the JavaScript layer so it can perform additional setup
        notifyListeners("shortcutActivated", data: [
            "type": userActivity.activityType,
            "title": userActivity.title ?? "",
            "route": route,
            "userInfo": userActivity.userInfo ?? [:]
        ])
    }

    // MARK: - Private Helpers

    /// Navigate the Capacitor web view to a specific route by evaluating
    /// JavaScript that pushes the route onto the React Router history.
    private func navigateWebView(to route: String) {
        let escapedRoute = route.replacingOccurrences(of: "'", with: "\\'")
        let js = """
        (function() {
            if (window.location.pathname !== '\(escapedRoute)') {
                window.history.pushState({}, '', '\(escapedRoute)');
                window.dispatchEvent(new PopStateEvent('popstate'));
            }
        })();
        """

        DispatchQueue.main.async { [weak self] in
            self?.bridge?.webView?.evaluateJavaScript(js) { _, error in
                if let error = error {
                    print("[SiriShortcuts] Navigation error: \(error.localizedDescription)")
                }
            }
        }
    }

    /// Build search keywords for a given activity type and title.
    private func buildKeywords(for activityType: String, title: String) -> [String] {
        var keywords = ["Perennia", "mortgage", "loan"]

        switch activityType {
        case SiriShortcutsPlugin.activityTypeViewProperty:
            keywords.append(contentsOf: ["pipeline", "property", "leads", "loans", "status"])
        case SiriShortcutsPlugin.activityTypeContactClient:
            keywords.append(contentsOf: ["contact", "client", "call", "borrower", "communication"])
        case SiriShortcutsPlugin.activityTypeManageTask:
            keywords.append(contentsOf: ["task", "tasks", "todo", "action", "workflow"])
        default:
            break
        }

        // Add words from the title as keywords
        let titleWords = title.components(separatedBy: .whitespaces)
            .filter { $0.count > 2 }
        keywords.append(contentsOf: titleWords)

        return keywords
    }

    /// Build a suggestion dictionary for a given activity type.
    private func buildSuggestion(for activityType: String, frequency: Int) -> [String: Any] {
        let route = SiriShortcutsPlugin.defaultRoutes[activityType] ?? "/"

        switch activityType {
        case SiriShortcutsPlugin.activityTypeViewProperty:
            return [
                "type": activityType,
                "title": "View Pipeline",
                "description": "Check your mortgage pipeline status",
                "route": route,
                "frequency": frequency,
                "isPersonalized": false
            ]
        case SiriShortcutsPlugin.activityTypeContactClient:
            return [
                "type": activityType,
                "title": "Contact Client",
                "description": "Reach out to a client",
                "route": route,
                "frequency": frequency,
                "isPersonalized": false
            ]
        case SiriShortcutsPlugin.activityTypeManageTask:
            return [
                "type": activityType,
                "title": "Manage Tasks",
                "description": "View and manage your tasks",
                "route": route,
                "frequency": frequency,
                "isPersonalized": false
            ]
        default:
            return [
                "type": activityType,
                "title": activityType,
                "description": "",
                "route": route,
                "frequency": frequency,
                "isPersonalized": false
            ]
        }
    }

    // MARK: - Usage Persistence

    /// Increment the donation count for an activity type.
    private func incrementUsage(for activityType: String) {
        usageCounts[activityType, default: 0] += 1
        saveUsageData()
    }

    /// Track a recently contacted client name.
    private func trackRecentClient(_ name: String) {
        // Remove if already present (to move to front)
        recentClients.removeAll { $0 == name }
        // Insert at front
        recentClients.insert(name, at: 0)
        // Trim to max
        if recentClients.count > SiriShortcutsPlugin.maxRecentClients {
            recentClients = Array(recentClients.prefix(SiriShortcutsPlugin.maxRecentClients))
        }
        saveRecentClients()
    }

    /// Load usage counts from UserDefaults (non-sensitive frequency data).
    private func loadUsageData() {
        let defaults = UserDefaults.standard
        if let saved = defaults.dictionary(forKey: SiriShortcutsPlugin.usageDefaultsKey) as? [String: Int] {
            usageCounts = saved
        }
    }

    /// Save usage counts to UserDefaults (non-sensitive frequency data).
    private func saveUsageData() {
        let defaults = UserDefaults.standard
        defaults.set(usageCounts, forKey: SiriShortcutsPlugin.usageDefaultsKey)
    }

    /// Load recent client names from encrypted cache (PII — GLBA protected).
    private func loadRecentClients() {
        if #available(iOS 14.0, *) {
            if let saved: [String] = EncryptedCacheService.shared.retrieve(
                key: SiriShortcutsPlugin.recentClientsKey,
                type: [String].self
            ) {
                recentClients = saved
            }
        }
    }

    /// Save recent client names to encrypted cache (PII — GLBA protected).
    private func saveRecentClients() {
        if #available(iOS 14.0, *) {
            EncryptedCacheService.shared.store(
                key: SiriShortcutsPlugin.recentClientsKey,
                value: recentClients
            )
        }
    }
}
