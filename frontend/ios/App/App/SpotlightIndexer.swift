/**
 * SpotlightIndexer.swift
 * Perennia AI — iOS Spotlight Search Indexing Service
 *
 * Indexes leads, loans, and tasks into Core Spotlight so loan officers can
 * search their CRM data directly from the iOS home screen.
 *
 * - Fetches data from the Perennia API using the stored auth token
 * - Indexes up to 500 items per category (leads, loans, tasks)
 * - Sets expiration dates (leads: 30 days, loans: 90 days, tasks: 7 days after due)
 * - Runs all indexing on a background queue to avoid blocking the main thread
 * - Supports incremental updates via indexItem(type:id:data:)
 * - Exposes a Capacitor plugin method for React-triggered re-indexing
 *
 * Integration:
 *   - Called from AppDelegate on launch and resume (throttled to 30 min)
 *   - Registered as a Capacitor plugin via PerenniaViewController.capacitorDidLoad()
 *   - Deep link handling is in SpotlightHandler.swift
 */

import Foundation
import CoreSpotlight
import UniformTypeIdentifiers
import Capacitor

// MARK: - Domain Constants

private enum SpotlightDomain {
    static let leads = "com.perenniaai.crm.leads"
    static let loans = "com.perenniaai.crm.loans"
    static let tasks = "com.perenniaai.crm.tasks"
}

private enum SpotlightPrefix {
    static let lead = "lead_"
    static let loan = "loan_"
    static let task = "task_"
}

// MARK: - API Response Models

/// Minimal lead representation from /api/v1/leads/
private struct APILead: Decodable {
    let id: Int
    let first_name: String?
    let last_name: String?
    let email: String?
    let phone: String?
    let stage: String?
    let company: String?
}

/// Minimal loan representation from /api/v1/loans/
private struct APILoan: Decodable {
    let id: Int
    let borrower_first_name: String?
    let borrower_last_name: String?
    let loan_amount: Double?
    let stage: String?
    let property_address: String?
    let loan_number: String?
}

/// Minimal task representation from /api/v1/tasks/
private struct APITask: Decodable {
    let id: Int
    let title: String?
    let description: String?
    let due_date: String?
    let priority: String?
    let status: String?
}

// MARK: - SpotlightIndexer

/// Singleton service for indexing CRM data into iOS Spotlight.
///
/// All public methods dispatch work onto a serial background queue.
/// The indexer reads the auth token from Capacitor's UserDefaults storage
/// and calls the Perennia API to fetch data for indexing.
final class SpotlightIndexer {

    static let shared = SpotlightIndexer()

    // MARK: - Configuration

    private let apiBaseURL = "https://api.perenniaai.com"
    private let maxItemsPerCategory = 500
    private let leadExpirationDays: TimeInterval = 30 * 24 * 60 * 60  // 30 days
    private let taskExpirationDaysAfterDue: TimeInterval = 7 * 24 * 60 * 60  // 7 days after due
    private let loanExpirationDays: TimeInterval = 90 * 24 * 60 * 60  // 90 days
    private let reindexThrottleSeconds: TimeInterval = 30 * 60  // 30 minutes

    // MARK: - State

    private let indexQueue = DispatchQueue(label: "com.perenniaai.crm.spotlight", qos: .utility)
    private let searchableIndex = CSSearchableIndex.default()
    /// Timestamp of the last successful full index. Exposed read-only for status checks.
    private(set) var lastFullIndexDate: Date?
    private let isoFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private let fallbackISOFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    private init() {}

    // MARK: - Auth Token

    /// Read the JWT auth token from the Keychain.
    private func getAuthToken() -> String? {
        return KeychainService.shared.authToken
    }

    /// Check whether the user is authenticated (token exists).
    private var isAuthenticated: Bool {
        return getAuthToken() != nil
    }

    // MARK: - Public API

