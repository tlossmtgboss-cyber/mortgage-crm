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
final class PerformanceMonitor: NSObject {

    static let shared = PerformanceMonitor()

    private let logger = Logger(subsystem: "com.perenniaai.crm", category: "Performance")
    private let monitorQueue = DispatchQueue(label: "com.perenniaai.crm.performanceMonitor", qos: .utility)

    // MARK: - Launch Time Tracking

    /// Set at process start (static initializer runs before main)
    static let processStartTime = CFAbsoluteTimeGetCurrent()

    /// Thread-safe storage for launch metrics (written once, read from summary)
    private var _appLaunchDuration: TimeInterval = 0
    private var _firstFrameDuration: TimeInterval = 0

    private(set) var appLaunchDuration: TimeInterval {
        get { monitorQueue.sync { _appLaunchDuration } }
        set { monitorQueue.sync { _appLaunchDuration = newValue } }
    }

    private(set) var firstFrameDuration: TimeInterval {
        get { monitorQueue.sync { _firstFrameDuration } }
        set { monitorQueue.sync { _firstFrameDuration = newValue } }
    }

    /// Call from applicationDidFinishLaunching
    func recordAppLaunch() {
        let launchDuration = CFAbsoluteTimeGetCurrent() - Self.processStartTime
        appLaunchDuration = launchDuration
        beginSignpost("AppLaunch")
        endSignpost("AppLaunch")
        logger.info("App launch (didFinishLaunching): \(String(format: "%.3f", launchDuration))s")

        // Measure time to first frame on the next run loop iteration
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            let frameDuration = CFAbsoluteTimeGetCurrent() - Self.processStartTime
            self.firstFrameDuration = frameDuration
            self.logger.info("First frame rendered: \(String(format: "%.3f", frameDuration))s")

            // Log launch metrics
            self.logMetrics(event: "app_launch", data: [
                "launch_duration_ms": Int(launchDuration * 1000),
                "first_frame_ms": Int(frameDuration * 1000)
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

    private var _memoryWarningCount = 0
    private var memoryWarningCount: Int {
        get { monitorQueue.sync { _memoryWarningCount } }
    }

    /// Call from applicationDidReceiveMemoryWarning
    func recordMemoryWarning() {
        let count: Int = monitorQueue.sync {
            _memoryWarningCount += 1
            return _memoryWarningCount
        }
        let mem = residentMemoryFormatted
        logger.warning("Memory warning #\(count) — current usage: \(mem)")

        logMetrics(event: "memory_warning", data: [
            "warning_count": count,
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
        // UIDevice properties must be read on the main thread
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }

            let batteryLevel = Int(UIDevice.current.batteryLevel * 100)
            let batteryState: String = {
                switch UIDevice.current.batteryState {
                case .charging: return "charging"
                case .full: return "full"
                case .unplugged: return "unplugged"
                default: return "unknown"
                }
            }()

            // Move heavy work off the main thread
            self.monitorQueue.async { [weak self] in
                guard let self = self else { return }

                let memMB = Int(Double(self.residentMemory) / 1_048_576.0)
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

    /// Average request latency over recent requests (thread-safe)
    var averageRequestLatencyMs: Int {
        return monitorQueue.sync {
            guard !requestTimings.isEmpty else { return 0 }
            let total = requestTimings.reduce(0) { $0 + $1.durationMs }
            return total / requestTimings.count
        }
    }

    /// P95 request latency (thread-safe)
    var p95RequestLatencyMs: Int {
        return monitorQueue.sync {
            guard requestTimings.count > 0 else { return 0 }
            let sorted = requestTimings.map(\.durationMs).sorted()
            let p95Index = min(Int(Double(sorted.count - 1) * 0.95), sorted.count - 1)
            return sorted[p95Index]
        }
    }

    // MARK: - Metrics Reporting

    private func logMetrics(event: String, data: [String: Any]) {
        // Log to AuditLogger using featureAccess event type for performance telemetry
        AuditLogger.shared.log(
            event: .featureAccess,
            details: ["performance_event": event].merging(data.mapValues { "\($0)" }) { _, new in new }
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
    private let maxPayloadEntries = 50

    private func storeMetricPayload(_ jsonData: Data, type: String) {
        monitorQueue.async { [weak self] in
            guard let self = self else { return }
            let key = "\(self.payloadStorageKey).\(type).\(Int(Date().timeIntervalSince1970))"

            EncryptedCacheService.shared.store(key: key, value: jsonData)

            // Track in index, evicting oldest entries if over capacity
            var index = UserDefaults.standard.stringArray(forKey: self.payloadIndexKey) ?? []
            index.append(key)

            if index.count > self.maxPayloadEntries {
                let overflow = index.count - self.maxPayloadEntries
                let evicted = Array(index.prefix(overflow))
                index = Array(index.dropFirst(overflow))
                // Clean up evicted entries from cache
                for evictedKey in evicted {
                    EncryptedCacheService.shared.delete(key: evictedKey)
                }
            }

            UserDefaults.standard.set(index, forKey: self.payloadIndexKey)
        }
    }

    /// Retrieve stored MetricKit payloads for backend sync
    func getPendingMetricPayloads() -> [(type: String, data: Data)] {
        var results: [(type: String, data: Data)] = []
        let index = UserDefaults.standard.stringArray(forKey: payloadIndexKey) ?? []

        for key in index {
            if let data: Data = EncryptedCacheService.shared.retrieve(key: key, type: Data.self) {
                let type = key.contains(".diagnostic.") ? "diagnostic" : "performance"
                results.append((type: type, data: data))
            }
        }
        return results
    }

    /// Clear all synced payloads from encrypted cache and index
    func clearSyncedPayloads() {
        let index = UserDefaults.standard.stringArray(forKey: payloadIndexKey) ?? []
        for key in index {
            EncryptedCacheService.shared.delete(key: key)
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

    private override init() {
        super.init()

        // Enable battery monitoring (UIDevice must be accessed on main thread)
        if Thread.isMainThread {
            UIDevice.current.isBatteryMonitoringEnabled = true
        } else {
            DispatchQueue.main.async {
                UIDevice.current.isBatteryMonitoringEnabled = true
            }
        }

        // Register for MetricKit payloads (crash reports + performance)
        MXMetricManager.shared.add(self)
    }

    deinit {
        healthCheckTimer?.invalidate()
        MXMetricManager.shared.remove(self)
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
            let jsonData = payload.jsonRepresentation()
            storeMetricPayload(jsonData, type: "performance")
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
            let jsonData = payload.jsonRepresentation()
            storeMetricPayload(jsonData, type: "diagnostic")
        }
    }
}
