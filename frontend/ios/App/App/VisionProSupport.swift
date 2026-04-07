/**
 * VisionProSupport.swift
 * Perennia AI — Apple Vision Pro Window & Scene Configuration
 *
 * Configures the main Capacitor WKWebView window for optimal display on
 * Apple Vision Pro. The Capacitor web view remains the primary interface;
 * this module ensures it looks and feels native in a spatial computing
 * environment.
 *
 * Responsibilities:
 *   - Preferred window sizing and placement
 *   - Glass background material behind the web content
 *   - Hover effects for eye-tracking interactivity
 *   - Ornament attachment points for companion SwiftUI views
 *   - Shared API service for fetching pipeline data from the backend
 *
 * All code is gated behind #if os(visionOS) so iOS builds are unaffected.
 */

#if os(visionOS)

import SwiftUI
import UIKit

// MARK: - Window Configuration

/// Central configuration for the Perennia AI main window on visionOS.
struct VisionProWindowConfig {

    /// Default window dimensions (points). Vision Pro windows are scalable,
    /// but we set a comfortable starting size for a CRM dashboard.
    static let preferredSize = CGSize(width: 1280, height: 960)

    /// Minimum allowed window size before content becomes cramped.
    static let minimumSize = CGSize(width: 800, height: 600)

    /// Maximum allowed window size.
    static let maximumSize = CGSize(width: 1920, height: 1200)

    /// Corner radius matching the visionOS window chrome.
    static let windowCornerRadius: CGFloat = 40

    /// Applies spatial computing optimizations to the given UIWindow.
    ///
    /// Call this from the AppDelegate or SceneDelegate after the window
    /// is created but before it is made visible.
    ///
    /// - Parameter window: The UIWindow hosting the Capacitor web view.
    static func configureWindow(_ window: UIWindow) {
        // Apply glass material as the root background so the web view
        // composites over the visionOS passthrough with depth.
        window.backgroundColor = .clear

        // Request the preferred window geometry from the system.
        if let windowScene = window.windowScene {
            configureWindowGeometry(windowScene)
        }

        // Ensure the root view controller respects the glass backdrop.
        if let rootVC = window.rootViewController {
            rootVC.view.backgroundColor = .clear

            // Walk the view hierarchy to make intermediate views transparent
            // so the glass material shows through behind the WKWebView.
            makeViewHierarchyTransparent(rootVC.view)
        }
    }

    /// Requests the preferred window size from the visionOS window manager.
    private static func configureWindowGeometry(_ scene: UIWindowScene) {
        let geometryPreferences = UIWindowScene.GeometryPreferences.Vision()
        geometryPreferences.minimumSize = minimumSize
        geometryPreferences.maximumSize = maximumSize
        geometryPreferences.resizingRestrictions = .uniform

        scene.requestGeometryUpdate(geometryPreferences) { error in
            NSLog("[VisionPro] Window geometry update failed: \(error.localizedDescription)")
        }
    }

    /// Recursively sets backgrounds to clear so the system glass material
    /// is visible behind the web content.
    private static func makeViewHierarchyTransparent(_ view: UIView) {
        // Only clear backgrounds that are opaque white/system background.
        // Preserve any intentionally colored views.
        if view.backgroundColor == .systemBackground || view.backgroundColor == .white {
            view.backgroundColor = .clear
        }

        for subview in view.subviews {
            makeViewHierarchyTransparent(subview)
        }
    }
}


// MARK: - Hover Effect Utilities

/// UIKit-level hover effect registration for Capacitor's UIView hierarchy.
/// visionOS uses hover effects (eye tracking) to indicate interactivity.
struct VisionProHoverEffects {

    /// Registers a standard lift hover effect on the given view.
    /// Suitable for buttons and tappable cards in the web view overlay.
    static func registerLiftEffect(on view: UIView) {
        let hoverStyle = UIHoverStyle(
            effect: .lift,
            shape: .roundedRect(cornerRadius: 12)
        )
        view.hoverStyle = hoverStyle
    }