    /// Index all CRM data (leads, loans, tasks) from the API.
    ///
    /// Fetches data in parallel and indexes into Spotlight.
    /// Throttled to run at most once per 30 minutes unless `force` is true.
    /// Safe to call from any thread — work is dispatched to a background queue.
    func indexAllData(force: Bool = false) {
        indexQueue.async { [weak self] in
            guard let self = self else { return }

            // Throttle: skip if last index was recent (unless forced)
            if !force, let lastIndex = self.lastFullIndexDate,
               Date().timeIntervalSince(lastIndex) < self.reindexThrottleSeconds {
                NSLog("[SpotlightIndexer] Skipping re-index — last indexed %.0f seconds ago",
                      Date().timeIntervalSince(lastIndex))
                return
            }

            guard self.isAuthenticated else {
                NSLog("[SpotlightIndexer] Skipping index — user not authenticated")
                return
            }

            NSLog("[SpotlightIndexer] Starting full index...")

            let group = DispatchGroup()
            var allItems: [CSSearchableItem] = []
            let itemsLock = NSLock()

            // Fetch and index leads
            group.enter()
            self.fetchLeads { leads in
                let items = leads.map { self.searchableItem(forLead: $0) }
                itemsLock.lock()
                allItems.append(contentsOf: items)
                itemsLock.unlock()
                AuditLogger.shared.log(event: .dataAccess, details: ["source": "spotlight_index", "type": "leads", "count": "\(items.count)"])
                NSLog("[SpotlightIndexer] Prepared %d lead items", items.count)
                group.leave()
            }

            // Fetch and index loans
            group.enter()
            self.fetchLoans { loans in
                let items = loans.map { self.searchableItem(forLoan: $0) }
                itemsLock.lock()
                allItems.append(contentsOf: items)
                itemsLock.unlock()
                AuditLogger.shared.log(event: .dataAccess, details: ["source": "spotlight_index", "type": "loans", "count": "\(items.count)"])
                NSLog("[SpotlightIndexer] Prepared %d loan items", items.count)
                group.leave()
            }

            // Fetch and index tasks
            group.enter()
            self.fetchTasks { tasks in
                let items = tasks.map { self.searchableItem(forTask: $0) }
                itemsLock.lock()
                allItems.append(contentsOf: items)
                itemsLock.unlock()
                AuditLogger.shared.log(event: .dataAccess, details: ["source": "spotlight_index", "type": "tasks", "count": "\(items.count)"])
                NSLog("[SpotlightIndexer] Prepared %d task items", items.count)
                group.leave()
            }

            group.wait()

            guard !allItems.isEmpty else {
                NSLog("[SpotlightIndexer] No items to index")
                return
            }

            // Batch index all items
            self.searchableIndex.indexSearchableItems(allItems) { error in
                if let error = error {
                    NSLog("[SpotlightIndexer] Indexing error: %@", error.localizedDescription)
                } else {
                    NSLog("[SpotlightIndexer] Successfully indexed %d items", allItems.count)
                    self.lastFullIndexDate = Date()
                }
            }
        }
    }

    /// Index a single item incrementally (for real-time updates).
    ///
    /// - Parameters:
    ///   - type: The item type ("lead", "loan", or "task")
    ///   - id: The item's integer ID from the API
    ///   - data: A dictionary with the item's fields (keys match API response)
    func indexItem(type: String, id: Int, data: [String: Any]) {
        indexQueue.async { [weak self] in
            guard let self = self else { return }

            let item: CSSearchableItem?

            switch type {
            case "lead":
                let lead = APILead(
                    id: id,
                    first_name: data["first_name"] as? String,
                    last_name: data["last_name"] as? String,
                    email: data["email"] as? String,
                    phone: data["phone"] as? String,
                    stage: data["stage"] as? String,
                    company: data["company"] as? String
                )
                item = self.searchableItem(forLead: lead)

            case "loan":
                let loan = APILoan(
                    id: id,
                    borrower_first_name: data["borrower_first_name"] as? String,
                    borrower_last_name: data["borrower_last_name"] as? String,
                    loan_amount: data["loan_amount"] as? Double,
                    stage: data["stage"] as? String,
                    property_address: data["property_address"] as? String,
                    loan_number: data["loan_number"] as? String
                )
                item = self.searchableItem(forLoan: loan)

            case "task":
                let task = APITask(
                    id: id,
                    title: data["title"] as? String,
                    description: data["description"] as? String,
                    due_date: data["due_date"] as? String,
                    priority: data["priority"] as? String,
                    status: data["status"] as? String
                )
                item = self.searchableItem(forTask: task)

            default:
                NSLog("[SpotlightIndexer] Unknown item type: %@", type)
                return
            }

            if let item = item {
                self.searchableIndex.indexSearchableItems([item]) { error in
                    if let error = error {
                        NSLog("[SpotlightIndexer] Error indexing %@_%d: %@", type, id, error.localizedDescription)
                    }
                }
            }
        }
    }

