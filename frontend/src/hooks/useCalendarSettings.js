/**
 * Perennia AI - useCalendarSettings Hook
 *
 * Manages calendar settings state with API persistence.
 * Supports section-level loading, saving, auto-save with debounce,
 * dirty tracking, and error rollback.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { calendarSettingsAPI } from '../services/api';

const DEBOUNCE_MS = 1500;

const SECTION_LOADERS = {
  availability: () => calendarSettingsAPI.getAvailability(),
  appointmentTypes: () => calendarSettingsAPI.getAppointmentTypes(),
  bookingPage: () => calendarSettingsAPI.getBookingPage(),
  notifications: () => calendarSettingsAPI.getNotifications(),
  integrations: () => calendarSettingsAPI.getIntegrations(),
  team: () => calendarSettingsAPI.getTeam(),
};

const SECTION_SAVERS = {
  availability: (data) => calendarSettingsAPI.updateAvailability(data),
  appointmentTypes: (data) => calendarSettingsAPI.updateAppointmentTypes(data),
  bookingPage: (data) => calendarSettingsAPI.updateBookingPage(data),
  notifications: (data) => calendarSettingsAPI.updateNotifications(data),
  integrations: (data) => calendarSettingsAPI.updateIntegrations(data),
  team: (data) => calendarSettingsAPI.updateTeam(data),
};

/**
 * @param {string[]} sections - Which sections to load on mount (e.g. ['availability', 'notifications'])
 * @param {Object} options
 * @param {boolean} options.autoSave - Enable auto-save on changes (default false)
 * @param {number} options.debounceMs - Debounce delay for auto-save
 */
export default function useCalendarSettings(sections = [], options = {}) {
  const { autoSave = false, debounceMs = DEBOUNCE_MS } = options;

  const [settings, setSettings] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [dirtyFields, setDirtyFields] = useState(new Set());

  // Snapshot for rollback on save failure
  const snapshotRef = useRef({});
  const debounceTimerRef = useRef(null);

  // -------------------------------------------------------------------------
  // Load settings on mount
  // -------------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);

      const results = {};
      const loads = sections.map(async (section) => {
        const loader = SECTION_LOADERS[section];
        if (!loader) return;
        try {
          const response = await loader();
          results[section] = response?.data ?? null;
        } catch (err) {
          console.error(`Failed to load ${section}:`, err);
          results[section] = null;
        }
      });

      await Promise.all(loads);

      if (!cancelled) {
        setSettings(results);
        snapshotRef.current = JSON.parse(JSON.stringify(results));
        setLoading(false);
      }
    }

    if (sections.length > 0) {
      load();
    } else {
      setLoading(false);
    }

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -------------------------------------------------------------------------
  // Update a section locally (mark dirty)
  // -------------------------------------------------------------------------
  const updateSection = useCallback((section, data) => {
    setSettings((prev) => ({
      ...prev,
      [section]: { ...prev[section], ...data },
    }));
    setDirtyFields((prev) => new Set(prev).add(section));
  }, []);

  // -------------------------------------------------------------------------
  // Save a section to the API
  // -------------------------------------------------------------------------
  const saveSection = useCallback(async (section) => {
    const saver = SECTION_SAVERS[section];
    if (!saver) {
      throw new Error(`Unknown section: ${section}`);
    }

    setSaving(true);
    setError(null);

    // Take snapshot before save for rollback
    const previousData = snapshotRef.current[section];

    try {
      await saver(settings[section]);
      // Update snapshot on success
      snapshotRef.current[section] = JSON.parse(JSON.stringify(settings[section]));
      // Clear dirty flag
      setDirtyFields((prev) => {
        const next = new Set(prev);
        next.delete(section);
        return next;
      });
    } catch (err) {
      // Rollback local state on failure
      setSettings((prev) => ({
        ...prev,
        [section]: previousData != null ? JSON.parse(JSON.stringify(previousData)) : prev[section],
      }));
      setError(err);
      throw err;
    } finally {
      setSaving(false);
    }
  }, [settings]);

  // -------------------------------------------------------------------------
  // Auto-save with debounce
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (!autoSave || dirtyFields.size === 0) return;

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(() => {
      dirtyFields.forEach((section) => {
        saveSection(section).catch(() => {
          // Error already set in saveSection
        });
      });
    }, debounceMs);

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [autoSave, dirtyFields, debounceMs, saveSection]);

  // -------------------------------------------------------------------------
  // Dirty tracking
  // -------------------------------------------------------------------------
  const isDirty = dirtyFields.size > 0;
  const isSectionDirty = useCallback((section) => dirtyFields.has(section), [dirtyFields]);

  return {
    settings,
    loading,
    saving,
    error,
    isDirty,
    isSectionDirty,
    updateSection,
    saveSection,
  };
}
