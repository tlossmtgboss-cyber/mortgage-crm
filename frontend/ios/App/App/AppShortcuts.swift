/**
 * AppShortcuts.swift
 * Perennia AI — Siri Shortcuts & Spotlight Integration (iOS 16.4+)
 *
 * Surfaces the App Intents defined in AppIntents.swift as pre-built
 * Shortcuts that appear in the Shortcuts app and Siri suggestions.
 *
 * AppShortcutsProvider requires iOS 16.4+. On earlier versions the intents
 * are still usable via the Shortcuts app "Add Action" flow but won't
 * appear as pre-built suggestions.
 *
 * Phrases use \(.applicationName) so iOS substitutes the localized app
 * name ("Perennia AI") automatically, enabling Siri to recognize the
 * app name in any supported language.
 */

import AppIntents

// MARK: - Shortcuts Provider

@available(iOS 16.4, *)
struct PerenniaShortcuts: AppShortcutsProvider {

    static var appShortcuts: [AppShortcut] {
        // ---------------------------------------------------------------
        // 1. Pipeline Summary
        // ---------------------------------------------------------------
        AppShortcut(
            intent: CheckPipelineIntent(),
            phrases: [
                "Check my pipeline in \(.applicationName)",
                "Show my pipeline in \(.applicationName)",
                "Pipeline summary in \(.applicationName)",
                "How is my pipeline in \(.applicationName)",
                "What's in my pipeline in \(.applicationName)"
            ],
            shortTitle: "Pipeline Summary",
            systemImageName: "chart.bar.fill"
        )

        // ---------------------------------------------------------------
        // 2. Add a Lead
        // ---------------------------------------------------------------
        AppShortcut(
            intent: AddLeadIntent(),
            phrases: [
                "Add a lead in \(.applicationName)",
                "Create a lead in \(.applicationName)",
                "New lead in \(.applicationName)",
                "Add a new lead in \(.applicationName)"
            ],
            shortTitle: "Add Lead",
            systemImageName: "person.badge.plus"
        )

        // ---------------------------------------------------------------
        // 3. Call a Borrower
        // ---------------------------------------------------------------
        AppShortcut(
            intent: CallBorrowerIntent(),
            phrases: [
                "Call a borrower in \(.applicationName)",
                "Call borrower in \(.applicationName)",
                "Phone a borrower in \(.applicationName)",
                "Dial a borrower in \(.applicationName)"
            ],
            shortTitle: "Call Borrower",
            systemImageName: "phone.fill"
        )

        // ---------------------------------------------------------------
        // 4. Today's Tasks
        // ---------------------------------------------------------------
        AppShortcut(
            intent: CheckTasksIntent(),
            phrases: [
                "Show my tasks in \(.applicationName)",
                "What are my tasks today in \(.applicationName)",
                "Today's tasks in \(.applicationName)",
                "Check my tasks in \(.applicationName)",
                "What do I need to do in \(.applicationName)"
            ],
            shortTitle: "Today's Tasks",
            systemImageName: "checklist"
        )

        // ---------------------------------------------------------------
        // 5. Quick Note
        // ---------------------------------------------------------------
        AppShortcut(
            intent: QuickNoteIntent(),
            phrases: [
                "Add a note in \(.applicationName)",
                "Quick note in \(.applicationName)",
                "Note for a lead in \(.applicationName)",
                "Add note to a lead in \(.applicationName)"
            ],
            shortTitle: "Quick Note",
            systemImageName: "note.text.badge.plus"
        )
    }
}
