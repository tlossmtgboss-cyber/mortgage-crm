import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './DataUpload.css';

function DataUpload() {
  const navigate = useNavigate();
  const [uploadState, setUploadState] = useState('select'); // select, analyzing, questions, mapping, importing, complete
  const [file, setFile] = useState(null);
  const [parsedData, setParsedData] = useState(null);
  const [aiQuestions, setAiQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [columnMappings, setColumnMappings] = useState({});
  const [importResults, setImportResults] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState(null);

  // Clear any initial errors on mount
  useEffect(() => {
    setError(null);
  }, []);

  const handleFileSelect = (e) => {
    const selectedFile = e.target.files[0];
    if (!selectedFile) return;

    // Validate file type
    const validTypes = [
      'text/csv',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ];

    if (!validTypes.includes(selectedFile.type) &&
        !selectedFile.name.endsWith('.csv') &&
        !selectedFile.name.endsWith('.xlsx') &&
        !selectedFile.name.endsWith('.xls')) {
      setError('Please upload a CSV or Excel file');
      return;
    }

    setFile(selectedFile);
    setError(null);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();

    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      handleFileSelect({ target: { files: [droppedFile] } });
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const analyzeFile = async () => {
    if (!file) return;

    setIsProcessing(true);
    setUploadState('analyzing');
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      // Use relative URL to leverage Vercel proxy (see vercel.json)
      const response = await fetch('/api/v1/data-import/analyze', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: formData
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server error: ${response.status}`);
      }

      const data = await response.json();
      setParsedData(data.preview);
      setAiQuestions(data.questions || []);
      setColumnMappings(data.suggested_mappings || {});
      setUploadState('questions');
    } catch (err) {
      console.error('Analysis error:', err);
      let errorMessage = 'Failed to analyze file. Please try again.';
      if (err.message.includes('Failed to fetch')) {
        errorMessage = 'Unable to connect to server. Please check your internet connection and try again.';
      } else if (err.message) {
        errorMessage = err.message;
      }
      setError(errorMessage);
      setUploadState('select');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleAnswerQuestion = (questionId, answer) => {
    setAnswers({
      ...answers,
      [questionId]: answer
    });
  };

  const proceedToMapping = () => {
    setUploadState('mapping');
  };

  const handleColumnMappingChange = (sourceColumn, targetField) => {
    setColumnMappings({
      ...columnMappings,
      [sourceColumn]: targetField
    });
  };

  const importData = async () => {
    setIsProcessing(true);
    setUploadState('importing');
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('answers', JSON.stringify(answers));
      formData.append('mappings', JSON.stringify(columnMappings));

      // Use relative URL to leverage Vercel proxy (see vercel.json)
      const response = await fetch('/api/v1/data-import/execute', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: formData
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server error: ${response.status}`);
      }

      const result = await response.json();
      setImportResults(result);
      setUploadState('complete');
    } catch (err) {
      console.error('Import error:', err);
      let errorMessage = 'Failed to import data. Please try again.';
      if (err.message.includes('Failed to fetch')) {
        errorMessage = 'Unable to connect to server. Please check your internet connection and try again.';
      } else if (err.message) {
        errorMessage = err.message;
      }
      setError(errorMessage);
      setUploadState('mapping');
    } finally {
      setIsProcessing(false);
    }
  };

  const reset = () => {
    setUploadState('select');
    setFile(null);
    setParsedData(null);
    setAiQuestions([]);
    setAnswers({});
    setColumnMappings({});
    setImportResults(null);
    setError(null);
  };

  // CSV template for leads import
  const downloadLeadsTemplate = () => {
    const headers = [
      'First Name',
      'Last Name',
      'Email',
      'Phone',
      'Stage',
      'Property Address',
      'City',
      'State',
      'Zip Code',
      'Loan Amount',
      'Property Value',
      'Down Payment',
      'Credit Score',
      'Annual Income',
      'Loan Type',
      'Loan Officer',
      'Source',
      'Notes'
    ];

    const sampleData = [
      'John',
      'Smith',
      'john.smith@email.com',
      '555-123-4567',
      'New',
      '123 Main Street',
      'Austin',
      'TX',
      '78701',
      '350000',
      '450000',
      '90000',
      '720',
      '95000',
      'Conventional',
      '',
      'Website',
      'Interested in buying first home'
    ];

    const csvContent = headers.join(',') + '\n' + sampleData.join(',');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'leads_import_template.csv';
    link.click();
  };

  // CSV template for loans import
  const downloadLoansTemplate = () => {
    const headers = [
      'Loan Number',
      'Borrower First Name',
      'Borrower Last Name',
      'Borrower Email',
      'Borrower Phone',
      'Stage',
      'Property Address',
      'City',
      'State',
      'Zip Code',
      'Loan Amount',
      'Interest Rate',
      'Loan Term',
      'Loan Type',
      'Purchase Price',
      'Down Payment',
      'Closing Date',
      'Loan Officer',
      'Processor'
    ];

    const sampleData = [
      'LN-2024-001',
      'Jane',
      'Doe',
      'jane.doe@email.com',
      '555-987-6543',
      'Processing',
      '456 Oak Avenue',
      'Dallas',
      'TX',
      '75201',
      '280000',
      '6.5',
      '360',
      'FHA',
      '320000',
      '40000',
      '2024-03-15',
      '',
      ''
    ];

    const csvContent = headers.join(',') + '\n' + sampleData.join(',');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'loans_import_template.csv';
    link.click();
  };

  // CSV template for portfolio loans import
  const downloadPortfolioTemplate = () => {
    const headers = [
      'Loan Number',
      'Borrower Name',
      'Borrower Email',
      'Borrower Phone',
      'Property Address',
      'City',
      'State',
      'Zip Code',
      'Original Loan Amount',
      'Current Balance',
      'Interest Rate',
      'Loan Term',
      'Monthly Payment',
      'LTV',
      'APR',
      'Origination Date',
      'Maturity Date',
      'Last Payment Date',
      'Payment Status',
      'Loan Officer',
      'Processor'
    ];

    const sampleData = [
      'PF-2023-001',
      'Robert Johnson',
      'robert.johnson@email.com',
      '555-456-7890',
      '789 Pine Street',
      'Houston',
      'TX',
      '77001',
      '325000',
      '298500',
      '5.875',
      '360',
      '1923.45',
      '78.5',
      '6.125',
      '2023-06-15',
      '2053-06-15',
      '2024-11-01',
      'Current',
      '',
      ''
    ];

    const csvContent = headers.join(',') + '\n' + sampleData.join(',');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'portfolio_import_template.csv';
    link.click();
  };

  const targetFields = {
    leads: [
      // Identifiers
      { value: 'loan_number', label: 'Loan Number / File Name', group: 'Identifiers' },
      { value: 'organization_code', label: 'Organization Code', group: 'Identifiers' },
      // Contact Info
      { value: 'name', label: 'Full Name', group: 'Contact Info' },
      { value: 'first_name', label: 'First Name', group: 'Contact Info' },
      { value: 'last_name', label: 'Last Name', group: 'Contact Info' },
      { value: 'email', label: 'Email', group: 'Contact Info' },
      { value: 'phone', label: 'Phone', group: 'Contact Info' },
      { value: 'co_applicant_name', label: 'Co-Applicant Name', group: 'Contact Info' },
      { value: 'co_applicant_email', label: 'Co-Applicant Email', group: 'Contact Info' },
      { value: 'co_applicant_phone', label: 'Co-Applicant Phone', group: 'Contact Info' },
      { value: 'preferred_communication', label: 'Preferred Communication', group: 'Contact Info' },
      // Property Info
      { value: 'address', label: 'Property Address', group: 'Property Info' },
      { value: 'city', label: 'City', group: 'Property Info' },
      { value: 'state', label: 'State', group: 'Property Info' },
      { value: 'zip_code', label: 'Zip Code', group: 'Property Info' },
      { value: 'property_type', label: 'Property Type', group: 'Property Info' },
      { value: 'property_value', label: 'Property Value', group: 'Property Info' },
      // Loan Details
      { value: 'loan_type', label: 'Loan Type', group: 'Loan Details' },
      { value: 'program', label: 'Loan Program', group: 'Loan Details' },
      { value: 'loan_amount', label: 'Loan Amount', group: 'Loan Details' },
      { value: 'down_payment', label: 'Down Payment', group: 'Loan Details' },
      { value: 'interest_rate', label: 'Interest Rate', group: 'Loan Details' },
      { value: 'loan_term', label: 'Loan Term', group: 'Loan Details' },
      { value: 'preapproval_amount', label: 'Preapproval Amount', group: 'Loan Details' },
      { value: 'lender', label: 'Lender', group: 'Loan Details' },
      // Financial Info
      { value: 'credit_score', label: 'Credit Score', group: 'Financial Info' },
      { value: 'annual_income', label: 'Annual Income', group: 'Financial Info' },
      { value: 'monthly_debts', label: 'Monthly Debts', group: 'Financial Info' },
      { value: 'debt_to_income', label: 'DTI Ratio', group: 'Financial Info' },
      { value: 'dti_front', label: 'DTI Front', group: 'Financial Info' },
      { value: 'dti_back', label: 'DTI Back', group: 'Financial Info' },
      { value: 'ltv', label: 'LTV', group: 'Financial Info' },
      { value: 'cltv', label: 'CLTV', group: 'Financial Info' },
      { value: 'employment_status', label: 'Employment Status', group: 'Financial Info' },
      { value: 'first_time_buyer', label: 'First Time Buyer', group: 'Financial Info' },
      // Team & Source
      { value: 'source', label: 'Lead Source', group: 'Team & Source' },
      { value: 'loan_officer', label: 'Loan Officer', group: 'Team & Source' },
      { value: 'processor', label: 'Processor', group: 'Team & Source' },
      // Dates
      { value: 'created_at', label: 'Date Created', group: 'Dates' },
      { value: 'status_date', label: 'Status Date', group: 'Dates' },
      // Other
      { value: 'notes', label: 'Notes', group: 'Other' },
      { value: 'stage', label: 'Stage', group: 'Other' }
    ],
    loans: [
      // Loan Identifiers
      { value: 'loan_number', label: 'Loan Number', group: 'Loan Identifiers' },
      { value: 'stage', label: 'Loan Stage', group: 'Loan Identifiers' },
      // Borrower Info
      { value: 'borrower_name', label: 'Borrower Name', group: 'Borrower Info' },
      { value: 'borrower_email', label: 'Borrower Email', group: 'Borrower Info' },
      { value: 'borrower_phone', label: 'Borrower Phone', group: 'Borrower Info' },
      { value: 'coborrower_name', label: 'Co-Borrower Name', group: 'Borrower Info' },
      { value: 'co_borrower_email', label: 'Co-Borrower Email', group: 'Borrower Info' },
      { value: 'preferred_communication', label: 'Preferred Communication', group: 'Borrower Info' },
      // Loan Details
      { value: 'amount', label: 'Loan Amount', group: 'Loan Details' },
      { value: 'rate', label: 'Interest Rate', group: 'Loan Details' },
      { value: 'term', label: 'Loan Term (months)', group: 'Loan Details' },
      { value: 'program', label: 'Loan Program', group: 'Loan Details' },
      { value: 'loan_type', label: 'Loan Type', group: 'Loan Details' },
      { value: 'purchase_price', label: 'Purchase Price', group: 'Loan Details' },
      { value: 'down_payment', label: 'Down Payment', group: 'Loan Details' },
      { value: 'lender', label: 'Lender/Investor', group: 'Loan Details' },
      // Property Info
      { value: 'property_address', label: 'Property Address', group: 'Property Info' },
      { value: 'property_city', label: 'City', group: 'Property Info' },
      { value: 'property_state', label: 'State', group: 'Property Info' },
      { value: 'property_zip', label: 'Zip Code', group: 'Property Info' },
      { value: 'appraisal_value', label: 'Appraisal Value', group: 'Property Info' },
      // Team Members
      { value: 'loan_officer_name', label: 'Loan Officer', group: 'Team Members' },
      { value: 'loan_officer_email', label: 'LO Email', group: 'Team Members' },
      { value: 'processor', label: 'Processor', group: 'Team Members' },
      { value: 'processor_email', label: 'Processor Email', group: 'Team Members' },
      { value: 'underwriter', label: 'Underwriter', group: 'Team Members' },
      { value: 'underwriter_email', label: 'UW Email', group: 'Team Members' },
      { value: 'closer', label: 'Closer', group: 'Team Members' },
      { value: 'closer_email', label: 'Closer Email', group: 'Team Members' },
      { value: 'realtor_agent', label: 'Realtor/Agent', group: 'Team Members' },
      { value: 'title_company', label: 'Title Company', group: 'Team Members' },
      // Important Dates
      { value: 'closing_date', label: 'Closing Date', group: 'Important Dates' },
      { value: 'lock_date', label: 'Lock Date', group: 'Important Dates' },
      { value: 'lock_expiration_date', label: 'Lock Expiration', group: 'Important Dates' },
      { value: 'funded_date', label: 'Funded Date', group: 'Important Dates' },
      { value: 'contract_received_date', label: 'Contract Received', group: 'Important Dates' },
      { value: 'loan_estimate_sent_date', label: 'LE Sent Date', group: 'Important Dates' },
      { value: 'initial_disclosures_sent_date', label: 'Initial Disclosures Sent', group: 'Important Dates' },
      { value: 'initial_disclosures_signed_date', label: 'Initial Disclosures Signed', group: 'Important Dates' },
      { value: 'cd_received_signed_date', label: 'CD Signed', group: 'Important Dates' },
      { value: 'conditional_approval_date', label: 'Conditional Approval', group: 'Important Dates' },
      { value: 'final_closing_package_sent_date', label: 'Final Package Sent', group: 'Important Dates' },
      // Appraisal
      { value: 'appraisal_ordered_date', label: 'Appraisal Ordered', group: 'Appraisal' },
      { value: 'appraisal_scheduled_date', label: 'Appraisal Scheduled', group: 'Appraisal' },
      { value: 'appraisal_completed_date', label: 'Appraisal Completed', group: 'Appraisal' },
      // Rate Lock
      { value: 'lock_term_days', label: 'Lock Term (days)', group: 'Rate Lock' },
      { value: 'float_down_available', label: 'Float Down Available', group: 'Rate Lock' }
    ],
    portfolio: [
      // Loan Info
      { value: 'loan_number', label: 'Loan Number', group: 'Loan Info' },
      { value: 'borrower_name', label: 'Borrower Name', group: 'Loan Info' },
      { value: 'borrower_email', label: 'Borrower Email', group: 'Loan Info' },
      { value: 'borrower_phone', label: 'Borrower Phone', group: 'Loan Info' },
      // Property
      { value: 'property_address', label: 'Property Address', group: 'Property' },
      { value: 'property_city', label: 'City', group: 'Property' },
      { value: 'property_state', label: 'State', group: 'Property' },
      { value: 'property_zip', label: 'Zip Code', group: 'Property' },
      // Loan Details
      { value: 'original_loan_amount', label: 'Original Loan Amount', group: 'Loan Details' },
      { value: 'current_balance', label: 'Current Balance', group: 'Loan Details' },
      { value: 'rate', label: 'Interest Rate', group: 'Loan Details' },
      { value: 'term', label: 'Loan Term', group: 'Loan Details' },
      { value: 'monthly_payment', label: 'Monthly Payment', group: 'Loan Details' },
      { value: 'ltv', label: 'LTV', group: 'Loan Details' },
      { value: 'apr', label: 'APR', group: 'Loan Details' },
      // Dates
      { value: 'origination_date', label: 'Origination Date', group: 'Dates' },
      { value: 'maturity_date', label: 'Maturity Date', group: 'Dates' },
      { value: 'last_payment_date', label: 'Last Payment Date', group: 'Dates' },
      // Status
      { value: 'payment_status', label: 'Payment Status', group: 'Status' },
      // Team
      { value: 'loan_officer_name', label: 'Loan Officer', group: 'Team' },
      { value: 'processor', label: 'Processor', group: 'Team' }
    ]
  };

  // Determine destination based on answers
  const getDestination = () => {
    if (answers.destination) {
      return answers.destination;
    }
    // Default based on file analysis
    return 'leads';
  };

  return (
    <div className="data-upload-page">
      <div className="upload-header">
        <button className="btn-back" onClick={() => navigate('/settings')}>
          ← Back to Settings
        </button>
        <div>
          <h1>Data Management</h1>
          <p>Upload CSV or Excel files to import data into your CRM</p>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <span className="error-icon">⚠️</span>
          <span>{error}</span>
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      <div className="upload-content">
        {/* Step 1: File Selection */}
        {uploadState === 'select' && (
          <div className="upload-step">
            <div className="step-header">
              <h2>Step 1: Select File</h2>
              <p>Choose a CSV or Excel file to upload</p>
            </div>

            {/* Template Downloads */}
            <div className="template-section">
              <h3>Download Templates</h3>
              <p>Start with a pre-formatted template to ensure your data imports correctly</p>
              <div className="template-buttons">
                <button className="btn-template" onClick={downloadLeadsTemplate}>
                  <span className="template-icon">📋</span>
                  <div>
                    <div className="template-title">Leads Template</div>
                    <div className="template-desc">Import new prospects and contacts</div>
                  </div>
                  <span className="download-icon">⬇️</span>
                </button>
                <button className="btn-template" onClick={downloadLoansTemplate}>
                  <span className="template-icon">📑</span>
                  <div>
                    <div className="template-title">Loans Template</div>
                    <div className="template-desc">Import active loan files</div>
                  </div>
                  <span className="download-icon">⬇️</span>
                </button>
                <button className="btn-template" onClick={downloadPortfolioTemplate}>
                  <span className="template-icon">💼</span>
                  <div>
                    <div className="template-title">Portfolio Template</div>
                    <div className="template-desc">Import closed/funded loans for servicing</div>
                  </div>
                  <span className="download-icon">⬇️</span>
                </button>
              </div>
            </div>

            <div
              className="file-dropzone"
              onDrop={handleDrop}
              onDragOver={handleDragOver}
            >
              <div className="dropzone-icon">📂</div>
              <h3>Drag & drop your file here</h3>
              <p>or</p>
              <label className="btn-select-file">
                Choose File
                <input
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  onChange={handleFileSelect}
                  style={{ display: 'none' }}
                />
              </label>
              <p className="file-hint">Supported formats: CSV, Excel (.xlsx, .xls)</p>
            </div>

            {file && (
              <div className="selected-file-card">
                <div className="file-info">
                  <span className="file-icon">📄</span>
                  <div>
                    <div className="file-name">{file.name}</div>
                    <div className="file-size">{(file.size / 1024).toFixed(2)} KB</div>
                  </div>
                </div>
                <button className="btn-primary" onClick={analyzeFile}>
                  Analyze File →
                </button>
              </div>
            )}
          </div>
        )}

        {/* Step 2: Analyzing */}
        {uploadState === 'analyzing' && (
          <div className="upload-step">
            <div className="analyzing-card">
              <div className="spinner"></div>
              <h2>Analyzing your data...</h2>
              <p>AI is reviewing your file and preparing questions</p>
            </div>
          </div>
        )}

        {/* Step 3: AI Questions */}
        {uploadState === 'questions' && (
          <div className="upload-step">
            <div className="step-header">
              <h2>Step 2: Answer Questions</h2>
              <p>Help AI understand your data by answering these questions</p>
            </div>

            <div className="data-preview-card">
              <h3>Data Preview</h3>
              <p>First 5 rows of your file:</p>
              <div className="preview-table-container">
                <table className="preview-table">
                  <thead>
                    <tr>
                      {parsedData?.headers?.map((header, idx) => (
                        <th key={idx}>{header}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {parsedData?.rows?.slice(0, 5).map((row, rowIdx) => (
                      <tr key={rowIdx}>
                        {row.map((cell, cellIdx) => (
                          <td key={cellIdx}>{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="preview-stats">Total rows: {parsedData?.total_rows || 0}</p>
            </div>

            <div className="questions-card">
              <h3>Questions</h3>
              {aiQuestions.map((question, idx) => (
                <div key={idx} className="question-item">
                  <label className="question-label">{question.question}</label>
                  {question.type === 'choice' ? (
                    <div className="choice-options">
                      {question.options.map((option, optIdx) => (
                        <button
                          key={optIdx}
                          className={`choice-btn ${answers[question.id] === option.value ? 'selected' : ''}`}
                          onClick={() => handleAnswerQuestion(question.id, option.value)}
                        >
                          <span className="choice-icon">{option.icon}</span>
                          <div>
                            <div className="choice-label">{option.label}</div>
                            <div className="choice-description">{option.description}</div>
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <input
                      type="text"
                      className="text-input"
                      placeholder={question.placeholder}
                      value={answers[question.id] || ''}
                      onChange={(e) => handleAnswerQuestion(question.id, e.target.value)}
                    />
                  )}
                </div>
              ))}
            </div>

            <div className="step-actions">
              <button className="btn-secondary" onClick={reset}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={proceedToMapping}
                disabled={aiQuestions.some(q => !answers[q.id])}
              >
                Next: Map Columns →
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Column Mapping */}
        {uploadState === 'mapping' && (
          <div className="upload-step">
            <div className="step-header">
              <h2>Step 3: Map Columns</h2>
              <p>Match your file columns to CRM fields</p>
            </div>

            <div className="mapping-card">
              <div className="mapping-info">
                <span className="info-icon">💡</span>
                <p>AI has suggested mappings based on your data. Review and adjust as needed.</p>
              </div>

              <div className="mapping-grid">
                {parsedData?.headers?.map((header, idx) => (
                  <div key={idx} className="mapping-row">
                    <div className="source-column">
                      <span className="column-label">Your Column:</span>
                      <span className="column-name">{header}</span>
                      <span className="sample-value">
                        Sample: {parsedData.rows[0]?.[idx] || 'N/A'}
                      </span>
                    </div>
                    <div className="mapping-arrow">→</div>
                    <div className="target-column">
                      <select
                        className="mapping-select"
                        value={columnMappings[header] || ''}
                        onChange={(e) => handleColumnMappingChange(header, e.target.value)}
                      >
                        <option value="">Skip this column</option>
                        {(() => {
                          const fields = targetFields[getDestination()] || [];
                          const groups = [...new Set(fields.map(f => f.group))];
                          return groups.map(group => (
                            <optgroup key={group} label={group}>
                              {fields.filter(f => f.group === group).map(field => (
                                <option key={field.value} value={field.value}>
                                  {field.label}
                                </option>
                              ))}
                            </optgroup>
                          ));
                        })()}
                      </select>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="step-actions">
              <button className="btn-secondary" onClick={() => setUploadState('questions')}>
                ← Back
              </button>
              <button
                className="btn-primary"
                onClick={importData}
                disabled={Object.keys(columnMappings).filter(k => columnMappings[k]).length === 0}
              >
                Import Data →
              </button>
            </div>
          </div>
        )}

        {/* Step 5: Importing */}
        {uploadState === 'importing' && (
          <div className="upload-step">
            <div className="importing-card">
              <div className="spinner"></div>
              <h2>Importing your data...</h2>
              <p>Please wait while we add records to your CRM</p>
            </div>
          </div>
        )}

        {/* Step 6: Complete */}
        {uploadState === 'complete' && (
          <div className="upload-step">
            <div className="complete-card">
              <div className="success-icon">✓</div>
              <h2>Import Complete!</h2>
              <p>Your data has been successfully imported</p>

              <div className="results-summary">
                <div className="result-stat">
                  <div className="stat-value">{importResults?.total || 0}</div>
                  <div className="stat-label">Total Records</div>
                </div>
                <div className="result-stat success">
                  <div className="stat-value">{importResults?.imported || 0}</div>
                  <div className="stat-label">Imported</div>
                </div>
                <div className="result-stat error">
                  <div className="stat-value">{importResults?.failed || 0}</div>
                  <div className="stat-label">Failed</div>
                </div>
              </div>

              {importResults?.destination && (
                <div className="destination-info">
                  <p>Data was imported to: <strong>{importResults.destination}</strong></p>
                </div>
              )}

              {importResults?.errors && importResults.errors.length > 0 && (
                <div className="errors-section">
                  <h3>Errors</h3>
                  <ul className="error-list">
                    {importResults.errors.slice(0, 10).map((error, idx) => (
                      <li key={idx}>{error}</li>
                    ))}
                  </ul>
                  {importResults.errors.length > 10 && (
                    <p className="more-errors">
                      ...and {importResults.errors.length - 10} more errors
                    </p>
                  )}
                </div>
              )}

              <div className="complete-actions">
                <button className="btn-secondary" onClick={reset}>
                  Upload Another File
                </button>
                <button className="btn-primary" onClick={() => navigate('/leads')}>
                  View Imported Data →
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default DataUpload;
