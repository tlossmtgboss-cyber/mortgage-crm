import UIKit
import Social
import MobileCoreServices
import UniformTypeIdentifiers

// MARK: - Share Extension View Controller
// Custom UI for sharing documents into Perennia AI Smart Docs.
// Memory budget: 120MB. No Capacitor imports. Pure UIKit + URLSession.

class ShareViewController: UIViewController {

    // MARK: - Data Types

    enum DocumentType: String, CaseIterable {
        case payStub = "Pay Stub"
        case bankStatement = "Bank Statement"
        case taxReturn = "Tax Return"
        case idDocument = "ID Document"
        case other = "Other"
    }

    struct SharedFile {
        let data: Data
        let fileName: String
        let mimeType: String
        var thumbnail: UIImage?
    }

    /// A non-file shared item (URL or text).
    struct SharedTextItem {
        enum Kind: String { case url, text }
        let kind: Kind
        let content: String
        let title: String? // e.g., page title from Safari
    }

    /// Unified target — either a lead (with its first loan) or a loan directly.
    struct Target {
        let displayName: String
        let loanID: Int
        let borrowerID: Int
    }

    // MARK: - State

    private var sharedFiles: [SharedFile] = []
    private var sharedTextItems: [SharedTextItem] = []
    private var targets: [Target] = []
    private var selectedTargetIndex: Int = 0
    private var selectedDocType: DocumentType = .other
    private var isLoading = false
    private var isUploading = false
    private let networkService = ShareNetworkService.shared

    // MARK: - UI Elements

    private let containerView = UIView()
    private let headerView = UIView()
    private let titleLabel = UILabel()
    private let cancelButton = UIButton(type: .system)
    private let uploadButton = UIButton(type: .system)

    private let scrollView = UIScrollView()
    private let contentStack = UIStackView()

    private let thumbnailCollectionView: UICollectionView = {
        let layout = UICollectionViewFlowLayout()
        layout.scrollDirection = .horizontal
        layout.itemSize = CGSize(width: 72, height: 72)
        layout.minimumInteritemSpacing = 8
        layout.sectionInset = UIEdgeInsets(top: 0, left: 16, bottom: 0, right: 16)
        return UICollectionView(frame: .zero, collectionViewLayout: layout)
    }()

    private let fileCountLabel = UILabel()
    private let targetLabel = UILabel()
    private let targetPicker = UIPickerView()
    private let docTypeLabel = UILabel()
    private let docTypePicker = UIPickerView()

    private let progressContainer = UIView()
    private let progressBar = UIProgressView(progressViewStyle: .default)
    private let progressLabel = UILabel()

    private let statusLabel = UILabel()
    private let loadingSpinner = UIActivityIndicatorView(style: .medium)

    private let notLoggedInView = UIView()

    // MARK: - Colors

    private let accentColor = UIColor(red: 0.18, green: 0.45, blue: 0.82, alpha: 1.0) // Perennia blue
    private let backgroundColor = UIColor.systemBackground
    private let secondaryBackground = UIColor.secondarySystemBackground

    // MARK: - Lifecycle

    override func viewDidLoad() {
        super.viewDidLoad()
        setupUI()

        if networkService.isAuthenticated {
            loadSharedItems()
            fetchTargets()
        } else {
            showNotLoggedIn()
        }
    }

    // MARK: - UI Setup

    private func setupUI() {
        view.backgroundColor = UIColor.black.withAlphaComponent(0.4)

        // Container
        containerView.backgroundColor = backgroundColor
        containerView.layer.cornerRadius = 16
        containerView.layer.maskedCorners = [.layerMinXMinYCorner, .layerMaxXMinYCorner]
        containerView.clipsToBounds = true
        containerView.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(containerView)

        NSLayoutConstraint.activate([
            containerView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            containerView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            containerView.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            containerView.heightAnchor.constraint(equalTo: view.heightAnchor, multiplier: 0.7),
        ])

        setupHeader()
        setupScrollContent()
        setupProgressView()
        setupNotLoggedInView()
    }

