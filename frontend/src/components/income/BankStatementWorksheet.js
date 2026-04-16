import React, { useState, useEffect, useCallback } from 'react';
import './BankStatementWorksheet.css';
import { getToken } from '../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const CALCULATION_METHODS = [
  {
    id: 'UNIFORM_EXPENSE_RATIO',
    label: 'Method 1: Uniform Expense Ratio',
    shortLabel: '50%/60% Expense Ratio',
    description: '50% expense ratio for LTV ≤ 80%, 60% for LTV > 80%',
    requiresCPA: false,
  },
  {
    id: 'CPA_PL',
    label: 'Method 2: CPA Prepared P&L',
    shortLabel: 'CPA P&L',
    description: 'Income based on CPA-prepared Profit & Loss statement',
    requiresCPA: true,
  },
  {
    id: 'CPA_EXPENSE_RATIO',
    label: 'Method 3: CPA Letter Expense Ratio',
    shortLabel: 'CPA Expense Ratio',
    description: 'Uses CPA-stated expense ratio from letter',
    requiresCPA: true,
  },
];

export default function BankStatementWorksheet({ loanId, borrowerId, borrowerName, onIncomeCalculated }) {
  const [loading, setLoading] = useState(true);
  const [extracting, setExtracting] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [worksheet, setWorksheet] = useState(null);
  const [worksheetId, setWorksheetId] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Settings
  const [statementType, setStatementType] = useState('PERSONAL');
  const [calculationMethod, setCalculationMethod] = useState('UNIFORM_EXPENSE_RATIO');
  const [ltv, setLtv] = useState(80);
  const [ownershipPct, setOwnershipPct] = useState(100);
  const [cpaExpenseRatio, setCpaExpenseRatio] = useState('');
  const [businessName, setBusinessName] = useState('');
  const [hasSeparateBusiness, setHasSeparateBusiness] = useState(false);

  const token = getToken();

  // Fetch existing worksheet for the loan
  const fetchWorksheet = useCallback(async () => {
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/bank-statements/loan/${loanId}/worksheet`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        if (data.exists && data.worksheet_id) {
          setWorksheetId(data.worksheet_id);
          // Fetch full worksheet details
          const detailResponse = await fetch(
            `${API_BASE}/api/v1/bank-statements/worksheets/${data.worksheet_id}`,
            {
              headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
              },
            }
          );
          if (detailResponse.ok) {
            const worksheetData = await detailResponse.json();
            setWorksheet(worksheetData);
            setCalculationMethod(worksheetData.calculation_method || 'UNIFORM_EXPENSE_RATIO');
            setLtv(worksheetData.ltv_percentage || 80);
            setOwnershipPct(worksheetData.ownership_percentage || 100);
            setBusinessName(worksheetData.business_name || '');
            setHasSeparateBusiness(worksheetData.has_separate_business_account || false);
            if (worksheetData.cpa_expense_ratio) {
              setCpaExpenseRatio(worksheetData.cpa_expense_ratio.toString());
            }
          }
        }
      }
    } catch (err) {
      console.error('Error fetching worksheet:', err);
    }
  }, [loanId, token]);

  // Fetch bank statement documents
  const fetchDocuments = useCallback(async () => {
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
        const allDocs = data.documents || data || [];
        // Filter for bank statements
        const bankStatements = allDocs.filter(doc => {
          const docType = (doc.doc_type || doc.document_type || '').toLowerCase();
          return docType.includes('bank') || docType.includes('statement');
        });
        setDocuments(bankStatements);
      }
    } catch (err) {
      console.error('Error fetching documents:', err);
    }
  }, [loanId, token]);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchWorksheet(), fetchDocuments()]);
      setLoading(false);
    };
    loadData();
  }, [fetchWorksheet, fetchDocuments]);

  // Create or update worksheet
  const handleCreateWorksheet = async () => {
    setError(null);
    setExtracting(true);

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/bank-statements/worksheets`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            loan_id: loanId,
            borrower_id: borrowerId,
            borrower_name: borrowerName || 'Borrower',
            business_name: businessName,
            ownership_percentage: ownershipPct,
            months_of_statements: 12,
            calculation_method: calculationMethod,
            ltv_percentage: ltv,
            cpa_expense_ratio: cpaExpenseRatio ? parseFloat(cpaExpenseRatio) : null,
            has_separate_business_account: hasSeparateBusiness,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create worksheet');
      }

      const data = await response.json();
      setWorksheetId(data.worksheet_id);
      setSuccess('Worksheet created successfully');

      // Fetch the full worksheet
      await fetchWorksheet();
    } catch (err) {
      setError(err.message);
    } finally {
      setExtracting(false);
    }
  };

  // Extract data from selected documents
  const handleExtractData = async () => {
    if (selectedDocs.length === 0) {
      setError('Please select at least one bank statement to extract');
      return;
    }

    if (!worksheetId) {
      await handleCreateWorksheet();
    }

    setError(null);
    setExtracting(true);

    try {
      const currentWorksheetId = worksheetId || (await createAndGetWorksheetId());

      const response = await fetch(
        `${API_BASE}/api/v1/bank-statements/worksheets/${currentWorksheetId}/extract`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            document_ids: selectedDocs,
            statement_type: statementType,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to extract data');
      }

      const data = await response.json();
      setSuccess(`Extracted ${data.months_extracted} months of data`);

      // Refresh worksheet data
      await fetchWorksheet();

      // Notify parent of calculated income
      if (onIncomeCalculated && data.calculated_monthly_income) {
        onIncomeCalculated({
          monthly: data.calculated_monthly_income,
          annual: data.calculated_annual_income,
        });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setExtracting(false);
    }
  };

  const createAndGetWorksheetId = async () => {
    const response = await fetch(
      `${API_BASE}/api/v1/bank-statements/worksheets`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          loan_id: loanId,
          borrower_id: borrowerId,
          borrower_name: borrowerName || 'Borrower',
          business_name: businessName,
          ownership_percentage: ownershipPct,
          months_of_statements: 12,
          calculation_method: calculationMethod,
          ltv_percentage: ltv,
          cpa_expense_ratio: cpaExpenseRatio ? parseFloat(cpaExpenseRatio) : null,
          has_separate_business_account: hasSeparateBusiness,
        }),
      }
    );

    if (!response.ok) {
      throw new Error('Failed to create worksheet');
    }

    const data = await response.json();
    setWorksheetId(data.worksheet_id);
    return data.worksheet_id;
  };

  // Download worksheet as Excel
  const handleDownloadWorksheet = async () => {
    if (!worksheetId) {
      setError('No worksheet to download');
      return;
    }

    setDownloading(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/bank-statements/worksheets/${worksheetId}/download`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to download worksheet');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Bank_Statement_Worksheet_${borrowerName?.replace(/\s+/g, '_') || 'Borrower'}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      setSuccess('Worksheet downloaded successfully');
    } catch (err) {
      setError(err.message);
    } finally {
      setDownloading(false);
    }
  };

  const toggleDocSelection = (docId) => {
    setSelectedDocs(prev =>
      prev.includes(docId)
        ? prev.filter(id => id !== docId)
        : [...prev, docId]
    );
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

  if (loading) {
    return (
      <div className="bsw-loading">
        <div className="loading-spinner"></div>
        <p>Loading bank statement data...</p>
      </div>
    );
  }

  return (
    <div className="bank-statement-worksheet">
      {/* Messages */}
      {error && (
        <div className="bsw-error">
          {error}
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}
      {success && (
        <div className="bsw-success">
          {success}
          <button onClick={() => setSuccess(null)}>&times;</button>
        </div>
      )}

      {/* Configuration Section */}
      <div className="bsw-config-section">
        <h4>Non-QM Bank Statement Program Settings</h4>

        <div className="bsw-config-grid">
          <div className="config-item">
            <label>Statement Type</label>
            <select
              value={statementType}
              onChange={e => setStatementType(e.target.value)}
            >
              <option value="PERSONAL">Personal Bank Statements</option>
              <option value="BUSINESS">Business Bank Statements</option>
            </select>
          </div>

          <div className="config-item">
            <label>Calculation Method</label>
            <select
              value={calculationMethod}
              onChange={e => setCalculationMethod(e.target.value)}
            >
              {CALCULATION_METHODS.map(method => (
                <option key={method.id} value={method.id}>
                  {method.shortLabel}
                </option>
              ))}
            </select>
          </div>

          <div className="config-item">
            <label>LTV %</label>
            <input
              type="number"
              value={ltv}
              onChange={e => setLtv(parseFloat(e.target.value) || 0)}
              min="0"
              max="100"
              step="0.1"
            />
          </div>

          {statementType === 'BUSINESS' && (
            <>
              <div className="config-item">
                <label>Ownership %</label>
                <input
                  type="number"
                  value={ownershipPct}
                  onChange={e => setOwnershipPct(parseFloat(e.target.value) || 0)}
                  min="0"
                  max="100"
                  step="1"
                />
              </div>

              <div className="config-item">
                <label>Business Name</label>
                <input
                  type="text"
                  value={businessName}
                  onChange={e => setBusinessName(e.target.value)}
                  placeholder="Enter business name"
                />
              </div>
            </>
          )}

          {calculationMethod === 'CPA_EXPENSE_RATIO' && (
            <div className="config-item">
              <label>CPA Expense Ratio %</label>
              <input
                type="number"
                value={cpaExpenseRatio}
                onChange={e => setCpaExpenseRatio(e.target.value)}
                min="0"
                max="100"
                step="0.1"
                placeholder="e.g., 35"
              />
            </div>
          )}

          <div className="config-item checkbox-item">
            <label>
              <input
                type="checkbox"
                checked={hasSeparateBusiness}
                onChange={e => setHasSeparateBusiness(e.target.checked)}
              />
              Has Separate Business Account
            </label>
          </div>
        </div>

        <p className="method-description">
          {CALCULATION_METHODS.find(m => m.id === calculationMethod)?.description}
        </p>
      </div>

      {/* Document Selection */}
      <div className="bsw-documents-section">
        <div className="section-header">
          <h4>Select Bank Statements ({documents.length} available)</h4>
          {documents.length > 0 && (
            <button
              className="select-all-btn"
              onClick={() => setSelectedDocs(
                selectedDocs.length === documents.length
                  ? []
                  : documents.map(d => d.id)
              )}
            >
              {selectedDocs.length === documents.length ? 'Deselect All' : 'Select All'}
            </button>
          )}
        </div>

        {documents.length > 0 ? (
          <div className="bsw-documents-list">
            {documents.map(doc => (
              <div
                key={doc.id}
                className={`bsw-doc-item ${selectedDocs.includes(doc.id) ? 'selected' : ''}`}
                onClick={() => toggleDocSelection(doc.id)}
              >
                <input
                  type="checkbox"
                  checked={selectedDocs.includes(doc.id)}
                  onChange={() => {}}
                />
                <span className="doc-icon">📄</span>
                <div className="doc-info">
                  <span className="doc-name">{doc.file_name || doc.filename}</span>
                  <span className="doc-type">{doc.doc_type || doc.document_type}</span>
                </div>
                <span className="doc-status">
                  {doc.status === 'accepted' ? '✓' : '○'}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="bsw-no-docs">
            <p>No bank statement documents uploaded yet.</p>
            <p className="hint">Upload 12 months of bank statements in the Documents section.</p>
          </div>
        )}
      </div>

      {/* Results Section */}
      {worksheet && worksheet.accounts && worksheet.accounts.length > 0 && (
        <div className="bsw-results-section">
          <h4>Extracted Data</h4>

          {worksheet.accounts.map((account, idx) => (
            <div key={idx} className="bsw-account-card">
              <div className="account-header">
                <span className="account-type">{account.statement_type} Account</span>
                <span className="bank-info">{account.bank_name} ****{account.account_last_four}</span>
              </div>

              <div className="monthly-data-table">
                <table>
                  <thead>
                    <tr>
                      <th>Month</th>
                      <th>Total Deposits</th>
                      <th>Ineligible</th>
                      <th>Eligible</th>
                      <th>Beginning Bal</th>
                      <th>Ending Bal</th>
                      <th>NSFs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {account.monthly_data?.map((month, midx) => (
                      <tr key={midx}>
                        <td>{month.statement_month || `Month ${month.month_number}`}</td>
                        <td>{formatCurrency(month.total_deposits)}</td>
                        <td>{formatCurrency(month.ineligible_deposits)}</td>
                        <td>{formatCurrency(month.eligible_deposits)}</td>
                        <td>{formatCurrency(month.beginning_balance)}</td>
                        <td>{formatCurrency(month.ending_balance)}</td>
                        <td>{month.nsf_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}

          {/* Calculated Income */}
          <div className="bsw-income-summary">
            <div className="income-box">
              <label>Monthly Qualifying Income</label>
              <span className="amount">{formatCurrency(worksheet.calculated_monthly_income)}</span>
            </div>
            <div className="income-box">
              <label>Annual Qualifying Income</label>
              <span className="amount">{formatCurrency(worksheet.calculated_annual_income)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="bsw-actions">
        <button
          className="bsw-btn extract"
          onClick={handleExtractData}
          disabled={extracting || selectedDocs.length === 0}
        >
          {extracting ? (
            <>
              <span className="spinner"></span>
              Extracting...
            </>
          ) : (
            <>
              Extract Data ({selectedDocs.length} statements)
            </>
          )}
        </button>

        <button
          className="bsw-btn download"
          onClick={handleDownloadWorksheet}
          disabled={downloading || !worksheetId}
        >
          {downloading ? (
            <>
              <span className="spinner"></span>
              Downloading...
            </>
          ) : (
            <>
              Download Excel Worksheet
            </>
          )}
        </button>
      </div>
    </div>
  );
}
