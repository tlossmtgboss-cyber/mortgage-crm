/**
 * PerenniaWidget.swift
 * Perennia AI Widget Extension — Home Screen Pipeline & Tasks Widget
 *
 * Provides three widget sizes:
 *   - Small:  Pipeline count + tasks due today badge
 *   - Medium: Pipeline stage breakdown (color-coded) + top 3 tasks
 *   - Large:  Full pipeline breakdown + tasks + recent lead
 *
 * Timeline refreshes every 30 minutes. Data is fetched from the Perennia
 * API via NetworkService and cached in the App Group container.
 *
 * Deep links open the Capacitor app to the relevant page:
 *   - perenniaai://pipeline  (pipeline view)
 *   - perenniaai://tasks     (task list)
 */

import WidgetKit
import SwiftUI

// MARK: - Timeline Entry

struct PerenniaWidgetEntry: TimelineEntry {
    let date: Date
    let data: WidgetData
    let isPlaceholder: Bool

    static var placeholder: PerenniaWidgetEntry {
        PerenniaWidgetEntry(
            date: Date(),
            data: WidgetData(
                pipeline: PipelineSummaryData(
                    activeLoans: 0,
                    closingSoon: 0,
                    totalVolume: 0,
                    stages: [
                        PipelineStage(id: "application", name: "Application", count: 0, volume: 0),
                        PipelineStage(id: "processing", name: "Processing", count: 0, volume: 0),
                        PipelineStage(id: "underwriting", name: "Underwriting", count: 0, volume: 0),
                        PipelineStage(id: "ctc", name: "Clear to Close", count: 0, volume: 0),
                        PipelineStage(id: "closing", name: "Closing", count: 0, volume: 0),
                    ],
                    tasksDueToday: 0
                ),
                tasks: [
                    WidgetTask(id: 1, title: "Loading...", priority: "normal", dueDate: nil, status: "pending", contactName: nil),
                    WidgetTask(id: 2, title: "Loading...", priority: "normal", dueDate: nil, status: "pending", contactName: nil),
                    WidgetTask(id: 3, title: "Loading...", priority: "normal", dueDate: nil, status: "pending", contactName: nil),
                ],
                recentLeads: [
                    RecentLead(name: "Loading...", stage: nil, createdAt: nil),
                ],
                lastUpdated: Date(),
                isAuthenticated: true
            ),
            isPlaceholder: true
        )
    }
}

// MARK: - Timeline Provider

struct PerenniaTimelineProvider: TimelineProvider {

    typealias Entry = PerenniaWidgetEntry

    func placeholder(in context: Context) -> PerenniaWidgetEntry {
        .placeholder
    }

    func getSnapshot(in context: Context, completion: @escaping (PerenniaWidgetEntry) -> Void) {
        if context.isPreview {
            completion(.placeholder)
            return
        }

        Task {
            let data = await WidgetNetworkService.shared.fetchWidgetData()
            let entry = PerenniaWidgetEntry(date: Date(), data: data, isPlaceholder: false)
            completion(entry)
        }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<PerenniaWidgetEntry>) -> Void) {
        Task {
            let data = await WidgetNetworkService.shared.fetchWidgetData()
            let entry = PerenniaWidgetEntry(date: Date(), data: data, isPlaceholder: false)

            // Refresh every 30 minutes
            let nextUpdate = Calendar.current.date(byAdding: .minute, value: 30, to: Date())!
            let timeline = Timeline(entries: [entry], policy: .after(nextUpdate))
            completion(timeline)
        }
    }
}

// MARK: - Stage Colors

extension PipelineStage {

    var stageColor: Color {
        switch id.lowercased() {
        case "application", "disclosed":
            return Color(red: 0.25, green: 0.48, blue: 0.85)       // Blue
        case "processing", "submitted", "in_processing":
            return Color(red: 0.90, green: 0.72, blue: 0.15)       // Yellow/Gold
        case "underwriting", "uw_received", "conditional_approval", "in_underwriting":
            return Color(red: 0.92, green: 0.55, blue: 0.15)       // Orange
        case "ctc", "clear_to_close", "approved":
            return Color(red: 0.25, green: 0.75, blue: 0.40)       // Green
        case "closing", "docs", "docs_out":
            return Color(red: 0.58, green: 0.35, blue: 0.78)       // Purple
        case "funded", "funded_this_month":
            return Color(red: 0.10, green: 0.70, blue: 0.55)       // Emerald
        default:
            return Color.secondary
        }
    }
}

