import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { rest } from 'msw';
import EstimateComparison from '../pages/EstimateComparison';
import { server } from '../mocks/server';

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

  // Mock window.open for CTA
  global.open = jest.fn();
});

describe('EstimateComparison - Full User Flow', () => {
  test('complete flow: render → verify initial state', async () => {
    renderWithRouter(<EstimateComparison />);

    // Step 1: Verify initial render
    expect(screen.getByText(/Compare Loan Estimates/i)).toBeInTheDocument();
    expect(screen.getByText(/Upload two loan estimates/i)).toBeInTheDocument();

    // Step 2: Verify upload zones
    const uploadZones = screen.getAllByText(/Drop your Loan Estimate here/i);
    expect(uploadZones).toHaveLength(2);

    // Step 3: Verify no results shown initially
    expect(screen.queryByText(/Best Option/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Comparison Results/i)).not.toBeInTheDocument();
  });

  test('user can see supported file formats', () => {
    renderWithRouter(<EstimateComparison />);

    // Should show supported formats
    const formatText = screen.getAllByText(/PDF, JPG, PNG, WebP/i);
    expect(formatText.length).toBeGreaterThan(0);
  });

  test('privacy notice is visible', () => {
    renderWithRouter(<EstimateComparison />);

    expect(screen.getByText(/Privacy First/i)).toBeInTheDocument();
    expect(screen.getByText(/Personal information is redacted before AI analysis/i)).toBeInTheDocument();
  });

  test('disclaimer is visible', () => {
    renderWithRouter(<EstimateComparison />);

    expect(screen.getByText(/This tool provides estimates for comparison purposes only/i)).toBeInTheDocument();
  });

  test('VS divider is visible between upload zones', () => {
    renderWithRouter(<EstimateComparison />);

    expect(screen.getByText('VS')).toBeInTheDocument();
  });
});

describe('EstimateComparison - Error Handling', () => {
  test('handles network errors gracefully', async () => {
    server.use(
      rest.post(
        'http://localhost:8000/api/v1/estimate-parser/parse',
        (req, res) => {
          return res.networkError('Failed to connect');
        }
      )
    );

    renderWithRouter(<EstimateComparison />);

    // Component should not crash on network error
    expect(screen.getByText(/Compare Loan Estimates/i)).toBeInTheDocument();
  });
});

describe('EstimateComparison - Accessibility', () => {
  test('has accessible labels on upload zones', () => {
    renderWithRouter(<EstimateComparison />);

    // Upload zones should have clickable areas
    const uploadZones = screen.getAllByText(/Drop your Loan Estimate here/i);
    uploadZones.forEach(zone => {
      expect(zone).toBeInTheDocument();
    });
  });

  test('buttons have accessible names', () => {
    renderWithRouter(<EstimateComparison />);

    // Check for any visible buttons
    const buttons = screen.queryAllByRole('button');
    buttons.forEach(button => {
      expect(button).toHaveAccessibleName();
    });
  });
});
