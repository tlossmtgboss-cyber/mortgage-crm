import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../SmartDocumentUpload.css', () => ({}));
vi.mock('../RejectionExplainer.css', () => ({}));
vi.mock('../FreshnessIndicator.css', () => ({}));
vi.mock('../../document-review/DocumentReviewModal.css', () => ({}));
vi.mock('../../document-review/DocumentViewer.css', () => ({}));

// Mock smartDocsApi
const mockUploadDocument = vi.fn();
vi.mock('../../../services/smartDocsApi', () => ({
  smartDocsAPI: {
    uploadDocument: (...args) => mockUploadDocument(...args),
  },
}));

// Mock child components to isolate unit tests
vi.mock('../RejectionExplainer', () => ({
  default: ({ category, reason }) => (
    <div data-testid="rejection-explainer" data-category={category}>
      {reason}
    </div>
  ),
}));

vi.mock('../FreshnessIndicator', () => ({
  default: ({ status, daysUntilExpiration }) => (
    <div data-testid="freshness-indicator" data-status={status}>
      {daysUntilExpiration && `${daysUntilExpiration} days`}
    </div>
  ),
}));

vi.mock('../../document-review/DocumentReviewModal', () => ({
  default: ({ documentId, onClose, onApprove }) => (
    <div data-testid="review-modal" data-doc-id={documentId}>
      <button onClick={onClose}>Close Modal</button>
      <button onClick={() => onApprove({ documentId })}>Approve Modal</button>
    </div>
  ),
}));

import SmartDocumentUpload from '../SmartDocumentUpload';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const defaultProps = {
  loanId: 'loan-1',
  borrowerId: 'borrower-1',
  onUploadComplete: vi.fn(),
  onUploadError: vi.fn(),
  onDocumentApproved: vi.fn(),
};

function createFile(name = 'paystub.pdf', size = 1024, type = 'application/pdf') {
  const content = new ArrayBuffer(size);
  return new File([content], name, { type });
}

