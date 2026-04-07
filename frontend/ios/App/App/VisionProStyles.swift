/**
 * VisionProStyles.swift
 * Perennia AI — Shared SwiftUI Styles for Apple Vision Pro
 *
 * Provides a consistent visual language for all visionOS companion views:
 *   - Glass material modifiers
 *   - Hover effect configurations for eye tracking
 *   - Typography scaled for spatial computing (distance viewing)
 *   - Color palette optimized for passthrough display
 *   - Animation presets for spatial transitions
 *
 * All code is gated behind #if os(visionOS) so iOS builds are unaffected.
 */

#if os(visionOS)

import SwiftUI
import RealityKit

// MARK: - Color Palette

/// Colors optimized for visionOS passthrough display.
/// High-contrast tones that remain legible against real-world backgrounds.
struct PerenniaColors {
    // Brand
    static let primary = Color(red: 0.18, green: 0.55, blue: 0.94)       // Perennia blue
    static let primaryLight = Color(red: 0.40, green: 0.70, blue: 1.0)
    static let accent = Color(red: 0.30, green: 0.82, blue: 0.65)        // Teal accent

    // Pipeline stage colors
    static let stageApplication = Color(red: 0.55, green: 0.75, blue: 0.95)
    static let stageProcessing = Color(red: 0.30, green: 0.60, blue: 0.95)
    static let stageUnderwriting = Color(red: 0.95, green: 0.65, blue: 0.25)
    static let stageApproved = Color(red: 0.30, green: 0.82, blue: 0.50)
    static let stageSuspended = Color(red: 0.92, green: 0.35, blue: 0.30)
    static let stageFunded = Color(red: 0.20, green: 0.78, blue: 0.45)
    static let stageClosing = Color(red: 0.55, green: 0.40, blue: 0.90)
    static let stageDefault = Color(red: 0.60, green: 0.65, blue: 0.70)

    // Semantic
    static let textPrimary = Color.white
    static let textSecondary = Color.white.opacity(0.75)
    static let textTertiary = Color.white.opacity(0.50)
    static let cardBackground = Color.white.opacity(0.08)
    static let separator = Color.white.opacity(0.15)
    static let destructive = Color(red: 0.92, green: 0.30, blue: 0.25)
    static let warning = Color(red: 0.95, green: 0.75, blue: 0.20)
    static let success = Color(red: 0.25, green: 0.80, blue: 0.45)

    /// Returns the canonical color for a given loan pipeline stage.
    static func color(forStage stage: String) -> Color {
        switch stage.uppercased() {
        case "APPLICATION", "DISCLOSED":
            return stageApplication
        case "PROCESSING", "SUBMITTED":
            return stageProcessing
        case "UNDERWRITING", "UW_RECEIVED":
            return stageUnderwriting
        case "CONDITIONAL_APPROVAL", "APPROVED", "CTC", "CLEAR_TO_CLOSE":
            return stageApproved
        case "SUSPENDED":
            return stageSuspended
        case "CLOSING", "DOCS", "DOCS_OUT":
            return stageClosing
        case "FUNDED":
            return stageFunded
        case "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY":
            return destructive
        case "NURTURE":
            return warning
        default:
            return stageDefault
        }
    }
}


// MARK: - Typography

/// Typography system sized for comfortable reading at arm's length in spatial computing.
/// visionOS renders at roughly 2x the apparent pixel density of iPhone, but users view
/// content from further away, so font sizes are larger than iPad equivalents.
struct PerenniaTypography {
    static let largeTitle = Font.system(size: 36, weight: .bold, design: .rounded)
    static let title = Font.system(size: 28, weight: .semibold, design: .rounded)
    static let title2 = Font.system(size: 24, weight: .semibold, design: .default)
    static let title3 = Font.system(size: 20, weight: .medium, design: .default)
    static let headline = Font.system(size: 18, weight: .semibold, design: .default)
    static let body = Font.system(size: 16, weight: .regular, design: .default)
    static let callout = Font.system(size: 15, weight: .regular, design: .default)
    static let caption = Font.system(size: 13, weight: .medium, design: .default)
    static let captionSmall = Font.system(size: 11, weight: .regular, design: .default)

    /// Monospaced variant for currency / numeric values.
    static let currencyLarge = Font.system(size: 32, weight: .bold, design: .monospaced)
    static let currency = Font.system(size: 20, weight: .semibold, design: .monospaced)
    static let currencySmall = Font.system(size: 15, weight: .medium, design: .monospaced)
}


// MARK: - Glass Material Modifiers

/// Applies a standard glass background with rounded corners.
struct GlassCardModifier: ViewModifier {
    var cornerRadius: CGFloat = 20
    var padding: CGFloat = 16

    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: cornerRadius))
    }
}

/// A thinner, more transparent glass for overlays and secondary panels.
struct GlassOverlayModifier: ViewModifier {
    var cornerRadius: CGFloat = 16

    func body(content: Content) -> some View {
        content
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: cornerRadius))
    }
}

/// Ultra-thin glass for subtle depth layering.
struct GlassSubtleModifier: ViewModifier {
    var cornerRadius: CGFloat = 12

    func body(content: Content) -> some View {
        content
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: cornerRadius))
    }
}

extension View {
    /// Wraps the view in a standard Perennia glass card.
    func perenniaGlassCard(cornerRadius: CGFloat = 20, padding: CGFloat = 16) -> some View {
        modifier(GlassCardModifier(cornerRadius: cornerRadius, padding: padding))
    }

    /// Wraps the view in a thin glass overlay.
    func perenniaGlassOverlay(cornerRadius: CGFloat = 16) -> some View {
        modifier(GlassOverlayModifier(cornerRadius: cornerRadius))
    }