    /// Remove a specific item from the Spotlight index.
    ///
    /// - Parameters:
    ///   - type: The item type ("lead", "loan", or "task")
    ///   - id: The item's integer ID
    func removeItem(type: String, id: Int) {
        let identifier: String
        switch type {
        case "lead": identifier = "\(SpotlightPrefix.lead)\(id)"
        case "loan": identifier = "\(SpotlightPrefix.loan)\(id)"
        case "task": identifier = "\(SpotlightPrefix.task)\(id)"
        default: return
        }

        searchableIndex.deleteSearchableItems(withIdentifiers: [identifier]) { error in
            if let error = error {
                NSLog("[SpotlightIndexer] Error removing %@: %@", identifier, error.localizedDescription)
            }
        }
    }

    /// Remove all items for a specific domain (e.g., all leads).
    func removeAllItems(forDomain domain: String) {
        searchableIndex.deleteSearchableItems(withDomainIdentifiers: [domain]) { error in
            if let error = error {
                NSLog("[SpotlightIndexer] Error removing domain %@: %@", domain, error.localizedDescription)
            }
        }
    }

    /// Remove all Perennia items from the Spotlight index.
    /// Called on logout to clear sensitive CRM data.
    func removeAllItems() {
        let domains = [SpotlightDomain.leads, SpotlightDomain.loans, SpotlightDomain.tasks]
        searchableIndex.deleteSearchableItems(withDomainIdentifiers: domains) { error in
            if let error = error {
                NSLog("[SpotlightIndexer] Error removing all items: %@", error.localizedDescription)
            } else {
                NSLog("[SpotlightIndexer] All Spotlight items removed")
            }
        }
        lastFullIndexDate = nil
    }

    /// Remove expired items by re-indexing the current active set.
    /// CoreSpotlight handles expiration automatically via expirationDate, but this
    /// provides an explicit refresh path.
    func removeExpiredItems() {
        indexQueue.async { [weak self] in
            guard let self = self, self.isAuthenticated else { return }

            // Re-index tasks — completed/deleted tasks will not be in the response
            // and their expiration dates will cause CoreSpotlight to prune them.
            self.fetchTasks { tasks in
                let items = tasks.map { self.searchableItem(forTask: $0) }
                if !items.isEmpty {
                    self.searchableIndex.indexSearchableItems(items) { error in
                        if let error = error {
                            NSLog("[SpotlightIndexer] Error refreshing tasks: %@", error.localizedDescription)
                        }
                    }
                }
            }
        }
    }

    /// Whether enough time has passed since the last index to warrant re-indexing.
    var shouldReindex: Bool {
        guard let lastIndex = lastFullIndexDate else { return true }
        return Date().timeIntervalSince(lastIndex) >= reindexThrottleSeconds
    }

    // MARK: - API Fetching

    /// Fetch leads from the API.
    private func fetchLeads(completion: @escaping ([APILead]) -> Void) {
        fetchFromAPI(
            path: "/api/v1/leads/?limit=\(maxItemsPerCategory)&sort=-updated_at",
            completion: completion
        )
    }

    /// Fetch loans from the API.
    private func fetchLoans(completion: @escaping ([APILoan]) -> Void) {
        fetchFromAPI(
            path: "/api/v1/loans/?limit=\(maxItemsPerCategory)&sort=-updated_at",
            completion: completion
        )
    }

    /// Fetch pending tasks from the API.
    private func fetchTasks(completion: @escaping ([APITask]) -> Void) {
        fetchFromAPI(
            path: "/api/v1/tasks/?limit=\(maxItemsPerCategory)&status=pending&sort=-due_date",
            completion: completion
        )
    }