    private func setupHeader() {
        headerView.backgroundColor = backgroundColor
        headerView.translatesAutoresizingMaskIntoConstraints = false
        containerView.addSubview(headerView)

        // Title
        titleLabel.text = "Share to Perennia AI"
        titleLabel.font = .systemFont(ofSize: 17, weight: .semibold)
        titleLabel.textAlignment = .center
        titleLabel.translatesAutoresizingMaskIntoConstraints = false
        headerView.addSubview(titleLabel)

        // Cancel
        cancelButton.setTitle("Cancel", for: .normal)
        cancelButton.titleLabel?.font = .systemFont(ofSize: 16)
        cancelButton.addTarget(self, action: #selector(cancelTapped), for: .touchUpInside)
        cancelButton.translatesAutoresizingMaskIntoConstraints = false
        headerView.addSubview(cancelButton)

        // Upload
        uploadButton.setTitle("Upload", for: .normal)
        uploadButton.titleLabel?.font = .systemFont(ofSize: 16, weight: .semibold)
        uploadButton.setTitleColor(accentColor, for: .normal)
        uploadButton.setTitleColor(.gray, for: .disabled)
        uploadButton.addTarget(self, action: #selector(uploadTapped), for: .touchUpInside)
        uploadButton.isEnabled = false
        uploadButton.translatesAutoresizingMaskIntoConstraints = false
        headerView.addSubview(uploadButton)

        // Separator
        let separator = UIView()
        separator.backgroundColor = .separator
        separator.translatesAutoresizingMaskIntoConstraints = false
        headerView.addSubview(separator)

        NSLayoutConstraint.activate([
            headerView.topAnchor.constraint(equalTo: containerView.topAnchor),
            headerView.leadingAnchor.constraint(equalTo: containerView.leadingAnchor),
            headerView.trailingAnchor.constraint(equalTo: containerView.trailingAnchor),
            headerView.heightAnchor.constraint(equalToConstant: 52),

            cancelButton.centerYAnchor.constraint(equalTo: headerView.centerYAnchor),
            cancelButton.leadingAnchor.constraint(equalTo: headerView.leadingAnchor, constant: 16),

            titleLabel.centerXAnchor.constraint(equalTo: headerView.centerXAnchor),
            titleLabel.centerYAnchor.constraint(equalTo: headerView.centerYAnchor),

            uploadButton.centerYAnchor.constraint(equalTo: headerView.centerYAnchor),
            uploadButton.trailingAnchor.constraint(equalTo: headerView.trailingAnchor, constant: -16),

            separator.leadingAnchor.constraint(equalTo: headerView.leadingAnchor),
            separator.trailingAnchor.constraint(equalTo: headerView.trailingAnchor),
            separator.bottomAnchor.constraint(equalTo: headerView.bottomAnchor),
            separator.heightAnchor.constraint(equalToConstant: 0.5),
        ])
    }

    private func setupScrollContent() {
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        containerView.addSubview(scrollView)

        contentStack.axis = .vertical
        contentStack.spacing = 20
        contentStack.translatesAutoresizingMaskIntoConstraints = false
        scrollView.addSubview(contentStack)

        NSLayoutConstraint.activate([
            scrollView.topAnchor.constraint(equalTo: headerView.bottomAnchor),
            scrollView.leadingAnchor.constraint(equalTo: containerView.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: containerView.trailingAnchor),
            scrollView.bottomAnchor.constraint(equalTo: containerView.bottomAnchor),

            contentStack.topAnchor.constraint(equalTo: scrollView.topAnchor, constant: 16),
            contentStack.leadingAnchor.constraint(equalTo: scrollView.leadingAnchor, constant: 16),
            contentStack.trailingAnchor.constraint(equalTo: scrollView.trailingAnchor, constant: -16),
            contentStack.bottomAnchor.constraint(equalTo: scrollView.bottomAnchor, constant: -32),
            contentStack.widthAnchor.constraint(equalTo: scrollView.widthAnchor, constant: -32),
        ])

        // -- Thumbnails Section --
        let thumbSection = createSectionView()

        fileCountLabel.font = .systemFont(ofSize: 14, weight: .medium)
        fileCountLabel.textColor = .secondaryLabel
        fileCountLabel.text = "Loading files..."
        thumbSection.addArrangedSubview(fileCountLabel)

        thumbnailCollectionView.backgroundColor = .clear
        thumbnailCollectionView.showsHorizontalScrollIndicator = false
        thumbnailCollectionView.register(ThumbnailCell.self, forCellWithReuseIdentifier: "ThumbnailCell")
        thumbnailCollectionView.dataSource = self
        thumbnailCollectionView.delegate = self
        thumbnailCollectionView.translatesAutoresizingMaskIntoConstraints = false
        thumbnailCollectionView.heightAnchor.constraint(equalToConstant: 80).isActive = true
        thumbSection.addArrangedSubview(thumbnailCollectionView)

        contentStack.addArrangedSubview(thumbSection)

        // -- Target Picker Section --
        let targetSection = createSectionView()

        targetLabel.text = "Upload To"
        targetLabel.font = .systemFont(ofSize: 14, weight: .medium)
        targetLabel.textColor = .secondaryLabel
        targetSection.addArrangedSubview(targetLabel)

        targetPicker.dataSource = self
        targetPicker.delegate = self
        targetPicker.tag = 1
        targetPicker.translatesAutoresizingMaskIntoConstraints = false
        targetPicker.heightAnchor.constraint(equalToConstant: 120).isActive = true
        targetSection.addArrangedSubview(targetPicker)

        // Loading spinner for targets
        loadingSpinner.hidesWhenStopped = true
        loadingSpinner.translatesAutoresizingMaskIntoConstraints = false
        targetSection.addArrangedSubview(loadingSpinner)

        contentStack.addArrangedSubview(targetSection)

        // -- Document Type Section --
        let docTypeSection = createSectionView()

        docTypeLabel.text = "Document Type"
        docTypeLabel.font = .systemFont(ofSize: 14, weight: .medium)
        docTypeLabel.textColor = .secondaryLabel
        docTypeSection.addArrangedSubview(docTypeLabel)

        docTypePicker.dataSource = self
        docTypePicker.delegate = self
        docTypePicker.tag = 2
        // Default to "Other"
        docTypePicker.selectRow(DocumentType.allCases.count - 1, inComponent: 0, animated: false)
        docTypePicker.translatesAutoresizingMaskIntoConstraints = false
        docTypePicker.heightAnchor.constraint(equalToConstant: 120).isActive = true
        docTypeSection.addArrangedSubview(docTypePicker)

        contentStack.addArrangedSubview(docTypeSection)

        // -- Status Label --
        statusLabel.font = .systemFont(ofSize: 14)
        statusLabel.textColor = .secondaryLabel
        statusLabel.textAlignment = .center
        statusLabel.numberOfLines = 0
        statusLabel.isHidden = true
        contentStack.addArrangedSubview(statusLabel)
    }

    private func setupProgressView() {
        progressContainer.isHidden = true
        progressContainer.translatesAutoresizingMaskIntoConstraints = false
        containerView.addSubview(progressContainer)

        // Semi-transparent overlay
        let overlay = UIView()
        overlay.backgroundColor = backgroundColor.withAlphaComponent(0.95)
        overlay.translatesAutoresizingMaskIntoConstraints = false
        progressContainer.addSubview(overlay)

        let progressStack = UIStackView()
        progressStack.axis = .vertical
        progressStack.spacing = 12
        progressStack.alignment = .center
        progressStack.translatesAutoresizingMaskIntoConstraints = false
        progressContainer.addSubview(progressStack)

        let uploadIcon = UIImageView(image: UIImage(systemName: "arrow.up.doc.fill"))
        uploadIcon.tintColor = accentColor
        uploadIcon.contentMode = .scaleAspectFit
        uploadIcon.translatesAutoresizingMaskIntoConstraints = false
        uploadIcon.heightAnchor.constraint(equalToConstant: 40).isActive = true
        uploadIcon.widthAnchor.constraint(equalToConstant: 40).isActive = true
        progressStack.addArrangedSubview(uploadIcon)

        progressLabel.text = "Uploading..."
        progressLabel.font = .systemFont(ofSize: 15, weight: .medium)
        progressLabel.textAlignment = .center
        progressStack.addArrangedSubview(progressLabel)

        progressBar.progressTintColor = accentColor
        progressBar.trackTintColor = secondaryBackground
        progressBar.translatesAutoresizingMaskIntoConstraints = false
        progressBar.widthAnchor.constraint(equalToConstant: 200).isActive = true
        progressStack.addArrangedSubview(progressBar)

        NSLayoutConstraint.activate([
            progressContainer.topAnchor.constraint(equalTo: headerView.bottomAnchor),
            progressContainer.leadingAnchor.constraint(equalTo: containerView.leadingAnchor),
            progressContainer.trailingAnchor.constraint(equalTo: containerView.trailingAnchor),
            progressContainer.bottomAnchor.constraint(equalTo: containerView.bottomAnchor),

            overlay.topAnchor.constraint(equalTo: progressContainer.topAnchor),
            overlay.leadingAnchor.constraint(equalTo: progressContainer.leadingAnchor),
            overlay.trailingAnchor.constraint(equalTo: progressContainer.trailingAnchor),
            overlay.bottomAnchor.constraint(equalTo: progressContainer.bottomAnchor),

            progressStack.centerXAnchor.constraint(equalTo: progressContainer.centerXAnchor),
            progressStack.centerYAnchor.constraint(equalTo: progressContainer.centerYAnchor),
        ])
    }

    private func setupNotLoggedInView() {
        notLoggedInView.isHidden = true
        notLoggedInView.backgroundColor = backgroundColor
        notLoggedInView.translatesAutoresizingMaskIntoConstraints = false
        containerView.addSubview(notLoggedInView)

        let stack = UIStackView()
        stack.axis = .vertical
        stack.spacing = 16
        stack.alignment = .center
        stack.translatesAutoresizingMaskIntoConstraints = false
        notLoggedInView.addSubview(stack)

        let lockIcon = UIImageView(image: UIImage(systemName: "lock.circle.fill"))
        lockIcon.tintColor = .secondaryLabel
        lockIcon.contentMode = .scaleAspectFit
        lockIcon.translatesAutoresizingMaskIntoConstraints = false
        lockIcon.heightAnchor.constraint(equalToConstant: 48).isActive = true
        lockIcon.widthAnchor.constraint(equalToConstant: 48).isActive = true
        stack.addArrangedSubview(lockIcon)

        let messageLabel = UILabel()
        messageLabel.text = "Please log in to Perennia AI first"
        messageLabel.font = .systemFont(ofSize: 16, weight: .medium)
        messageLabel.textColor = .secondaryLabel
        messageLabel.textAlignment = .center
        messageLabel.numberOfLines = 0
        stack.addArrangedSubview(messageLabel)

        let openAppButton = UIButton(type: .system)
        openAppButton.setTitle("Open Perennia AI", for: .normal)
        openAppButton.titleLabel?.font = .systemFont(ofSize: 16, weight: .semibold)
        openAppButton.backgroundColor = accentColor
        openAppButton.setTitleColor(.white, for: .normal)
        openAppButton.layer.cornerRadius = 12
        openAppButton.contentEdgeInsets = UIEdgeInsets(top: 12, left: 32, bottom: 12, right: 32)
        openAppButton.addTarget(self, action: #selector(openMainApp), for: .touchUpInside)
        stack.addArrangedSubview(openAppButton)

        NSLayoutConstraint.activate([
            notLoggedInView.topAnchor.constraint(equalTo: headerView.bottomAnchor),
            notLoggedInView.leadingAnchor.constraint(equalTo: containerView.leadingAnchor),
            notLoggedInView.trailingAnchor.constraint(equalTo: containerView.trailingAnchor),
            notLoggedInView.bottomAnchor.constraint(equalTo: containerView.bottomAnchor),

            stack.centerXAnchor.constraint(equalTo: notLoggedInView.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: notLoggedInView.centerYAnchor),
            stack.leadingAnchor.constraint(greaterThanOrEqualTo: notLoggedInView.leadingAnchor, constant: 32),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: notLoggedInView.trailingAnchor, constant: -32),
        ])
    }

    private func createSectionView() -> UIStackView {
        let stack = UIStackView()
        stack.axis = .vertical
        stack.spacing = 8
        stack.backgroundColor = secondaryBackground
        stack.layer.cornerRadius = 12
        stack.layoutMargins = UIEdgeInsets(top: 12, left: 12, bottom: 12, right: 12)
        stack.isLayoutMarginsRelativeArrangement = true
        return stack
    }

    // MARK: - Show States

    private func showNotLoggedIn() {
        notLoggedInView.isHidden = false
        scrollView.isHidden = true
        uploadButton.isHidden = true
    }

    private func showSuccess(targetName: String, fileCount: Int, message: String? = nil) {
        progressContainer.isHidden = false
        progressBar.isHidden = true
        uploadButton.isEnabled = false
        cancelButton.setTitle("Done", for: .normal)

        let checkmark = UIImageView(image: UIImage(systemName: "checkmark.circle.fill"))
        checkmark.tintColor = UIColor.systemGreen
        checkmark.contentMode = .scaleAspectFit
        checkmark.translatesAutoresizingMaskIntoConstraints = false
        checkmark.heightAnchor.constraint(equalToConstant: 48).isActive = true
        checkmark.widthAnchor.constraint(equalToConstant: 48).isActive = true

        // Replace the progress content
        for subview in progressContainer.subviews {
            subview.removeFromSuperview()
        }

        let overlay = UIView()
        overlay.backgroundColor = backgroundColor
        overlay.translatesAutoresizingMaskIntoConstraints = false
        progressContainer.addSubview(overlay)

        let stack = UIStackView()
        stack.axis = .vertical
        stack.spacing = 12
        stack.alignment = .center
        stack.translatesAutoresizingMaskIntoConstraints = false
        progressContainer.addSubview(stack)

        stack.addArrangedSubview(checkmark)

        let label = UILabel()
        let successMessage: String
        if let message = message {
            successMessage = message
        } else {
            let fileText = fileCount == 1 ? "Document" : "\(fileCount) documents"
            successMessage = "\(fileText) uploaded to\n\(targetName)"
        }
        label.text = successMessage
        label.font = .systemFont(ofSize: 16, weight: .medium)
        label.textAlignment = .center
        label.numberOfLines = 0
        stack.addArrangedSubview(label)

        NSLayoutConstraint.activate([
            overlay.topAnchor.constraint(equalTo: progressContainer.topAnchor),
            overlay.leadingAnchor.constraint(equalTo: progressContainer.leadingAnchor),
            overlay.trailingAnchor.constraint(equalTo: progressContainer.trailingAnchor),
            overlay.bottomAnchor.constraint(equalTo: progressContainer.bottomAnchor),

            stack.centerXAnchor.constraint(equalTo: progressContainer.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: progressContainer.centerYAnchor),
            stack.leadingAnchor.constraint(greaterThanOrEqualTo: progressContainer.leadingAnchor, constant: 32),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: progressContainer.trailingAnchor, constant: -32),
        ])

        // Auto-dismiss after 1.5 seconds
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
            self?.extensionContext?.completeRequest(returningItems: nil, completionHandler: nil)
        }
    }