// MARK: - Priority Colors

extension TaskPriority {

    var color: Color {
        switch self {
        case .urgent:
            return .red
        case .normal:
            return Color(red: 0.90, green: 0.72, blue: 0.15)
        case .low:
            return Color(.systemGray3)
        }
    }
}

// MARK: - Brand Colors

enum PerenniaBrand {
    static let primary = Color(red: 0.15, green: 0.30, blue: 0.55)
    static let accent = Color(red: 0.25, green: 0.48, blue: 0.85)
    static let darkBackground = Color(red: 0.08, green: 0.10, blue: 0.15)
    static let cardBackground = Color(red: 0.12, green: 0.14, blue: 0.20)
}

// MARK: - Formatters

private let volumeFormatter: NumberFormatter = {
    let f = NumberFormatter()
    f.numberStyle = .currency
    f.maximumFractionDigits = 0
    f.currencySymbol = "$"
    return f
}()

private let compactVolumeFormatter: NumberFormatter = {
    let f = NumberFormatter()
    f.numberStyle = .decimal
    f.maximumFractionDigits = 1
    return f
}()

private func formatVolume(_ value: Double) -> String {
    if value >= 1_000_000 {
        let millions = value / 1_000_000
        return "$\(compactVolumeFormatter.string(from: NSNumber(value: millions)) ?? "0")M"
    } else if value >= 1_000 {
        let thousands = value / 1_000
        return "$\(compactVolumeFormatter.string(from: NSNumber(value: thousands)) ?? "0")K"
    } else {
        return volumeFormatter.string(from: NSNumber(value: value)) ?? "$0"
    }
}

// MARK: - PII Masking Helpers

/// Masks a full name to initials: "John Smith" -> "J. S.", "Jane Mary Doe" -> "J. D."
private func maskName(_ name: String) -> String {
    let components = name.trimmingCharacters(in: .whitespaces)
        .split(separator: " ")
        .map(String.init)
    guard !components.isEmpty else { return "---" }
    if components.count == 1 {
        return String(components[0].prefix(1)).uppercased() + "."
    }
    let first = String(components.first!.prefix(1)).uppercased()
    let last = String(components.last!.prefix(1)).uppercased()
    return "\(first). \(last)."
}

/// Masks a dollar amount to a range: $425,500 -> "$400K-$500K", $1,250,000 -> "$1.0M-$1.5M"
private func maskAmount(_ value: Double) -> String {
    if value >= 1_000_000 {
        let lowerM = floor(value / 500_000) * 500_000 / 1_000_000
        let upperM = lowerM + 0.5
        return String(format: "$%.1fM-$%.1fM", lowerM, upperM)
    } else if value >= 1_000 {
        let lowerK = floor(value / 100_000) * 100
        let upperK = lowerK + 100
        return "$\(Int(lowerK))K-$\(Int(upperK))K"
    } else {
        return "$0"
    }
}

/// Masks a lead display string: "New lead: David Park" -> "New lead: D. P."
private func maskLeadDisplay(_ display: String) -> String {
    // Handle "prefix: Name" pattern (e.g., "New lead: David Park")
    if let colonRange = display.range(of: ": ") {
        let prefix = String(display[display.startIndex..<colonRange.lowerBound])
        let namePart = String(display[colonRange.upperBound...])
        return "\(prefix): \(maskName(namePart))"
    }
    // Otherwise mask the whole string as a name
    return maskName(display)
}

// MARK: - Small Widget View

struct SmallWidgetView: View {
    let entry: PerenniaWidgetEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Header
            HStack {
                Image(systemName: "chart.bar.fill")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(PerenniaBrand.accent)
                    .accessibilityHidden(true)
                Text("Pipeline")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.secondary)
                Spacer()
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Pipeline overview")