    /// Generic API fetch with JSON decoding.
    /// Tries to decode the response as either a bare array or a paginated wrapper
    /// with a "results", "data", or "items" key.
    private func fetchFromAPI<T: Decodable>(path: String, completion: @escaping ([T]) -> Void) {
        guard let token = getAuthToken(),
              let url = URL(string: apiBaseURL + path) else {
            completion([])
            return
        }

        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 30

        let task = URLSession.shared.dataTask(with: request) { data, response, error in
            guard let data = data, error == nil else {
                if let error = error {
                    NSLog("[SpotlightIndexer] API fetch error for %@: %@", path, error.localizedDescription)
                }
                completion([])
                return
            }

            // Check HTTP status
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode != 200 {
                NSLog("[SpotlightIndexer] API returned %d for %@", httpResponse.statusCode, path)
                if httpResponse.statusCode == 401 {
                    AuditLogger.shared.log(event: .authFailure, details: [
                        "source": "spotlight_index",
                        "path": path,
                        "status": "401"
                    ])
                }
                completion([])
                return
            }

            let decoder = JSONDecoder()

            // Try decoding as bare array first
            if let items = try? decoder.decode([T].self, from: data) {
                completion(Array(items.prefix(self.maxItemsPerCategory)))
                return
            }

            // Try paginated wrapper with common key names
            struct PaginatedResults: Decodable {
                let results: [T]?
                let data: [T]?
                let items: [T]?
            }

            if let wrapper = try? decoder.decode(PaginatedResults.self, from: data) {
                let items = wrapper.results ?? wrapper.data ?? wrapper.items ?? []
                completion(Array(items.prefix(self.maxItemsPerCategory)))
                return
            }

            NSLog("[SpotlightIndexer] Failed to decode response for %@", path)
            completion([])
        }
        task.resume()
    }

    // MARK: - Searchable Item Builders

    /// Create a CSSearchableItem for a lead.
    /// PII protection: Title shows "Lead -- [Stage]" (visible from lock screen).
    /// Full name, email, phone are in contentDescription (visible only after unlock).
    private func searchableItem(forLead lead: APILead) -> CSSearchableItem {
        let attributes = CSSearchableItemAttributeSet(contentType: .contact)
        let uniqueID = "\(SpotlightPrefix.lead)\(lead.id)"

        // Title: non-PII label with stage (visible from lock screen)
        let stage = lead.stage ?? "New"
        attributes.displayName = "Lead \u{2014} \(stage)"

        // Content description: PII details (only visible after device unlock)
        let firstName = lead.first_name ?? ""
        let lastName = lead.last_name ?? ""
        let fullName = [firstName, lastName].filter { !$0.isEmpty }.joined(separator: " ")
        var descParts: [String] = []
        if !fullName.isEmpty { descParts.append(fullName) }
        if let phone = lead.phone, !phone.isEmpty {
            descParts.append(phone)
        }
        if let email = lead.email, !email.isEmpty {
            descParts.append(email)
        }
        if let company = lead.company, !company.isEmpty {
            descParts.append(company)
        }
        attributes.contentDescription = descParts.isEmpty
            ? "Lead #\(lead.id)"
            : descParts.joined(separator: " \u{2014} ")

        // Dedup identifier
        attributes.relatedUniqueIdentifier = uniqueID

        // Contact fields
        if let email = lead.email {
            attributes.supportsEmailAddress = true as NSNumber
            attributes.emailAddresses = [email]
        }
        if let phone = lead.phone {
            attributes.supportsPhoneCall = true as NSNumber
            attributes.phoneNumbers = [phone]
        }
        if let company = lead.company {
            attributes.organizationName = company
        }

        // Thumbnail — system person icon
        attributes.thumbnailData = personIconData()

        // Keywords for search
        var keywords = ["lead", "contact", "mortgage"]
        if !firstName.isEmpty { keywords.append(firstName.lowercased()) }
        if !lastName.isEmpty { keywords.append(lastName.lowercased()) }
        keywords.append(stage.lowercased())
        attributes.keywords = keywords

        // Expiration
        attributes.expirationDate = Date().addingTimeInterval(leadExpirationDays)

        return CSSearchableItem(
            uniqueIdentifier: uniqueID,
            domainIdentifier: SpotlightDomain.leads,
            attributeSet: attributes
        )
    }

