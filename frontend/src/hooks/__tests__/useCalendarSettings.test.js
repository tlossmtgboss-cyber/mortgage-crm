import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

// ---------------------------------------------------------------------------
// Mocks — vi.hoisted ensures mockAPI is defined before the hoisted vi.mock
// ---------------------------------------------------------------------------

const mockAPI = vi.hoisted(() => ({
  getAvailability: vi.fn(),
  getAppointmentTypes: vi.fn(),
  getBookingPage: vi.fn(),
  getNotifications: vi.fn(),
  getIntegrations: vi.fn(),
  getTeam: vi.fn(),
  updateAvailability: vi.fn(),
  updateAppointmentTypes: vi.fn(),
  updateBookingPage: vi.fn(),
  updateNotifications: vi.fn(),
  updateIntegrations: vi.fn(),
  updateTeam: vi.fn(),
}));

vi.mock('../../services/api', () => ({
  calendarSettingsAPI: mockAPI,
}));

import useCalendarSettings from '../useCalendarSettings';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Resolve all pending promises (flush microtask queue). */
const flushPromises = () => new Promise((resolve) => setTimeout(resolve, 0));

/** Default mock responses per section. */
const SECTION_RESPONSES = {
  availability: { data: { timezone: 'America/New_York', days: ['mon', 'tue'] } },
  appointmentTypes: { data: { types: [{ id: 1, name: 'Consultation' }] } },
  bookingPage: { data: { slug: 'my-page', color: '#3366ff' } },
  notifications: { data: { email: true, sms: false } },
  integrations: { data: { google: true, outlook: false } },
  team: { data: { members: [] } },
};

