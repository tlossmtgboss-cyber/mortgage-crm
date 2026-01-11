/**
 * Closing Costs Tab
 * Detailed breakdown of closing costs with lender credit waterfall
 */
import React, { useState, useEffect } from 'react';

const API_BASE_URL = typeof window !== 'undefined' &&
  (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
  ? 'https://api.perenniaai.com'
  : 'http://localhost:8000';

const COST_CATEGORIES = [
  { id: 'origination', label: 'Origination Charges', icon: '📋' },
  { id: 'title', label: 'Title & Settlement', icon: '📜' },
  { id: 'government', label: 'Government Fees', icon: '🏛️' },
  { id: 'prepaid', label: 'Prepaid Items', icon: '📅' },
  { id: 'escrow', label: 'Initial Escrow', icon: '🏦' }
];

const ClosingCostsTab = ({ clientId, callSessionId, userRole }) => {
  const [costs, setCosts] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedCategories, setExpandedCategories] = useState(['origination']);

  useEffect(() => {
    fetchClosingCosts();
  }, [clientId, callSessionId]);

  const fetchClosingCosts = async () => {
    try {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams();
      if (clientId) params.append('client_id', clientId);
      if (callSessionId) params.append('call_session_id', callSessionId);

      const response = await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/closing-costs?${params}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setCosts(data);
      }
    } catch (err) {
      console.error('Error fetching closing costs:', err);
    } finally {
      // Demo data
      setCosts({
        loan_amount: 500000,
        purchase_price: 625000,
        categories: {
          origination: {
            items: [
              { name: 'Origination Fee', amount: 2500, buyer_paid: true },
              { name: 'Points', amount: 625, buyer_paid: true },
              { name: 'Processing Fee', amount: 895, buyer_paid: true },
              { name: 'Underwriting Fee', amount: 995, buyer_paid: true }
            ],
            total: 5015
          },
          title: {
            items: [
              { name: 'Title Insurance (Lender)', amount: 1250, buyer_paid: true },
              { name: 'Title Insurance (Owner)', amount: 2100, buyer_paid: true },
              { name: 'Settlement Fee', amount: 750, buyer_paid: true },
              { name: 'Title Search', amount: 350, buyer_paid: true },
              { name: 'Recording Fees', amount: 125, buyer_paid: true }
            ],
            total: 4575
          },
          government: {
            items: [
              { name: 'Transfer Taxes', amount: 3125, buyer_paid: false },
              { name: 'Recording Fees', amount: 250, buyer_paid: true },
              { name: 'State Tax/Stamps', amount: 0, buyer_paid: true }
            ],
            total: 3375
          },
          prepaid: {
            items: [
              { name: 'Prepaid Interest (15 days)', amount: 1250, buyer_paid: true },
              { name: 'Homeowners Insurance (12 mo)', amount: 2400, buyer_paid: true },
              { name: 'Flood Insurance', amount: 0, buyer_paid: true }
            ],
            total: 3650
          },
          escrow: {
            items: [
              { name: 'Property Tax Reserve (3 mo)', amount: 1875, buyer_paid: true },
              { name: 'Insurance Reserve (2 mo)', amount: 400, buyer_paid: true },
              { name: 'Aggregate Adjustment', amount: -125, buyer_paid: true }
            ],
            total: 2150
          }
        },
        lender_credits: [
          { description: 'Lender Credit at 6.000%', amount: -5000 },
          { description: 'Rate Lock Credit', amount: -250 }
        ],
        seller_credits: 7500,
        earnest_money: 15000,
        down_payment: 125000,
        total_closing_costs: 18765,
        total_credits: 12750,
        net_closing_costs: 6015,
        cash_to_close: 116015
      });
      setLoading(false);
    }
  };

  const toggleCategory = (categoryId) => {
    setExpandedCategories(prev =>
      prev.includes(categoryId)
        ? prev.filter(id => id !== categoryId)
        : [...prev, categoryId]
    );
  };

  const formatCurrency = (amount) => {
    const absAmount = Math.abs(amount);
    const formatted = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(absAmount);
    return amount < 0 ? `(${formatted})` : formatted;
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
        <p style={{ color: '#6b7280' }}>Loading closing costs...</p>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (!costs) {
    return (
      <div style={{ textAlign: 'center', padding: '48px', color: '#6b7280' }}>
        <p>No closing cost data available</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '16px' }}>
      <h2 style={{ margin: '0 0 24px', fontSize: '24px', fontWeight: '700', color: '#111827' }}>
        Closing Cost Breakdown
      </h2>

      {/* Summary Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: '16px',
        marginBottom: '24px'
      }}>
        <div style={{
          backgroundColor: '#fff',
          border: '1px solid #e5e7eb',
          borderRadius: '12px',
          padding: '16px'
        }}>
          <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>Total Closing Costs</div>
          <div style={{ fontSize: '20px', fontWeight: '700', color: '#111827' }}>
            {formatCurrency(costs.total_closing_costs)}
          </div>
        </div>

        <div style={{
          backgroundColor: '#fff',
          border: '1px solid #e5e7eb',
          borderRadius: '12px',
          padding: '16px'
        }}>
          <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>Credits Applied</div>
          <div style={{ fontSize: '20px', fontWeight: '700', color: '#059669' }}>
            {formatCurrency(-costs.total_credits)}
          </div>
        </div>

        <div style={{
          backgroundColor: '#fff',
          border: '1px solid #e5e7eb',
          borderRadius: '12px',
          padding: '16px'
        }}>
          <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>Net Closing Costs</div>
          <div style={{ fontSize: '20px', fontWeight: '700', color: '#111827' }}>
            {formatCurrency(costs.net_closing_costs)}
          </div>
        </div>

        <div style={{
          backgroundColor: '#2563eb',
          borderRadius: '12px',
          padding: '16px'
        }}>
          <div style={{ fontSize: '12px', color: 'rgba(255,255,255,0.8)', marginBottom: '4px' }}>Cash to Close</div>
          <div style={{ fontSize: '20px', fontWeight: '700', color: '#fff' }}>
            {formatCurrency(costs.cash_to_close)}
          </div>
        </div>
      </div>

      {/* Cost Categories */}
      <div style={{ display: 'flex', gap: '24px' }}>
        {/* Left Column - Cost Breakdown */}
        <div style={{ flex: 2 }}>
          {COST_CATEGORIES.map(category => {
            const categoryData = costs.categories[category.id];
            if (!categoryData) return null;

            const isExpanded = expandedCategories.includes(category.id);

            return (
              <div
                key={category.id}
                style={{
                  backgroundColor: '#fff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '12px',
                  marginBottom: '12px',
                  overflow: 'hidden'
                }}
              >
                <button
                  onClick={() => toggleCategory(category.id)}
                  style={{
                    width: '100%',
                    padding: '16px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    backgroundColor: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ fontSize: '20px' }}>{category.icon}</span>
                    <span style={{ fontSize: '15px', fontWeight: '600', color: '#111827' }}>
                      {category.label}
                    </span>
                    <span style={{
                      fontSize: '12px',
                      color: '#6b7280',
                      backgroundColor: '#f3f4f6',
                      padding: '2px 8px',
                      borderRadius: '9999px'
                    }}>
                      {categoryData.items.length} items
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ fontSize: '16px', fontWeight: '600', color: '#111827' }}>
                      {formatCurrency(categoryData.total)}
                    </span>
                    <span style={{
                      transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                      transition: 'transform 0.2s ease',
                      color: '#9ca3af'
                    }}>
                      ▼
                    </span>
                  </div>
                </button>

                {isExpanded && (
                  <div style={{ padding: '0 16px 16px' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <tbody>
                        {categoryData.items.map((item, idx) => (
                          <tr
                            key={idx}
                            style={{
                              borderTop: idx === 0 ? '1px solid #e5e7eb' : 'none'
                            }}
                          >
                            <td style={{
                              padding: '10px 0',
                              fontSize: '14px',
                              color: '#374151'
                            }}>
                              {item.name}
                            </td>
                            <td style={{
                              padding: '10px 0',
                              fontSize: '14px',
                              color: item.amount < 0 ? '#059669' : '#111827',
                              textAlign: 'right',
                              fontWeight: '500'
                            }}>
                              {formatCurrency(item.amount)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Right Column - Credits & Summary */}
        <div style={{ flex: 1 }}>
          {/* Lender Credit Waterfall */}
          <div style={{
            backgroundColor: '#fff',
            border: '1px solid #e5e7eb',
            borderRadius: '12px',
            padding: '16px',
            marginBottom: '12px'
          }}>
            <h4 style={{
              margin: '0 0 12px',
              fontSize: '14px',
              fontWeight: '600',
              color: '#111827',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}>
              <span>💰</span> Lender Credits
            </h4>

            <div style={{ marginBottom: '12px' }}>
              {costs.lender_credits.map((credit, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 0',
                    borderBottom: idx < costs.lender_credits.length - 1 ? '1px solid #f3f4f6' : 'none'
                  }}
                >
                  <span style={{ fontSize: '13px', color: '#6b7280' }}>
                    {credit.description}
                  </span>
                  <span style={{ fontSize: '14px', fontWeight: '500', color: '#059669' }}>
                    {formatCurrency(credit.amount)}
                  </span>
                </div>
              ))}
            </div>

            <div style={{
              borderTop: '1px solid #e5e7eb',
              paddingTop: '12px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <span style={{ fontSize: '13px', fontWeight: '600', color: '#111827' }}>
                Total Lender Credit
              </span>
              <span style={{ fontSize: '15px', fontWeight: '700', color: '#059669' }}>
                {formatCurrency(costs.lender_credits.reduce((sum, c) => sum + c.amount, 0))}
              </span>
            </div>
          </div>

          {/* Other Credits */}
          <div style={{
            backgroundColor: '#fff',
            border: '1px solid #e5e7eb',
            borderRadius: '12px',
            padding: '16px',
            marginBottom: '12px'
          }}>
            <h4 style={{
              margin: '0 0 12px',
              fontSize: '14px',
              fontWeight: '600',
              color: '#111827'
            }}>
              Other Credits
            </h4>

            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '8px 0',
              borderBottom: '1px solid #f3f4f6'
            }}>
              <span style={{ fontSize: '13px', color: '#6b7280' }}>Seller Credit</span>
              <span style={{ fontSize: '14px', fontWeight: '500', color: '#059669' }}>
                {formatCurrency(-costs.seller_credits)}
              </span>
            </div>

            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '8px 0'
            }}>
              <span style={{ fontSize: '13px', color: '#6b7280' }}>Earnest Money Deposit</span>
              <span style={{ fontSize: '14px', fontWeight: '500', color: '#059669' }}>
                {formatCurrency(-costs.earnest_money)}
              </span>
            </div>
          </div>

          {/* Cash to Close Calculation */}
          <div style={{
            backgroundColor: '#f0f9ff',
            border: '1px solid #bae6fd',
            borderRadius: '12px',
            padding: '16px'
          }}>
            <h4 style={{
              margin: '0 0 12px',
              fontSize: '14px',
              fontWeight: '600',
              color: '#0369a1'
            }}>
              Cash to Close Calculation
            </h4>

            <div style={{ fontSize: '13px', color: '#374151' }}>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '6px 0'
              }}>
                <span>Down Payment</span>
                <span style={{ fontWeight: '500' }}>{formatCurrency(costs.down_payment)}</span>
              </div>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '6px 0'
              }}>
                <span>Total Closing Costs</span>
                <span style={{ fontWeight: '500' }}>{formatCurrency(costs.total_closing_costs)}</span>
              </div>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '6px 0',
                color: '#059669'
              }}>
                <span>Less: All Credits</span>
                <span style={{ fontWeight: '500' }}>{formatCurrency(-costs.total_credits)}</span>
              </div>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '6px 0',
                color: '#059669'
              }}>
                <span>Less: Earnest Money</span>
                <span style={{ fontWeight: '500' }}>{formatCurrency(-costs.earnest_money)}</span>
              </div>

              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '12px 0 0',
                marginTop: '8px',
                borderTop: '2px solid #0369a1'
              }}>
                <span style={{ fontWeight: '700', color: '#0369a1' }}>Cash to Close</span>
                <span style={{ fontWeight: '700', color: '#0369a1', fontSize: '16px' }}>
                  {formatCurrency(costs.cash_to_close)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Disclaimer */}
      <div style={{
        marginTop: '24px',
        padding: '12px 16px',
        backgroundColor: '#fffbeb',
        border: '1px solid #fcd34d',
        borderRadius: '8px',
        fontSize: '12px',
        color: '#92400e'
      }}>
        <strong>Note:</strong> This is an estimate of closing costs. Actual costs may vary.
        Please refer to your Loan Estimate and Closing Disclosure for final figures.
      </div>
    </div>
  );
};

export default ClosingCostsTab;
export { ClosingCostsTab };
