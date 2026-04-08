/**
 * PerformanceMonitor.swift
 * Perennia AI — App Performance Monitoring
 *
 * Tracks launch time, memory usage, frame drops, and battery state.
 * Reports metrics to AuditLogger and optionally to the backend.
 */

import Foundation
import UIKit
import os.log
import MetricKit
import os.signpost

@available(iOS 14.0, *)
final class PerformanceMonitor {

    static let shared = PerformanceMonitor()

    private let logger = Logger(subsystem: "com.perenniaai.crm", category: "Performance")
    private let monitorQueue = DispatchQueue(label: "com.perenniaai.crm.performanceMonitor", qos: .utility)

    // MARK: - Launch Time Tracking

    /// Set at process start (static initializer runs before main)
    static let processStartTime = CFAbsoluteTimeGetCurrent()

    private(set) var appLaunchDuration: TimeInterval = 0
    private(set) var firstFrameDuration: TimeInterval = 0

    /// Call from applicationDidFinishLaunching
    func recordAppLaunch() {
        appLaunchDuration = CFAbsoluteTimeGetCurrent() - Self.processStartTime
        endSignpost("AppLaunch") // Pair with beginSignpost at process start
        logger.info("App launch (didFinishLaunching): \(String(format: "%.3f", self.appLaunchDuration))s")

        // Measure time to first frame
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.firstFrameDuration = CFAbsoluteTimeGetCurrent() - Self.processStartTime
            self.logger.info("First frame rendered: \(String(format: "%.3f", self.firstFrameDuration))s")

            // Log launch metrics
            self.logMetrics(event: "app_launch", data: [
                "launch_duration_ms": Int(self.appLaunchDuration * 1000),
                "first_frame_ms": Int(self.firstFrameDuration * 1000)
            ])
        }
    }

    // MARK: - Memory Monitoring

    /// Current resident memory in bytes
    var residentMemory: UInt64 {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size) / 4
        let result = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
            }
        }
        return result == KERN_SUCCESS ? info.resident_size : 0
    }

    /// Formatted memory string (e.g., "142.3 MB")
    var residentMemoryFormatted: String {
        let mb = Double(residentMemory) / 1_048_576.0
        return String(format: "%.1f MB", mb)
    }

    // MARK: - Memory Pressure

    private var memoryWarningCount = 0

    /// Call from applicationDidReceiveMemoryWarning
    func recordMemoryWarning() {
        memoryWarningCount += 1
        let mem = residentMemoryFormatted
        logger.warning("Memory warning #\(self.memoryWarningCount) — current usage: \(mem)")

        logMetrics(event: "memory_warning", data: [
            "warning_count": memoryWarningCount,
            "resident_mb": Int(Double(residentMemory) / 1_048_576.0)
        ])
    }

    // MARK: - Periodic Health Check

    private var healthCheckTimer: Timer?

    /// Start periodic health monitoring (every 5 minutes)
    func startPeriodicMonitoring(interval: TimeInterval = 300) {
        DispatchQueue.main.async { [weak self] in
            self?.healthCheckTimer?.invalidate()
            self?.healthCheckTimer = Timer.scheduledTimer(
                withTimeInterval: interval,
                repeats: true
            ) { [weak self] _ in
                self?.captureHealthSnapshot()
            }
        }
    }

    func stopPeriodicMonitoring() {
        DispatchQueue.main.async { [weak self] in
            self?.healthCheckTimer?.invalidate()
            self?.healthCheckTimer = nil
        }
    }

    private func captureHealthSnapshot() {
        monitorQueue.async { [weak self] in
            guard let self = self else { return }

            let memMB = Int(Double(self.residentMemory) / 1_048_576.0)
            let batteryLevel = Int(UIDevice.current.batteryLevel * 100)
            let batteryState: String = {
                switch UIDevice.current.batteryState {
                case .charging: return "charging"
                case .full: return "full"
                case .unplugged: return "unplugged"
                default: return "unknown"
                }
            }()
            let thermalState: String = {
                switch ProcessInfo.processInfo.thermalState {
                case .nominal: return "nominal"
                case .fair: return "fair"
                case .serious: return "serious"
                case .critical: return "critical"
                @unknown default: return "unknown"
                }
            }()

            self.logger.debug("Health: mem=\(memMB)MB battery=\(batteryLevel)% thermal=\(thermalState)")

            // Alert on concerning states
            if memMB > 300 {
                self.logger.warning("High memory usage: \(memMB)MB")
            }
            if thermalState == "serious" || thermalState == "critical" {
                self.logger.warning("Thermal pressure: \(thermalState)")
                self.logMetrics(event: "thermal_pressure", data: [
                    "state": thermalState,
                    "resident_mb": memMB
                ])
            }
        }
    }

    // MARK: - Network Request Timing

    private var requestTimings: [(endpoint: String, durationMs: Int, timestamp: Date)] = []
    private let maxTimings = 100

    /// Record an API request duration for performance tracking
    func recordRequestTiming(endpoint: String, durationMs: Int) {
        emitSignpost("APIRequest")
        monitorQueue.async { [weak self] in
            guard let self = self else { return }
            self.requestTimings.append((endpoint: endpoint, durationMs: durationMs, timestamp: Date()))
            if self.requestTimings.count > self.maxTimings {
                self.requestTimings.removeFirst(self.requestTimings.count - self.maxTimings)
            }

            // Warn on slow requests (> 5 seconds)
            if durationMs > 5000 {
                self.logger.warning("Slow API request: \(endpoint) took \(durationMs)ms")
            }
        }
    }

    /// Average request latency over recent requests
    var averageRequestLatencyMs: Int {
        guard !requestTimings.isEmpty else { return 0 }
        let total = requestTimings.reduce(0) { $0 + $1.durationMs }
        return total / requestTimings.count
    }

    /// P95 request latency
    var p95RequestLatencyMs: Int {
        guard !requestTimings.isEmpty else { return 0 }
        let sorted = requestTimings.map(\.durationMs).sorted()
        let index = Int(Double(sorted.count) * 0.95)
        return sorted[min(index, sorted.count - 1)]
    }

    // MARK: - Metrics Reporting

    private func logMetrics(event: String, data: [String: Any]) {
        // Log to AuditLogger using featureAccess event type for performance telemetry
        AuditLogger.shared.log(
            event: .featureAccess,
            details: ["performance_event": event] + data.mapValues { "\($0)" }
        )
    }

    // MARK: - Summary

    /// Generate a performance summary dictionary (for diagnostics or reporting)
    func summary() -> [String: Any] {
        return [
            "launch_duration_ms": Int(appLaunchDuration * 1000),
            "first_frame_ms": Int(firstFrameDuration * 1000),
            "resident_memory_mb": Int(Double(residentMemory) / 1_048_576.0),
            "memory_warnings": memoryWarningCount,
            "avg_request_latency_ms": averageRequestLatencyMs,
            "p95_request_latency_ms": p95RequestLatencyMs,
            "thermal_state": {
                switch ProcessInfo.processInfo.thermalState {
                case .nominal: return "nominal"
                case .fair: return "fair"
                case .serious: return "serious"
                case .critical: return "critical"
                @unknown default: return "unknown"
                }
            }()
        ]
    }

    // MARK: - MetricKit Payload Storage

    private let payloadStorageKey = "com.perenniaai.metrickit.payloads"
    private let payloadIndexKey = "com.perenniaai.metrickit.payloadIndex"

    private func storeMetricPayload(_ jsonData: Data, type: String) {
        monitorQueue.async { [weak self] in
            guard let self = self else { return }
            let key = "\(self.payloadStorageKey).\(type).\(Int(Date().timeIntervalSince1970))"

            if #available(iOS 14.0, *) {
                EncryptedCacheService.shared.store(key: key, value: jsonData)
            }

            // Track in index
            var index = UserDefaults.standard.stringArray(forKey: self.payloadIndexKey) ?? []
            index.append(key)
            UserDefaults.standard.set(index, forKey: self.payloadIndexKey)
        }
    }

    /// Retrieve stored MetricKit payloads for backend sync
    func getPendingMetricPayloads() -> [(type: String, data: Data)] {
        var results: [(type: String, data: Data)] = []
        let index = UserDefaults.standard.stringArray(forKey: payloadIndexKey) ?? []

        for key in index {
            if #available(iOS 14.0, *) {
                if let data: Data = EncryptedCacheService.shared.retrieve(key: key, type: Data.self) {
                    let type = key.contains(".diagnostic.") ? "diagnostic" : "performance"
                    results.append((type: type, data: data))
                }
            }
        }
        return results
    }

    /// Clear all synced payloads from encrypted cache and index
    func clearSyncedPayloads() {
        let index = UserDefaults.standard.stringArray(forKey: payloadIndexKey) ?? []
        for key in index {
            if #available(iOS 14.0, *) {
                EncryptedCacheService.shared.delete(key: key)
            }
        }
        UserDefaults.standard.removeObject(forKey: payloadIndexKey)
    }

    // MARK: - Signpost Instrumentation (Instruments.app integration)

    private static let signpostLog = OSLog(subsystem: "com.perenniaai.crm", category: .pointsOfInterest)

    /// Begin a signpost interval for a named operation (shows in Instruments)
    func beginSignpost(_ name: StaticString, id: OSSignpostID = .exclusive) {
        os_signpost(.begin, log: Self.signpostLog, name: name, signpostID: id)
    }

    /// End a signpost interval
    func endSignpost(_ name: StaticString, id: OSSignpostID = .exclusive) {
        os_signpost(.end, log: Self.signpostLog, name: name, signpostID: id)
    }

    /// Emit a single signpost event
    func emitSignpost(_ name: StaticString) {
        os_signpost(.event, log: Self.signpostLog, name: name)
    }

    private init() {
        // Enable battery monitoring
        UIDevice.current.isBatteryMonitoringEnabled = true

        // Register for MetricKit payloads (crash reports + performance)
        if #available(iOS 14.0, *) {
            MXMetricManager.shared.add(self)
        }
    }

    deinit {
        if #available(iOS 14.0, *) {
            MXMetricManager.shared.remove(self)
        }
    }
}