    private func showError(_ message: String, queued: Bool) {
        progressContainer.isHidden = true
        isUploading = false
        uploadButton.isEnabled = true
        cancelButton.isEnabled = true

        statusLabel.isHidden = false
        if queued {
            statusLabel.textColor = UIColor.systemOrange
            statusLabel.text = "Upload failed \u{2014} saved to upload later.\n\(message)"
        } else {
            statusLabel.textColor = .systemRed
            statusLabel.text = message
        }
    }

    // MARK: - Actions

    @objc private func cancelTapped() {
        extensionContext?.cancelRequest(withError: NSError(
            domain: "com.perenniaai.crm.share",
            code: 0,
            userInfo: [NSLocalizedDescriptionKey: "User cancelled"]
        ))
    }

    @objc private func openMainApp() {
        // Deep link to main app
        if let url = URL(string: "perenniaai://login") {
            // Share extensions can't use UIApplication.shared.open directly
            // Use the extension context to open the URL via a responder chain workaround
            var responder: UIResponder? = self
            while responder != nil {
                if let application = responder as? UIApplication {
                    application.open(url, options: [:], completionHandler: nil)
                    break
                }
                responder = responder?.next
            }
        }
        extensionContext?.cancelRequest(withError: NSError(
            domain: "com.perenniaai.crm.share",
            code: 1,
            userInfo: [NSLocalizedDescriptionKey: "Opening main app"]
        ))
    }

