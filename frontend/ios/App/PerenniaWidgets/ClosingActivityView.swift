/**
 * ClosingActivityView.swift
 * Perennia AI - Live Activity SwiftUI Views
 *
 * Renders loan closing progress on:
 * - Lock Screen (expanded and compact presentations)
 * - Dynamic Island (compact leading, compact trailing, expanded, minimal)
 *
 * Stage color scheme:
 *   Processing  = yellow
 *   Underwriting = orange
 *   CTC / Clear to Close = green
 *   Closing     = blue
 *   Funded      = emerald/teal
 *   Default     = indigo (application, conditional approval)
 */

import SwiftUI
import WidgetKit
import ActivityKit

// MARK: - Color Theme

/// Stage-aware color provider
struct ClosingColors {
    static func forStage(_ stageString: String) -> Color {
        guard let stage = ClosingStage(fromRawStage: stageString) else {
            return .indigo
        }
        return forStage(stage)
    }

    static func forStage(_ stage: ClosingStage) -> Color {
        switch stage {
        case .application:
            return .indigo
        case .processing:
            return .yellow
        case .underwriting:
            return .orange
        case .conditionalApproval:
            return .indigo
        case .ctc, .clearToClose:
            return .green
        case .closing:
            return .blue
        case .funded:
            return Color(red: 0.2, green: 0.78, blue: 0.64) // emerald
        }
    }

    /// Background gradient for the Lock Screen expanded view
    static func backgroundGradient(for stageString: String) -> LinearGradient {
        let primary = forStage(stageString)
        return LinearGradient(
            colors: [primary.opacity(0.3), primary.opacity(0.1)],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

// MARK: - Live Activity Widget Configuration

@available(iOS 16.1, *)
struct ClosingActivityLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: ClosingActivityAttributes.self) { context in
            // Lock Screen / StandBy presentation
            LockScreenView(
                attributes: context.attributes,
                state: context.state
            )
            .activityBackgroundTint(Color.black.opacity(0.85))
            .activitySystemActionForegroundColor(.white)

        } dynamicIsland: { context in
            DynamicIsland {
                // Expanded presentation
                DynamicIslandExpandedRegion(.leading) {
                    ExpandedLeadingView(attributes: context.attributes, state: context.state)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    ExpandedTrailingView(state: context.state)
                }
                DynamicIslandExpandedRegion(.center) {
                    ExpandedCenterView(attributes: context.attributes, state: context.state)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    ExpandedBottomView(state: context.state)
                }
            } compactLeading: {
                // Compact leading: loan amount
                CompactLeadingView(attributes: context.attributes)
            } compactTrailing: {
                // Compact trailing: stage abbreviation
                CompactTrailingView(state: context.state)
            } minimal: {
                // Minimal: stage icon
                MinimalView(state: context.state)
            }
        }
    }
}

// MARK: - Lock Screen Expanded View

@available(iOS 16.1, *)
struct LockScreenView: View {
    let attributes: ClosingActivityAttributes
    let state: ClosingActivityAttributes.ContentState

    private var currentStage: ClosingStage? {
        ClosingStage(fromRawStage: state.currentStage)
    }

    private var stageColor: Color {
        ClosingColors.forStage(state.currentStage)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header row: borrower name + stage badge
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(attributes.borrowerName)
                        .font(.headline)
                        .fontWeight(.semibold)
                        .foregroundColor(.white)
                        .lineLimit(1)

                    Text(attributes.propertyAddress)
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))
                        .lineLimit(1)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Loan closing status for your borrower")

                Spacer()

                // Stage badge
                Text(currentStage?.displayName ?? state.currentStage)
                    .font(.caption)
                    .fontWeight(.bold)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(stageColor.opacity(0.8))
                    .foregroundColor(.white)
                    .clipShape(Capsule())
                    .accessibilityLabel("Stage: \(currentStage?.displayName ?? state.currentStage)")
            }

            // Progress bar through stages
            StageProgressBar(
                currentStage: state.currentStage,
                progress: state.stageProgress
            )
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Loan progress: \(Int(state.stageProgress * 100)) percent, currently in \(currentStage?.displayName ?? state.currentStage)")
            .accessibilityValue("\(Int(state.stageProgress * 100)) percent complete")

            // Bottom row: next action + estimated close
            HStack {
                // Next action
                HStack(spacing: 4) {
                    Image(systemName: "arrow.forward.circle.fill")
                        .font(.caption2)
                        .foregroundColor(stageColor)
                        .accessibilityHidden(true)
                    Text(state.nextAction)
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.9))
                        .lineLimit(1)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Next step: \(state.nextAction)")

                Spacer()

                // Estimated close date
                if let estimatedClose = state.estimatedClose {
                    HStack(spacing: 4) {
                        Image(systemName: "calendar")
                            .font(.caption2)
                            .foregroundColor(.white.opacity(0.6))
                            .accessibilityHidden(true)
                        Text(estimatedClose, style: .date)
                            .font(.caption)
                            .foregroundColor(.white.opacity(0.8))
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel("Estimated closing date: \(estimatedClose, style: .date)")
                }
            }
        }
        .padding(16)
    }
}

