/**
 * VisionProDashboardView.swift
 * Perennia AI — Spatial Dashboard for Apple Vision Pro
 *
 * Presents pipeline summary, today's tasks, and rate alerts in a spatial layout
 * optimized for visionOS. Falls back to a standard SwiftUI view on iOS/iPadOS.
 *
 * Data is fetched live via CarPlayAPIService.shared, mapping DashboardData,
 * TaskItem, and RateAlert (from CarPlayModels) to local display types.
 */

import SwiftUI

// MARK: - Data Models

/// Pipeline stage with display metadata.
struct PipelineStageCard: Identifiable {
    let id = UUID()
    let stage: String
    let count: Int
    let icon: String
    let color: Color
}

/// A single task item mapped from the API's TaskItem.
struct DashboardTask: Identifiable {
    let id: String
    let title: String
    let subtitle: String
    let priority: TaskPriority
    let dueTime: String?

    enum TaskPriority: String {
        case high, medium, low

        var color: Color {
            switch self {
            case .high:   return .red
            case .medium: return .orange
            case .low:    return .green
            }
        }

        var icon: String {
            switch self {
            case .high:   return "exclamationmark.triangle.fill"
            case .medium: return "clock.fill"
            case .low:    return "checkmark.circle"
            }
        }
    }

    /// Map a CarPlayModels.CPTaskItem to a DashboardTask for display.
    static func from(_ item: CPTaskItem) -> DashboardTask {
        let priority: TaskPriority
        switch item.priority.lowercased() {
        case "high":   priority = .high
        case "medium": priority = .medium
        default:       priority = .low
        }

        let subtitle: String
        if let desc = item.description, !desc.isEmpty {
            subtitle = desc
        } else if let name = item.leadName, !name.isEmpty {
            subtitle = name
        } else {
            subtitle = item.status.capitalized
        }

        let dueTime = DashboardTask.formatDueDate(item.dueDate)

        return DashboardTask(
            id: String(item.id),
            title: item.title,
            subtitle: subtitle,
            priority: priority,
            dueTime: dueTime
        )
    }

    /// Parse an ISO 8601 date string into a short time string like "9:00 AM".
    private static func formatDueDate(_ isoString: String?) -> String? {
        guard let isoString = isoString, !isoString.isEmpty else { return nil }

        let isoFormatter = ISO8601DateFormatter()
        isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var date = isoFormatter.date(from: isoString)
        if date == nil {
            isoFormatter.formatOptions = [.withInternetDateTime]
            date = isoFormatter.date(from: isoString)
        }
        guard let parsed = date else { return nil }

        let display = DateFormatter()
        display.dateFormat = "h:mm a"
        return display.string(from: parsed)
    }
}

/// A rate alert mapped from the API's RateAlert (CarPlayModels).
/// Named DashboardRateAlert to avoid collision with CarPlayModels.RateAlert.
struct DashboardRateAlert: Identifiable {
    let id: UUID = UUID()
    let product: String
    let currentRate: Double
    let changeAmount: Double
    let direction: Direction

    enum Direction {
        case up, down

        var icon: String {
            switch self {
            case .up:   return "arrow.up.right"
            case .down: return "arrow.down.right"
            }
        }

        var color: Color {
            switch self {
            case .up:   return .red
            case .down: return .green
            }
        }
    }

    /// Map a CarPlayModels.CPRateAlert to a DashboardRateAlert for display.
    static func from(_ alert: CPRateAlert) -> DashboardRateAlert {
        let direction: Direction = alert.changeDirection.lowercased() == "down" ? .down : .up
        let change = abs(alert.currentRate - alert.previousRate)

        return DashboardRateAlert(
            product: alert.spokenRateType,
            currentRate: alert.currentRate,
            changeAmount: change,
            direction: direction
        )
    }
}

// MARK: - View Model

@available(iOS 15.0, *)
final class VisionProDashboardViewModel: ObservableObject {
    @Published var pipelineStages: [PipelineStageCard] = []
    @Published var tasks: [DashboardTask] = []
    @Published var rateAlerts: [DashboardRateAlert] = []
    @Published var isLoading = true
    @Published var errorMessage: String?

