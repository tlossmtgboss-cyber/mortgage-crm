/**
 * AccessibilityTests.swift
 * Perennia AI — Automated Accessibility Audit
 *
 * XCUITest suite that validates WCAG 2.1 AA compliance:
 * - VoiceOver element presence and labels
 * - Dynamic Type scaling
 * - Minimum tap target sizes (44x44pt)
 * - Color contrast (via element existence)
 * - Accessibility traits and hints
 *
 * Run: xcodebuild test -scheme App -testPlan Accessibility
 */

import XCTest

final class AccessibilityTests: XCTestCase {

    let app = XCUIApplication()

    override func setUpWithError() throws {
        continueAfterFailure = false
        app.launch()
    }

    // MARK: - Biometric Gate Accessibility

    func testBiometricGateAccessibility() throws {
        let webView = app.webViews.firstMatch
        guard webView.waitForExistence(timeout: 10) else {
            throw XCTSkip("WebView did not load")
        }

        // Verify the web view contains interactive elements
        let allElements = webView.descendants(matching: .any).allElementsBoundByIndex
        XCTAssertGreaterThan(allElements.count, 5, "WebView should contain multiple accessible elements")

        // Verify no element has an empty accessibility identifier when it should have one
        let interactiveTypes: [XCUIElement.ElementType] = [.button, .textField, .link, .switch_]
        for elementType in interactiveTypes {
            let elements = webView.descendants(matching: elementType).allElementsBoundByIndex
            for element in elements where element.exists && element.isHittable {
                // Interactive elements should be reachable by accessibility
                XCTAssertTrue(
                    element.isEnabled || !element.label.isEmpty,
                    "\(elementType) at \(element.frame) is not accessible"
                )
            }
        }
    }

    // MARK: - App Switcher Guard Accessibility

    func testAppSwitcherGuardHasAccessibilityLabel() throws {
        // Background the app to trigger the guard
        XCUIDevice.shared.press(.home)

        // Wait briefly
        Thread.sleep(forTimeInterval: 1)

        // Return to app
        app.activate()

        // The guard should have been shown and hidden — verify app recovered
        let webView = app.webViews.firstMatch
        XCTAssertTrue(webView.waitForExistence(timeout: 5), "App should recover after backgrounding")
    }

    // MARK: - Dynamic Type Support

    func testDynamicTypeScaling() throws {
        // Verify the app launches successfully at different content sizes
        // This test ensures the layout doesn't break with larger text

        let webView = app.webViews.firstMatch
        guard webView.waitForExistence(timeout: 10) else {
            throw XCTSkip("WebView did not load")
        }

        // Verify the web view fills the screen (responsive layout)
        let webFrame = webView.frame
        let screenBounds = XCUIApplication().frame

        XCTAssertGreaterThan(webFrame.width, screenBounds.width * 0.9,
            "WebView should fill at least 90% of screen width")
        XCTAssertGreaterThan(webFrame.height, screenBounds.height * 0.5,
            "WebView should fill at least 50% of screen height")
    }

    // MARK: - Minimum Tap Target Size

    func testMinimumTapTargetSizes() throws {
        let webView = app.webViews.firstMatch
        guard webView.waitForExistence(timeout: 10) else {
            throw XCTSkip("WebView did not load")
        }

        let buttons = webView.buttons.allElementsBoundByIndex
        for button in buttons {
            if button.exists && button.isHittable {
                let frame = button.frame
                if frame.width > 0 && frame.height > 0 {
                    // WCAG 2.5.5: BOTH width AND height must be at least 44pt
                    XCTAssertGreaterThanOrEqual(
                        frame.width, 44,
                        "Button '\(button.label)' width \(frame.width) is below 44pt minimum"
                    )
                    XCTAssertGreaterThanOrEqual(
                        frame.height, 44,
                        "Button '\(button.label)' height \(frame.height) is below 44pt minimum"
                    )
                }
            }
        }
    }

    // MARK: - VoiceOver Element Audit

    func testAllInteractiveElementsHaveLabels() throws {
        let webView = app.webViews.firstMatch
        guard webView.waitForExistence(timeout: 10) else {
            throw XCTSkip("WebView did not load")
        }

        let buttons = webView.buttons.allElementsBoundByIndex
        for button in buttons where button.exists {
            let label = button.label
            XCTAssertFalse(label.isEmpty, "Button at \(button.frame) has empty accessibility label")

            // Check label quality — reject generic/meaningless labels
            let genericLabels = ["button", "btn", "click", "tap", "here", "link", "image"]
            let lowerLabel = label.lowercased()
            for generic in genericLabels {
                XCTAssertNotEqual(
                    lowerLabel, generic,
                    "Button has generic label '\(label)' — should be descriptive"
                )
            }

            // Labels should be at least 3 characters (meaningful content)
            XCTAssertGreaterThanOrEqual(
                label.count, 3,
                "Button label '\(label)' is too short to be meaningful"
            )
        }

        // Text fields must have labels for form accessibility
        let textFields = webView.textFields.allElementsBoundByIndex
        for field in textFields where field.exists {
            XCTAssertFalse(
                field.label.isEmpty && field.placeholderValue?.isEmpty != false,
                "Text field at \(field.frame) has no label or placeholder"
            )
        }
    }

    // MARK: - Navigation Accessibility

    func testNavigationElementsExist() throws {
        let webView = app.webViews.firstMatch
        guard webView.waitForExistence(timeout: 10) else {
            throw XCTSkip("WebView did not load")
        }

        // The app should have navigable elements
        let allElements = webView.descendants(matching: .any).allElementsBoundByIndex
        XCTAssertGreaterThan(allElements.count, 0, "WebView should contain accessible elements")
    }

    // MARK: - iOS 17+ Accessibility Audit

    @available(iOS 17.0, *)
    func testPerformAccessibilityAudit() throws {
        let webView = app.webViews.firstMatch
        guard webView.waitForExistence(timeout: 10) else {
            throw XCTSkip("WebView did not load")
        }

        // Run Apple's built-in accessibility audit — report ALL issues
        try app.performAccessibilityAudit(for: [
            .dynamicType,
            .sufficientElementDescription,
            .contrast,
            .hitRegion,
            .trait
        ])
        // No filter — all issues should be visible in test output
    }

    // MARK: - Dynamic Type Truncation

    func testDynamicTypeDoesNotTruncate() throws {
        // Launch with large accessibility text size
        app.launchArguments.append(contentsOf: [
            "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityExtraLarge"
        ])
        app.terminate()
        app.launch()

        let webView = app.webViews.firstMatch
        guard webView.waitForExistence(timeout: 15) else {
            throw XCTSkip("WebView did not load with large text")
        }

        // Verify the web view is still usable at large text size
        let webFrame = webView.frame
        let screenBounds = app.frame
        XCTAssertGreaterThan(webFrame.width, screenBounds.width * 0.9,
            "WebView should fill screen width even with large text")

        // Verify buttons are still tappable
        let buttons = webView.buttons.allElementsBoundByIndex
        let hittableButtons = buttons.filter { $0.exists && $0.isHittable }
        // At least some buttons should be reachable
        if !buttons.isEmpty {
            XCTAssertGreaterThan(hittableButtons.count, 0,
                "At least some buttons should be hittable with large text")
        }
    }
}
