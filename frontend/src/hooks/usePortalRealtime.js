/**
 * usePortalRealtime — borrower portal liveness hook.
 *
 * Phase 1 (shipping now): polling-only against the already-PURL-authed
 * GET /api/purl/workspace/{slug} via api.getWorkspaceData(slug). It formalizes
 * and replaces the crude 60s setInterval that lived inline in PortalContainer.
 *
 * Why polling and not a WebSocket (Phase 1):
 *  - browsers can't attach the purl_live_* Bearer token to a WS handshake via
 *    headers, only via ?token= which leaks a long-lived token into proxy logs;
 *  - the existing /ws/loan/{loan_id} endpoint is keyed on CRM Loan.id and
 *    authorizes via a borrower JWT the PURL stack does not hold;
 *  - the loan-id bridge needed to subscribe (PURLLoan.main_loan_id) is not yet
 *    on the wire for every workspace.
 * Polling reuses the existing slug-keyed, PURL-token endpoint and the same
 * api.authToken the stack already holds — no new credential, no token in a URL.
 *
 * Contract:
 *   usePortalRealtime({ slug, token, enabled = true, intervalMs = 30000,
 *                       onUpdate, onError })
 *     -> { lastUpdatedAt, isPolling, refreshNow, transport }
 *
 * Behavior:
 *  - on mount and every intervalMs (default 30s) call api.getWorkspaceData(slug);
 *    on success call onUpdate(data) and set lastUpdatedAt;
 *  - on a 401/403 stop the loop and call onError(err) so the container can
 *    surface re-auth instead of hammering the endpoint;
 *  - pause while document.hidden and fire one immediate refresh on becoming
 *    visible again (the keep-alive analog — there is no socket to ping);
 *  - refreshNow() lets QuickActions / document-upload trigger an instant
 *    refetch after a borrower action;
 *  - transport returns 'poll' in Phase 1 ('ws' reserved for Phase 2).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';

export default function usePortalRealtime({
  slug,
  token,
  enabled = true,
  intervalMs = 30000,
  onUpdate,
  onError,
} = {}) {
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null);
  const [isPolling, setIsPolling] = useState(false);

  // Keep the latest callbacks/flags in refs so the polling loop closure stays
  // stable and we don't tear down + rebuild the interval on every render.
  const onUpdateRef = useRef(onUpdate);
  const onErrorRef = useRef(onError);
  const enabledRef = useRef(enabled);
  const stoppedRef = useRef(false); // hard-stop after an auth failure
  const inFlightRef = useRef(false); // de-dupe overlapping ticks

  useEffect(() => { onUpdateRef.current = onUpdate; }, [onUpdate]);
  useEffect(() => { onErrorRef.current = onError; }, [onError]);
  useEffect(() => { enabledRef.current = enabled; }, [enabled]);

  // Re-arm the loop whenever the workspace identity changes.
  useEffect(() => { stoppedRef.current = false; }, [slug, token]);

  const poll = useCallback(async () => {
    if (!slug) return;
    if (stoppedRef.current) return;
    if (!enabledRef.current) return;
    if (inFlightRef.current) return; // skip if a prior tick is still running

    inFlightRef.current = true;
    setIsPolling(true);
    try {
      if (token) {
        api.setAuthToken(token);
      }
      const data = await api.getWorkspaceData(slug);
      if (data) {
        setLastUpdatedAt(Date.now());
        if (onUpdateRef.current) onUpdateRef.current(data);
      }
    } catch (err) {
      const status = err?.status;
      if (status === 401 || status === 403) {
        // Auth expired / revoked: stop polling and let the container re-auth.
        stoppedRef.current = true;
      }
      if (onErrorRef.current) onErrorRef.current(err);
    } finally {
      inFlightRef.current = false;
      setIsPolling(false);
    }
  }, [slug, token]);

  // refreshNow — imperative, ignores the enabled gate intentionally so a
  // post-action refetch still lands even between ticks (but still respects the
  // hard auth-stop so we never hammer an expired token).
  const refreshNow = useCallback(() => {
    if (stoppedRef.current) return Promise.resolve();
    return poll();
  }, [poll]);

  // Interval loop + visibility pause/resume.
  useEffect(() => {
    if (!enabled || !slug) return undefined;

    let intervalId = null;

    const start = () => {
      if (intervalId != null) return;
      intervalId = setInterval(() => { poll(); }, intervalMs);
    };
    const stop = () => {
      if (intervalId != null) {
        clearInterval(intervalId);
        intervalId = null;
      }
    };

    const handleVisibility = () => {
      if (typeof document === 'undefined') return;
      if (document.hidden) {
        stop();
      } else {
        // Becoming visible: immediate refresh (keep-alive analog), then resume.
        poll();
        start();
      }
    };

    // Initial fetch + arm the loop (unless the tab is already hidden).
    poll();
    if (typeof document === 'undefined' || !document.hidden) {
      start();
    }

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibility);
    }

    return () => {
      stop();
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', handleVisibility);
      }
    };
  }, [enabled, slug, intervalMs, poll]);

  return {
    lastUpdatedAt,
    isPolling,
    refreshNow,
    transport: 'poll',
  };
}
