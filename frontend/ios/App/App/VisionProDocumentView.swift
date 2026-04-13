/**
 * VisionProDocumentView.swift
 * Perennia AI — Spatial Document Viewer for Apple Vision Pro
 *
 * Displays loan documents (PDF, images) in an immersive, readable format.
 * On visionOS, uses spatial layout hints for side-by-side viewing and depth effects.
 * On iOS/iPadOS, provides a standard PDFKit viewer with pinch-to-zoom.
 */

import SwiftUI
import PDFKit
import UIKit

// MARK: - Document View Model

@available(iOS 15.0, *)
final class VisionProDocumentViewModel: ObservableObject {
    @Published var pdfDocument: PDFDocument?
    @Published var isLoading = true
    @Published var errorMessage: String?
    @Published var currentPage: Int = 0
    @Published var totalPages: Int = 0
    @Published var documentTitle: String = "Document"

    let documentURL: URL

    init(url: URL, title: String? = nil) {
        self.documentURL = url
        if let title = title {
            self.documentTitle = title
        } else {
            self.documentTitle = url.deletingPathExtension().lastPathComponent
        }
    }

    @MainActor
    func loadDocument() async {
        isLoading = true
        errorMessage = nil

        if documentURL.isFileURL {
            loadLocalDocument()
        } else {
            await loadRemoteDocument()
        }
    }

    @MainActor
    private func loadLocalDocument() {
        if let document = PDFDocument(url: documentURL) {
            self.pdfDocument = document
            self.totalPages = document.pageCount
            self.isLoading = false
        } else {
            self.errorMessage = "Unable to open document."
            self.isLoading = false
        }
    }

    @MainActor
    private func loadRemoteDocument() async {
        do {
            var request = URLRequest(url: documentURL)
            request.httpMethod = "GET"

            // Attach auth token when fetching from the Perennia API backend,
            // since document endpoints require authentication.
            let apiHost = URL(string: APIConfig.apiBaseURL)?.host
            if let apiHost = apiHost,
               documentURL.host == apiHost,
               let token = KeychainService.shared.authToken {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }

            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                self.errorMessage = "Invalid server response."
                self.isLoading = false
                return
            }

            guard (200...299).contains(httpResponse.statusCode) else {
                if httpResponse.statusCode == 401 {
                    self.errorMessage = "Authentication required. Please sign in again."
                } else {
                    self.errorMessage = "Server returned error \(httpResponse.statusCode)."
                }
                self.isLoading = false
                return
            }

            if let document = PDFDocument(data: data) {
                self.pdfDocument = document
                self.totalPages = document.pageCount
            } else {
                self.errorMessage = "The file is not a valid PDF."
            }
        } catch {
            self.errorMessage = "Failed to download: \(error.localizedDescription)"
        }

        self.isLoading = false
    }
}

// MARK: - Main Document View

@available(iOS 15.0, *)
struct VisionProDocumentView: View {
    @StateObject private var viewModel: VisionProDocumentViewModel
    @State private var showThumbnails = false
    @State private var zoomScale: CGFloat = 1.0

    init(url: URL, title: String? = nil) {
        _viewModel = StateObject(wrappedValue: VisionProDocumentViewModel(url: url, title: title))
    }

    var body: some View {
        Group {
            if viewModel.isLoading {
                loadingView
            } else if let error = viewModel.errorMessage {
                errorView(error)
            } else if viewModel.pdfDocument != nil {
                documentContent
            }
        }
        .task {
            await viewModel.loadDocument()
        }
    }

    // MARK: - Document Content

    private var documentContent: some View {
        VStack(spacing: 0) {
            // Toolbar
            documentToolbar

            // PDF viewer
            ZStack {
                pdfViewRepresentable
                    .ignoresSafeArea(.container, edges: .bottom)

                // Thumbnail sidebar
                if showThumbnails {
                    thumbnailSidebar
                }
            }
        }
        .background(documentBackground)
        #if os(visionOS)
        .ornament(attachmentAnchor: .scene(.bottom)) {
            pageNavigationOrnament
        }
        #endif
    }

    // MARK: - Toolbar

