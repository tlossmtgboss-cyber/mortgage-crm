//
//  CarPlayVoiceHandler.swift
//  App
//
//  Handles natural language voice commands from CarPlay.
//  Parses intent from spoken input, executes the corresponding API call
//  via CarPlayAPIService, and returns a spoken response string for TTS.
//
//  Supported commands:
//    "show pipeline" / "pipeline status" / "how's my pipeline"
//    "call [name]" / "phone [name]"
//    "complete task" / "finish task" / "mark task done"
//    "what's my schedule" / "upcoming meetings" / "calendar"
//    "how many leads" / "lead count" / "new leads"
//    "rate alerts" / "rate update" / "what are rates"
//    "task summary" / "pending tasks" / "what tasks"
//    "loan status" / "active loans"
//

import Foundation
import os.log

// MARK: - CarPlayVoiceHandler

/// Processes natural language voice commands for hands-free CRM operation
/// while driving. Each command maps to one or more CarPlayAPIService calls
/// and produces a spoken English response suitable for text-to-speech.
@available(iOS 14.0, *)
final class CarPlayVoiceHandler {

    // MARK: - Singleton

    static let shared = CarPlayVoiceHandler()

    // MARK: - Properties

    private let api: CarPlayAPIService
    private let log = OSLog(subsystem: "com.perenniaai.crm", category: "CarPlayVoice")

    /// Recognized command intents, ordered by matching priority.
    private enum Intent {
        case showPipeline
        case callContact(name: String)
        case completeTask
        case showSchedule
        case leadCount
        case rateAlerts
        case taskSummary
        case loanStatus
        case help
        case unknown(raw: String)
    }

    // MARK: - Init

    /// Creates a voice handler backed by the given API service.
    /// - Parameter apiService: The API service to use. Defaults to the shared singleton.
    init(apiService: CarPlayAPIService = .shared) {
        self.api = apiService
    }

    // MARK: - Public API

    /// Parse a natural language voice command and execute the corresponding action.
    ///
    /// - Parameter command: Raw spoken text from the CarPlay voice recognition system.
    /// - Returns: A spoken response string suitable for text-to-speech output.
    ///
    /// This method never throws. On any error it returns a graceful spoken message
    /// describing the problem.
    func handleCommand(_ command: String) async -> String {
        let trimmed = command.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return "I didn't catch that. Try saying: show pipeline, call a client, or what's my schedule."
        }

        os_log("Voice command received: %{public}@", log: log, type: .info, trimmed)

        let intent = parseIntent(trimmed)
        os_log("Parsed intent: %{public}@", log: log, type: .debug, String(describing: intent))

