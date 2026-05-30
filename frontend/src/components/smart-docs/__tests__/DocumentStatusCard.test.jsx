import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../DocumentStatusCard.css', () => ({}));
vi.mock('../FreshnessIndicator.css', () => ({}));

// Mock FreshnessIndicator
vi.mock('../FreshnessIndicator', () => ({
  default: ({ status, daysUntilExpiration, expiresAt, compact }) => (
    <div data-testid="freshness-indicator" data-status={status} data-compact={compact}>
      {daysUntilExpiration !== null && daysUntilExpiration !== undefined
        ? `${daysUntilExpiration} days`
        : ''}
    </div>
  ),
}));

import DocumentStatusCard from '../DocumentStatusCard.jsx';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeDocument(overrides = {}) {
  return {
    id: 'doc-1',
    file_name: 'paystub_march_2026.pdf',
    doc_type: 'PAYSTUB',
    status: 'APPROVED',
    decision: null,
    rejection_category: null,
    rejection_reason: null,
    screenshot_detection: null,
    dates: null,
    created_at: new Date(Date.now() - 3600000).toISOString(), // 1 hour ago
    reviewed_at: null,
    reviewed_by: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DocumentStatusCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. Basic rendering with approved status
  // -------------------------------------------------------------------------
  it('renders file name and approved status badge', () => {
    const doc = makeDocument();
    render(<DocumentStatusCard document={doc} />);

    expect(screen.getByText('paystub_march_2026.pdf')).toBeInTheDocument();
    expect(screen.getByText('Approved')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. Document type formatting
  // -------------------------------------------------------------------------
  it('formats document type from enum to readable text', () => {
    const doc = makeDocument({ doc_type: 'BANK_STATEMENT' });
    render(<DocumentStatusCard document={doc} />);

    expect(screen.getByText('Bank Statement')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 3. Status badge — REJECTED
  // -------------------------------------------------------------------------
  it('renders Rejected status badge with rejection details', () => {
    const doc = makeDocument({
      status: 'REJECTED',
      rejection_category: 'SCREENSHOT',
      rejection_reason: 'This appears to be a screenshot of a mobile banking app.',
    });
    render(<DocumentStatusCard document={doc} />);

    expect(screen.getByText('Rejected')).toBeInTheDocument();
    expect(screen.getByText('Screenshot Detected')).toBeInTheDocument();
    expect(screen.getByText('This appears to be a screenshot of a mobile banking app.')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 4. Status badge — NEEDS_REVIEW
  // -------------------------------------------------------------------------
  it('renders Needs Review status badge', () => {
    const doc = makeDocument({ status: 'NEEDS_REVIEW' });
    render(<DocumentStatusCard document={doc} />);

    expect(screen.getByText('Needs Review')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 5. Status badge — PROCESSING
  // -------------------------------------------------------------------------
  it('renders Processing status badge', () => {
    const doc = makeDocument({ status: 'PROCESSING' });
    render(<DocumentStatusCard document={doc} />);

    expect(screen.getByText('Processing')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 6. Status badge — EXPIRED
  // -------------------------------------------------------------------------
  it('renders Expired status badge', () => {
    const doc = makeDocument({ status: 'EXPIRED' });
    render(<DocumentStatusCard document={doc} />);

    expect(screen.getByText('Expired')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 7. Screenshot detection alert
  // -------------------------------------------------------------------------
  it('shows screenshot detection alert when is_screenshot is true', () => {
    const doc = makeDocument({
      status: 'REJECTED',
      screenshot_detection: {
        is_screenshot: true,
        confidence: 0.93,
      },
    });
    render(<DocumentStatusCard document={doc} />);

    expect(screen.getByText('Screenshot Detected')).toBeInTheDocument();
    expect(screen.getByText(/93% confidence/)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 8. No screenshot alert when not detected
  // -------------------------------------------------------------------------
  it('does not show screenshot alert when is_screenshot is false', () => {
    const doc = makeDocument({
      screenshot_detection: {
        is_screenshot: false,
        confidence: 0.1,
      },
    });
    render(<DocumentStatusCard document={doc} />);

    expect(screen.queryByText('Screenshot Detected')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 9. Document dates display
  // -------------------------------------------------------------------------
  it('renders document date when dates are provided', () => {
    const doc = makeDocument({
      dates: {
        doc_date: '2026-03-01',
        expires_at: '2026-04-01',
        days_until_expiration: 14,
        is_expired: false,
      },
    });
    render(<DocumentStatusCard document={doc} />);

    expect(screen.getByText('Document Date:')).toBeInTheDocument();
    // FreshnessIndicator is mocked
    expect(screen.getByTestId('freshness-indicator')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 10. Reviewed-by metadata
  // -------------------------------------------------------------------------
  it('shows reviewer name when document has been reviewed', () => {
    const doc = makeDocument({
      reviewed_at: new Date().toISOString(),
      reviewed_by: 'Jane Smith',
    });
    render(<DocumentStatusCard document={doc} />);

    expect(screen.getByText(/Reviewed by Jane Smith/)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 11. Auto-reviewed by system
  // -------------------------------------------------------------------------
  it('shows "Auto" for system-reviewed documents', () => {
    const doc = makeDocument({
      reviewed_at: new Date().toISOString(),
      reviewed_by: 'SYSTEM',
    });
    render(<DocumentStatusCard document={doc} />);

    expect(screen.getByText(/Reviewed by Auto/)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 12. Action buttons — View
  // -------------------------------------------------------------------------
  it('calls onView when View button is clicked', () => {
    const onView = vi.fn();
    const doc = makeDocument();
    render(<DocumentStatusCard document={doc} onView={onView} />);

    fireEvent.click(screen.getByText('View'));

    expect(onView).toHaveBeenCalledWith(doc);
  });

  // -------------------------------------------------------------------------
  // 13. Action buttons — Review only visible for NEEDS_REVIEW
  // -------------------------------------------------------------------------
  it('shows Review button only when status is NEEDS_REVIEW', () => {
    const onReview = vi.fn();

    const { rerender } = render(
      <DocumentStatusCard
        document={makeDocument({ status: 'APPROVED' })}
        onReview={onReview}
      />
    );

    expect(screen.queryByText('Review')).not.toBeInTheDocument();

    rerender(
      <DocumentStatusCard
        document={makeDocument({ status: 'NEEDS_REVIEW' })}
        onReview={onReview}
      />
    );

    expect(screen.getByText('Review')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Review'));
    expect(onReview).toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 14. Action buttons — Download
  // -------------------------------------------------------------------------
  it('calls onDownload when Download button is clicked', () => {
    const onDownload = vi.fn();
    const doc = makeDocument();
    render(<DocumentStatusCard document={doc} onDownload={onDownload} />);

    fireEvent.click(screen.getByText('Download'));

    expect(onDownload).toHaveBeenCalledWith(doc);
  });

  // -------------------------------------------------------------------------
  // 15. showActions=false hides all action buttons
  // -------------------------------------------------------------------------
  it('hides all action buttons when showActions is false', () => {
    const doc = makeDocument({ status: 'NEEDS_REVIEW' });
    render(
      <DocumentStatusCard
        document={doc}
        showActions={false}
        onView={vi.fn()}
        onReview={vi.fn()}
        onDownload={vi.fn()}
      />
    );

    expect(screen.queryByText('View')).not.toBeInTheDocument();
    expect(screen.queryByText('Review')).not.toBeInTheDocument();
    expect(screen.queryByText('Download')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 16. File name truncation
  // -------------------------------------------------------------------------
  it('truncates long file names', () => {
    const doc = makeDocument({
      file_name: 'very_long_filename_that_exceeds_the_thirty_character_limit_for_display.pdf',
    });
    render(<DocumentStatusCard document={doc} />);

    // The truncated name should end with ...pdf and be shorter
    const fileNameEl = document.querySelector('.file-name');
    expect(fileNameEl.textContent.length).toBeLessThan(
      'very_long_filename_that_exceeds_the_thirty_character_limit_for_display.pdf'.length
    );
    expect(fileNameEl.textContent).toContain('...');
  });

  // -------------------------------------------------------------------------
  // 17. Rejection categories format correctly
  // -------------------------------------------------------------------------
  it('formats different rejection categories correctly', () => {
    const categories = [
      { category: 'EXPIRED', expected: 'Document Expired' },
      { category: 'POOR_QUALITY', expected: 'Poor Quality' },
      { category: 'INCOMPLETE', expected: 'Incomplete Document' },
      { category: 'WRONG_TYPE', expected: 'Wrong Document Type' },
    ];

    categories.forEach(({ category, expected }) => {
      const { unmount } = render(
        <DocumentStatusCard
          document={makeDocument({
            status: 'REJECTED',
            rejection_category: category,
            rejection_reason: 'Test reason',
          })}
        />
      );

      expect(screen.getByText(expected)).toBeInTheDocument();
      unmount();
    });
  });

  // -------------------------------------------------------------------------
  // 18. Document status transitions — pending to approved
  // -------------------------------------------------------------------------
  it('updates display when document status changes from pending to approved', () => {
    const doc = makeDocument({ status: 'NEEDS_REVIEW' });
    const { rerender } = render(
      <DocumentStatusCard document={doc} onReview={vi.fn()} />
    );

    expect(screen.getByText('Needs Review')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();

    // Simulate status transition
    const updatedDoc = makeDocument({ status: 'APPROVED', reviewed_at: new Date().toISOString(), reviewed_by: 'LO User' });
    rerender(<DocumentStatusCard document={updatedDoc} onReview={vi.fn()} />);

    expect(screen.getByText('Approved')).toBeInTheDocument();
    expect(screen.queryByText('Needs Review')).not.toBeInTheDocument();
    // Review button should be gone since status is no longer NEEDS_REVIEW
    expect(screen.queryByText('Review')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 19. Document status transitions — pending to rejected
  // -------------------------------------------------------------------------
  it('updates display when document status changes from pending to rejected', () => {
    const doc = makeDocument({ status: 'NEEDS_REVIEW' });
    const { rerender } = render(<DocumentStatusCard document={doc} />);

    expect(screen.getByText('Needs Review')).toBeInTheDocument();

    const rejectedDoc = makeDocument({
      status: 'REJECTED',
      rejection_category: 'EXPIRED',
      rejection_reason: 'Bank statement is 90 days old',
    });
    rerender(<DocumentStatusCard document={rejectedDoc} />);

    expect(screen.getByText('Rejected')).toBeInTheDocument();
    expect(screen.getByText('Bank statement is 90 days old')).toBeInTheDocument();
  });
});
