/**
 * PerenniaWidgetBundle.swift
 * Perennia AI Widget Extension — Entry Point
 *
 * Registers the widget(s) with the system.
 * Add additional widgets to the body as needed (e.g., lock screen widgets).
 */

import WidgetKit
import SwiftUI

@main
struct PerenniaWidgetBundle: WidgetBundle {
    var body: some Widget {
        PerenniaWidget()
        ClosingActivityLiveActivity()
    }
}