    private var documentToolbar: some View {
        HStack(spacing: 16) {
            // Document title
            VStack(alignment: .leading, spacing: 2) {
                Text(viewModel.documentTitle)
                    .font(.headline)
                    .lineLimit(1)

                if viewModel.totalPages > 0 {
                    Text("Page \(viewModel.currentPage + 1) of \(viewModel.totalPages)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .monospacedDigit()
                }
            }

            Spacer()

            // Thumbnail toggle
            Button(action: {
                withAnimation(.easeInOut(duration: 0.25)) {
                    showThumbnails.toggle()
                }
            }) {
                Image(systemName: showThumbnails ? "sidebar.left" : "sidebar.left")
                    .font(.title3)
                    .foregroundColor(showThumbnails ? .accentColor : .secondary)
            }
            .accessibilityLabel(showThumbnails ? "Hide thumbnails" : "Show thumbnails")

            // Zoom controls
            HStack(spacing: 8) {
                Button(action: { adjustZoom(by: -0.25) }) {
                    Image(systemName: "minus.magnifyingglass")
                        .font(.title3)
                }
                .disabled(zoomScale <= 0.5)

                Text("\(Int(zoomScale * 100))%")
                    .font(.caption.monospacedDigit())
                    .frame(minWidth: 44)

                Button(action: { adjustZoom(by: 0.25) }) {
                    Image(systemName: "plus.magnifyingglass")
                        .font(.title3)
                }
                .disabled(zoomScale >= 4.0)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Zoom: \(Int(zoomScale * 100)) percent")

            // Share button
            if #available(iOS 16.0, *) {
                ShareLink(item: viewModel.documentURL) {
                    Image(systemName: "square.and.arrow.up")
                        .font(.title3)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(toolbarBackground)
    }

    // MARK: - PDF View (UIKit bridge)

    private var pdfViewRepresentable: some View {
        PDFViewRepresentable(
            document: viewModel.pdfDocument,
            currentPage: $viewModel.currentPage,
            zoomScale: $zoomScale
        )
    }

    // MARK: - Thumbnail Sidebar

    private var thumbnailSidebar: some View {
        HStack(spacing: 0) {
            ScrollView(.vertical, showsIndicators: true) {
                LazyVStack(spacing: 8) {
                    if let document = viewModel.pdfDocument {
                        ForEach(0..<document.pageCount, id: \.self) { index in
                            thumbnailItem(for: document, at: index)
                        }
                    }
                }
                .padding(8)
            }
            .frame(width: thumbnailWidth)
            .background(sidebarBackground)

            Spacer()
        }
        .transition(.move(edge: .leading))
    }

    private func thumbnailItem(for document: PDFDocument, at index: Int) -> some View {
        Button(action: {
            viewModel.currentPage = index
        }) {
            VStack(spacing: 4) {
                if let page = document.page(at: index) {
                    PDFThumbnailRepresentable(page: page)
                        .frame(width: thumbnailWidth - 32, height: (thumbnailWidth - 32) * 1.4)
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(index == viewModel.currentPage ? Color.accentColor : Color.clear, lineWidth: 2)
                        )
                }

                Text("\(index + 1)")
                    .font(.caption2)
                    .foregroundColor(index == viewModel.currentPage ? .accentColor : .secondary)
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Page \(index + 1)")
    }

    // MARK: - visionOS Ornament

    #if os(visionOS)
    private var pageNavigationOrnament: some View {
        HStack(spacing: 20) {
            Button(action: { navigatePage(by: -1) }) {
                Image(systemName: "chevron.left")
                    .font(.title3)
            }
            .disabled(viewModel.currentPage <= 0)

            Text("Page \(viewModel.currentPage + 1) / \(viewModel.totalPages)")
                .font(.subheadline.monospacedDigit())
                .frame(minWidth: 100)

            Button(action: { navigatePage(by: 1) }) {
                Image(systemName: "chevron.right")
                    .font(.title3)
            }
            .disabled(viewModel.currentPage >= viewModel.totalPages - 1)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .glassBackgroundEffect()
    }
    #endif

    // MARK: - Loading & Error States

    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.5)
            Text("Loading document...")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(documentBackground)
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "doc.text.fill.viewfinder")
                .font(.system(size: 48))
                .foregroundColor(.red.opacity(0.8))

            Text("Could not open document")
                .font(.headline)

            Text(message)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            Button(action: {
                Task { await viewModel.loadDocument() }
            }) {
                Label("Try Again", systemImage: "arrow.clockwise")
            }
            .buttonStyle(.borderedProminent)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(documentBackground)
    }

    // MARK: - Helpers

    private func adjustZoom(by delta: CGFloat) {
        let newScale = max(0.5, min(4.0, zoomScale + delta))
        withAnimation(.easeInOut(duration: 0.2)) {
            zoomScale = newScale
        }
    }

    private func navigatePage(by offset: Int) {
        let newPage = viewModel.currentPage + offset
        guard newPage >= 0, newPage < viewModel.totalPages else { return }
        viewModel.currentPage = newPage
    }

    // MARK: - Platform-Adaptive Styling

    private var thumbnailWidth: CGFloat {
        #if os(visionOS)
        return 160
        #else
        return VisionProSupport.isVisionPro ? 160 : 120
        #endif
    }

    @ViewBuilder
    private var documentBackground: some View {
        #if os(visionOS)
        Color.clear
        #else
        Color(.systemBackground)
            .ignoresSafeArea()
        #endif
    }

    @ViewBuilder
    private var toolbarBackground: some View {
        #if os(visionOS)
        Rectangle().fill(.ultraThinMaterial)
        #else
        Rectangle().fill(Color(.secondarySystemBackground))
        #endif
    }

    @ViewBuilder
    private var sidebarBackground: some View {
        #if os(visionOS)
        Rectangle().fill(.thinMaterial)
        #else
        Rectangle().fill(Color(.secondarySystemBackground))
        #endif
    }
}

// MARK: - PDFView UIKit Representable

@available(iOS 15.0, *)
struct PDFViewRepresentable: UIViewRepresentable {
    let document: PDFDocument?
    @Binding var currentPage: Int
    @Binding var zoomScale: CGFloat

    func makeUIView(context: Context) -> PDFView {
        let pdfView = PDFView()
        pdfView.document = document
        pdfView.autoScales = true
        pdfView.displayMode = .singlePageContinuous
        pdfView.displayDirection = .vertical
        pdfView.backgroundColor = .clear

        // Enable pinch-to-zoom
        pdfView.minScaleFactor = pdfView.scaleFactorForSizeToFit * 0.5
        pdfView.maxScaleFactor = pdfView.scaleFactorForSizeToFit * 4.0

        // Configure for visionOS / large displays
        #if os(visionOS)
        pdfView.pageShadowsEnabled = false
        #else
        if VisionProSupport.isVisionPro {
            pdfView.pageShadowsEnabled = false
        }
        #endif

        // Observe page changes
        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.pageChanged(_:)),
            name: .PDFViewPageChanged,
            object: pdfView
        )

        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.scaleChanged(_:)),
            name: .PDFViewScaleChanged,
            object: pdfView
        )

