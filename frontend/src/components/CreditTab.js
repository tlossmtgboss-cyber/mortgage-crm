import React, { useState, useEffect } from 'react';
import api, { API_BASE_URL } from '../services/api';
import './CreditTab.css';
import { getToken } from '../utils/tokenStore';

/**
 * CreditTab Component
 * Displays credit report information, allows uploading credit reports,
 * and shows AI-analyzed credit items that need to be addressed with the applicant.
 */
function CreditTab({ leadId, loanId, borrowerId, formData = {} }) {
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [creditReports, setCreditReports] = useState([]);
  const [creditItems, setCreditItems] = useState([]);
  const [creditSummary, setCreditSummary] = useState(null);
  const [error, setError] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [showUploadModal, setShowUploadModal] = useState(false);

  // Helper function for authenticated API calls using centralized api
  const fetchWithAuth = async (endpoint, options = {}) => {
    const method = (options.method || 'GET').toLowerCase();
    const body = options.body ? JSON.parse(options.body) : undefined;
    const { data } = await api[method](endpoint, body);
    return data;
  };

  // Load credit data on mount
  useEffect(() => {
    loadCreditData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leadId, loanId]);

  const loadCreditData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch credit reports for this loan/lead
      const endpoint = loanId
        ? `/api/v1/loans/${loanId}/credit-reports`
        : `/api/v1/leads/${leadId}/credit-reports`;

      const response = await fetchWithAuth(endpoint);

      if (response) {
        setCreditReports(response.reports || []);
        setCreditItems(response.items || []);
        setCreditSummary(response.summary || null);
      }
    } catch (err) {
      console.error('Failed to load credit data:', err);
      // Set empty state if no credit data exists yet
      setCreditReports([]);
      setCreditItems([]);
      setCreditSummary(null);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    // Validate file type
    const allowedTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg'];
    if (!allowedTypes.includes(file.type)) {
      setError('Please upload a PDF or image file (PNG, JPG)');
      return;
    }

    // Validate file size (max 20MB)
    if (file.size > 20 * 1024 * 1024) {
      setError('File size must be less than 20MB');
      return;
    }

    try {
      setUploading(true);
      setError(null);
      setUploadProgress(0);

      const formData = new FormData();
      formData.append('file', file);
      formData.append('doc_type', 'CREDIT_REPORT');
      if (loanId) formData.append('loan_id', loanId);
      // Backend uses borrower_id - use leadId as borrower_id if no separate borrowerId
      if (borrowerId) {
        formData.append('borrower_id', borrowerId);
      } else if (leadId) {
        formData.append('borrower_id', leadId);
      }

      const token = getToken();
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const progress = Math.round((e.loaded / e.total) * 100);
          setUploadProgress(progress);
        }
      });

      const uploadPromise = new Promise((resolve, reject) => {
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(JSON.parse(xhr.responseText));
          } else {
            reject(new Error('Upload failed'));
          }
        };
        xhr.onerror = () => reject(new Error('Upload failed'));
      });

      xhr.open('POST', `${API_BASE_URL}/api/v1/documents/upload`);
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.send(formData);

      const result = await uploadPromise;

      // Refresh credit data after upload
      await loadCreditData();

      // Automatically trigger AI analysis
      if (result.document_id) {
        await analyzeReport(result.document_id);
      }

      setShowUploadModal(false);
    } catch (err) {
      console.error('Upload failed:', err);
      setError('Failed to upload credit report. Please try again.');
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  };

  const analyzeReport = async (documentId) => {
    try {
      setAnalyzing(true);
      setError(null);

      const response = await fetchWithAuth(`/api/v1/ai/analyze-credit-report`, {
        method: 'POST',
        body: JSON.stringify({
          document_id: documentId,
          loan_id: loanId,
          lead_id: leadId
        })
      });

      if (response) {
        // Refresh to get updated credit items
        await loadCreditData();
      }
    } catch (err) {
      console.error('Analysis failed:', err);
      setError('Failed to analyze credit report. Please try again.');
    } finally {
      setAnalyzing(false);
    }
  };

  const updateItemStatus = async (itemId, status, notes = '') => {
    try {
      await fetchWithAuth(`/api/v1/credit-items/${itemId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status, notes })
      });

      // Update local state
      setCreditItems(items =>
        items.map(item =>
          item.id === itemId ? { ...item, status, notes } : item
        )
      );
    } catch (err) {
      console.error('Failed to update item status:', err);
      setError('Failed to update item. Please try again.');
    }
  };

  const getScoreColor = (score) => {
    if (!score) return '#9e9e9e';
    if (score >= 740) return '#4caf50';
    if (score >= 670) return '#8bc34a';
    if (score >= 580) return '#ff9800';
    return '#f44336';
  };

  const getScoreLabel = (score) => {
    if (!score) return 'Unknown';
    if (score >= 740) return 'Excellent';
    if (score >= 670) return 'Good';
    if (score >= 580) return 'Fair';
    return 'Poor';
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'critical': return '#f44336';
      case 'high': return '#ff5722';
      case 'medium': return '#ff9800';
      case 'low': return '#4caf50';
      default: return '#9e9e9e';
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  if (loading) {
    return (
      <div className="credit-tab">
        <div className="loading-container">
          <div className="loading-spinner" />
          <p>Loading credit information...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="credit-tab">
      {/* Header */}
      <div className="credit-header">
        <div className="credit-header-left">
          <h2>Credit Analysis</h2>
          <p className="credit-subtitle">
            Upload and analyze credit reports to identify items for discussion
          </p>
        </div>
        <div className="credit-header-actions">
          <button
            className="btn-primary"
            onClick={() => setShowUploadModal(true)}
            disabled={uploading || analyzing}
          >
            <span className="btn-icon">+</span>
            Upload Credit Report
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Credit Score Summary */}
      {creditSummary && (
        <div className="credit-summary-card">
          <div className="score-section">
            <div className="score-display">
              <div
                className="score-circle"
                style={{ borderColor: getScoreColor(creditSummary.credit_score) }}
              >
                <span className="score-value">{creditSummary.credit_score || '---'}</span>
                <span className="score-label">{getScoreLabel(creditSummary.credit_score)}</span>
              </div>
            </div>
            <div className="score-details">
              <div className="score-bureau">
                <span className="label">Bureau:</span>
                <span className="value">{creditSummary.bureau || 'Tri-Merge'}</span>
              </div>
              <div className="score-date">
                <span className="label">Report Date:</span>
                <span className="value">{formatDate(creditSummary.report_date)}</span>
              </div>
            </div>
          </div>
          <div className="summary-stats">
            <div className="stat-item">
              <span className="stat-value">{creditSummary.total_accounts || 0}</span>
              <span className="stat-label">Total Accounts</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{creditSummary.open_accounts || 0}</span>
              <span className="stat-label">Open Accounts</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">${(creditSummary.total_debt || 0).toLocaleString()}</span>
              <span className="stat-label">Total Debt</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{creditSummary.utilization || 0}%</span>
              <span className="stat-label">Utilization</span>
            </div>
          </div>
        </div>
      )}

      {/* No Credit Data State */}
      {!creditSummary && creditReports.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">📊</div>
          <h3>No Credit Report Uploaded</h3>
          <p>Upload a credit report to get AI-powered analysis and identify items to discuss with the applicant.</p>
          <button
            className="btn-primary"
            onClick={() => setShowUploadModal(true)}
          >
            Upload Credit Report
          </button>
        </div>
      )}

      {/* Credit Items to Address */}
      {creditItems.length > 0 && (
        <div className="credit-items-section">
          <div className="section-header">
            <h3>Items to Address</h3>
            <span className="item-count">
              {creditItems.filter(i => i.status !== 'resolved').length} outstanding
            </span>
          </div>
          <div className="credit-items-list">
            {creditItems.map((item) => (
              <div
                key={item.id}
                className={`credit-item ${item.status === 'resolved' ? 'resolved' : ''}`}
              >
                <div className="item-header">
                  <div className="item-severity">
                    <span
                      className="severity-badge"
                      style={{ backgroundColor: getSeverityColor(item.severity) }}
                    >
                      {item.severity || 'Info'}
                    </span>
                  </div>
                  <div className="item-category">{item.category || 'General'}</div>
                  <div className="item-status">
                    <select
                      value={item.status || 'pending'}
                      onChange={(e) => updateItemStatus(item.id, e.target.value)}
                      className="status-select"
                    >
                      <option value="pending">Pending</option>
                      <option value="discussed">Discussed</option>
                      <option value="action_needed">Action Needed</option>
                      <option value="resolved">Resolved</option>
                    </select>
                  </div>
                </div>
                <div className="item-content">
                  <h4 className="item-title">{item.title}</h4>
                  <p className="item-description">{item.description}</p>
                  {item.recommendation && (
                    <div className="item-recommendation">
                      <span className="rec-label">AI Recommendation:</span>
                      <span className="rec-text">{item.recommendation}</span>
                    </div>
                  )}
                  {item.account_name && (
                    <div className="item-account">
                      <span className="account-label">Account:</span>
                      <span className="account-name">{item.account_name}</span>
                      {item.account_balance && (
                        <span className="account-balance">${item.account_balance.toLocaleString()}</span>
                      )}
                    </div>
                  )}
                </div>
                <div className="item-footer">
                  <span className="item-date">Found: {formatDate(item.created_at)}</span>
                  {item.updated_at && item.updated_at !== item.created_at && (
                    <span className="item-updated">Updated: {formatDate(item.updated_at)}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Credit Reports List */}
      {creditReports.length > 0 && (
        <div className="credit-reports-section">
          <div className="section-header">
            <h3>Uploaded Reports</h3>
          </div>
          <div className="reports-list">
            {creditReports.map((report) => (
              <div key={report.id} className="report-item">
                <div className="report-icon">📄</div>
                <div className="report-info">
                  <span className="report-name">{report.file_name || 'Credit Report'}</span>
                  <span className="report-date">Uploaded: {formatDate(report.uploaded_at)}</span>
                </div>
                <div className="report-actions">
                  {report.analysis_status === 'pending' && (
                    <button
                      className="btn-analyze"
                      onClick={() => analyzeReport(report.id)}
                      disabled={analyzing}
                    >
                      {analyzing ? 'Analyzing...' : 'Analyze'}
                    </button>
                  )}
                  {report.analysis_status === 'completed' && (
                    <span className="analysis-complete">✓ Analyzed</span>
                  )}
                  <button
                    className="btn-view"
                    onClick={() => window.open(report.file_url, '_blank')}
                  >
                    View
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="modal-overlay" onClick={() => !uploading && setShowUploadModal(false)}>
          <div className="upload-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Upload Credit Report</h3>
              <button
                className="modal-close"
                onClick={() => !uploading && setShowUploadModal(false)}
                disabled={uploading}
              >
                ×
              </button>
            </div>
            <div className="modal-content">
              <div className="upload-zone">
                <input
                  type="file"
                  id="credit-file-input"
                  accept=".pdf,.png,.jpg,.jpeg"
                  onChange={handleFileUpload}
                  disabled={uploading}
                  style={{ display: 'none' }}
                />
                <label htmlFor="credit-file-input" className="upload-label">
                  {uploading ? (
                    <div className="upload-progress">
                      <div className="progress-bar">
                        <div
                          className="progress-fill"
                          style={{ width: `${uploadProgress}%` }}
                        />
                      </div>
                      <span>{uploadProgress}% uploaded</span>
                    </div>
                  ) : (
                    <>
                      <div className="upload-icon">📤</div>
                      <span className="upload-text">
                        Click to upload or drag and drop
                      </span>
                      <span className="upload-hint">
                        PDF, PNG, or JPG (max 20MB)
                      </span>
                    </>
                  )}
                </label>
              </div>
              <div className="upload-tips">
                <h4>Supported Credit Reports:</h4>
                <ul>
                  <li>Tri-Merge Credit Report (PDF)</li>
                  <li>Single Bureau Report (Equifax, Experian, TransUnion)</li>
                  <li>Credit Karma Screenshot</li>
                  <li>Any credit report document</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Analyzing Overlay */}
      {analyzing && (
        <div className="analyzing-overlay">
          <div className="analyzing-content">
            <div className="loading-spinner large" />
            <h3>Analyzing Credit Report</h3>
            <p>AI is reviewing the credit report and identifying items to discuss...</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default CreditTab;