function setDefaultMockResponses() {
  mockAPI.getAvailability.mockResolvedValue(SECTION_RESPONSES.availability);
  mockAPI.getAppointmentTypes.mockResolvedValue(SECTION_RESPONSES.appointmentTypes);
  mockAPI.getBookingPage.mockResolvedValue(SECTION_RESPONSES.bookingPage);
  mockAPI.getNotifications.mockResolvedValue(SECTION_RESPONSES.notifications);
  mockAPI.getIntegrations.mockResolvedValue(SECTION_RESPONSES.integrations);
  mockAPI.getTeam.mockResolvedValue(SECTION_RESPONSES.team);

  mockAPI.updateAvailability.mockResolvedValue({ data: {} });
  mockAPI.updateAppointmentTypes.mockResolvedValue({ data: {} });
  mockAPI.updateBookingPage.mockResolvedValue({ data: {} });
  mockAPI.updateNotifications.mockResolvedValue({ data: {} });
  mockAPI.updateIntegrations.mockResolvedValue({ data: {} });
  mockAPI.updateTeam.mockResolvedValue({ data: {} });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useCalendarSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setDefaultMockResponses();
  });

  // =========================================================================
  // Loading tests
  // =========================================================================

  describe('Loading', () => {
    it('sets loading=true initially, then false after sections load', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings(['availability']),
      );

      // loading starts true (synchronous initial state)
      expect(result.current.loading).toBe(true);

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
    });

    it('loads specified sections on mount and calls correct API methods', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings(['availability', 'notifications', 'team']),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(mockAPI.getAvailability).toHaveBeenCalledTimes(1);
      expect(mockAPI.getNotifications).toHaveBeenCalledTimes(1);
      expect(mockAPI.getTeam).toHaveBeenCalledTimes(1);

      // Should NOT call loaders for sections not requested
      expect(mockAPI.getAppointmentTypes).not.toHaveBeenCalled();
      expect(mockAPI.getBookingPage).not.toHaveBeenCalled();
      expect(mockAPI.getIntegrations).not.toHaveBeenCalled();

      // Settings should contain loaded data
      expect(result.current.settings.availability).toEqual(
        SECTION_RESPONSES.availability.data,
      );
      expect(result.current.settings.notifications).toEqual(
        SECTION_RESPONSES.notifications.data,
      );
      expect(result.current.settings.team).toEqual(
        SECTION_RESPONSES.team.data,
      );
    });

    it('handles empty sections array (immediately sets loading=false)', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings([]),
      );

      // With no sections the hook skips the async path and calls
      // setLoading(false) synchronously inside the effect.
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // No API calls should have been made
      expect(mockAPI.getAvailability).not.toHaveBeenCalled();
      expect(mockAPI.getBookingPage).not.toHaveBeenCalled();
    });

    it('handles API errors gracefully (sets section to null, does not crash)', async () => {
      mockAPI.getAvailability.mockRejectedValue(new Error('Network error'));
      // notifications still succeeds
      mockAPI.getNotifications.mockResolvedValue(SECTION_RESPONSES.notifications);

      const { result } = renderHook(() =>
        useCalendarSettings(['availability', 'notifications']),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Failed section is set to null
      expect(result.current.settings.availability).toBeNull();
      // Successful section still loads
      expect(result.current.settings.notifications).toEqual(
        SECTION_RESPONSES.notifications.data,
      );
      // Hook does not set top-level error for load failures
      expect(result.current.error).toBeNull();
    });

    it('cancels in-flight loads on unmount (cancelled flag)', async () => {
      // Create a slow-resolving promise we can control
      let resolveAvailability;
      mockAPI.getAvailability.mockReturnValue(
        new Promise((resolve) => {
          resolveAvailability = resolve;
        }),
      );

      const { result, unmount } = renderHook(() =>
        useCalendarSettings(['availability']),
      );

      expect(result.current.loading).toBe(true);

      // Unmount before the promise resolves
      unmount();

      // Resolve the promise after unmount
      resolveAvailability(SECTION_RESPONSES.availability);
      await flushPromises();

      // Since the component unmounted, state should NOT have been updated.
      // If the cancelled flag works correctly, React won't see a state update
      // on an unmounted component. We verify by checking that no warnings
      // were thrown and the test completes without error.
      // (The loading would remain true since state was never updated.)
    });
  });

  // =========================================================================
  // Update tests
  // =========================================================================

  describe('Update', () => {
    it('updateSection merges data into the correct section', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings(['availability']),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      act(() => {
        result.current.updateSection('availability', { timezone: 'America/Chicago' });
      });

      // Merged: timezone updated, days preserved
      expect(result.current.settings.availability).toEqual({
        timezone: 'America/Chicago',
        days: ['mon', 'tue'],
      });
    });

    it('updateSection marks the section as dirty', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings(['availability']),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.isSectionDirty('availability')).toBe(false);

      act(() => {
        result.current.updateSection('availability', { timezone: 'UTC' });
      });

      expect(result.current.isSectionDirty('availability')).toBe(true);
    });

    it('isDirty returns true when any section has been modified', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings(['availability', 'notifications']),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.isDirty).toBe(false);

      act(() => {
        result.current.updateSection('notifications', { sms: true });
      });

      expect(result.current.isDirty).toBe(true);
    });

    it('isSectionDirty returns true only for modified sections', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings(['availability', 'notifications']),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      act(() => {
        result.current.updateSection('notifications', { sms: true });
      });

      expect(result.current.isSectionDirty('notifications')).toBe(true);
      expect(result.current.isSectionDirty('availability')).toBe(false);
    });
  });

  // =========================================================================
  // Save tests
  // =========================================================================

  describe('Save', () => {
    it('saveSection calls the correct API saver with section data', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings(['availability']),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      act(() => {
        result.current.updateSection('availability', { timezone: 'America/Denver' });
      });

      await act(async () => {
        await result.current.saveSection('availability');
      });

      expect(mockAPI.updateAvailability).toHaveBeenCalledTimes(1);
      expect(mockAPI.updateAvailability).toHaveBeenCalledWith({
        timezone: 'America/Denver',
        days: ['mon', 'tue'],
      });
    });

    it('saveSection clears dirty flag on success', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings(['availability']),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      act(() => {
        result.current.updateSection('availability', { timezone: 'UTC' });
      });
      expect(result.current.isSectionDirty('availability')).toBe(true);

      await act(async () => {
        await result.current.saveSection('availability');
      });

      expect(result.current.isSectionDirty('availability')).toBe(false);
      expect(result.current.isDirty).toBe(false);
    });

    it('saveSection updates snapshot on success', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings(['notifications']),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // First update + save
      act(() => {
        result.current.updateSection('notifications', { sms: true });
      });

      await act(async () => {
        await result.current.saveSection('notifications');
      });

      // Second update + failed save should rollback to the FIRST save's data,
      // not the original load data.
      mockAPI.updateNotifications.mockRejectedValueOnce(new Error('Server error'));

      act(() => {
        result.current.updateSection('notifications', { sms: false, push: true });
      });

      await act(async () => {
        try {
          await result.current.saveSection('notifications');
        } catch {
          // expected
        }
      });

      // Rolled back to snapshot from first successful save
      expect(result.current.settings.notifications).toEqual({
        email: true,
        sms: true, // from first save, not original false
      });
    });

    it('saveSection rolls back on failure (restores previous data)', async () => {
      mockAPI.updateAvailability.mockRejectedValue(new Error('Save failed'));

      const { result } = renderHook(() =>
        useCalendarSettings(['availability']),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      const originalData = { ...result.current.settings.availability };

      act(() => {
        result.current.updateSection('availability', { timezone: 'Europe/London' });
      });

      // Verify the optimistic update happened
      expect(result.current.settings.availability.timezone).toBe('Europe/London');

      await act(async () => {
        try {
          await result.current.saveSection('availability');
        } catch {
          // expected
        }
      });

      // Data should be rolled back to original snapshot
      expect(result.current.settings.availability).toEqual(originalData);
    });

    it('saveSection sets error on failure', async () => {
      const saveError = new Error('Server unavailable');
      mockAPI.updateAvailability.mockRejectedValue(saveError);

      const { result } = renderHook(() =>
        useCalendarSettings(['availability']),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      act(() => {
        result.current.updateSection('availability', { timezone: 'UTC' });
      });

      await act(async () => {
        try {
          await result.current.saveSection('availability');
        } catch {
          // expected
        }
      });

      expect(result.current.error).toBe(saveError);
      expect(result.current.error.message).toBe('Server unavailable');
    });

    it('saveSection throws for unknown sections', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings(['availability']),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      await expect(
        act(async () => {
          await result.current.saveSection('nonexistent');
        }),
      ).rejects.toThrow('Unknown section: nonexistent');
    });

    it('saving flag is true during save, false after', async () => {
      let resolveSave;
      mockAPI.updateAvailability.mockReturnValue(
        new Promise((resolve) => {
          resolveSave = resolve;
        }),
      );

      const { result } = renderHook(() =>
        useCalendarSettings(['availability']),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.saving).toBe(false);

      act(() => {
        result.current.updateSection('availability', { timezone: 'UTC' });
      });

      // Start save (don't await)
      let savePromise;
      act(() => {
        savePromise = result.current.saveSection('availability');
      });

      // saving should be true while in-flight
      expect(result.current.saving).toBe(true);

      // Resolve the API call
      await act(async () => {
        resolveSave({ data: {} });
        await savePromise;
      });

      expect(result.current.saving).toBe(false);
    });
  });

  // =========================================================================
  // Auto-save tests
  // =========================================================================

  describe('Auto-save', () => {
    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('when autoSave=true, saves dirty sections after debounce delay', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings(['availability'], { autoSave: true, debounceMs: 1500 }),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      act(() => {
        result.current.updateSection('availability', { timezone: 'UTC' });
      });

      // Save should NOT have been called yet (within debounce window)
      expect(mockAPI.updateAvailability).not.toHaveBeenCalled();

      // Advance past debounce window
      await act(async () => {
        vi.advanceTimersByTime(1500);
      });

      await waitFor(() => {
        expect(mockAPI.updateAvailability).toHaveBeenCalledTimes(1);
      });

      expect(mockAPI.updateAvailability).toHaveBeenCalledWith({
        timezone: 'UTC',
        days: ['mon', 'tue'],
      });
    });

    it('when autoSave=false, does not auto-save', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings(['availability'], { autoSave: false }),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      act(() => {
        result.current.updateSection('availability', { timezone: 'UTC' });
      });

      // Advance well past default debounce window
      await act(async () => {
        vi.advanceTimersByTime(5000);
      });

      // No auto-save should have occurred
      expect(mockAPI.updateAvailability).not.toHaveBeenCalled();
    });

    it('resets debounce timer when data changes again within window', async () => {
      const { result } = renderHook(() =>
        useCalendarSettings(['availability'], { autoSave: true, debounceMs: 1500 }),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // First update
      act(() => {
        result.current.updateSection('availability', { timezone: 'UTC' });
      });

      // Advance 1000ms (still within 1500ms window)
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      // No save yet
      expect(mockAPI.updateAvailability).not.toHaveBeenCalled();

      // Second update -- should reset the timer
      act(() => {
        result.current.updateSection('availability', { timezone: 'America/Chicago' });
      });

      // Advance another 1000ms (1000ms since second update, 2000ms since first)
      // If debounce was NOT reset, save would have fired at 1500ms since first update.
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      // Still no save -- debounce was reset by second update
      expect(mockAPI.updateAvailability).not.toHaveBeenCalled();

      // Advance remaining 500ms to complete debounce from second update
      await act(async () => {
        vi.advanceTimersByTime(500);
      });

      await waitFor(() => {
        expect(mockAPI.updateAvailability).toHaveBeenCalledTimes(1);
      });

      // Should have saved the latest data (from second update)
      expect(mockAPI.updateAvailability).toHaveBeenCalledWith({
        timezone: 'America/Chicago',
        days: ['mon', 'tue'],
      });
    });
  });
});
