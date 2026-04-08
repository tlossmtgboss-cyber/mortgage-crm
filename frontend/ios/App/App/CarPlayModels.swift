//
//  CarPlayModels.swift
//  App
//
//  Codable model structs for all CarPlay API responses.
//  These map to the backend FastAPI endpoints at api.perenniaai.com.
//
//  All models use snake_case JSON keys via JSONDecoder.convertFromSnakeCase.
//

import Foundation

// MARK: - Dashboard / Pipeline Metrics

/// Response from GET /api/v1/pipeline/metrics
/// Maps to the backend pipeline metrics endpoint which returns aggregate
/// counts and dollar amounts for the authenticated loan officer's pipeline.
struct DashboardData: Codable {
    let totalLeads: Int
    let totalLoans: Int
    let totalPipeline: Double       // aggregate dollar amount of active loans
    let pendingTasks: Int
    let urgentTasks: Int
    let todayEvents: Int
    let activeLoans: Int
    let fundedThisMonth: Int

    /// Provide sensible defaults for any missing keys so the decoder
    /// never fails on a partial backend response.
    enum CodingKeys: String, CodingKey {
        case totalLeads, totalLoans, totalPipeline
        case pendingTasks, urgentTasks, todayEvents
        case activeLoans, fundedThisMonth
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        totalLeads       = try c.decodeIfPresent(Int.self, forKey: .totalLeads) ?? 0
        totalLoans       = try c.decodeIfPresent(Int.self, forKey: .totalLoans) ?? 0
        totalPipeline    = try c.decodeIfPresent(Double.self, forKey: .totalPipeline) ?? 0
        pendingTasks     = try c.decodeIfPresent(Int.self, forKey: .pendingTasks) ?? 0
        urgentTasks      = try c.decodeIfPresent(Int.self, forKey: .urgentTasks) ?? 0
        todayEvents      = try c.decodeIfPresent(Int.self, forKey: .todayEvents) ?? 0
        activeLoans      = try c.decodeIfPresent(Int.self, forKey: .activeLoans) ?? 0
        fundedThisMonth  = try c.decodeIfPresent(Int.self, forKey: .fundedThisMonth) ?? 0
    }

    /// Memberwise initializer for unit tests and previews.
    init(
        totalLeads: Int = 0,
        totalLoans: Int = 0,
        totalPipeline: Double = 0,
        pendingTasks: Int = 0,
        urgentTasks: Int = 0,
        todayEvents: Int = 0,
        activeLoans: Int = 0,
        fundedThisMonth: Int = 0
    ) {
        self.totalLeads = totalLeads
        self.totalLoans = totalLoans
        self.totalPipeline = totalPipeline
        self.pendingTasks = pendingTasks
        self.urgentTasks = urgentTasks
        self.todayEvents = todayEvents
        self.activeLoans = activeLoans
        self.fundedThisMonth = fundedThisMonth
    }

    /// Human-readable pipeline value (e.g. "$2.5M").
    var formattedPipeline: String {
        if totalPipeline >= 1_000_000 {
            return String(format: "$%.1fM", totalPipeline / 1_000_000)
        } else if totalPipeline >= 1_000 {
            return String(format: "$%.0fK", totalPipeline / 1_000)
        } else {
            return String(format: "$%.0f", totalPipeline)
        }
    }

    /// TTS-friendly pipeline value (e.g. "2.5 million dollars").
    /// Avoids "$" symbols and abbreviations that screen readers mispronounce.
    var spokenPipeline: String {
        if totalPipeline >= 1_000_000 {
            let millions = totalPipeline / 1_000_000
            if millions == Double(Int(millions)) {
                return String(format: "%.0f million dollars", millions)
            }
            return String(format: "%.1f million dollars", millions)
        } else if totalPipeline >= 1_000 {
            return String(format: "%.0f thousand dollars", totalPipeline / 1_000)
        } else if totalPipeline > 0 {
            return String(format: "%.0f dollars", totalPipeline)
        } else {
            return "zero dollars"
        }
    }
}

// MARK: - Tasks

/// A single task item from GET /api/v1/tasks/?status=pending&limit=20
/// Backend tasks table columns: id, title, description, status, priority,
/// due_date, lead_id, loan_id, related_contact_name, owner_id, etc.
struct TaskItem: Codable, Identifiable {
    let id: Int
    let title: String
    let description: String?
    let dueDate: String?
    let priority: String          // "high", "medium", "low"
    let status: String            // "pending", "in_progress", "completed"
    let leadName: String?         // from related_contact_name or joined lead
    let loanNumber: String?       // from joined loan

    /// Whether this task is overdue based on its due_date.
    var isOverdue: Bool {
        guard let dueDate = dueDate else { return false }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: dueDate) {
            return date < Date()
        }
        // Try without fractional seconds
        formatter.formatOptions = [.withInternetDateTime]
        if let date = formatter.date(from: dueDate) {
            return date < Date()
        }
        return false
    }

    /// Priority as a sortable integer (lower = more urgent).
    var priorityRank: Int {
        switch priority.lowercased() {
        case "high":   return 0
        case "medium": return 1
        case "low":    return 2
        default:       return 3
        }
    }

    /// Short label for CarPlay display.
    var shortLabel: String {
        if let name = leadName, !name.isEmpty {
            return "\(title) - \(name)"
        }
        return title
    }
}

