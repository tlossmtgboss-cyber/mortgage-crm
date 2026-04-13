import UIKit
import CarPlay
import os.log

// MARK: - Logger

private let logger = Logger(subsystem: "com.perenniaai.crm", category: "CarPlay")

// MARK: - Data Cache

/// Thread-safe in-memory cache for CarPlay data so the UI remains populated briefly if the network drops.
private final class CarPlayDataCache {
    static let shared = CarPlayDataCache()

    private let queue = DispatchQueue(label: "com.perenniaai.carplay.cache", attributes: .concurrent)

    private var _dashboard: CPDashboardData?
    private var _tasks: [CPTaskItem] = []
    private var _leads: [LeadItem] = []
    private var _loans: [LoanItem] = []
    private var _rateAlerts: [CPRateAlert] = []
    private var _events: [CalendarEvent] = []

    var dashboard: CPDashboardData? {
        get { queue.sync { _dashboard } }
        set { queue.async(flags: .barrier) { self._dashboard = newValue } }
    }
    var tasks: [CPTaskItem] {
        get { queue.sync { _tasks } }
        set { queue.async(flags: .barrier) { self._tasks = newValue } }
    }
    var leads: [LeadItem] {
        get { queue.sync { _leads } }
        set { queue.async(flags: .barrier) { self._leads = newValue } }
    }
    var loans: [LoanItem] {
        get { queue.sync { _loans } }
        set { queue.async(flags: .barrier) { self._loans = newValue } }
    }
    var rateAlerts: [CPRateAlert] {
        get { queue.sync { _rateAlerts } }
        set { queue.async(flags: .barrier) { self._rateAlerts = newValue } }
    }
    var events: [CalendarEvent] {
        get { queue.sync { _events } }
        set { queue.async(flags: .barrier) { self._events = newValue } }
    }
}

// MARK: - CarPlaySceneDelegate

@available(iOS 14.0, *)
class CarPlaySceneDelegate: UIResponder, CPTemplateApplicationSceneDelegate {

    // MARK: - Properties

    fileprivate var interfaceController: CPInterfaceController?
    fileprivate var tabBarTemplate: CPTabBarTemplate?
    private var refreshTimer: Timer?
    private var notificationObservers: [NSObjectProtocol] = []

    private let cache = CarPlayDataCache.shared
    private let api = CarPlayAPIService.shared

    private static let refreshInterval: TimeInterval = 60

    // Tab indices for targeted refresh
    private enum TabIndex: Int {
        case dashboard = 0
        case contacts = 1
        case tasks = 2
        case schedule = 3
    }

    // MARK: - CPTemplateApplicationSceneDelegate

    func templateApplicationScene(
        _ templateApplicationScene: CPTemplateApplicationScene,
        didConnect interfaceController: CPInterfaceController
    ) {
        logger.info("CarPlay connected")
        self.interfaceController = interfaceController
        setupCarPlayInterface()
        startAutoRefresh()
        registerNotificationObservers()
    }

    func templateApplicationScene(
        _ templateApplicationScene: CPTemplateApplicationScene,
        didDisconnectInterfaceController interfaceController: CPInterfaceController
    ) {
        logger.info("CarPlay disconnected")
        stopAutoRefresh()
        removeNotificationObservers()
        self.interfaceController = nil
        self.tabBarTemplate = nil
    }

    // MARK: - Interface Setup

    private func setupCarPlayInterface() {
        guard let interfaceController = interfaceController else { return }

        let dashboardTab = buildLoadingTemplate(title: "Dashboard", tabTitle: "Dashboard", tabImage: "chart.bar.fill")
        let contactsTab = buildLoadingTemplate(title: "Contacts", tabTitle: "Contacts", tabImage: "person.2.fill")
        let tasksTab = buildLoadingTemplate(title: "Tasks", tabTitle: "Tasks", tabImage: "checklist")
        let scheduleTab = buildLoadingTemplate(title: "Schedule", tabTitle: "Schedule", tabImage: "calendar")

        let tabBar = CPTabBarTemplate(templates: [dashboardTab, contactsTab, tasksTab, scheduleTab])
        self.tabBarTemplate = tabBar

        interfaceController.setRootTemplate(tabBar, animated: true) { success, error in
            if let error = error {
                logger.error("Failed to set root template: \(error.localizedDescription)")
            }
        }

        // Kick off initial data load for all tabs
        refreshAllTabs()
    }

    // MARK: - Loading / Error Templates