    @objc private func uploadTapped() {
        guard !isUploading else { return }

        // Handle text/URL-only shares (no files)
        if sharedFiles.isEmpty && !sharedTextItems.isEmpty {
            isUploading = true
            uploadButton.isEnabled = false
            cancelButton.isEnabled = false
            saveTextItemsToAppGroup()
            return
        }

        guard !sharedFiles.isEmpty, !targets.isEmpty else { return }

        isUploading = true
        uploadButton.isEnabled = false
        cancelButton.isEnabled = false
        progressContainer.isHidden = false
        progressBar.progress = 0
        progressBar.isHidden = false

        // Also save any text items alongside the file upload
        if !sharedTextItems.isEmpty {
            saveTextItemsToAppGroup()
        }

        let target = targets[selectedTargetIndex]
        let docType = selectedDocType.rawValue
        let totalFiles = sharedFiles.count
        var completedFiles = 0
        var failedFiles: [SharedFile] = []

        let uploadGroup = DispatchGroup()

        for file in sharedFiles {
            uploadGroup.enter()

            networkService.uploadDocument(
                fileData: file.data,
                fileName: file.fileName,
                mimeType: file.mimeType,
                loanID: target.loanID,
                borrowerID: target.borrowerID,
                docType: docType,
                progressHandler: { [weak self] progress in
                    guard let self = self else { return }
                    // Weighted progress across all files
                    let fileWeight = 1.0 / Double(totalFiles)
                    let overallProgress = (Double(completedFiles) * fileWeight) + (progress * fileWeight)
                    self.progressBar.progress = Float(overallProgress)
                    self.progressLabel.text = "Uploading \(completedFiles + 1) of \(totalFiles)..."
                },
                completion: { [weak self] result in
                    switch result {
                    case .success:
                        completedFiles += 1
                    case .failure:
                        failedFiles.append(file)
                        completedFiles += 1
                    }
                    uploadGroup.leave()
                }
            )
        }

        uploadGroup.notify(queue: .main) { [weak self] in
            guard let self = self else { return }

            if failedFiles.isEmpty {
                // All succeeded
                self.showSuccess(targetName: target.displayName, fileCount: totalFiles)
            } else if completedFiles == failedFiles.count {
                // All failed — queue them for later
                self.queueFailedFiles(failedFiles, target: target, docType: docType)
            } else {
                // Partial success
                self.queueFailedFiles(failedFiles, target: target, docType: docType)
                let successCount = totalFiles - failedFiles.count
                self.showSuccess(targetName: target.displayName, fileCount: successCount)
            }
        }
    }

