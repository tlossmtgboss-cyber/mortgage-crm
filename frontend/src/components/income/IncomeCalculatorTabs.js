import React, { useState, useEffect, useCallback } from 'react';
import './IncomeCalculatorTabs.css';
import { getToken } from '../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

// Income type configurations with document type mappings
const INCOME_TABS = [
  {
    id: 'W2_EMPLOYMENT',
    label: 'W-2 Employment',
    shortLabel: 'W-2',
    icon: '💼',
    docTypes: ['paystub', 'w2', 'offer_letter', 'voe'],
    description: 'Salary and wage income from W-2 employment',
  },
  {
    id: 'SELF_EMPLOYED_SCHEDULE_C',
    label: 'Schedule C',
    shortLabel: 'Sch C',
    icon: '📋',
    docTypes: ['tax_return', 'schedule_c', 'profit_loss', 'business_license'],
    description: 'Self-employment income from sole proprietorship',
  },
  {
    id: 'RENTAL_SCHEDULE_E',
    label: 'Rental Income',
    shortLabel: 'Rental',
    icon: '🏠',
    docTypes: ['tax_return', 'schedule_e', 'lease_agreement', 'rental_statement'],
    description: 'Rental property income from Schedule E',
  },
  {
    id: 'SELF_EMPLOYED_S_CORP',
    label: 'S-Corp / K-1',
    shortLabel: 'K-1',
    icon: '🏢',
    docTypes: ['k1', 'tax_return', 'corporate_tax_return'],
    description: 'Income from S-Corporation or Partnership K-1',
  },
  {
    id: 'BANK_STATEMENT',
    label: 'Bank Statements',
    shortLabel: 'Bank',
    icon: '🏦',
    docTypes: ['bank_statement'],
    description: 'Non-QM bank statement income program',
  },
  {
    id: 'OTHER',
    label: 'Other Income',
    shortLabel: 'Other',
    icon: '📄',
    docTypes: ['other_income', 'social_security', 'pension', 'alimony'],
    description: 'Social Security, Pension, Alimony, etc.',
  },
];

const VERIFICATION_STATUSES = {
  'PENDING': { label: 'Pending', color: '#f59e0b', bgColor: '#fef3c7' },
  'DOCUMENTS_RECEIVED': { label: 'Docs Received', color: '#3b82f6', bgColor: '#dbeafe' },
  'VERIFIED': { label: 'Verified', color: '#10b981', bgColor: '#d1fae5' },
  'NEEDS_ADDITIONAL_DOCS': { label: 'Needs Docs', color: '#ef4444', bgColor: '#fee2e2' },
  'CALCULATED': { label: 'Calculated', color: '#8b5cf6', bgColor: '#ede9fe' },
};

