/**
 * ClientFileView tests.
 *
 * Tests cover: loading state, error state, successful render with client name,
 * quick action buttons, quick action click behavior, avatar initials.
 */
import React from 'react';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, beforeAll } from 'vitest';
import { renderWithProviders } from '../test/testUtils';

// ---------------------------------------------------------------------------
// Mock Capacitor
// ---------------------------------------------------------------------------
vi.mock('@capacitor/core', () => ({
  Capacitor: { isNativePlatform: () => false },
}));

vi.mock('@capacitor/preferences', () => ({
  Preferences: {
    get: vi.fn().mockResolvedValue({ value: null }),
    set: vi.fn().mockResolvedValue(undefined),
    remove: vi.fn().mockResolvedValue(undefined),
  },
}));

// ---------------------------------------------------------------------------
// Mock useClientFile hook — this is the TanStack Query wrapper
// ---------------------------------------------------------------------------
const mockRefetch = vi.fn();
let mockClientFileResult = {
  data: null,
  isLoading: true,
  error: null,
  refetch: mockRefetch,
};

vi.mock('../client-file/hooks', () => ({
  useClientFile: () => mockClientFileResult,
}));

// ---------------------------------------------------------------------------
// Mock sub-components — these are complex components we don't need to test here
// ---------------------------------------------------------------------------
vi.mock('../client-file/ActivityPane', () => ({
  ActivityPane: () => <div data-testid="activity-pane">Activity Pane</div>,
}));

vi.mock('../client-file/IdentityPanel', () => ({
  IdentityPanel: ({ client }) => <div data-testid="identity-panel">{client.first_name}</div>,
}));

vi.mock('../client-file/ToolsRail', () => ({
  ToolsRail: () => <div data-testid="tools-rail">Tools Rail</div>,
}));

vi.mock('../client-file/QuickActionsRail', () => ({
  QuickActionsRail: ({ onAction, client }) => (
    <div data-testid="quick-actions-rail">
      {/* Render clickable buttons for each quick action */}
      {['sms', 'email', 'task', 'appointment', 'video', 'voicemail', 'record_video', 'application', 'portals', 'escalation'].map(key => (
        <button key={key} data-testid={`qa-${key}`} onClick={() => onAction(key)}>
          {key}
        </button>
      ))}
    </div>
  ),
}));

// Mock modal components — they just render when open
vi.mock('../components/SMSModal', () => ({
  default: ({ isOpen }) => isOpen ? <div data-testid="sms-modal">SMS Modal</div> : null,
}));
vi.mock('../components/EmailComposerModal', () => ({
  default: ({ isOpen }) => isOpen ? <div data-testid="email-modal">Email Modal</div> : null,
}));
vi.mock('../components/CreateTaskModal', () => ({
  default: ({ isOpen }) => isOpen ? <div data-testid="task-modal">Task Modal</div> : null,
}));
vi.mock('../components/ScheduleAppointmentModal', () => ({
  default: ({ isOpen }) => isOpen ? <div data-testid="appointment-modal">Appointment Modal</div> : null,
}));
vi.mock('../components/VideoCallScheduleModal', () => ({
  default: ({ isOpen }) => isOpen ? <div data-testid="video-modal">Video Modal</div> : null,
}));
vi.mock('../components/VoicemailDrop', () => ({
  default: ({ onClose }) => <div data-testid="voicemail-modal">Voicemail Drop</div>,
}));
vi.mock('../components/EscalationModal', () => ({
  default: ({ isOpen }) => isOpen ? <div data-testid="escalation-modal">Escalation Modal</div> : null,
}));
vi.mock('../components/SendApplicationModal', () => ({
  default: ({ isOpen }) => isOpen ? <div data-testid="application-modal">Application Modal</div> : null,
}));