    // MARK: - Save Text/URL Items

    /// Saves shared text/URL items to the App Group container so the main app
    /// can process them (e.g., attach a URL to a lead, create a note, etc.).
    /// Posts a Darwin notification to wake the main app if it's running.
    private func saveTextItemsToAppGroup() {
        guard let containerURL = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: "group.com.perenniaai.crm"
        ) else {
            if sharedFiles.isEmpty {
                showError("Could not access shared storage.", queued: false)
            }
            return
        }

        let sharedItemsDir = containerURL.appendingPathComponent("SharedItems", isDirectory: true)
        try? FileManager.default.createDirectory(at: sharedItemsDir, withIntermediateDirectories: true)

        let defaults = UserDefaults(suiteName: "group.com.perenniaai.crm")

        // Load existing pending shared items
        var pendingItems: [[String: String]] = []
        if let data = defaults?.data(forKey: "PendingSharedItems"),
           let existing = try? JSONSerialization.jsonObject(with: data) as? [[String: String]] {
            pendingItems = existing
        }

        for item in sharedTextItems {
            let entry: [String: String] = [
                "id": UUID().uuidString,
                "kind": item.kind.rawValue,
                "content": item.content,
                "title": item.title ?? "",
                "sharedAt": ISO8601DateFormatter().string(from: Date()),
            ]
            pendingItems.append(entry)
        }

