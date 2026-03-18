import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../DocumentViewer.css', () => ({}));

import DocumentViewer from '../DocumentViewer';

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DocumentViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. Empty state — no document URL
  // -------------------------------------------------------------------------
  it('shows empty state when no documentUrl is provided', () => {
    render(<DocumentViewer documentUrl={null} mimeType="application/pdf" />);

    expect(screen.getByText('No document to display')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. PDF rendering
  // -------------------------------------------------------------------------
  it('renders an iframe for PDF documents', () => {
    render(
      <DocumentViewer
        documentUrl="https://example.com/doc.pdf"
        mimeType="application/pdf"
        fileName="paystub.pdf"
      />
    );

    const iframe = document.querySelector('iframe.pdf-viewer');
    expect(iframe).toBeInTheDocument();
    expect(iframe.src).toContain('https://example.com/doc.pdf');
    expect(iframe).toHaveAttribute('title', 'paystub.pdf');
  });

  // -------------------------------------------------------------------------
  // 3. Image rendering
  // -------------------------------------------------------------------------
  it('renders an img element for image documents', () => {
    render(
      <DocumentViewer
        documentUrl="https://example.com/doc.jpg"
        mimeType="image/jpeg"
        fileName="license.jpg"
      />
    );

    const img = screen.getByAlt('license.jpg');
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute('src', 'https://example.com/doc.jpg');
  });

  // -------------------------------------------------------------------------
  // 4. Unsupported file type
  // -------------------------------------------------------------------------
  it('shows unsupported format message for non-PDF non-image files', () => {
    render(
      <DocumentViewer
        documentUrl="https://example.com/data.xlsx"
        mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        fileName="data.xlsx"
      />
    );

    expect(screen.getByText('Preview not available for this file type')).toBeInTheDocument();
    expect(screen.getByText('Download File')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 5. Toolbar displays file name
  // -------------------------------------------------------------------------
  it('displays the file name in the toolbar', () => {
    render(
      <DocumentViewer
        documentUrl="https://example.com/w2.pdf"
        mimeType="application/pdf"
        fileName="W2_2026_Smith.pdf"
      />
    );

    expect(screen.getByText('W2_2026_Smith.pdf')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 6. Default file name when none provided
  // -------------------------------------------------------------------------
  it('shows "Document" as default when no fileName is provided', () => {
    render(
      <DocumentViewer
        documentUrl="https://example.com/unknown.pdf"
        mimeType="application/pdf"
      />
    );

    expect(screen.getByText('Document')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 7. Zoom in
  // -------------------------------------------------------------------------
  it('increases zoom level when zoom in button is clicked', () => {
    render(
      <DocumentViewer
        documentUrl="https://example.com/doc.pdf"
        mimeType="application/pdf"
        fileName="doc.pdf"
      />
    );

    expect(screen.getByText('100%')).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('Zoom In'));

    expect(screen.getByText('125%')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 8. Zoom out
  // -------------------------------------------------------------------------
  it('decreases zoom level when zoom out button is clicked', () => {
    render(
      <DocumentViewer
        documentUrl="https://example.com/doc.pdf"
        mimeType="application/pdf"
        fileName="doc.pdf"
      />
    );

    fireEvent.click(screen.getByTitle('Zoom Out'));

    expect(screen.getByText('75%')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 9. Zoom limits
  // -------------------------------------------------------------------------
  it('disables zoom out at minimum (50%) and zoom in at maximum (200%)', () => {
    render(
      <DocumentViewer
        documentUrl="https://example.com/doc.pdf"
        mimeType="application/pdf"
        fileName="doc.pdf"
      />
    );

    const zoomOut = screen.getByTitle('Zoom Out');
    const zoomIn = screen.getByTitle('Zoom In');

    // Zoom out to minimum
    fireEvent.click(zoomOut); // 75%
    fireEvent.click(zoomOut); // 50%
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(zoomOut).toBeDisabled();

    // Reset and zoom in to maximum
    fireEvent.click(screen.getByTitle('Reset View'));
    expect(screen.getByText('100%')).toBeInTheDocument();

    fireEvent.click(zoomIn); // 125%
    fireEvent.click(zoomIn); // 150%
    fireEvent.click(zoomIn); // 175%
    fireEvent.click(zoomIn); // 200%
    expect(screen.getByText('200%')).toBeInTheDocument();
    expect(zoomIn).toBeDisabled();
  });

  // -------------------------------------------------------------------------
  // 10. Rotate button for images
  // -------------------------------------------------------------------------
  it('shows rotate button only for image documents', () => {
    const { rerender } = render(
      <DocumentViewer
        documentUrl="https://example.com/doc.jpg"
        mimeType="image/jpeg"
        fileName="photo.jpg"
      />
    );

    expect(screen.getByTitle('Rotate')).toBeInTheDocument();

    // Rerender as PDF — rotate should not appear
    rerender(
      <DocumentViewer
        documentUrl="https://example.com/doc.pdf"
        mimeType="application/pdf"
        fileName="doc.pdf"
      />
    );

    expect(screen.queryByTitle('Rotate')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 11. Reset view
  // -------------------------------------------------------------------------
  it('resets zoom and rotation when reset button is clicked', () => {
    render(
      <DocumentViewer
        documentUrl="https://example.com/photo.jpg"
        mimeType="image/jpeg"
        fileName="photo.jpg"
      />
    );

    // Change zoom
    fireEvent.click(screen.getByTitle('Zoom In'));
    expect(screen.getByText('125%')).toBeInTheDocument();

    // Rotate
    fireEvent.click(screen.getByTitle('Rotate'));

    // Reset
    fireEvent.click(screen.getByTitle('Reset View'));

    expect(screen.getByText('100%')).toBeInTheDocument();
    // Rotation resets to 0 (no visible indicator, but container style should reset)
    const imageContainer = document.querySelector('.image-container');
    expect(imageContainer.style.transform).toContain('scale(1)');
    expect(imageContainer.style.transform).toContain('rotate(0deg)');
  });

  // -------------------------------------------------------------------------
  // 12. Open in new tab link
  // -------------------------------------------------------------------------
  it('has an open in new tab link pointing to the document URL', () => {
    render(
      <DocumentViewer
        documentUrl="https://example.com/report.pdf"
        mimeType="application/pdf"
        fileName="report.pdf"
      />
    );

    const link = screen.getByTitle('Open in New Tab');
    expect(link).toHaveAttribute('href', 'https://example.com/report.pdf');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  // -------------------------------------------------------------------------
  // 13. Loading state
  // -------------------------------------------------------------------------
  it('shows loading state before document loads', () => {
    render(
      <DocumentViewer
        documentUrl="https://example.com/doc.pdf"
        mimeType="application/pdf"
        fileName="doc.pdf"
      />
    );

    expect(screen.getByText('Loading document...')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 14. File extension-based type detection for PDF
  // -------------------------------------------------------------------------
  it('detects PDF from file extension when mimeType is not set', () => {
    render(
      <DocumentViewer
        documentUrl="https://example.com/document.pdf"
        mimeType={null}
        fileName="document.pdf"
      />
    );

    // Should render iframe for PDF
    const iframe = document.querySelector('iframe.pdf-viewer');
    expect(iframe).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 15. File extension-based type detection for images
  // -------------------------------------------------------------------------
  it('detects image type from file extension when mimeType is not set', () => {
    render(
      <DocumentViewer
        documentUrl="https://example.com/scan.png"
        mimeType={null}
        fileName="scan.png"
      />
    );

    // Should render img, not iframe
    const img = screen.getByAlt('scan.png');
    expect(img).toBeInTheDocument();
    expect(document.querySelector('iframe')).not.toBeInTheDocument();
  });
});
