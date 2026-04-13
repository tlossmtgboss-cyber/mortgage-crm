/**
 * SpotlightSearchPlugin.swift
 * Perennia AI — Capacitor Bridge for SpotlightIndexer
 *
 * Exposes Spotlight search indexing (SpotlightIndexer.swift) to the
 * JavaScript layer via Capacitor plugin methods. Allows the React app
 * to trigger re-indexing, index individual items, remove items, and
 * check the current index status.
 *
 * Methods available from JavaScript:
 *   - SpotlightSearch.indexAllData({ force?: boolean })  — full re-index
 *   - SpotlightSearch.indexItem({ type, id, data })      — index one item
 *   - SpotlightSearch.removeItem({ type, id })           — remove one item
 *   - SpotlightSearch.removeAllItems()                   — clear all indexed data
 *   - SpotlightSearch.getIndexStatus()                   — check last index time
 */

import Foundation
import Capacitor

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
