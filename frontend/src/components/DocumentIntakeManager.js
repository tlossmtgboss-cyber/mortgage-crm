import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../services/api';
import './DocumentIntakeManager.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

function DocumentIntakeManager() {
  const [loading, setLoading] = useState(true);
  const [pendingIntakes, setPendingIntakes] = useState([]);
  const [selectedIntake, setSelectedIntake] = useState(null);
  const [intakeDetails, setIntakeDetails] = useState(null);
  const [docTypes, setDocTypes] = useState(null);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [classifying, setClassifying] = useState(null);
  const [searchBorrower, setSearchBorrower] = useState('');
  const [borrowerResults, setBorrowerResults] = useState([]);
  const [loanResults, setLoanResults] = useState([]);

  // Load pending intakes and doc types
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [intakesRes, typesRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/document-intake/pending`, {
          headers: { 'Authorization': `Bearer ${getToken()}` }
        }),
        fetch(`${API_BASE_URL}/api/v1/document-intake/doc-types`, {
          headers: { 'Authorization': `Bearer ${getToken()}` }
        })
      ]);

      if (intakesRes.ok) {
        const data = await intakesRes.json();
        setPendingIntakes(data);
      }

      if (typesRes.ok) {
        const data = await typesRes.json();
        setDocTypes(data);
      }
    } catch (error) {
      console.error('Error loading document intake data:', error);
      setMessage({ type: 'error', text: 'Failed to load document intake data' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Load intake details when selected
  const loadIntakeDetails = async (intakeId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/document-intake/${intakeId}`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });

      if (response.ok) {
        const data = await response.json();
        setIntakeDetails(data);
        setSelectedIntake(intakeId);
      }
    } catch (error) {
      console.error('Error loading intake details:', error);
      setMessage({ type: 'error', text: 'Failed to load intake details' });
    }
  };

  // Search for borrowers/loans
  const searchEntities = async (query) => {
    if (!query || query.length < 2) {
      setBorrowerResults([]);
      setLoanResults([]);
      return;
    }

    try {
      const [borrowersRes, loansRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/leads?search=${encodeURIComponent(query)}&limit=5`, {
          headers: { 'Authorization': `Bearer ${getToken()}` }
        }),
        fetch(`${API_BASE_URL}/api/v1/loans?search=${encodeURIComponent(query)}&limit=5`, {
          headers: { 'Authorization': `Bearer ${getToken()}` }
        })
      ]);

      if (borrowersRes.ok) {
        const data = await borrowersRes.json();
        setBorrowerResults(data.slice ? data.slice(0, 5) : []);
      }

      if (loansRes.ok) {
        const data = await loansRes.json();
        setLoanResults(data.slice ? data.slice(0, 5) : []);
      }
    } catch (error) {
      console.error('Error searching entities:', error);
    }
  };

  // Classify attachment
  const handleClassify = async (attachmentId, classification) => {
    setClassifying(attachmentId);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/document-intake/attachments/${attachmentId}/classify`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(classification)
      });

      if (response.ok) {
        const data = await response.json();
        setMessage({ type: 'success', text: `Classified as ${classification.doc_type}` });
        // Reload intake details
        if (selectedIntake) {
          loadIntakeDetails(selectedIntake);
        }
        loadData();
      } else {
        const error = await response.json();
        setMessage({ type: 'error', text: error.detail || 'Failed to classify' });
      }
    } catch (error) {
      console.error('Error classifying attachment:', error);
      setMessage({ type: 'error', text: 'Error classifying attachment' });
    } finally {
      setClassifying(null);
      setTimeout(() => setMessage({ type: '', text: '' }), 5000);
    }
  };

  // Discard attachment
  const handleDiscard = async (attachmentId, reason) => {
    setClassifying(attachmentId);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/document-intake/attachments/${attachmentId}/discard`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ reason })
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'Attachment discarded' });
        if (selectedIntake) {
          loadIntakeDetails(selectedIntake);
        }
        loadData();
      } else {
        const error = await response.json();
        setMessage({ type: 'error', text: error.detail || 'Failed to discard' });
      }
    } catch (error) {
      console.error('Error discarding attachment:', error);
      setMessage({ type: 'error', text: 'Error discarding attachment' });
    } finally {
      setClassifying(null);
      setTimeout(() => setMessage({ type: '', text: '' }), 5000);
    }
  };

  // Update match
  const handleUpdateMatch = async (intakeId, borrowerId, loanId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/document-intake/${intakeId}/match`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ borrower_id: borrowerId, loan_id: loanId })
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'Match updated' });
        loadIntakeDetails(intakeId);
        loadData();
      } else {
        const error = await response.json();
        setMessage({ type: 'error', text: error.detail || 'Failed to update match' });
      }
    } catch (error) {
      console.error('Error updating match:', error);
      setMessage({ type: 'error', text: 'Error updating match' });
    }
    setTimeout(() => setMessage({ type: '', text: '' }), 5000);
  };

  // Complete classification task
  const handleCompleteTask = async (taskId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/document-intake/tasks/${taskId}/complete`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'Classification task completed!' });
        setSelectedIntake(null);
        setIntakeDetails(null);
        loadData();
      } else {
        const error = await response.json();
        setMessage({ type: 'error', text: error.detail || 'Cannot complete - some attachments pending' });
      }
    } catch (error) {
      console.error('Error completing task:', error);
      setMessage({ type: 'error', text: 'Error completing task' });
    }
    setTimeout(() => setMessage({ type: '', text: '' }), 5000);
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  };

  if (loading) {
    return (
      <div className="document-intake-manager">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading document intake...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="document-intake-manager">
      <div className="manager-header">
        <div className="header-content">
          <h2>Document Intake Classification</h2>
          <p>Review and classify documents received via email</p>
        </div>
        <button className="refresh-btn" onClick={loadData}>
          Refresh
        </button>
      </div>

      {message.text && (
        <div className={`message-banner ${message.type}`}>
          {message.text}
          <button onClick={() => setMessage({ type: '', text: '' })} className="close-btn">x</button>
        </div>
      )}

      <div className="intake-layout">
        {/* Left Panel - Pending Intakes List */}
        <div className="intakes-panel">
          <h3>Pending Classification ({pendingIntakes.length})</h3>

          {pendingIntakes.length === 0 ? (
            <div className="empty-state">
              <span className="check-icon">&#10003;</span>
              <p>No documents pending classification</p>
            </div>
          ) : (
            <div className="intakes-list">
              {pendingIntakes.map(intake => (
                <div
                  key={intake.id}
                  className={`intake-card ${selectedIntake === intake.id ? 'selected' : ''}`}
                  onClick={() => loadIntakeDetails(intake.id)}
                >
                  <div className="intake-header">
                    <span className="from-email">{intake.from_email}</span>
                    <span className={`match-badge ${intake.match_status}`}>
                      {intake.match_status}
                    </span>
                  </div>
                  <div className="intake-subject">{intake.subject || '(No subject)'}</div>
                  <div className="intake-meta">
                    <span>{formatDate(intake.received_at)}</span>
                    <span className="attachment-count">
                      {intake.pending_attachments}/{intake.total_attachments} pending
                    </span>
                  </div>
                  {intake.matched_borrower && (
                    <div className="matched-to">
                      Matched: {intake.matched_borrower.name}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Panel - Classification Detail */}
        <div className="detail-panel">
          {!intakeDetails ? (
            <div className="no-selection">
              <span className="icon">&#128196;</span>
              <p>Select an email to classify documents</p>
            </div>
          ) : (
            <div className="intake-detail">
              {/* Email Info */}
              <div className="email-info">
                <h3>Email Details</h3>
                <div className="info-grid">
                  <div className="info-row">
                    <label>From:</label>
                    <span>{intakeDetails.from_email}</span>
                  </div>
                  <div className="info-row">
                    <label>Subject:</label>
                    <span>{intakeDetails.subject || '(No subject)'}</span>
                  </div>
                  <div className="info-row">
                    <label>Received:</label>
                    <span>{formatDate(intakeDetails.received_at)}</span>
                  </div>
                  {intakeDetails.body_snippet && (
                    <div className="info-row full">
                      <label>Preview:</label>
                      <span className="body-snippet">{intakeDetails.body_snippet}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Match Info */}
              <div className="match-section">
                <h4>Borrower/Loan Match</h4>
                <div className={`match-status ${intakeDetails.match_status}`}>
                  {intakeDetails.match_status === 'matched' ? (
                    <div className="matched-info">
                      <span className="match-icon">&#10003;</span>
                      <div>
                        {intakeDetails.matched_borrower && (
                          <div><strong>Borrower:</strong> {intakeDetails.matched_borrower.name}</div>
                        )}
                        {intakeDetails.matched_loan && (
                          <div><strong>Loan:</strong> {intakeDetails.matched_loan.loan_number}</div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="unmatched-info">
                      <span className="warning-icon">!</span>
                      <span>
                        {intakeDetails.match_status === 'multiple'
                          ? 'Multiple potential matches found'
                          : 'No match found - manual assignment required'}
                      </span>
                    </div>
                  )}
                </div>

                {/* Manual Match Search */}
                <div className="match-search">
                  <input
                    type="text"
                    placeholder="Search borrower or loan..."
                    value={searchBorrower}
                    onChange={(e) => {
                      setSearchBorrower(e.target.value);
                      searchEntities(e.target.value);
                    }}
                  />
                  {(borrowerResults.length > 0 || loanResults.length > 0) && (
                    <div className="search-results">
                      {borrowerResults.length > 0 && (
                        <div className="result-group">
                          <label>Borrowers</label>
                          {borrowerResults.map(b => (
                            <div
                              key={b.id}
                              className="result-item"
                              onClick={() => {
                                handleUpdateMatch(intakeDetails.id, b.id, null);
                                setSearchBorrower('');
                                setBorrowerResults([]);
                                setLoanResults([]);
                              }}
                            >
                              {b.name} - {b.email}
                            </div>
                          ))}
                        </div>
                      )}
                      {loanResults.length > 0 && (
                        <div className="result-group">
                          <label>Loans</label>
                          {loanResults.map(l => (
                            <div
                              key={l.id}
                              className="result-item"
                              onClick={() => {
                                handleUpdateMatch(intakeDetails.id, null, l.id);
                                setSearchBorrower('');
                                setBorrowerResults([]);
                                setLoanResults([]);
                              }}
                            >
                              {l.loan_number} - {l.borrower_name}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Attachments to Classify */}
              <div className="attachments-section">
                <h4>Attachments ({intakeDetails.attachments?.length || 0})</h4>

                {intakeDetails.attachments?.map(att => (
                  <AttachmentClassifier
                    key={att.id}
                    attachment={att}
                    docTypes={docTypes}
                    defaultBorrowerId={intakeDetails.matched_borrower?.id}
                    defaultLoanId={intakeDetails.matched_loan?.id}
                    onClassify={handleClassify}
                    onDiscard={handleDiscard}
                    isProcessing={classifying === att.id}
                    formatFileSize={formatFileSize}
                  />
                ))}
              </div>

              {/* Complete Task Button */}
              {intakeDetails.classification_task && (
                <div className="complete-section">
                  <button
                    className="complete-btn"
                    onClick={() => handleCompleteTask(intakeDetails.classification_task.id)}
                    disabled={intakeDetails.attachments?.some(
                      a => a.classification_status === 'pending'
                    )}
                  >
                    Complete Classification Task
                  </button>
                  {intakeDetails.attachments?.some(a => a.classification_status === 'pending') && (
                    <p className="complete-hint">Classify or discard all attachments first</p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Attachment Classifier Sub-component
function AttachmentClassifier({
  attachment,
  docTypes,
  defaultBorrowerId,
  defaultLoanId,
  onClassify,
  onDiscard,
  isProcessing,
  formatFileSize
}) {
  const [selectedType, setSelectedType] = useState(
    attachment.ai_suggested_doc_type || ''
  );
  const [selectedCategory, setSelectedCategory] = useState(
    attachment.ai_suggested_doc_category || ''
  );
  const [periodStart, setPeriodStart] = useState('');
  const [periodEnd, setPeriodEnd] = useState('');
  const [notes, setNotes] = useState('');
  const [showDiscard, setShowDiscard] = useState(false);
  const [discardReason, setDiscardReason] = useState('');

  // Auto-update category when type changes
  useEffect(() => {
    if (selectedType && docTypes?.type_to_category?.[selectedType]) {
      setSelectedCategory(docTypes.type_to_category[selectedType]);
    }
  }, [selectedType, docTypes]);

  const handleSubmitClassification = () => {
    if (!selectedType || !selectedCategory) {
      toast.error('Please select document type and category');
      return;
    }

    onClassify(attachment.id, {
      doc_type: selectedType,
      doc_category: selectedCategory,
      borrower_id: defaultBorrowerId,
      loan_id: defaultLoanId,
      period_start: periodStart || null,
      period_end: periodEnd || null,
      notes: notes || null
    });
  };

  const handleSubmitDiscard = () => {
    if (!discardReason) {
      toast.error('Please provide a reason for discarding');
      return;
    }
    onDiscard(attachment.id, discardReason);
  };

  // Already classified or discarded
  if (attachment.classification_status !== 'pending') {
    return (
      <div className={`attachment-item ${attachment.classification_status}`}>
        <div className="att-header">
          <span className="att-icon">
            {attachment.classification_status === 'classified' ? '&#10003;' : '&#10007;'}
          </span>
          <span className="att-filename">{attachment.filename}</span>
          <span className="att-size">{formatFileSize(attachment.file_size)}</span>
        </div>
        <div className="att-status">
          {attachment.classification_status === 'classified' ? (
            <span className="classified-as">
              Classified as: <strong>{attachment.classified_doc_type}</strong>
            </span>
          ) : (
            <span className="discarded-reason">
              Discarded: {attachment.discarded_reason}
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="attachment-item pending">
      <div className="att-header">
        <span className="att-icon file">&#128196;</span>
        <span className="att-filename">{attachment.filename}</span>
        <span className="att-size">{formatFileSize(attachment.file_size)}</span>
        <span className="att-type">{attachment.mime_type}</span>
      </div>

      {/* AI Suggestion */}
      {attachment.ai_suggested_doc_type && (
        <div className="ai-suggestion">
          <span className="ai-label">AI Suggestion:</span>
          <span className="ai-value">{attachment.ai_suggested_doc_type}</span>
          {attachment.ai_confidence && (
            <span className="ai-confidence">
              ({Math.round(attachment.ai_confidence * 100)}% confident)
            </span>
          )}
        </div>
      )}

      {!showDiscard ? (
        <div className="classification-form">
          <div className="form-row">
            <div className="form-field">
              <label>Document Type</label>
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
              >
                <option value="">Select type...</option>
                {docTypes?.doc_types?.map(type => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
            </div>

            <div className="form-field">
              <label>Category</label>
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
              >
                <option value="">Select category...</option>
                {docTypes?.doc_categories?.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Period fields for statements */}
          {(selectedType?.includes('STATEMENT') || selectedType === 'W2') && (
            <div className="form-row">
              <div className="form-field">
                <label>Period Start</label>
                <input
                  type="date"
                  value={periodStart}
                  onChange={(e) => setPeriodStart(e.target.value)}
                />
              </div>
              <div className="form-field">
                <label>Period End</label>
                <input
                  type="date"
                  value={periodEnd}
                  onChange={(e) => setPeriodEnd(e.target.value)}
                />
              </div>
            </div>
          )}

          <div className="form-row">
            <div className="form-field full">
              <label>Notes (optional)</label>
              <input
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Any additional notes..."
              />
            </div>
          </div>

          <div className="form-actions">
            <button
              className="classify-btn"
              onClick={handleSubmitClassification}
              disabled={isProcessing}
            >
              {isProcessing ? 'Classifying...' : 'Classify Document'}
            </button>
            <button
              className="discard-link"
              onClick={() => setShowDiscard(true)}
            >
              Discard as junk
            </button>
          </div>
        </div>
      ) : (
        <div className="discard-form">
          <label>Why discard this attachment?</label>
          <select
            value={discardReason}
            onChange={(e) => setDiscardReason(e.target.value)}
          >
            <option value="">Select reason...</option>
            <option value="Signature image">Signature image</option>
            <option value="Email footer/logo">Email footer/logo</option>
            <option value="Duplicate document">Duplicate document</option>
            <option value="Irrelevant/unrelated">Irrelevant/unrelated</option>
            <option value="Corrupted/unreadable">Corrupted/unreadable</option>
            <option value="Other">Other</option>
          </select>
          <div className="form-actions">
            <button
              className="discard-btn"
              onClick={handleSubmitDiscard}
              disabled={isProcessing}
            >
              {isProcessing ? 'Discarding...' : 'Confirm Discard'}
            </button>
            <button
              className="cancel-link"
              onClick={() => {
                setShowDiscard(false);
                setDiscardReason('');
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default DocumentIntakeManager;