// Mock toast
vi.mock('../utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

// Mock CSS
vi.mock('../client-file/styles.css', () => ({}));

// ---------------------------------------------------------------------------
// Mock services/api since ClientFileView transitively imports it
// ---------------------------------------------------------------------------
vi.mock('../services/api', () => ({
  default: { defaults: { baseURL: 'http://test-api.local' } },
  API_BASE_URL: 'http://test-api.local',
}));

// ---------------------------------------------------------------------------
// Mock client data
// ---------------------------------------------------------------------------
const mockClient = {
  id: 'cf-123',
  org_id: 'org-1',
  first_name: 'Jane',
  last_name: 'Doe',
  primary_email: 'jane@example.com',
  primary_phone: '+15551234567',
  lifecycle_stage: 'in_processing',
  lead_id: 42,
  language_pref: 'en',
  tags: [],
  custom_fields: {},
  unread_thread_count: 0,
  open_doc_request_count: 0,
  property_address: {
    city: 'Austin',
    state: 'TX',
  },
  active_loan_purpose: 'purchase',
};

// ---------------------------------------------------------------------------
// Lazy import after mocks
// ---------------------------------------------------------------------------
let ClientFileView;
beforeAll(async () => {
  const mod = await import('../client-file/ClientFileView');
  ClientFileView = mod.ClientFileView;
});

beforeEach(() => {
  vi.clearAllMocks();
  mockClientFileResult = {
    data: null,
    isLoading: true,
    error: null,
    refetch: mockRefetch,
  };
});

// ===========================================================================
// Tests
// ===========================================================================

describe('ClientFileView', () => {
  // -----------------------------------------------------------------------
  // Loading state
  // -----------------------------------------------------------------------
  describe('Loading state', () => {
    it('renders loading indicator while fetching', () => {
      mockClientFileResult = { data: null, isLoading: true, error: null, refetch: mockRefetch };
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      expect(screen.getByText(/loading client file/i)).toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Error state
  // -----------------------------------------------------------------------
  describe('Error state', () => {
    it('shows "Could not load client file" on error', () => {
      mockClientFileResult = {
        data: null,
        isLoading: false,
        error: { status: 500, message: 'Server error' },
        refetch: mockRefetch,
      };
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      expect(screen.getByText('Could not load client file.')).toBeInTheDocument();
    });

    it('shows 404-specific message for missing records', () => {
      mockClientFileResult = {
        data: null,
        isLoading: false,
        error: { status: 404, message: 'Not found' },
        refetch: mockRefetch,
      };
      renderWithProviders(<ClientFileView clientFileId="cf-999" currentUserId="user-1" />);

      expect(screen.getByText(/may not exist yet/i)).toBeInTheDocument();
    });

    it('shows generic message for non-404 errors', () => {
      mockClientFileResult = {
        data: null,
        isLoading: false,
        error: { status: 503, message: 'Unavailable' },
        refetch: mockRefetch,
      };
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      expect(screen.getByText(/temporarily unavailable/i)).toBeInTheDocument();
    });

    it('renders Retry button that calls refetch', () => {
      mockClientFileResult = {
        data: null,
        isLoading: false,
        error: { status: 500 },
        refetch: mockRefetch,
      };
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      const retryBtn = screen.getByText('Retry');
      fireEvent.click(retryBtn);
      expect(mockRefetch).toHaveBeenCalledTimes(1);
    });

    it('renders Go Back button on error', () => {
      mockClientFileResult = {
        data: null,
        isLoading: false,
        error: { status: 500 },
        refetch: mockRefetch,
      };
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      expect(screen.getByText('Go Back')).toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Successful load
  // -----------------------------------------------------------------------
  describe('Successful load', () => {
    it('displays client name (not "Unknown")', () => {
      mockClientFileResult = {
        data: mockClient,
        isLoading: false,
        error: null,
        refetch: mockRefetch,
      };
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    it('shows "Unknown" when both first and last name are empty', () => {
      mockClientFileResult = {
        data: { ...mockClient, first_name: '', last_name: '' },
        isLoading: false,
        error: null,
        refetch: mockRefetch,
      };
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      expect(screen.getByText('Unknown')).toBeInTheDocument();
    });

    it('renders avatar with correct initials', () => {
      mockClientFileResult = {
        data: mockClient,
        isLoading: false,
        error: null,
        refetch: mockRefetch,
      };
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      // deriveInitials("Jane Doe") = "JD"
      expect(screen.getByText('JD')).toBeInTheDocument();
    });

    it('renders property info in header subtitle', () => {
      mockClientFileResult = {
        data: mockClient,
        isLoading: false,
        error: null,
        refetch: mockRefetch,
      };
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      // Should show city/state and loan purpose
      expect(screen.getByText(/Austin TX/)).toBeInTheDocument();
    });

    it('renders Lead Details button when lead_id is present', () => {
      mockClientFileResult = {
        data: mockClient,
        isLoading: false,
        error: null,
        refetch: mockRefetch,
      };
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      expect(screen.getByText('Lead Details')).toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Quick action buttons
  // -----------------------------------------------------------------------
  describe('Quick actions', () => {
    beforeEach(() => {
      mockClientFileResult = {
        data: mockClient,
        isLoading: false,
        error: null,
        refetch: mockRefetch,
      };
    });

    it('renders all 10 quick action buttons', () => {
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      const actions = ['sms', 'email', 'task', 'appointment', 'video', 'voicemail', 'record_video', 'application', 'portals', 'escalation'];
      for (const key of actions) {
        expect(screen.getByTestId(`qa-${key}`)).toBeInTheDocument();
      }
    });

    it('clicking SMS opens SMS modal', async () => {
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      fireEvent.click(screen.getByTestId('qa-sms'));
      await waitFor(() => {
        expect(screen.getByTestId('sms-modal')).toBeInTheDocument();
      });
    });

    it('clicking Email opens Email modal', async () => {
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      fireEvent.click(screen.getByTestId('qa-email'));
      await waitFor(() => {
        expect(screen.getByTestId('email-modal')).toBeInTheDocument();
      });
    });

    it('clicking Task opens Task modal', async () => {
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      fireEvent.click(screen.getByTestId('qa-task'));
      await waitFor(() => {
        expect(screen.getByTestId('task-modal')).toBeInTheDocument();
      });
    });

    it('clicking Escalation opens Escalation modal', async () => {
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      fireEvent.click(screen.getByTestId('qa-escalation'));
      await waitFor(() => {
        expect(screen.getByTestId('escalation-modal')).toBeInTheDocument();
      });
    });

    it('clicking Voicemail opens VoicemailDrop when phone is available', async () => {
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      fireEvent.click(screen.getByTestId('qa-voicemail'));
      await waitFor(() => {
        expect(screen.getByTestId('voicemail-modal')).toBeInTheDocument();
      });
    });
  });

  // -----------------------------------------------------------------------
  // Sub-component rendering
  // -----------------------------------------------------------------------
  describe('Sub-components', () => {
    it('renders IdentityPanel, ActivityPane, QuickActionsRail', () => {
      mockClientFileResult = {
        data: mockClient,
        isLoading: false,
        error: null,
        refetch: mockRefetch,
      };
      renderWithProviders(<ClientFileView clientFileId="cf-123" currentUserId="user-1" />);

      expect(screen.getByTestId('identity-panel')).toBeInTheDocument();
      expect(screen.getByTestId('activity-pane')).toBeInTheDocument();
      expect(screen.getByTestId('quick-actions-rail')).toBeInTheDocument();
    });
  });
});