        // Save back
        if let data = try? JSONSerialization.data(withJSONObject: pendingItems) {
            defaults?.set(data, forKey: "PendingSharedItems")
        }

        // Post a Darwin notification so the main app picks up the new items
        let notificationName = "com.perenniaai.crm.sharedItemReceived" as CFString
        CFNotificationCenterPostNotification(
            CFNotificationCenterGetDarwinNotifyCenter(),
            CFNotificationName(notificationName),
            nil, nil, true
        )

        // If this was a text/URL-only share, show success and dismiss
        if sharedFiles.isEmpty {
            let count = sharedTextItems.count
            let itemLabel: String
            if count == 1 {
                itemLabel = sharedTextItems[0].kind == .url ? "Link" : "Text"
            } else {
                itemLabel = "\(count) items"
            }
            showSuccess(
                targetName: "Perennia AI",
                fileCount: count,
                message: "\(itemLabel) saved to Perennia AI"
            )
        }
    }

    private func queueFailedFiles(_ files: [SharedFile], target: Target, docType: String) {
        var allQueued = true
        for file in files {
            let success = networkService.queueForLaterUpload(
                fileData: file.data,
                fileName: file.fileName,
                mimeType: file.mimeType,
                loanID: target.loanID,
                borrowerID: target.borrowerID,
                docType: docType
            )
            if !success { allQueued = false }
        }

        if allQueued {
            showError(
                "\(files.count) file(s) will upload when you next open the app.",
                queued: true
            )
        } else {
            showError("Upload failed. Please try again from the Perennia AI app.", queued: false)
        }
    }

    // MARK: - Load Shared Items

    private func loadSharedItems() {
        guard let extensionItems = extensionContext?.inputItems as? [NSExtensionItem] else {
            fileCountLabel.text = "No items to share"
            return
        }

        let group = DispatchGroup()
        var loadedFiles: [SharedFile] = []
        var loadedTextItems: [SharedTextItem] = []

        for item in extensionItems {
            guard let attachments = item.attachments else { continue }
            let itemTitle = item.attributedContentText?.string

            for provider in attachments {
                group.enter()
                loadAttachment(provider: provider, itemTitle: itemTitle) { file, textItem in
                    if let file = file {
                        loadedFiles.append(file)
                    }
                    if let textItem = textItem {
                        loadedTextItems.append(textItem)
                    }
                    group.leave()
                }
            }
        }

        group.notify(queue: .main) { [weak self] in
            guard let self = self else { return }
            self.sharedFiles = loadedFiles
            self.sharedTextItems = loadedTextItems

            if !loadedFiles.isEmpty {
                self.fileCountLabel.text = "\(loadedFiles.count) file\(loadedFiles.count == 1 ? "" : "s") ready to upload"
            } else if !loadedTextItems.isEmpty {
                let desc = loadedTextItems.map { $0.kind == .url ? "link" : "text" }
                let summary = desc.count == 1 ? "1 \(desc[0])" : "\(desc.count) items"
                self.fileCountLabel.text = "\(summary) ready to save"
                // For text/URL-only shares, change the button label
                self.uploadButton.setTitle("Save", for: .normal)
            } else {
                self.fileCountLabel.text = "No supported items found"
            }

            self.thumbnailCollectionView.reloadData()
            self.updateUploadButtonState()
        }
    }

    private func loadAttachment(provider: NSItemProvider, itemTitle: String? = nil, completion: @escaping (SharedFile?, SharedTextItem?) -> Void) {
        // Try loading in order of specificity: PDF, image, data, URL, text
        let supportedTypes: [(UTType, String)] = [
            (.pdf, "application/pdf"),
            (.jpeg, "image/jpeg"),
            (.png, "image/png"),
            (.heic, "image/heic"),
            (.tiff, "image/tiff"),
        ]

        // Check for specific UTTypes first
        for (utType, mimeType) in supportedTypes {
            if provider.hasItemConformingToTypeIdentifier(utType.identifier) {
                provider.loadFileRepresentation(forTypeIdentifier: utType.identifier) { url, error in
                    guard let url = url, error == nil else {
                        completion(nil, nil)
                        return
                    }
                    self.readFileFromURL(url, mimeType: mimeType) { file in
                        completion(file, nil)
                    }
                }
                return
            }
        }

        // Check for generic data types (Word, Excel)
        let dataTypes = [
            "com.microsoft.word.doc",
            "org.openxmlformats.wordprocessingml.document",
            "com.microsoft.excel.xls",
            "org.openxmlformats.spreadsheetml.sheet",
        ]

        for typeID in dataTypes {
            if provider.hasItemConformingToTypeIdentifier(typeID) {
                provider.loadFileRepresentation(forTypeIdentifier: typeID) { url, error in
                    guard let url = url, error == nil else {
                        completion(nil, nil)
                        return
                    }
                    let mime = self.mimeTypeForExtension(url.pathExtension)
                    self.readFileFromURL(url, mimeType: mime) { file in
                        completion(file, nil)
                    }
                }
                return
            }
        }

        // Fallback: generic public.data (files)
        if provider.hasItemConformingToTypeIdentifier(UTType.data.identifier)
            && !provider.hasItemConformingToTypeIdentifier(UTType.url.identifier)
            && !provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
            provider.loadFileRepresentation(forTypeIdentifier: UTType.data.identifier) { url, error in
                guard let url = url, error == nil else {
                    completion(nil, nil)
                    return
                }
                let mime = self.mimeTypeForExtension(url.pathExtension)
                self.readFileFromURL(url, mimeType: mime) { file in
                    completion(file, nil)
                }
            }
            return
        }

        // URL sharing (e.g., from Safari, property listing links)
        if provider.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
            provider.loadItem(forTypeIdentifier: UTType.url.identifier, options: nil) { item, error in
                guard error == nil else {
                    completion(nil, nil)
                    return
                }
                if let url = item as? URL {
                    if url.isFileURL {
                        // File URL — treat as a document
                        let mime = self.mimeTypeForExtension(url.pathExtension)
                        self.readFileFromURL(url, mimeType: mime) { file in
                            completion(file, nil)
                        }
                    } else {
                        // Web URL — store as a shared text item
                        let textItem = SharedTextItem(
                            kind: .url,
                            content: url.absoluteString,
                            title: itemTitle
                        )
                        completion(nil, textItem)
                    }
                } else {
                    completion(nil, nil)
                }
            }
            return
        }

        // Plain text sharing (notes, addresses, etc.)
        if provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
            provider.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { item, error in
                guard error == nil else {
                    completion(nil, nil)
                    return
                }
                if let text = item as? String, !text.isEmpty {
                    let textItem = SharedTextItem(
                        kind: .text,
                        content: text,
                        title: itemTitle
                    )
                    completion(nil, textItem)
                } else {
                    completion(nil, nil)
                }
            }
            return
        }

        completion(nil, nil)
    }

    private func readFileFromURL(_ url: URL, mimeType: String, completion: @escaping (SharedFile?) -> Void) {
        do {
            let data = try Data(contentsOf: url, options: .mappedIfSafe)

            // 20MB limit per file (API constraint)
            guard data.count <= 20 * 1024 * 1024 else {
                completion(nil)
                return
            }

            let fileName = url.lastPathComponent
            let thumbnail = generateThumbnail(for: url, mimeType: mimeType)

            completion(SharedFile(data: data, fileName: fileName, mimeType: mimeType, thumbnail: thumbnail))
        } catch {
            completion(nil)
        }
    }

    private func generateThumbnail(for url: URL, mimeType: String) -> UIImage? {
        if mimeType.hasPrefix("image/") {
            // Downsample for memory efficiency
            let options: [CFString: Any] = [
                kCGImageSourceThumbnailMaxPixelSize: 144,
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
            ]
            guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
                  let cgImage = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else {
                return nil
            }
            return UIImage(cgImage: cgImage)
        }

        if mimeType == "application/pdf" {
            return UIImage(systemName: "doc.fill")
        }

        // Generic document icon
        return UIImage(systemName: "doc.text.fill")
    }

    // MARK: - Fetch Targets (Leads + Loans)

    private func fetchTargets() {
        loadingSpinner.startAnimating()
        isLoading = true

        let group = DispatchGroup()
        var allTargets: [Target] = []

        // Fetch loans (primary target since upload requires loan_id)
        group.enter()
        networkService.fetchRecentLoans { result in
            switch result {
            case .success(let loans):
                for loan in loans {
                    allTargets.append(Target(
                        displayName: loan.displayName,
                        loanID: loan.id,
                        borrowerID: loan.borrower_id ?? 0
                    ))
                }
            case .failure:
                break // Continue with leads
            }
            group.leave()
        }

        // Fetch leads as secondary option
        group.enter()
        networkService.fetchRecentLeads { result in
            switch result {
            case .success(let leads):
                // Leads need a loan_id for upload. We include them but mark they need a loan.
                // For leads without a loan, we still show them — the upload may fail gracefully
                // or the API may handle lead-only uploads in the future.
                for lead in leads {
                    // Only add leads that aren't already represented via loans
                    if !allTargets.contains(where: { $0.displayName.contains(lead.displayName) }) {
                        allTargets.append(Target(
                            displayName: "\(lead.displayName) (Lead)",
                            loanID: 0, // Will need special handling
                            borrowerID: 0
                        ))
                    }
                }
            case .failure:
                break
            }
            group.leave()
        }

        group.notify(queue: .main) { [weak self] in
            guard let self = self else { return }
            self.loadingSpinner.stopAnimating()
            self.isLoading = false

            // Filter to only targets that have a valid loan ID
            self.targets = allTargets.filter { $0.loanID > 0 }

            if self.targets.isEmpty {
                self.targetLabel.text = "Upload To (no active loans found)"
            } else {
                self.targetLabel.text = "Upload To"
            }

            self.targetPicker.reloadAllComponents()
            self.updateUploadButtonState()
        }
    }

    // MARK: - Helpers

    private func updateUploadButtonState() {
        let hasFiles = !sharedFiles.isEmpty && !targets.isEmpty
        let hasTextItems = !sharedTextItems.isEmpty
        uploadButton.isEnabled = (hasFiles || hasTextItems) && !isUploading
    }

    private func mimeTypeForExtension(_ ext: String) -> String {
        switch ext.lowercased() {
        case "pdf": return "application/pdf"
        case "jpg", "jpeg": return "image/jpeg"
        case "png": return "image/png"
        case "heic", "heif": return "image/heic"
        case "tiff", "tif": return "image/tiff"
        case "doc": return "application/msword"
        case "docx": return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        case "xls": return "application/vnd.ms-excel"
        case "xlsx": return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        default: return "application/octet-stream"
        }
    }
}