// MARK: - Stage Progress Bar

@available(iOS 16.1, *)
struct StageProgressBar: View {
    let currentStage: String
    let progress: Double

    /// Stages to display as milestone dots on the progress bar
    private let milestoneStages: [ClosingStage] = [
        .application, .processing, .underwriting,
        .conditionalApproval, .ctc, .closing, .funded
    ]

    private var currentClosingStage: ClosingStage? {
        ClosingStage(fromRawStage: currentStage)
    }

    var body: some View {
        VStack(spacing: 4) {
            // Progress track
            GeometryReader { geometry in
                let trackWidth = geometry.size.width

                ZStack(alignment: .leading) {
                    // Background track
                    Capsule()
                        .fill(Color.white.opacity(0.15))
                        .frame(height: 4)

                    // Filled progress
                    Capsule()
                        .fill(
                            LinearGradient(
                                colors: [
                                    ClosingColors.forStage(currentStage).opacity(0.8),
                                    ClosingColors.forStage(currentStage)
                                ],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: max(0, trackWidth * CGFloat(progress)), height: 4)

                    // Milestone dots
                    ForEach(Array(milestoneStages.enumerated()), id: \.element) { index, stage in
                        let dotProgress = Double(index) / Double(max(milestoneStages.count - 1, 1))
                        let xPos = trackWidth * CGFloat(dotProgress)
                        let isReached = progress >= dotProgress
                        let isCurrent = stage == currentClosingStage

                        Circle()
                            .fill(isReached ? ClosingColors.forStage(stage) : Color.white.opacity(0.3))
                            .frame(width: isCurrent ? 8 : 5, height: isCurrent ? 8 : 5)
                            .overlay(
                                Circle()
                                    .stroke(Color.white.opacity(isCurrent ? 0.8 : 0.0), lineWidth: 1)
                            )
                            .position(x: xPos, y: 2)
                    }
                }
            }
            .frame(height: 8)

            // Stage labels (show first, current, and last)
            HStack {
                Text("Application")
                    .font(.system(size: 8))
                    .foregroundColor(.white.opacity(0.5))

                Spacer()

                if let current = currentClosingStage,
                   current != .application && current != .funded {
                    Text(current.displayName)
                        .font(.system(size: 8))
                        .fontWeight(.medium)
                        .foregroundColor(ClosingColors.forStage(current))
                }

                Spacer()

                Text("Funded")
                    .font(.system(size: 8))
                    .foregroundColor(.white.opacity(0.5))
            }
        }
    }
}

// MARK: - Dynamic Island: Compact Leading (Loan Amount)

@available(iOS 16.1, *)
struct CompactLeadingView: View {
    let attributes: ClosingActivityAttributes

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "house.fill")
                .font(.system(size: 10))
                .foregroundColor(.white.opacity(0.8))
                .accessibilityHidden(true)
            Text(attributes.loanAmount)
                .font(.caption2)
                .fontWeight(.semibold)
                .foregroundColor(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Loan amount: \(attributes.loanAmount)")
    }
}

// MARK: - Dynamic Island: Compact Trailing (Stage Abbreviation)

@available(iOS 16.1, *)
struct CompactTrailingView: View {
    let state: ClosingActivityAttributes.ContentState

    private var stageColor: Color {
        ClosingColors.forStage(state.currentStage)
    }

    private var abbreviation: String {
        ClosingStage(fromRawStage: state.currentStage)?.abbreviation ?? "---"
    }

    private var fullStageName: String {
        ClosingStage(fromRawStage: state.currentStage)?.displayName ?? state.currentStage
    }

    var body: some View {
        Text(abbreviation)
            .font(.caption2)
            .fontWeight(.bold)
            .foregroundColor(stageColor)
            .padding(.horizontal, 4)
            .accessibilityLabel("Stage: \(fullStageName)")
    }
}

// MARK: - Dynamic Island: Minimal (Stage Icon)

@available(iOS 16.1, *)
struct MinimalView: View {
    let state: ClosingActivityAttributes.ContentState

    private var iconName: String {
        ClosingStage(fromRawStage: state.currentStage)?.iconName ?? "doc.text"
    }

    private var stageColor: Color {
        ClosingColors.forStage(state.currentStage)
    }

    private var fullStageName: String {
        ClosingStage(fromRawStage: state.currentStage)?.displayName ?? state.currentStage
    }