            if !entry.data.isAuthenticated {
                Spacer()
                VStack(spacing: 4) {
                    Image(systemName: "lock.fill")
                        .font(.system(size: 24))
                        .foregroundColor(.secondary)
                        .accessibilityHidden(true)
                    Text("Sign in to\nPerennia AI")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Sign in to Perennia AI to view your pipeline")
                Spacer()
            } else {
                // Active loans count
                HStack(alignment: .firstTextBaseline, spacing: 2) {
                    Text("\(entry.data.pipeline.activeLoans)")
                        .font(.system(size: 36, weight: .bold, design: .rounded))
                        .foregroundColor(.primary)
                    Text("active")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(.secondary)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("\(entry.data.pipeline.activeLoans) active loans")

                Spacer()

                // Volume (masked range)
                Text(maskAmount(entry.data.pipeline.totalVolume))
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundColor(PerenniaBrand.accent)
                    .accessibilityLabel("Pipeline volume: \(maskAmount(entry.data.pipeline.totalVolume))")

                // Tasks badge
                HStack(spacing: 4) {
                    Image(systemName: "checklist")
                        .font(.system(size: 10))
                        .accessibilityHidden(true)
                    Text("\(entry.data.pipeline.tasksDueToday) tasks today")
                        .font(.system(size: 11, weight: .medium))
                }
                .foregroundColor(entry.data.pipeline.tasksDueToday > 0 ? .orange : .secondary)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("\(entry.data.pipeline.tasksDueToday) tasks due today")
            }
        }
        .padding(14)
        .widgetURL(URL(string: "\(WidgetConstants.deepLinkScheme)://pipeline"))
    }
}

// MARK: - Medium Widget View

struct MediumWidgetView: View {
    let entry: PerenniaWidgetEntry

    var body: some View {
        if !entry.data.isAuthenticated {
            loginRequiredView
        } else {
            HStack(spacing: 12) {
                // Left: Pipeline stages
                pipelineColumn
                    .frame(maxWidth: .infinity)

                Divider()
                    .background(Color.secondary.opacity(0.3))

                // Right: Today's tasks
                tasksColumn
                    .frame(maxWidth: .infinity)
            }
            .padding(14)
        }
    }

