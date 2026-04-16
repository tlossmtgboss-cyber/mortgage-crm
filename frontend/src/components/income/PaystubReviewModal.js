import React, { useState, useEffect, useCallback } from 'react';
import './PaystubReviewModal.css';
import { getToken } from '../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const FIELD_SECTIONS = [
  {
    id: 'employer',
    title: 'Employer Information',
    fields: [
      { key: 'employer_name', label: 'Company Name' },
      { key: 'employer_address_line1', label: 'Address Line 1' },
      { key: 'employer_address_line2', label: 'Address Line 2' },
      { key: 'employer_city', label: 'City' },
      { key: 'employer_state', label: 'State' },
      { key: 'employer_zip', label: 'ZIP Code' },
      { key: 'employer_phone', label: 'Phone' },
      { key: 'employer_ein', label: 'EIN' },
    ],
  },
  {
    id: 'employee',
    title: 'Employee Information',
    fields: [
      { key: 'employee_name', label: 'Full Name' },
      { key: 'employee_address_line1', label: 'Address Line 1' },
      { key: 'employee_city', label: 'City' },
      { key: 'employee_state', label: 'State' },
      { key: 'employee_zip', label: 'ZIP Code' },
      { key: 'ssn_last4', label: 'SSN Last 4' },
      { key: 'employee_id', label: 'Employee ID' },
      { key: 'hire_date', label: 'Hire Date', type: 'date' },
    ],
  },
  {
    id: 'pay_period',
    title: 'Pay Period',
    fields: [
      { key: 'pay_period_start', label: 'Period Start', type: 'date' },
      { key: 'pay_period_end', label: 'Period End', type: 'date' },
      { key: 'pay_date', label: 'Pay Date', type: 'date' },
      { key: 'pay_frequency', label: 'Pay Frequency' },
    ],
  },
  {
    id: 'earnings',
    title: 'Current Earnings',
    fields: [
      { key: 'gross_pay', label: 'Gross Pay', type: 'currency' },
      { key: 'net_pay', label: 'Net Pay', type: 'currency' },
      { key: 'regular_hours', label: 'Regular Hours', type: 'number' },
      { key: 'overtime_hours', label: 'Overtime Hours', type: 'number' },
      { key: 'hourly_rate', label: 'Hourly Rate', type: 'currency' },
      { key: 'regular_earnings', label: 'Regular Earnings', type: 'currency' },
      { key: 'overtime_earnings', label: 'Overtime Earnings', type: 'currency' },
      { key: 'bonus', label: 'Bonus', type: 'currency' },
      { key: 'commission', label: 'Commission', type: 'currency' },
    ],
  },
  {
    id: 'ytd',
    title: 'Year-to-Date Totals',
    fields: [
      { key: 'ytd_gross', label: 'YTD Gross', type: 'currency' },
      { key: 'ytd_net', label: 'YTD Net', type: 'currency' },
      { key: 'ytd_bonus', label: 'YTD Bonus', type: 'currency' },
      { key: 'ytd_commission', label: 'YTD Commission', type: 'currency' },
      { key: 'ytd_overtime', label: 'YTD Overtime', type: 'currency' },
    ],
  },
  {
    id: 'deductions',
    title: 'Deductions',
    fields: [
      { key: 'federal_tax', label: 'Federal Tax', type: 'currency' },
      { key: 'state_tax', label: 'State Tax', type: 'currency' },
      { key: 'local_tax', label: 'Local Tax', type: 'currency' },
      { key: 'social_security', label: 'Social Security', type: 'currency' },
      { key: 'medicare', label: 'Medicare', type: 'currency' },
      { key: 'retirement_401k', label: '401(k)', type: 'currency' },
      { key: 'health_insurance', label: 'Health Insurance', type: 'currency' },
    ],
  },
];