    var body: some View {
        Image(systemName: iconName)
            .font(.system(size: 12))
            .foregroundColor(stageColor)
            .accessibilityLabel("Loan closing: \(fullStageName)")
    }
}

// MARK: - Dynamic Island: Expanded Leading

@available(iOS 16.1, *)
struct ExpandedLeadingView: View {
    let attributes: ClosingActivityAttributes
    let state: ClosingActivityAttributes.ContentState

    private var stageColor: Color {
        ClosingColors.forStage(state.currentStage)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Image(systemName: "house.fill")
                .font(.title3)
                .foregroundColor(stageColor)
                .accessibilityHidden(true)

            Text(attributes.loanAmount)
                .font(.caption2)
                .fontWeight(.semibold)
                .foregroundColor(.white)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Loan amount: \(attributes.loanAmount)")
    }
}

// MARK: - Dynamic Island: Expanded Trailing

@available(iOS 16.1, *)
struct ExpandedTrailingView: View {
    let state: ClosingActivityAttributes.ContentState

    private var stageColor: Color {
        ClosingColors.forStage(state.currentStage)
    }

    private var fullStageName: String {
        ClosingStage(fromRawStage: state.currentStage)?.displayName ?? state.currentStage
    }

    var body: some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text(fullStageName)
                .font(.caption2)
                .fontWeight(.bold)
                .foregroundColor(stageColor)

            // Progress percentage
            Text("\(Int(state.stageProgress * 100))%")
                .font(.caption)
                .fontWeight(.heavy)
                .foregroundColor(.white)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(fullStageName), \(Int(state.stageProgress * 100)) percent complete")
    }
}

// MARK: - Dynamic Island: Expanded Center (Borrower + Progress)

@available(iOS 16.1, *)
struct ExpandedCenterView: View {
    let attributes: ClosingActivityAttributes
    let state: ClosingActivityAttributes.ContentState

    var body: some View {
        VStack(spacing: 4) {
            Text(attributes.borrowerName)
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundColor(.white)
                .lineLimit(1)
                .accessibilityLabel("Borrower loan progress")

            // Compact progress bar for Dynamic Island
            ProgressView(value: state.stageProgress)
                .tint(ClosingColors.forStage(state.currentStage))
                .scaleEffect(y: 1.5)
                .accessibilityLabel("Closing progress")
                .accessibilityValue("\(Int(state.stageProgress * 100)) percent")
        }
    }
}

// MARK: - Dynamic Island: Expanded Bottom (Next Action)

@available(iOS 16.1, *)
struct ExpandedBottomView: View {
    let state: ClosingActivityAttributes.ContentState

    var body: some View {
        HStack {
            HStack(spacing: 4) {
                Image(systemName: "arrow.forward.circle.fill")
                    .font(.caption2)
                    .foregroundColor(ClosingColors.forStage(state.currentStage))
                    .accessibilityHidden(true)
                Text(state.nextAction)
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.9))
                    .lineLimit(1)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Next step: \(state.nextAction)")

            Spacer()

            if let estimatedClose = state.estimatedClose {
                HStack(spacing: 2) {
                    Image(systemName: "calendar")
                        .font(.system(size: 8))
                        .foregroundColor(.white.opacity(0.6))
                        .accessibilityHidden(true)
                    Text(estimatedClose, style: .date)
                        .font(.system(size: 9))
                        .foregroundColor(.white.opacity(0.7))
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Estimated close: \(estimatedClose, style: .date)")
            }
        }
    }
}

// MARK: - Previews

#if DEBUG
@available(iOS 17.0, *)
#Preview("Lock Screen", as: .content, using: ClosingActivityAttributes(
    borrowerName: "John & Jane Smith",
    loanAmount: "$425,000",
    propertyAddress: "123 Main St, Charleston, SC 29401",
    loanId: "loan-abc-123"
)) {
    ClosingActivityLiveActivity()
} contentStates: {
    ClosingActivityAttributes.ContentState(
        currentStage: "UNDERWRITING",
        stageProgress: 0.35,
        lastUpdate: Date(),
        nextAction: "Awaiting underwriter review",
        estimatedClose: Calendar.current.date(byAdding: .day, value: 14, to: Date())
    )
    ClosingActivityAttributes.ContentState(
        currentStage: "CTC",
        stageProgress: 0.65,
        lastUpdate: Date(),
        nextAction: "Title company preparing documents",
        estimatedClose: Calendar.current.date(byAdding: .day, value: 7, to: Date())
    )
    ClosingActivityAttributes.ContentState(
        currentStage: "FUNDED",
        stageProgress: 1.0,
        lastUpdate: Date(),
        nextAction: "Loan funded — congratulations!",
        estimatedClose: nil
    )
}
#endif
