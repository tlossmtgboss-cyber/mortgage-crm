/**
 * Rates Tab
 * Interactive rate ladder with points/credits explanation
 */
import React, { useState, useEffect, useCallback } from 'react';

const API_BASE_URL = typeof window !== 'undefined' &&
  (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
  ? 'https://api.perenniaai.com'
  : 'http://localhost:8000';

const RatesTab = ({ clientId, callSessionId, userRole }) => {
  const [rateSheet, setRateSheet] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState('AGENCY');
  const [selectedProgram, setSelectedProgram] = useState('30 Year Fixed');
  const [selectedLock, setSelectedLock] = useState(30);
  const [viewMode, setViewMode] = useState('simple');
  const [rates, setRates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loanAmount, setLoanAmount] = useState(500000);

  // Fetch active rate sheet
  useEffect(() => {
    fetchRateSheet();
  }, []);

  // Load rates when selections change
  useEffect(() => {
    if (rateSheet) {
      loadRates();
    }
  }, [rateSheet, selectedProduct, selectedProgram, selectedLock]);

  const fetchRateSheet = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/rate-sheets/active`,
        {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setRateSheet(data);
      }
    } catch (err) {
      console.error('Error fetching rate sheet:', err);
    } finally {
      // Set demo data
      setRateSheet({
        id: 'demo-sheet',
        name: 'Demo Rate Sheet',
        effective_at: new Date().toISOString()
      });
      setLoading(false);
    }
  };

  const loadRates = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/rate-sheets/${rateSheet.id}/rates?` +
        `product_family=${selectedProduct}&program=${encodeURIComponent(selectedProgram)}&lock_days=${selectedLock}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setRates(data.rates || []);
      }
    } catch (err) {
      console.error('Error loading rates:', err);
    } finally {
      // Set demo rates
      setRates([
        { id: '1', rate: 5.250, price: 1.500, is_par: false },
        { id: '2', rate: 5.375, price: 1.000, is_par: false },
        { id: '3', rate: 5.500, price: 0.500, is_par: false },
        { id: '4', rate: 5.625, price: 0.125, is_par: true },
        { id: '5', rate: 5.750, price: -0.250, is_par: false },
        { id: '6', rate: 5.875, price: -0.625, is_par: false },
        { id: '7', rate: 6.000, price: -1.000, is_par: false },
        { id: '8', rate: 6.125, price: -1.375, is_par: false },
        { id: '9', rate: 6.250, price: -1.750, is_par: false },
        { id: '10', rate: 6.375, price: -2.125, is_par: false },
      ]);
    }
  };

  const formatPrice = (price) => {
    if (price > 0) {
      return `+${price.toFixed(3)} pts`;
    } else if (price < 0) {
      return `${price.toFixed(3)} pts (credit)`;
    } else {
      return 'Par';
    }
  };

  const calculatePayment = (rate) => {
    const monthlyRate = rate / 100 / 12;
    const termMonths = selectedProgram.includes('15') ? 180 : 360;
    if (monthlyRate > 0) {
      return loanAmount * (
        monthlyRate * Math.pow(1 + monthlyRate, termMonths)
      ) / (
        Math.pow(1 + monthlyRate, termMonths) - 1
      );
    }
    return loanAmount / termMonths;
  };

  const getBadge = (row) => {
    if (row.is_par) return { text: 'Low Cost', color: 'blue' };
    if (row.price < -1) return { text: 'Max Credit', color: 'green' };
    if (row.price < 0) return { text: 'Credit Option', color: 'green' };
    if (row.price > 1) return { text: 'Buy Down', color: 'purple' };
    return null;
  };

  const displayedRates = viewMode === 'simple'
    ? rates.filter(r => Math.abs(r.price) <= 2).slice(0, 7)
    : rates;

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
        <p style={{ color: '#6b7280' }}>Loading rates...</p>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div style={{ padding: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h2 style={{ margin: 0, fontSize: '24px', fontWeight: '700', color: '#111827' }}>
          Rates
        </h2>

        {userRole === 'lo' && (
          <button
            onClick={() => setViewMode(viewMode === 'simple' ? 'pro' : 'simple')}
            style={{
              padding: '8px 16px',
              backgroundColor: '#f3f4f6',
              border: 'none',
              borderRadius: '8px',
              fontSize: '14px',
              cursor: 'pointer',
              color: '#374151'
            }}
          >
            {viewMode === 'simple' ? 'Pro View' : 'Simple View'}
          </button>
        )}
      </div>

      {/* As-of Timestamp */}
      {rateSheet && (
        <div style={{
          backgroundColor: '#eff6ff',
          border: '1px solid #bfdbfe',
          borderRadius: '8px',
          padding: '12px 16px',
          marginBottom: '16px'
        }}>
          <p style={{ margin: 0, fontSize: '14px', color: '#1e40af' }}>
            📊 <strong>Rates as of:</strong> {new Date(rateSheet.effective_at).toLocaleString()}
          </p>
        </div>
      )}

      {/* Controls */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '16px',
        marginBottom: '16px'
      }}>
        <div>
          <label style={{ display: 'block', fontSize: '12px', fontWeight: '500', color: '#6b7280', marginBottom: '4px' }}>
            Product Family
          </label>
          <select
            value={selectedProduct}
            onChange={(e) => setSelectedProduct(e.target.value)}
            style={{
              width: '100%',
              padding: '8px 12px',
              border: '1px solid #d1d5db',
              borderRadius: '8px',
              fontSize: '14px',
              backgroundColor: '#fff'
            }}
          >
            <option value="AGENCY">Conventional</option>
            <option value="GOV">FHA/VA/USDA</option>
            <option value="JUMBO">Jumbo</option>
          </select>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: '12px', fontWeight: '500', color: '#6b7280', marginBottom: '4px' }}>
            Program
          </label>
          <select
            value={selectedProgram}
            onChange={(e) => setSelectedProgram(e.target.value)}
            style={{
              width: '100%',
              padding: '8px 12px',
              border: '1px solid #d1d5db',
              borderRadius: '8px',
              fontSize: '14px',
              backgroundColor: '#fff'
            }}
          >
            <option value="30 Year Fixed">30 Year Fixed</option>
            <option value="15 Year Fixed">15 Year Fixed</option>
            <option value="5/6 ARM">5/6 ARM</option>
          </select>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: '12px', fontWeight: '500', color: '#6b7280', marginBottom: '4px' }}>
            Lock Period
          </label>
          <select
            value={selectedLock}
            onChange={(e) => setSelectedLock(parseInt(e.target.value))}
            style={{
              width: '100%',
              padding: '8px 12px',
              border: '1px solid #d1d5db',
              borderRadius: '8px',
              fontSize: '14px',
              backgroundColor: '#fff'
            }}
          >
            <option value={15}>15 Days</option>
            <option value={30}>30 Days</option>
            <option value={45}>45 Days</option>
            <option value={60}>60 Days</option>
          </select>
        </div>
      </div>

      {/* Explanation */}
      <div style={{
        backgroundColor: '#f9fafb',
        border: '1px solid #e5e7eb',
        borderRadius: '8px',
        padding: '12px 16px',
        marginBottom: '16px'
      }}>
        <p style={{ margin: 0, fontSize: '13px', color: '#6b7280', lineHeight: '1.5' }}>
          <strong>Points</strong> = prepaid interest to buy a lower rate (you pay more upfront to save monthly).<br />
          <strong>Credits</strong> = lender helps cover closing costs for a slightly higher rate.
        </p>
      </div>

      {/* Rate Ladder */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ backgroundColor: '#f9fafb' }}>
              <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase' }}>
                Rate
              </th>
              <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase' }}>
                Points / Credit
              </th>
              <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase' }}>
                P&I Payment
              </th>
              <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase' }}>
                Badge
              </th>
            </tr>
          </thead>
          <tbody>
            {displayedRates.map((row) => {
              const badge = getBadge(row);
              const payment = calculatePayment(row.rate);
              const pointsDollars = loanAmount * (row.price / 100);

              return (
                <tr
                  key={row.id}
                  style={{
                    borderBottom: '1px solid #e5e7eb',
                    cursor: 'pointer',
                    backgroundColor: row.is_par ? '#eff6ff' : 'transparent'
                  }}
                >
                  <td style={{ padding: '16px' }}>
                    <span style={{ fontSize: '18px', fontWeight: '600', color: '#111827' }}>
                      {row.rate.toFixed(3)}%
                    </span>
                  </td>
                  <td style={{ padding: '16px' }}>
                    <div>
                      <span style={{
                        fontWeight: '500',
                        color: row.price < 0 ? '#059669' : '#111827'
                      }}>
                        {formatPrice(row.price)}
                      </span>
                      <br />
                      <span style={{ fontSize: '12px', color: '#9ca3af' }}>
                        {row.price < 0 ? 'Credit: ' : 'Cost: '}
                        ${Math.abs(pointsDollars).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </span>
                    </div>
                  </td>
                  <td style={{ padding: '16px' }}>
                    <span style={{ fontWeight: '500', color: '#111827' }}>
                      ${payment.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                  </td>
                  <td style={{ padding: '16px' }}>
                    {badge && (
                      <span style={{
                        padding: '4px 8px',
                        borderRadius: '9999px',
                        fontSize: '11px',
                        fontWeight: '500',
                        backgroundColor: badge.color === 'blue' ? '#dbeafe' :
                                        badge.color === 'green' ? '#dcfce7' :
                                        badge.color === 'purple' ? '#f3e8ff' : '#f3f4f6',
                        color: badge.color === 'blue' ? '#1e40af' :
                              badge.color === 'green' ? '#166534' :
                              badge.color === 'purple' ? '#7e22ce' : '#374151'
                      }}>
                        {badge.text}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default RatesTab;
export { RatesTab };
