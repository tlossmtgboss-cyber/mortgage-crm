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

// MARK: - Dashboard Summary

/// Response from GET /api/v1/dashboard/summary
/// Maps to the backend dashboard_summary_routes.py endpoint which returns
/// aggregate counts for the authenticated loan officer's pipeline.
///
/// The backend returns camelCase keys directly (not snake_case), so this
/// struct uses explicit CodingKeys matching the JSON as-is. The
/// CarPlayAPIService decodes this with a plain JSONDecoder (no
/// convertFromSnakeCase) to avoid double-conversion.
struct CPDashboardData: Codable {
    let urgentTaskCount: Int
    let activeLoanCount: Int
    let rateAlertCount: Int
    let newLeadCount: Int
    let todayAppointmentCount: Int
    let pipelineSummary: PipelineSummary?

    struct PipelineSummary: Codable {
        let applicationCount: Int
        let processingCount: Int
        let underwritingCount: Int
        let clearToCloseCount: Int

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            applicationCount   = try c.decodeIfPresent(Int.self, forKey: .applicationCount) ?? 0
            processingCount    = try c.decodeIfPresent(Int.self, forKey: .processingCount) ?? 0
            underwritingCount  = try c.decodeIfPresent(Int.self, forKey: .underwritingCount) ?? 0
            clearToCloseCount  = try c.decodeIfPresent(Int.self, forKey: .clearToCloseCount) ?? 0
        }

        init(applicationCount: Int = 0, processingCount: Int = 0,
             underwritingCount: Int = 0, clearToCloseCount: Int = 0) {
            self.applicationCount = applicationCount
            self.processingCount = processingCount
            self.underwritingCount = underwritingCount
            self.clearToCloseCount = clearToCloseCount
        }
    }

    /// Provide sensible defaults for any missing keys so the decoder
    /// never fails on a partial backend response.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        urgentTaskCount       = try c.decodeIfPresent(Int.self, forKey: .urgentTaskCount) ?? 0
        activeLoanCount       = try c.decodeIfPresent(Int.self, forKey: .activeLoanCount) ?? 0
        rateAlertCount        = try c.decodeIfPresent(Int.self, forKey: .rateAlertCount) ?? 0
        newLeadCount          = try c.decodeIfPresent(Int.self, forKey: .newLeadCount) ?? 0
        todayAppointmentCount = try c.decodeIfPresent(Int.self, forKey: .todayAppointmentCount) ?? 0
        pipelineSummary       = try c.decodeIfPresent(PipelineSummary.self, forKey: .pipelineSummary)
    }

    /// Memberwise initializer for unit tests and previews.
    init(
        urgentTaskCount: Int = 0,
        activeLoanCount: Int = 0,
        rateAlertCount: Int = 0,
        newLeadCount: Int = 0,
        todayAppointmentCount: Int = 0,
        pipelineSummary: PipelineSummary? = nil
    ) {
        self.urgentTaskCount = urgentTaskCount
        self.activeLoanCount = activeLoanCount
        self.rateAlertCount = rateAlertCount
        self.newLeadCount = newLeadCount
        self.todayAppointmentCount = todayAppointmentCount
        self.pipelineSummary = pipelineSummary
    }

    /// Total active loans as spoken text for CarPlay TTS.
    var spokenActiveLoanSummary: String {
        if activeLoanCount == 0 {
            return "no active loans"
        } else if activeLoanCount == 1 {
            return "1 active loan"
        } else {
            return "\(activeLoanCount) active loans"
        }
    }

    /// Spoken pipeline breakdown for CarPlay TTS.
    var spokenPipelineBreakdown: String {
        guard let ps = pipelineSummary else { return "no pipeline data" }
        var parts: [String] = []
        if ps.applicationCount > 0 { parts.append("\(ps.applicationCount) in application") }
        if ps.processingCount > 0 { parts.append("\(ps.processingCount) in processing") }
        if ps.underwritingCount > 0 { parts.append("\(ps.underwritingCount) in underwriting") }
        if ps.clearToCloseCount > 0 { parts.append("\(ps.clearToCloseCount) clear to close") }
        return parts.isEmpty ? "pipeline is empty" : parts.joined(separator: ", ")
    }
}