    private func buildLoadingTemplate(title: String, tabTitle: String, tabImage: String) -> CPListTemplate {
        let loadingItem = CPListItem(text: "Loading...", detailText: "Fetching latest data")
        loadingItem.isEnabled = false
        loadingItem.accessibilityLabel = "\(tabTitle): Loading, fetching latest data"
        let template = CPListTemplate(title: title, sections: [CPListSection(items: [loadingItem])])
        template.tabTitle = tabTitle
        template.tabImage = UIImage(systemName: tabImage)
        return template
    }

    private func buildErrorSection(message: String, retryAction: @escaping () -> Void) -> CPListSection {
        let errorItem = CPListItem(
            text: "Unable to load",
            detailText: message,
            image: UIImage(systemName: "exclamationmark.triangle.fill")
        )
        errorItem.accessibilityLabel = "Error: Unable to load. \(message)"
        errorItem.accessibilityHint = "Tap to retry loading"
        errorItem.handler = { _, completion in
            retryAction()
            completion()
        }
        let retryItem = CPListItem(
            text: "Tap to retry",
            detailText: nil,
            image: UIImage(systemName: "arrow.clockwise")
        )
        retryItem.accessibilityLabel = "Retry"
        retryItem.accessibilityHint = "Double tap to reload data"
        retryItem.handler = { _, completion in
            retryAction()
            completion()
        }
        return CPListSection(items: [errorItem, retryItem])
    }

    // MARK: - Auto Refresh

