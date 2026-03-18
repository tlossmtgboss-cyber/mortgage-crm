import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../PartnerClientDetail.css', () => ({}));

// Mock react-router-dom
const mockNavigate = vi.fn();
const mockUseParams = vi.fn();
vi.mock('react-router-dom', () => ({
  useParams: () => mockUseParams(),
  useNavigate: () => mockNavigate,
}));

// Mock sub-components that are not under test
vi.mock('../../components/MilestoneProgressTracker', () => ({
  default: ({ currentStatus }) => (
    <div data-testid="milestone-tracker">{currentStatus}</div>
  ),
}));

vi.mock('../../components/PreApprovalLetterModal', () => ({
  default: ({ isOpen, onClose }) =>
    isOpen ? (
      <div data-testid="pre-approval-modal">
        <button onClick={onClose}>Close Modal</button>
      </div>
    ) : null,
}));

vi.mock('../../services/api', () => ({
  activitiesAPI: {
    getAll: vi.fn(),
  },
}));

vi.mock('../../utils/toast', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
  },
}));

import PartnerClientDetail from '../PartnerClientDetail';
import { activitiesAPI } from '../../services/api';
import { toast } from '../../utils/toast';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockFetch = vi.fn();

function mockResponse(body, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

const sampleClient = {
  id: 42,
  name: 'Sarah Johnson',
  borrower_name: 'Sarah Johnson',
  first_name: 'Sarah',
  last_name: 'Johnson',
  email: 'sarah.johnson@example.com',
  phone: '5551234567',
  stage: 'Pre-Approved',
  loan_amount: 425000,
  loan_type: 'Conventional',
  property_type: 'Single Family',
  address: '123 Main St',
  city: 'Austin',
  state: 'TX',
  zip_code: '78701',
  credit_score: 720,
  created_at: '2026-01-15T10:00:00Z',
  expected_close_date: '2026-04-15',
  purchase_price: 500000,
  down_payment: 75000,
  interest_rate: 6.5,
  loan_term: 30,
  assigned_user: {
    name: 'Timothy Loss',
    email: 'tloss@lender.com',
    phone: '5559876543',
  },
};

const sampleActivities = [
  {
    id: 1,
    type: 'Call',
    content: 'Discussed pre-approval options',
    created_at: '2026-03-10T14:00:00Z',
    user_name: 'Timothy Loss',
  },
  {
    id: 2,
    type: 'Email',
    content: 'Sent rate comparison document',
    created_at: '2026-03-08T09:00:00Z',
    user_name: 'Timothy Loss',
  },
  {
    id: 3,
    type: 'Note',
    content: 'Client prefers email communication',
    created_at: '2026-03-05T16:30:00Z',
    user_name: 'Sarah AI',
  },
];

/**
 * Set up fetch and API mocks for a successful page load.
 */
function setupSuccessfulLoad() {
  // Mock localStorage
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => {
    if (key === 'token') return 'mock-jwt-token';
    if (key === 'partnerToken') return null;
    return null;
  });

  // Mock the leads API call (JWT path)
  mockFetch.mockImplementation((url, options) => {
    if (url.includes(`/api/v1/leads/42`)) {
      return mockResponse(sampleClient);
    }
    if (url.includes('/stage-history')) {
      return mockResponse({
        stage_history: [
          { id: 1, to_stage: 'qualified', changed_at: '2026-02-01T10:00:00Z' },
          { id: 2, to_stage: 'pre_approved', changed_at: '2026-02-15T14:00:00Z' },
        ],
      });
    }
    if (url.includes('/chat-messages')) {
      return mockResponse({ messages: [] });
    }
    if (url.includes('/smart-docs/queue')) {
      return mockResponse([]);
    }
    if (url.includes('/conditions')) {
      return mockResponse({ conditions: [] });
    }
    return mockResponse({});
  });

  activitiesAPI.getAll.mockResolvedValue(sampleActivities);
}