    /// Create a CSSearchableItem for a loan.
    /// PII protection: Title shows "Loan -- [Stage]" (visible from lock screen).
    /// Borrower names and addresses are in contentDescription (visible only after unlock).
    private func searchableItem(forLoan loan: APILoan) -> CSSearchableItem {
        let attributes = CSSearchableItemAttributeSet(contentType: UTType.financeDocument)
        let uniqueID = "\(SpotlightPrefix.loan)\(loan.id)"

        // Title: non-PII label with stage (visible from lock screen)
        let stage = loan.stage ?? "Application"
        attributes.displayName = "Loan \u{2014} \(stage)"

        // Content description: PII details (only visible after device unlock)
        let firstName = loan.borrower_first_name ?? ""
        let lastName = loan.borrower_last_name ?? ""
        let borrowerName = [firstName, lastName].filter { !$0.isEmpty }.joined(separator: " ")
        var descParts: [String] = []
        if !borrowerName.isEmpty { descParts.append(borrowerName) }
        if let amount = loan.loan_amount, amount > 0 {
            let formatter = NumberFormatter()
            formatter.numberStyle = .currency
            formatter.currencyCode = "USD"
            formatter.maximumFractionDigits = 0
            if let formatted = formatter.string(from: NSNumber(value: amount)) {
                descParts.append(formatted)
            }
        }
        if let address = loan.property_address, !address.isEmpty {
            descParts.append(address)
        }
        if let loanNum = loan.loan_number, !loanNum.isEmpty {
            descParts.append("#\(loanNum)")
        }
        attributes.contentDescription = descParts.isEmpty
            ? "Loan #\(loan.id)"
            : descParts.joined(separator: " \u{2014} ")

        // Dedup identifier
        attributes.relatedUniqueIdentifier = uniqueID

        // Thumbnail — system document icon
        attributes.thumbnailData = documentIconData()

        // Keywords
        var keywords = ["loan", "mortgage", "pipeline"]
        if !firstName.isEmpty { keywords.append(firstName.lowercased()) }
        if !lastName.isEmpty { keywords.append(lastName.lowercased()) }
        keywords.append(stage.lowercased())
        if let loanNum = loan.loan_number { keywords.append(loanNum) }
        if let address = loan.property_address { keywords.append(address.lowercased()) }
        attributes.keywords = keywords

        // Expiration
        attributes.expirationDate = Date().addingTimeInterval(loanExpirationDays)

        return CSSearchableItem(
            uniqueIdentifier: uniqueID,
            domainIdentifier: SpotlightDomain.loans,
            attributeSet: attributes
        )
    }

    /// Create a CSSearchableItem for a task.
    /// PII protection: Task title is kept as-is (usually not PII).
    /// Any contact names in the description are moved to contentDescription
    /// (visible only after device unlock). Priority and due date stay in the title area.
    private func searchableItem(forTask task: APITask) -> CSSearchableItem {
        let attributes = CSSearchableItemAttributeSet(contentType: UTType.toDoItem)
        let uniqueID = "\(SpotlightPrefix.task)\(task.id)"

        // Title: task title (usually non-PII, e.g. "Follow up", "Submit docs")
        var titleParts: [String] = [task.title ?? "Task #\(task.id)"]
        if let priority = task.priority, !priority.isEmpty {
            titleParts.append(priority.capitalized)
        }
        if let dueDate = task.due_date, !dueDate.isEmpty {
            titleParts.append("Due: \(formatDueDate(dueDate))")
        }
        attributes.displayName = titleParts.joined(separator: " \u{2014} ")

        // Content description: task body which may contain contact names
        // (only visible after device unlock)
        if let desc = task.description, !desc.isEmpty {
            attributes.contentDescription = desc
        }

        // Dedup identifier
        attributes.relatedUniqueIdentifier = uniqueID

        // Due date
        if let dueDateStr = task.due_date {
            attributes.dueDate = parseISO8601(dueDateStr)
        }

        // Thumbnail — system checklist icon
        attributes.thumbnailData = taskIconData()

        // Keywords
        var keywords = ["task", "todo", "action"]
        if let title = task.title { keywords.append(title.lowercased()) }
        if let priority = task.priority { keywords.append(priority.lowercased()) }
        attributes.keywords = keywords

        // Expiration: 7 days after due date, or 30 days from now if no due date
        if let dueDateStr = task.due_date, let dueDate = parseISO8601(dueDateStr) {
            attributes.expirationDate = dueDate.addingTimeInterval(taskExpirationDaysAfterDue)
        } else {
            attributes.expirationDate = Date().addingTimeInterval(30 * 24 * 60 * 60)
        }

        return CSSearchableItem(
            uniqueIdentifier: uniqueID,
            domainIdentifier: SpotlightDomain.tasks,
            attributeSet: attributes
        )
    }

    // MARK: - Helpers

    /// Parse an ISO 8601 date string, trying fractional seconds first, then without.
    private func parseISO8601(_ string: String) -> Date? {
        return isoFormatter.date(from: string) ?? fallbackISOFormatter.date(from: string)
    }

