import React, { useState, useEffect, useCallback } from 'react';
import './IncomeTab.css';
import { getToken } from '../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const INCOME_TYPES = [
  { value: 'W2_EMPLOYMENT', label: 'W-2 Employment', icon: 'briefcase' },
  { value: 'SELF_EMPLOYED_SCHEDULE_C', label: 'Self-Employed (Schedule C)', icon: 'store' },
  { value: 'SELF_EMPLOYED_S_CORP', label: 'Self-Employed (S-Corp)', icon: 'building' },
  { value: 'SELF_EMPLOYED_PARTNERSHIP', label: 'Self-Employed (Partnership)', icon: 'handshake' },
  { value: 'CONTRACTOR_1099', label: '1099 Contractor', icon: 'file-contract' },
  { value: 'RENTAL_SCHEDULE_E', label: 'Rental Income (Schedule E)', icon: 'home' },
  { value: 'RETIREMENT_PENSION', label: 'Retirement/Pension', icon: 'user-clock' },
  { value: 'SOCIAL_SECURITY', label: 'Social Security', icon: 'id-card' },
  { value: 'INVESTMENT_DIVIDEND', label: 'Investment/Dividend', icon: 'chart-line' },
  { value: 'BANK_STATEMENT', label: 'Bank Statement Income', icon: 'university' },
  { value: 'ALIMONY_CHILD_SUPPORT', label: 'Alimony/Child Support', icon: 'hand-holding-usd' },
  { value: 'OTHER', label: 'Other Income', icon: 'plus-circle' },
];

const VERIFICATION_STATUSES = {
  'PENDING': { label: 'Pending', color: '#6b7280', bgColor: '#f3f4f6' },
  'DOCUMENTS_RECEIVED': { label: 'Docs Received', color: '#d97706', bgColor: '#fef3c7' },
  'VERIFIED': { label: 'Verified', color: '#059669', bgColor: '#d1fae5' },
  'NEEDS_ADDITIONAL_DOCS': { label: 'Needs Docs', color: '#dc2626', bgColor: '#fee2e2' },
  'VERBAL_VOE_COMPLETE': { label: 'VOE Complete', color: '#059669', bgColor: '#d1fae5' },
  'WRITTEN_VOE_COMPLETE': { label: 'Written VOE', color: '#059669', bgColor: '#d1fae5' },
  'REJECTED': { label: 'Rejected', color: '#dc2626', bgColor: '#fee2e2' },
};

