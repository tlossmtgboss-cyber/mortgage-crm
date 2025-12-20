import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  NeedsListView,
  SmartDocumentUpload,
  DocumentStatusCard
} from '../components/smart-docs';
import { smartDocsAPI } from '../services/smartDocsApi';
import './SmartDocs.css';

function SmartDocs() {
  const [searchParams] = useSearchParams();
  const [selectedLoanId, setSelectedLoanId] = useState(searchParams.get('loan_id') || '');
  const [selectedLoan, setSelectedLoan] = useState(null);
  const [loans, setLoans] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [expiringDocs, setExpiringDocs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('needs-list');

  // Fetch loans for selector
  useEffect(() => {
    const fetchLoans = async () => {
      try {
        const response = await fetch('/api/v1/loans?limit=50');
        if (response.ok) {
          const data = await response.json();
          setLoans(data.loans || data || []);
        }
      } catch (error) {
        console.error('Error fetching loans:', error);
      }
    };
    fetchLoans();
  }, []);

  // Fetch documents when loan is selected
  useEffect(() => {
    if (selectedLoanId) {
      fetchDocuments();
      fetchExpiringDocs();
    }
  }, [selectedLoanId]);

  const fetchDocuments = async () => {
    if (!selectedLoanId) return;
    setLoading(true);
    try {
      const docs = await smartDocsAPI.getLoanDocuments(selectedLoanId);
      setDocuments(docs.documents || []);
    } catch (error) {
      console.error('Error fetching documents:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchExpiringDocs = async () => {
    try {
      const expiring = await smartDocsAPI.getExpiringDocuments(selectedLoanId, 30);
      setExpiringDocs(expiring.documents || []);
    } catch (error) {
      console.error('Error fetching expiring documents:', error);
    }
  };

  const handleDocumentUploaded = (result) => {
    fetchDocuments();
  };

  const handleRequestUpdated = () => {
    fetchDocuments();
  };

  return (
    <div className="smart-docs-page">
      <div className="smart-docs-header">
        <h1>Smart Document Collection</h1>
        <p className="subtitle">Intelligent document management with automated validation</p>
      </div>

      <div className="loan-selector">
        <label htmlFor="loan-select">Select Loan:</label>
        <select
          id="loan-select"
          value={selectedLoanId}
          onChange={(e) => {
            const loanId = e.target.value;
            setSelectedLoanId(loanId);
            const loan = loans.find(l => String(l.id) === loanId);
            setSelectedLoan(loan || null);
          }}
        >
          <option value="">-- Select a loan --</option>
          {loans.map((loan) => (
            <option key={loan.id} value={loan.id}>
              {loan.loan_number || loan.id} - {loan.borrower_name || 'Unknown Borrower'}
            </option>
          ))}
        </select>
      </div>

      {selectedLoanId && (
        <>
          {/* Expiring Documents Alert */}
          {expiringDocs.length > 0 && (
            <div className="expiring-docs-alert">
              <div className="alert-icon">!</div>
              <div className="alert-content">
                <strong>{expiringDocs.length} document(s) expiring soon</strong>
                <p>Some documents will need to be refreshed within the next 30 days.</p>
              </div>
            </div>
          )}

          {/* Tab Navigation */}
          <div className="smart-docs-tabs">
            <button
              className={`tab-btn ${activeTab === 'needs-list' ? 'active' : ''}`}
              onClick={() => setActiveTab('needs-list')}
            >
              Needs List
            </button>
            <button
              className={`tab-btn ${activeTab === 'documents' ? 'active' : ''}`}
              onClick={() => setActiveTab('documents')}
            >
              Documents ({documents.length})
            </button>
            <button
              className={`tab-btn ${activeTab === 'upload' ? 'active' : ''}`}
              onClick={() => setActiveTab('upload')}
            >
              Upload
            </button>
          </div>

          {/* Tab Content */}
          <div className="smart-docs-content">
            {activeTab === 'needs-list' && (
              <NeedsListView
                loanId={selectedLoanId}
                onRequestUpdated={handleRequestUpdated}
              />
            )}

            {activeTab === 'documents' && (
              <div className="documents-grid">
                {loading ? (
                  <div className="loading">Loading documents...</div>
                ) : documents.length === 0 ? (
                  <div className="no-documents">
                    <p>No documents uploaded yet.</p>
                    <button onClick={() => setActiveTab('upload')}>
                      Upload First Document
                    </button>
                  </div>
                ) : (
                  documents.map((doc) => (
                    <DocumentStatusCard
                      key={doc.id}
                      document={doc}
                      onView={() => window.open(doc.storage_key, '_blank')}
                      onReview={() => {/* Handle review */}}
                    />
                  ))
                )}
              </div>
            )}

            {activeTab === 'upload' && (
              <div className="upload-section">
                <SmartDocumentUpload
                  loanId={selectedLoanId}
                  borrowerId={selectedLoan?.borrower_id || selectedLoan?.primary_borrower_id || null}
                  onUploadComplete={handleDocumentUploaded}
                />
              </div>
            )}
          </div>
        </>
      )}

      {!selectedLoanId && (
        <div className="select-loan-prompt">
          <div className="prompt-icon">📄</div>
          <h2>Select a Loan to Manage Documents</h2>
          <p>Choose a loan from the dropdown above to view and manage its document requirements.</p>
        </div>
      )}
    </div>
  );
}

export default SmartDocs;
