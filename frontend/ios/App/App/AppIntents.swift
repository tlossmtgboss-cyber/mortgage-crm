/**
 * AppIntents.swift
 * Perennia AI — App Intents & Siri Integration (iOS 16+)
 *
 * Defines five App Intents using the modern AppIntents framework:
 *   1. CheckPipelineIntent  — Pipeline summary (loan counts by stage)
 *   2. AddLeadIntent        — Create a new lead
 *   3. CallBorrowerIntent   — Search and call a borrower
 *   4. CheckTasksIntent     — Today's tasks
 *   5. QuickNoteIntent      — Add a note to a lead's activity feed
 *
 * All intents communicate with https://api.perenniaai.com using the
 * auth token stored in the iOS Keychain via KeychainService.
 *
 * Requires iOS 16.0+ (the app deployment target is iOS 15.0, so all
 * intent types are gated with @available).
 */

import Foundation
import AppIntents
import UIKit

// MARK: - API Client

/// Shared HTTP client for all App Intents. Reads the JWT from Capacitor's
/// UserDefaults storage and makes authenticated requests to the Perennia API.
@available(iOS 16.0, *)
struct PerenniaAPIClient {

    static let baseURL = "https://api.perenniaai.com"

    /// Retrieve the stored auth token from Keychain, or nil if the user is not logged in.
    static var authToken: String? {
        KeychainService.shared.authToken
    }

    /// Build an authenticated URLRequest.
    static func request(
        method: String,
        path: String,
        queryItems: [URLQueryItem]? = nil,
        body: [String: Any]? = nil
    ) throws -> URLRequest {
        guard let token = authToken, !token.isEmpty else {
            throw PerenniaIntentError.notAuthenticated
        }

        var components = URLComponents(string: "\(baseURL)\(path)")!
        if let queryItems = queryItems, !queryItems.isEmpty {
            components.queryItems = queryItems
        }

        guard let url = components.url else {
            throw PerenniaIntentError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("PerenniaAI-iOS/1.0 AppIntents", forHTTPHeaderField: "User-Agent")
        request.timeoutInterval = 15

        if let body = body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }

        return request
    }

    /// Execute a request and return the decoded JSON (dictionary or array).
    static func execute(_ request: URLRequest) async throws -> Any {
        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw PerenniaIntentError.networkError("Invalid response")
        }

        if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
            throw PerenniaIntentError.notAuthenticated
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            let bodySnippet = String(data: data.prefix(200), encoding: .utf8) ?? ""
            throw PerenniaIntentError.networkError(
                "HTTP \(httpResponse.statusCode): \(bodySnippet)"
            )
        }

        return try JSONSerialization.jsonObject(with: data)
    }

    /// Convenience: GET request returning a dictionary.
    static func get(
        path: String,
        queryItems: [URLQueryItem]? = nil
    ) async throws -> [String: Any] {
        let req = try request(method: "GET", path: path, queryItems: queryItems)
        let result = try await execute(req)
        guard let dict = result as? [String: Any] else {
            throw PerenniaIntentError.unexpectedResponse
        }
        return dict
    }

    /// Convenience: GET request returning an array.
    static func getArray(
        path: String,
        queryItems: [URLQueryItem]? = nil
    ) async throws -> [[String: Any]] {
        let req = try request(method: "GET", path: path, queryItems: queryItems)
        let result = try await execute(req)
        // Handle both array responses and paginated { items: [...] } responses
        if let array = result as? [[String: Any]] {
            return array
        }
        if let dict = result as? [String: Any] {
            if let items = dict["items"] as? [[String: Any]] {
                return items
            }
            if let leads = dict["leads"] as? [[String: Any]] {
                return leads
            }
            if let tasks = dict["tasks"] as? [[String: Any]] {
                return tasks
            }
            if let data = dict["data"] as? [[String: Any]] {
                return data
            }
            // Wrap single dict as an array for uniform handling
            return [dict]
        }
        throw PerenniaIntentError.unexpectedResponse
    }

    /// Convenience: POST request returning a dictionary.
    static func post(
        path: String,
        body: [String: Any]
    ) async throws -> [String: Any] {
        let req = try request(method: "POST", path: path, body: body)
        let result = try await execute(req)
        guard let dict = result as? [String: Any] else {
            throw PerenniaIntentError.unexpectedResponse
        }
        return dict
    }
}


// MARK: - Error Types

@available(iOS 16.0, *)
enum PerenniaIntentError: Swift.Error, CustomLocalizedStringResourceConvertible {
    case notAuthenticated
    case invalidURL
    case networkError(String)
    case unexpectedResponse
    case noResults

    var localizedStringResource: LocalizedStringResource {
        switch self {
        case .notAuthenticated:
            return "Please log in to Perennia AI first."
        case .invalidURL:
            return "Could not build the API request."
        case .networkError(let detail):
            return "Network error: \(detail)"
        case .unexpectedResponse:
            return "Received an unexpected response from the server."
        case .noResults:
            return "No results found."
        }
    }
}