export default function IncomeTab({ borrowerId, loanId, onIncomeChange }) {
  const [loading, setLoading] = useState(true);
  const [incomeSources, setIncomeSources] = useState([]);
  const [summary, setSummary] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedSource, setSelectedSource] = useState(null);
  const [error, setError] = useState(null);

  const token = getToken();

  const fetchIncomeSources = useCallback(async () => {
    if (!borrowerId || !loanId) return;

    setLoading(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/income/borrowers/${borrowerId}/summary?loan_id=${loanId}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) throw new Error('Failed to fetch income sources');

      const data = await response.json();
      setIncomeSources(data.sources || []);
      setSummary({
        totalMonthly: data.total_monthly_income || 0,
        totalAnnual: data.total_annual_income || 0,
        sourceCount: data.source_count || 0,
        verifiedCount: data.verified_count || 0,
        hasDecliningIncome: data.has_declining_income || false,
      });

      // Return the data so we can use it in useEffect
      return { monthly: data.total_monthly_income, annual: data.total_annual_income };
    } catch (err) {
      console.error('Error fetching income:', err);
      setError(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, [borrowerId, loanId, token]); // Note: onIncomeChange intentionally omitted to prevent loops

  useEffect(() => {
    const loadData = async () => {
      const result = await fetchIncomeSources();
      if (result && onIncomeChange) {
        onIncomeChange(result.monthly, result.annual);
      }
    };
    loadData();
  }, [fetchIncomeSources, onIncomeChange]);

  const handleAddSource = async (incomeType) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/income/borrowers/${borrowerId}/sources`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            borrower_id: borrowerId,
            loan_id: loanId,
            income_type: incomeType,
            is_primary: incomeSources.length === 0,
          }),
        }
      );

      if (!response.ok) throw new Error('Failed to add income source');

      setShowAddModal(false);
      fetchIncomeSources();
    } catch (err) {
      console.error('Error adding income source:', err);
      setError(err.message);
    }
  };

  const handleDeleteSource = async (sourceId) => {
    if (!window.confirm('Are you sure you want to remove this income source?')) return;

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/income/sources/${sourceId}`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) throw new Error('Failed to delete income source');

      fetchIncomeSources();
    } catch (err) {
      console.error('Error deleting income source:', err);
      setError(err.message);
    }
  };

  const handleCalculateIncome = async (sourceId) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/income/sources/${sourceId}/calculate`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) throw new Error('Failed to calculate income');

      fetchIncomeSources();
    } catch (err) {
      console.error('Error calculating income:', err);
      setError(err.message);
    }
  };

  const formatCurrency = (amount) => {
    if (!amount) return '$0';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const getIncomeTypeInfo = (type) => {
    return INCOME_TYPES.find(t => t.value === type) || { label: type, icon: 'dollar-sign' };
  };

  const getVerificationStatus = (status) => {
    return VERIFICATION_STATUSES[status] || VERIFICATION_STATUSES['PENDING'];
  };

  if (loading) {
    return (
      <div className="income-tab loading">
        <div className="loading-spinner"></div>
        <p>Loading income sources...</p>
      </div>
    );
  }

  return (
    <div className="income-tab">
      {error && (
        <div className="error-banner">
          {error}
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Qualifying Income Summary */}
      <div className="income-summary-card">
        <div className="summary-header">
          <h3>Qualifying Income Summary</h3>
          <span className="ai-badge">AI Calculated</span>
        </div>
        <div className="summary-amounts">
          <div className="amount-box">
            <label>Monthly</label>
            <span className="amount">{formatCurrency(summary?.totalMonthly)}</span>
          </div>
          <div className="amount-divider">|</div>
          <div className="amount-box">
            <label>Annual</label>
            <span className="amount">{formatCurrency(summary?.totalAnnual)}</span>
          </div>
        </div>
        <div className="summary-meta">
          <span className={`status-pill ${summary?.verifiedCount === summary?.sourceCount ? 'verified' : 'pending'}`}>
            {summary?.verifiedCount}/{summary?.sourceCount} Verified
          </span>
          {summary?.hasDecliningIncome && (
            <span className="warning-pill">
              Declining Income Detected
            </span>
          )}
        </div>
      </div>

      {/* Income Sources List */}
      <div className="income-sources-section">
        <div className="section-header">
          <h3>Income Sources</h3>
          <button className="add-income-btn" onClick={() => setShowAddModal(true)}>
            + Add Income
          </button>
        </div>

        {incomeSources.length === 0 ? (
          <div className="no-sources">
            <div className="no-sources-icon">$</div>
            <p>No income sources added yet</p>
            <button onClick={() => setShowAddModal(true)}>Add Income Source</button>
          </div>
        ) : (
          <div className="sources-list">
            {incomeSources.map((source) => {
              const typeInfo = getIncomeTypeInfo(source.income_type);
              const verificationStatus = getVerificationStatus(source.verification_status);

              return (
                <div
                  key={source.id}
                  className={`source-card ${source.is_primary ? 'primary' : ''} ${source.declining_income_flag ? 'declining' : ''}`}
                  onClick={() => setSelectedSource(source)}
                >
                  <div className="source-header">
                    <div className="source-type">
                      <span className="type-icon">{typeInfo.icon === 'briefcase' ? 'W2' : typeInfo.icon.charAt(0).toUpperCase()}</span>
                      <span className="type-label">{typeInfo.label}</span>
                      {source.is_primary && <span className="primary-badge">Primary</span>}
                    </div>
                    <span
                      className="verification-badge"
                      style={{
                        backgroundColor: verificationStatus.bgColor,
                        color: verificationStatus.color,
                      }}
                    >
                      {verificationStatus.label}
                    </span>
                  </div>

                  <div className="source-name">
                    {source.source_name || 'Unnamed Source'}
                  </div>

                  <div className="source-amounts">
                    <div className="amount-col">
                      <label>Monthly</label>
                      <span>{formatCurrency(source.monthly_qualifying_income)}</span>
                    </div>
                    <div className="amount-col">
                      <label>Annual</label>
                      <span>{formatCurrency(source.annual_qualifying_income)}</span>
                    </div>
                  </div>

                  {source.calculation_method && (
                    <div className="source-method">
                      Calculated: {source.calculation_method.replace(/_/g, ' ')}
                    </div>
                  )}

                  {source.declining_income_flag && (
                    <div className="declining-warning">
                      Income declining - using conservative calculation
                    </div>
                  )}

                  <div className="source-actions">
                    <button
                      className="action-btn calculate"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCalculateIncome(source.id);
                      }}
                      title="Recalculate Income"
                    >
                      Recalculate
                    </button>
                    <button
                      className="action-btn delete"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteSource(source.id);
                      }}
                      title="Remove Source"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Add Income Modal */}
      {showAddModal && (
        <div className="modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Add Income Source</h3>
              <button className="close-btn" onClick={() => setShowAddModal(false)}>X</button>
            </div>
            <div className="income-type-grid">
              {INCOME_TYPES.map((type) => (
                <button
                  key={type.value}
                  className="income-type-option"
                  onClick={() => handleAddSource(type.value)}
                >
                  <span className="type-icon">{type.label.charAt(0)}</span>
                  <span className="type-name">{type.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Source Detail Modal */}
      {selectedSource && (
        <div className="modal-overlay" onClick={() => setSelectedSource(null)}>
          <div className="modal-content source-detail" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{getIncomeTypeInfo(selectedSource.income_type).label}</h3>
              <button className="close-btn" onClick={() => setSelectedSource(null)}>X</button>
            </div>
            <div className="detail-content">
              <div className="detail-row">
                <label>Source Name</label>
                <span>{selectedSource.source_name || 'Not specified'}</span>
              </div>
              <div className="detail-row">
                <label>Monthly Qualifying Income</label>
                <span className="amount">{formatCurrency(selectedSource.monthly_qualifying_income)}</span>
              </div>
              <div className="detail-row">
                <label>Annual Qualifying Income</label>
                <span className="amount">{formatCurrency(selectedSource.annual_qualifying_income)}</span>
              </div>
              <div className="detail-row">
                <label>Calculation Method</label>
                <span>{selectedSource.calculation_method?.replace(/_/g, ' ') || 'Not calculated'}</span>
              </div>
              <div className="detail-row">
                <label>Verification Status</label>
                <span>{getVerificationStatus(selectedSource.verification_status).label}</span>
              </div>
              {selectedSource.trending_direction && (
                <div className="detail-row">
                  <label>Income Trend</label>
                  <span className={`trend ${selectedSource.trending_direction}`}>
                    {selectedSource.trending_direction}
                  </span>
                </div>
              )}
              {selectedSource.calculation_date && (
                <div className="detail-row">
                  <label>Last Calculated</label>
                  <span>{new Date(selectedSource.calculation_date).toLocaleDateString()}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
