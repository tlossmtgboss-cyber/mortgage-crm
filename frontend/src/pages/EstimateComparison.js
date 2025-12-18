import React, { useState, useCallback, useRef, useEffect } from 'react';
import './EstimateComparison.css';

const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

const CALENDLY_URL = "https://calendly.com/timlossteam/client-reengagement-clone?hide_event_type_details=1&hide_gdpr_banner=1";

function EstimateComparison() {
  // State for estimates A and B
  const [estimateA, setEstimateA] = useState(null);
  const [estimateB, setEstimateB] = useState(null);
  const [fileA, setFileA] = useState(null);
  const [fileB, setFileB] = useState(null);

  // Loading states
  const [loadingA, setLoadingA] = useState(false);
  const [loadingB, setLoadingB] = useState(false);
  const [comparing, setComparing] = useState(false);

  // Results
  const [comparison, setComparison] = useState(null);
  const [error, setError] = useState(null);

  // Provenance accordion state
  const [expandedProvenance, setExpandedProvenance] = useState({});

  // Calendly modal state
  const [showCalendly, setShowCalendly] = useState(false);

  // File input refs
  const fileInputA = useRef(null);
  const fileInputB = useRef(null);

  // Load Calendly script when modal opens
  useEffect(() => {
    if (showCalendly) {
      // Check if script already exists
      if (!document.querySelector('script[src="https://assets.calendly.com/assets/external/widget.js"]')) {
        const script = document.createElement('script');
        script.src = 'https://assets.calendly.com/assets/external/widget.js';
        script.async = true;
        document.body.appendChild(script);
      }
      // Prevent body scroll when modal is open
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }

    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [showCalendly]);

  // Handle schedule call button click
  const handleScheduleCall = () => {
    if (comparison?.comparison_id) {
      // Track conversion
      fetch(`${API_BASE_URL}/api/v1/estimate-parser/compare/convert?comparison_id=${comparison.comparison_id}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      }).catch(err => console.error('Failed to track conversion:', err));
    }
    setShowCalendly(true);
  };

  // Format currency
  const formatCurrency = (amount) => {
    if (amount === null || amount === undefined) return '—';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  // Format percentage
  const formatPercent = (value) => {
    if (value === null || value === undefined) return '—';
    return `${parseFloat(value).toFixed(3)}%`;
  };

  // Parse estimate from file
  const parseEstimate = async (file, setEstimate, setLoading, label) => {
    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${API_BASE_URL}/api/v1/estimate-parser/parse`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: formData
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || data.detail || 'Failed to parse estimate');
      }

      if (data.success && data.data) {
        setEstimate({
          ...data.data,
          doc_hash: data.data.doc_hash,
          request_id: data.request_id
        });
      } else {
        throw new Error(data.error || 'Failed to parse estimate');
      }
    } catch (err) {
      console.error(`Parse error (${label}):`, err);
      setError(`Failed to parse ${label}: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Handle file selection
  const handleFileSelect = (e, side) => {
    const file = e.target.files[0];
    if (!file) return;

    // Validate file type
    const validTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'];
    if (!validTypes.includes(file.type)) {
      setError('Please upload a PDF or image file (JPG, PNG, WebP)');
      return;
    }

    // Validate size (15MB max)
    if (file.size > 15 * 1024 * 1024) {
      setError('File size must be under 15MB');
      return;
    }

    if (side === 'A') {
      setFileA(file);
      setEstimateA(null);
      parseEstimate(file, setEstimateA, setLoadingA, 'Estimate A');
    } else {
      setFileB(file);
      setEstimateB(null);
      parseEstimate(file, setEstimateB, setLoadingB, 'Estimate B');
    }
  };

  // Handle drag and drop
  const handleDrop = useCallback((e, side) => {
    e.preventDefault();
    e.stopPropagation();

    const file = e.dataTransfer.files[0];
    if (file) {
      handleFileSelect({ target: { files: [file] } }, side);
    }
  }, []);

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  // Compare estimates
  const compareEstimates = async () => {
    if (!estimateA?.doc_hash || !estimateB?.doc_hash) {
      setError('Please upload both estimates first');
      return;
    }

    setComparing(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/estimate-parser/compare`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          estimate_a_hash: estimateA.doc_hash,
          estimate_b_hash: estimateB.doc_hash,
          session_id: `session_${Date.now()}`
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to compare estimates');
      }

      if (data.success) {
        setComparison(data);
      } else {
        throw new Error('Comparison failed');
      }
    } catch (err) {
      console.error('Compare error:', err);
      setError(`Failed to compare estimates: ${err.message}`);
    } finally {
      setComparing(false);
    }
  };

  // Track conversion click
  const handleCTAClick = async () => {
    if (comparison?.comparison_id) {
      try {
        await fetch(`${API_BASE_URL}/api/v1/estimate-parser/compare/convert?comparison_id=${comparison.comparison_id}`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        });
      } catch (err) {
        console.error('Failed to track conversion:', err);
      }
    }
    // Open contact form or redirect
    window.open('/apply', '_blank');
  };

  // Download PDF
  const handleDownloadPDF = async () => {
    if (!comparison?.comparison_id) return;

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/estimate-parser/compare/${comparison.comparison_id}/pdf`,
        {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        }
      );

      if (!response.ok) {
        throw new Error('Failed to generate PDF');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `loan_comparison_${comparison.comparison_id.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('PDF download error:', err);
      setError('Failed to download PDF. Please try again.');
    }
  };

  // Toggle provenance accordion
  const toggleProvenance = (key) => {
    setExpandedProvenance(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  // Reset and start over
  const reset = () => {
    setEstimateA(null);
    setEstimateB(null);
    setFileA(null);
    setFileB(null);
    setComparison(null);
    setError(null);
    setExpandedProvenance({});
    if (fileInputA.current) fileInputA.current.value = '';
    if (fileInputB.current) fileInputB.current.value = '';
  };

  // Render upload card
  const renderUploadCard = (side, file, estimate, loading) => {
    const isA = side === 'A';

    return (
      <div className={`estimate-card ${comparison?.winner === side ? 'winner' : ''}`}>
        {comparison?.winner === side && (
          <div className="winner-badge">
            <span className="trophy">🏆</span>
            <span>Best Option</span>
          </div>
        )}

        <h3>Estimate {side}</h3>

        {!estimate && !loading && (
          <div
            className="upload-zone"
            onDrop={(e) => handleDrop(e, side)}
            onDragOver={handleDragOver}
            onClick={() => isA ? fileInputA.current?.click() : fileInputB.current?.click()}
          >
            <div className="upload-icon">📄</div>
            <p>Drop your Loan Estimate here</p>
            <p className="hint">or click to browse</p>
            <p className="formats">PDF, JPG, PNG, WebP (max 15MB)</p>
            <input
              ref={isA ? fileInputA : fileInputB}
              type="file"
              accept=".pdf,image/jpeg,image/png,image/webp"
              onChange={(e) => handleFileSelect(e, side)}
              style={{ display: 'none' }}
            />
          </div>
        )}

        {loading && (
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Analyzing document...</p>
            <p className="hint">Extracting loan details with AI</p>
          </div>
        )}

        {estimate && !loading && (
          <div className="estimate-details">
            <div className="file-info">
              <span className="file-icon">✓</span>
              <span className="file-name">{file?.name || 'Document parsed'}</span>
              <button className="btn-remove" onClick={() => {
                if (isA) {
                  setEstimateA(null);
                  setFileA(null);
                  if (fileInputA.current) fileInputA.current.value = '';
                } else {
                  setEstimateB(null);
                  setFileB(null);
                  if (fileInputB.current) fileInputB.current.value = '';
                }
                setComparison(null);
              }}>✕</button>
            </div>

            {estimate.needs_review && (
              <div className="review-warning">
                <span>⚠️</span>
                <span>Some values may need review</span>
              </div>
            )}

            <div className="detail-grid">
              <div className="detail-row highlight">
                <span className="label">Loan Amount</span>
                <span className="value">{formatCurrency(estimate.loan_amount)}</span>
              </div>
              <div className="detail-row">
                <span className="label">Interest Rate</span>
                <span className="value">{formatPercent(estimate.interest_rate)}</span>
              </div>
              <div className="detail-row">
                <span className="label">APR</span>
                <span className="value">{formatPercent(estimate.apr)}</span>
              </div>
              <div className="detail-row">
                <span className="label">Monthly P&I</span>
                <span className="value">{formatCurrency(estimate.monthly_principal_and_interest)}</span>
              </div>
              <div className="detail-row highlight">
                <span className="label">Total Closing Costs</span>
                <span className="value">{formatCurrency(estimate.total_closing_costs)}</span>
              </div>
              <div className="detail-row highlight">
                <span className="label">Cash to Close</span>
                <span className="value">{formatCurrency(estimate.cash_to_close)}</span>
              </div>
              {estimate.loan_type && (
                <div className="detail-row">
                  <span className="label">Loan Type</span>
                  <span className="value">{estimate.loan_type}</span>
                </div>
              )}
              {estimate.loan_term && (
                <div className="detail-row">
                  <span className="label">Loan Term</span>
                  <span className="value">{estimate.loan_term}</span>
                </div>
              )}
            </div>

            {/* Provenance snippets */}
            {estimate.provenance && Object.keys(estimate.provenance).length > 0 && (
              <div className="provenance-section">
                <button
                  className="provenance-toggle"
                  onClick={() => toggleProvenance(side)}
                >
                  <span>{expandedProvenance[side] ? '▼' : '▶'}</span>
                  <span>Show me where this came from</span>
                </button>

                {expandedProvenance[side] && (
                  <div className="provenance-content">
                    {Object.entries(estimate.provenance).map(([field, snippet]) => (
                      <div key={field} className="provenance-item">
                        <span className="provenance-field">{field.replace(/_/g, ' ')}:</span>
                        <span className="provenance-snippet">"{snippet}"</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {estimate.confidence_score && (
              <div className="confidence-badge">
                Confidence: {Math.round(estimate.confidence_score * 100)}%
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="estimate-comparison-page">
      <div className="page-header">
        <div className="header-content">
          <h1>Compare Loan Estimates</h1>
          <p>Upload two loan estimates to see which one saves you money</p>
        </div>
        {(estimateA || estimateB || comparison) && (
          <button className="btn-reset" onClick={reset}>
            Start Over
          </button>
        )}
      </div>

      {error && (
        <div className="error-banner">
          <span className="error-icon">⚠️</span>
          <span>{error}</span>
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      <div className="comparison-container">
        <div className="estimates-row">
          {renderUploadCard('A', fileA, estimateA, loadingA)}

          <div className="vs-divider">
            <span>VS</span>
          </div>

          {renderUploadCard('B', fileB, estimateB, loadingB)}
        </div>

        {/* Compare button */}
        {estimateA && estimateB && !comparison && (
          <div className="compare-action">
            <button
              className="btn-compare"
              onClick={compareEstimates}
              disabled={comparing}
            >
              {comparing ? (
                <>
                  <span className="spinner-small"></span>
                  Comparing...
                </>
              ) : (
                <>
                  <span className="compare-icon">⚖️</span>
                  Compare Estimates
                </>
              )}
            </button>
          </div>
        )}

        {/* Comparison results */}
        {comparison && (
          <div className="comparison-results">
            <div className="result-header">
              <h2>Comparison Results</h2>
              {comparison.winner && (
                <div className="winner-announcement">
                  <span className="trophy-large">🏆</span>
                  <div className="winner-text">
                    <span className="winner-label">Estimate {comparison.winner} is the better option</span>
                    <span className="winner-reason">{comparison.reason}</span>
                  </div>
                </div>
              )}
            </div>

            {comparison.savings_amount > 0 && (
              <div className="savings-card">
                <div className="savings-amount">
                  {formatCurrency(comparison.savings_amount)}
                </div>
                <div className="savings-label">
                  {comparison.savings_message || 'Potential Savings'}
                </div>
              </div>
            )}

            {/* Side by side comparison table */}
            <div className="comparison-table">
              <div className="table-header">
                <div className="col-label"></div>
                <div className="col-a">Estimate A</div>
                <div className="col-b">Estimate B</div>
                <div className="col-diff">Difference</div>
              </div>

              {[
                { label: 'Cash to Close', key: 'cash_to_close', format: formatCurrency },
                { label: 'Total Closing Costs', key: 'total_closing_costs', format: formatCurrency },
                { label: 'APR', key: 'apr', format: formatPercent },
                { label: 'Interest Rate', key: 'interest_rate', format: formatPercent },
                { label: 'Monthly P&I', key: 'monthly_principal_and_interest', format: formatCurrency },
                { label: 'Loan Amount', key: 'loan_amount', format: formatCurrency },
              ].map(({ label, key, format }) => {
                const valA = comparison.estimate_a?.[key];
                const valB = comparison.estimate_b?.[key];
                const diff = (valA && valB) ? valA - valB : null;
                const isCurrency = format === formatCurrency;

                return (
                  <div key={key} className="table-row">
                    <div className="col-label">{label}</div>
                    <div className={`col-a ${comparison.winner === 'A' && key === 'cash_to_close' ? 'better' : ''}`}>
                      {format(valA)}
                    </div>
                    <div className={`col-b ${comparison.winner === 'B' && key === 'cash_to_close' ? 'better' : ''}`}>
                      {format(valB)}
                    </div>
                    <div className={`col-diff ${diff < 0 ? 'positive' : diff > 0 ? 'negative' : ''}`}>
                      {diff !== null ? (
                        isCurrency
                          ? `${diff > 0 ? '+' : ''}${formatCurrency(diff)}`
                          : `${diff > 0 ? '+' : ''}${diff.toFixed(3)}%`
                      ) : '—'}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Actions */}
            <div className="results-actions">
              <button className="btn-download" onClick={handleDownloadPDF}>
                <span className="download-icon">📄</span>
                Download PDF Report
              </button>
            </div>

            {/* CTA */}
            <div className="cta-section">
              <div className="cta-content">
                <h3>Want to get an even better deal?</h3>
                <p>Let our experts review your situation and find you the best rate.</p>
              </div>
              <div className="cta-buttons">
                <button className="btn-schedule" onClick={handleScheduleCall}>
                  <span className="calendar-icon">📅</span>
                  Schedule a Free Call
                </button>
                <button className="btn-cta" onClick={handleCTAClick}>
                  Get My Custom Quote
                  <span className="arrow">→</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Calendly Modal */}
        {showCalendly && (
          <div className="calendly-modal-overlay" onClick={() => setShowCalendly(false)}>
            <div className="calendly-modal" onClick={(e) => e.stopPropagation()}>
              <div className="calendly-modal-header">
                <h3>Schedule Your Free Consultation</h3>
                <p>No cost, no obligation - just expert advice on your loan options</p>
                <button className="btn-close-modal" onClick={() => setShowCalendly(false)}>
                  ✕
                </button>
              </div>
              <div className="calendly-modal-body">
                <div
                  className="calendly-inline-widget"
                  data-url={CALENDLY_URL}
                  style={{ minWidth: '320px', height: '630px' }}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Footer info */}
      <div className="page-footer">
        <div className="footer-info">
          <p>
            <strong>Privacy First:</strong> Your documents are processed securely.
            Personal information is redacted before AI analysis.
          </p>
          <p className="disclaimer">
            This tool provides estimates for comparison purposes only.
            Actual loan terms may vary. Contact a loan officer for official quotes.
          </p>
        </div>
      </div>
    </div>
  );
}

export default EstimateComparison;
