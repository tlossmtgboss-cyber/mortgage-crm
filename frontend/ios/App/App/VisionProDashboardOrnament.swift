/**
 * VisionProDashboardOrnament.swift
 * Perennia AI — Dashboard Ornament for Apple Vision Pro
 *
 * A SwiftUI ornament view that floats alongside the main Capacitor web view
 * window, providing at-a-glance pipeline metrics, quick actions, and
 * real-time notification badges.
 *
 * On visionOS, ornaments are lightweight panels anchored to a window edge.
 * This ornament attaches to the bottom edge of the main app window and
 * provides:
 *   - Pipeline summary (total leads, active loans, pipeline value)
 *   - Quick action buttons (Add Lead, Quick Call, New Task)
 *   - Unread notification count badge
 *
 * Data is fetched via PerenniaAPIService.shared, the same service used
 * by VisionProPipelineView.
 *
 * All code is gated behind #if os(visionOS) so iOS builds are unaffected.
 */

#if os(visionOS)

import SwiftUI

// MARK: - Dashboard Ornament View

/// The main ornament content. Attach this to the app's primary window
/// using the `.ornament()` modifier in your WindowGroup scene.
///
/// Usage in a SwiftUI App scene:
/// ```
/// WindowGroup {
///     ContentView()
///         .ornament(
///             visibility: .visible,
///             attachmentAnchor: .scene(.bottom),
///             contentAlignment: .center
///         ) {
///             DashboardOrnamentView()
///                 .glassBackgroundEffect()
///         }
/// }
/// ```
struct DashboardOrnamentView: View {

    @ObservedObject private var api = PerenniaAPIService.shared

    @State private var showNotifications = false
    @State private var hasAppeared = false

    var body: some View {
        HStack(spacing: 20) {

            // Pipeline metrics (left section)
            pipelineMetrics

            divider

            // Quick actions (center section)
            quickActions

            divider

            // Notifications (right section)
            notificationBadge
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 14)
        .frame(maxWidth: 720)
        .opacity(hasAppeared ? 1 : 0)
        .offset(y: hasAppeared ? 0 : 20)
        .onAppear {
            withAnimation(PerenniaAnimation.standard) {
                hasAppeared = true
            }
            api.startPolling()
        }
        .onDisappear {
            api.stopPolling()
        }
    }

    // MARK: - Pipeline Metrics

    private var pipelineMetrics: some View {
        HStack(spacing: 16) {
            MetricPill(
                icon: "person.2.fill",
                label: "Leads",
                value: formatCount(api.pipelineSummary.totalLeads),
                tint: PerenniaColors.primary
            )

            MetricPill(
                icon: "doc.text.fill",
                label: "Active Loans",
                value: formatCount(api.pipelineSummary.activeLoans),
                tint: PerenniaColors.accent
            )

            MetricPill(
                icon: "dollarsign.circle.fill",
                label: "Pipeline",
                value: formatCurrency(api.pipelineSummary.totalPipelineValue),
                tint: PerenniaColors.success
            )
        }
    }

    // MARK: - Quick Actions

    private var quickActions: some View {
        HStack(spacing: 12) {
            OrnamentActionButton(
                title: "Add Lead",
                systemImage: "person.badge.plus",
                tint: PerenniaColors.primary
            ) {
                postWebViewAction("addLead")
            }

            OrnamentActionButton(
                title: "Quick Call",
                systemImage: "phone.arrow.up.right",
                tint: PerenniaColors.accent
            ) {
                postWebViewAction("quickCall")
            }

            OrnamentActionButton(
                title: "New Task",
                systemImage: "plus.circle",
                tint: PerenniaColors.warning
            ) {
                postWebViewAction("newTask")
            }
        }
    }

    // MARK: - Notification Badge

    private var notificationBadge: some View {
        Button {
            showNotifications.toggle()
        } label: {
            ZStack(alignment: .topTrailing) {
                Image(systemName: "bell.fill")
                    .font(.system(size: 20, weight: .medium))
                    .foregroundStyle(PerenniaColors.textPrimary)
                    .frame(width: 44, height: 44)

                if unreadCount > 0 {
                    Text(unreadCount > 99 ? "99+" : "\(unreadCount)")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(PerenniaColors.destructive, in: Capsule())
                        .offset(x: 6, y: -4)
                }
            }
        }
        .buttonStyle(.plain)
        .perenniaHover(glow: PerenniaColors.primary)
        .popover(isPresented: $showNotifications) {
            NotificationPopoverView(notifications: api.notifications)
                .frame(width: 320, height: 400)
        }
    }

    // MARK: - Helpers

    private var divider: some View {
        Rectangle()
            .fill(PerenniaColors.separator)
            .frame(width: 1, height: 36)
    }

    private var unreadCount: Int {
        api.notifications.filter { !$0.isRead }.count
    }

