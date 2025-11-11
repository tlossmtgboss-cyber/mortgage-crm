import React, { useState } from 'react';
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

      const response = await fetch(`${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/api/v1/data-import/analyze`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: formData
      });

      if (!response.ok) {
        throw new Error('Failed to analyze file');
      }

      const data = await response.json();
      setParsedData(data.preview);
      setAiQuestions(data.questions || []);
      setColumnMappings(data.suggested_mappings || {});
      setUploadState('questions');
    } catch (err) {
      console.error('Analysis error:', err);
      setError(err.message || 'Failed to analyze file. Please try again.');
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

      const response = await fetch(`${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/api/v1/data-import/execute`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: formData
      });

      if (!response.ok) {
        throw new Error('Failed to import data');
      }

      const result = await response.json();
      setImportResults(result);
      setUploadState('complete');
    } catch (err) {
      console.error('Import error:', err);
      setError(err.message || 'Failed to import data. Please try again.');
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

  const targetFields = {
    leads: [
      { value: 'first_name', label: 'First Name' },
      { value: 'last_name', label: 'Last Name' },
      { value: 'email', label: 'Email' },
      { value: 'phone', label: 'Phone' },
      { value: 'address', label: 'Address' },
      { value: 'city', label: 'City' },
      { value: 'state', label: 'State' },
      { value: 'zip_code', label: 'Zip Code' },
      { value: 'property_value', label: 'Property Value' },
      { value: 'loan_amount', label: 'Loan Amount' },
      { value: 'down_payment', label: 'Down Payment' },
      { value: 'employment_status', label: 'Employment Status' },
      { value: 'annual_income', label: 'Annual Income' },
      { value: 'credit_score', label: 'Credit Score' },
      { value: 'notes', label: 'Notes' }
    ],
    loans: [
      { value: 'loan_number', label: 'Loan Number' },
      { value: 'borrower_name', label: 'Borrower Name' },
      { value: 'co_borrower_name', label: 'Co-Borrower Name' },
      { value: 'property_address', label: 'Property Address' },
      { value: 'loan_amount', label: 'Loan Amount' },
      { value: 'interest_rate', label: 'Interest Rate' },
      { value: 'loan_term', label: 'Loan Term (months)' },
      { value: 'loan_type', label: 'Loan Type' },
      { value: 'loan_purpose', label: 'Loan Purpose' },
      { value: 'closing_date', label: 'Closing Date' },
      { value: 'lender', label: 'Lender' },
      { value: 'processor', label: 'Processor' },
      { value: 'underwriter', label: 'Underwriter' }
    ],
    portfolio: [
      { value: 'loan_number', label: 'Loan Number' },
      { value: 'borrower_name', label: 'Borrower Name' },
      { value: 'property_address', label: 'Property Address' },
      { value: 'original_loan_amount', label: 'Original Loan Amount' },
      { value: 'current_balance', label: 'Current Balance' },
      { value: 'interest_rate', label: 'Interest Rate' },
      { value: 'monthly_payment', label: 'Monthly Payment' },
      { value: 'origination_date', label: 'Origination Date' },
      { value: 'maturity_date', label: 'Maturity Date' },
      { value: 'last_payment_date', label: 'Last Payment Date' },
      { value: 'payment_status', label: 'Payment Status' }
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
          <h1>Data Upload</h1>
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
                        <optgroup label="Lead Fields">
                          {targetFields[getDestination()]?.map(field => (
                            <option key={field.value} value={field.value}>
                              {field.label}
                            </option>
                          ))}
                        </optgroup>
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
