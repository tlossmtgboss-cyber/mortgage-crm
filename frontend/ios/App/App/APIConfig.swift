//
//  APIConfig.swift
//  App
//
//  Central configuration for API and web-app base URLs.
//  Every Swift file that makes network requests should reference
//  APIConfig.apiBaseURL instead of hardcoding the domain.
//
//  Override without recompiling by adding API_BASE_URL or APP_BASE_URL
//  to Info.plist (useful for staging / dev builds).
//

import Foundation

enum APIConfig {

    /// Base URL for API requests (e.g. "https://api.perenniaai.com").
    /// Checks Info.plist first so staging builds can override without recompilation.
    static let apiBaseURL: String = {
        if let url = Bundle.main.object(forInfoDictionaryKey: "API_BASE_URL") as? String, !url.isEmpty {
            return url
        }
        return "https://api.perenniaai.com"
    }()

    /// Base URL for the web app (e.g. "https://app.perenniaai.com").
    /// Checks Info.plist first so staging builds can override without recompilation.
    static let appBaseURL: String = {
        if let url = Bundle.main.object(forInfoDictionaryKey: "APP_BASE_URL") as? String, !url.isEmpty {
            return url
        }
        return "https://app.perenniaai.com"
    }()
}
