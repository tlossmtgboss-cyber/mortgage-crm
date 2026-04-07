import Foundation
import Security

// MARK: - Share Extension Network Service
// Lightweight networking for the Perennia AI share extension.
// Uses URLSession directly (no Capacitor dependency) to stay under the 120MB memory limit.

final class ShareNetworkService {

    // MARK: - Constants

    private static let baseURL = "https://api.perenniaai.com"
    private static let appGroupID = "group.com.perenniaai.crm"
    private static let authTokenKey = "CapacitorStorage.auth_token"
    private static let leadsEndpoint = "/api/v1/leads/"
    private static let loansEndpoint = "/api/v1/loans/"
    private static let uploadEndpoint = "/api/v1/smart-docs/upload"
    private static let timeoutInterval: TimeInterval = 30

    // MARK: - Shared Instance

    static let shared = ShareNetworkService()
    private init() {}

    // MARK: - Auth Token

    /// Reads the JWT auth token from the shared iOS Keychain (preferred)
    /// with a fallback to App Group UserDefaults for migration compatibility.
    func getAuthToken() -> String? {
        // Primary: read from shared Keychain (secure, encrypted at rest)
        if let keychainToken = ShareNetworkService.getAuthTokenFromKeychain(),
           !keychainToken.isEmpty {
            return keychainToken
        }

        // Fallback: read from App Group UserDefaults (plaintext, for migration)
        guard let defaults = UserDefaults(suiteName: ShareNetworkService.appGroupID) else {
            return nil
        }
        return defaults.string(forKey: ShareNetworkService.authTokenKey)
    }

    /// Reads the auth token from the shared iOS Keychain using the same
    /// service/account identifiers as KeychainService.swift in the main app.
    private static func getAuthTokenFromKeychain() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "com.perenniaai.crm.auth",
            kSecAttrAccount as String: "access_token",
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    /// Whether the user is currently authenticated.
    var isAuthenticated: Bool {
        guard let token = getAuthToken(), !token.isEmpty else { return false }
        // Basic JWT expiry check: decode the payload and check exp claim
        return !isTokenExpired(token)
    }

    // MARK: - Fetch Leads

    struct LeadSummary: Decodable, Identifiable {
        let id: Int
        let first_name: String?
        let last_name: String?
        let email: String?
        let stage: String?

        var displayName: String {
            let first = first_name ?? ""
            let last = last_name ?? ""
            let name = "\(first) \(last)".trimmingCharacters(in: .whitespaces)
            return name.isEmpty ? (email ?? "Lead #\(id)") : name
        }
    }

    struct LeadsResponse: Decodable {
        let leads: [LeadSummary]?
        // Some endpoints return array directly
    }