// MARK: - MXMetricManagerSubscriber

@available(iOS 14.0, *)
extension PerformanceMonitor: MXMetricManagerSubscriber {

    /// Receives daily performance metric payloads from Apple
    func didReceive(_ payloads: [MXMetricPayload]) {
        for payload in payloads {
            let metrics: [String: Any] = [
                "type": "metric_payload",
                "timeStamp": ISO8601DateFormatter().string(from: payload.timeStampEnd),
                "includes_cpu": payload.cpuMetrics != nil,
                "includes_memory": payload.memoryMetrics != nil,
                "includes_display": payload.displayMetrics != nil,
                "includes_network": payload.networkTransferMetrics != nil,
                "includes_launch": payload.applicationLaunchMetrics != nil
            ]
            logger.info("MetricKit payload received: \(metrics.description)")

            // Store payload JSON for backend sync
            if let jsonData = payload.jsonRepresentation() {
                storeMetricPayload(jsonData, type: "performance")
            }
        }
    }

    /// Receives crash diagnostics, hang reports, and disk write exceptions (iOS 14+)
    func didReceive(_ payloads: [MXDiagnosticPayload]) {
        for payload in payloads {
            logger.warning("MetricKit diagnostic received — crashes: \(payload.crashDiagnostics?.count ?? 0), hangs: \(payload.hangDiagnostics?.count ?? 0)")

            // Log crash count to audit trail
            let crashCount = payload.crashDiagnostics?.count ?? 0
            let hangCount = payload.hangDiagnostics?.count ?? 0

            if crashCount > 0 || hangCount > 0 {
                AuditLogger.shared.log(
                    event: .featureAccess,
                    details: [
                        "performance_event": "diagnostic_payload",
                        "crash_count": "\(crashCount)",
                        "hang_count": "\(hangCount)",
                        "disk_write_exceptions": "\(payload.diskWriteExceptionDiagnostics?.count ?? 0)"
                    ]
                )
            }

            // Store diagnostic JSON for backend sync
            if let jsonData = payload.jsonRepresentation() {
                storeMetricPayload(jsonData, type: "diagnostic")
            }
        }
    }
}
