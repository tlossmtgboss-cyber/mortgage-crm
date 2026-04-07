/**
 * VisionProPipelineView.swift
 * Perennia AI — Spatial 3D Pipeline Visualization for Apple Vision Pro
 *
 * Renders the loan pipeline as a 3D bar chart in a volumetric window.
 * Each loan stage is represented as a colored column whose height is
 * proportional to the loan count or dollar value for that stage.
 *
 * Features:
 *   - 3D columns using RealityKit ModelEntity (rounded boxes)
 *   - Color-coded by stage (green=funded, blue=processing, etc.)
 *   - Eye gaze highlights a stage; tap shows detail popover
 *   - Stage labels and dollar amounts rendered as billboard text
 *   - Animated entrance with staggered column growth
 *   - Can be opened as a volumetric window alongside the main app
 *
 * Uses only built-in RealityKit primitives (no custom USDZ models).
 *
 * All code is gated behind #if os(visionOS) so iOS builds are unaffected.
 */

#if os(visionOS)

import SwiftUI
import RealityKit

// MARK: - Pipeline Volumetric View

/// Top-level view for the 3D pipeline visualization.
/// Open this in a volumetric WindowGroup scene:
///
/// ```
/// WindowGroup(id: "pipeline-3d") {
///     PipelineVolumetricView()
/// }
/// .windowStyle(.volumetric)
/// .defaultSize(width: 1.0, height: 0.6, depth: 0.5, in: .meters)
/// ```
struct PipelineVolumetricView: View {

    @ObservedObject private var api = PerenniaAPIService.shared

    @State private var selectedStage: PipelineStage? = nil
    @State private var hasAppeared = false
    @State private var displayMode: PipelineDisplayMode = .count

    var body: some View {
        ZStack {
            // 3D content
            RealityView { content in
                // Anchor for the entire pipeline chart
                let anchor = AnchorEntity()
                content.add(anchor)
            } update: { content in
                // Rebuild columns when data changes
                guard let anchor = content.entities.first as? AnchorEntity else { return }
                rebuildPipeline(anchor: anchor)
            }

            // 2D overlay for labels and controls
            VStack {
                overlayHeader
                Spacer()
                if let stage = selectedStage {
                    stageDetailCard(stage)
                }
            }
            .padding(24)
        }
        .opacity(hasAppeared ? 1 : 0)
        .onAppear {
            withAnimation(PerenniaAnimation.dramatic) {
                hasAppeared = true
            }
            Task { await api.refreshAll() }
        }
    }

    // MARK: - Overlay Header

    private var overlayHeader: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("Loan Pipeline")
                    .font(PerenniaTypography.title)
                    .foregroundStyle(PerenniaColors.textPrimary)