    private func startAutoRefresh() {
        stopAutoRefresh()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: Self.refreshInterval, repeats: true) { [weak self] _ in
            self?.refreshAllTabs()
        }
    }

    private func stopAutoRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }

    private func refreshAllTabs() {
        loadDashboard()
        loadContacts()
        loadTasks()
        loadSchedule()
    }

    // MARK: - Push Notification Observers

    private func registerNotificationObservers() {
        // Remove any existing observers first to prevent accumulation on reconnect
        removeNotificationObservers()

        let taskObserver = NotificationCenter.default.addObserver(
            forName: Notification.Name("PerenniaTaskUpdated"), object: nil, queue: .main
        ) { [weak self] _ in
            self?.loadTasks()
            self?.loadDashboard()
        }

        let leadObserver = NotificationCenter.default.addObserver(
            forName: Notification.Name("PerenniaLeadUpdated"), object: nil, queue: .main
        ) { [weak self] _ in
            self?.loadContacts()
            self?.loadDashboard()
        }

        let scheduleObserver = NotificationCenter.default.addObserver(
            forName: Notification.Name("PerenniaScheduleUpdated"), object: nil, queue: .main
        ) { [weak self] _ in
            self?.loadSchedule()
            self?.loadDashboard()
        }

        let rateObserver = NotificationCenter.default.addObserver(
            forName: Notification.Name("PerenniaRateAlertReceived"), object: nil, queue: .main
        ) { [weak self] _ in
            self?.loadDashboard()
        }

        notificationObservers = [taskObserver, leadObserver, scheduleObserver, rateObserver]
    }

    private func removeNotificationObservers() {
        for observer in notificationObservers {
            NotificationCenter.default.removeObserver(observer)
        }
        notificationObservers.removeAll()
    }

    // MARK: - Dashboard Tab

    private func loadDashboard() {
        Task { [weak self] in
            guard let self = self else { return }
            do {
                async let dashboardResult = self.api.fetchDashboard()
                async let rateAlertsResult = self.api.fetchRateAlerts()
                async let tasksResult = self.api.fetchTasks()
                async let eventsResult = self.api.fetchUpcomingEvents()

                let dashboard = try await dashboardResult
                let rateAlerts = try await rateAlertsResult
                let tasks = try await tasksResult
                let events = try await eventsResult

                self.cache.dashboard = dashboard
                self.cache.rateAlerts = rateAlerts

                let urgentTaskCount = tasks.filter { $0.priority == "high" || $0.priority == "urgent" }.count
                let todayEventCount = events.filter { Calendar.current.isDateInToday(($0.startDate ?? .distantPast)) }.count

                await MainActor.run {
                    self.updateDashboardTemplate(
                        dashboard: dashboard,
                        rateAlerts: rateAlerts,
                        urgentTaskCount: urgentTaskCount,
                        todayEventCount: todayEventCount
                    )
                }
            } catch {
                logger.error("Dashboard load failed: \(error.localizedDescription)")
                // Fall back to cached data if available
                if let cached = self.cache.dashboard {
                    await MainActor.run {
                        self.updateDashboardTemplate(
                            dashboard: cached,
                            rateAlerts: self.cache.rateAlerts,
                            urgentTaskCount: 0,
                            todayEventCount: 0
                        )
                    }
                } else {
                    await MainActor.run {
                        self.updateTabWithError(index: TabIndex.dashboard, message: "Check your connection") { [weak self] in
                            self?.loadDashboard()
                        }
                    }
                }
            }
        }
    }

    private func updateDashboardTemplate(
        dashboard: CPDashboardData,
        rateAlerts: [CPRateAlert],
        urgentTaskCount: Int,
        todayEventCount: Int
    ) {
        guard let tabBar = tabBarTemplate,
              tabBar.templates.count > TabIndex.dashboard.rawValue,
              let dashboardTemplate = tabBar.templates[TabIndex.dashboard.rawValue] as? CPListTemplate else { return }

        // Pipeline summary section
        let ps = dashboard.pipelineSummary
        let pipelineItems: [CPListItem] = [
            makeItem(
                text: "New Leads",
                detail: "\(dashboard.newLeadCount)",
                image: "person.3.fill"
            ),
            makeItem(
                text: "Active Loans",
                detail: "\(dashboard.activeLoanCount)",
                image: "doc.text.fill"
            ),
            makeItem(
                text: "In Underwriting",
                detail: "\(ps?.underwritingCount ?? 0)",
                image: "doc.text.magnifyingglass"
            ),
            makeItem(
                text: "Clear to Close",
                detail: "\(ps?.clearToCloseCount ?? 0)",
                image: "checkmark.seal.fill"
            )
        ]
        let pipelineSection = CPListSection(items: pipelineItems, header: "Pipeline", sectionIndexTitle: nil)

        // Urgent tasks with drill-down
        let urgentItem = makeItem(
            text: "Urgent Tasks",
            detail: urgentTaskCount > 0 ? "\(urgentTaskCount) need attention" : "All clear",
            image: "exclamationmark.triangle.fill"
        )
        urgentItem.accessibilityHint = "Double tap to view tasks"
        urgentItem.handler = { [weak self] _, completion in
            self?.drillIntoTasks()
            completion()
        }

        // Today's schedule with drill-down
        let scheduleItem = makeItem(
            text: "Today's Schedule",
            detail: todayEventCount > 0 ? "\(todayEventCount) events today" : "No events today",
            image: "calendar"
        )
        scheduleItem.accessibilityHint = "Double tap to view schedule"
        scheduleItem.handler = { [weak self] _, completion in
            self?.drillIntoSchedule()
            completion()
        }

        let activitySection = CPListSection(items: [urgentItem, scheduleItem], header: "Activity", sectionIndexTitle: nil)

        // Rate alerts section
        var rateItems: [CPListItem] = []
        for alert in rateAlerts.prefix(4) {
            let direction = alert.changeDirection == "up" ? "^" : (alert.changeDirection == "down" ? "v" : "-")
            let spokenDirection = alert.changeDirection == "up" ? "up" : (alert.changeDirection == "down" ? "down" : "unchanged")
            let bpChange = abs(alert.basisPointChange)
            let item = makeItem(
                text: alert.spokenRateType,
                detail: "\(alert.currentRate)% \(direction) \(bpChange)bp",
                image: alert.changeDirection == "down" ? "arrow.down.right" : "arrow.up.right"
            )
            item.accessibilityLabel = "\(alert.spokenRateType): \(alert.currentRate) percent, \(spokenDirection) \(bpChange) basis points"
            rateItems.append(item)
        }
        if rateItems.isEmpty {
            let noAlerts = makeItem(text: "No rate alerts", detail: "Rates stable", image: "checkmark.circle")
            noAlerts.isEnabled = false
            rateItems.append(noAlerts)
        }
        let rateSection = CPListSection(items: rateItems, header: "Rate Alerts", sectionIndexTitle: nil)

        dashboardTemplate.updateSections([pipelineSection, activitySection, rateSection])
    }

    // MARK: - Contacts Tab

    private func loadContacts() {
        Task { [weak self] in
            guard let self = self else { return }
            do {
                async let leadsResult = self.api.fetchLeads()
                async let loansResult = self.api.fetchLoans()

                let leads = try await leadsResult
                let loans = try await loansResult

                self.cache.leads = leads
                self.cache.loans = loans

                await MainActor.run {
                    self.updateContactsTemplate(leads: leads, loans: loans)
                }
            } catch {
                logger.error("Contacts load failed: \(error.localizedDescription)")
                let cachedLeads = self.cache.leads
                let cachedLoans = self.cache.loans
                if !cachedLeads.isEmpty || !cachedLoans.isEmpty {
                    await MainActor.run {
                        self.updateContactsTemplate(leads: cachedLeads, loans: cachedLoans)
                    }
                } else {
                    await MainActor.run {
                        self.updateTabWithError(index: TabIndex.contacts, message: "Check your connection") { [weak self] in
                            self?.loadContacts()
                        }
                    }
                }
            }
        }
    }

    private func updateContactsTemplate(leads: [LeadItem], loans: [LoanItem]) {
        guard let tabBar = tabBarTemplate,
              tabBar.templates.count > TabIndex.contacts.rawValue,
              let contactsTemplate = tabBar.templates[TabIndex.contacts.rawValue] as? CPListTemplate else { return }

        // Recent Leads section (most recent first, max 12 for CarPlay)
        var leadItems: [CPListItem] = []
        for lead in leads.prefix(12) {
            let item = makeItem(
                text: lead.fullName,
                detail: "\(lead.stage) - \(lead.updatedAt)",
                image: "person.fill"
            )
            item.accessibilityHint = "Double tap to view details"
            item.handler = { [weak self] (_, completion: @escaping () -> Void) in
                self?.showContactDetail(leadId: lead.id, name: lead.fullName, stage: lead.stage, lastActivity: lead.updatedAt)
                completion()
            }
            leadItems.append(item)
        }
        if leadItems.isEmpty {
            let empty = makeItem(text: "No recent leads", detail: nil, image: "person.fill.questionmark")
            empty.isEnabled = false
            leadItems.append(empty)
        }
        let leadsSection = CPListSection(items: leadItems, header: "Recent Leads", sectionIndexTitle: nil)

        // Active Borrowers section (from loans)
        var borrowerItems: [CPListItem] = []
        for loan in loans.prefix(12) {
            let item = makeItem(
                text: loan.borrowerName ?? "Unknown Borrower",
                detail: "\(loan.stage) - \(formatCurrency(loan.amount ?? 0))",
                image: "person.text.rectangle.fill"
            )
            item.accessibilityHint = "Double tap to view loan details"
            item.handler = { [weak self] (_, completion: @escaping () -> Void) in
                self?.showBorrowerDetail(loan: loan)
                completion()
            }
            borrowerItems.append(item)
        }
        if borrowerItems.isEmpty {
            let empty = makeItem(text: "No active borrowers", detail: nil, image: "person.fill.questionmark")
            empty.isEnabled = false
            borrowerItems.append(empty)
        }
        let borrowersSection = CPListSection(items: borrowerItems, header: "Active Borrowers", sectionIndexTitle: nil)

        contactsTemplate.updateSections([leadsSection, borrowersSection])
    }

    private func showContactDetail(leadId: Int, name: String, stage: String, lastActivity: String) {
        guard let interfaceController = interfaceController else { return }

        let stageItem = makeItem(text: "Stage", detail: stage, image: "flag.fill")
        stageItem.isEnabled = false

        let activityItem = makeItem(text: "Last Activity", detail: lastActivity, image: "clock.fill")
        activityItem.isEnabled = false

        let callItem = makeItem(text: "Call \(name)", detail: "Initiate call via Perennia", image: "phone.fill")
        callItem.accessibilityHint = "Double tap to start a phone call"
        callItem.handler = { [weak self] _, completion in
            self?.initiateCall(leadId: leadId, name: name)
            completion()
        }

        let detailTemplate = CPListTemplate(title: name, sections: [
            CPListSection(items: [stageItem, activityItem]),
            CPListSection(items: [callItem], header: "Actions", sectionIndexTitle: nil)
        ])

        interfaceController.pushTemplate(detailTemplate, animated: true, completion: nil)
    }

    private func showBorrowerDetail(loan: LoanItem) {
        guard let interfaceController = interfaceController else { return }

        let stageItem = makeItem(text: "Stage", detail: loan.stage, image: "flag.fill")
        stageItem.isEnabled = false

        let amountItem = makeItem(text: "Loan Amount", detail: formatCurrency(loan.amount ?? 0), image: "dollarsign.circle")
        amountItem.isEnabled = false

        let typeItem = makeItem(text: "Loan Type", detail: loan.loanType ?? "N/A", image: "doc.text")
        typeItem.isEnabled = false

        let borrowerDisplay = loan.borrowerName ?? "Unknown"
        let callItem = makeItem(text: "Call \(borrowerDisplay)", detail: "Initiate call via Perennia", image: "phone.fill")
        callItem.accessibilityHint = "Double tap to start a phone call"
        callItem.handler = { [weak self] (_, completion: @escaping () -> Void) in
            self?.initiateCall(leadId: loan.id, name: borrowerDisplay)
            completion()
        }

        let detailTemplate = CPListTemplate(title: borrowerDisplay, sections: [
            CPListSection(items: [stageItem, amountItem, typeItem]),
            CPListSection(items: [callItem], header: "Actions", sectionIndexTitle: nil)
        ])

        interfaceController.pushTemplate(detailTemplate, animated: true, completion: nil)
    }

    private func initiateCall(leadId: Int, name: String, phone: String? = nil) {
        Task { [weak self] in
            guard let self = self else { return }
            do {
                let callInitiation = try await self.api.callContact(phoneNumber: phone ?? "", contactName: name, leadId: leadId)
                logger.info("Call initiated for \(name): success=\(callInitiation.success)")
                await MainActor.run {
                    self.showAlert(title: "Calling \(name)", message: "Call is being connected...")
                }
            } catch {
                logger.error("Call failed for \(name): \(error.localizedDescription)")
                await MainActor.run {
                    self.showAlert(title: "Call Failed", message: "Could not connect call to \(name). Try again later.")
                }
            }
        }
    }

    // MARK: - Tasks Tab

    private func loadTasks() {
        Task { [weak self] in
            guard let self = self else { return }
            do {
                let tasks = try await self.api.fetchTasks()
                self.cache.tasks = tasks

                await MainActor.run {
                    self.updateTasksTemplate(tasks: tasks)
                }
            } catch {
                logger.error("Tasks load failed: \(error.localizedDescription)")
                let cachedTasks = self.cache.tasks
                if !cachedTasks.isEmpty {
                    await MainActor.run {
                        self.updateTasksTemplate(tasks: cachedTasks)
                    }
                } else {
                    await MainActor.run {
                        self.updateTabWithError(index: TabIndex.tasks, message: "Check your connection") { [weak self] in
                            self?.loadTasks()
                        }
                    }
                }
            }
        }
    }

    private func updateTasksTemplate(tasks: [CPTaskItem]) {
        guard let tabBar = tabBarTemplate,
              tabBar.templates.count > TabIndex.tasks.rawValue,
              let tasksTemplate = tabBar.templates[TabIndex.tasks.rawValue] as? CPListTemplate else { return }

        let calendar = Calendar.current
        let now = Date()
        let endOfToday = calendar.startOfDay(for: calendar.date(byAdding: .day, value: 1, to: now)!)
        let endOfWeek = calendar.startOfDay(for: calendar.date(byAdding: .day, value: 7, to: now)!)

        var overdue: [CPTaskItem] = []
        var dueToday: [CPTaskItem] = []
        var thisWeek: [CPTaskItem] = []

        let iso = ISO8601DateFormatter()
        for task in tasks {
            guard let dueDateStr = task.dueDate, let dueDate = iso.date(from: dueDateStr) else { continue }
            if dueDate < now && dueDate < calendar.startOfDay(for: now) {
                overdue.append(task)
            } else if dueDate < endOfToday {
                dueToday.append(task)
            } else if dueDate < endOfWeek {
                thisWeek.append(task)
            }
        }

        var sections: [CPListSection] = []

        // Overdue section (show first for urgency)
        if !overdue.isEmpty {
            let items = overdue.prefix(8).map { task in
                self.buildTaskListItem(task: task)
            }
            sections.append(CPListSection(items: items, header: "Overdue (\(overdue.count))", sectionIndexTitle: nil))
        }

        // Due Today section
        if !dueToday.isEmpty {
            let items = dueToday.prefix(8).map { task in
                self.buildTaskListItem(task: task)
            }
            sections.append(CPListSection(items: items, header: "Due Today (\(dueToday.count))", sectionIndexTitle: nil))
        }

        // This Week section
        if !thisWeek.isEmpty {
            let items = thisWeek.prefix(8).map { task in
                self.buildTaskListItem(task: task)
            }
            sections.append(CPListSection(items: items, header: "This Week (\(thisWeek.count))", sectionIndexTitle: nil))
        }

        if sections.isEmpty {
            let emptyItem = makeItem(text: "No pending tasks", detail: "You're all caught up", image: "checkmark.circle.fill")
            emptyItem.isEnabled = false
            sections.append(CPListSection(items: [emptyItem]))
        }

        tasksTemplate.updateSections(sections)
    }

    private func buildTaskListItem(task: CPTaskItem) -> CPListItem {
        let priorityIcon: String
        let spokenPriority: String
        switch task.priority.lowercased() {
        case "urgent":
            priorityIcon = "exclamationmark.3"
            spokenPriority = "urgent priority"
        case "high":
            priorityIcon = "exclamationmark.2"
            spokenPriority = "high priority"
        case "medium":
            priorityIcon = "minus"
            spokenPriority = "medium priority"
        default:
            priorityIcon = "arrow.down"
            spokenPriority = "low priority"
        }

        let dateFormatter = DateFormatter()
        dateFormatter.dateStyle = .short
        dateFormatter.timeStyle = .short

        let iso = ISO8601DateFormatter()
        let parsedDue = task.dueDate.flatMap { iso.date(from: $0) }

        var detail = parsedDue.map { dateFormatter.string(from: $0) } ?? "No due date"
        if let contact = task.leadName, !contact.isEmpty {
            detail += " - \(contact)"
        }

        let item = makeItem(text: task.title, detail: detail, image: priorityIcon)
        var accessLabel = "\(spokenPriority): \(task.title)"
        if let dueDate = parsedDue {
            accessLabel += ", due \(dateFormatter.string(from: dueDate))"
        }
        if let contact = task.leadName, !contact.isEmpty {
            accessLabel += ", for \(contact)"
        }
        item.accessibilityLabel = accessLabel
        item.accessibilityHint = "Double tap to view task details"
        item.handler = { [weak self] (_, completion: @escaping () -> Void) in
            self?.showTaskDetail(task: task)
            completion()
        }
        return item
    }

    private func showTaskDetail(task: CPTaskItem) {
        guard let interfaceController = interfaceController else { return }

        let dateFormatter = DateFormatter()
        dateFormatter.dateStyle = .medium
        dateFormatter.timeStyle = .short

        let iso = ISO8601DateFormatter()
        let parsedDue = task.dueDate.flatMap { iso.date(from: $0) }

        let titleItem = makeItem(text: "Task", detail: task.title, image: "doc.text")
        titleItem.isEnabled = false

        let dueDetail = parsedDue.map { dateFormatter.string(from: $0) } ?? "No due date"
        let dueItem = makeItem(text: "Due", detail: dueDetail, image: "clock.fill")
        dueItem.isEnabled = false

        let priorityItem = makeItem(text: "Priority", detail: task.priority.capitalized, image: "flag.fill")
        priorityItem.isEnabled = false

        var infoItems = [titleItem, dueItem, priorityItem]

        if let contactName = task.leadName, !contactName.isEmpty {
            let contactItem = makeItem(text: "Contact", detail: contactName, image: "person.fill")
            contactItem.isEnabled = false
            infoItems.append(contactItem)
        }

        // Mark Complete action
        let completeItem = makeItem(text: "Mark Complete", detail: "Tap to complete this task", image: "checkmark.circle.fill")
        completeItem.accessibilityHint = "Double tap to mark this task as done"
        completeItem.handler = { [weak self] _, completion in
            self?.completeTask(task: task)
            completion()
        }

        let detailTemplate = CPListTemplate(title: "Task Detail", sections: [
            CPListSection(items: infoItems),
            CPListSection(items: [completeItem], header: "Actions", sectionIndexTitle: nil)
        ])

        interfaceController.pushTemplate(detailTemplate, animated: true, completion: nil)
    }

    private func completeTask(task: CPTaskItem) {
        Task { [weak self] in
            guard let self = self else { return }
            do {
                try await self.api.completeTask(id: task.id)
                logger.info("Task completed: \(task.title)")
                await MainActor.run {
                    // Pop back from detail view
                    self.interfaceController?.popTemplate(animated: true, completion: nil)
                    self.showAlert(title: "Task Complete", message: "\"\(task.title)\" marked as done.")
                    // Refresh tasks tab
                    self.loadTasks()
                    self.loadDashboard()
                }
            } catch {
                logger.error("Task complete failed: \(error.localizedDescription)")
                await MainActor.run {
                    self.showAlert(title: "Error", message: "Could not complete task. Try again later.")
                }
            }
        }
    }

    // MARK: - Schedule Tab

    private func loadSchedule() {
        Task { [weak self] in
            guard let self = self else { return }
            do {
                let events = try await self.api.fetchUpcomingEvents()
                self.cache.events = events

                await MainActor.run {
                    self.updateScheduleTemplate(events: events)
                }
            } catch {
                logger.error("Schedule load failed: \(error.localizedDescription)")
                let cachedEvents = self.cache.events
                if !cachedEvents.isEmpty {
                    await MainActor.run {
                        self.updateScheduleTemplate(events: cachedEvents)
                    }
                } else {
                    await MainActor.run {
                        self.updateTabWithError(index: TabIndex.schedule, message: "Check your connection") { [weak self] in
                            self?.loadSchedule()
                        }
                    }
                }
            }
        }
    }

    private func updateScheduleTemplate(events: [CalendarEvent]) {
        guard let tabBar = tabBarTemplate,
              tabBar.templates.count > TabIndex.schedule.rawValue,
              let scheduleTemplate = tabBar.templates[TabIndex.schedule.rawValue] as? CPListTemplate else { return }

        // Filter to today's events and sort by start time
        let todayEvents = events
            .filter { Calendar.current.isDateInToday(($0.startDate ?? .distantPast)) }
            .sorted { ($0.startDate ?? .distantPast) < ($1.startDate ?? .distantPast) }

        var items: [CPListItem] = []

        let timeFormatter = DateFormatter()
        timeFormatter.dateStyle = .none
        timeFormatter.timeStyle = .short

        for event in todayEvents.prefix(12) {
            let timeString = event.startDate.map { timeFormatter.string(from: $0) } ?? event.formattedTime
            var detail = timeString
            if let location = event.location, !location.isEmpty {
                detail += " - \(location)"
            } else if let attendee = event.attendeeName, !attendee.isEmpty {
                detail += " - \(attendee)"
            }

            let item = makeItem(text: event.title, detail: detail, image: "calendar")
            item.accessibilityHint = "Double tap to view event details"
            item.handler = { [weak self] (_, completion: @escaping () -> Void) in
                self?.showEventDetail(event: event)
                completion()
            }
            items.append(item)
        }

        if items.isEmpty {
            let emptyItem = makeItem(text: "No events today", detail: "Your calendar is clear", image: "calendar.badge.checkmark")
            emptyItem.isEnabled = false
            items.append(emptyItem)
        }

        let section = CPListSection(items: items, header: "Today's Schedule", sectionIndexTitle: nil)
        scheduleTemplate.updateSections([section])
    }

    private func showEventDetail(event: CalendarEvent) {
        guard let interfaceController = interfaceController else { return }

        let timeFormatter = DateFormatter()
        timeFormatter.dateStyle = .none
        timeFormatter.timeStyle = .short

        let startStr = event.startDate.map { timeFormatter.string(from: $0) } ?? event.formattedTime
        let iso = ISO8601DateFormatter()
        let endDate = event.scheduledEnd.flatMap { iso.date(from: $0) }
        let endStr = endDate.map { timeFormatter.string(from: $0) } ?? event.scheduledEnd ?? ""
        let timeRange = "\(startStr) - \(endStr)"

        let titleItem = makeItem(text: "Event", detail: event.title, image: "calendar")
        titleItem.isEnabled = false

        let timeItem = makeItem(text: "Time", detail: timeRange, image: "clock.fill")
        timeItem.isEnabled = false

        var infoItems = [titleItem, timeItem]

        if let attendee = event.attendeeName, !attendee.isEmpty {
            let attendeeItem = makeItem(text: "Attendee", detail: attendee, image: "person.fill")
            attendeeItem.isEnabled = false
            infoItems.append(attendeeItem)
        }

        var actionItems: [CPListItem] = []

        if let location = event.location, !location.isEmpty {
            let locationItem = makeItem(text: "Location", detail: location, image: "mappin.and.ellipse")
            locationItem.isEnabled = false
            infoItems.append(locationItem)

            // Navigate action
            let navigateItem = makeItem(text: "Navigate to Location", detail: location, image: "location.fill")
            navigateItem.accessibilityHint = "Double tap to open directions in Maps"
            navigateItem.handler = { _, completion in
                // Open Apple Maps with the location
                let encodedAddress = location.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
                if let url = URL(string: "https://maps.apple.com/?q=\(encodedAddress)") {
                    DispatchQueue.main.async {
                        UIApplication.shared.open(url, options: [:], completionHandler: nil)
                    }
                }
                completion()
            }
            actionItems.append(navigateItem)
        }

        var sections = [CPListSection(items: infoItems)]
        if !actionItems.isEmpty {
            sections.append(CPListSection(items: actionItems, header: "Actions", sectionIndexTitle: nil))
        }

        let detailTemplate = CPListTemplate(title: event.title, sections: sections)
        interfaceController.pushTemplate(detailTemplate, animated: true, completion: nil)
    }

    // MARK: - Drill-down Shortcuts (from Dashboard)

    private func drillIntoTasks() {
        // Refresh tasks data (CPTabBarTemplate tab selection is user-driven)
        loadTasks()
    }

    private func drillIntoSchedule() {
        // Refresh schedule data (CPTabBarTemplate tab selection is user-driven)
        loadSchedule()
    }

    // MARK: - Error Handling for Tabs

    private func updateTabWithError(index: TabIndex, message: String, retryAction: @escaping () -> Void) {
        guard let tabBar = tabBarTemplate,
              tabBar.templates.count > index.rawValue,
              let template = tabBar.templates[index.rawValue] as? CPListTemplate else { return }

        let section = buildErrorSection(message: message, retryAction: retryAction)
        template.updateSections([section])
    }

    // MARK: - Alerts

    private func showAlert(title: String, message: String) {
        guard let interfaceController = interfaceController else { return }

        let action = CPAlertAction(title: "OK", style: .default) { _ in
            interfaceController.dismissTemplate(animated: true, completion: nil)
        }

        let alertTemplate = CPAlertTemplate(titleVariants: [title], actions: [action])
        interfaceController.presentTemplate(alertTemplate, animated: true, completion: nil)
    }

    // MARK: - Utility Helpers

    private func makeItem(text: String, detail: String?, image: String) -> CPListItem {
        let item = CPListItem(
            text: text,
            detailText: detail,
            image: UIImage(systemName: image)
        )
        // CPListItem uses text/detailText for VoiceOver by default.
        // Provide a combined accessibilityLabel for a smoother spoken experience.
        if let detail = detail, !detail.isEmpty {
            item.accessibilityLabel = "\(text): \(detail)"
        }
        return item
    }

    private func formatCurrency(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = "USD"
        formatter.maximumFractionDigits = 0
        return formatter.string(from: NSNumber(value: value)) ?? "$\(Int(value))"
    }
}