    /// Registers a highlight hover effect on the given view.
    /// Suitable for list rows and secondary interactive elements.
    static func registerHighlightEffect(on view: UIView) {
        let hoverStyle = UIHoverStyle(
            effect: .highlight,
            shape: .roundedRect(cornerRadius: 8)
        )
        view.hoverStyle = hoverStyle
    }

    /// Removes any hover effect from the given view.
    static func removeEffect(from view: UIView) {
        view.hoverStyle = nil
    }
}


// MARK: - Shared API Service

/// Lightweight API client shared across all visionOS companion views
/// (dashboard ornament, 3D pipeline, etc.). Uses the same backend as
/// the Capacitor web app.
///
/// This singleton fetches data independently of the WKWebView so that
/// ornaments and volumetric views can update even when the main window
/// is showing a different page.
@MainActor
final class PerenniaAPIService: ObservableObject {

    static let shared = PerenniaAPIService()

    // MARK: Published State

    @Published var pipelineSummary: PipelineSummary = .empty
    @Published var notifications: [PerenniaNotification] = []
    @Published var isLoading = false
    @Published var lastError: String? = nil

    // MARK: Configuration

    private let baseURL: URL
    private let session: URLSession

    /// Auth token injected from the Capacitor bridge when the user logs in.
    var authToken: String? {
        didSet {
            if authToken != nil {
                Task { await refreshAll() }
            }
        }
    }

    /// Polling interval for background data refresh (seconds).
    private let pollInterval: TimeInterval = 60

    /// Timer handle for periodic refresh.
    private var refreshTask: Task<Void, Never>?

    private init() {
        // Use the production API domain from Info.plist / build config.
        // Falls back to the standard domain if not configured.
        let domain = Bundle.main.object(forInfoDictionaryKey: "PERENNIA_API_DOMAIN") as? String
            ?? "api.perenniaai.com"
        self.baseURL = URL(string: "https://\(domain)")!

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        config.waitsForConnectivity = true
        self.session = URLSession(configuration: config)
    }

    // MARK: Public API

    /// Fetches all data needed by companion views.
    func refreshAll() async {
        guard authToken != nil else { return }

        isLoading = true
        defer { isLoading = false }

        async let pipeline = fetchPipelineSummary()
        async let notifs = fetchNotifications()

        self.pipelineSummary = await pipeline
        self.notifications = await notifs
    }

    /// Starts periodic background polling.
    func startPolling() {
        stopPolling()
        refreshTask = Task { [weak self] in
            guard let self = self else { return }
            while !Task.isCancelled {
                await self.refreshAll()
                try? await Task.sleep(for: .seconds(self.pollInterval))
            }
        }
    }

    /// Stops periodic background polling.
    func stopPolling() {
        refreshTask?.cancel()
        refreshTask = nil
    }

    // MARK: Endpoints

    /// Fetches the pipeline summary (stage counts and values).
    func fetchPipelineSummary() async -> PipelineSummary {
        guard let data = await get(path: "/api/v1/pipeline/metrics") else {
            return pipelineSummary // Keep stale data on failure
        }

        do {
            let decoded = try JSONDecoder().decode(PipelineSummaryResponse.self, from: data)
            lastError = nil
            return PipelineSummary(from: decoded)
        } catch {
            lastError = "Failed to decode pipeline data: \(error.localizedDescription)"
            NSLog("[VisionPro API] Pipeline decode error: \(error)")
            return pipelineSummary
        }
    }

    /// Fetches recent notifications.
    func fetchNotifications() async -> [PerenniaNotification] {
        guard let data = await get(path: "/api/v1/notifications?limit=20&unread=true") else {
            return notifications
        }

        do {
            let decoded = try JSONDecoder().decode(NotificationsResponse.self, from: data)
            lastError = nil
            return decoded.notifications.map { PerenniaNotification(from: $0) }
        } catch {
            lastError = "Failed to decode notifications: \(error.localizedDescription)"
            NSLog("[VisionPro API] Notifications decode error: \(error)")
            return notifications
        }
    }

