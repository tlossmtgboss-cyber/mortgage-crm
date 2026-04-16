import React, { useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { usePermissions } from '../contexts/PermissionContext';
import { getAuthHeaders } from '../utils/auth';
import './UserBulkUpload.css';
import { getToken } from '../utils/tokenStore';

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE_URL = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// Upload stages
const STAGES = {
  UPLOAD: 'upload',
  MAPPING: 'mapping',
  VALIDATION: 'validation',
  ROLE_ASSIGNMENT: 'role_assignment',
  PROCESSING: 'processing',
  RESULTS: 'results'
};

// Required and optional fields
const REQUIRED_FIELDS = ['first_name', 'last_name', 'email'];
const OPTIONAL_FIELDS = ['phone', 'department', 'job_title', 'role'];

const FIELD_LABELS = {
  first_name: 'First Name',
  last_name: 'Last Name',
  email: 'Email Address',
  phone: 'Phone Number',
  department: 'Department',
  job_title: 'Job Title',
  role: 'Role'
};

function UserBulkUpload() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - only admins can bulk upload users
  const canBulkUpload = isAdmin || hasAnyPermission(['admin.manage', 'users.manage', 'users.create', 'system.admin']) ||
    userRole === 'admin' || userRole === 'site_admin';

  const [stage, setStage] = useState(STAGES.UPLOAD);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  // File and data state
  const [file, setFile] = useState(null);
  const [fileHeaders, setFileHeaders] = useState([]);
  const [previewData, setPreviewData] = useState([]);
  const [totalRows, setTotalRows] = useState(0);

  // Mapping state
  const [columnMapping, setColumnMapping] = useState({});

  // Validation state
  const [validationResults, setValidationResults] = useState(null);

  // Processing state
  const [processingProgress, setProcessingProgress] = useState(0);
  const [processedUsers, setProcessedUsers] = useState([]);

  // Role assignment state
  const [defaultRoleId, setDefaultRoleId] = useState(null);
  const [roles, setRoles] = useState([]);

  const handleFileSelect = async (e) => {
    const selectedFile = e.target.files[0];
    if (!selectedFile) return;

    // Validate file type
    const validTypes = [
      'text/csv',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ];
    const ext = selectedFile.name.split('.').pop().toLowerCase();
    if (!validTypes.includes(selectedFile.type) && !['csv', 'xlsx', 'xls'].includes(ext)) {
      setError('Please upload a CSV or Excel file (.csv, .xlsx, .xls)');
      return;
    }

    setFile(selectedFile);
    setError(null);
    setLoading(true);

    try {
      // Upload file for parsing
      const formData = new FormData();
      formData.append('file', selectedFile);

      const response = await axios.post(
        `${API_BASE_URL}/api/v1/admin/users/bulk/parse`,
        formData,
        {
          headers: {
            'Authorization': `Bearer ${getToken()}`,
            'Content-Type': 'multipart/form-data'
          }
        }
      );

      const { headers, preview, total_rows } = response.data;
      setFileHeaders(headers);
      setPreviewData(preview);
      setTotalRows(total_rows);

      // Auto-detect column mappings
      const autoMapping = {};
      headers.forEach(header => {
        const normalized = header.toLowerCase().replace(/[^a-z]/g, '_');
        const allFields = [...REQUIRED_FIELDS, ...OPTIONAL_FIELDS];
        const match = allFields.find(f => {
          const fieldNorm = f.toLowerCase().replace(/_/g, '');
          const headerNorm = normalized.replace(/_/g, '');
          return fieldNorm === headerNorm ||
                 header.toLowerCase().includes(f.replace('_', ' ')) ||
                 header.toLowerCase().includes(f.replace('_', ''));
        });
        if (match) {
          autoMapping[match] = header;
        }
      });
      setColumnMapping(autoMapping);

      // Load roles for assignment
      const rolesRes = await axios.get(
        `${API_BASE_URL}/api/v1/admin/users/roles`,
        { headers: getAuthHeaders() }
      );
      setRoles(rolesRes.data || []);

      setStage(STAGES.MAPPING);
    } catch (err) {
      console.error('Error parsing file:', err);
      setError(err.response?.data?.detail || 'Failed to parse file. Please check the format and try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleMappingChange = (field, header) => {
    setColumnMapping(prev => ({
      ...prev,
      [field]: header || undefined
    }));
  };

  const validateMapping = () => {
    // Check all required fields are mapped
    const missingRequired = REQUIRED_FIELDS.filter(f => !columnMapping[f]);
    if (missingRequired.length > 0) {
      setError(`Please map required fields: ${missingRequired.map(f => FIELD_LABELS[f]).join(', ')}`);
      return false;
    }
    return true;
  };

  const handleValidate = async () => {
    if (!validateMapping()) return;

    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('column_mapping', JSON.stringify(columnMapping));

      const response = await axios.post(
        `${API_BASE_URL}/api/v1/admin/users/bulk/validate`,
        formData,
        {
          headers: {
            'Authorization': `Bearer ${getToken()}`,
            'Content-Type': 'multipart/form-data'
          }
        }
      );

      setValidationResults(response.data);
      setStage(STAGES.VALIDATION);
    } catch (err) {
      console.error('Error validating:', err);
      setError(err.response?.data?.detail || 'Validation failed. Please check your data.');
    } finally {
      setLoading(false);
    }
  };

  const handleProcess = async () => {
    setLoading(true);
    setError(null);
    setStage(STAGES.PROCESSING);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('column_mapping', JSON.stringify(columnMapping));
      if (defaultRoleId) {
        formData.append('default_role_id', defaultRoleId);
      }

      const response = await axios.post(
        `${API_BASE_URL}/api/v1/admin/users/bulk/process`,
        formData,
        {
          headers: {
            'Authorization': `Bearer ${getToken()}`,
            'Content-Type': 'multipart/form-data'
          },
          onUploadProgress: (progressEvent) => {
            const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setProcessingProgress(Math.min(progress, 50)); // Upload is 50%
          }
        }
      );

      setProcessedUsers(response.data.results || []);
      setProcessingProgress(100);
      setStage(STAGES.RESULTS);
    } catch (err) {
      console.error('Error processing:', err);
      setError(err.response?.data?.detail || 'Processing failed. Please try again.');
      setStage(STAGES.VALIDATION);
    } finally {
      setLoading(false);
    }
  };

  const resetUpload = () => {
    setStage(STAGES.UPLOAD);
    setFile(null);
    setFileHeaders([]);
    setPreviewData([]);
    setTotalRows(0);
    setColumnMapping({});
    setValidationResults(null);
    setProcessingProgress(0);
    setProcessedUsers([]);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const renderUploadStage = () => (
    <div className="upload-stage">
      <div className="upload-header">
        <h2>Bulk User Upload</h2>
        <p>Upload a CSV or Excel file to create multiple users at once.</p>
      </div>

      <div
        className={`upload-dropzone ${loading ? 'loading' : ''}`}
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const droppedFile = e.dataTransfer.files[0];
          if (droppedFile) {
            handleFileSelect({ target: { files: [droppedFile] } });
          }
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />
        <div className="dropzone-content">
          <div className="dropzone-icon">📄</div>
          <h3>Drop your file here</h3>
          <p>or click to browse</p>
          <span className="file-types">Supported: CSV, XLSX, XLS</span>
        </div>
      </div>

      <div className="upload-template">
        <h3>Template Format</h3>
        <p>Your file should include these columns:</p>
        <div className="template-columns">
          <div className="column-group required">
            <h4>Required</h4>
            <ul>
              <li>First Name</li>
              <li>Last Name</li>
              <li>Email</li>
            </ul>
          </div>
          <div className="column-group optional">
            <h4>Optional</h4>
            <ul>
              <li>Phone</li>
              <li>Department</li>
              <li>Job Title</li>
              <li>Role</li>
            </ul>
          </div>
        </div>
        <button
          className="btn-download-template"
          onClick={() => {
            const csv = 'First Name,Last Name,Email,Phone,Department,Job Title,Role\nJohn,Doe,john@example.com,555-0100,Operations,Loan Officer,loan_officer\n';
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'user_upload_template.csv';
            a.click();
          }}
        >
          Download Template
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}
    </div>
  );

  const renderMappingStage = () => (
    <div className="mapping-stage">
      <div className="stage-header">
        <h2>Column Mapping</h2>
        <p>Map your file columns to the user fields. We've auto-detected some mappings for you.</p>
      </div>

      <div className="file-info">
        <span className="file-name">📄 {file?.name}</span>
        <span className="row-count">{totalRows} rows detected</span>
      </div>

      <div className="mapping-grid">
        <div className="mapping-section">
          <h3>Required Fields</h3>
          {REQUIRED_FIELDS.map(field => (
            <div key={field} className="mapping-row">
              <label className="field-label required">{FIELD_LABELS[field]}</label>
              <select
                value={columnMapping[field] || ''}
                onChange={(e) => handleMappingChange(field, e.target.value)}
              >
                <option value="">Select column...</option>
                {fileHeaders.map(header => (
                  <option key={header} value={header}>{header}</option>
                ))}
              </select>
              {columnMapping[field] && <span className="mapping-check">✓</span>}
            </div>
          ))}
        </div>

        <div className="mapping-section">
          <h3>Optional Fields</h3>
          {OPTIONAL_FIELDS.map(field => (
            <div key={field} className="mapping-row">
              <label className="field-label">{FIELD_LABELS[field]}</label>
              <select
                value={columnMapping[field] || ''}
                onChange={(e) => handleMappingChange(field, e.target.value)}
              >
                <option value="">Select column...</option>
                {fileHeaders.map(header => (
                  <option key={header} value={header}>{header}</option>
                ))}
              </select>
              {columnMapping[field] && <span className="mapping-check">✓</span>}
            </div>
          ))}
        </div>
      </div>

      {/* Preview */}
      <div className="data-preview">
        <h3>Data Preview (First 5 Rows)</h3>
        <div className="preview-table-container">
          <table className="preview-table">
            <thead>
              <tr>
                {fileHeaders.map(header => (
                  <th key={header}>{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {previewData.map((row, idx) => (
                <tr key={idx}>
                  {fileHeaders.map(header => (
                    <td key={header}>{row[header]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="stage-actions">
        <button className="btn-secondary" onClick={resetUpload}>Cancel</button>
        <button className="btn-primary" onClick={handleValidate} disabled={loading}>
          {loading ? 'Validating...' : 'Validate Data'}
        </button>
      </div>
    </div>
  );

  const renderValidationStage = () => {
    const { valid_count = 0, invalid_count = 0, errors = [], warnings = [] } = validationResults || {};

    return (
      <div className="validation-stage">
        <div className="stage-header">
          <h2>Validation Results</h2>
          <p>Review the validation results before processing.</p>
        </div>

        <div className="validation-summary">
          <div className="summary-card valid">
            <span className="summary-number">{valid_count}</span>
            <span className="summary-label">Valid Records</span>
          </div>
          <div className="summary-card invalid">
            <span className="summary-number">{invalid_count}</span>
            <span className="summary-label">Invalid Records</span>
          </div>
          <div className="summary-card warnings">
            <span className="summary-number">{warnings.length}</span>
            <span className="summary-label">Warnings</span>
          </div>
        </div>

        {errors.length > 0 && (
          <div className="validation-errors">
            <h3>Errors</h3>
            <div className="error-list">
              {errors.slice(0, 10).map((err, idx) => (
                <div key={idx} className="error-item">
                  <span className="error-row">Row {err.row}:</span>
                  <span className="error-message">{err.message}</span>
                </div>
              ))}
              {errors.length > 10 && (
                <div className="error-more">...and {errors.length - 10} more errors</div>
              )}
            </div>
          </div>
        )}

        {warnings.length > 0 && (
          <div className="validation-warnings">
            <h3>Warnings</h3>
            <div className="warning-list">
              {warnings.slice(0, 5).map((warn, idx) => (
                <div key={idx} className="warning-item">
                  <span className="warning-row">Row {warn.row}:</span>
                  <span className="warning-message">{warn.message}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Default Role Assignment */}
        <div className="role-assignment">
          <h3>Default Role Assignment</h3>
          <p>Select a default role for users without a role specified in the file:</p>
          <select
            value={defaultRoleId || ''}
            onChange={(e) => setDefaultRoleId(e.target.value || null)}
          >
            <option value="">No default role</option>
            {roles.map(role => (
              <option key={role.id} value={role.id}>{role.display_name}</option>
            ))}
          </select>
        </div>

        {error && <div className="error-message">{error}</div>}

        <div className="stage-actions">
          <button className="btn-secondary" onClick={() => setStage(STAGES.MAPPING)}>
            Back to Mapping
          </button>
          <button
            className="btn-primary"
            onClick={handleProcess}
            disabled={loading || valid_count === 0}
          >
            Create {valid_count} Users
          </button>
        </div>
      </div>
    );
  };

  const renderProcessingStage = () => (
    <div className="processing-stage">
      <div className="processing-content">
        <div className="spinner large"></div>
        <h2>Processing Users</h2>
        <p>Creating user accounts and generating scorecards...</p>
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${processingProgress}%` }}></div>
        </div>
        <span className="progress-text">{processingProgress}% complete</span>
      </div>
    </div>
  );

  const renderResultsStage = () => {
    const successful = processedUsers.filter(u => u.success);
    const failed = processedUsers.filter(u => !u.success);

    return (
      <div className="results-stage">
        <div className="results-header">
          <div className="success-icon large">✓</div>
          <h2>Upload Complete</h2>
          <p>{successful.length} users created successfully</p>
        </div>

        <div className="results-summary">
          <div className="summary-card success">
            <span className="summary-number">{successful.length}</span>
            <span className="summary-label">Created</span>
          </div>
          <div className="summary-card failed">
            <span className="summary-number">{failed.length}</span>
            <span className="summary-label">Failed</span>
          </div>
        </div>

        {successful.length > 0 && (
          <div className="results-list">
            <h3>Successfully Created Users</h3>
            <div className="user-list">
              {successful.slice(0, 10).map((user, idx) => (
                <div key={idx} className="user-item success">
                  <span className="user-name">{user.name}</span>
                  <span className="user-email">{user.email}</span>
                  <span className="user-status">Activation email sent</span>
                </div>
              ))}
              {successful.length > 10 && (
                <div className="list-more">...and {successful.length - 10} more</div>
              )}
            </div>
          </div>
        )}

        {failed.length > 0 && (
          <div className="results-list failed">
            <h3>Failed Records</h3>
            <div className="user-list">
              {failed.map((user, idx) => (
                <div key={idx} className="user-item failed">
                  <span className="user-name">{user.name || 'Unknown'}</span>
                  <span className="user-email">{user.email || 'N/A'}</span>
                  <span className="user-error">{user.error}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="stage-actions centered">
          <button className="btn-secondary" onClick={() => window.location.href = '/users'}>
            Back to Users
          </button>
          <button className="btn-primary" onClick={resetUpload}>
            Upload Another File
          </button>
        </div>
      </div>
    );
  };

  const renderCurrentStage = () => {
    switch (stage) {
      case STAGES.UPLOAD:
        return renderUploadStage();
      case STAGES.MAPPING:
        return renderMappingStage();
      case STAGES.VALIDATION:
        return renderValidationStage();
      case STAGES.PROCESSING:
        return renderProcessingStage();
      case STAGES.RESULTS:
        return renderResultsStage();
      default:
        return renderUploadStage();
    }
  };

  // Access denied if user doesn't have bulk upload permissions
  if (!canBulkUpload) {
    return (
      <div className="user-bulk-upload">
        <div style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to bulk upload users.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')} style={{ marginTop: '16px' }}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="user-bulk-upload">
      <div className="bulk-upload-header">
        <h1>Bulk User Upload</h1>
        <p>Create multiple users from a CSV or Excel file</p>
      </div>

      <div className="bulk-upload-body">
        {renderCurrentStage()}
      </div>
    </div>
  );
}

export default UserBulkUpload;
