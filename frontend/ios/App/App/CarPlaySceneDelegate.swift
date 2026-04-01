import UIKit
import CarPlay

@available(iOS 14.0, *)
class CarPlaySceneDelegate: UIResponder, CPTemplateApplicationSceneDelegate {

    var interfaceController: CPInterfaceController?

    func templateApplicationScene(_ templateApplicationScene: CPTemplateApplicationScene,
                                didConnect interfaceController: CPInterfaceController) {
        self.interfaceController = interfaceController

        // Create main CarPlay interface
        setupCarPlayInterface()
    }

    func templateApplicationScene(_ templateApplicationScene: CPTemplateApplicationScene,
                                didDisconnectInterfaceController interfaceController: CPInterfaceController) {
        self.interfaceController = nil
    }

    private func setupCarPlayInterface() {
        guard let interfaceController = interfaceController else { return }

        // Create main tabs for CRM functionality
        let tabBarTemplate = createTabBarTemplate()

        // Set the root template
        interfaceController.setRootTemplate(tabBarTemplate, animated: true) { success, error in
            if let error = error {
                print("CarPlay setup error: \(error)")
            } else {
                print("CarPlay interface setup successful")
            }
        }
    }

    private func createTabBarTemplate() -> CPTabBarTemplate {

        // Dashboard Tab
        let dashboardTab = CPListTemplate(title: "Dashboard", sections: [
            CPListSection(items: [
                createListItem(title: "Today's Priority", subtitle: "5 urgent tasks", image: "star.fill"),
                createListItem(title: "Pipeline Status", subtitle: "23 active loans", image: "chart.bar.fill"),
                createListItem(title: "Rate Alerts", subtitle: "3 new alerts", image: "bell.fill")
            ])
        ])
        dashboardTab.tabTitle = "Dashboard"
        dashboardTab.tabImage = UIImage(systemName: "house.fill")

        // Contacts Tab
        let contactsTab = CPListTemplate(title: "Contacts", sections: [
            CPListSection(items: [
                createListItem(title: "Recent Clients", subtitle: "Last contacted", image: "person.2.fill"),
                createListItem(title: "Hot Leads", subtitle: "Needs follow-up", image: "flame.fill"),
                createListItem(title: "Call List", subtitle: "Scheduled calls", image: "phone.fill")
            ])
        ])
        contactsTab.tabTitle = "Contacts"
        contactsTab.tabImage = UIImage(systemName: "person.2.fill")

        // Tasks Tab
        let tasksTab = CPListTemplate(title: "Tasks", sections: [
            CPListSection(items: [
                createListItem(title: "Due Today", subtitle: "8 tasks pending", image: "clock.fill"),
                createListItem(title: "This Week", subtitle: "15 upcoming", image: "calendar"),
                createListItem(title: "Overdue", subtitle: "2 need attention", image: "exclamationmark.triangle.fill")
            ])
        ])
        tasksTab.tabTitle = "Tasks"
        tasksTab.tabImage = UIImage(systemName: "checklist")

        // Navigation Tab
        let navigationTab = CPListTemplate(title: "Navigation", sections: [
            CPListSection(items: [
                createListItem(title: "Property Visits", subtitle: "Today's appointments", image: "house.fill"),
                createListItem(title: "Client Meetings", subtitle: "Scheduled locations", image: "mappin.and.ellipse"),
                createListItem(title: "Office Locations", subtitle: "Find nearest branch", image: "building.2.fill")
            ])
        ])
        navigationTab.tabTitle = "Navigate"
        navigationTab.tabImage = UIImage(systemName: "map.fill")

        return CPTabBarTemplate(templates: [dashboardTab, contactsTab, tasksTab, navigationTab])
    }

    private func createListItem(title: String, subtitle: String, image: String) -> CPListItem {
        let item = CPListItem(text: title, detailText: subtitle, image: UIImage(systemName: image))

        // Add handler for item selection
        item.handler = { [weak self] listItem, completion in
            if let cpItem = listItem as? CPListItem {
                self?.handleItemSelection(item: cpItem)
            }
            completion()
        }

        return item
    }

    private func handleItemSelection(item: CPListItem) {
        // Handle CarPlay item selection
        print("Selected CarPlay item: \(item.text ?? "Unknown")")

        switch item.text {
        case "Property Visits":
            showPropertyVisits()
        case "Recent Clients":
            showRecentClients()
        case "Due Today":
            showTodaysTasks()
        case "Rate Alerts":
            announceRateAlerts()
        default:
            break
        }
    }

    private func showPropertyVisits() {
        let properties = [
            createListItem(title: "123 Oak Street", subtitle: "2:00 PM - Client: John Doe", image: "house.fill"),
            createListItem(title: "456 Pine Avenue", subtitle: "4:00 PM - Client: Jane Smith", image: "house.fill"),
            createListItem(title: "789 Maple Drive", subtitle: "6:00 PM - Client: Bob Johnson", image: "house.fill")
        ]

        let propertiesTemplate = CPListTemplate(title: "Today's Property Visits", sections: [
            CPListSection(items: properties)
        ])

        interfaceController?.pushTemplate(propertiesTemplate, animated: true, completion: nil)
    }

    private func showRecentClients() {
        let clients = [
            createListItem(title: "John Doe", subtitle: "Last call: 2 hours ago", image: "person.fill"),
            createListItem(title: "Jane Smith", subtitle: "Application submitted", image: "person.fill"),
            createListItem(title: "Bob Johnson", subtitle: "Awaiting documents", image: "person.fill")
        ]

        let clientsTemplate = CPListTemplate(title: "Recent Clients", sections: [
            CPListSection(items: clients)
        ])

        interfaceController?.pushTemplate(clientsTemplate, animated: true, completion: nil)
    }

    private func showTodaysTasks() {
        let tasks = [
            createListItem(title: "Follow up with John Doe", subtitle: "Rate lock expires today", image: "clock.fill"),
            createListItem(title: "Review Jane's application", subtitle: "Underwriter feedback", image: "doc.text.fill"),
            createListItem(title: "Schedule Bob's closing", subtitle: "Coordinate with title company", image: "calendar")
        ]

        let tasksTemplate = CPListTemplate(title: "Today's Tasks", sections: [
            CPListSection(items: tasks)
        ])

        interfaceController?.pushTemplate(tasksTemplate, animated: true, completion: nil)
    }

    private func announceRateAlerts() {
        let announcement = "You have 3 new rate alerts. 30-year fixed is now at 6.75%, down 0.25 points. VA loans at 6.5%, and FHA at 6.25%."
        print("CarPlay Announcement: \(announcement)")
    }
}

// MARK: - CarPlay Audio & Communication Extensions
@available(iOS 14.0, *)
extension CarPlaySceneDelegate {

    // Handle voice commands for hands-free operation
    func handleVoiceCommand(_ command: String) {
        switch command.lowercased() {
        case "show pipeline":
            showPipelineStatus()
        case "call recent client":
            initiateCallToRecentClient()
        case "navigation to property":
            startNavigationToNextProperty()
        default:
            print("Unrecognized voice command: \(command)")
        }
    }

    private func showPipelineStatus() {
        let announcement = "Your pipeline shows 23 active loans. 5 in application, 8 in processing, 6 in underwriting, and 4 clear to close."
        print("Pipeline Status: \(announcement)")
    }

    private func initiateCallToRecentClient() {
        print("Initiating call to most recent client...")
    }

    private func startNavigationToNextProperty() {
        print("Starting navigation to next property visit...")
    }
}