    // MARK: HTTP

    private func get(path: String) async -> Data? {
        guard let token = authToken else {
            lastError = "Not authenticated"
            return nil
        }

        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Perennia-iOS-VisionPro/1.0", forHTTPHeaderField: "User-Agent")

        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                lastError = "Invalid response"
                return nil
            }
            guard (200...299).contains(httpResponse.statusCode) else {
                lastError = "HTTP \(httpResponse.statusCode) for \(path)"
                NSLog("[VisionPro API] HTTP \(httpResponse.statusCode) for \(path)")
                return nil
            }
            return data
        } catch {
            lastError = error.localizedDescription
            NSLog("[VisionPro API] Request failed for \(path): \(error)")
            return nil
        }
    }
}


// MARK: - Data Models

/// Summary of the loan pipeline, aggregated by stage.
struct PipelineSummary: Equatable {
    var totalLeads: Int
    var activeLoans: Int
    var totalPipelineValue: Double
    var stages: [PipelineStage]

    static let empty = PipelineSummary(
        totalLeads: 0,
        activeLoans: 0,
        totalPipelineValue: 0,
        stages: []
    )

    init(totalLeads: Int, activeLoans: Int, totalPipelineValue: Double, stages: [PipelineStage]) {
        self.totalLeads = totalLeads
        self.activeLoans = activeLoans
        self.totalPipelineValue = totalPipelineValue
        self.stages = stages
    }

    init(from response: PipelineSummaryResponse) {
        self.totalLeads = response.total_leads ?? 0
        self.activeLoans = response.active_loans ?? 0
        self.totalPipelineValue = response.total_pipeline_value ?? 0

        self.stages = (response.stages ?? []).map { stageData in
            PipelineStage(
                name: stageData.stage ?? "UNKNOWN",
                count: stageData.count ?? 0,
                totalValue: stageData.total_value ?? 0
            )
        }
    }
}

/// A single stage in the pipeline with count and dollar value.
struct PipelineStage: Identifiable, Equatable {
    let id = UUID()
    let name: String
    let count: Int
    let totalValue: Double

    /// Human-readable display name (e.g., "UW_RECEIVED" -> "UW Received").
    var displayName: String {
        name.replacingOccurrences(of: "_", with: " ")
            .split(separator: " ")
            .map { word in
                let lower = word.lowercased()
                // Keep common abbreviations uppercase
                if ["uw", "ctc"].contains(lower) {
                    return word.uppercased()
                }
                return word.prefix(1).uppercased() + word.dropFirst().lowercased()
            }
            .joined(separator: " ")
    }
}

/// In-app notification.
struct PerenniaNotification: Identifiable {
    let id: String
    let title: String
    let message: String
    let type: String
    let isRead: Bool
    let createdAt: Date?

    init(from response: NotificationItem) {
        self.id = response.id ?? UUID().uuidString
        self.title = response.title ?? "Notification"
        self.message = response.message ?? ""
        self.type = response.type ?? "info"
        self.isRead = response.is_read ?? false

        if let dateStr = response.created_at {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            self.createdAt = formatter.date(from: dateStr)
        } else {
            self.createdAt = nil
        }
    }
}

// MARK: - API Response DTOs (snake_case to match Python backend)

struct PipelineSummaryResponse: Decodable {
    let total_leads: Int?
    let active_loans: Int?
    let total_pipeline_value: Double?
    let stages: [StageData]?
}

struct StageData: Decodable {
    let stage: String?
    let count: Int?
    let total_value: Double?
}

struct NotificationsResponse: Decodable {
    let notifications: [NotificationItem]
}

struct NotificationItem: Decodable {
    let id: String?
    let title: String?
    let message: String?
    let type: String?
    let is_read: Bool?
    let created_at: String?
}

#endif
