/**
 * ClosingActivityAttributes.swift
 * Shared ActivityAttributes definition used by both the App target
 * (LiveActivityManager) and the PerenniaWidgets target (ClosingActivityView).
 */

import Foundation
import ActivityKit

struct ClosingActivityAttributes: ActivityAttributes {
    let borrowerName: String
    let loanAmount: String
    let propertyAddress: String
    let loanId: String

    struct ContentState: Codable, Hashable {
        let currentStage: String
        let stageProgress: Double
        let lastUpdate: Date
        let nextAction: String
        let estimatedClose: Date?
    }
}