// MARK: - Leads

/// A single lead from GET /api/v1/leads/?limit=20&sort=-updated_at
/// Maps to the Lead SQLAlchemy model (database/models/lead_loan.py).
struct LeadItem: Codable, Identifiable {
    let id: Int
    let firstName: String?
    let lastName: String?
    let email: String?
    let phone: String?
    let stage: String             // "New", "Contacted", "APPLICATION", etc.
    let source: String?
    let createdAt: String
    let updatedAt: String

    /// Full display name, gracefully handling nil components.
    var fullName: String {
        let parts = [firstName, lastName].compactMap { $0?.trimmingCharacters(in: .whitespaces) }
        let joined = parts.filter { !$0.isEmpty }.joined(separator: " ")
        return joined.isEmpty ? "Unknown Lead" : joined
    }

    /// Stage formatted for spoken output — expands abbreviations that
    /// TTS engines and screen readers would mispronounce.
    var spokenStage: String {
        Self.spokenStageMap[stage.uppercased()]
            ?? stage.replacingOccurrences(of: "_", with: " ").lowercased()
    }

    /// Maps stage codes to natural language for text-to-speech.
    private static let spokenStageMap: [String: String] = [
        "APPLICATION":          "application",
        "DISCLOSED":            "disclosed",
        "PROCESSING":           "processing",
        "SUBMITTED":            "submitted",
        "UNDERWRITING":         "underwriting",
        "UW_RECEIVED":          "underwriting received",
        "CONDITIONAL_APPROVAL": "conditional approval",
        "APPROVED":             "approved",
        "SUSPENDED":            "suspended",
        "CTC":                  "clear to close",
        "CLEAR_TO_CLOSE":       "clear to close",
        "CLOSING":              "closing",
        "DOCS":                 "docs out",
        "DOCS_OUT":             "docs out",
        "FUNDED":               "funded",
        "CANCELLED":            "cancelled",
        "DENIED":               "denied",
        "DEAD":                 "dead",
        "WITHDRAWN":            "withdrawn",
        "DOES_NOT_QUALIFY":     "does not qualify",
        "NURTURE":              "nurture",
        "NEW":                  "new",
        "CONTACTED":            "contacted",
        "QUALIFIED":            "qualified",
    ]
}

// MARK: - Loans

/// A single loan from GET /api/v1/loans/?limit=20
/// Maps to the Loan SQLAlchemy model (database/models/lead_loan.py).
struct LoanItem: Codable, Identifiable {
    let id: Int
    let borrowerName: String?
    let loanNumber: String?
    let loanAmount: Double?
    let stage: String             // UPPERCASE: APPLICATION, PROCESSING, FUNDED, etc.
    let loanType: String?         // "conventional", "fha", "va", "usda"
    let propertyAddress: String?
    let closingDate: String?

    /// Human-readable loan amount.
    var formattedAmount: String {
        guard let amount = loanAmount else { return "N/A" }
        if amount >= 1_000_000 {
            return String(format: "$%.2fM", amount / 1_000_000)
        } else if amount >= 1_000 {
            return String(format: "$%.0fK", amount / 1_000)
        } else {
            return String(format: "$%.0f", amount)
        }
    }

    /// TTS-friendly loan amount (e.g. "425 thousand dollars").
    /// Avoids "$" symbols and abbreviations that screen readers mispronounce.
    var spokenAmount: String {
        guard let amount = loanAmount else { return "unknown amount" }
        if amount >= 1_000_000 {
            let millions = amount / 1_000_000
            if millions == Double(Int(millions)) {
                return String(format: "%.0f million dollars", millions)
            }
            return String(format: "%.1f million dollars", millions)
        } else if amount >= 1_000 {
            return String(format: "%.0f thousand dollars", amount / 1_000)
        } else if amount > 0 {
            return String(format: "%.0f dollars", amount)
        } else {
            return "zero dollars"
        }
    }

    /// Stage formatted for spoken output — expands abbreviations that
    /// TTS engines and screen readers would mispronounce.
    var spokenStage: String {
        Self.spokenStageMap[stage.uppercased()]
            ?? stage.replacingOccurrences(of: "_", with: " ").lowercased()
    }

    /// Maps stage codes to natural language for text-to-speech.
    private static let spokenStageMap: [String: String] = [
        "APPLICATION":          "application",
        "DISCLOSED":            "disclosed",
        "PROCESSING":           "processing",
        "SUBMITTED":            "submitted",
        "UNDERWRITING":         "underwriting",
        "UW_RECEIVED":          "underwriting received",
        "CONDITIONAL_APPROVAL": "conditional approval",
        "APPROVED":             "approved",
        "SUSPENDED":            "suspended",
        "CTC":                  "clear to close",
        "CLEAR_TO_CLOSE":       "clear to close",
        "CLOSING":              "closing",
        "DOCS":                 "docs out",
        "DOCS_OUT":             "docs out",
        "FUNDED":               "funded",
        "CANCELLED":            "cancelled",
        "DENIED":               "denied",
        "DEAD":                 "dead",
        "WITHDRAWN":            "withdrawn",
        "DOES_NOT_QUALIFY":     "does not qualify",
        "NURTURE":              "nurture",
    ]
}

