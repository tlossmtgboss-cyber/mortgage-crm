import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

// ============================================================================
// CONSTANTS
// ============================================================================

const STATUS_COLORS = {
  draft: { bg: '#f3f4f6', color: '#374151', border: '#d1d5db', label: 'Draft' },
  active: { bg: '#dcfce7', color: '#166534', border: '#86efac', label: 'Active' },
  completed: { bg: '#dbeafe', color: '#1d4ed8', border: '#93c5fd', label: 'Completed' },
};

const ELEMENT_LABELS = {
  headline: 'Headline',
  cta_button: 'CTA Button',
  layout: 'Layout',
  color_scheme: 'Color Scheme',
};

const ELEMENT_TYPES = ['headline', 'cta_button', 'layout', 'color_scheme'];

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

const StatusBadge = ({ status }) => {
  const config = STATUS_COLORS[status] || STATUS_COLORS.draft;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        fontSize: '12px',
        fontWeight: 600,
        padding: '3px 10px',
        borderRadius: '9999px',
        backgroundColor: config.bg,
        color: config.color,
        border: `1px solid ${config.border}`,
        whiteSpace: 'nowrap',
      }}
    >
      <span
        style={{
          width: '6px', height: '6px', borderRadius: '50%',
          backgroundColor: config.color, flexShrink: 0,
        }}
        aria-hidden="true"
      />
      {config.label}
    </span>
  );
};

const ConfidenceMeter = ({ confidence, isSignificant }) => {
  const barWidth = Math.min(confidence, 100);
  const barColor = isSignificant ? '#16a34a' : confidence > 80 ? '#f59e0b' : '#9ca3af';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div
        style={{
          flex: 1, height: '8px', backgroundColor: '#f3f4f6',
          borderRadius: '4px', overflow: 'hidden', minWidth: '100px',
        }}
      >
        <div
          style={{
            width: `${barWidth}%`, height: '100%',
            backgroundColor: barColor, borderRadius: '4px',
            transition: 'width 0.3s ease',
          }}
        />
      </div>
      <span style={{ fontSize: '13px', fontWeight: 600, color: barColor, minWidth: '50px' }}>
        {confidence.toFixed(1)}%
      </span>
    </div>
  );
};