// MARK: - 1. CheckPipelineIntent

@available(iOS 16.0, *)
struct CheckPipelineIntent: AppIntent {

    static var title: LocalizedStringResource = "Check My Pipeline"

    static var description = IntentDescription(
        "View a summary of your active loan pipeline in Perennia AI.",
        categoryName: "Pipeline"
    )

    static var openAppWhenRun: Bool = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let loans = try await PerenniaAPIClient.getArray(path: "/api/v1/loans/")

        if loans.isEmpty {
            return .result(dialog: "Your pipeline is empty. No active loans found.")
        }

        // Count loans by stage
        var stageCount: [String: Int] = [:]
        for loan in loans {
            let stage = (loan["stage"] as? String ?? "Unknown").capitalized
            stageCount[stage, default: 0] += 1
        }

        let total = loans.count

        // Build the stage breakdown, sorted by count descending
        let sorted = stageCount.sorted { $0.value > $1.value }
        var lines: [String] = []
        for (stage, count) in sorted {
            let label = stage.replacingOccurrences(of: "_", with: " ")
            lines.append("\(label): \(count)")
        }

        let breakdown = lines.joined(separator: "\n")
        let summary = "You have \(total) loan\(total == 1 ? "" : "s") in your pipeline.\n\n\(breakdown)"

        return .result(dialog: "\(summary)")
    }
}


// MARK: - 2. AddLeadIntent

@available(iOS 16.0, *)
struct AddLeadIntent: AppIntent {

    static var title: LocalizedStringResource = "Add a New Lead"

    static var description = IntentDescription(
        "Create a new lead in Perennia AI.",
        categoryName: "Leads"
    )

    static var openAppWhenRun: Bool = false

    @Parameter(title: "Name", description: "Full name of the lead")
    var name: String

    @Parameter(title: "Phone", description: "Phone number (optional)")
    var phone: String?

    @Parameter(title: "Email", description: "Email address (optional)")
    var email: String?

    static var parameterSummary: some ParameterSummary {
        Summary("Add lead named \(\.$name)") {
            \.$phone
            \.$email
        }
    }

    func perform() async throws -> some IntentResult & ProvidesDialog {
        // Split name into first/last
        let components = name.trimmingCharacters(in: .whitespaces).split(
            separator: " ", maxSplits: 1
        )
        let firstName = String(components.first ?? "")
        let lastName = components.count > 1 ? String(components[1]) : ""

        var body: [String: Any] = [
            "first_name": firstName,
            "last_name": lastName,
            "source": "Siri",
            "stage": "New"
        ]

        if let phone = phone, !phone.isEmpty {
            body["phone"] = phone
        }
        if let email = email, !email.isEmpty {
            body["email"] = email
        }

        let result = try await PerenniaAPIClient.post(
            path: "/api/v1/leads/",
            body: body
        )

        let createdName = [
            result["first_name"] as? String,
            result["last_name"] as? String
        ].compactMap { $0 }.joined(separator: " ")

        let displayName = createdName.isEmpty ? name : createdName
        return .result(dialog: "Lead \"\(displayName)\" has been created in Perennia AI.")
    }
}


// MARK: - 3. CallBorrowerIntent

@available(iOS 16.0, *)
struct CallBorrowerIntent: AppIntent {

    static var title: LocalizedStringResource = "Call a Borrower"

    static var description = IntentDescription(
        "Search for a borrower by name and place a phone call.",
        categoryName: "Contacts"
    )

    /// Opens the app so the tel:// URL scheme triggers the phone dialer.
    static var openAppWhenRun: Bool = true

    @Parameter(title: "Borrower Name", description: "Name to search for")
    var name: String

    static var parameterSummary: some ParameterSummary {
        Summary("Call borrower \(\.$name)")
    }

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let leads = try await PerenniaAPIClient.getArray(
            path: "/api/v1/leads/",
            queryItems: [URLQueryItem(name: "search", value: name)]
        )

        // Filter leads that have a phone number
        let withPhone = leads.filter { lead in
            if let phone = lead["phone"] as? String, !phone.isEmpty {
                return true
            }
            if let mobile = lead["mobile_phone"] as? String, !mobile.isEmpty {
                return true
            }
            return false
        }

        guard !withPhone.isEmpty else {
            return .result(
                dialog: "No borrowers named \"\(name)\" with a phone number were found."
            )
        }

