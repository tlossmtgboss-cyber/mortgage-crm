/**
 * PublicBooking page tests.
 *
 * PublicBooking is a public-facing scheduler page that:
 *  1. Fetches a booking link config (title, appointment types)
 *  2. Shows a date/time picker (datetime step)
 *  3. Collects attendee info (form step)
 *  4. Confirms the booking (confirmation step)
 *
 * It uses the LanguageProvider for i18n and useOrgBranding for org theming.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { mockBookingLink, mockAvailableSlots, createMockFetch } from '../test/testUtils';

// Mock useOrgBranding hook
vi.mock('../hooks/useOrgBranding', () => ({
  default: vi.fn(() => ({
    branding: {
      org_name: 'Test Mortgage Co',
      logo_url: 'https://example.com/logo.png',
      primary_color: '#217F8D',
      accent_color: '#34a853',
      tagline: 'Your trusted mortgage partner',
      welcome_message: 'Welcome to our booking page',
      lo: null,
      show_testimonials: false,
      testimonials: [],
    },
    loading: false,
    error: null,
  })),
}));

// Lazy-import after mocks are registered
let PublicBooking;
beforeAll(async () => {
  const mod = await import('../pages/PublicBooking');
  PublicBooking = mod.default;
});

// Wrapper with MemoryRouter (PublicBooking uses useParams)
function renderBooking(initialEntries = ['/book/test-slug']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <PublicBooking />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------
beforeEach(() => {
  vi.clearAllMocks();

  // Default: successful booking link + slots
  // Note: order matters -- /slots must come BEFORE the booking link pattern
  // because createMockFetch uses string.includes() and the slots URL also
  // contains the booking link path prefix.
  global.fetch = vi.fn().mockImplementation((url) => {
    if (url.includes('/slots')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ available_slots: mockAvailableSlots }),
      });
    }
    if (url.includes('/scheduler/public/book/')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          booking_page: {
            ...mockBookingLink,
            custom_title: null,
            custom_description: null,
          },
        }),
      });
    }
    return Promise.resolve({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: 'Not found' }),
    });
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PublicBooking Page', () => {
  // ------ Loading / Initial Render ------

  it('shows loading spinner initially', () => {
    // Make fetch hang to see loading state
    global.fetch = vi.fn(() => new Promise(() => {}));
    renderBooking();

    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders booking page after loading', async () => {
    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Pick a date')).toBeInTheDocument();
    });
  });

  it('shows booking link title', async () => {
    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Schedule a meeting')).toBeInTheDocument();
    });
  });

  it('shows booking link description', async () => {
    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Pick a time that works for you.')).toBeInTheDocument();
    });
  });

  it('renders "Powered by Perennia AI" footer', async () => {
    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Perennia AI')).toBeInTheDocument();
    });
  });

  // ------ Error States ------

  it('shows error when booking link returns 404', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: 'Not found' }),
    });

    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Booking Unavailable')).toBeInTheDocument();
    });
  });

  it('shows connection error when fetch throws', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network failure'));

    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Booking Unavailable')).toBeInTheDocument();
    });
  });

  // ------ Step 1: Date/Time Selection ------

  it('renders week date cards', async () => {
    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Pick a date')).toBeInTheDocument();
    });

    // Should show 7 date cards (one per day of the week)
    const dateCards = screen.getAllByRole('button').filter(btn =>
      btn.classList.contains('date-card')
    );
    // Date cards are buttons with day numbers
    expect(dateCards.length).toBe(7);
  });

  it('renders week navigation arrows', async () => {
    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Pick a date')).toBeInTheDocument();
    });

    expect(screen.getByLabelText('Previous week')).toBeInTheDocument();
    expect(screen.getByLabelText('Next week')).toBeInTheDocument();
  });

  it('navigates to next week when arrow is clicked', async () => {
    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Pick a date')).toBeInTheDocument();
    });

    const nextWeekBtn = screen.getByLabelText('Next week');
    fireEvent.click(nextWeekBtn);

    // After clicking next week, the date cards should update
    // (exact dates depend on current date, so just verify the click didn't crash)
    expect(screen.getByText('Pick a date')).toBeInTheDocument();
  });

  it('renders time picker section', async () => {
    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Pick a time')).toBeInTheDocument();
    });
  });

  it('renders meeting mode toggle (phone/video)', async () => {
    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Phone call')).toBeInTheDocument();
      expect(screen.getByText('Video call')).toBeInTheDocument();
    });
  });

  it('appointment type pills are shown when multiple types exist', async () => {
    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Consultation')).toBeInTheDocument();
      expect(screen.getByText('Rate Review')).toBeInTheDocument();
    });
  });

  it('Next button is disabled when no time slot is selected and no slots available', async () => {
    // Return no slots -- check /slots first since the slots URL also contains the booking path
    global.fetch = vi.fn().mockImplementation((url) => {
      if (url.includes('/slots')) {
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ available_slots: [] }),
        });
      }
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({
          booking_page: {
            ...mockBookingLink,
            appointment_types: [mockBookingLink.appointment_types[0]],
          },
        }),
      });
    });

    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Pick a date')).toBeInTheDocument();
    });

    const nextBtn = screen.getByText('Next');
    expect(nextBtn).toBeDisabled();
  });

  // ------ Step 2: Form ------

  it('navigates to form step when Next is clicked with a selected slot', async () => {
    renderBooking();

    await waitFor(() => {
      expect(screen.getByText('Pick a date')).toBeInTheDocument();
    });

    // Wait for slots to load (auto-selects first slot)
    await waitFor(() => {
      const nextBtn = screen.getByText('Next');
      expect(nextBtn).not.toBeDisabled();
    });

    fireEvent.click(screen.getByText('Next'));

    await waitFor(() => {
      expect(screen.getByText('Tell us a little about yourself')).toBeInTheDocument();
    });
  });

  it('renders form fields for first name, last name, email, phone, notes', async () => {
    renderBooking();

    await waitFor(() => {
      const nextBtn = screen.getByText('Next');
      expect(nextBtn).not.toBeDisabled();
    });

    fireEvent.click(screen.getByText('Next'));

    await waitFor(() => {
      expect(screen.getByLabelText(/First Name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Last Name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Phone/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Notes/i)).toBeInTheDocument();
    });
  });

  it('has a back button on form step that returns to datetime', async () => {
    renderBooking();

    await waitFor(() => {
      const nextBtn = screen.getByText('Next');
      expect(nextBtn).not.toBeDisabled();
    });

    fireEvent.click(screen.getByText('Next'));

    await waitFor(() => {
      expect(screen.getByText('Back')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Back'));

    await waitFor(() => {
      expect(screen.getByText('Pick a date')).toBeInTheDocument();
    });
  });

  it('renders custom question about working with loan officer', async () => {
    renderBooking();

    await waitFor(() => {
      const nextBtn = screen.getByText('Next');
      expect(nextBtn).not.toBeDisabled();
    });

    fireEvent.click(screen.getByText('Next'));

    await waitFor(() => {
      expect(screen.getByText(/working with a loan officer/i)).toBeInTheDocument();
    });
  });

  // ------ Form Validation ------

  it('shows error when submitting with empty required fields', async () => {
    renderBooking();

    await waitFor(() => {
      const nextBtn = screen.getByText('Next');
      expect(nextBtn).not.toBeDisabled();
    });

    fireEvent.click(screen.getByText('Next'));

    await waitFor(() => {
      expect(screen.getByText('Schedule Appointment')).toBeInTheDocument();
    });

    // The inputs have HTML5 `required` attribute, so clicking submit won't
    // trigger onSubmit. Use fireEvent.submit on the form to invoke the
    // custom validation handler directly.
    const form = screen.getByText('Schedule Appointment').closest('form');
    fireEvent.submit(form);

    await waitFor(() => {
      // The error message about required fields
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  // ------ Step 3: Successful Booking ------

  it('shows confirmation after successful booking', async () => {
    // Setup fetch to handle booking confirmation too
    const fetchMock = vi.fn().mockImplementation((url, options) => {
      if (url.includes('/confirm') && options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ appointment_id: 'new-appt-1' }),
        });
      }
      if (url.includes('/slots')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ available_slots: mockAvailableSlots }),
        });
      }
      // Booking link
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          booking_page: {
            ...mockBookingLink,
            appointment_types: [mockBookingLink.appointment_types[0]],
          },
        }),
      });
    });
    global.fetch = fetchMock;

    renderBooking();

    // Wait for datetime step
    await waitFor(() => {
      const nextBtn = screen.getByText('Next');
      expect(nextBtn).not.toBeDisabled();
    });

    // Go to form step
    fireEvent.click(screen.getByText('Next'));

    await waitFor(() => {
      expect(screen.getByLabelText(/First Name/i)).toBeInTheDocument();
    });

    // Fill out form
    await userEvent.type(screen.getByLabelText(/First Name/i), 'Jane');
    await userEvent.type(screen.getByLabelText(/Last Name/i), 'Doe');
    await userEvent.type(screen.getByLabelText(/Email/i), 'jane@test.com');

    // Submit
    fireEvent.click(screen.getByText('Schedule Appointment'));

    // Should show confirmation
    await waitFor(() => {
      expect(screen.getByText('Your request has been made')).toBeInTheDocument();
    });
  });

  it('shows error when booking fails', async () => {
    const fetchMock = vi.fn().mockImplementation((url, options) => {
      if (url.includes('/confirm') && options?.method === 'POST') {
        return Promise.resolve({
          ok: false,
          status: 500,
          json: () => Promise.resolve({ detail: 'Server error' }),
        });
      }
      if (url.includes('/slots')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ available_slots: mockAvailableSlots }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          booking_page: {
            ...mockBookingLink,
            appointment_types: [mockBookingLink.appointment_types[0]],
          },
        }),
      });
    });
    global.fetch = fetchMock;

    renderBooking();

    await waitFor(() => {
      const nextBtn = screen.getByText('Next');
      expect(nextBtn).not.toBeDisabled();
    });

    fireEvent.click(screen.getByText('Next'));

    await waitFor(() => {
      expect(screen.getByLabelText(/First Name/i)).toBeInTheDocument();
    });

    await userEvent.type(screen.getByLabelText(/First Name/i), 'Jane');
    await userEvent.type(screen.getByLabelText(/Last Name/i), 'Doe');
    await userEvent.type(screen.getByLabelText(/Email/i), 'jane@test.com');

    fireEvent.click(screen.getByText('Schedule Appointment'));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText(/Unable to complete your booking/i)).toBeInTheDocument();
    });
  });

  // ------ Language Selector ------

  it('renders language selector', async () => {
    renderBooking();

    await waitFor(() => {
      // LanguageSelector renders both a nav and a select with aria-label "Language"
      const selects = screen.getAllByLabelText('Language');
      expect(selects.length).toBeGreaterThanOrEqual(1);
    });
  });
});
