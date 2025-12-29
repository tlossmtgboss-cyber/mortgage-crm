import React, { useState, useEffect, useCallback, useRef } from 'react';
import './IncomeCalculatorModal.css';
import BankStatementWorksheet from './BankStatementWorksheet';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

// Custom hook for draggable modal
function useDraggable() {
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [hasBeenDragged, setHasBeenDragged] = useState(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const modalRef = useRef(null);

  const handleMouseDown = useCallback((e) => {
    // Only drag from header, not close button
    if (e.target.closest('.modal-close-btn')) return;

    setIsDragging(true);
    dragStart.current = {
      x: e.clientX - position.x,
      y: e.clientY - position.y,
    };
    e.preventDefault();
  }, [position]);

  const handleMouseMove = useCallback((e) => {
    if (!isDragging) return;

    setHasBeenDragged(true);
    setPosition({
      x: e.clientX - dragStart.current.x,
      y: e.clientY - dragStart.current.y,
    });
  }, [isDragging]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, handleMouseMove, handleMouseUp]);

  const resetPosition = useCallback(() => {
    setPosition({ x: 0, y: 0 });
    setHasBeenDragged(false);
  }, []);

  return {
    position,
    isDragging,
    hasBeenDragged,
    handleMouseDown,
    modalRef,
    resetPosition,
  };
}

// Income type configurations - All available types
const ALL_INCOME_TABS = [
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
    id: 'PARTNERSHIP_SCORP',
    label: 'S-Corp / K-1',
    shortLabel: 'K-1',
    icon: '🏢',
    docTypes: ['k1', 'tax_return', 'corporate_tax_return'],
    description: 'Income from S-Corporation or Partnership K-1',
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
    id: 'SOCIAL_SECURITY',
    label: 'Social Security',
    shortLabel: 'SS',
    icon: '🏛️',
    docTypes: ['social_security', 'ssa_1099'],
    description: 'Social Security retirement benefits',
  },
  {
    id: 'RETIREMENT_PENSION',
    label: 'Retirement/Pension',
    shortLabel: 'Pension',
    icon: '💰',
    docTypes: ['pension', '1099_r', 'retirement_statement'],
    description: 'Pension and retirement income',
  },
  {
    id: 'OTHER',
    label: 'Other Income',
    shortLabel: 'Other',
    icon: '📄',
    docTypes: ['other_income', 'alimony', 'child_support'],
    description: 'Other qualifying income sources',
  },
];

const VERIFICATION_STATUSES = {
  'PENDING': { label: 'Pending', color: '#f59e0b', bgColor: '#fef3c7' },
  'DOCUMENTS_RECEIVED': { label: 'Docs Received', color: '#3b82f6', bgColor: '#dbeafe' },
  'VERIFIED': { label: 'Verified', color: '#10b981', bgColor: '#d1fae5' },
  'NEEDS_ADDITIONAL_DOCS': { label: 'Needs Docs', color: '#ef4444', bgColor: '#fee2e2' },
  'CALCULATED': { label: 'Calculated', color: '#8b5cf6', bgColor: '#ede9fe' },
};