async function renderPage(params = { partnerId: 'p1', clientId: '42' }) {
  mockUseParams.mockReturnValue(params);
  let result;
  await act(async () => {
    result = render(<PartnerClientDetail />);
  });
  return result;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PartnerClientDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = mockFetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -- Loading State --

  it('displays a loading spinner while fetching client data', async () => {
    mockUseParams.mockReturnValue({ partnerId: 'p1', clientId: '42' });
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('mock-jwt');

    // Never resolve the fetch so loading stays visible
    mockFetch.mockReturnValue(new Promise(() => {}));
    activitiesAPI.getAll.mockReturnValue(new Promise(() => {}));

    render(<PartnerClientDetail />);
    expect(screen.getByText('Loading client details...')).toBeInTheDocument();
  });

  // -- Error State --

  it('displays an error message when API returns 404', async () => {
    mockUseParams.mockReturnValue({ partnerId: 'p1', clientId: '999' });
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => {
      if (key === 'token') return 'mock-jwt';
      return null;
    });

    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/v1/leads/999')) {
        return mockResponse({ detail: 'Not found' }, 404);
      }
      return mockResponse({});
    });
    activitiesAPI.getAll.mockResolvedValue([]);

    await renderPage({ partnerId: 'p1', clientId: '999' });

    await waitFor(() => {
      expect(screen.getByText('Unable to Load')).toBeInTheDocument();
      expect(screen.getByText('Client not found.')).toBeInTheDocument();
    });
  });

  it('shows Go Back button on error and navigates on click', async () => {
    mockUseParams.mockReturnValue({ partnerId: 'p1', clientId: '999' });
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => {
      if (key === 'token') return 'mock-jwt';
      return null;
    });
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/v1/leads/999')) {
        return mockResponse({}, 404);
      }
      return mockResponse({});
    });
    activitiesAPI.getAll.mockResolvedValue([]);

    await renderPage({ partnerId: 'p1', clientId: '999' });

    await waitFor(() => {
      expect(screen.getByText('Go Back')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Go Back'));
    expect(mockNavigate).toHaveBeenCalledWith(-1);
  });

  // -- Contact Information Display --

  it('displays borrower name in the header', async () => {
    setupSuccessfulLoad();
    await renderPage();

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Sarah Johnson');
    });
  });

  it('displays borrower email and phone in the contact card', async () => {
    setupSuccessfulLoad();
    await renderPage();

    await waitFor(() => {
      expect(screen.getByText('sarah.johnson@example.com')).toBeInTheDocument();
    });

    // Phone should be formatted as (555) 123-4567
    expect(screen.getByText('(555) 123-4567')).toBeInTheDocument();
  });

  it('displays loan officer contact information', async () => {
    setupSuccessfulLoad();
    await renderPage();

    await waitFor(() => {
      expect(screen.getByText('Timothy Loss')).toBeInTheDocument();
      expect(screen.getByText(/tloss@lender\.com/)).toBeInTheDocument();
    });
  });

  it('shows fallback message when no loan officer is assigned', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => {
      if (key === 'token') return 'mock-jwt';
      return null;
    });

    const clientWithoutLO = { ...sampleClient, assigned_user: null };
    mockFetch.mockImplementation((url) => {
      if (url.includes(`/api/v1/leads/42`) && !url.includes('stage-history') && !url.includes('chat-messages') && !url.includes('conditions')) {
        return mockResponse(clientWithoutLO);
      }
      if (url.includes('/stage-history')) {
        return mockResponse({ stage_history: [] });
      }
      if (url.includes('/chat-messages')) {
        return mockResponse({ messages: [] });
      }
      if (url.includes('/smart-docs/queue')) {
        return mockResponse([]);
      }
      if (url.includes('/conditions')) {
        return mockResponse({ conditions: [] });
      }
      return mockResponse({});
    });
    activitiesAPI.getAll.mockResolvedValue([]);

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText('Loan officer will be assigned soon')).toBeInTheDocument();
    });
  });

  // -- Phone / Email Formatting --

  it('renders email as a clickable mailto link in the contact card', async () => {
    setupSuccessfulLoad();
    await renderPage();

    await waitFor(() => {
      const emailLink = screen.getByText('sarah.johnson@example.com');
      expect(emailLink.closest('a')).toHaveAttribute('href', 'mailto:sarah.johnson@example.com');
    });
  });

  it('renders phone as a clickable tel link in the contact card', async () => {
    setupSuccessfulLoad();
    await renderPage();

    await waitFor(() => {
      const phoneLink = screen.getByText('(555) 123-4567');
      expect(phoneLink.closest('a')).toHaveAttribute('href', 'tel:5551234567');
    });
  });

  // -- Communication History / Activity Timeline --

  it('displays activity timeline with correct activity count', async () => {
    setupSuccessfulLoad();
    await renderPage();

    await waitFor(() => {
      // Activities + stage history entries should both appear
      expect(screen.getByText('Conversation Log')).toBeInTheDocument();
    });

    // Check that at least some activities are rendered
    await waitFor(() => {
      expect(screen.getByText('Discussed pre-approval options')).toBeInTheDocument();
      expect(screen.getByText('Sent rate comparison document')).toBeInTheDocument();
      expect(screen.getByText('Client prefers email communication')).toBeInTheDocument();
    });
  });

  it('shows empty state when there are no activities', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => {
      if (key === 'token') return 'mock-jwt';
      return null;
    });

    mockFetch.mockImplementation((url) => {
      if (url.includes(`/api/v1/leads/42`) && !url.includes('stage-history') && !url.includes('chat-messages') && !url.includes('conditions')) {
        return mockResponse(sampleClient);
      }
      if (url.includes('/stage-history')) {
        return mockResponse({ stage_history: [] });
      }
      if (url.includes('/chat-messages')) {
        return mockResponse({ messages: [] });
      }
      if (url.includes('/smart-docs/queue')) {
        return mockResponse([]);
      }
      if (url.includes('/conditions')) {
        return mockResponse({ conditions: [] });
      }
      return mockResponse({});
    });
    activitiesAPI.getAll.mockResolvedValue([]);

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText('No conversations yet')).toBeInTheDocument();
    });
  });

  // -- Loan Summary Display --

  it('displays loan amount in the header summary', async () => {
    setupSuccessfulLoad();
    await renderPage();

    await waitFor(() => {
      expect(screen.getByText('$425,000')).toBeInTheDocument();
    });
  });

  it('displays loan type and current stage in the header', async () => {
    setupSuccessfulLoad();
    await renderPage();

    await waitFor(() => {
      expect(screen.getByText('Conventional')).toBeInTheDocument();
    });
  });

  // -- Stage Badge --

  it('maps stage to correct display label', async () => {
    setupSuccessfulLoad();
    await renderPage();

    await waitFor(() => {
      // Pre-Approved stage should show its label
      expect(screen.getByText('Pre-Approved')).toBeInTheDocument();
    });
  });

  // -- Property Address --

  it('displays formatted property address', async () => {
    setupSuccessfulLoad();
    await renderPage();

    await waitFor(() => {
      expect(screen.getByText(/123 Main St, Austin, TX/)).toBeInTheDocument();
    });
  });

  it('shows fallback when property address is missing', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => {
      if (key === 'token') return 'mock-jwt';
      return null;
    });

    const clientNoAddress = { ...sampleClient, address: null, city: null, state: null };
    mockFetch.mockImplementation((url) => {
      if (url.includes(`/api/v1/leads/42`) && !url.includes('stage-history') && !url.includes('chat-messages') && !url.includes('conditions')) {
        return mockResponse(clientNoAddress);
      }
      if (url.includes('/stage-history')) {
        return mockResponse({ stage_history: [] });
      }
      if (url.includes('/chat-messages')) {
        return mockResponse({ messages: [] });
      }
      if (url.includes('/smart-docs/queue')) {
        return mockResponse([]);
      }
      if (url.includes('/conditions')) {
        return mockResponse({ conditions: [] });
      }
      return mockResponse({});
    });
    activitiesAPI.getAll.mockResolvedValue([]);

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Property Address TBD/)).toBeInTheDocument();
    });
  });

  // -- Pre-Approval Letter Modal --

  it('opens pre-approval letter modal on button click', async () => {
    setupSuccessfulLoad();
    await renderPage();

    await waitFor(() => {
      expect(screen.getByText('Pre-Approval Letter')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Pre-Approval Letter'));
    expect(screen.getByTestId('pre-approval-modal')).toBeInTheDocument();
  });

  // -- Navigation --

  it('navigates back when Back to Dashboard is clicked', async () => {
    setupSuccessfulLoad();
    await renderPage();

    await waitFor(() => {
      const backBtn = screen.getByText(/Back to Dashboard/);
      expect(backBtn).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/Back to Dashboard/));
    expect(mockNavigate).toHaveBeenCalledWith(-1);
  });

  // -- Authentication Handling --

  it('shows auth error when no tokens are available', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null);
    // Also mock URLSearchParams to return no token
    const originalLocation = window.location;
    delete window.location;
    window.location = { ...originalLocation, search: '' };

    mockFetch.mockImplementation(() => mockResponse({}, 401));
    activitiesAPI.getAll.mockResolvedValue([]);

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Authentication required/)).toBeInTheDocument();
    });

    window.location = originalLocation;
  });
});