// MARK: - Tasks

/// A single task item from GET /api/v1/mobile/tasks?status=pending&limit=20
/// Backend response wraps tasks in {"tasks": [...], "count": N, "filter": "..."}
/// Task fields: id, title, description, status, priority, due_date, lead_id,
/// loan_id, related_contact_name, is_overdue, created_at, updated_at, etc.
struct CPTaskItem: Codable, Identifiable {
    let id: Int
    let title: String
    let description: String?
    let dueDate: String?
    let priority: String          // "high", "medium", "low"
    let status: String            // "pending", "in_progress", "completed"
    let relatedContactName: String?  // backend JSON: related_contact_name -> relatedContactName
    let leadId: Int?              // backend JSON: lead_id -> leadId
    let loanId: Int?              // backend JSON: loan_id -> loanId
    let backendIsOverdue: Bool?    // backend JSON: is_overdue -> isOverdue (renamed to avoid conflict)

    /// Convenience alias for display — uses related_contact_name from backend.
    var leadName: String? { relatedContactName }

    // We need explicit CodingKeys because `backendIsOverdue` maps to JSON key
    // `isOverdue` (after convertFromSnakeCase converts `is_overdue`).
    enum CodingKeys: String, CodingKey {
        case id, title, description, dueDate, priority, status
        case relatedContactName, leadId, loanId
        case backendIsOverdue = "isOverdue"
    }