        context.coordinator.pdfView = pdfView
        return pdfView
    }

    func updateUIView(_ pdfView: PDFView, context: Context) {
        if pdfView.document !== document {
            pdfView.document = document
        }

        // Navigate to requested page
        if let document = document,
           currentPage >= 0,
           currentPage < document.pageCount,
           let page = document.page(at: currentPage) {
            let currentVisiblePage = pdfView.currentPage
            if currentVisiblePage != page {
                pdfView.go(to: page)
            }
        }

        // Apply zoom scale
        let targetScale = pdfView.scaleFactorForSizeToFit * zoomScale
        if abs(pdfView.scaleFactor - targetScale) > 0.01 {
            pdfView.scaleFactor = targetScale
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    class Coordinator: NSObject {
        let parent: PDFViewRepresentable
        weak var pdfView: PDFView?

        init(parent: PDFViewRepresentable) {
            self.parent = parent
        }

        @objc func pageChanged(_ notification: Notification) {
            guard let pdfView = pdfView,
                  let currentPage = pdfView.currentPage,
                  let document = pdfView.document else { return }

            let pageIndex = document.index(for: currentPage)
            DispatchQueue.main.async {
                if self.parent.currentPage != pageIndex {
                    self.parent.currentPage = pageIndex
                }
            }
        }

        @objc func scaleChanged(_ notification: Notification) {
            guard let pdfView = pdfView else { return }
            let relativeScale = pdfView.scaleFactor / pdfView.scaleFactorForSizeToFit
            DispatchQueue.main.async {
                if abs(self.parent.zoomScale - relativeScale) > 0.01 {
                    self.parent.zoomScale = relativeScale
                }
            }
        }

        deinit {
            NotificationCenter.default.removeObserver(self)
        }
    }
}

// MARK: - PDF Thumbnail Representable

@available(iOS 15.0, *)
struct PDFThumbnailRepresentable: UIViewRepresentable {
    let page: PDFPage

    func makeUIView(context: Context) -> UIImageView {
        let imageView = UIImageView()
        imageView.contentMode = .scaleAspectFit
        imageView.backgroundColor = .white
        imageView.clipsToBounds = true
        return imageView
    }

    func updateUIView(_ imageView: UIImageView, context: Context) {
        let bounds = page.bounds(for: .mediaBox)
        let size = CGSize(width: 120, height: 120 * (bounds.height / bounds.width))
        imageView.image = page.thumbnail(of: size, for: .mediaBox)
    }
}

// MARK: - UIKit Hosting Controller

@available(iOS 15.0, *)
final class VisionProDocumentHostingController: UIHostingController<VisionProDocumentView> {

    init(url: URL, title: String? = nil) {
        super.init(rootView: VisionProDocumentView(url: url, title: title))
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()

        #if os(visionOS)
        // Request a larger window for document viewing on Vision Pro
        let docSize = CGSize(width: 1400, height: 1050)
        preferredContentSize = docSize
        view.backgroundColor = .clear
        #else
        if VisionProSupport.isVisionPro {
            let docSize = CGSize(width: 1400, height: 1050)
            preferredContentSize = docSize
            view.backgroundColor = .clear
        }
        #endif
    }
}

// MARK: - Preview

#if DEBUG
@available(iOS 15.0, *)
struct VisionProDocumentView_Previews: PreviewProvider {
    static var previews: some View {
        VisionProDocumentView(
            url: URL(string: "https://example.com/sample.pdf")!,
            title: "Loan Application - John Doe"
        )
        .previewDisplayName("Document Viewer")
    }
}
#endif