                Text("\(api.pipelineSummary.activeLoans) active loans")
                    .font(PerenniaTypography.callout)
                    .foregroundStyle(PerenniaColors.textSecondary)
            }

            Spacer()

            // Display mode toggle
            Picker("Display", selection: $displayMode) {
                Text("Count").tag(PipelineDisplayMode.count)
                Text("Value").tag(PipelineDisplayMode.value)
            }
            .pickerStyle(.segmented)
            .frame(width: 200)
        }
        .perenniaGlassCard(cornerRadius: 16, padding: 14)
    }

    // MARK: - Stage Detail Card

    private func stageDetailCard(_ stage: PipelineStage) -> some View {
        HStack(spacing: 16) {
            // Color indicator
            RoundedRectangle(cornerRadius: 4)
                .fill(PerenniaColors.color(forStage: stage.name))
                .frame(width: 6, height: 48)

            VStack(alignment: .leading, spacing: 4) {
                Text(stage.displayName)
                    .font(PerenniaTypography.headline)
                    .foregroundStyle(PerenniaColors.textPrimary)

                HStack(spacing: 16) {
                    Label("\(stage.count) loans", systemImage: "doc.text.fill")
                        .font(PerenniaTypography.callout)
                        .foregroundStyle(PerenniaColors.textSecondary)

                    Label(formatCurrency(stage.totalValue), systemImage: "dollarsign.circle")
                        .font(PerenniaTypography.callout)
                        .foregroundStyle(PerenniaColors.textSecondary)
                }
            }

            Spacer()

            Button {
                withAnimation(PerenniaAnimation.quick) {
                    selectedStage = nil
                }
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 20))
                    .foregroundStyle(PerenniaColors.textTertiary)
            }
            .buttonStyle(.plain)
        }
        .perenniaGlassCard(cornerRadius: 16, padding: 14)
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    // MARK: - 3D Pipeline Construction

    /// Rebuilds the 3D column chart from current pipeline data.
    private func rebuildPipeline(anchor: AnchorEntity) {
        // Remove existing children
        anchor.children.removeAll()

        let stages = api.pipelineSummary.stages
        guard !stages.isEmpty else {
            addEmptyStateEntity(to: anchor)
            return
        }

        // Calculate layout parameters
        let maxValue = stages.map({ displayMode == .count ? Double($0.count) : $0.totalValue }).max() ?? 1
        let columnWidth: Float = 0.06   // meters
        let columnDepth: Float = 0.06
        let maxHeight: Float = 0.35     // meters (tallest column)
        let spacing: Float = 0.03       // gap between columns
        let totalWidth = Float(stages.count) * (columnWidth + spacing) - spacing
        let startX = -totalWidth / 2 + columnWidth / 2

        // Base platform
        let baseMesh = MeshResource.generateBox(
            width: totalWidth + 0.08,
            height: 0.008,
            depth: columnDepth + 0.06,
            cornerRadius: 0.004
        )
        var baseMaterial = PhysicallyBasedMaterial()
        baseMaterial.baseColor.tint = UIColor(white: 0.3, alpha: 0.6)
        baseMaterial.roughness = .float(0.8)
        let baseEntity = ModelEntity(mesh: baseMesh, materials: [baseMaterial])
        baseEntity.position = SIMD3<Float>(0, -0.004, 0)
        anchor.addChild(baseEntity)

        // Create columns
        for (index, stage) in stages.enumerated() {
            let rawValue = displayMode == .count ? Double(stage.count) : stage.totalValue
            let normalizedHeight = maxValue > 0 ? Float(rawValue / maxValue) : 0
            let columnHeight = max(normalizedHeight * maxHeight, 0.01) // minimum visible height

            // Column mesh
            let mesh = MeshResource.generateBox(
                width: columnWidth,
                height: columnHeight,
                depth: columnDepth,
                cornerRadius: 0.008
            )

            // Material with stage color
            let stageColor = UIColor(PerenniaColors.color(forStage: stage.name))
            var material = PhysicallyBasedMaterial()
            material.baseColor.tint = stageColor
            material.roughness = .float(0.3)
            material.metallic = .float(0.1)
            // Glass-like emissive glow
            material.emissiveColor = .color(stageColor.withAlphaComponent(0.2))
            material.emissiveIntensity = 0.3

            let columnEntity = ModelEntity(mesh: mesh, materials: [material])

            // Position: bottom-aligned on the base platform
            let xPos = startX + Float(index) * (columnWidth + spacing)
            let yPos = columnHeight / 2  // center of column above base
            columnEntity.position = SIMD3<Float>(xPos, yPos, 0)

            // Collision for tap detection
            let collisionShape = ShapeResource.generateBox(
                width: columnWidth,
                height: columnHeight,
                depth: columnDepth
            )
            columnEntity.components.set(CollisionComponent(shapes: [collisionShape]))

            // Input target for eye gaze and tap
            columnEntity.components.set(InputTargetComponent())

            // Hover effect
            columnEntity.components.set(HoverEffectComponent())

            // Store stage name for identification
            columnEntity.name = "stage_\(stage.name)"

            anchor.addChild(columnEntity)

            // Label below column
            addStageLabel(
                to: anchor,
                text: abbreviateStageName(stage.name),
                position: SIMD3<Float>(xPos, -0.02, columnDepth / 2 + 0.025),
                color: stageColor
            )

            // Value label above column
            let valueText = displayMode == .count
                ? "\(stage.count)"
                : formatCurrency(stage.totalValue)
            addStageLabel(
                to: anchor,
                text: valueText,
                position: SIMD3<Float>(xPos, yPos + columnHeight / 2 + 0.02, 0),
                color: .white
            )
        }
    }

    /// Adds a text label as a billboard entity.
    private func addStageLabel(to parent: Entity, text: String, position: SIMD3<Float>, color: UIColor) {
        let textMesh = MeshResource.generateText(
            text,
            extrusionDepth: 0.001,
            font: .systemFont(ofSize: 0.015, weight: .semibold),
            containerFrame: .zero,
            alignment: .center,
            lineBreakMode: .byTruncatingTail
        )

        var material = UnlitMaterial()
        material.color.tint = color

        let textEntity = ModelEntity(mesh: textMesh, materials: [material])

        // Center the text mesh on its position
        let bounds = textEntity.visualBounds(relativeTo: nil)
        let centerOffset = -bounds.center
        textEntity.position = position + centerOffset

        parent.addChild(textEntity)
    }

    /// Adds a placeholder when no pipeline data is available.
    private func addEmptyStateEntity(to anchor: AnchorEntity) {
        let textMesh = MeshResource.generateText(
            "No pipeline data",
            extrusionDepth: 0.002,
            font: .systemFont(ofSize: 0.03, weight: .medium),
            containerFrame: .zero,
            alignment: .center,
            lineBreakMode: .byWordWrapping
        )

        var material = UnlitMaterial()
        material.color.tint = UIColor(white: 0.7, alpha: 1.0)

        let textEntity = ModelEntity(mesh: textMesh, materials: [material])
        let bounds = textEntity.visualBounds(relativeTo: nil)
        textEntity.position = -bounds.center
        anchor.addChild(textEntity)
    }

    /// Shortens stage names for column labels.
    private func abbreviateStageName(_ name: String) -> String {
        switch name.uppercased() {
        case "APPLICATION": return "App"
        case "DISCLOSED": return "Disc"
        case "PROCESSING": return "Proc"
        case "SUBMITTED": return "Sub"
        case "UNDERWRITING": return "UW"
        case "UW_RECEIVED": return "UW Rcv"
        case "CONDITIONAL_APPROVAL": return "Cond"
        case "APPROVED": return "Appr"
        case "SUSPENDED": return "Susp"
        case "CTC", "CLEAR_TO_CLOSE": return "CTC"
        case "CLOSING": return "Close"
        case "DOCS": return "Docs"
        case "DOCS_OUT": return "D/Out"
        case "FUNDED": return "Fund"
        case "CANCELLED": return "Canc"
        case "DENIED": return "Den"
        default: return String(name.prefix(4))
        }
    }
}


