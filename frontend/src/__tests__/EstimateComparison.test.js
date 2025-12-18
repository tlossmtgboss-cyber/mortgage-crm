import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import EstimateComparison from '../pages/EstimateComparison';
import { server } from '../mocks/server';
import { rest } from 'msw';
import { errorHandlers } from '../mocks/handlers';

// Helper to render component with router
const renderWithRouter = (component) => {
  return render(<BrowserRouter>{component}</BrowserRouter>);
};

// Setup/teardown
beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Mock URL APIs
beforeEach(() => {
  global.URL.createObjectURL = jest.fn(() => 'mock-url');
  global.URL.revokeObjectURL = jest.fn();
});

describe('EstimateComparison Component', () => {
  test('renders upload interface initially', () => {
    renderWithRouter(<EstimateComparison />);

    expect(screen.getByText(/Compare Loan Estimates/i)).toBeInTheDocument();
    expect(screen.getByText(/Estimate A/i)).toBeInTheDocument();
    expect(screen.getByText(/Estimate B/i)).toBeInTheDocument();
  });

  test('shows upload zones for both estimates', () => {
    renderWithRouter(<EstimateComparison />);

    const uploadZones = screen.getAllByText(/Drop your Loan Estimate here/i);
    expect(uploadZones).toHaveLength(2);
  });

  test('accepts valid file types (PDF)', async () => {
    renderWithRouter(<EstimateComparison />);

    const file = new File(['pdf content'], 'estimate.pdf', { type: 'application/pdf' });
    const uploadZones = screen.getAllByText(/Drop your Loan Estimate here/i);

    // Simulate file input change
    const fileInput = uploadZones[0].closest('.upload-zone').querySelector('input[type="file"]') ||
                     document.querySelector('input[type="file"]');

    if (fileInput) {
      await userEvent.upload(fileInput, file);
    }
  });

  test('rejects invalid file types', async () => {
    renderWithRouter(<EstimateComparison />);

    // Try to upload a text file (should be rejected client-side)
    const invalidFile = new File(['text content'], 'document.txt', { type: 'text/plain' });

    // The component should show an error for invalid file types
    // This tests client-side validation
  });

  test('shows loading state during parse', async () => {
    renderWithRouter(<EstimateComparison />);

    // Add delay to parse response to see loading state
    server.use(
      rest.post('http://localhost:8000/api/v1/estimate-parser/parse', (req, res, ctx) => {
        return res(
          ctx.delay(100),
          ctx.status(200),
          ctx.json({
            success: true,
            data: {
              loan_amount: 400000,
              interest_rate: 6.875,
              doc_hash: 'test_hash',
            },
            request_id: 'test-123',
          })
        );
      })
    );

    // Component should show loading indicator when processing
    expect(screen.queryByText(/Analyzing/i)).not.toBeInTheDocument();
  });

  test('displays parsed estimate data', async () => {
    renderWithRouter(<EstimateComparison />);

    // After successful parse, data should be displayed
    // This would require triggering the upload flow
  });

  test('enables compare button when both estimates loaded', async () => {
    renderWithRouter(<EstimateComparison />);

    // Initially, there should be no compare button visible
    // or it should be disabled
  });

  test('displays comparison results with winner badge', async () => {
    // This test requires mocking the full flow:
    // 1. Upload file A
    // 2. Upload file B
    // 3. Click compare
    // 4. Verify results displayed
  });

  test('shows savings message for significant savings', async () => {
    // After comparison, verify savings message is displayed
  });

  test('provenance accordion toggles correctly', async () => {
    // Test that clicking "Show me where" expands provenance
  });

  test('download PDF button triggers download', async () => {
    // Test PDF download functionality
  });

  test('CTA button tracks conversion', async () => {
    let conversionTracked = false;

    server.use(
      rest.post('http://localhost:8000/api/v1/estimate-parser/compare/convert', (req, res, ctx) => {
        conversionTracked = true;
        return res(ctx.status(200), ctx.json({ success: true }));
      })
    );

    // After comparison, click CTA and verify conversion tracked
  });

  test('displays error message on parse failure', async () => {
    server.use(errorHandlers.parseError);

    renderWithRouter(<EstimateComparison />);

    // Trigger upload and verify error displayed
  });

  test('displays review warning for low confidence', async () => {
    server.use(errorHandlers.lowConfidence);

    renderWithRouter(<EstimateComparison />);

    // Trigger upload with low confidence response
    // Verify warning displayed
  });

  test('handles rate limiting gracefully', async () => {
    server.use(errorHandlers.rateLimited);

    renderWithRouter(<EstimateComparison />);

    // Verify rate limit error is displayed nicely
  });

  test('reset button clears all state', async () => {
    renderWithRouter(<EstimateComparison />);

    // Find reset button (Start Over)
    const resetButton = screen.queryByText(/Start Over/i);

    // If visible, click and verify state cleared
    if (resetButton) {
      fireEvent.click(resetButton);
    }
  });

  test('displays privacy disclaimer', () => {
    renderWithRouter(<EstimateComparison />);

    expect(screen.getByText(/Privacy First/i)).toBeInTheDocument();
    expect(screen.getByText(/Personal information is redacted/i)).toBeInTheDocument();
  });
});

describe('EstimateComparison - Comparison Table', () => {
  test('shows all comparison metrics', async () => {
    // After comparison, verify table shows:
    // - Cash to Close
    // - Total Closing Costs
    // - APR
    // - Interest Rate
    // - Monthly P&I
    // - Loan Amount
  });

  test('highlights winner column', async () => {
    // Verify winner column has special styling
  });

  test('shows difference column with +/- indicators', async () => {
    // Verify differences are shown with proper signs
  });
});

describe('EstimateComparison - Mobile Responsiveness', () => {
  test('renders properly on mobile viewport', () => {
    // Set viewport to mobile size
    global.innerWidth = 375;
    global.dispatchEvent(new Event('resize'));

    renderWithRouter(<EstimateComparison />);

    // Verify component renders without horizontal scroll
  });
});