// MARK: - UICollectionView DataSource & Delegate

extension ShareViewController: UICollectionViewDataSource, UICollectionViewDelegate {

    func collectionView(_ collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return sharedFiles.count
    }

    func collectionView(_ collectionView: UICollectionView, cellForItemAt indexPath: IndexPath) -> UICollectionViewCell {
        let cell = collectionView.dequeueReusableCell(withReuseIdentifier: "ThumbnailCell", for: indexPath) as! ThumbnailCell
        let file = sharedFiles[indexPath.item]
        cell.configure(with: file)
        return cell
    }
}

// MARK: - UIPickerView DataSource & Delegate

extension ShareViewController: UIPickerViewDataSource, UIPickerViewDelegate {

    func numberOfComponents(in pickerView: UIPickerView) -> Int {
        return 1
    }

    func pickerView(_ pickerView: UIPickerView, numberOfRowsInComponent component: Int) -> Int {
        if pickerView.tag == 1 {
            return max(targets.count, 1) // Show at least 1 row with placeholder
        } else {
            return DocumentType.allCases.count
        }
    }

    func pickerView(_ pickerView: UIPickerView, titleForRow row: Int, forComponent component: Int) -> String? {
        if pickerView.tag == 1 {
            if targets.isEmpty {
                return isLoading ? "Loading..." : "No active loans"
            }
            return targets[row].displayName
        } else {
            return DocumentType.allCases[row].rawValue
        }
    }