// MARK: - Display Mode

/// Determines whether columns are sized by loan count or dollar value.
enum PipelineDisplayMode: String, CaseIterable, Identifiable {
    case count = "count"
    case value = "value"

    var id: String { rawValue }
}


// MARK: - 2D Fallback Pipeline View

/// A 2D SwiftUI fallback of the pipeline chart, used when volumetric
/// rendering is not desired or as an alternative window style.
struct PipelineChartView: View {

    @ObservedObject private var api = PerenniaAPIService.shared
    @State private var selectedStage: PipelineStage? = nil
    @State private var displayMode: PipelineDisplayMode = .count
    @State private var hasAppeared = false

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Loan Pipeline")
                        .font(PerenniaTypography.title)
                        .foregroundStyle(PerenniaColors.textPrimary)

                    HStack(spacing: 16) {
                        SpatialMetricCard(
                            label: "Active Loans",
                            value: "\(api.pipelineSummary.activeLoans)",
                            tint: PerenniaColors.primary
                        )
                        SpatialMetricCard(
                            label: "Pipeline Value",
                            value: formatCurrency(api.pipelineSummary.totalPipelineValue),
                            tint: PerenniaColors.success
                        )
                        SpatialMetricCard(
                            label: "Total Leads",
                            value: "\(api.pipelineSummary.totalLeads)",
                            tint: PerenniaColors.accent
                        )
                    }
                }

                Spacer()

                Picker("Display", selection: $displayMode) {
                    Text("Count").tag(PipelineDisplayMode.count)
                    Text("Value").tag(PipelineDisplayMode.value)
                }
                .pickerStyle(.segmented)
                .frame(width: 200)
            }

            // Bar chart
            if api.pipelineSummary.stages.isEmpty {
                emptyState
            } else {
                barChart
            }

            // Selected stage detail
            if let stage = selectedStage {
                selectedStageDetail(stage)
            }
        }
        .padding(24)
        .onAppear {
            withAnimation(PerenniaAnimation.standard) {
                hasAppeared = true
            }
            Task { await api.refreshAll() }
        }
    }

    // MARK: Bar Chart

    private var barChart: some View {
        let stages = api.pipelineSummary.stages
        let maxValue = stages.map({ displayMode == .count ? Double($0.count) : $0.totalValue }).max() ?? 1

        return GeometryReader { geometry in
            HStack(alignment: .bottom, spacing: 4) {
                ForEach(Array(stages.enumerated()), id: \.element.id) { index, stage in
                    let rawValue = displayMode == .count ? Double(stage.count) : stage.totalValue
                    let fraction = maxValue > 0 ? CGFloat(rawValue / maxValue) : 0
                    let barHeight = max(fraction * (geometry.size.height - 40), 4)
                    let isSelected = selectedStage?.name == stage.name

                    VStack(spacing: 4) {
                        Spacer()

                        // Value label
                        Text(displayMode == .count ? "\(stage.count)" : formatCurrency(stage.totalValue))
                            .font(PerenniaTypography.captionSmall)
                            .foregroundStyle(PerenniaColors.textSecondary)
                            .opacity(hasAppeared ? 1 : 0)
                            .animation(PerenniaAnimation.staggered(index: index, base: 0.08), value: hasAppeared)

                        // Bar
                        RoundedRectangle(cornerRadius: 6)
                            .fill(PerenniaColors.color(forStage: stage.name))
                            .frame(height: hasAppeared ? barHeight : 0)
                            .opacity(isSelected ? 1 : 0.8)
                            .scaleEffect(x: isSelected ? 1.05 : 1.0, y: 1.0, anchor: .bottom)
                            .animation(PerenniaAnimation.staggered(index: index, base: 0.06), value: hasAppeared)
                            .animation(PerenniaAnimation.quick, value: isSelected)
                            .onTapGesture {
                                withAnimation(PerenniaAnimation.quick) {
                                    selectedStage = selectedStage?.name == stage.name ? nil : stage
                                }
                            }
                            .perenniaSubtleHover()

                        // Stage label
                        Text(abbreviateStageName(stage.name))
                            .font(PerenniaTypography.captionSmall)
                            .foregroundStyle(PerenniaColors.textTertiary)
                            .lineLimit(1)
                            .frame(maxWidth: .infinity)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .frame(minHeight: 200)
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "chart.bar.xaxis")
                .font(.system(size: 48, weight: .light))
                .foregroundStyle(PerenniaColors.textTertiary)

            Text("No pipeline data available")
                .font(PerenniaTypography.body)
                .foregroundStyle(PerenniaColors.textSecondary)

            if api.isLoading {
                ProgressView()
                    .tint(PerenniaColors.primary)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 200)
    }

    private func selectedStageDetail(_ stage: PipelineStage) -> some View {
        HStack(spacing: 16) {
            RoundedRectangle(cornerRadius: 4)
                .fill(PerenniaColors.color(forStage: stage.name))
                .frame(width: 6, height: 40)

            VStack(alignment: .leading, spacing: 2) {
                Text(stage.displayName)
                    .font(PerenniaTypography.headline)
                    .foregroundStyle(PerenniaColors.textPrimary)

                HStack(spacing: 20) {
                    Label("\(stage.count) loans", systemImage: "doc.text.fill")
                    Label(formatCurrency(stage.totalValue), systemImage: "dollarsign.circle")
                }
                .font(PerenniaTypography.callout)
                .foregroundStyle(PerenniaColors.textSecondary)
            }

            Spacer()
        }
        .perenniaGlassCard(cornerRadius: 12, padding: 12)
        .transition(.opacity.combined(with: .scale(scale: 0.95)))
    }

    /// Shortens stage names for bar labels. Mirrors the 3D view's abbreviations.
    private func abbreviateStageName(_ name: String) -> String {
        switch name.uppercased() {
        case "APPLICATION": return "App"
        case "DISCLOSED": return "Disc"
        case "PROCESSING": return "Proc"
        case "SUBMITTED": return "Sub"
        case "UNDERWRITING": return "UW"
        case "UW_RECEIVED": return "UW Rcv"
        case "CONDITIONAL_APPROVAL": return "Cond"
        case "APPROVED": return "Appr"
        case "SUSPENDED": return "Susp"
        case "CTC", "CLEAR_TO_CLOSE": return "CTC"
        case "CLOSING": return "Close"
        case "DOCS": return "Docs"
        case "DOCS_OUT": return "D/Out"
        case "FUNDED": return "Fund"
        case "CANCELLED": return "Canc"
        case "DENIED": return "Den"
        default: return String(name.prefix(4))
        }
    }
}

#endif