    @MainActor
    func loadData() async {
        isLoading = true
        errorMessage = nil

        do {
            async let pipelineResult = fetchPipelineData()
            async let tasksResult = fetchTasksData()
            async let alertsResult = fetchRateAlertData()

            let (pipeline, taskList, alerts) = try await (pipelineResult, tasksResult, alertsResult)
            self.pipelineStages = pipeline
            self.tasks = taskList
            self.rateAlerts = alerts
        } catch {
            errorMessage = "Unable to load dashboard: \(error.localizedDescription)"
        }

        isLoading = false
    }

    // MARK: - Data Fetching (via CarPlayAPIService)

    private func fetchPipelineData() async throws -> [PipelineStageCard] {
        let dashboard = try await CarPlayAPIService.shared.fetchDashboard()

        // Map dashboard summary counts into stage cards.
        // Only include stages that have a non-zero count so the grid stays relevant.
        let ps = dashboard.pipelineSummary
        var cards: [PipelineStageCard] = []

        if dashboard.newLeadCount > 0 {
            cards.append(PipelineStageCard(stage: "New Leads", count: dashboard.newLeadCount, icon: "person.3.fill", color: .blue))
        }
        if dashboard.activeLoanCount > 0 {
            cards.append(PipelineStageCard(stage: "Active Loans", count: dashboard.activeLoanCount, icon: "doc.text.fill", color: .indigo))
        }
        if (ps?.applicationCount ?? 0) > 0 {
            cards.append(PipelineStageCard(stage: "Application", count: ps!.applicationCount, icon: "pencil.and.list.clipboard", color: .teal))
        }
        if (ps?.processingCount ?? 0) > 0 {
            cards.append(PipelineStageCard(stage: "Processing", count: ps!.processingCount, icon: "gearshape.2.fill", color: .purple))
        }
        if (ps?.underwritingCount ?? 0) > 0 {
            cards.append(PipelineStageCard(stage: "Underwriting", count: ps!.underwritingCount, icon: "doc.text.magnifyingglass", color: .orange))
        }
        if dashboard.urgentTaskCount > 0 {
            cards.append(PipelineStageCard(stage: "Urgent Tasks", count: dashboard.urgentTaskCount, icon: "exclamationmark.triangle.fill", color: .red))
        }
        if (ps?.clearToCloseCount ?? 0) > 0 {
            cards.append(PipelineStageCard(stage: "Clear to Close", count: ps!.clearToCloseCount, icon: "checkmark.seal.fill", color: .green))
        }

        // If everything came back zero, still show the primary counts so the
        // dashboard is not completely empty.
        if cards.isEmpty {
            cards = [
                PipelineStageCard(stage: "New Leads", count: dashboard.newLeadCount, icon: "person.3.fill", color: .blue),
                PipelineStageCard(stage: "Active Loans", count: dashboard.activeLoanCount, icon: "doc.text.fill", color: .indigo),
                PipelineStageCard(stage: "Urgent Tasks", count: dashboard.urgentTaskCount, icon: "exclamationmark.triangle.fill", color: .red),
                PipelineStageCard(stage: "Appointments", count: dashboard.todayAppointmentCount, icon: "calendar", color: .orange),
            ]
        }

        return cards
    }

    private func fetchTasksData() async throws -> [DashboardTask] {
        let items = try await CarPlayAPIService.shared.fetchTasks()
        return items.map { DashboardTask.from($0) }
    }

    private func fetchRateAlertData() async throws -> [DashboardRateAlert] {
        let alerts = try await CarPlayAPIService.shared.fetchRateAlerts()
        return alerts.map { DashboardRateAlert.from($0) }
    }
}

// MARK: - Main Dashboard View