function createOversizedFile(name = 'huge.pdf', sizeMB = 25) {
  return createFile(name, sizeMB * 1024 * 1024);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SmartDocumentUpload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. Idle state rendering
  // -------------------------------------------------------------------------
  it('renders the drop zone in idle state', () => {
    render(<SmartDocumentUpload {...defaultProps} />);

    expect(screen.getByText('Drag & drop your document here')).toBeInTheDocument();
    expect(screen.getByText('or click to browse')).toBeInTheDocument();
    expect(screen.getByText(/Accepted: PDF, JPG, PNG/)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. Document guidelines
  // -------------------------------------------------------------------------
  it('displays document upload guidelines', () => {
    render(<SmartDocumentUpload {...defaultProps} />);

    expect(screen.getByText('Document Guidelines')).toBeInTheDocument();
    expect(screen.getByText(/Upload the original PDF document/)).toBeInTheDocument();
    expect(screen.getByText(/Screenshots will be automatically rejected/)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 3. File type validation — reject unsupported types
  // -------------------------------------------------------------------------
  it('shows error for unsupported file types', async () => {
    render(<SmartDocumentUpload {...defaultProps} />);

    const input = document.querySelector('input[type="file"]');
    const badFile = createFile('malware.exe', 1024, 'application/x-msdownload');

    fireEvent.change(input, { target: { files: [badFile] } });

    await waitFor(() => {
      expect(screen.getByText(/File type not accepted/)).toBeInTheDocument();
    });

    // Upload should NOT have been called
    expect(mockUploadDocument).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 4. File size validation — reject oversized files
  // -------------------------------------------------------------------------
  it('shows error for files exceeding max size', async () => {
    render(<SmartDocumentUpload {...defaultProps} maxSizeMB={20} />);

    const input = document.querySelector('input[type="file"]');
    const hugeFile = createOversizedFile('huge.pdf', 25);

    fireEvent.change(input, { target: { files: [hugeFile] } });

    await waitFor(() => {
      expect(screen.getByText(/File is too large/)).toBeInTheDocument();
    });

    expect(mockUploadDocument).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 5. Successful upload flow
  // -------------------------------------------------------------------------
  it('handles successful upload and shows result', async () => {
    mockUploadDocument.mockResolvedValue({
      document_id: 'doc-123',
      status: 'APPROVED',
      file_name: 'paystub.pdf',
      analysis: {
        screenshot: { is_screenshot: false },
        dates: { primary_date: '2026-03-01' },
        freshness: { status: 'fresh', days_until_expiration: 25 },
      },
    });

    render(<SmartDocumentUpload {...defaultProps} />);

    const input = document.querySelector('input[type="file"]');
    const file = createFile('paystub.pdf');

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText('Document Accepted')).toBeInTheDocument();
    });

    expect(defaultProps.onUploadComplete).toHaveBeenCalledTimes(1);
    expect(defaultProps.onUploadError).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 6. Upload progress state
  // -------------------------------------------------------------------------
  it('shows uploading state while upload is in progress', async () => {
    // Never-resolving promise to freeze in uploading state
    mockUploadDocument.mockReturnValue(new Promise(() => {}));

    render(<SmartDocumentUpload {...defaultProps} />);

    const input = document.querySelector('input[type="file"]');
    const file = createFile('w2.pdf');

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/Uploading w2.pdf/)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 7. Upload error handling
  // -------------------------------------------------------------------------
  it('shows error state when upload fails', async () => {
    mockUploadDocument.mockRejectedValue(new Error('Network error'));

    render(<SmartDocumentUpload {...defaultProps} />);

    const input = document.querySelector('input[type="file"]');
    const file = createFile('bank_statement.pdf');

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });

    expect(defaultProps.onUploadError).toHaveBeenCalledTimes(1);
  });

  // -------------------------------------------------------------------------
  // 8. Try Again resets to idle
  // -------------------------------------------------------------------------
  it('resets to idle state when Try Again is clicked after error', async () => {
    mockUploadDocument.mockRejectedValue(new Error('Timeout'));

    render(<SmartDocumentUpload {...defaultProps} />);

    const input = document.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [createFile()] } });

    await waitFor(() => {
      expect(screen.getByText('Timeout')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Try Again'));

    expect(screen.getByText('Drag & drop your document here')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 9. Rejected document shows rejection explainer
  // -------------------------------------------------------------------------
  it('shows rejection explainer when document is rejected', async () => {
    mockUploadDocument.mockResolvedValue({
      document_id: 'doc-456',
      status: 'REJECTED',
      rejection_category: 'SCREENSHOT',
      rejection_reason: 'Document appears to be a screenshot of a bank app',
      fix_instructions: 'Please download the PDF from your bank website',
      analysis: {
        screenshot: { is_screenshot: true, confidence: 0.95 },
      },
    });

    render(<SmartDocumentUpload {...defaultProps} />);

    const input = document.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [createFile('screenshot.png')] } });

    await waitFor(() => {
      expect(screen.getByText('Document Rejected')).toBeInTheDocument();
    });
    expect(screen.getByTestId('rejection-explainer')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 10. Needs Review status display
  // -------------------------------------------------------------------------
  it('shows Review Required when document needs review', async () => {
    mockUploadDocument.mockResolvedValue({
      document_id: 'doc-789',
      status: 'NEEDS_REVIEW',
      analysis: {
        screenshot: { is_screenshot: false },
        freshness: { status: 'expiring_soon', days_until_expiration: 5 },
      },
    });

    render(<SmartDocumentUpload {...defaultProps} />);

    const input = document.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [createFile()] } });

    await waitFor(() => {
      expect(screen.getByText('Review Required')).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 11. Drag and drop interaction
  // -------------------------------------------------------------------------
  it('applies dragging class on drag over and removes on drag leave', () => {
    render(<SmartDocumentUpload {...defaultProps} />);

    const dropZone = document.querySelector('.drop-zone');

    fireEvent.dragOver(dropZone, { dataTransfer: { files: [] } });
    expect(dropZone.classList.contains('dragging')).toBe(true);

    fireEvent.dragLeave(dropZone, { dataTransfer: { files: [] } });
    expect(dropZone.classList.contains('dragging')).toBe(false);
  });

  // -------------------------------------------------------------------------
  // 12. Auto-open review modal on successful upload
  // -------------------------------------------------------------------------
  it('auto-opens review modal after successful upload', async () => {
    mockUploadDocument.mockResolvedValue({
      document_id: 'doc-auto',
      status: 'APPROVED',
      file_name: 'w2_2026.pdf',
      analysis: {},
    });

    render(<SmartDocumentUpload {...defaultProps} autoOpenReview={true} />);

    const input = document.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [createFile('w2_2026.pdf')] } });

    await waitFor(() => {
      expect(screen.getByTestId('review-modal')).toBeInTheDocument();
    });
    expect(screen.getByTestId('review-modal')).toHaveAttribute('data-doc-id', 'doc-auto');
  });

  // -------------------------------------------------------------------------
  // 13. Upload Another Document resets state
  // -------------------------------------------------------------------------
  it('resets to idle when Upload Another Document is clicked', async () => {
    mockUploadDocument.mockResolvedValue({
      document_id: 'doc-done',
      status: 'APPROVED',
      analysis: {},
    });

    render(<SmartDocumentUpload {...defaultProps} autoOpenReview={false} />);

    const input = document.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [createFile()] } });

    await waitFor(() => {
      expect(screen.getByText('Document Accepted')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Upload Another Document'));

    expect(screen.getByText('Drag & drop your document here')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 14. Screenshot detection display
  // -------------------------------------------------------------------------
  it('shows screenshot detection result in upload analysis', async () => {
    mockUploadDocument.mockResolvedValue({
      document_id: 'doc-ss',
      status: 'REJECTED',
      rejection_category: 'SCREENSHOT',
      rejection_reason: 'Screenshot detected',
      analysis: {
        screenshot: { is_screenshot: true, confidence: 0.92 },
      },
    });

    render(<SmartDocumentUpload {...defaultProps} />);

    const input = document.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [createFile('screen.png')] } });

    await waitFor(() => {
      expect(screen.getByText(/Screenshot detected/)).toBeInTheDocument();
      expect(screen.getByText(/92% confidence/)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 15. Passes correct params to upload API
  // -------------------------------------------------------------------------
  it('passes loanId, borrowerId, requestId, and docType to API', async () => {
    mockUploadDocument.mockResolvedValue({
      document_id: 'doc-params',
      status: 'APPROVED',
      analysis: {},
    });

    render(
      <SmartDocumentUpload
        loanId="loan-99"
        borrowerId="borrower-55"
        requestId="req-7"
        docType="PAYSTUB"
        onUploadComplete={vi.fn()}
        autoOpenReview={false}
      />
    );

    const input = document.querySelector('input[type="file"]');
    const file = createFile('pay.pdf');
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(mockUploadDocument).toHaveBeenCalledWith(
        file,
        'loan-99',
        'borrower-55',
        'req-7',
        'PAYSTUB'
      );
    });
  });
});
