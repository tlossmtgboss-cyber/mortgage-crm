/**
 * Webhook Health Dashboard
 * Shows the status of all webhook subscriptions with retry controls.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../../services/api';

function WebhookHealthDashboard() {
  const [webhooks, setWebhooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState(null);

  const loadWebhooks = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE_URL}/api/v1/scheduler/webhooks/health`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setWebhooks(data.subscriptions || []);
      }
    } catch (err) {
      console.warn('Could not load webhook health:', err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadWebhooks(); }, [loadWebhooks]);

  const retryFailed = useCallback(async (deliveryId) => {
    setRetrying(deliveryId);
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE_URL}/api/v1/scheduler/webhooks/deliveries/${deliveryId}/retry`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      await loadWebhooks();
    } catch (err) {
      console.error('Retry failed:', err);
    } finally {
      setRetrying(null);
    }
  }, [loadWebhooks]);

  if (loading) return <div style={{ padding: 20, color: '#94a3b8' }}>Loading webhook status...</div>;
  if (webhooks.length === 0) return <div style={{ padding: 20, color: '#94a3b8' }}>No webhook subscriptions configured.</div>;

  return (
    <div className="webhook-health-dashboard">
      <h3 style={{ marginBottom: 16 }}>Webhook Health</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {webhooks.map((wh) => {
          const statusColor = wh.status === 'healthy' ? '#22c55e' : wh.status === 'degraded' ? '#f59e0b' : '#ef4444';
          let hostname = 'Webhook';
          try {
            if (wh.target_url) hostname = new URL(wh.target_url).hostname;
          } catch (_) {
            // target_url may not be a valid URL
          }
          return (
            <div key={wh.subscription_id || wh.target_url || hostname} style={{
              background: '#f8fafc',
              border: `1px solid ${wh.status === 'unhealthy' ? '#fecaca' : '#e2e8f0'}`,
              borderRadius: 8,
              padding: 16,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{
                    width: 10, height: 10, borderRadius: '50%',
                    background: statusColor,
                  }} />
                  <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>
                    {hostname}
                  </span>
                </div>
                <span style={{ fontSize: '0.8rem', color: statusColor, fontWeight: 600 }}>
                  {wh.success_rate != null ? `${wh.success_rate}% success` : '--'}
                </span>
              </div>
              <div style={{ marginTop: 8, fontSize: '0.82rem', color: '#64748b' }}>
                {wh.total_deliveries_24h != null ? wh.total_deliveries_24h : 0} deliveries in last 24h
                {wh.failed_24h > 0 && (
                  <span style={{ color: '#ef4444' }}> ({wh.failed_24h} failed)</span>
                )}
              </div>
              {wh.last_failure && (
                <div style={{ marginTop: 4, fontSize: '0.8rem', color: '#94a3b8' }}>
                  Last failure: {new Date(wh.last_failure).toLocaleString()}
                </div>
              )}
              {wh.status === 'unhealthy' && (
                <button
                  onClick={() => retryFailed(wh.subscription_id)}
                  disabled={retrying === wh.subscription_id}
                  style={{
                    marginTop: 8,
                    background: '#ef4444',
                    color: '#fff',
                    border: 'none',
                    borderRadius: 4,
                    padding: '6px 14px',
                    cursor: 'pointer',
                    fontSize: '0.82rem',
                  }}
                >
                  {retrying === wh.subscription_id ? 'Retrying...' : 'Retry Failed Deliveries'}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default React.memo(WebhookHealthDashboard);