// MARK: - Voice Commands

@available(iOS 14.0, *)
extension CarPlaySceneDelegate {

    /// Handle a voice command string by dispatching to CarPlayVoiceHandler and displaying the result.
    func handleVoiceCommand(_ command: String) {
        logger.info("Voice command received: \(command)")

        Task { [weak self] in
            let response = await CarPlayVoiceHandler.shared.handleCommand(command)
            await MainActor.run {
                self?.displayVoiceResponse(command: command, response: response)
            }
        }
    }

    private func displayVoiceResponse(command: String, response: String) {
        guard let interfaceController = interfaceController else { return }

        let okAction = CPAlertAction(title: "OK", style: .default) { _ in
            interfaceController.dismissTemplate(animated: true, completion: nil)
        }

        // CPAlertTemplate supports title variants for different display widths
        let alertTemplate = CPAlertTemplate(titleVariants: [response, "Response received"], actions: [okAction])

        interfaceController.presentTemplate(alertTemplate, animated: true) { success, error in
            if let error = error {
                logger.error("Failed to present voice response: \(error.localizedDescription)")
            }
        }
    }
}

// MARK: - Legacy Connection Delegate Support (pre-iOS 14)

/// Provides backward compatibility for devices or entitlements using the older CPApplicationDelegate protocol.
/// On iOS 14+ the scene-based CarPlaySceneDelegate is preferred. This class handles the older
/// `application(_:didConnectCarInterfaceController:to:)` path by creating a CarPlaySceneDelegate
/// and forwarding the interface controller to it via a shared helper.
class CarPlayLegacyConnectionDelegate: NSObject, CPApplicationDelegate {

