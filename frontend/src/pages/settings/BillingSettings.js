import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from '../../utils/toast';

const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000'
  : 'https://api.perenniaai.com';

const TIER_DISPLAY = {
  trial: { name: 'Trial', color: '#6b7280', price: 0 },
  lead_management: { name: 'Lead Management', color: '#3b82f6', price: 99 },
  lead_and_active: { name: 'Lead & Active', color: '#8b5cf6', price: 249 },
  full_pipeline: { name: 'Full Pipeline', color: '#f59e0b', price: 499 },
};

const BillingSettings = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const upgradeModule = searchParams.get('upgrade');

  const [activeTab, setActiveTab] = useState('subscription');
  const [loading, setLoading] = useState(true);
  const [subscription, setSubscription] = useState(null);
  const [features, setFeatures] = useState(null);
  const [usage, setUsage] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [changingPlan, setChangingPlan] = useState(false);
  const [selectedTier, setSelectedTier] = useState(null);

  const getAuthHeaders = useCallback(() => {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  }, []);

  const loadBillingData = useCallback(async () => {
    try {
      setLoading(true);
      const [subRes, usageRes, invoiceRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/admin/billing/subscription`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/admin/billing/usage-summary`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/admin/billing/invoices?limit=10`, { headers: getAuthHeaders() }),
      ]);

      if (subRes.ok) {
        const data = await subRes.json();
        setSubscription(data.subscription);
        setFeatures(data.features);
      }
      if (usageRes.ok) {
        const data = await usageRes.json();
        setUsage(data.usage);
      }
      if (invoiceRes.ok) {
        const data = await invoiceRes.json();
        setInvoices(data.invoices || []);
      }
    } catch (err) {
      console.error('Failed to load billing data:', err);
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders]);

  useEffect(() => {
    loadBillingData();
  }, [loadBillingData]);

  useEffect(() => {
    if (upgradeModule) {
      setActiveTab('plans');
    }
  }, [upgradeModule]);

  const handleChangePlan = async (newTier) => {
    if (changingPlan) return;
    setChangingPlan(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/billing/change-plan`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ new_tier: newTier, billing_cycle: 'monthly' }),
      });
      if (res.ok) {
        toast.success('Plan updated successfully');
        setSelectedTier(null);
        await loadBillingData();
      } else {
        const data = await res.json();
        toast.error(data.detail || 'Failed to change plan');
      }
    } catch (err) {
      toast.error('Failed to change plan');
    } finally {
      setChangingPlan(false);
    }
  };

  const currentTier = subscription?.tier || 'trial';
  const tierInfo = TIER_DISPLAY[currentTier] || TIER_DISPLAY.trial;

  if (loading) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontSize: '18px', color: '#6b7280' }}>Loading billing information...</div>
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1100px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px' }}>
        <button
          onClick={() => navigate('/settings')}
          style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: '14px', marginBottom: '8px' }}
        >
          ← Back to Settings
        </button>
        <h1 style={{ fontSize: '24px', fontWeight: '700', margin: 0 }}>Billing & Subscription</h1>
        <p style={{ color: '#6b7280', margin: '4px 0 0' }}>Manage your plan, payment methods, and invoices</p>
      </div>

      {/* Tab Navigation */}
      <div style={{ display: 'flex', gap: '0', borderBottom: '2px solid #e5e7eb', marginBottom: '24px' }}>
        {['subscription', 'plans', 'usage', 'invoices'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '10px 20px',
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: activeTab === tab ? '600' : '400',
              color: activeTab === tab ? '#3b82f6' : '#6b7280',
              borderBottom: activeTab === tab ? '2px solid #3b82f6' : '2px solid transparent',
              marginBottom: '-2px',
              textTransform: 'capitalize',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Subscription Tab */}
      {activeTab === 'subscription' && (
        <div>
          <div style={{
            background: 'white', border: '1px solid #e5e7eb', borderRadius: '12px', padding: '24px', marginBottom: '20px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <span style={{
                  display: 'inline-block', padding: '4px 12px', borderRadius: '999px',
                  background: tierInfo.color + '20', color: tierInfo.color, fontWeight: '600', fontSize: '13px',
                }}>
                  {tierInfo.name}
                </span>
                <h2 style={{ fontSize: '28px', fontWeight: '700', margin: '8px 0 0' }}>
                  ${tierInfo.price}<span style={{ fontSize: '16px', fontWeight: '400', color: '#6b7280' }}>/month</span>
                </h2>
              </div>
              <button
                onClick={() => setActiveTab('plans')}
                style={{
                  padding: '10px 20px', background: '#3b82f6', color: 'white', border: 'none',
                  borderRadius: '8px', cursor: 'pointer', fontWeight: '500', fontSize: '14px',
                }}
              >
                Change Plan
              </button>
            </div>
            {subscription && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px', marginTop: '16px' }}>
                <div>
                  <div style={{ fontSize: '12px', color: '#6b7280', textTransform: 'uppercase' }}>Status</div>
                  <div style={{ fontWeight: '600', color: subscription.status === 'active' ? '#10b981' : '#f59e0b' }}>
                    {subscription.status || 'Active'}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '12px', color: '#6b7280', textTransform: 'uppercase' }}>Billing Cycle</div>
                  <div style={{ fontWeight: '500' }}>{subscription.billing_cycle || 'Monthly'}</div>
                </div>
                <div>
                  <div style={{ fontSize: '12px', color: '#6b7280', textTransform: 'uppercase' }}>Next Payment</div>
                  <div style={{ fontWeight: '500' }}>{subscription.current_period_end || '-'}</div>
                </div>
              </div>
            )}
          </div>

          {/* Features */}
          {features && (
            <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: '12px', padding: '24px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '12px' }}>Included Features</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                {Object.entries(features).map(([key, value]) => (
                  <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 0' }}>
                    <span style={{ color: value ? '#10b981' : '#d1d5db', fontSize: '16px' }}>
                      {value ? '\u2713' : '\u2717'}
                    </span>
                    <span style={{ fontSize: '14px', color: value ? '#111827' : '#9ca3af' }}>
                      {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Plans Tab */}
      {activeTab === 'plans' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px' }}>
          {Object.entries(TIER_DISPLAY).filter(([k]) => k !== 'trial').map(([tier, info]) => {
            const isCurrent = tier === currentTier;
            return (
              <div key={tier} style={{
                background: 'white', border: isCurrent ? `2px solid ${info.color}` : '1px solid #e5e7eb',
                borderRadius: '12px', padding: '24px', position: 'relative',
              }}>
                {isCurrent && (
                  <div style={{
                    position: 'absolute', top: '-12px', left: '50%', transform: 'translateX(-50%)',
                    background: info.color, color: 'white', padding: '2px 12px', borderRadius: '999px',
                    fontSize: '11px', fontWeight: '600',
                  }}>
                    CURRENT PLAN
                  </div>
                )}
                <h3 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '4px' }}>{info.name}</h3>
                <div style={{ fontSize: '32px', fontWeight: '700', marginBottom: '16px' }}>
                  ${info.price}<span style={{ fontSize: '14px', fontWeight: '400', color: '#6b7280' }}>/mo</span>
                </div>
                <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 20px', fontSize: '13px', lineHeight: '2' }}>
                  {tier === 'lead_management' && (
                    <>
                      <li>Lead tracking & scoring</li>
                      <li>Basic reporting</li>
                      <li>Email integration</li>
                      <li>Up to 5 users</li>
                    </>
                  )}
                  {tier === 'lead_and_active' && (
                    <>
                      <li>Everything in Lead Management</li>
                      <li>Loan pipeline management</li>
                      <li>AI assistant</li>
                      <li>Partner portals</li>
                      <li>Up to 25 users</li>
                    </>
                  )}
                  {tier === 'full_pipeline' && (
                    <>
                      <li>Everything in Lead & Active</li>
                      <li>Advanced analytics</li>
                      <li>White-label branding</li>
                      <li>API access</li>
                      <li>Unlimited users</li>
                    </>
                  )}
                </ul>
                <button
                  onClick={() => {
                    if (!isCurrent) {
                      setSelectedTier(tier);
                    }
                  }}
                  disabled={isCurrent || changingPlan}
                  style={{
                    width: '100%', padding: '10px', border: isCurrent ? '1px solid #d1d5db' : 'none',
                    background: isCurrent ? 'white' : info.color, color: isCurrent ? '#6b7280' : 'white',
                    borderRadius: '8px', cursor: isCurrent ? 'default' : 'pointer', fontWeight: '500',
                    fontSize: '14px',
                  }}
                >
                  {isCurrent ? 'Current Plan' : `${info.price > tierInfo.price ? 'Upgrade' : 'Switch'} to ${info.name}`}
                </button>
              </div>
            );
          })}

          {/* Confirmation Modal */}
          {selectedTier && (
            <div style={{
              position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
              background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              zIndex: 1000,
            }}>
              <div style={{
                background: 'white', borderRadius: '12px', padding: '32px', maxWidth: '440px', width: '90%',
              }}>
                <h3 style={{ margin: '0 0 12px', fontSize: '18px' }}>Confirm Plan Change</h3>
                <p style={{ color: '#6b7280', margin: '0 0 20px', fontSize: '14px' }}>
                  Change from <strong>{tierInfo.name}</strong> to <strong>{TIER_DISPLAY[selectedTier]?.name}</strong>?
                  Your billing will be prorated automatically.
                </p>
                <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                  <button
                    onClick={() => setSelectedTier(null)}
                    style={{
                      padding: '10px 20px', background: '#f3f4f6', border: 'none', borderRadius: '8px',
                      cursor: 'pointer', fontSize: '14px',
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => handleChangePlan(selectedTier)}
                    disabled={changingPlan}
                    style={{
                      padding: '10px 20px', background: '#3b82f6', color: 'white', border: 'none',
                      borderRadius: '8px', cursor: 'pointer', fontWeight: '500', fontSize: '14px',
                    }}
                  >
                    {changingPlan ? 'Processing...' : 'Confirm Change'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Usage Tab */}
      {activeTab === 'usage' && (
        <div>
          <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: '12px', padding: '24px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '16px' }}>Current Period Usage</h3>
            {usage ? (
              <div style={{ display: 'grid', gap: '16px' }}>
                {Object.entries(usage).map(([key, val]) => {
                  const used = typeof val === 'object' ? val.used || val.count || 0 : val;
                  const limit = typeof val === 'object' ? val.limit || val.max || 100 : 100;
                  const pct = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;
                  return (
                    <div key={key}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span style={{ fontSize: '14px', fontWeight: '500' }}>
                          {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </span>
                        <span style={{ fontSize: '13px', color: '#6b7280' }}>
                          {typeof used === 'number' ? used.toLocaleString() : used} / {typeof limit === 'number' ? limit.toLocaleString() : limit}
                        </span>
                      </div>
                      <div style={{ height: '8px', background: '#f3f4f6', borderRadius: '4px', overflow: 'hidden' }}>
                        <div style={{
                          height: '100%', borderRadius: '4px', width: `${pct}%`,
                          background: pct > 90 ? '#ef4444' : pct > 70 ? '#f59e0b' : '#10b981',
                          transition: 'width 0.3s',
                        }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p style={{ color: '#6b7280', fontSize: '14px' }}>No usage data available for current period.</p>
            )}
          </div>
        </div>
      )}

      {/* Invoices Tab */}
      {activeTab === 'invoices' && (
        <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: '12px', overflow: 'hidden' }}>
          <div style={{ padding: '16px 24px', borderBottom: '1px solid #e5e7eb' }}>
            <h3 style={{ fontSize: '16px', fontWeight: '600', margin: 0 }}>Invoice History</h3>
          </div>
          {invoices.length > 0 ? (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#f9fafb' }}>
                  <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: '12px', color: '#6b7280', fontWeight: '500', textTransform: 'uppercase' }}>Invoice</th>
                  <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: '12px', color: '#6b7280', fontWeight: '500', textTransform: 'uppercase' }}>Date</th>
                  <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: '12px', color: '#6b7280', fontWeight: '500', textTransform: 'uppercase' }}>Amount</th>
                  <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: '12px', color: '#6b7280', fontWeight: '500', textTransform: 'uppercase' }}>Status</th>
                  <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: '12px', color: '#6b7280', fontWeight: '500', textTransform: 'uppercase' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((inv, i) => (
                  <tr key={inv.id || i} style={{ borderTop: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '12px 16px', fontSize: '14px', fontWeight: '500' }}>{inv.invoice_number || `INV-${inv.id}`}</td>
                    <td style={{ padding: '12px 16px', fontSize: '14px', color: '#6b7280' }}>{inv.created_at ? new Date(inv.created_at).toLocaleDateString() : '-'}</td>
                    <td style={{ padding: '12px 16px', fontSize: '14px', fontWeight: '500' }}>${(inv.total_amount || 0).toFixed(2)}</td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{
                        display: 'inline-block', padding: '2px 8px', borderRadius: '999px', fontSize: '12px',
                        fontWeight: '500',
                        background: inv.status === 'paid' ? '#d1fae5' : inv.status === 'open' ? '#fef3c7' : '#f3f4f6',
                        color: inv.status === 'paid' ? '#065f46' : inv.status === 'open' ? '#92400e' : '#6b7280',
                      }}>
                        {inv.status || 'pending'}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                      {inv.pdf_url && (
                        <a href={inv.pdf_url} target="_blank" rel="noopener noreferrer"
                          style={{ color: '#3b82f6', textDecoration: 'none', fontSize: '13px' }}>
                          Download
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ padding: '40px', textAlign: 'center', color: '#6b7280', fontSize: '14px' }}>
              No invoices found. Invoices will appear here once billing is active.
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default BillingSettings;