// MARK: - Rate Alerts

/// A single rate alert from GET /api/v1/rate-monitor/alerts
/// Maps to the RateMonitorAlert model (models/rate_monitor.py).
struct RateAlert: Codable, Identifiable {
    let id: Int
    let rateType: String          // "30yr_fixed", "15yr_fixed", "fha", "va"
    let currentRate: Double
    let previousRate: Double
    let changeDirection: String   // "up", "down"
    let timestamp: String

    /// Basis point change (e.g. -25 for a 0.25% drop).
    var basisPointChange: Int {
        Int(round((currentRate - previousRate) * 100))
    }

    /// Human-readable rate type for spoken output.
    var spokenRateType: String {
        switch rateType.lowercased() {
        case "30yr_fixed":  return "30-year fixed"
        case "15yr_fixed":  return "15-year fixed"
        case "fha":         return "FHA"
        case "va":          return "VA"
        case "usda":        return "USDA"
        case "jumbo":       return "Jumbo"
        default:            return rateType.replacingOccurrences(of: "_", with: " ")
        }
    }

    /// Spoken summary (e.g. "30-year fixed down to 6.75%").
    var spokenSummary: String {
        let direction = changeDirection == "down" ? "down" : "up"
        return "\(spokenRateType) \(direction) to \(String(format: "%.2f", currentRate))%"
    }
}

// MARK: - Calendar Events

/// A single calendar event from GET /api/v1/calendar/events?upcoming=true&limit=10
/// Maps to the Appointment model in smart_scheduler_models.py.
struct CalendarEvent: Codable, Identifiable {
    let id: Int
    let title: String
    let startTime: String
    let endTime: String?
    let location: String?
    let eventType: String?        // "call", "meeting", "closing", "showing"
    let attendeeName: String?

    /// Parsed start time for sorting and display.
    var startDate: Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: startTime) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: startTime)
    }

    /// Time-only string for CarPlay display (e.g. "2:30 PM").
    var formattedTime: String {
        guard let date = startDate else { return startTime }
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm a"
        return formatter.string(from: date)
    }

    /// Short label for CarPlay list items.
    var shortLabel: String {
        if let name = attendeeName, !name.isEmpty {
            return "\(formattedTime) - \(title) with \(name)"
        }
        return "\(formattedTime) - \(title)"
    }
}

// MARK: - Call Initiation

/// Response from POST /api/v1/dialer/click-to-dial
/// Maps to the ClickToDialResponse schema (telephony/schemas.py).
struct CallInitiation: Codable {
    let success: Bool
    let callId: String?           // maps to call_sid from backend
    let message: String?          // human-readable status or error

    enum CodingKeys: String, CodingKey {
        case success
        case callId = "callSid"   // backend field is call_sid -> callSid via snake_case conversion
        case message = "error"    // backend returns "error" field; we treat as message
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        success = try c.decodeIfPresent(Bool.self, forKey: .success) ?? false
        callId  = try c.decodeIfPresent(String.self, forKey: .callId)
        message = try c.decodeIfPresent(String.self, forKey: .message)
    }

    init(success: Bool, callId: String? = nil, message: String? = nil) {
        self.success = success
        self.callId = callId
        self.message = message
    }
}

// MARK: - API Error Response

/// Generic API error envelope returned by the backend on 4xx/5xx responses.
struct APIErrorResponse: Codable {
    let detail: String?
    let message: String?

    /// Best available error description.
    var displayMessage: String {
        detail ?? message ?? "An unknown error occurred"
    }
}

// MARK: - Paginated List Wrapper

/// Some backend list endpoints return { items: [...], total: N, ... }.
/// This wrapper handles both array responses and paginated envelopes.
struct PaginatedResponse<T: Codable>: Codable {
    let items: [T]
    let total: Int?
    let limit: Int?
    let offset: Int?

    enum CodingKeys: String, CodingKey {
        case items, total, limit, offset
    }

    init(from decoder: Decoder) throws {
        // Try paginated envelope first
        if let container = try? decoder.container(keyedBy: CodingKeys.self),
           let items = try? container.decode([T].self, forKey: .items) {
            self.items = items
            self.total = try? container.decodeIfPresent(Int.self, forKey: .total)
            self.limit = try? container.decodeIfPresent(Int.self, forKey: .limit)
            self.offset = try? container.decodeIfPresent(Int.self, forKey: .offset)
            return
        }
        // Fall back to plain array
        let singleValue = try decoder.singleValueContainer()
        self.items = try singleValue.decode([T].self)
        self.total = nil
        self.limit = nil
        self.offset = nil
    }
}
