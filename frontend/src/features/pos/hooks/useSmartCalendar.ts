/**
 * useSmartCalendar — Step 9 booking widget state.
 *
 * Lifecycle:
 *   1. Fetch the assigned LO (`loadLO`)
 *   2. Fetch a date range of slots (`loadSlots`)
 *   3. User picks a slot → optionally `hold` it (5-min TTL countdown)
 *   4. User confirms → `book` → returns BookingResponse with .ics + email
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { posApi } from '../api';
import type {
  AssignedLOResponse,
  AvailableSlotsResponse,
  BookingResponse,
  MeetingType,
  SlotHoldResponse,
  TimeSlot,
} from '../types';

export interface CalendarRange {
  startDate: string; // YYYY-MM-DD
  endDate: string;
}

function defaultRange(): CalendarRange {
  const today = new Date();
  const start = today.toISOString().slice(0, 10);
  const end = new Date(today.getTime() + 14 * 24 * 60 * 60 * 1000)
    .toISOString()
    .slice(0, 10);
  return { startDate: start, endDate: end };
}

export function useSmartCalendar(applicationId: string | undefined) {
  const [lo, setLO] = useState<AssignedLOResponse | null>(null);
  const [slots, setSlots] = useState<AvailableSlotsResponse | null>(null);
  const [hold, setHold] = useState<SlotHoldResponse | null>(null);
  const [holdSecondsRemaining, setHoldSecondsRemaining] = useState<number | null>(
    null,
  );
  const [booking, setBooking] = useState<BookingResponse | null>(null);

  const [loadingLO, setLoadingLO] = useState(false);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const holdTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ---------- load LO ----------

  const loadLO = useCallback(async () => {
    if (!applicationId) return;
    setLoadingLO(true);
    setError(null);
    try {
      const result = await posApi.getAssignedLO(applicationId);
      setLO(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not find your loan officer');
    } finally {
      setLoadingLO(false);
    }
  }, [applicationId]);

  // ---------- load slots ----------

  const loadSlots = useCallback(
    async (range: CalendarRange = defaultRange(), durationMinutes: number = 30) => {
      if (!applicationId) return;
      setLoadingSlots(true);
      setError(null);
      try {
        const tz =
          Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York';
        const result = await posApi.getAvailableSlots(applicationId, {
          start_date: range.startDate,
          end_date: range.endDate,
          duration_minutes: durationMinutes,
          timezone: tz,
        });
        setSlots(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not load times');
      } finally {
        setLoadingSlots(false);
      }
    },
    [applicationId],
  );

  // ---------- hold ----------

  const holdSlot = useCallback(
    async (slot: TimeSlot) => {
      if (!applicationId) return;
      setBusy(true);
      try {
        const h = await posApi.holdSlot(
          applicationId,
          slot.start,
          slot.end,
          Math.round(
            (new Date(slot.end).getTime() - new Date(slot.start).getTime()) / 60000,
          ),
        );
        setHold(h);
        const expiresAt = new Date(h.expires_at).getTime();
        const tick = () => {
          const remaining = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
          setHoldSecondsRemaining(remaining);
          if (remaining <= 0 && holdTimerRef.current) {
            clearInterval(holdTimerRef.current);
            holdTimerRef.current = null;
            setHold(null);
          }
        };
        if (holdTimerRef.current) clearInterval(holdTimerRef.current);
        holdTimerRef.current = setInterval(tick, 1000);
        tick();
        return h;
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not hold the slot');
      } finally {
        setBusy(false);
      }
    },
    [applicationId],
  );

  const releaseHold = useCallback(() => {
    if (holdTimerRef.current) clearInterval(holdTimerRef.current);
    holdTimerRef.current = null;
    setHold(null);
    setHoldSecondsRemaining(null);
  }, []);

  // ---------- book ----------

  const bookSlot = useCallback(
    async (
      slot: TimeSlot,
      meetingType: MeetingType,
      notes?: string,
    ): Promise<BookingResponse | null> => {
      if (!applicationId) return null;
      setBusy(true);
      setError(null);
      try {
        const tz =
          Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York';
        const result = await posApi.bookSlot({
          application_id: applicationId,
          hold_id: hold?.hold_id ?? null,
          meeting_type: meetingType,
          slot_start: slot.start,
          slot_end: slot.end,
          timezone: tz,
          notes: notes ?? null,
        });
        setBooking(result);
        releaseHold();
        return result;
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Booking failed');
        return null;
      } finally {
        setBusy(false);
      }
    },
    [applicationId, hold, releaseHold],
  );

  // ---------- cleanup ----------

  useEffect(() => {
    return () => {
      if (holdTimerRef.current) clearInterval(holdTimerRef.current);
    };
  }, []);

  return {
    lo,
    slots,
    hold,
    holdSecondsRemaining,
    booking,
    loadingLO,
    loadingSlots,
    busy,
    error,

    loadLO,
    loadSlots,
    holdSlot,
    releaseHold,
    bookSlot,
  };
}