    /// Stored as `Any` to avoid @available requirements on the property type.
    private var legacyBridge: Any?

    func application(_ application: UIApplication,
                     didConnectCarInterfaceController interfaceController: CPInterfaceController,
                     to window: CPWindow) {
        logger.info("CarPlay legacy connection established")

        if #available(iOS 14.0, *) {
            let bridge = CarPlaySceneDelegateLegacyBridge()
            bridge.connect(interfaceController: interfaceController)
            self.legacyBridge = bridge
        }
    }

    func application(_ application: UIApplication,
                     didDisconnectCarInterfaceController interfaceController: CPInterfaceController,
                     from window: CPWindow) {
        logger.info("CarPlay legacy connection terminated")

        if #available(iOS 14.0, *) {
            (legacyBridge as? CarPlaySceneDelegateLegacyBridge)?.disconnect()
        }
        legacyBridge = nil
    }
}

/// Lightweight bridge that reuses the CarPlaySceneDelegate logic for the legacy (pre-scene) connection path.
/// It directly drives the same tab-bar setup and refresh cycle without requiring a CPTemplateApplicationScene.
@available(iOS 14.0, *)
private final class CarPlaySceneDelegateLegacyBridge {

    private let delegate = CarPlaySceneDelegate()

    func connect(interfaceController: CPInterfaceController) {
        // Directly inject the interface controller and trigger setup via the public-facing
        // helper that the scene delegate exposes for this purpose.
        delegate.legacyConnect(interfaceController: interfaceController)
    }

    func disconnect() {
        delegate.legacyDisconnect()
    }
}

// Extension on CarPlaySceneDelegate to support legacy bridge without exposing internals broadly.
@available(iOS 14.0, *)
extension CarPlaySceneDelegate {

    /// Called by the legacy bridge to set up CarPlay without a scene object.
    func legacyConnect(interfaceController: CPInterfaceController) {
        self.interfaceController = interfaceController
        setupCarPlayInterface()
        startAutoRefresh()
        registerNotificationObservers()
    }

    /// Called by the legacy bridge on disconnect.
    func legacyDisconnect() {
        stopAutoRefresh()
        removeNotificationObservers()
        self.interfaceController = nil
        self.tabBarTemplate = nil
    }
}