    private var loginRequiredView: some View {
        HStack(spacing: 16) {
            VStack(spacing: 8) {
                Image(systemName: "lock.fill")
                    .font(.system(size: 28))
                    .foregroundColor(.secondary)
                    .accessibilityHidden(true)
                Text("Sign in to Perennia AI")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.secondary)
                Text("Open the app to connect your pipeline")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary.opacity(0.7))
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity)
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Sign in required. Open Perennia AI to connect your pipeline.")
        }
        .padding(14)
        .widgetURL(URL(string: "\(WidgetConstants.deepLinkScheme)://login"))
    }

    private var pipelineColumn: some View {
        VStack(alignment: .leading, spacing: 6) {
            // Header
            HStack {
                Image(systemName: "chart.bar.fill")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(PerenniaBrand.accent)
                    .accessibilityHidden(true)
                Text("Pipeline")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(.primary)
                Spacer()
                Text("\(entry.data.pipeline.activeLoans)")
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundColor(PerenniaBrand.accent)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Pipeline: \(entry.data.pipeline.activeLoans) active loans")

            if entry.data.pipeline.stages.isEmpty {
                Spacer()
                Text("No active loans")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                Spacer()
            } else {
                // Stage breakdown (mini bar chart)
                let maxCount = entry.data.pipeline.stages.map(\.count).max() ?? 1

                ForEach(entry.data.pipeline.stages.prefix(5)) { stage in
                    HStack(spacing: 6) {
                        Circle()
                            .fill(stage.stageColor)
                            .frame(width: 6, height: 6)
                            .accessibilityHidden(true)

                        Text(stage.displayName)
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                            .frame(width: 58, alignment: .leading)

                        // Mini bar
                        GeometryReader { geo in
                            let barWidth = max(4, geo.size.width * CGFloat(stage.count) / CGFloat(max(maxCount, 1)))
                            RoundedRectangle(cornerRadius: 2)
                                .fill(stage.stageColor.opacity(0.75))
                                .frame(width: barWidth, height: 8)
                                .frame(maxHeight: .infinity, alignment: .center)
                        }
                        .frame(height: 12)
                        .accessibilityHidden(true)

                        Text("\(stage.count)")
                            .font(.system(size: 10, weight: .semibold, design: .rounded))
                            .foregroundColor(.primary)
                            .frame(width: 18, alignment: .trailing)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel("\(stage.displayName): \(stage.count) loans")
                }
            }

            Spacer(minLength: 0)

            // Volume footer (masked range)
            Text(maskAmount(entry.data.pipeline.totalVolume))
                .font(.system(size: 10, weight: .semibold, design: .rounded))
                .foregroundColor(PerenniaBrand.accent)
                .accessibilityLabel("Pipeline volume: \(maskAmount(entry.data.pipeline.totalVolume))")
        }
        .widgetURL(URL(string: "\(WidgetConstants.deepLinkScheme)://pipeline"))
    }

    private var tasksColumn: some View {
        VStack(alignment: .leading, spacing: 6) {
            // Header
            HStack {
                Image(systemName: "checklist")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.orange)
                    .accessibilityHidden(true)
                Text("Today")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(.primary)
                Spacer()
                if entry.data.pipeline.tasksDueToday > 0 {
                    Text("\(entry.data.pipeline.tasksDueToday)")
                        .font(.system(size: 10, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Capsule().fill(Color.orange))
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Today's tasks: \(entry.data.pipeline.tasksDueToday) due")

            if entry.data.tasks.isEmpty {
                Spacer()
                VStack(spacing: 4) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 20))
                        .foregroundColor(.green)
                        .accessibilityHidden(true)
                    Text("All clear")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("All tasks complete")
                Spacer()
            } else {
                ForEach(entry.data.tasks.prefix(3)) { task in
                    HStack(spacing: 6) {
                        Circle()
                            .fill(task.priorityLevel.color)
                            .frame(width: 6, height: 6)
                            .accessibilityHidden(true)

                        VStack(alignment: .leading, spacing: 1) {
                            Text(task.title)
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(.primary)
                                .lineLimit(1)

                            if let time = task.dueTimeString as String?, !time.isEmpty {
                                Text(time)
                                    .font(.system(size: 9))
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel("Task: \(task.title)\(task.dueTimeString.isEmpty ? "" : ", due \(task.dueTimeString)")")
                }

                Spacer(minLength: 0)

                if entry.data.tasks.count > 3 {
                    Text("+\(entry.data.tasks.count - 3) more")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .accessibilityLabel("\(entry.data.tasks.count - 3) more tasks")
                }
            }
        }
    }
}

// MARK: - Large Widget View

struct LargeWidgetView: View {
    let entry: PerenniaWidgetEntry

    var body: some View {
        if !entry.data.isAuthenticated {
            largeLoginView
        } else {
            VStack(alignment: .leading, spacing: 10) {
                // Header
                headerSection

                Divider()
                    .background(Color.secondary.opacity(0.3))

                // Pipeline breakdown
                pipelineSection

                Divider()
                    .background(Color.secondary.opacity(0.3))

                // Tasks
                tasksSection

                // Recent lead
                if let lead = entry.data.recentLeads.first {
                    Divider()
                        .background(Color.secondary.opacity(0.3))
                    recentLeadRow(lead)
                }

                Spacer(minLength: 0)

                // Last updated
                lastUpdatedFooter
            }
            .padding(14)
            .widgetURL(URL(string: "\(WidgetConstants.deepLinkScheme)://pipeline"))
        }
    }

    private var largeLoginView: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "lock.shield.fill")
                .font(.system(size: 40))
                .foregroundColor(PerenniaBrand.accent)
                .accessibilityHidden(true)
            Text("Sign in to Perennia AI")
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(.primary)
            Text("Open the app to see your pipeline,\ntasks, and recent activity")
                .font(.system(size: 13))
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Spacer()
        }
        .frame(maxWidth: .infinity)
        .padding(14)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Sign in required. Open Perennia AI to see your pipeline, tasks, and recent activity.")
        .widgetURL(URL(string: "\(WidgetConstants.deepLinkScheme)://login"))
    }

    private var headerSection: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Perennia AI")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(.primary)
                Text("Pipeline Overview")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Perennia AI Pipeline Overview")

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                Text("\(entry.data.pipeline.activeLoans) Active")
                    .font(.system(size: 16, weight: .bold, design: .rounded))
                    .foregroundColor(PerenniaBrand.accent)
                Text(maskAmount(entry.data.pipeline.totalVolume))
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundColor(.secondary)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("\(entry.data.pipeline.activeLoans) active loans, volume \(maskAmount(entry.data.pipeline.totalVolume))")
        }
    }

    private var pipelineSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: "chart.bar.fill")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(PerenniaBrand.accent)
                    .accessibilityHidden(true)
                Text("Stages")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(.primary)
                Spacer()
                if entry.data.pipeline.closingSoon > 0 {
                    HStack(spacing: 3) {
                        Image(systemName: "star.fill")
                            .font(.system(size: 8))
                            .accessibilityHidden(true)
                        Text("\(entry.data.pipeline.closingSoon) closing")
                            .font(.system(size: 10, weight: .medium))
                    }
                    .foregroundColor(.green)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Pipeline stages\(entry.data.pipeline.closingSoon > 0 ? ", \(entry.data.pipeline.closingSoon) closing soon" : "")")

            if entry.data.pipeline.stages.isEmpty {
                Text("No active pipeline data")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .padding(.vertical, 4)
            } else {
                let maxCount = entry.data.pipeline.stages.map(\.count).max() ?? 1

                ForEach(entry.data.pipeline.stages.prefix(7)) { stage in
                    HStack(spacing: 8) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(stage.stageColor)
                            .frame(width: 4, height: 16)
                            .accessibilityHidden(true)

                        Text(stage.displayName)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.primary)
                            .frame(width: 80, alignment: .leading)
                            .lineLimit(1)

                        // Progress bar
                        GeometryReader { geo in
                            let barWidth = max(6, geo.size.width * CGFloat(stage.count) / CGFloat(max(maxCount, 1)))
                            ZStack(alignment: .leading) {
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(Color.secondary.opacity(0.1))
                                    .frame(height: 10)
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(stage.stageColor.opacity(0.8))
                                    .frame(width: barWidth, height: 10)
                            }
                            .frame(maxHeight: .infinity, alignment: .center)
                        }
                        .frame(height: 16)
                        .accessibilityHidden(true)

                        Text("\(stage.count)")
                            .font(.system(size: 11, weight: .bold, design: .rounded))
                            .foregroundColor(.primary)
                            .frame(width: 24, alignment: .trailing)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel("\(stage.displayName): \(stage.count) loans")
                }
            }
        }
    }

    private var tasksSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: "checklist")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.orange)
                    .accessibilityHidden(true)
                Text("Today's Tasks")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(.primary)
                Spacer()
                if entry.data.pipeline.tasksDueToday > 0 {
                    Text("\(entry.data.pipeline.tasksDueToday) due")
                        .font(.system(size: 10, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Capsule().fill(Color.orange))
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Today's tasks: \(entry.data.pipeline.tasksDueToday) due")

            if entry.data.tasks.isEmpty {
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 14))
                        .foregroundColor(.green)
                        .accessibilityHidden(true)
                    Text("All tasks complete")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .padding(.vertical, 2)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("All tasks complete")
            } else {
                ForEach(entry.data.tasks.prefix(5)) { task in
                    HStack(spacing: 8) {
                        Circle()
                            .fill(task.priorityLevel.color)
                            .frame(width: 7, height: 7)
                            .accessibilityHidden(true)

                        VStack(alignment: .leading, spacing: 1) {
                            Text(task.title)
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(.primary)
                                .lineLimit(1)

                            HStack(spacing: 4) {
                                if let contact = task.contactName, !contact.isEmpty {
                                    Text(maskName(contact))
                                        .font(.system(size: 9))
                                        .foregroundColor(.secondary)
                                }
                                if let time = task.dueTimeString as String?, !time.isEmpty {
                                    Text(time)
                                        .font(.system(size: 9))
                                        .foregroundColor(.secondary)
                                }
                            }
                        }

                        Spacer(minLength: 0)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel({
                        var label = "Task: \(task.title)"
                        if let contact = task.contactName, !contact.isEmpty {
                            label += ", for lead \(maskName(contact))"
                        }
                        if !task.dueTimeString.isEmpty {
                            label += ", due \(task.dueTimeString)"
                        }
                        return label
                    }())
                }
            }
        }
    }

    private func recentLeadRow(_ lead: RecentLead) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "person.badge.plus")
                .font(.system(size: 12))
                .foregroundColor(PerenniaBrand.accent)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 1) {
                Text(maskLeadDisplay(lead.name))
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.primary)
                    .lineLimit(1)
                if let stage = lead.stage {
                    Text(stage)
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                }
            }

            Spacer()

            if let time = lead.createdAt {
                Text(time)
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel({
            // Announce masked initials as "Recent lead" instead of spelling out letters
            var label = "Recent lead"
            if let stage = lead.stage {
                label += ", \(stage)"
            }
            if let time = lead.createdAt {
                label += ", \(time)"
            }
            return label
        }())
    }

    private var lastUpdatedFooter: some View {
        HStack {
            Spacer()
            if entry.data.lastUpdated.timeIntervalSinceNow > -120 {
                Text("Just updated")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary.opacity(0.6))
                    .accessibilityLabel("Data just updated")
            } else {
                let formatter = RelativeDateTimeFormatter()
                Text("Updated \(formatter.localizedString(for: entry.data.lastUpdated, relativeTo: Date()))")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary.opacity(0.6))
                    .accessibilityLabel("Data updated \(formatter.localizedString(for: entry.data.lastUpdated, relativeTo: Date()))")
            }
        }
    }
}