@available(iOS 15.0, *)
struct VisionProDashboardView: View {
    @StateObject private var viewModel = VisionProDashboardViewModel()
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Group {
            if viewModel.isLoading {
                loadingView
            } else if let error = viewModel.errorMessage {
                errorView(error)
            } else {
                dashboardContent
            }
        }
        .task {
            await viewModel.loadData()
        }
    }

    // MARK: - Dashboard Content

    private var dashboardContent: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: 24) {
                // Rate alert banner
                if !viewModel.rateAlerts.isEmpty {
                    rateAlertBanner
                }

                // Pipeline summary
                pipelineSection

                // Today's tasks
                tasksSection
            }
            .padding(platformPadding)
        }
        .background(backgroundStyle)
        #if os(visionOS)
        .ornament(attachmentAnchor: .scene(.topTrailing)) {
            refreshOrnament
        }
        #endif
    }

    // MARK: - Rate Alert Banner

    private var rateAlertBanner: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Rate Alerts", systemImage: "bell.badge.fill")
                .font(.headline)
                .foregroundColor(.primary)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(viewModel.rateAlerts) { alert in
                        rateAlertCard(alert)
                    }
                }
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(alertBannerBackground)
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Rate alerts section")
    }

    private func rateAlertCard(_ alert: DashboardRateAlert) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(alert.product)
                .font(.caption)
                .foregroundColor(.secondary)

            HStack(spacing: 4) {
                Text(String(format: "%.3f%%", alert.currentRate))
                    .font(.title3.monospacedDigit().bold())

                Image(systemName: alert.direction.icon)
                    .font(.caption)
                    .foregroundColor(alert.direction.color)
            }

            Text(String(format: "%@%.3f",
                         alert.direction == .down ? "-" : "+",
                         alert.changeAmount))
                .font(.caption2.monospacedDigit())
                .foregroundColor(alert.direction.color)
        }
        .padding(12)
        .frame(minWidth: 140)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(cardBackground)
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(alert.product): \(String(format: "%.3f", alert.currentRate)) percent, \(alert.direction == .down ? "down" : "up") \(String(format: "%.3f", alert.changeAmount))")
    }

    // MARK: - Pipeline Section

    private var pipelineSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("Pipeline Overview", systemImage: "chart.bar.fill")
                .font(.title3.bold())
                .foregroundColor(.primary)

            pipelineGrid
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Pipeline overview section")
    }

    private var pipelineGrid: some View {
        let columns = pipelineColumns

        return LazyVGrid(columns: columns, spacing: 16) {
            ForEach(viewModel.pipelineStages) { stage in
                pipelineCard(stage)
            }
        }
    }

    private func pipelineCard(_ stage: PipelineStageCard) -> some View {
        VStack(spacing: 10) {
            Image(systemName: stage.icon)
                .font(.title2)
                .foregroundColor(stage.color)
                .frame(width: 44, height: 44)
                .background(
                    Circle()
                        .fill(stage.color.opacity(0.15))
                )

            Text("\(stage.count)")
                .font(.title.bold().monospacedDigit())
                .foregroundColor(.primary)

            Text(stage.stage)
                .font(.caption)
                .foregroundColor(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity)
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(cardBackground)
                .shadow(color: .black.opacity(0.05), radius: 4, x: 0, y: 2)
        )
        #if os(visionOS)
        .hoverEffect(.lift)
        #endif
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(stage.stage): \(stage.count) loans")
    }

    // MARK: - Tasks Section

    private var tasksSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Label("Today's Tasks", systemImage: "checklist")
                    .font(.title3.bold())
                    .foregroundColor(.primary)

                Spacer()

                Text("\(viewModel.tasks.count) items")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }

            if viewModel.tasks.isEmpty {
                Text("No pending tasks.")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 24)
            } else {
                LazyVStack(spacing: 10) {
                    ForEach(viewModel.tasks) { task in
                        taskRow(task)
                    }
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Today's tasks section")
    }

    private func taskRow(_ task: DashboardTask) -> some View {
        HStack(spacing: 14) {
            // Priority indicator
            Image(systemName: task.priority.icon)
                .font(.title3)
                .foregroundColor(task.priority.color)
                .frame(width: 36, height: 36)
                .background(
                    Circle()
                        .fill(task.priority.color.opacity(0.12))
                )

            // Task info
            VStack(alignment: .leading, spacing: 3) {
                Text(task.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundColor(.primary)
                    .lineLimit(1)

                Text(task.subtitle)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            // Due time
            if let dueTime = task.dueTime {
                Text(dueTime)
                    .font(.caption.monospacedDigit())
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(
                        Capsule()
                            .fill(Color(.systemGray5))
                    )
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(cardBackground)
                .shadow(color: .black.opacity(0.03), radius: 2, x: 0, y: 1)
        )
        #if os(visionOS)
        .hoverEffect(.highlight)
        #endif
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(task.priority.rawValue) priority: \(task.title). \(task.subtitle). Due \(task.dueTime ?? "no time set")")
    }

    // MARK: - Loading & Error States

    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.5)
            Text("Loading dashboard...")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.icloud.fill")
                .font(.largeTitle)
                .foregroundColor(.red)
            Text(message)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Button(action: {
                Task { await viewModel.loadData() }
            }) {
                Label("Retry", systemImage: "arrow.clockwise")
            }
            .buttonStyle(.borderedProminent)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - visionOS Ornament

    #if os(visionOS)
    private var refreshOrnament: some View {
        Button(action: {
            Task { await viewModel.loadData() }
        }) {
            Label("Refresh", systemImage: "arrow.clockwise")
                .font(.subheadline)
                .padding(8)
        }
        .buttonStyle(.bordered)
        .glassBackgroundEffect()
    }
    #endif

    // MARK: - Platform-Adaptive Styling

    private var platformPadding: EdgeInsets {
        #if os(visionOS)
        return EdgeInsets(top: 32, leading: 40, bottom: 32, trailing: 40)
        #else
        if VisionProSupport.isVisionPro {
            return EdgeInsets(top: 24, leading: 32, bottom: 24, trailing: 32)
        }
        return EdgeInsets(top: 16, leading: 16, bottom: 16, trailing: 16)
        #endif
    }

    private var pipelineColumns: [GridItem] {
        #if os(visionOS)
        return Array(repeating: GridItem(.flexible(), spacing: 16), count: 6)
        #else
        if VisionProSupport.isVisionPro {
            return Array(repeating: GridItem(.flexible(), spacing: 16), count: 6)
        }
        // 3 columns on iPad, 2 on iPhone
        let count = UIDevice.current.userInterfaceIdiom == .pad ? 3 : 2
        return Array(repeating: GridItem(.flexible(), spacing: 12), count: count)
        #endif
    }

    private var cardBackground: some ShapeStyle {
        #if os(visionOS)
        return .ultraThinMaterial
        #else
        return Color(.secondarySystemGroupedBackground)
        #endif
    }

    private var alertBannerBackground: some ShapeStyle {
        #if os(visionOS)
        return .thinMaterial
        #else
        return Color(.systemGroupedBackground)
        #endif
    }

    @ViewBuilder
    private var backgroundStyle: some View {
        #if os(visionOS)
        Color.clear
        #else
        Color(.systemGroupedBackground)
            .ignoresSafeArea()
        #endif
    }
}

// MARK: - UIKit Hosting (for use as a secondary window or embedded view)

@available(iOS 15.0, *)
final class VisionProDashboardHostingController: UIHostingController<VisionProDashboardView> {

    init() {
        super.init(rootView: VisionProDashboardView())
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        title = "Perennia AI Dashboard"

        #if os(visionOS)
        preferredContentSize = VisionProWindowConfig.preferredSize
        view.backgroundColor = .clear
        #else
        if VisionProSupport.isVisionPro {
            preferredContentSize = VisionProSupport.preferredContentSize
            view.backgroundColor = .clear
        }
        #endif
    }
}

// MARK: - Preview

#if DEBUG
@available(iOS 15.0, *)
struct VisionProDashboardView_Previews: PreviewProvider {
    static var previews: some View {
        VisionProDashboardView()
            .previewDisplayName("Dashboard")
    }
}
#endif