    /// Wraps the view in a subtle glass background.
    func perenniaGlassSubtle(cornerRadius: CGFloat = 12) -> some View {
        modifier(GlassSubtleModifier(cornerRadius: cornerRadius))
    }
}


// MARK: - Hover Effects

/// Configures standard hover (eye-tracking highlight) behavior for interactive elements.
struct PerenniaHoverEffect: ViewModifier {
    @State private var isHovered = false

    var scaleAmount: CGFloat = 1.03
    var glowColor: Color = PerenniaColors.primary

    func body(content: Content) -> some View {
        content
            .scaleEffect(isHovered ? scaleAmount : 1.0)
            .shadow(color: isHovered ? glowColor.opacity(0.4) : .clear, radius: 12)
            .onHover { hovering in
                withAnimation(.easeInOut(duration: 0.2)) {
                    isHovered = hovering
                }
            }
            .hoverEffect(.lift)
    }
}

/// A subtler hover for list rows and secondary elements.
struct PerenniaSubtleHoverEffect: ViewModifier {
    func body(content: Content) -> some View {
        content
            .hoverEffect(.highlight)
    }
}

extension View {
    /// Adds the standard Perennia hover lift effect (eye tracking highlight + scale).
    func perenniaHover(scale: CGFloat = 1.03, glow: Color = PerenniaColors.primary) -> some View {
        modifier(PerenniaHoverEffect(scaleAmount: scale, glowColor: glow))
    }

    /// Adds a subtle highlight hover for secondary elements.
    func perenniaSubtleHover() -> some View {
        modifier(PerenniaSubtleHoverEffect())
    }
}


// MARK: - Animation Presets

/// Standard animation curves for spatial transitions.
struct PerenniaAnimation {
    /// Quick interactive response (button taps, toggles).
    static let quick = Animation.spring(response: 0.3, dampingFraction: 0.8)

    /// Standard content transition (panels appearing, cards expanding).
    static let standard = Animation.spring(response: 0.45, dampingFraction: 0.75)

    /// Slower, more dramatic entrance (volumetric windows, 3D objects).
    static let dramatic = Animation.spring(response: 0.65, dampingFraction: 0.7)

    /// Gentle continuous loop (pulsing indicators, subtle breathing effects).
    static let pulse = Animation.easeInOut(duration: 1.5).repeatForever(autoreverses: true)

    /// Staggered delay for list items appearing sequentially.
    static func staggered(index: Int, base: Double = 0.05) -> Animation {
        .spring(response: 0.4, dampingFraction: 0.8).delay(Double(index) * base)
    }
}


// MARK: - Reusable Components

/// A quick-action button styled for visionOS with icon and label.
struct SpatialActionButton: View {
    let title: String
    let systemImage: String
    var tint: Color = PerenniaColors.primary
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: systemImage)
                    .font(.system(size: 24, weight: .medium))
                    .foregroundStyle(tint)
                    .frame(width: 48, height: 48)
                    .background(tint.opacity(0.15), in: Circle())

                Text(title)
                    .font(PerenniaTypography.caption)
                    .foregroundStyle(PerenniaColors.textPrimary)
            }
            .frame(minWidth: 80)
            .padding(.vertical, 8)
        }
        .buttonStyle(.plain)
        .perenniaHover(glow: tint)
    }
}

/// A metric card showing a label, value, and optional trend indicator.
struct SpatialMetricCard: View {
    let label: String
    let value: String
    var trend: String? = nil
    var trendPositive: Bool = true
    var tint: Color = PerenniaColors.primary

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(PerenniaTypography.caption)
                .foregroundStyle(PerenniaColors.textSecondary)

            Text(value)
                .font(PerenniaTypography.currency)
                .foregroundStyle(PerenniaColors.textPrimary)

            if let trend = trend {
                HStack(spacing: 4) {
                    Image(systemName: trendPositive ? "arrow.up.right" : "arrow.down.right")
                        .font(.system(size: 10, weight: .bold))
                    Text(trend)
                        .font(PerenniaTypography.captionSmall)
                }
                .foregroundStyle(trendPositive ? PerenniaColors.success : PerenniaColors.destructive)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .perenniaGlassCard(cornerRadius: 16, padding: 14)
    }
}

/// A section header with an optional trailing accessory.
struct SpatialSectionHeader<Trailing: View>: View {
    let title: String
    var systemImage: String? = nil
    @ViewBuilder var trailing: () -> Trailing

    var body: some View {
        HStack {
            if let systemImage = systemImage {
                Image(systemName: systemImage)
                    .foregroundStyle(PerenniaColors.primary)
            }
            Text(title)
                .font(PerenniaTypography.headline)
                .foregroundStyle(PerenniaColors.textPrimary)

            Spacer()

            trailing()
        }
    }
}

extension SpatialSectionHeader where Trailing == EmptyView {
    init(title: String, systemImage: String? = nil) {
        self.title = title
        self.systemImage = systemImage
        self.trailing = { EmptyView() }
    }
}


// MARK: - Currency Formatting

/// Formats a dollar amount for display in pipeline views.
func formatCurrency(_ amount: Double) -> String {
    if amount >= 1_000_000 {
        return String(format: "$%.1fM", amount / 1_000_000)
    } else if amount >= 1_000 {
        return String(format: "$%.0fK", amount / 1_000)
    } else {
        return String(format: "$%.0f", amount)
    }
}

/// Formats a whole number with comma grouping.
func formatCount(_ count: Int) -> String {
    let formatter = NumberFormatter()
    formatter.numberStyle = .decimal
    return formatter.string(from: NSNumber(value: count)) ?? "\(count)"
}

#endif