        // Pick the best match (first result if single, disambiguate if multiple)
        let target: [String: Any]
        if withPhone.count == 1 {
            target = withPhone[0]
        } else {
            // Show the top matches and use the first one.
            // Full disambiguation would require a custom entity query (future enhancement).
            let names = withPhone.prefix(5).compactMap { lead -> String? in
                let first = lead["first_name"] as? String ?? ""
                let last = lead["last_name"] as? String ?? ""
                let full = "\(first) \(last)".trimmingCharacters(in: .whitespaces)
                return full.isEmpty ? nil : full
            }

            if withPhone.count <= 5 {
                // Small list — pick the first and inform the user
                target = withPhone[0]
                let listText = names.joined(separator: ", ")
                NSLog("[AppIntents] Multiple matches for \"%@\": %@. Using first.", name, listText)
            } else {
                // Too many — ask user to be more specific
                return .result(
                    dialog: "Found \(withPhone.count) borrowers matching \"\(name)\". Please be more specific. Top matches: \(names.joined(separator: ", "))"
                )
            }
        }

        let phoneNumber = (target["phone"] as? String)
            ?? (target["mobile_phone"] as? String)
            ?? ""

        let firstName = target["first_name"] as? String ?? ""
        let lastName = target["last_name"] as? String ?? ""
        let displayName = "\(firstName) \(lastName)".trimmingCharacters(in: .whitespaces)

        // Clean phone number for tel:// URL
        let cleaned = phoneNumber.components(separatedBy: CharacterSet.decimalDigits.inverted).joined()
        guard !cleaned.isEmpty, let telURL = URL(string: "tel://\(cleaned)") else {
            return .result(
                dialog: "Found \(displayName) but their phone number \"\(phoneNumber)\" is invalid."
            )
        }

        // Open the dialer on the main thread
        await MainActor.run {
            UIApplication.shared.open(telURL, options: [:], completionHandler: nil)
        }

        return .result(dialog: "Calling \(displayName) at \(phoneNumber).")
    }
}


// MARK: - 4. CheckTasksIntent

@available(iOS 16.0, *)
struct CheckTasksIntent: AppIntent {

    static var title: LocalizedStringResource = "Check Today's Tasks"

    static var description = IntentDescription(
        "View your tasks due today in Perennia AI.",
        categoryName: "Tasks"
    )

    static var openAppWhenRun: Bool = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let today = Self.todayString()

        let tasks = try await PerenniaAPIClient.getArray(
            path: "/api/v1/mobile/tasks",
            queryItems: [URLQueryItem(name: "due", value: today)]
        )

        if tasks.isEmpty {
            return .result(dialog: "You have no tasks due today. Nice work!")
        }

        var lines: [String] = []
        for (index, task) in tasks.prefix(10).enumerated() {
            let title = task["title"] as? String
                ?? task["name"] as? String
                ?? task["description"] as? String
                ?? "Untitled task"
            let status = task["status"] as? String ?? ""
            let statusIcon = status.lowercased() == "completed" ? "[done]" : "[open]"
            lines.append("\(index + 1). \(statusIcon) \(title)")
        }

        let remaining = tasks.count > 10 ? "\n...and \(tasks.count - 10) more." : ""
        let header = "You have \(tasks.count) task\(tasks.count == 1 ? "" : "s") due today:\n\n"

        return .result(dialog: "\(header)\(lines.joined(separator: "\n"))\(remaining)")
    }

    /// Format today's date as YYYY-MM-DD for the API query parameter.
    private static func todayString() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = .current
        return formatter.string(from: Date())
    }
}


// MARK: - 5. QuickNoteIntent

@available(iOS 16.0, *)
struct QuickNoteIntent: AppIntent {

    static var title: LocalizedStringResource = "Add a Note"

    static var description = IntentDescription(
        "Add a note to a lead's activity feed in Perennia AI.",
        categoryName: "Notes"
    )

    static var openAppWhenRun: Bool = false

    @Parameter(title: "Lead Name", description: "Name of the lead to add a note to")
    var leadName: String

    @Parameter(title: "Note", description: "The note content")
    var note: String

    static var parameterSummary: some ParameterSummary {
        Summary("Add note \(\.$note) to \(\.$leadName)")
    }

    func perform() async throws -> some IntentResult & ProvidesDialog {
        // Search for the lead by name
        let leads = try await PerenniaAPIClient.getArray(
            path: "/api/v1/leads/",
            queryItems: [URLQueryItem(name: "search", value: leadName)]
        )

        guard let lead = leads.first else {
            return .result(
                dialog: "No lead named \"\(leadName)\" was found. Please check the name and try again."
            )
        }

        guard let leadId = lead["id"] else {
            throw PerenniaIntentError.unexpectedResponse
        }

        // Post the note as an activity entry
        let body: [String: Any] = [
            "type": "note",
            "content": note,
            "source": "siri"
        ]

        _ = try await PerenniaAPIClient.post(
            path: "/api/v1/leads/\(leadId)/activities",
            body: body
        )

        let firstName = lead["first_name"] as? String ?? ""
        let lastName = lead["last_name"] as? String ?? ""
        let displayName = "\(firstName) \(lastName)".trimmingCharacters(in: .whitespaces)

        return .result(dialog: "Note added to \(displayName.isEmpty ? leadName : displayName)'s record.")
    }
}
