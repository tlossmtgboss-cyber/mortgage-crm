/**
 * usePOSApplication — manages the borrower's draft application.
 *
 * Provides:
 *   - the current ApplicationResponse
 *   - per-section autosave (debounced 800ms after the last keystroke)
 *   - explicit `markComplete` to advance steps
 *   - submit flow
 *
 * The hook is intentionally minimal — no Redux, no React Query. If your
 * portal already uses RQ, swap the internals; the public API stays the same.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { posApi, APIError } from '../api';
import type {
  ApplicationResponse,
  ApplicationSubmitRequest,
  ApplicationSubmitResponse,
  SectionKey,
  SectionResponse,
  SectionUpdateRequest,
} from '../types';

const AUTOSAVE_DELAY_MS = 800;

export type SaveState = 'idle' | 'saving' | 'saved' | 'error';

export function usePOSApplication(loanId?: number) {
  const [application, setApplication] = useState<ApplicationResponse | null>(null);
  const [sections, setSections] = useState<Partial<Record<SectionKey, SectionResponse>>>({});
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [error, setError] = useState<string | null>(null);

  // Autosave debounce timers per section.
  const timersRef = useRef<Partial<Record<SectionKey, ReturnType<typeof setTimeout>>>>({});

  // Track whether there are unsaved changes (pending debounce or active save).
  const dirtyRef = useRef(false);

  // Sequence counter to prevent stale autosave responses from overwriting newer data.
  const saveSeqRef = useRef(0);

  // ---------- beforeunload guard ----------
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []);

  // ---------- bootstrap ----------

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const app = await posApi.getOrStart(loanId);
        if (!cancelled) {
          setApplication(app);
          setLoading(false);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load application');
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      // Cancel any in-flight autosave timers.
      Object.values(timersRef.current).forEach(t => t && clearTimeout(t));
    };
  }, [loanId]);

  // ---------- section read ----------

  const loadSection = useCallback(
    async (sectionKey: SectionKey) => {
      if (!application) return;
      // schedule and review are UI-only steps with no backend section data.
      if (sectionKey === 'schedule') return;
      try {
        const section = await posApi.getSection(application.id, sectionKey);
        setSections(prev => ({ ...prev, [sectionKey]: section }));
        return section;
      } catch (e) {
        // Don't promote a per-section 401/403 to the global error state once
        // the application has loaded. /applications/me already proved the
        // token works; a section-scoped auth failure is either transient or
        // a backend issue specific to that endpoint, and bouncing the user
        // back to the signup screen would just wipe their session for no
        // reason. Retry once after a short delay before giving up silently.
        if (e instanceof APIError && [401, 403].includes(e.status)) {
          console.warn('Section auth failed, retrying once', sectionKey, e.status);
          try {
            await new Promise(r => setTimeout(r, 400));
            const section = await posApi.getSection(application.id, sectionKey);
            setSections(prev => ({ ...prev, [sectionKey]: section }));
            return section;
          } catch (retryErr) {
            console.error('Section auth failed after retry', sectionKey, retryErr);
            return;
          }
        }
        console.error('Failed to load section', sectionKey, e);
        if (e instanceof APIError && e.status === 400) {
          setError(e.message);
        }
      }
    },
    [application],
  );

  // ---------- autosave ----------

  const saveSection = useCallback(
    async (sectionKey: SectionKey, body: SectionUpdateRequest) => {
      if (!application) return;
      // Back up to localStorage before network save so data survives failures.
      try {
        localStorage.setItem(
          `pos_draft_${application.id}_${sectionKey}`,
          JSON.stringify(body.data),
        );
      } catch (_) { /* quota exceeded — best effort */ }
      const seq = ++saveSeqRef.current;
      setSaveState('saving');
      try {
        const section = await posApi.updateSection(application.id, sectionKey, body);
        if (seq === saveSeqRef.current) {
          setSections(prev => ({ ...prev, [sectionKey]: section }));
          if (section.application) {
            setApplication(section.application);
          }
          dirtyRef.current = Object.values(timersRef.current).some(t => t != null);
          setSaveState('saved');
          // Clear draft backup on successful save.
          try { localStorage.removeItem(`pos_draft_${application.id}_${sectionKey}`); } catch {}
          setTimeout(() => setSaveState(prev => (prev === 'saved' ? 'idle' : prev)), 2000);
        }
        return section;
      } catch (e) {
        // Keep dirtyRef true — data is still unsaved.
        setSaveState('error');
        setError(e instanceof Error ? e.message : 'Save failed');
      }
    },
    [application],
  );

  const updateSectionData = useCallback(
    (sectionKey: SectionKey, data: Record<string, unknown>) => {
      // Optimistic update.
      setSections(prev => ({
        ...prev,
        [sectionKey]: {
          ...(prev[sectionKey] || {
            section_key: sectionKey,
            data: {},
            is_complete: false,
            completed_at: null,
            updated_at: new Date().toISOString(),
            has_ssn: false,
            has_co_ssn: false,
            has_dob: false,
          }),
          data,
        } as SectionResponse,
      }));

      // Debounced save.
      const existing = timersRef.current[sectionKey];
      if (existing) clearTimeout(existing);
      dirtyRef.current = true;
      const lastUpdated = sections[sectionKey]?.updated_at;
      timersRef.current[sectionKey] = setTimeout(() => {
        saveSection(sectionKey, {
          data,
          mark_complete: false,
          expected_updated_at: lastUpdated,
        });
      }, AUTOSAVE_DELAY_MS);
    },
    [saveSection, sections],
  );

  const markComplete = useCallback(
    async (sectionKey: SectionKey) => {
      if (!application) return;
      let current = sections[sectionKey];
      if (!current) {
        current = await loadSection(sectionKey);
      }
      if (!current) return;
      // Cancel any pending autosave for this section — we'll save with
      // mark_complete=true instead.
      const t = timersRef.current[sectionKey];
      if (t) clearTimeout(t);
      return saveSection(sectionKey, {
        data: current.data || {},
        mark_complete: true,
      });
    },
    [application, sections, saveSection, loadSection],
  );

  // ---------- submit ----------

  const submit = useCallback(
    async (body: ApplicationSubmitRequest): Promise<ApplicationSubmitResponse | null> => {
      if (!application) return null;
      setSaveState('saving');
      try {
        const resp = await posApi.submit(application.id, body);
        // Refresh application shell.
        const app = await posApi.getApplication(application.id);
        setApplication(app);
        setSaveState('saved');
        return resp;
      } catch (e) {
        setSaveState('error');
        if (e instanceof APIError) {
          setError(e.detail);
        } else {
          setError(e instanceof Error ? e.message : 'Submit failed');
        }
        return null;
      }
    },
    [application],
  );

  return {
    application,
    sections,
    loading,
    error,
    saveState,
    loadSection,
    updateSectionData,
    markComplete,
    submit,
  };
}