    /// Format a due date string for display in Spotlight results.
    private func formatDueDate(_ isoString: String) -> String {
        guard let date = parseISO8601(isoString) else { return isoString }
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }

    /// Generate a small person icon as PNG data for lead thumbnails.
    private func personIconData() -> Data? {
        return systemIconData(named: "person.circle.fill")
    }

    /// Generate a small document icon as PNG data for loan thumbnails.
    private func documentIconData() -> Data? {
        return systemIconData(named: "doc.text.fill")
    }

    /// Generate a small task icon as PNG data for task thumbnails.
    private func taskIconData() -> Data? {
        return systemIconData(named: "checkmark.circle.fill")
    }

    /// Render a SF Symbol as a 60x60 PNG image for use as a Spotlight thumbnail.
    private func systemIconData(named name: String) -> Data? {
        let size = CGSize(width: 60, height: 60)
        let config = UIImage.SymbolConfiguration(pointSize: 40, weight: .regular)
        guard let image = UIImage(systemName: name, withConfiguration: config) else { return nil }

        let renderer = UIGraphicsImageRenderer(size: size)
        let rendered = renderer.image { _ in
            // Draw centered
            let imageSize = image.size
            let x = (size.width - imageSize.width) / 2
            let y = (size.height - imageSize.height) / 2
            image.withTintColor(.systemBlue).draw(at: CGPoint(x: x, y: y))
        }
        return rendered.pngData()
    }
}

// MARK: - UTType Extension for Custom Content Types

private extension UTType {
    /// A content type representing a financial document (loan file).
    /// Falls back to .content if the specific type is unavailable.
    static var financeDocument: UTType {
        return UTType("public.financial-content") ?? .content
    }

    /// A content type representing a to-do / task item.
    static var toDoItem: UTType {
        return UTType("public.to-do-item") ?? .content
    }
}

// MARK: - Capacitor Plugin

/// Capacitor plugin that exposes Spotlight indexing to the React app.
///
/// Methods available from JavaScript:
///   - SpotlightSearch.indexAllData({ force?: boolean })  — full re-index
///   - SpotlightSearch.indexItem({ type, id, data })      — index one item
///   - SpotlightSearch.removeItem({ type, id })           — remove one item
///   - SpotlightSearch.removeAllItems()                   — clear all indexed data
///   - SpotlightSearch.getIndexStatus()                   — check last index time
@objc(SpotlightSearchPlugin)
public class SpotlightSearchPlugin: CAPPlugin, CAPBridgedPlugin {

    public let identifier = "SpotlightSearchPlugin"
    public let jsName = "SpotlightSearch"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "indexAllData", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "indexItem", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "removeItem", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "removeAllItems", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getIndexStatus", returnType: CAPPluginReturnPromise)
    ]

    @objc func indexAllData(_ call: CAPPluginCall) {
        let force = call.getBool("force") ?? false
        SpotlightIndexer.shared.indexAllData(force: force)
        call.resolve(["started": true])
    }

    @objc func indexItem(_ call: CAPPluginCall) {
        guard let type = call.getString("type"),
              let id = call.getInt("id") else {
            call.reject("Missing required parameters: type, id")
            return
        }

        let data = call.getObject("data") ?? [:]
        var nativeData: [String: Any] = [:]
        for (key, value) in data {
            nativeData[key] = value
        }

        SpotlightIndexer.shared.indexItem(type: type, id: id, data: nativeData)
        call.resolve(["indexed": true])
    }

    @objc func removeItem(_ call: CAPPluginCall) {
        guard let type = call.getString("type"),
              let id = call.getInt("id") else {
            call.reject("Missing required parameters: type, id")
            return
        }

        SpotlightIndexer.shared.removeItem(type: type, id: id)
        call.resolve(["removed": true])
    }

    @objc func removeAllItems(_ call: CAPPluginCall) {
        SpotlightIndexer.shared.removeAllItems()
        call.resolve(["cleared": true])
    }

    @objc func getIndexStatus(_ call: CAPPluginCall) {
        let indexer = SpotlightIndexer.shared
        var result: [String: Any] = [
            "shouldReindex": indexer.shouldReindex,
            "isAuthenticated": KeychainService.shared.authToken != nil
        ]

        if let lastIndex = indexer.lastFullIndexDate {
            result["lastIndexedAt"] = ISO8601DateFormatter().string(from: lastIndex)
        }

        call.resolve(result)
    }
}