// MARK: - Widget Configuration

struct PerenniaWidget: Widget {
    let kind: String = "PerenniaWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: PerenniaTimelineProvider()) { entry in
            if #available(iOS 17.0, *) {
                PerenniaWidgetEntryView(entry: entry)
                    .containerBackground(.fill.tertiary, for: .widget)
            } else {
                PerenniaWidgetEntryView(entry: entry)
                    .padding()
                    .background()
            }
        }
        .configurationDisplayName("Pipeline & Tasks")
        .description("See your active loan pipeline and today's tasks at a glance.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
        .contentMarginsDisabled()
    }
}

// MARK: - Entry View Router

struct PerenniaWidgetEntryView: View {
    @Environment(\.widgetFamily) var family
    let entry: PerenniaWidgetEntry

    var body: some View {
        switch family {
        case .systemSmall:
            SmallWidgetView(entry: entry)
        case .systemMedium:
            MediumWidgetView(entry: entry)
        case .systemLarge:
            LargeWidgetView(entry: entry)
        default:
            SmallWidgetView(entry: entry)
        }
    }
}

// MARK: - Previews

#if DEBUG
struct PerenniaWidget_Previews: PreviewProvider {
    static var previews: some View {
        Group {
            PerenniaWidgetEntryView(entry: .placeholder)
                .previewContext(WidgetPreviewContext(family: .systemSmall))
                .previewDisplayName("Small")

            PerenniaWidgetEntryView(entry: .placeholder)
                .previewContext(WidgetPreviewContext(family: .systemMedium))
                .previewDisplayName("Medium")

            PerenniaWidgetEntryView(entry: .placeholder)
                .previewContext(WidgetPreviewContext(family: .systemLarge))
                .previewDisplayName("Large")

            // Dark mode
            PerenniaWidgetEntryView(entry: .placeholder)
                .previewContext(WidgetPreviewContext(family: .systemMedium))
                .previewDisplayName("Medium (Dark)")
                .environment(\.colorScheme, .dark)
        }
    }
}
#endif