    func fetchRecentLeads(completion: @escaping (Result<[LeadSummary], ShareError>) -> Void) {
        guard let token = getAuthToken() else {
            completion(.failure(.notAuthenticated))
            return
        }

        // Fetch recent leads, limited to 50 for memory efficiency
        guard let url = URL(string: "\(ShareNetworkService.baseURL)\(ShareNetworkService.leadsEndpoint)?limit=50&sort=updated_at&order=desc") else {
            completion(.failure(.invalidURL))
            return
        }

        var request = URLRequest(url: url, timeoutInterval: ShareNetworkService.timeoutInterval)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let task = URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(.network(error.localizedDescription)))
                return
            }

            guard let httpResponse = response as? HTTPURLResponse else {
                completion(.failure(.network("Invalid response")))
                return
            }

            if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
                completion(.failure(.notAuthenticated))
                return
            }

            guard (200...299).contains(httpResponse.statusCode), let data = data else {
                completion(.failure(.serverError(httpResponse.statusCode)))
                return
            }

            do {
                // The leads endpoint may return { leads: [...] } or just [...]
                if let response = try? JSONDecoder().decode(LeadsResponse.self, from: data),
                   let leads = response.leads {
                    completion(.success(leads))
                } else {
                    let leads = try JSONDecoder().decode([LeadSummary].self, from: data)
                    completion(.success(leads))
                }
            } catch {
                completion(.failure(.decodingError(error.localizedDescription)))
            }
        }
        task.resume()
    }

    // MARK: - Fetch Loans

    struct LoanSummary: Decodable, Identifiable {
        let id: Int
        let loan_number: String?
        let loan_amount: Double?
        let stage: String?
        let lead_id: Int?
        let borrower_id: Int?
        let property_address: String?

        var displayName: String {
            if let number = loan_number, !number.isEmpty {
                return "Loan #\(number)"
            }
            if let address = property_address, !address.isEmpty {
                return address
            }
            return "Loan #\(id)"
        }
    }

    func fetchRecentLoans(completion: @escaping (Result<[LoanSummary], ShareError>) -> Void) {
        guard let token = getAuthToken() else {
            completion(.failure(.notAuthenticated))
            return
        }

        guard let url = URL(string: "\(ShareNetworkService.baseURL)\(ShareNetworkService.loansEndpoint)?limit=50&sort=updated_at&order=desc") else {
            completion(.failure(.invalidURL))
            return
        }

        var request = URLRequest(url: url, timeoutInterval: ShareNetworkService.timeoutInterval)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let task = URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(.network(error.localizedDescription)))
                return
            }

            guard let httpResponse = response as? HTTPURLResponse else {
                completion(.failure(.network("Invalid response")))
                return
            }

            if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
                completion(.failure(.notAuthenticated))
                return
            }

            guard (200...299).contains(httpResponse.statusCode), let data = data else {
                completion(.failure(.serverError(httpResponse.statusCode)))
                return
            }

            do {
                let loans = try JSONDecoder().decode([LoanSummary].self, from: data)
                completion(.success(loans))
            } catch {
                completion(.failure(.decodingError(error.localizedDescription)))
            }
        }
        task.resume()
    }

    // MARK: - Upload Document

    struct UploadResult: Decodable {
        let id: Int?
        let status: String?
        let message: String?
    }

    /// Uploads a document to the Smart Docs API endpoint via multipart form data.
    ///
    /// - Parameters:
    ///   - fileData: Raw file bytes
    ///   - fileName: Original filename (e.g., "paystub.pdf")
    ///   - mimeType: MIME type string (e.g., "application/pdf")
    ///   - loanID: Target loan ID (required by API)
    ///   - borrowerID: Target borrower ID (required by API)
    ///   - docType: Document type category (optional)
    ///   - progressHandler: Called on the main thread with upload progress (0.0 - 1.0)
    ///   - completion: Called on the main thread with the result
    func uploadDocument(
        fileData: Data,
        fileName: String,
        mimeType: String,
        loanID: Int,
        borrowerID: Int,
        docType: String?,
        progressHandler: ((Double) -> Void)? = nil,
        completion: @escaping (Result<UploadResult, ShareError>) -> Void
    ) {
        guard let token = getAuthToken() else {
            completion(.failure(.notAuthenticated))
            return
        }

        guard let url = URL(string: "\(ShareNetworkService.baseURL)\(ShareNetworkService.uploadEndpoint)") else {
            completion(.failure(.invalidURL))
            return
        }

        let boundary = "PerenniaShare-\(UUID().uuidString)"

        var request = URLRequest(url: url, timeoutInterval: ShareNetworkService.timeoutInterval)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        // Build multipart body
        var body = Data()

        // loan_id field
        body.appendMultipartField(name: "loan_id", value: "\(loanID)", boundary: boundary)

        // borrower_id field
        body.appendMultipartField(name: "borrower_id", value: "\(borrowerID)", boundary: boundary)

        // doc_type field (optional)
        if let docType = docType {
            body.appendMultipartField(name: "doc_type", value: docType, boundary: boundary)
        }

        // File field
        body.appendMultipartFile(
            name: "file",
            fileName: fileName,
            mimeType: mimeType,
            fileData: fileData,
            boundary: boundary
        )

        // Closing boundary
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        request.httpBody = body

        // Use a delegate-based session for progress tracking
        let delegate = UploadProgressDelegate(progressHandler: progressHandler)
        let session = URLSession(configuration: .default, delegate: delegate, delegateQueue: nil)

        let task = session.uploadTask(with: request, from: body) { data, response, error in
            DispatchQueue.main.async {
                if let error = error {
                    completion(.failure(.network(error.localizedDescription)))
                    return
                }

                guard let httpResponse = response as? HTTPURLResponse else {
                    completion(.failure(.network("Invalid response")))
                    return
                }

                if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
                    completion(.failure(.notAuthenticated))
                    return
                }

                if httpResponse.statusCode == 413 {
                    completion(.failure(.fileTooLarge))
                    return
                }

                guard (200...299).contains(httpResponse.statusCode) else {
                    completion(.failure(.serverError(httpResponse.statusCode)))
                    return
                }

                guard let data = data else {
                    // Success with no body is still success
                    completion(.success(UploadResult(id: nil, status: "success", message: nil)))
                    return
                }

                do {
                    let result = try JSONDecoder().decode(UploadResult.self, from: data)
                    completion(.success(result))
                } catch {
                    // Even if we can't decode, the upload succeeded (2xx status)
                    completion(.success(UploadResult(id: nil, status: "success", message: nil)))
                }
            }
        }
        task.resume()
    }

    // MARK: - Offline Queue (App Group File Storage)

    struct PendingUpload: Codable {
        let id: String
        let fileName: String
        let mimeType: String
        let loanID: Int
        let borrowerID: Int
        let docType: String?
        let queuedAt: Date
        let relativePath: String // Path relative to App Group container
    }

    private var pendingUploadsKey: String { "PendingShareUploads" }

    /// Saves a file to the App Group container for later upload by the main app.
    func queueForLaterUpload(
        fileData: Data,
        fileName: String,
        mimeType: String,
        loanID: Int,
        borrowerID: Int,
        docType: String?
    ) -> Bool {
        guard let containerURL = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: ShareNetworkService.appGroupID
        ) else {
            return false
        }

        let pendingDir = containerURL.appendingPathComponent("PendingUploads", isDirectory: true)
        try? FileManager.default.createDirectory(at: pendingDir, withIntermediateDirectories: true)

        let fileID = UUID().uuidString
        let sanitizedName = fileName.replacingOccurrences(of: "/", with: "_")
        let fileURL = pendingDir.appendingPathComponent("\(fileID)_\(sanitizedName)")

        do {
            try fileData.write(to: fileURL)
        } catch {
            return false
        }

        // Record the pending upload metadata
        let pending = PendingUpload(
            id: fileID,
            fileName: fileName,
            mimeType: mimeType,
            loanID: loanID,
            borrowerID: borrowerID,
            docType: docType,
            queuedAt: Date(),
            relativePath: "PendingUploads/\(fileID)_\(sanitizedName)"
        )

        var existing = loadPendingUploads()
        existing.append(pending)
        savePendingUploads(existing)

        return true
    }

    func loadPendingUploads() -> [PendingUpload] {
        guard let defaults = UserDefaults(suiteName: ShareNetworkService.appGroupID) else {
            return []
        }
        guard let data = defaults.data(forKey: pendingUploadsKey) else {
            return []
        }
        return (try? JSONDecoder().decode([PendingUpload].self, from: data)) ?? []
    }

    func savePendingUploads(_ uploads: [PendingUpload]) {
        guard let defaults = UserDefaults(suiteName: ShareNetworkService.appGroupID) else {
            return
        }
        if let data = try? JSONEncoder().encode(uploads) {
            defaults.set(data, forKey: pendingUploadsKey)
        }
    }

    func removePendingUpload(id: String) {
        var uploads = loadPendingUploads()
        uploads.removeAll { $0.id == id }
        savePendingUploads(uploads)

        // Also remove the file
        if let containerURL = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: ShareNetworkService.appGroupID
        ) {
            if let upload = loadPendingUploads().first(where: { $0.id == id }) {
                let fileURL = containerURL.appendingPathComponent(upload.relativePath)
                try? FileManager.default.removeItem(at: fileURL)
            }
        }
    }

    // MARK: - JWT Helpers

    private func isTokenExpired(_ token: String) -> Bool {
        let segments = token.split(separator: ".")
        guard segments.count >= 2 else { return true }

        var base64 = String(segments[1])
        // Pad to multiple of 4
        let remainder = base64.count % 4
        if remainder > 0 {
            base64 += String(repeating: "=", count: 4 - remainder)
        }

        guard let payloadData = Data(base64Encoded: base64) else { return true }
        guard let json = try? JSONSerialization.jsonObject(with: payloadData) as? [String: Any] else { return true }
        guard let exp = json["exp"] as? TimeInterval else { return true }

        // Consider expired if within 60 seconds of expiry
        return Date().timeIntervalSince1970 >= (exp - 60)
    }

    // MARK: - Error Types

    enum ShareError: Error, LocalizedError {
        case notAuthenticated
        case invalidURL
        case network(String)
        case serverError(Int)
        case fileTooLarge
        case decodingError(String)
        case fileReadError

        var errorDescription: String? {
            switch self {
            case .notAuthenticated:
                return "Please log in to Perennia AI first"
            case .invalidURL:
                return "Invalid API URL"
            case .network(let message):
                return "Network error: \(message)"
            case .serverError(let code):
                return "Server error (HTTP \(code))"
            case .fileTooLarge:
                return "File exceeds the 20MB size limit"
            case .decodingError(let message):
                return "Data error: \(message)"
            case .fileReadError:
                return "Could not read the shared file"
            }
        }
    }
}