export default function IncomeCalculatorTabs({ loanId, borrowerId, onIncomeChange }) {
  const [activeTab, setActiveTab] = useState('W2_EMPLOYMENT');
  const [loading, setLoading] = useState(true);
  const [calculating, setCalculating] = useState(false);
  const [incomeSources, setIncomeSources] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [extractedData, setExtractedData] = useState({});
  const [error, setError] = useState(null);
  const [totalIncome, setTotalIncome] = useState({ monthly: 0, annual: 0 });

  const token = getToken();

  // Fetch income sources for the loan
  const fetchIncomeSources = useCallback(async () => {
    if (!borrowerId || !loanId) return;

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/income/borrowers/${borrowerId}/sources?loan_id=${loanId}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setIncomeSources(data.sources || []);

        // Calculate totals
        const sources = data.sources || [];
        const monthly = sources.reduce((sum, s) => sum + (s.monthly_qualifying_income || 0), 0);
        const annual = sources.reduce((sum, s) => sum + (s.annual_qualifying_income || 0), 0);
        setTotalIncome({ monthly, annual });

        if (onIncomeChange) {
          onIncomeChange(monthly, annual);
        }
      }
    } catch (err) {
      console.error('Error fetching income sources:', err);
    }
  }, [borrowerId, loanId, token, onIncomeChange]);

  // Fetch documents for the loan
  const fetchDocuments = useCallback(async () => {
    if (!loanId) return;

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/smart-docs/loan/${loanId}/documents`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setDocuments(data.documents || data || []);
      }
    } catch (err) {
      console.error('Error fetching documents:', err);
    }
  }, [loanId, token]);

  // Fetch extracted data for documents
  const fetchExtractedData = useCallback(async () => {
    if (!loanId) return;

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/income/loan/${loanId}/extractions`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setExtractedData(data.extractions || {});
      }
    } catch (err) {
      console.error('Error fetching extracted data:', err);
    }
  }, [loanId, token]);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([
        fetchIncomeSources(),
        fetchDocuments(),
        fetchExtractedData(),
      ]);
      setLoading(false);
    };
    loadData();
  }, [fetchIncomeSources, fetchDocuments, fetchExtractedData]);

  // Get documents for a specific income type
  const getDocumentsForType = (incomeType) => {
    const tabConfig = INCOME_TABS.find(t => t.id === incomeType);
    if (!tabConfig) return [];

    return documents.filter(doc => {
      const docType = (doc.doc_type || doc.document_type || '').toLowerCase();
      return tabConfig.docTypes.some(type => docType.includes(type.toLowerCase()));
    });
  };

  // Get income source for a specific type
  const getIncomeSourceForType = (incomeType) => {
    return incomeSources.find(s => s.income_type === incomeType);
  };

  // Extract income from documents
  const handleExtractIncome = async (incomeType) => {
    setCalculating(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/income/extract-from-documents`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            loan_id: loanId,
            borrower_id: borrowerId,
            income_type: incomeType,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to extract income');
      }

      // Refresh data
      await Promise.all([fetchIncomeSources(), fetchExtractedData()]);
    } catch (err) {
      console.error('Error extracting income:', err);
      setError(err.message);
    } finally {
      setCalculating(false);
    }
  };

  // Calculate qualifying income
  const handleCalculateIncome = async (incomeType) => {
    setCalculating(true);
    setError(null);

    try {
      const source = getIncomeSourceForType(incomeType);
      if (!source) {
        // Create income source first
        await fetch(
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
            }),
          }
        );
        await fetchIncomeSources();
      }

      // Trigger calculation
      const updatedSource = getIncomeSourceForType(incomeType) || source;
      if (updatedSource) {
        await fetch(
          `${API_BASE}/api/v1/income/sources/${updatedSource.id}/calculate`,
          {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
            },
          }
        );
      }

      await fetchIncomeSources();
    } catch (err) {
      console.error('Error calculating income:', err);
      setError(err.message);
    } finally {
      setCalculating(false);
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

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString();
  };

  const activeTabConfig = INCOME_TABS.find(t => t.id === activeTab);
  const tabDocuments = getDocumentsForType(activeTab);
  const tabIncomeSource = getIncomeSourceForType(activeTab);

  if (loading) {
    return (
      <div className="income-calculator-tabs loading">
        <div className="loading-spinner"></div>
        <p>Loading income data...</p>
      </div>
    );
  }

  return (
    <div className="income-calculator-tabs">
      {/* Total Income Summary */}
      <div className="income-total-banner">
        <div className="total-label">Total Qualifying Income</div>
        <div className="total-amounts">
          <span className="monthly">{formatCurrency(totalIncome.monthly)}/mo</span>
          <span className="divider">|</span>
          <span className="annual">{formatCurrency(totalIncome.annual)}/yr</span>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="income-tabs-nav">
        {INCOME_TABS.map(tab => {
          const source = getIncomeSourceForType(tab.id);
          const docs = getDocumentsForType(tab.id);
          const hasIncome = source?.monthly_qualifying_income > 0;
          const hasDocs = docs.length > 0;

          return (
            <button
              key={tab.id}
              className={`income-tab-btn ${activeTab === tab.id ? 'active' : ''} ${hasIncome ? 'has-income' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <span className="tab-icon">{tab.icon}</span>
              <span className="tab-label">{tab.shortLabel}</span>
              {hasIncome && (
                <span className="tab-amount">{formatCurrency(source.monthly_qualifying_income)}</span>
              )}
              {hasDocs && !hasIncome && (
                <span className="tab-docs-badge">{docs.length}</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Active Tab Content */}
      <div className="income-tab-content">
        {error && (
          <div className="error-banner">
            {error}
            <button onClick={() => setError(null)}>Dismiss</button>
          </div>
        )}

        <div className="tab-header">
          <div className="tab-title">
            <span className="title-icon">{activeTabConfig?.icon}</span>
            <div>
              <h3>{activeTabConfig?.label}</h3>
              <p className="tab-description">{activeTabConfig?.description}</p>
            </div>
          </div>
          <div className="tab-actions">
            <button
              className="action-btn extract"
              onClick={() => handleExtractIncome(activeTab)}
              disabled={calculating || tabDocuments.length === 0}
            >
              {calculating ? 'Extracting...' : 'Extract from Docs'}
            </button>
            <button
              className="action-btn calculate"
              onClick={() => handleCalculateIncome(activeTab)}
              disabled={calculating}
            >
              {calculating ? 'Calculating...' : 'Calculate Income'}
            </button>
          </div>
        </div>

        {/* Income Source Card */}
        {tabIncomeSource ? (
          <div className="income-source-card">
            <div className="source-header">
              <h4>{tabIncomeSource.source_name || activeTabConfig?.label}</h4>
              <span
                className="status-badge"
                style={{
                  backgroundColor: VERIFICATION_STATUSES[tabIncomeSource.verification_status]?.bgColor,
                  color: VERIFICATION_STATUSES[tabIncomeSource.verification_status]?.color,
                }}
              >
                {VERIFICATION_STATUSES[tabIncomeSource.verification_status]?.label}
              </span>
            </div>
            <div className="source-income-grid">
              <div className="income-box">
                <label>Gross Monthly</label>
                <span className="amount">{formatCurrency(tabIncomeSource.gross_monthly_income)}</span>
              </div>
              <div className="income-box">
                <label>Gross Annual</label>
                <span className="amount">{formatCurrency(tabIncomeSource.gross_annual_income)}</span>
              </div>
              <div className="income-box qualifying">
                <label>Qualifying Monthly</label>
                <span className="amount">{formatCurrency(tabIncomeSource.monthly_qualifying_income)}</span>
              </div>
              <div className="income-box qualifying">
                <label>Qualifying Annual</label>
                <span className="amount">{formatCurrency(tabIncomeSource.annual_qualifying_income)}</span>
              </div>
            </div>
            {tabIncomeSource.calculation_method && (
              <div className="calculation-method">
                <span className="method-label">Calculation Method:</span>
                <span className="method-value">{tabIncomeSource.calculation_method.replace(/_/g, ' ')}</span>
              </div>
            )}
            {tabIncomeSource.declining_income_flag && (
              <div className="warning-banner">
                Income is declining - using conservative calculation method
              </div>
            )}
          </div>
        ) : (
          <div className="no-income-source">
            <p>No income calculated for this type yet.</p>
            <p className="hint">Upload documents and click "Extract from Docs" to start.</p>
          </div>
        )}

        {/* Documents Section */}
        <div className="documents-section">
          <h4>Supporting Documents ({tabDocuments.length})</h4>
          {tabDocuments.length > 0 ? (
            <div className="documents-list">
              {tabDocuments.map(doc => (
                <div key={doc.id} className="document-row">
                  <div className="doc-icon">📄</div>
                  <div className="doc-info">
                    <span className="doc-name">{doc.file_name || doc.filename}</span>
                    <span className="doc-type">{doc.doc_type || doc.document_type}</span>
                  </div>
                  <div className="doc-date">{formatDate(doc.doc_date || doc.upload_date)}</div>
                  <div className="doc-status">
                    {doc.extraction_status === 'completed' ? (
                      <span className="extracted">Extracted</span>
                    ) : (
                      <span className="pending">Pending</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="no-documents">
              <p>No documents uploaded for this income type.</p>
              <p className="hint">Upload paystubs, W-2s, tax returns, etc. in the Documents section.</p>
            </div>
          )}
        </div>

        {/* Extracted Data Preview */}
        {extractedData[activeTab] && (
          <div className="extracted-data-section">
            <h4>Extracted Data</h4>
            <div className="extracted-grid">
              {Object.entries(extractedData[activeTab]).map(([key, value]) => (
                <div key={key} className="extracted-item">
                  <label>{key.replace(/_/g, ' ')}</label>
                  <span>{typeof value === 'number' ? formatCurrency(value) : value}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
