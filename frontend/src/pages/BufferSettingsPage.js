import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'react-toastify';
import BufferTimeSettings from '../components/calendar/BufferTimeSettings';
import api from '../services/api';

/**
 * BufferSettingsPage - Standalone page wrapper for BufferTimeSettings.
 * Route: /calendar/buffer-settings
 *
 * Manages its own state and saves changes back to the scheduler config API.
 */
export default function BufferSettingsPage() {
  const [settings, setSettings] = useState({
    buffer_minutes: 5,
    min_booking_notice_hours: 2,
    max_advance_booking_days: 60,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetchSettings = useCallback(async () => {
    try {
      // TODO: Replace with real endpoint when available (e.g., schedulerAPI.getConfig)
      const response = await api.get('/api/v1/scheduler/config');
      const data = response.data;
      setSettings({
        buffer_minutes: data.buffer_minutes ?? 5,
        min_booking_notice_hours: data.min_booking_notice_hours ?? 2,
        max_advance_booking_days: data.max_advance_booking_days ?? 60,
      });
    } catch (err) {
      // Use defaults if endpoint not available
      console.warn('Could not load buffer settings, using defaults:', err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const handleChange = useCallback((field, value) => {
    setSettings((prev) => ({ ...prev, [field]: value }));
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      // TODO: Replace with real endpoint when available
      await api.put('/api/v1/scheduler/config', settings);
      toast.success('Buffer settings saved');
    } catch (err) {
      toast.error('Failed to save settings');
      console.error('Save buffer settings failed:', err);
    } finally {
      setSaving(false);
    }
  }, [settings]);

  if (loading) {
    return (
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '24px 16px' }}>
        <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>Loading settings...</div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '24px 16px' }}>
      <div style={{ marginBottom: 16 }}>
        <Link
          to="/calendar-settings"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 14,
            color: '#3b82f6',
            textDecoration: 'none',
          }}
        >
          &larr; Back to Calendar Settings
        </Link>
      </div>

      <h1 style={{ fontSize: 22, fontWeight: 600, color: '#1e293b', marginBottom: 4 }}>
        Buffer &amp; Booking Settings
      </h1>
      <p style={{ fontSize: 14, color: '#6b7280', marginBottom: 24 }}>
        Configure buffer time between meetings and booking windows for your calendar.
      </p>

      <div
        style={{
          background: '#fff',
          border: '1px solid #e5e7eb',
          borderRadius: 12,
          padding: 24,
          marginBottom: 20,
        }}
      >
        <BufferTimeSettings
          bufferMinutes={settings.buffer_minutes}
          minNoticeHours={settings.min_booking_notice_hours}
          maxAdvanceDays={settings.max_advance_booking_days}
          onChange={handleChange}
        />
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            padding: '10px 24px',
            borderRadius: 8,
            border: 'none',
            backgroundColor: '#2563eb',
            color: '#fff',
            fontSize: 14,
            fontWeight: 500,
            cursor: saving ? 'not-allowed' : 'pointer',
            opacity: saving ? 0.6 : 1,
          }}
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}