    /// Custom decoder that handles `id` arriving as either Int or String
    /// from the backend (mirrors CarPlayContact's defensive pattern).
    /// Note: Uses the shared .convertFromSnakeCase decoder, so snake_case JSON
    /// keys are automatically converted (due_date -> dueDate, related_contact_name
    /// -> relatedContactName, etc.) before CodingKey lookup.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let intId = try? c.decode(Int.self, forKey: .id) {
            id = intId
        } else {
            let stringId = try c.decode(String.self, forKey: .id)
            guard let parsed = Int(stringId) else {
                throw DecodingError.dataCorruptedError(forKey: .id, in: c,
                    debugDescription: "id is neither Int nor numeric String")
            }
            id = parsed
        }
        title       = try c.decode(String.self, forKey: .title)
        description = try c.decodeIfPresent(String.self, forKey: .description)
        dueDate     = try c.decodeIfPresent(String.self, forKey: .dueDate)
        priority    = try c.decodeIfPresent(String.self, forKey: .priority) ?? "medium"
        status      = try c.decodeIfPresent(String.self, forKey: .status) ?? "pending"
        relatedContactName = try c.decodeIfPresent(String.self, forKey: .relatedContactName)
        // leadId/loanId may arrive as Int or String from the backend
        if let intLeadId = try? c.decodeIfPresent(Int.self, forKey: .leadId) {
            leadId = intLeadId
        } else if let strLeadId = try? c.decodeIfPresent(String.self, forKey: .leadId) {
            leadId = Int(strLeadId)
        } else {
            leadId = nil
        }
        if let intLoanId = try? c.decodeIfPresent(Int.self, forKey: .loanId) {
            loanId = intLoanId
        } else if let strLoanId = try? c.decodeIfPresent(String.self, forKey: .loanId) {
            loanId = Int(strLoanId)
        } else {
            loanId = nil
        }
        backendIsOverdue = try c.decodeIfPresent(Bool.self, forKey: .backendIsOverdue)
    }

    /// Whether this task is overdue. Prefers the backend's is_overdue flag
    /// (computed server-side against the task's due_date), with a client-side
    /// fallback if the backend field is missing.
    var isOverdue: Bool {
        if let serverFlag = backendIsOverdue { return serverFlag }
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

/// A single lead from GET /api/v1/leads/?limit=20
/// Maps to the Lead SQLAlchemy model (database/models/lead_loan.py).
/// Backend returns `name` (single combined field), not separate first/last.
struct LeadItem: Codable, Identifiable {
    let id: Int
    let name: String?             // backend field: name (combined first+last)
    let email: String?
    let phone: String?
    let stage: String             // "New", "Contacted", "APPLICATION", etc.
    let source: String?
    let createdAt: String
    let updatedAt: String

    /// Custom decoder that handles `id` arriving as either Int or String
    /// from the backend (mirrors CarPlayContact's defensive pattern).
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let intId = try? c.decode(Int.self, forKey: .id) {
            id = intId
        } else {
            let stringId = try c.decode(String.self, forKey: .id)
            guard let parsed = Int(stringId) else {
                throw DecodingError.dataCorruptedError(forKey: .id, in: c,
                    debugDescription: "id is neither Int nor numeric String")
            }
            id = parsed
        }
        name      = try c.decodeIfPresent(String.self, forKey: .name)
        email     = try c.decodeIfPresent(String.self, forKey: .email)
        phone     = try c.decodeIfPresent(String.self, forKey: .phone)
        stage     = try c.decodeIfPresent(String.self, forKey: .stage) ?? "New"
        source    = try c.decodeIfPresent(String.self, forKey: .source)
        createdAt = try c.decodeIfPresent(String.self, forKey: .createdAt) ?? ""
        updatedAt = try c.decodeIfPresent(String.self, forKey: .updatedAt) ?? ""
    }

    /// Full display name from the backend's combined `name` field.
    var fullName: String {
        guard let n = name?.trimmingCharacters(in: .whitespaces), !n.isEmpty else {
            return "Unknown Lead"
        }
        return n
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
/// Backend returns `amount` (not `loan_amount`) and `borrower_name`.
struct LoanItem: Codable, Identifiable {
    let id: Int
    let borrowerName: String?
    let loanNumber: String?
    let amount: Double?           // backend field: amount (not loan_amount)
    let stage: String             // UPPERCASE: APPLICATION, PROCESSING, FUNDED, etc.
    let loanType: String?         // "conventional", "fha", "va", "usda"
    let propertyAddress: String?
    let closingDate: String?

    /// Custom decoder that handles `id` arriving as either Int or String
    /// from the backend (mirrors CarPlayContact's defensive pattern).
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let intId = try? c.decode(Int.self, forKey: .id) {
            id = intId
        } else {
            let stringId = try c.decode(String.self, forKey: .id)
            guard let parsed = Int(stringId) else {
                throw DecodingError.dataCorruptedError(forKey: .id, in: c,
                    debugDescription: "id is neither Int nor numeric String")
            }
            id = parsed
        }
        borrowerName    = try c.decodeIfPresent(String.self, forKey: .borrowerName)
        loanNumber      = try c.decodeIfPresent(String.self, forKey: .loanNumber)
        amount          = try c.decodeIfPresent(Double.self, forKey: .amount)
        stage           = try c.decodeIfPresent(String.self, forKey: .stage) ?? "APPLICATION"
        loanType        = try c.decodeIfPresent(String.self, forKey: .loanType)
        propertyAddress = try c.decodeIfPresent(String.self, forKey: .propertyAddress)
        closingDate     = try c.decodeIfPresent(String.self, forKey: .closingDate)
    }

    /// Human-readable loan amount.
    var formattedAmount: String {
        guard let amt = amount else { return "N/A" }
        if amt >= 1_000_000 {
            return String(format: "$%.2fM", amt / 1_000_000)
        } else if amt >= 1_000 {
            return String(format: "$%.0fK", amt / 1_000)
        } else {
            return String(format: "$%.0f", amt)
        }
    }

    /// TTS-friendly loan amount (e.g. "425 thousand dollars").
    /// Avoids "$" symbols and abbreviations that screen readers mispronounce.
    var spokenAmount: String {
        guard let amt = amount else { return "unknown amount" }
        if amt >= 1_000_000 {
            let millions = amt / 1_000_000
            if millions == Double(Int(millions)) {
                return String(format: "%.0f million dollars", millions)
            }
            return String(format: "%.1f million dollars", millions)
        } else if amt >= 1_000 {
            return String(format: "%.0f thousand dollars", amt / 1_000)
        } else if amt > 0 {
            return String(format: "%.0f dollars", amt)
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

/// A single rate alert from GET /api/v1/rate-monitor/alerts/carplay
/// Maps to the RateMonitorAlert model (models/rate_monitor.py).
struct CPRateAlert: Codable, Identifiable {
    let id: Int
    let rateType: String          // "30yr_fixed", "15yr_fixed", "fha", "va"
    let currentRate: Double
    let previousRate: Double
    let changeDirection: String   // "up", "down"
    let timestamp: String

    /// Custom decoder that handles `id` arriving as either Int or String
    /// from the backend (mirrors CarPlayContact's defensive pattern).
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let intId = try? c.decode(Int.self, forKey: .id) {
            id = intId
        } else {
            let stringId = try c.decode(String.self, forKey: .id)
            guard let parsed = Int(stringId) else {
                throw DecodingError.dataCorruptedError(forKey: .id, in: c,
                    debugDescription: "id is neither Int nor numeric String")
            }
            id = parsed
        }
        rateType        = try c.decode(String.self, forKey: .rateType)
        currentRate     = try c.decode(Double.self, forKey: .currentRate)
        previousRate    = try c.decode(Double.self, forKey: .previousRate)
        changeDirection = try c.decodeIfPresent(String.self, forKey: .changeDirection) ?? "down"
        timestamp       = try c.decodeIfPresent(String.self, forKey: .timestamp) ?? ""
    }

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

/// A single calendar event from GET /api/v1/scheduler/appointments
/// Maps to the Appointment model in database/models/scheduler.py.
/// Backend returns appointments wrapped as {"appointments": [...], "total": N}.
/// Fields: scheduled_start, scheduled_end, meeting_type (not start_time/end_time/event_type).
struct CalendarEvent: Codable, Identifiable {
    let id: Int
    let title: String
    let scheduledStart: String    // backend field: scheduled_start (ISO-8601)
    let scheduledEnd: String?     // backend field: scheduled_end (ISO-8601)
    let location: String?
    let meetingType: String?      // backend field: meeting_type (MeetingType enum value)
    let attendeeName: String?     // backend field: attendee_name

    /// Custom decoder that handles `id` arriving as either Int or String
    /// from the backend (mirrors CarPlayContact's defensive pattern).
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let intId = try? c.decode(Int.self, forKey: .id) {
            id = intId
        } else {
            let stringId = try c.decode(String.self, forKey: .id)
            guard let parsed = Int(stringId) else {
                throw DecodingError.dataCorruptedError(forKey: .id, in: c,
                    debugDescription: "id is neither Int nor numeric String")
            }
            id = parsed
        }
        title          = try c.decode(String.self, forKey: .title)
        scheduledStart = try c.decode(String.self, forKey: .scheduledStart)
        scheduledEnd   = try c.decodeIfPresent(String.self, forKey: .scheduledEnd)
        location       = try c.decodeIfPresent(String.self, forKey: .location)
        meetingType    = try c.decodeIfPresent(String.self, forKey: .meetingType)
        attendeeName   = try c.decodeIfPresent(String.self, forKey: .attendeeName)
    }

    /// Parsed start time for sorting and display.
    var startDate: Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: scheduledStart) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: scheduledStart)
    }

    /// Time-only string for CarPlay display (e.g. "2:30 PM").
    var formattedTime: String {
        guard let date = startDate else { return scheduledStart }
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