export default function IncomeCalculatorModal({ isOpen, onClose, loanId, borrowerId, borrowerName, onSave }) {
  const [activeTab, setActiveTab] = useState('W2_EMPLOYMENT');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [incomeSources, setIncomeSources] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [totalIncome, setTotalIncome] = useState({ monthly: 0, annual: 0 });
  const [error, setError] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);
  const [supportedTypes, setSupportedTypes] = useState([]);
  const [employmentStatus, setEmploymentStatus] = useState(null);
  const [incomeTabs, setIncomeTabs] = useState(ALL_INCOME_TABS);

  // Draggable modal hook
  const { position, isDragging, hasBeenDragged, handleMouseDown, modalRef, resetPosition } = useDraggable();

  const token = localStorage.getItem('token');

  // Reset position when modal closes
  useEffect(() => {
    if (!isOpen) {
      resetPosition();
    }
  }, [isOpen, resetPosition]);

  // Fetch supported income types based on borrower's employment status
  const fetchSupportedTypes = useCallback(async () => {
    if (!loanId) return;

    try {
      const params = new URLSearchParams();
      params.append('loan_id', loanId);
      if (borrowerId) params.append('borrower_id', borrowerId);

      const response = await fetch(
        `${API_BASE}/api/v1/income/supported-types?${params}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        const types = data.types || [];
        setSupportedTypes(types);
        setEmploymentStatus(data.employment_status || null);

        // Filter tabs based on supported types
        if (types.length > 0) {
          const supportedCodes = types.map(t => t.type_code);
          const filteredTabs = ALL_INCOME_TABS.filter(tab =>
            supportedCodes.includes(tab.id)
          );
          setIncomeTabs(filteredTabs.length > 0 ? filteredTabs : ALL_INCOME_TABS);

          // Set first supported type as active tab if current isn't supported
          if (filteredTabs.length > 0 && !supportedCodes.includes(activeTab)) {
            setActiveTab(filteredTabs[0].id);
          }
        }
      }
    } catch (err) {
      console.error('Error fetching supported types:', err);
      // Fallback to all tabs on error
      setIncomeTabs(ALL_INCOME_TABS);
    }
  }, [loanId, borrowerId, token, activeTab]);

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
      }
    } catch (err) {
      console.error('Error fetching income sources:', err);
      // Don't set error state for load failures - just log
    }
  }, [borrowerId, loanId, token]);

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

  useEffect(() => {
    if (isOpen) {
      const loadData = async () => {
        setLoading(true);
        setError(null);
        await Promise.all([fetchSupportedTypes(), fetchIncomeSources(), fetchDocuments()]);
        setLoading(false);
      };
      loadData();
    }
  }, [isOpen, fetchSupportedTypes, fetchIncomeSources, fetchDocuments]);

  // Get documents for a specific income type
  const getDocumentsForType = (incomeType) => {
    const tabConfig = ALL_INCOME_TABS.find(t => t.id === incomeType);
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
    setSaving(true);
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
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to extract income from documents');
      }

      await fetchIncomeSources();
      setHasChanges(true);
    } catch (err) {
      console.error('Error extracting income:', err);
      // Don't show raw "Failed to fetch" errors - provide user-friendly message
      const message = err.message === 'Failed to fetch'
        ? 'Unable to connect to server. Please try again.'
        : err.message;
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  // Calculate qualifying income
  const handleCalculateIncome = async (incomeType) => {
    setSaving(true);
    setError(null);

    try {
      const source = getIncomeSourceForType(incomeType);
      if (!source) {
        // Create income source first
        const createResponse = await fetch(
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
        if (!createResponse.ok) {
          const errorData = await createResponse.json().catch(() => ({}));
          throw new Error(errorData.detail || 'Failed to create income source');
        }
        await fetchIncomeSources();
      }

      // Trigger calculation
      const updatedSource = getIncomeSourceForType(incomeType) || source;
      if (updatedSource) {
        const calcResponse = await fetch(
          `${API_BASE}/api/v1/income/sources/${updatedSource.id}/calculate`,
          {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
            },
          }
        );
        if (!calcResponse.ok) {
          const errorData = await calcResponse.json().catch(() => ({}));
          throw new Error(errorData.detail || 'Failed to calculate income');
        }
      }

      await fetchIncomeSources();
      setHasChanges(true);
    } catch (err) {
      console.error('Error calculating income:', err);
      // Don't show raw "Failed to fetch" errors - provide user-friendly message
      const message = err.message === 'Failed to fetch'
        ? 'Unable to connect to server. Please try again.'
        : err.message;
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAndClose = () => {
    if (onSave) {
      onSave(totalIncome);
    }
    onClose();
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

  const formatEmploymentStatus = (status) => {
    const labels = {
      'employed': 'W-2 Employee',
      'self_employed': 'Self-Employed',
      'retired': 'Retired',
      'unemployed': 'Unemployed',
    };
    return labels[status] || status || 'Unknown';
  };

  if (!isOpen) return null;

  const activeTabConfig = ALL_INCOME_TABS.find(t => t.id === activeTab);
  const tabDocuments = getDocumentsForType(activeTab);
  const tabIncomeSource = getIncomeSourceForType(activeTab);

  return (
    <div
      className={`income-modal-overlay ${hasBeenDragged ? 'dragged' : ''}`}
      onClick={hasBeenDragged ? undefined : onClose}
    >
      <div
        ref={modalRef}
        className={`income-modal ${isDragging ? 'dragging' : ''} ${hasBeenDragged ? 'dragged' : ''}`}
        onClick={e => e.stopPropagation()}
        style={hasBeenDragged ? {
          transform: `translate(${position.x}px, ${position.y}px)`,
          transition: isDragging ? 'none' : 'box-shadow 0.2s ease',
        } : undefined}
      >
        {/* Modal Header - Draggable */}
        <div
          className={`income-modal-header ${isDragging ? 'dragging' : ''}`}
          onMouseDown={handleMouseDown}
        >
          <div className="header-drag-area">
            <span className="drag-indicator">⋮⋮</span>
            <h2>Income Calculator</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}>&times;</button>
        </div>

        {/* Total Income Banner */}
        <div className="income-total-banner">
          <div className="total-label">Total Qualifying Income</div>
          <div className="total-amounts">
            <span className="monthly">{formatCurrency(totalIncome.monthly)}/mo</span>
            <span className="divider">|</span>
            <span className="annual">{formatCurrency(totalIncome.annual)}/yr</span>
          </div>
        </div>

        {loading ? (
          <div className="income-modal-loading">
            <div className="loading-spinner"></div>
            <p>Loading income data...</p>
          </div>
        ) : (
          <div className="income-modal-body">
            {/* Tab Navigation - Dynamic based on borrower's employment type */}
            <div className="income-tabs-nav">
              {incomeTabs.map(tab => {
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

            {/* Employment Status Notice */}
            {employmentStatus && (
              <div className="employment-status-notice">
                <span className="employment-badge">{formatEmploymentStatus(employmentStatus)}</span>
                <span className="employment-hint">Showing income types for this employment status</span>
              </div>
            )}

            {/* Active Tab Content */}
            <div className="income-tab-content">
              {activeTab === 'BANK_STATEMENT' ? (
                /* Bank Statement Worksheet - Full Non-QM functionality */
                <BankStatementWorksheet
                  loanId={loanId}
                  borrowerId={borrowerId}
                  borrowerName={borrowerName}
                  onIncomeCalculated={(income) => {
                    setTotalIncome(prev => ({
                      monthly: prev.monthly + income.monthly,
                      annual: prev.annual + income.annual,
                    }));
                    setHasChanges(true);
                  }}
                />
              ) : (
                /* Standard Income Tab Content */
                <>
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
                        disabled={saving || tabDocuments.length === 0}
                      >
                        {saving ? 'Extracting...' : 'Extract from Docs'}
                      </button>
                      <button
                        className="action-btn calculate"
                        onClick={() => handleCalculateIncome(activeTab)}
                        disabled={saving}
                      >
                        {saving ? 'Calculating...' : 'Calculate Income'}
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
                </>
              )}
            </div>
          </div>
        )}

        {/* Modal Footer */}
        <div className="income-modal-footer">
          <button className="cancel-btn" onClick={onClose}>Cancel</button>
          <button
            className="save-btn"
            onClick={handleSaveAndClose}
            disabled={saving}
          >
            {hasChanges ? 'Save & Close' : 'Close'}
          </button>
        </div>
      </div>
    </div>
  );
}