// MARK: - Upload Progress Delegate

private class UploadProgressDelegate: NSObject, URLSessionTaskDelegate {
    let progressHandler: ((Double) -> Void)?

    init(progressHandler: ((Double) -> Void)?) {
        self.progressHandler = progressHandler
    }

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        didSendBodyData bytesSent: Int64,
        totalBytesSent: Int64,
        totalBytesExpectedToSend: Int64
    ) {
        guard totalBytesExpectedToSend > 0 else { return }
        let progress = Double(totalBytesSent) / Double(totalBytesExpectedToSend)
        DispatchQueue.main.async { [weak self] in
            self?.progressHandler?(progress)
        }
    }
}

// MARK: - Data Extensions for Multipart

extension Data {
    mutating func appendMultipartField(name: String, value: String, boundary: String) {
        append("--\(boundary)\r\n".data(using: .utf8)!)
        append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
        append("\(value)\r\n".data(using: .utf8)!)
    }

    mutating func appendMultipartFile(name: String, fileName: String, mimeType: String, fileData: Data, boundary: String) {
        append("--\(boundary)\r\n".data(using: .utf8)!)
        append("Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(fileName)\"\r\n".data(using: .utf8)!)
        append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        append(fileData)
        append("\r\n".data(using: .utf8)!)
    }
}
