/**
 * Comparison Tab
 * Side-by-side scenario comparison with instant recalculation
 */
import React, { useState, useEffect } from 'react';

const API_BASE_URL = typeof window !== 'undefined' &&
  (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
  ? 'https://api.perenniaai.com'
  : 'http://localhost:8000';

const ComparisonTab = ({ clientId, callSessionId, userRole }) => {
  const [scenarios, setScenarios] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchScenarios();
  }, [clientId, callSessionId]);

  const fetchScenarios = async () => {
    try {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams();
      if (clientId) params.append('client_id', clientId);
      if (callSessionId) params.append('call_session_id', callSessionId);

      const response = await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/scenarios/compare?${params}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setScenarios(data.scenarios || []);
      }
    } catch (err) {
      console.error('Error fetching scenarios:', err);
    } finally {
      // Set demo scenarios
      if (scenarios.length === 0) {
        setScenarios([
          {
            id: 's1',
            name: 'Lower Payment',
            rate: 5.625,
            price: 0.125,
            points_dollars: 625,
            payment_pi: 2878,
            payment_piti: 3428,
            cash_to_close: 108625,
            is_recommended: true
          },
          {
            id: 's2',
            name: 'Lower Cash',
            rate: 6.000,
            price: -1.000,
            points_dollars: -5000,
            payment_pi: 2998,
            payment_piti: 3548,
            cash_to_close: 103000,
            is_recommended: false
          }
        ]);
      }
      setLoading(false);
    }
  };

  const handleSetRecommended = async (scenarioId) => {
    if (userRole !== 'lo') return;

    try {
      const token = localStorage.getItem('token');
      await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/scenarios/${scenarioId}/recommend`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );

      setScenarios(prev => prev.map(s => ({
        ...s,
        is_recommended: s.id === scenarioId
      })));
    } catch (err) {
      console.error('Error setting recommended:', err);
    }
  };

  const handleAddScenario = async () => {
    if (userRole !== 'lo') return;

    const newScenario = {
      id: `s${scenarios.length + 1}`,
      name: `Scenario ${String.fromCharCode(65 + scenarios.length)}`,
      rate: 5.750,
      price: -0.250,
      points_dollars: -1250,
      payment_pi: 2918,
      payment_piti: 3468,
      cash_to_close: 106750,
      is_recommended: false
    };

    setScenarios(prev => [...prev, newScenario]);
  };

  const calculateDelta = (value, baseline, isInverse = false) => {
    const diff = value - baseline;
    if (Math.abs(diff) < 1) return null;

    const isPositive = isInverse ? diff < 0 : diff > 0;
    return {
      value: Math.abs(diff),
      direction: isPositive ? 'up' : 'down',
      color: isPositive ? '#10b981' : '#ef4444'
    };
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '48px' }}>
        <div style={{
          width: '32px',
          height: '32px',
          margin: '0 auto 16px',
          border: '3px solid #e5e7eb',
          borderTopColor: '#2563eb',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite'
        }} />
        <p style={{ color: '#6b7280' }}>Loading scenarios...</p>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  const baselineScenario = scenarios.find(s => s.is_recommended) || scenarios[0];

  return (
    <div style={{ padding: '16px' }}>
      <h2 style={{ margin: '0 0 24px', fontSize: '24px', fontWeight: '700', color: '#111827' }}>
        Scenario Comparison
      </h2>

      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${Math.min(scenarios.length + 1, 4)}, minmax(240px, 1fr))`,
        gap: '16px'
      }}>
        {scenarios.map((scenario) => {
          const paymentDelta = baselineScenario && scenario.id !== baselineScenario.id
            ? calculateDelta(scenario.payment_pi, baselineScenario.payment_pi, true)
            : null;
          const cashDelta = baselineScenario && scenario.id !== baselineScenario.id
            ? calculateDelta(scenario.cash_to_close, baselineScenario.cash_to_close, true)
            : null;

          return (
            <div
              key={scenario.id}
              style={{
                backgroundColor: '#fff',
                border: scenario.is_recommended ? '2px solid #2563eb' : '1px solid #e5e7eb',
                borderRadius: '12px',
                padding: '20px',
                boxShadow: scenario.is_recommended ? '0 4px 6px rgba(37, 99, 235, 0.1)' : 'none'
              }}
            >
              {/* Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600', color: '#111827' }}>
                  {scenario.name}
                </h3>
                {scenario.is_recommended && (
                  <span style={{
                    padding: '4px 8px',
                    borderRadius: '9999px',
                    fontSize: '10px',
                    fontWeight: '600',
                    backgroundColor: '#2563eb',
                    color: '#fff'
                  }}>
                    Recommended
                  </span>
                )}
              </div>

              {/* Metrics */}
              <div style={{ marginBottom: '16px' }}>
                <div style={{ marginBottom: '12px' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '2px' }}>Rate</div>
                  <div style={{ fontSize: '24px', fontWeight: '700', color: '#111827' }}>
                    {scenario.rate.toFixed(3)}%
                  </div>
                </div>

                <div style={{ marginBottom: '12px' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '2px' }}>Points / Credit</div>
                  <div style={{
                    fontSize: '16px',
                    fontWeight: '600',
                    color: scenario.price < 0 ? '#059669' : '#111827'
                  }}>
                    {scenario.price > 0 ? '+' : ''}{scenario.price.toFixed(3)}
                    <span style={{ fontSize: '12px', fontWeight: '400', color: '#6b7280', marginLeft: '4px' }}>
                      (${Math.abs(scenario.points_dollars).toLocaleString()})
                    </span>
                  </div>
                </div>

                <div style={{ marginBottom: '12px' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '2px' }}>P&I Payment</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '18px', fontWeight: '600', color: '#111827' }}>
                      ${scenario.payment_pi.toLocaleString()}
                    </span>
                    {paymentDelta && (
                      <span style={{
                        fontSize: '12px',
                        color: paymentDelta.color,
                        display: 'flex',
                        alignItems: 'center'
                      }}>
                        {paymentDelta.direction === 'up' ? '↑' : '↓'}
                        ${paymentDelta.value.toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>

                <div style={{ marginBottom: '12px' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '2px' }}>PITI Payment</div>
                  <div style={{ fontSize: '16px', fontWeight: '600', color: '#111827' }}>
                    ${scenario.payment_piti.toLocaleString()}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '2px' }}>Cash to Close</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '18px', fontWeight: '600', color: '#111827' }}>
                      ${scenario.cash_to_close.toLocaleString()}
                    </span>
                    {cashDelta && (
                      <span style={{
                        fontSize: '12px',
                        color: cashDelta.color,
                        display: 'flex',
                        alignItems: 'center'
                      }}>
                        {cashDelta.direction === 'up' ? '↑' : '↓'}
                        ${cashDelta.value.toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Actions */}
              {userRole === 'lo' && !scenario.is_recommended && (
                <button
                  onClick={() => handleSetRecommended(scenario.id)}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: '#2563eb',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '8px',
                    fontSize: '13px',
                    fontWeight: '500',
                    cursor: 'pointer'
                  }}
                >
                  Set as Recommended
                </button>
              )}
            </div>
          );
        })}

        {/* Add Scenario Card (LO only, max 4) */}
        {userRole === 'lo' && scenarios.length < 4 && (
          <button
            onClick={handleAddScenario}
            style={{
              border: '2px dashed #d1d5db',
              borderRadius: '12px',
              padding: '32px',
              backgroundColor: 'transparent',
              color: '#9ca3af',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              minHeight: '300px',
              transition: 'all 0.2s ease'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = '#9ca3af';
              e.currentTarget.style.color = '#6b7280';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = '#d1d5db';
              e.currentTarget.style.color = '#9ca3af';
            }}
          >
            <span style={{ fontSize: '32px' }}>+</span>
            <span style={{ fontSize: '14px', fontWeight: '500' }}>Add Scenario</span>
          </button>
        )}
      </div>

      {/* Comparison Summary */}
      {scenarios.length >= 2 && (
        <div style={{
          backgroundColor: '#f9fafb',
          border: '1px solid #e5e7eb',
          borderRadius: '12px',
          padding: '20px',
          marginTop: '24px'
        }}>
          <h4 style={{ margin: '0 0 12px', fontSize: '14px', fontWeight: '600', color: '#111827' }}>
            Quick Comparison
          </h4>
          <div style={{ fontSize: '14px', color: '#6b7280', lineHeight: '1.6' }}>
            {scenarios[0] && scenarios[1] && (
              <>
                <p style={{ margin: '0 0 8px' }}>
                  <strong>{scenarios[0].name}</strong> has a {scenarios[0].rate < scenarios[1].rate ? 'lower' : 'higher'} rate
                  ({scenarios[0].rate}% vs {scenarios[1].rate}%) but requires ${Math.abs(scenarios[0].cash_to_close - scenarios[1].cash_to_close).toLocaleString()}
                  {scenarios[0].cash_to_close > scenarios[1].cash_to_close ? ' more' : ' less'} cash at closing.
                </p>
                <p style={{ margin: 0 }}>
                  Monthly payment difference: ${Math.abs(scenarios[0].payment_pi - scenarios[1].payment_pi).toLocaleString()}/month.
                </p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ComparisonTab;
export { ComparisonTab };
