/**
 * ClosingActivity.swift
 * Perennia AI - Live Activity for Loan Closing Status
 *
 * Defines the ActivityAttributes and ContentState for real-time
 * loan closing progress on the iOS Lock Screen and Dynamic Island.
 *
 * Requirements:
 * - iOS 16.1+ for Live Activities
 * - iOS 16.2+ for ActivityKit push token updates
 * - Bundle: com.perenniaai.crm
 *
 * Loan stages tracked (subset used for closing progress):
 *   APPLICATION -> PROCESSING -> UNDERWRITING -> CONDITIONAL_APPROVAL
 *   -> CTC -> CLEAR_TO_CLOSE -> CLOSING -> FUNDED
 */

import Foundation
import ActivityKit

// ClosingActivityAttributes is defined in App/ClosingActivityAttributes.swift
// and compiled into this target via shared source membership in the Xcode project.

// MARK: - Stage Definitions

/// The ordered stages used for closing progress calculation.
/// This is the subset of full loan stages relevant to the closing pipeline.
enum ClosingStage: String, CaseIterable, Codable {
    case application = "APPLICATION"
    case processing = "PROCESSING"
    case underwriting = "UNDERWRITING"
    case conditionalApproval = "CONDITIONAL_APPROVAL"
    case ctc = "CTC"
    case clearToClose = "CLEAR_TO_CLOSE"
    case closing = "CLOSING"
    case funded = "FUNDED"

    /// Zero-based index in the pipeline
    var index: Int {
        return ClosingStage.allCases.firstIndex(of: self) ?? 0
    }

    /// Total number of stages
    static var totalStages: Int {
        return ClosingStage.allCases.count
    }

    /// Progress as a fraction (0.0 - 1.0) for this stage
    var progress: Double {
        guard ClosingStage.totalStages > 1 else { return 0.0 }
        return Double(index) / Double(ClosingStage.totalStages - 1)
    }

    /// Short abbreviation for Dynamic Island compact trailing
    var abbreviation: String {
        switch self {
        case .application: return "APP"
        case .processing: return "PROC"
        case .underwriting: return "UW"
        case .conditionalApproval: return "CA"
        case .ctc: return "CTC"
        case .clearToClose: return "C2C"
        case .closing: return "CLO"
        case .funded: return "FND"
        }
    }

    /// Human-readable display name
    var displayName: String {
        switch self {
        case .application: return "Application"
        case .processing: return "Processing"
        case .underwriting: return "Underwriting"
        case .conditionalApproval: return "Conditional Approval"
        case .ctc: return "Clear to Close"
        case .clearToClose: return "Clear to Close"
        case .closing: return "Closing"
        case .funded: return "Funded"
        }
    }

    /// SF Symbol name for the stage
    var iconName: String {
        switch self {
        case .application: return "doc.text"
        case .processing: return "gearshape.2"
        case .underwriting: return "magnifyingglass.circle"
        case .conditionalApproval: return "checkmark.circle"
        case .ctc: return "checkmark.seal"
        case .clearToClose: return "checkmark.seal.fill"
        case .closing: return "signature"
        case .funded: return "banknote"
        }
    }

    /// Initialize from a raw stage string, mapping intermediate stages
    /// to their closest closing pipeline equivalent
    init?(fromRawStage raw: String) {
        let upper = raw.uppercased()

        // Direct match
        if let direct = ClosingStage(rawValue: upper) {
            self = direct
            return
        }

        // Map intermediate stages that aren't in the closing subset
        switch upper {
        case "DISCLOSED", "SUBMITTED":
            self = .processing
        case "UW_RECEIVED":
            self = .underwriting
        case "APPROVED":
            self = .conditionalApproval
        case "SUSPENDED":
            self = .underwriting  // Suspended goes back to UW review
        case "DOCS", "DOCS_OUT":
            self = .closing
        default:
            return nil
        }
    }
}