export default function PaystubReviewModal({
  isOpen,
  onClose,
  documentId,
  borrowerId,
  loanId,
  currentData = {},
  onApply,
}) {
  const [extractedData, setExtractedData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [extracting, setExtracting] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState(null);
  const [selectedFields, setSelectedFields] = useState({});
  const [documentPreviewUrl, setDocumentPreviewUrl] = useState(null);

  const token = getToken();

  const formatValue = (value, type) => {
    if (value === null || value === undefined || value === '') return '-';

    switch (type) {
      case 'currency':
        return new Intl.NumberFormat('en-US', {
          style: 'currency',
          currency: 'USD',
        }).format(value);
      case 'date':
        try {
          return new Date(value).toLocaleDateString();
        } catch {
          return value;
        }
      case 'number':
        return Number(value).toLocaleString();
      default:
        return String(value);
    }
  };

  const extractPaystub = useCallback(async () => {
    if (!documentId) return;

    setExtracting(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/income/documents/${documentId}/extract`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to extract paystub data');
      }

      const data = await response.json();
      setExtractedData(data.extracted_data || {});
      setDocumentPreviewUrl(data.preview_url);

      // Auto-select fields that have extracted data and differ from current
      const autoSelected = {};
      FIELD_SECTIONS.forEach(section => {
        section.fields.forEach(field => {
          const extracted = data.extracted_data?.[field.key];
          const current = currentData[field.key];
          if (extracted && extracted !== current) {
            autoSelected[field.key] = true;
          }
        });
      });
      setSelectedFields(autoSelected);
    } catch (err) {
      console.error('Extraction error:', err);
      setError(err.message);
    } finally {
      setExtracting(false);
      setLoading(false);
    }
  }, [documentId, token, currentData]);

  useEffect(() => {
    if (isOpen && documentId) {
      setLoading(true);
      setExtractedData(null);
      setSelectedFields({});
      extractPaystub();
    }
  }, [isOpen, documentId, extractPaystub]);

  const toggleField = (key) => {
    setSelectedFields(prev => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const toggleSection = (sectionId) => {
    const section = FIELD_SECTIONS.find(s => s.id === sectionId);
    if (!section) return;

    const sectionFields = section.fields.map(f => f.key);
    const allSelected = sectionFields.every(key =>
      selectedFields[key] || !extractedData?.[key]
    );

    const newSelected = { ...selectedFields };
    sectionFields.forEach(key => {
      if (extractedData?.[key]) {
        newSelected[key] = !allSelected;
      }
    });
    setSelectedFields(newSelected);
  };

  const handleApply = async () => {
    const selectedKeys = Object.keys(selectedFields).filter(k => selectedFields[k]);
    if (selectedKeys.length === 0) return;

    setApplying(true);
    setError(null);

    try {
      const fieldsToApply = {};
      selectedKeys.forEach(key => {
        fieldsToApply[key] = extractedData[key];
      });

      const response = await fetch(
        `${API_BASE}/api/v1/income/apply-extraction`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            document_id: documentId,
            borrower_id: borrowerId,
            loan_id: loanId,
            extracted_data: extractedData,
            selected_fields: selectedKeys,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to apply extraction');
      }

      if (onApply) {
        onApply(fieldsToApply);
      }
      onClose();
    } catch (err) {
      console.error('Apply error:', err);
      setError(err.message);
    } finally {
      setApplying(false);
    }
  };

  const selectedCount = Object.values(selectedFields).filter(Boolean).length;

  if (!isOpen) return null;

  return (
    <div className="paystub-modal-overlay" onClick={onClose}>
      <div className="paystub-modal-content" onClick={e => e.stopPropagation()}>
        <div className="paystub-modal-header">
          <div className="header-left">
            <h2>Review Paystub Data</h2>
            <span className="ai-extraction-badge">
              <span className="sparkle">✨</span> AI Extracted
            </span>
          </div>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        {error && (
          <div className="extraction-error">
            <span className="error-icon">⚠️</span>
            {error}
            <button onClick={() => setError(null)}>Dismiss</button>
          </div>
        )}

        <div className="paystub-modal-body">
          {/* Document Preview Panel */}
          <div className="document-preview-panel">
            <div className="preview-header">
              <h3>Document Preview</h3>
            </div>
            <div className="preview-container">
              {loading || extracting ? (
                <div className="preview-loading">
                  <div className="loading-spinner"></div>
                  <p>{extracting ? 'Extracting data with AI...' : 'Loading...'}</p>
                </div>
              ) : documentPreviewUrl ? (
                <iframe
                  src={documentPreviewUrl}
                  title="Paystub Preview"
                  className="document-iframe"
                />
              ) : (
                <div className="preview-placeholder">
                  <span className="doc-icon">📄</span>
                  <p>Preview not available</p>
                </div>
              )}
            </div>
          </div>

          {/* Comparison Panel */}
          <div className="comparison-panel">
            {loading || extracting ? (
              <div className="comparison-loading">
                <div className="loading-spinner"></div>
                <p>Analyzing paystub with AI...</p>
              </div>
            ) : (
              <div className="sections-container">
                {FIELD_SECTIONS.map(section => {
                  const hasExtractedData = section.fields.some(
                    f => extractedData?.[f.key]
                  );
                  if (!hasExtractedData) return null;

                  const sectionSelectedCount = section.fields.filter(
                    f => selectedFields[f.key]
                  ).length;
                  const sectionExtractedCount = section.fields.filter(
                    f => extractedData?.[f.key]
                  ).length;

                  return (
                    <div key={section.id} className="comparison-section">
                      <div className="section-header">
                        <div className="section-title-row">
                          <h4>{section.title}</h4>
                          <span className="section-count">
                            {sectionSelectedCount}/{sectionExtractedCount}
                          </span>
                        </div>
                        <button
                          className="select-all-btn"
                          onClick={() => toggleSection(section.id)}
                        >
                          {sectionSelectedCount === sectionExtractedCount ? 'Deselect All' : 'Select All'}
                        </button>
                      </div>

                      <table className="comparison-table">
                        <thead>
                          <tr>
                            <th></th>
                            <th>Field</th>
                            <th>Current</th>
                            <th>Extracted</th>
                          </tr>
                        </thead>
                        <tbody>
                          {section.fields.map(field => {
                            const currentVal = currentData[field.key];
                            const extractedVal = extractedData?.[field.key];

                            if (!extractedVal) return null;

                            const isDifferent = currentVal !== extractedVal;
                            const isSelected = selectedFields[field.key];

                            return (
                              <tr
                                key={field.key}
                                className={`${isDifferent ? 'different' : ''} ${isSelected ? 'selected' : ''}`}
                                onClick={() => toggleField(field.key)}
                              >
                                <td className="checkbox-cell">
                                  <input
                                    type="checkbox"
                                    checked={isSelected || false}
                                    onChange={() => toggleField(field.key)}
                                    onClick={e => e.stopPropagation()}
                                  />
                                </td>
                                <td className="field-label">{field.label}</td>
                                <td className="current-value">
                                  {formatValue(currentVal, field.type)}
                                </td>
                                <td className="extracted-value">
                                  {formatValue(extractedVal, field.type)}
                                  {isDifferent && (
                                    <span className="change-indicator">New</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="paystub-modal-footer">
          <div className="footer-info">
            {selectedCount > 0 ? (
              <span className="selected-info">
                {selectedCount} field{selectedCount !== 1 ? 's' : ''} selected
              </span>
            ) : (
              <span className="hint-text">Select fields to update your profile</span>
            )}
          </div>
          <div className="footer-actions">
            <button className="cancel-btn" onClick={onClose} disabled={applying}>
              Cancel
            </button>
            <button
              className="apply-btn"
              onClick={handleApply}
              disabled={selectedCount === 0 || applying}
            >
              {applying ? 'Applying...' : `Apply Selected (${selectedCount})`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