        do {
            switch intent {
            case .showPipeline:
                return try await handlePipeline()
            case .callContact(let name):
                return try await handleCall(name: name)
            case .completeTask:
                return try await handleCompleteTask()
            case .showSchedule:
                return try await handleSchedule()
            case .leadCount:
                return try await handleLeadCount()
            case .rateAlerts:
                return try await handleRateAlerts()
            case .taskSummary:
                return try await handleTaskSummary()
            case .loanStatus:
                return try await handleLoanStatus()
            case .help:
                return handleHelp()
            case .unknown(let raw):
                os_log("Unrecognized command: %{public}@", log: log, type: .info, raw)
                return "I didn't understand \"\(raw)\". Try: show pipeline, call someone, what's my schedule, rate alerts, or pending tasks."
            }
        } catch let error as CarPlayAPIError {
            os_log("API error handling command: %{public}@", log: log, type: .error, error.localizedDescription)
            return error.spokenMessage
        } catch {
            os_log("Unexpected error handling command: %{public}@", log: log, type: .error, error.localizedDescription)
            return "Something went wrong. Please try again."
        }
    }

    // MARK: - Intent Parsing

    /// Map raw command text to a structured intent.
    ///
    /// Uses keyword matching on the lowercased input. More specific patterns
    /// are checked first so "call John" is not confused with "calendar".
    private func parseIntent(_ command: String) -> Intent {
        let lower = command.lowercased()

        // "call [name]" / "phone [name]" / "dial [name]"
        if let name = extractCallTarget(from: lower) {
            return .callContact(name: name)
        }

        // Pipeline / dashboard
        if matchesAny(lower, patterns: ["pipeline", "show pipeline", "pipeline status",
                                        "how's my pipeline", "how is my pipeline",
                                        "dashboard", "show dashboard"]) {
            return .showPipeline
        }

        // Complete task
        if matchesAny(lower, patterns: ["complete task", "finish task", "mark task done",
                                        "done with task", "task complete", "mark done"]) {
            return .completeTask
        }

        // Schedule / calendar
        if matchesAny(lower, patterns: ["schedule", "my schedule", "what's my schedule",
                                        "upcoming meetings", "calendar", "appointments",
                                        "what's next", "next meeting", "next appointment"]) {
            return .showSchedule
        }

        // Lead count / leads
        if matchesAny(lower, patterns: ["how many leads", "lead count", "new leads",
                                        "leads today", "my leads", "show leads",
                                        "leads update"]) {
            return .leadCount
        }

        // Rate alerts
        if matchesAny(lower, patterns: ["rate alert", "rate alerts", "rate update",
                                        "what are rates", "rates today", "interest rates",
                                        "mortgage rates", "show rates"]) {
            return .rateAlerts
        }

        // Task summary
        if matchesAny(lower, patterns: ["task summary", "pending tasks", "what tasks",
                                        "my tasks", "tasks due", "show tasks",
                                        "how many tasks", "task list", "to do",
                                        "to-do", "todos"]) {
            return .taskSummary
        }

        // Loan status
        if matchesAny(lower, patterns: ["loan status", "active loans", "my loans",
                                        "show loans", "loan update", "loans in pipeline",
                                        "loan count"]) {
            return .loanStatus
        }

        // Help
        if matchesAny(lower, patterns: ["help", "what can you do", "commands",
                                        "what can i say"]) {
            return .help
        }

        return .unknown(raw: command)
    }

    /// Extract the contact name from a "call [name]" command.
    /// Returns nil if the command doesn't match a call pattern.
    private func extractCallTarget(from lower: String) -> String? {
        let callPrefixes = ["call ", "phone ", "dial ", "ring ", "call back "]
        for prefix in callPrefixes {
            if lower.hasPrefix(prefix) {
                let name = String(lower.dropFirst(prefix.count))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !name.isEmpty {
                    return name
                }
            }
        }
        return nil
    }

    /// Check if the input contains any of the given pattern strings.
    private func matchesAny(_ input: String, patterns: [String]) -> Bool {
        return patterns.contains { input.contains($0) }
    }

    // MARK: - Command Handlers

    /// "show pipeline" — Fetch and narrate dashboard metrics.
    private func handlePipeline() async throws -> String {
        let data = try await api.fetchDashboard()

        var parts: [String] = []
        parts.append("Here's your pipeline summary.")
        parts.append("You have \(data.activeLoans) active loans worth \(data.spokenPipeline).")

        if data.pendingTasks > 0 {
            parts.append("\(data.pendingTasks) pending tasks.")
        }
        if data.urgentTasks > 0 {
            parts.append("\(data.urgentTasks) are urgent.")
        }
        if data.todayEvents > 0 {
            parts.append("\(data.todayEvents) events on your calendar today.")
        }
        if data.fundedThisMonth > 0 {
            parts.append("\(data.fundedThisMonth) loans funded this month.")
        }
        if data.totalLeads > 0 {
            parts.append("\(data.totalLeads) total leads in your pipeline.")
        }

        return parts.joined(separator: " ")
    }

    /// "call [name]" — Find a matching lead and initiate a click-to-dial call.
    private func handleCall(name: String) async throws -> String {
        os_log("Searching for contact: %{public}@", log: log, type: .info, name)

        // Fetch recent leads and find a match by name
        let leads = try await api.fetchLeads()
        let normalizedName = name.lowercased()

        // Try exact full name match first, then partial
        let match = leads.first { lead in
            lead.fullName.lowercased() == normalizedName
        } ?? leads.first { lead in
            lead.fullName.lowercased().contains(normalizedName)
        } ?? leads.first { lead in
            // Match on first name or last name alone
            let first = (lead.firstName ?? "").lowercased()
            let last = (lead.lastName ?? "").lowercased()
            return first == normalizedName || last == normalizedName
        }

        guard let lead = match else {
            return "I couldn't find a contact named \(name) in your recent leads. Try saying the full name."
        }

        guard let phone = lead.phone, !phone.isEmpty else {
            return "\(lead.fullName) doesn't have a phone number on file."
        }

        os_log("Initiating call to %{public}@ (lead %d)", log: log, type: .info, lead.fullName, lead.id)
        let result = try await api.callContact(phoneNumber: phone, contactName: lead.fullName, leadId: lead.id)

        if result.success {
            return "Calling \(lead.fullName) now."
        } else {
            return "Couldn't initiate the call to \(lead.fullName). \(result.message ?? "Please try again.")"
        }
    }

    /// "complete task" — Complete the highest-priority pending task.
    private func handleCompleteTask() async throws -> String {
        let tasks = try await api.fetchTasks()

        guard let task = tasks.first else {
            return "You have no pending tasks to complete."
        }

        // Sort by priority rank to complete the most urgent task
        let sorted = tasks.sorted { $0.priorityRank < $1.priorityRank }
        let topTask = sorted.first!

        try await api.completeTask(id: topTask.id)

        let remaining = tasks.count - 1
        var response = "Done. Marked \"\(topTask.title)\" as completed."
        if remaining > 0 {
            response += " You have \(remaining) more pending task\(remaining == 1 ? "" : "s")."
        } else {
            response += " That was your last pending task."
        }
        return response
    }

    /// "what's my schedule" — Read out upcoming calendar events.
    private func handleSchedule() async throws -> String {
        let events = try await api.fetchUpcomingEvents()

        if events.isEmpty {
            return "You have no upcoming appointments."
        }

        var parts: [String] = ["Here's your upcoming schedule."]
        let eventsToRead = events.prefix(5) // Limit spoken output to 5 events

        for event in eventsToRead {
            parts.append(event.shortLabel + ".")
        }

        if events.count > 5 {
            parts.append("And \(events.count - 5) more event\(events.count - 5 == 1 ? "" : "s") after that.")
        }

        return parts.joined(separator: " ")
    }

    /// "how many leads" — Summarize lead counts and recent activity.
    private func handleLeadCount() async throws -> String {
        let leads = try await api.fetchLeads()

        if leads.isEmpty {
            return "You don't have any leads right now."
        }

        // Count leads by stage
        var stageCounts: [String: Int] = [:]
        for lead in leads {
            let stage = lead.stage.lowercased()
            stageCounts[stage, default: 0] += 1
        }

        var parts: [String] = ["You have \(leads.count) recent leads."]

        // Report notable stages
        let notableStages = ["new", "contacted", "application", "qualified"]
        for stage in notableStages {
            if let count = stageCounts[stage], count > 0 {
                parts.append("\(count) \(stage).")
            }
        }

        return parts.joined(separator: " ")
    }

    /// "rate alerts" — Read out recent rate monitor alerts.
    private func handleRateAlerts() async throws -> String {
        let alerts = try await api.fetchRateAlerts()

        if alerts.isEmpty {
            return "You have no rate alerts at this time."
        }

        var parts: [String] = ["You have \(alerts.count) rate alert\(alerts.count == 1 ? "" : "s")."]

        for alert in alerts.prefix(5) {
            parts.append(alert.spokenSummary + ".")
        }

        if alerts.count > 5 {
            parts.append("Plus \(alerts.count - 5) more alert\(alerts.count - 5 == 1 ? "" : "s").")
        }

        return parts.joined(separator: " ")
    }

    /// "pending tasks" — Read out task summary with priority breakdown.
    private func handleTaskSummary() async throws -> String {
        let tasks = try await api.fetchTasks()

        if tasks.isEmpty {
            return "You're all caught up. No pending tasks."
        }

        let highPriority = tasks.filter { $0.priority.lowercased() == "high" }
        let overdue = tasks.filter { $0.isOverdue }

        var parts: [String] = ["You have \(tasks.count) pending task\(tasks.count == 1 ? "" : "s")."]

        if !highPriority.isEmpty {
            parts.append("\(highPriority.count) high priority.")
        }
        if !overdue.isEmpty {
            parts.append("\(overdue.count) overdue.")
        }

        // Read the top 3 task titles
        let topTasks = tasks.sorted { $0.priorityRank < $1.priorityRank }.prefix(3)
        if !topTasks.isEmpty {
            parts.append("Top tasks:")
            for task in topTasks {
                parts.append(task.title + ".")
            }
        }

        return parts.joined(separator: " ")
    }

    /// "active loans" — Summarize loan pipeline status.
    private func handleLoanStatus() async throws -> String {
        let loans = try await api.fetchLoans()

        if loans.isEmpty {
            return "You have no active loans in your pipeline."
        }

        // Count by stage
        var stageCounts: [String: Int] = [:]
        var totalAmount: Double = 0
        for loan in loans {
            let stage = loan.spokenStage
            stageCounts[stage, default: 0] += 1
            totalAmount += loan.loanAmount ?? 0
        }

        var parts: [String] = ["You have \(loans.count) loan\(loans.count == 1 ? "" : "s") in your pipeline."]

        if totalAmount > 0 {
            let spoken: String
            if totalAmount >= 1_000_000 {
                let millions = totalAmount / 1_000_000
                if millions == Double(Int(millions)) {
                    spoken = String(format: "%.0f million dollars", millions)
                } else {
                    spoken = String(format: "%.1f million dollars", millions)
                }
            } else if totalAmount >= 1_000 {
                spoken = String(format: "%.0f thousand dollars", totalAmount / 1_000)
            } else {
                spoken = String(format: "%.0f dollars", totalAmount)
            }
            parts.append("Total volume: \(spoken).")
        }

        // Report top stages
        let sorted = stageCounts.sorted { $0.value > $1.value }
        for (stage, count) in sorted.prefix(4) {
            parts.append("\(count) in \(stage).")
        }

        return parts.joined(separator: " ")
    }

    /// "help" — List available voice commands.
    private func handleHelp() -> String {
        return """
        You can say: \
        show pipeline, \
        call and a contact name, \
        complete task, \
        what's my schedule, \
        how many leads, \
        rate alerts, \
        pending tasks, \
        or loan status.
        """
    }
}