    func pickerView(_ pickerView: UIPickerView, didSelectRow row: Int, inComponent component: Int) {
        if pickerView.tag == 1 {
            if !targets.isEmpty {
                selectedTargetIndex = row
            }
        } else {
            selectedDocType = DocumentType.allCases[row]
        }
    }
}

// MARK: - Thumbnail Cell

class ThumbnailCell: UICollectionViewCell {

    private let imageView = UIImageView()
    private let nameLabel = UILabel()

    override init(frame: CGRect) {
        super.init(frame: frame)
        setupCell()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func setupCell() {
        contentView.backgroundColor = UIColor.tertiarySystemBackground
        contentView.layer.cornerRadius = 8
        contentView.clipsToBounds = true

        imageView.contentMode = .scaleAspectFit
        imageView.tintColor = UIColor(red: 0.18, green: 0.45, blue: 0.82, alpha: 1.0)
        imageView.translatesAutoresizingMaskIntoConstraints = false
        contentView.addSubview(imageView)

        nameLabel.font = .systemFont(ofSize: 9)
        nameLabel.textColor = .secondaryLabel
        nameLabel.textAlignment = .center
        nameLabel.lineBreakMode = .byTruncatingMiddle
        nameLabel.translatesAutoresizingMaskIntoConstraints = false
        contentView.addSubview(nameLabel)

        NSLayoutConstraint.activate([
            imageView.topAnchor.constraint(equalTo: contentView.topAnchor, constant: 6),
            imageView.centerXAnchor.constraint(equalTo: contentView.centerXAnchor),
            imageView.widthAnchor.constraint(equalToConstant: 36),
            imageView.heightAnchor.constraint(equalToConstant: 36),

            nameLabel.topAnchor.constraint(equalTo: imageView.bottomAnchor, constant: 4),
            nameLabel.leadingAnchor.constraint(equalTo: contentView.leadingAnchor, constant: 4),
            nameLabel.trailingAnchor.constraint(equalTo: contentView.trailingAnchor, constant: -4),
            nameLabel.bottomAnchor.constraint(lessThanOrEqualTo: contentView.bottomAnchor, constant: -4),
        ])
    }

    func configure(with file: ShareViewController.SharedFile) {
        if let thumbnail = file.thumbnail {
            imageView.image = thumbnail
        } else {
            imageView.image = UIImage(systemName: "doc.fill")
        }
        nameLabel.text = file.fileName
    }
}