    /// Posts a navigation action to the Capacitor web view via NotificationCenter.
    /// The PerenniaViewController (or a JS bridge) can listen for these and
    /// route the web app accordingly.
    private func postWebViewAction(_ action: String) {
        NotificationCenter.default.post(
            name: Notification.Name("PerenniaVisionProAction"),
            object: nil,
            userInfo: ["action": action]
        )
    }
}


// MARK: - Sub-Components

/// A compact metric display for the ornament bar.
private struct MetricPill: View {
    let icon: String
    let label: String
    let value: String
    let tint: Color

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(tint)

            VStack(alignment: .leading, spacing: 1) {
                Text(label)
                    .font(PerenniaTypography.captionSmall)
                    .foregroundStyle(PerenniaColors.textTertiary)

                Text(value)
                    .font(PerenniaTypography.headline)
                    .foregroundStyle(PerenniaColors.textPrimary)
            }
        }
        .perenniaSubtleHover()
    }
}

/// A compact action button for the ornament bar.
private struct OrnamentActionButton: View {
    let title: String
    let systemImage: String
    var tint: Color = PerenniaColors.primary
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Image(systemName: systemImage)
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(tint)

                Text(title)
                    .font(PerenniaTypography.captionSmall)
                    .foregroundStyle(PerenniaColors.textSecondary)
            }
            .frame(width: 64, height: 52)
        }
        .buttonStyle(.plain)
        .perenniaHover(scale: 1.05, glow: tint)
    }
}


// MARK: - Notification Popover

/// Popover showing recent unread notifications.
struct NotificationPopoverView: View {
    let notifications: [PerenniaNotification]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Text("Notifications")
                    .font(PerenniaTypography.title3)
                    .foregroundStyle(PerenniaColors.textPrimary)

                Spacer()

                if !unreadNotifications.isEmpty {
                    Text("\(unreadNotifications.count) unread")
                        .font(PerenniaTypography.caption)
                        .foregroundStyle(PerenniaColors.textSecondary)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)

            Divider()
                .overlay(PerenniaColors.separator)

            // Notification list
            if unreadNotifications.isEmpty {
                emptyState
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(Array(unreadNotifications.enumerated()), id: \.element.id) { index, notification in
                            NotificationRow(notification: notification)
                                .opacity(1)
                                .animation(PerenniaAnimation.staggered(index: index), value: true)

                            if index < unreadNotifications.count - 1 {
                                Divider()
                                    .overlay(PerenniaColors.separator)
                                    .padding(.leading, 48)
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .background(.regularMaterial)
    }

    private var unreadNotifications: [PerenniaNotification] {
        notifications.filter { !$0.isRead }
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: "bell.slash")
                .font(.system(size: 32, weight: .light))
                .foregroundStyle(PerenniaColors.textTertiary)
            Text("All caught up")
                .font(PerenniaTypography.body)
                .foregroundStyle(PerenniaColors.textSecondary)
            Text("No unread notifications")
                .font(PerenniaTypography.caption)
                .foregroundStyle(PerenniaColors.textTertiary)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }
}

/// A single notification row.
private struct NotificationRow: View {
    let notification: PerenniaNotification

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Type icon
            Image(systemName: iconForType(notification.type))
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(colorForType(notification.type))
                .frame(width: 32, height: 32)
                .background(colorForType(notification.type).opacity(0.15), in: Circle())

            VStack(alignment: .leading, spacing: 3) {
                Text(notification.title)
                    .font(PerenniaTypography.callout)
                    .foregroundStyle(PerenniaColors.textPrimary)
                    .lineLimit(1)

                Text(notification.message)
                    .font(PerenniaTypography.captionSmall)
                    .foregroundStyle(PerenniaColors.textSecondary)
                    .lineLimit(2)

                if let date = notification.createdAt {
                    Text(date, style: .relative)
                        .font(PerenniaTypography.captionSmall)
                        .foregroundStyle(PerenniaColors.textTertiary)
                }
            }

            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .perenniaSubtleHover()
    }

    private func iconForType(_ type: String) -> String {
        switch type.lowercased() {
        case "lead": return "person.badge.plus"
        case "loan": return "doc.text.fill"
        case "task": return "checklist"
        case "compliance": return "shield.checkered"
        case "rate": return "chart.line.uptrend.xyaxis"
        case "call": return "phone.fill"
        case "sms": return "message.fill"
        case "email": return "envelope.fill"
        case "document": return "doc.fill"
        case "alert", "warning": return "exclamationmark.triangle.fill"
        default: return "bell.fill"
        }
    }

    private func colorForType(_ type: String) -> Color {
        switch type.lowercased() {
        case "lead": return PerenniaColors.primary
        case "loan": return PerenniaColors.accent
        case "task": return PerenniaColors.warning
        case "compliance": return PerenniaColors.stageApproved
        case "rate": return PerenniaColors.stageProcessing
        case "alert", "warning": return PerenniaColors.destructive
        default: return PerenniaColors.textSecondary
        }
    }
}

#endif
