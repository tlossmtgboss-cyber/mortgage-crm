/**
 * Automatic Data Import Component
 * Zero-configuration Excel/CSV imports with intelligent field mapping
 */

import React, { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { API_BASE_URL } from '../../services/api';
import './AutoDataImport.css';

function AutoDataImport({ onImportComplete }) {
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [progress, setProgress] = useState(0);
  const [activeTab, setActiveTab] = useState('stats');
  const [destination, setDestination] = useState('loans'); // 'loans' or 'leads'

  const onDrop = useCallback(async (acceptedFiles) => {
    const file = acceptedFiles[0];
    if (!file) return;

    setUploading(true);
    setProgress(0);
    setResult(null);

    try {
      // Simulate progress
      const progressInterval = setInterval(() => {
        setProgress(prev => Math.min(prev + 10, 90));
      }, 300);

      const formData = new FormData();
      formData.append('file', file);
      formData.append('use_ai', 'false');
      formData.append('table_name', destination);

      const response = await fetch(`${API_BASE_URL}/api/v1/auto-import`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: formData,
      });

      clearInterval(progressInterval);
      setProgress(100);

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || data.message || 'Import failed');
      }

      setResult(data);

      // Notify parent component
      if (onImportComplete) {
        onImportComplete(data);
      }

    } catch (error) {
      console.error('Import error:', error);
      setResult({
        success: false,
        message: error.message || 'Import failed',
        stats: {
          total_rows: 0,
          successful_rows: 0,
          failed_rows: 0,
          fields_matched: 0,
          confidence_average: 0,
        },
        mappings: [],
        errors: [error.message || 'Unknown error'],
      });
    } finally {
      setUploading(false);
      setTimeout(() => setProgress(0), 2000);
    }
  }, [onImportComplete, destination]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
      'text/csv': ['.csv'],
    },
    maxFiles: 1,
    disabled: uploading,
  });

  const clearResults = () => {
    setResult(null);
  };

  return (
    <div className="auto-data-import">
      {/* Upload Area */}
      <div className="upload-card">
        <div className="card-header">
          <h3>Automatic Import</h3>
          <p className="card-description">
            Drop your Excel file and fields will be automatically mapped using AI-powered recognition
          </p>
        </div>
        <div className="card-content">
          {/* Destination Selector */}
          <div className="destination-selector">
            <label className="destination-label">Import to:</label>
            <div className="destination-options">
              <button
                type="button"
                className={`destination-btn ${destination === 'leads' ? 'active' : ''}`}
                onClick={() => setDestination('leads')}
                disabled={uploading}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
                <span>Leads</span>
              </button>
              <button
                type="button"
                className={`destination-btn ${destination === 'loans' ? 'active' : ''}`}
                onClick={() => setDestination('loans')}
                disabled={uploading}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <line x1="10" y1="9" x2="8" y2="9" />
                </svg>
                <span>Loans</span>
              </button>
              <button
                type="button"
                className={`destination-btn ${destination === 'mum_clients' ? 'active' : ''}`}
                onClick={() => setDestination('mum_clients')}
                disabled={uploading}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                <span>Closed Loans</span>
              </button>
            </div>
          </div>

          <div
            {...getRootProps()}
            className={`file-dropzone ${isDragActive ? 'drag-active' : ''} ${uploading ? 'disabled' : ''}`}
          >
            <input {...getInputProps()} />

            {uploading ? (
              <div className="uploading-state">
                <div className="spinner"></div>
                <div className="progress-container">
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${progress}%` }}></div>
                  </div>
                  <p className="progress-text">Processing and importing data... {progress}%</p>
                </div>
              </div>
            ) : (
              <div className="dropzone-content">
                <div className="upload-icon">
                  <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="17 8 12 3 7 8" />
                    <line x1="12" y1="3" x2="12" y2="15" />
                  </svg>
                </div>
                <div className="dropzone-text">
                  <p className="primary-text">
                    {isDragActive ? 'Drop your file here' : 'Drag & drop your file here'}
                  </p>
                  <p className="secondary-text">or click to browse</p>
                </div>
                <div className="file-formats">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                    <polyline points="14 2 14 8 20 8" />
                  </svg>
                  <span>Supported formats: CSV, Excel (.xlsx, .xls)</span>
                </div>
              </div>
            )}
          </div>

          {/* Info Alert */}
          <div className="info-alert">
            <div className="alert-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
            </div>
            <div className="alert-content">
              <h4>Automatic Field Mapping</h4>
              <p>
                Your Excel columns will be automatically matched to CRM fields using intelligent
                pattern recognition. No manual configuration required!
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Results */}
      {result && (
        <div className="results-card">
          <div className="results-header">
            <div className="result-title">
              {result.success ? (
                <>
                  <span className="success-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                      <polyline points="22 4 12 14.01 9 11.01" />
                    </svg>
                  </span>
                  <span>Import Successful</span>
                </>
              ) : (
                <>
                  <span className="error-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10" />
                      <line x1="12" y1="8" x2="12" y2="12" />
                      <line x1="12" y1="16" x2="12.01" y2="16" />
                    </svg>
                  </span>
                  <span>Import Failed</span>
                </>
              )}
            </div>
            <button className="btn-clear" onClick={clearResults}>
              Clear Results
            </button>
          </div>
          <p className="result-message">{result.message}</p>

          {/* Tabs */}
          <div className="tabs">
            <button
              className={`tab ${activeTab === 'stats' ? 'active' : ''}`}
              onClick={() => setActiveTab('stats')}
            >
              Statistics
            </button>
            <button
              className={`tab ${activeTab === 'mappings' ? 'active' : ''}`}
              onClick={() => setActiveTab('mappings')}
            >
              Field Mappings
            </button>
            <button
              className={`tab ${activeTab === 'warnings' ? 'active' : ''}`}
              onClick={() => setActiveTab('warnings')}
            >
              Warnings {result.warnings && `(${result.warnings.length})`}
            </button>
            <button
              className={`tab ${activeTab === 'errors' ? 'active' : ''}`}
              onClick={() => setActiveTab('errors')}
            >
              Errors {result.errors && `(${result.errors.length})`}
            </button>
          </div>

          {/* Tab Content */}
          <div className="tab-content">
            {activeTab === 'stats' && (
              <div className="stats-grid">
                <StatCard
                  label="Imported To"
                  value={destination === 'leads' ? 'Leads' : destination === 'mum_clients' ? 'Closed Loans (MUM)' : 'Loans'}
                  variant="default"
                />
                <StatCard
                  label="Total Records"
                  value={result.stats?.total_rows || 0}
                  variant="default"
                />
                <StatCard
                  label="Successfully Imported"
                  value={result.stats?.imported || result.stats?.successful_rows || 0}
                  variant="success"
                />
                <StatCard
                  label="Failed Records"
                  value={result.stats?.failed_rows || result.stats?.failed_import || 0}
                  variant={result.stats?.failed_rows > 0 ? 'error' : 'default'}
                />
                <StatCard
                  label="Fields Matched"
                  value={result.stats?.fields_matched || 0}
                  variant="default"
                />
                <StatCard
                  label="Mapping Confidence"
                  value={result.stats?.mappingConfidence || `${result.stats?.confidence_average || 0}%`}
                  variant={(result.stats?.confidence_average || 0) >= 90 ? 'success' : 'warning'}
                />
              </div>
            )}

            {activeTab === 'mappings' && (
              <div className="mappings-table">
                <table>
                  <thead>
                    <tr>
                      <th>Excel Column</th>
                      <th>CRM Field</th>
                      <th>Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.mappings && result.mappings.map((mapping, index) => (
                      <tr key={index}>
                        <td className="column-name">{mapping.excel_column}</td>
                        <td>
                          <code className="field-code">{mapping.crm_field}</code>
                        </td>
                        <td>
                          <span className={`badge ${getConfidenceBadgeClass(mapping.confidence)}`}>
                            {mapping.confidence}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {activeTab === 'warnings' && (
              <div className="alerts-list">
                {result.warnings && result.warnings.length > 0 ? (
                  result.warnings.map((warning, index) => (
                    <div key={index} className="alert warning">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                        <line x1="12" y1="9" x2="12" y2="13" />
                        <line x1="12" y1="17" x2="12.01" y2="17" />
                      </svg>
                      <span>{warning}</span>
                    </div>
                  ))
                ) : (
                  <p className="no-items">No warnings</p>
                )}
              </div>
            )}

            {activeTab === 'errors' && (
              <div className="alerts-list">
                {result.errors && result.errors.length > 0 ? (
                  result.errors.map((error, index) => (
                    <div key={index} className="alert error">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="15" y1="9" x2="9" y2="15" />
                        <line x1="9" y1="9" x2="15" y2="15" />
                      </svg>
                      <span>{error}</span>
                    </div>
                  ))
                ) : (
                  <p className="no-items">No errors</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, variant = 'default' }) {
  return (
    <div className={`stat-card ${variant}`}>
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
    </div>
  );
}

function getConfidenceBadgeClass(confidence) {
  const numValue = parseInt(confidence);
  if (numValue >= 90) return 'high';
  if (numValue >= 80) return 'medium';
  return 'low';
}

export default AutoDataImport;