const VariantCard = ({ label, data, isWinner, variantConfig }) => {
  const borderColor = isWinner ? '#16a34a' : '#e5e7eb';
  const headerBg = isWinner ? '#f0fdf4' : '#fafafa';

  return (
    <div
      style={{
        flex: 1, border: `2px solid ${borderColor}`, borderRadius: '8px',
        overflow: 'hidden', minWidth: '200px',
      }}
    >
      <div
        style={{
          padding: '10px 14px', backgroundColor: headerBg,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          borderBottom: '1px solid #e5e7eb',
        }}
      >
        <span style={{ fontWeight: 700, fontSize: '15px', color: '#111827' }}>
          Variant {label}
        </span>
        {isWinner && (
          <span
            style={{
              fontSize: '11px', fontWeight: 700, color: '#166534',
              backgroundColor: '#dcfce7', padding: '2px 8px', borderRadius: '4px',
            }}
          >
            WINNER
          </span>
        )}
      </div>
      <div style={{ padding: '14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '13px', color: '#6b7280' }}>Impressions</span>
          <span style={{ fontSize: '14px', fontWeight: 600 }}>{(data.impressions || 0).toLocaleString()}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '13px', color: '#6b7280' }}>Bookings</span>
          <span style={{ fontSize: '14px', fontWeight: 600 }}>{(data.bookings || 0).toLocaleString()}</span>
        </div>
        <div
          style={{
            display: 'flex', justifyContent: 'space-between', padding: '8px 0',
            borderTop: '1px solid #f3f4f6',
          }}
        >
          <span style={{ fontSize: '13px', color: '#6b7280' }}>Conversion Rate</span>
          <span style={{ fontSize: '16px', fontWeight: 700, color: isWinner ? '#166534' : '#111827' }}>
            {(data.conversion_rate || 0).toFixed(2)}%
          </span>
        </div>
        {variantConfig && Object.keys(variantConfig).length > 0 && (
          <div
            style={{
              marginTop: '8px', padding: '8px', backgroundColor: '#f9fafb',
              borderRadius: '6px', fontSize: '12px', color: '#6b7280',
            }}
          >
            {Object.entries(variantConfig).map(([key, value]) => (
              <div key={key} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                <span>{key}:</span>
                <span style={{ fontWeight: 500, color: '#374151' }}>{String(value)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};


// ============================================================================
// CREATE TEST FORM
// ============================================================================

const CreateTestForm = ({ token, onCreated, onCancel }) => {
  const [form, setForm] = useState({
    name: '',
    description: '',
    element_type: 'headline',
    variant_a: '{}',
    variant_b: '{}',
    traffic_split: 50,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    let parsedA, parsedB;
    try {
      parsedA = JSON.parse(form.variant_a);
    } catch {
      setError('Variant A config must be valid JSON');
      return;
    }
    try {
      parsedB = JSON.parse(form.variant_b);
    } catch {
      setError('Variant B config must be valid JSON');
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/ab-tests`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: form.name,
          description: form.description || null,
          element_type: form.element_type,
          variant_a: parsedA,
          variant_b: parsedB,
          traffic_split: form.traffic_split,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to create test');
      }
      onCreated(data.test);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const inputStyle = {
    width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
    borderRadius: '6px', fontSize: '14px', boxSizing: 'border-box',
  };
  const labelStyle = { display: 'block', fontSize: '13px', fontWeight: 600, color: '#374151', marginBottom: '4px' };

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        padding: '20px', backgroundColor: '#ffffff', border: '1px solid #e5e7eb',
        borderRadius: '8px', marginBottom: '20px',
      }}
    >
      <h3 style={{ margin: '0 0 16px', fontSize: '16px', fontWeight: 700 }}>Create New A/B Test</h3>

      {error && (
        <div
          style={{
            padding: '10px 14px', backgroundColor: '#fef2f2', color: '#991b1b',
            borderRadius: '6px', marginBottom: '14px', fontSize: '13px',
          }}
        >
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
        <div>
          <label style={labelStyle}>Test Name</label>
          <input
            style={inputStyle}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g., CTA Button Color Test"
            required
          />
        </div>
        <div>
          <label style={labelStyle}>Element Type</label>
          <select
            style={inputStyle}
            value={form.element_type}
            onChange={(e) => setForm({ ...form, element_type: e.target.value })}
          >
            {ELEMENT_TYPES.map((t) => (
              <option key={t} value={t}>{ELEMENT_LABELS[t]}</option>
            ))}
          </select>
        </div>
      </div>

      <div style={{ marginBottom: '14px' }}>
        <label style={labelStyle}>Description (optional)</label>
        <input
          style={inputStyle}
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          placeholder="What are you testing?"
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
        <div>
          <label style={labelStyle}>Variant A Config (JSON)</label>
          <textarea
            style={{ ...inputStyle, height: '80px', fontFamily: 'monospace', fontSize: '13px' }}
            value={form.variant_a}
            onChange={(e) => setForm({ ...form, variant_a: e.target.value })}
            placeholder='{"text": "Book Now", "color": "#2563eb"}'
          />
        </div>
        <div>
          <label style={labelStyle}>Variant B Config (JSON)</label>
          <textarea
            style={{ ...inputStyle, height: '80px', fontFamily: 'monospace', fontSize: '13px' }}
            value={form.variant_b}
            onChange={(e) => setForm({ ...form, variant_b: e.target.value })}
            placeholder='{"text": "Schedule Today", "color": "#16a34a"}'
          />
        </div>
      </div>

      <div style={{ marginBottom: '18px' }}>
        <label style={labelStyle}>Traffic Split (% to Variant A): {form.traffic_split}%</label>
        <input
          type="range"
          min="1"
          max="99"
          value={form.traffic_split}
          onChange={(e) => setForm({ ...form, traffic_split: parseInt(e.target.value, 10) })}
          style={{ width: '100%' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#9ca3af' }}>
          <span>Variant A: {form.traffic_split}%</span>
          <span>Variant B: {100 - form.traffic_split}%</span>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
        <button
          type="button"
          onClick={onCancel}
          style={{
            padding: '8px 16px', fontSize: '14px', borderRadius: '6px',
            border: '1px solid #d1d5db', backgroundColor: '#ffffff', cursor: 'pointer',
          }}
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting || !form.name.trim()}
          style={{
            padding: '8px 16px', fontSize: '14px', fontWeight: 600, borderRadius: '6px',
            border: 'none', backgroundColor: '#2563eb', color: '#ffffff',
            cursor: submitting ? 'not-allowed' : 'pointer', opacity: submitting ? 0.6 : 1,
          }}
        >
          {submitting ? 'Creating...' : 'Create Test'}
        </button>
      </div>
    </form>
  );
};


// ============================================================================
// TEST RESULTS PANEL
// ============================================================================

const TestResultsPanel = ({ test, token }) => {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchResults = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/ab-tests/${test.id}/results`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to fetch results');
      setResults(data.results);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [test.id, token]);

  useEffect(() => {
    fetchResults();
  }, [fetchResults]);

  if (loading) {
    return (
      <div style={{ padding: '20px', textAlign: 'center', color: '#6b7280' }}>Loading results...</div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '14px', backgroundColor: '#fef2f2', color: '#991b1b', borderRadius: '6px' }}>
        {error}
      </div>
    );
  }

  if (!results) return null;

  const sig = results.significance || {};
  const testConfig = results.test_config || {};
  const isSignificant = sig.is_significant_95 || false;

  return (
    <div style={{ marginTop: '14px' }}>
      {/* Summary Stats */}
      <div
        style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
          gap: '12px', marginBottom: '16px',
        }}
      >
        <div style={{ padding: '12px', backgroundColor: '#f9fafb', borderRadius: '6px', textAlign: 'center' }}>
          <div style={{ fontSize: '20px', fontWeight: 700 }}>{(results.total_impressions || 0).toLocaleString()}</div>
          <div style={{ fontSize: '12px', color: '#6b7280' }}>Total Impressions</div>
        </div>
        <div style={{ padding: '12px', backgroundColor: '#f9fafb', borderRadius: '6px', textAlign: 'center' }}>
          <div style={{ fontSize: '20px', fontWeight: 700 }}>{(results.total_bookings || 0).toLocaleString()}</div>
          <div style={{ fontSize: '12px', color: '#6b7280' }}>Total Bookings</div>
        </div>
        <div style={{ padding: '12px', backgroundColor: '#f9fafb', borderRadius: '6px', textAlign: 'center' }}>
          <div style={{ fontSize: '20px', fontWeight: 700, color: results.lift > 0 ? '#166534' : '#374151' }}>
            {results.lift > 0 ? '+' : ''}{results.lift}%
          </div>
          <div style={{ fontSize: '12px', color: '#6b7280' }}>Conversion Lift</div>
        </div>
        <div style={{ padding: '12px', backgroundColor: '#f9fafb', borderRadius: '6px', textAlign: 'center' }}>
          <div style={{ fontSize: '20px', fontWeight: 700, color: results.relative_lift_pct > 0 ? '#166534' : '#374151' }}>
            {results.relative_lift_pct > 0 ? '+' : ''}{results.relative_lift_pct}%
          </div>
          <div style={{ fontSize: '12px', color: '#6b7280' }}>Relative Improvement</div>
        </div>
      </div>

      {/* Variant Comparison */}
      <div style={{ display: 'flex', gap: '14px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <VariantCard
          label="A"
          data={results.variants?.A || {}}
          isWinner={results.winner === 'A' && isSignificant}
          variantConfig={testConfig.variant_a}
        />
        <VariantCard
          label="B"
          data={results.variants?.B || {}}
          isWinner={results.winner === 'B' && isSignificant}
          variantConfig={testConfig.variant_b}
        />
      </div>

      {/* Statistical Significance */}
      <div
        style={{
          padding: '14px', backgroundColor: isSignificant ? '#f0fdf4' : '#fafafa',
          borderRadius: '8px', border: `1px solid ${isSignificant ? '#86efac' : '#e5e7eb'}`,
        }}
      >
        <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: '8px' }}>
          Statistical Significance
        </div>
        {sig.valid ? (
          <>
            <ConfidenceMeter confidence={sig.confidence_pct} isSignificant={isSignificant} />
            <div style={{ marginTop: '8px', fontSize: '13px', color: '#6b7280' }}>
              {isSignificant ? (
                <span style={{ color: '#166534' }}>
                  Results are statistically significant at 95% confidence.
                  {results.winner && ` Variant ${results.winner} is the winner.`}
                </span>
              ) : (
                <span>
                  Not yet significant. Continue collecting data for reliable results.
                  {sig.confidence_pct > 80 && ' Getting close -- consider running longer.'}
                </span>
              )}
            </div>
            <div style={{ marginTop: '6px', fontSize: '12px', color: '#9ca3af' }}>
              Chi-square: {sig.chi_square} | p-value: {sig.p_value}
            </div>
          </>
        ) : (
          <div style={{ fontSize: '13px', color: '#6b7280' }}>
            {sig.reason || 'Insufficient data for statistical analysis.'}
          </div>
        )}
      </div>
    </div>
  );
};


// ============================================================================
// MAIN DASHBOARD
// ============================================================================

const ABTestDashboard = ({ token }) => {
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [expandedTestId, setExpandedTestId] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [actionLoading, setActionLoading] = useState(null);

  const fetchTests = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.append('status', statusFilter);
      const url = `${API_BASE}/api/v1/scheduler/ab-tests?${params.toString()}`;

      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to fetch tests');
      setTests(data.tests || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, statusFilter]);

  useEffect(() => {
    fetchTests();
  }, [fetchTests]);

  const handleStatusChange = async (testId, newStatus) => {
    setActionLoading(testId);
    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/ab-tests/${testId}/status`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ status: newStatus }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to update status');
      fetchTests();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleTestCreated = (newTest) => {
    setShowCreate(false);
    fetchTests();
  };

  if (loading && tests.length === 0) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: '#6b7280' }}>
        Loading A/B tests...
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '900px', margin: '0 auto' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          marginBottom: '20px', flexWrap: 'wrap', gap: '10px',
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#111827' }}>
            A/B Testing
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: '14px', color: '#6b7280' }}>
            Optimize your booking page with data-driven experiments
          </p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          style={{
            padding: '8px 16px', fontSize: '14px', fontWeight: 600,
            borderRadius: '6px', border: 'none', backgroundColor: '#2563eb',
            color: '#ffffff', cursor: 'pointer',
          }}
        >
          {showCreate ? 'Cancel' : '+ New Test'}
        </button>
      </div>

      {/* Create Form */}
      {showCreate && (
        <CreateTestForm
          token={token}
          onCreated={handleTestCreated}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {/* Error */}
      {error && (
        <div
          style={{
            padding: '12px 16px', backgroundColor: '#fef2f2', color: '#991b1b',
            borderRadius: '6px', marginBottom: '14px', fontSize: '13px',
          }}
        >
          {error}
          <button
            onClick={() => setError(null)}
            style={{
              float: 'right', background: 'none', border: 'none',
              color: '#991b1b', cursor: 'pointer', fontWeight: 700,
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Status Filter */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        {['', 'draft', 'active', 'completed'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            style={{
              padding: '6px 14px', fontSize: '13px', fontWeight: 500,
              borderRadius: '6px', cursor: 'pointer',
              border: '1px solid',
              borderColor: statusFilter === s ? '#2563eb' : '#d1d5db',
              backgroundColor: statusFilter === s ? '#eff6ff' : '#ffffff',
              color: statusFilter === s ? '#2563eb' : '#374151',
            }}
          >
            {s ? (STATUS_COLORS[s]?.label || s) : 'All'}
          </button>
        ))}
      </div>

      {/* Tests List */}
      {tests.length === 0 ? (
        <div
          style={{
            padding: '40px', textAlign: 'center', backgroundColor: '#f9fafb',
            borderRadius: '8px', color: '#6b7280',
          }}
        >
          <div style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>No A/B tests found</div>
          <div style={{ fontSize: '14px' }}>Create your first test to start optimizing your booking page.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {tests.map((test) => {
            const isExpanded = expandedTestId === test.id;
            return (
              <div
                key={test.id}
                style={{
                  border: '1px solid #e5e7eb', borderRadius: '8px',
                  backgroundColor: '#ffffff', overflow: 'hidden',
                }}
              >
                {/* Test Header */}
                <div
                  onClick={() => setExpandedTestId(isExpanded ? null : test.id)}
                  style={{
                    padding: '14px 18px', cursor: 'pointer',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    borderBottom: isExpanded ? '1px solid #e5e7eb' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
                    <span style={{ fontWeight: 600, fontSize: '15px', color: '#111827' }}>
                      {test.name}
                    </span>
                    <StatusBadge status={test.status} />
                    <span
                      style={{
                        fontSize: '12px', color: '#6b7280', backgroundColor: '#f3f4f6',
                        padding: '2px 8px', borderRadius: '4px',
                      }}
                    >
                      {ELEMENT_LABELS[test.element_type] || test.element_type}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ fontSize: '13px', color: '#6b7280' }}>
                      {(test.total_impressions || 0).toLocaleString()} views
                    </span>
                    <span style={{ fontSize: '13px', color: '#6b7280' }}>
                      {(test.total_bookings || 0).toLocaleString()} bookings
                    </span>
                    {/* Action Buttons */}
                    {test.status === 'draft' && (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleStatusChange(test.id, 'active'); }}
                        disabled={actionLoading === test.id}
                        style={{
                          padding: '4px 12px', fontSize: '12px', fontWeight: 600,
                          borderRadius: '4px', border: 'none',
                          backgroundColor: '#16a34a', color: '#ffffff', cursor: 'pointer',
                          opacity: actionLoading === test.id ? 0.6 : 1,
                        }}
                      >
                        {actionLoading === test.id ? '...' : 'Activate'}
                      </button>
                    )}
                    {test.status === 'active' && (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleStatusChange(test.id, 'completed'); }}
                        disabled={actionLoading === test.id}
                        style={{
                          padding: '4px 12px', fontSize: '12px', fontWeight: 600,
                          borderRadius: '4px', border: '1px solid #d1d5db',
                          backgroundColor: '#ffffff', color: '#374151', cursor: 'pointer',
                          opacity: actionLoading === test.id ? 0.6 : 1,
                        }}
                      >
                        {actionLoading === test.id ? '...' : 'Complete'}
                      </button>
                    )}
                    <span style={{ fontSize: '18px', color: '#9ca3af', userSelect: 'none' }}>
                      {isExpanded ? '\u25B2' : '\u25BC'}
                    </span>
                  </div>
                </div>

                {/* Expanded Results */}
                {isExpanded && (
                  <div style={{ padding: '18px' }}>
                    {test.description && (
                      <p style={{ margin: '0 0 12px', fontSize: '14px', color: '#6b7280' }}>
                        {test.description}
                      </p>
                    )}
                    <div style={{ fontSize: '13px', color: '#9ca3af', marginBottom: '12px' }}>
                      Traffic split: {test.traffic_split}% A / {100 - test.traffic_split}% B
                      {test.start_date && ` | Started: ${new Date(test.start_date).toLocaleDateString()}`}
                      {test.end_date && ` | Ended: ${new Date(test.end_date).toLocaleDateString()}`}
                    </div>
                    <TestResultsPanel test={test} token={token} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default ABTestDashboard;
