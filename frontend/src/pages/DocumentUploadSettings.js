import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import { useAsyncOperation, useFormSubmit, APIError } from '../utils/errorHandling';
import './DocumentUploadSettings.css';
import { getToken } from '../utils/tokenStore';

function DocumentUploadSettings() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('upload');
  const [settings, setSettings] = useState(null);
  const [originalSettings, setOriginalSettings] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [availableFileTypes, setAvailableFileTypes] = useState([]);
  const [categories, setCategories] = useState([]);
  const [storageProviders, setStorageProviders] = useState([]);
  const [statistics, setStatistics] = useState(null);
  const [testingClassification, setTestingClassification] = useState(false);
  const [classificationResults, setClassificationResults] = useState(null);

  // Async operation hooks - we use our own showToast for this page
  const { loading, error, execute: fetchSettings } = useAsyncOperation({ showErrorToast: false });
  const { submitting, execute: saveSettings } = useFormSubmit({ showErrorToast: false, showSuccessToast: false });

  // Toast notification state
  const [toast, setToast] = useState({ show: false, type: '', message: '' });

  const showToast = (type, message) => {
    setToast({ show: true, type, message });
    setTimeout(() => setToast({ show: false, type: '', message: '' }), 5000);
  };

  // Load settings and reference data
  const loadData = useCallback(async () => {
    try {
      const token = getToken();
      const headers = { 'Authorization': `Bearer ${token}` };

      const [settingsRes, typesRes, categoriesRes, providersRes, statsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/document-upload-settings`, { headers }),
        fetch(`${API_BASE_URL}/api/v1/document-upload-settings/file-types`, { headers }),
        fetch(`${API_BASE_URL}/api/v1/document-upload-settings/document-categories`, { headers }),
        fetch(`${API_BASE_URL}/api/v1/document-upload-settings/storage-providers`, { headers }),
        fetch(`${API_BASE_URL}/api/v1/document-upload-settings/statistics`, { headers })
      ]);

      if (!settingsRes.ok) {
        const err = await settingsRes.json();
        throw new APIError(err.detail?.message || 'Failed to load settings', settingsRes.status, err.detail);
      }

      const settingsData = await settingsRes.json();
      setSettings(settingsData.data);
      setOriginalSettings(JSON.parse(JSON.stringify(settingsData.data)));

      if (typesRes.ok) {
        const typesData = await typesRes.json();
        setAvailableFileTypes(typesData.data?.file_types || []);
      }

      if (categoriesRes.ok) {
        const categoriesData = await categoriesRes.json();
        setCategories(categoriesData.data?.categories || []);
      }

      if (providersRes.ok) {
        const providersData = await providersRes.json();
        setStorageProviders(providersData.data?.providers || []);
      }

      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStatistics(statsData.data);
      }

    } catch (err) {
      console.error('Error loading document upload settings:', err);
      showToast('error', 'Failed to load document upload settings');
      throw err;
    }
  }, []);

  useEffect(() => {
    fetchSettings(loadData);
  }, [fetchSettings, loadData]);

  // Check for changes
  useEffect(() => {
    if (settings && originalSettings) {
      setHasChanges(JSON.stringify(settings) !== JSON.stringify(originalSettings));
    }
  }, [settings, originalSettings]);

  // Field update handler
  const updateField = (path, value) => {
    setSettings(prev => {
      const newSettings = { ...prev };
      const parts = path.split('.');
      let current = newSettings;

      for (let i = 0; i < parts.length - 1; i++) {
        if (!current[parts[i]]) {
          current[parts[i]] = {};
        }
        current = current[parts[i]];
      }

      current[parts[parts.length - 1]] = value;
      return newSettings;
    });

    // Clear field error
    if (fieldErrors[path]) {
      setFieldErrors(prev => {
        const updated = { ...prev };
        delete updated[path];
        return updated;
      });
    }
  };

  // Toggle file type
  const toggleFileType = (extension) => {
    setSettings(prev => {
      const newTypes = [...(prev.allowed_file_types || [])];
      const index = newTypes.findIndex(t => t.extension === extension);

      if (index >= 0) {
        newTypes[index] = { ...newTypes[index], enabled: !newTypes[index].enabled };
      }

      return { ...prev, allowed_file_types: newTypes };
    });
  };

  // Toggle document type
  const toggleDocumentType = (typeName) => {
    setSettings(prev => {
      const newTypes = [...(prev.document_types || [])];
      const index = newTypes.findIndex(t => t.type_name === typeName);

      if (index >= 0) {
        newTypes[index] = { ...newTypes[index], enabled: !newTypes[index].enabled };
      }

      return { ...prev, document_types: newTypes };
    });
  };

  // Validate form
  const validateForm = () => {
    const errors = {};

    // Validate upload limits
    if (settings.max_file_size_mb < 1 || settings.max_file_size_mb > 100) {
      errors['max_file_size_mb'] = 'File size must be between 1 and 100 MB';
    }

    if (settings.max_files_per_upload < 1 || settings.max_files_per_upload > 50) {
      errors['max_files_per_upload'] = 'Files per upload must be between 1 and 50';
    }

    // Validate at least one file type enabled
    const enabledTypes = (settings.allowed_file_types || []).filter(t => t.enabled);
    if (enabledTypes.length === 0) {
      errors['allowed_file_types'] = 'At least one file type must be enabled';
    }

    // Validate classification thresholds
    if (settings.classification?.enabled) {
      if (settings.classification.confidence_threshold > settings.classification.high_confidence_threshold) {
        errors['classification.high_confidence_threshold'] = 'Must be greater than or equal to base threshold';
      }
    }

    // Validate storage
    if (settings.storage?.provider && settings.storage.provider !== 'local') {
      if (!settings.storage.bucket_name) {
        errors['storage.bucket_name'] = 'Bucket name required for cloud storage';
      }
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  // Save settings
  const handleSave = async () => {
    if (!validateForm()) {
      showToast('error', 'Please fix the validation errors');
      return;
    }

    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/document-upload-settings`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(settings)
      });

      if (!response.ok) {
        const err = await response.json();
        if (err.detail?.field) {
          setFieldErrors({ [err.detail.field]: err.detail.message });
        }
        throw new APIError(err.detail?.message || 'Failed to save settings', response.status, err.detail);
      }

      const data = await response.json();
      setSettings(data.data);
      setOriginalSettings(JSON.parse(JSON.stringify(data.data)));
      setHasChanges(false);
      showToast('success', 'Document upload settings saved successfully');

    } catch (err) {
      console.error('Error saving settings:', err);
      showToast('error', err.message || 'Failed to save settings');
    }
  };

  // Discard changes
  const handleDiscard = () => {
    setSettings(JSON.parse(JSON.stringify(originalSettings)));
    setFieldErrors({});
    setHasChanges(false);
  };

  // Reset to defaults
  const handleResetDefaults = async () => {
    if (!window.confirm('Reset all document settings to defaults? This cannot be undone.')) {
      return;
    }

    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/document-upload-settings/reset-defaults`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        throw new Error('Failed to reset settings');
      }

      const data = await response.json();
      setSettings(data.data);
      setOriginalSettings(JSON.parse(JSON.stringify(data.data)));
      setHasChanges(false);
      showToast('success', 'Settings reset to defaults');

    } catch (err) {
      console.error('Error resetting settings:', err);
      showToast('error', 'Failed to reset settings');
    }
  };

  // Test classification
  const handleTestClassification = async () => {
    setTestingClassification(true);
    setClassificationResults(null);

    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/document-upload-settings/test-classification`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setClassificationResults(data.data);
      }
    } catch (err) {
      console.error('Error testing classification:', err);
    } finally {
      setTestingClassification(false);
    }
  };

  // Format file size
  const formatSize = (mb) => {
    if (mb >= 1000) return `${(mb / 1000).toFixed(1)} GB`;
    return `${mb} MB`;
  };

  // Loading state
  if (loading) {
    return (
      <div className="document-upload-settings-page">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading document upload settings...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="document-upload-settings-page">
        <div className="error-state">
          <i className="fas fa-exclamation-triangle"></i>
          <h2>Unable to Load Settings</h2>
          <p>{error.message || 'An unexpected error occurred'}</p>
          <button className="btn-primary" onClick={() => fetchSettings(loadData)}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  if (!settings) return null;

  return (
    <div className="document-upload-settings-page">
      {/* Toast Notification */}
      {toast.show && (
        <div className={`toast-notification ${toast.type}`}>
          <i className={`fas ${toast.type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}`}></i>
          <span>{toast.message}</span>
          <button onClick={() => setToast({ show: false, type: '', message: '' })}>
            <i className="fas fa-times"></i>
          </button>
        </div>
      )}

      {/* Header */}
      <div className="settings-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/settings')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div>
            <h1>Document Upload Settings</h1>
            <p className="subtitle">Configure file upload limits, classification, and storage</p>
          </div>
        </div>
        <button className="btn-secondary" onClick={handleResetDefaults}>
          <i className="fas fa-undo"></i> Reset Defaults
        </button>
      </div>

      {/* Statistics Banner */}
      {statistics && (
        <div className="stats-banner">
          <div className="stat-item">
            <span className="stat-value">{statistics.total_documents?.toLocaleString()}</span>
            <span className="stat-label">Total Documents</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{statistics.total_size_gb?.toFixed(1)} GB</span>
            <span className="stat-label">Storage Used</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{statistics.documents_this_month}</span>
            <span className="stat-label">This Month</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{Math.round((statistics.classification_stats?.avg_confidence || 0) * 100)}%</span>
            <span className="stat-label">Avg Confidence</span>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="settings-tabs">
        <button
          className={`tab-btn ${activeTab === 'upload' ? 'active' : ''}`}
          onClick={() => setActiveTab('upload')}
        >
          <i className="fas fa-upload"></i> Upload Limits
        </button>
        <button
          className={`tab-btn ${activeTab === 'types' ? 'active' : ''}`}
          onClick={() => setActiveTab('types')}
        >
          <i className="fas fa-file-alt"></i> File Types
        </button>
        <button
          className={`tab-btn ${activeTab === 'classification' ? 'active' : ''}`}
          onClick={() => setActiveTab('classification')}
        >
          <i className="fas fa-robot"></i> AI Classification
        </button>
        <button
          className={`tab-btn ${activeTab === 'storage' ? 'active' : ''}`}
          onClick={() => setActiveTab('storage')}
        >
          <i className="fas fa-database"></i> Storage
        </button>
        <button
          className={`tab-btn ${activeTab === 'notifications' ? 'active' : ''}`}
          onClick={() => setActiveTab('notifications')}
        >
          <i className="fas fa-bell"></i> Notifications
        </button>
      </div>

      {/* Upload Limits Tab */}
      {activeTab === 'upload' && (
        <div className="settings-section">
          <h2>Upload Limits</h2>
          <p className="section-description">Configure maximum file size and upload limits</p>

          <div className="form-row two-col">
            <div className="form-group">
              <label>Maximum File Size (MB)</label>
              <input
                type="number"
                min="1"
                max="100"
                value={settings.max_file_size_mb}
                onChange={(e) => updateField('max_file_size_mb', parseFloat(e.target.value))}
                className={fieldErrors['max_file_size_mb'] ? 'has-error' : ''}
              />
              {fieldErrors['max_file_size_mb'] && (
                <span className="field-error">{fieldErrors['max_file_size_mb']}</span>
              )}
              <span className="field-hint">Maximum size for a single file (1-100 MB)</span>
            </div>

            <div className="form-group">
              <label>Maximum Files Per Upload</label>
              <input
                type="number"
                min="1"
                max="50"
                value={settings.max_files_per_upload}
                onChange={(e) => updateField('max_files_per_upload', parseInt(e.target.value))}
                className={fieldErrors['max_files_per_upload'] ? 'has-error' : ''}
              />
              {fieldErrors['max_files_per_upload'] && (
                <span className="field-error">{fieldErrors['max_files_per_upload']}</span>
              )}
              <span className="field-hint">Maximum files in a single upload batch</span>
            </div>
          </div>

          <div className="divider"></div>

          <h3>Processing Options</h3>

          <div className="toggle-options">
            <label className="toggle-option">
              <input
                type="checkbox"
                checked={settings.enable_ocr}
                onChange={(e) => updateField('enable_ocr', e.target.checked)}
              />
              <div className="toggle-content">
                <span className="toggle-label">Enable OCR</span>
                <span className="toggle-hint">Extract text from images and scanned PDFs</span>
              </div>
            </label>

            <label className="toggle-option">
              <input
                type="checkbox"
                checked={settings.enable_virus_scan}
                onChange={(e) => updateField('enable_virus_scan', e.target.checked)}
              />
              <div className="toggle-content">
                <span className="toggle-label">Enable Virus Scanning</span>
                <span className="toggle-hint">Scan uploaded files for malware</span>
              </div>
            </label>

            <label className="toggle-option">
              <input
                type="checkbox"
                checked={settings.compress_images}
                onChange={(e) => updateField('compress_images', e.target.checked)}
              />
              <div className="toggle-content">
                <span className="toggle-label">Compress Images</span>
                <span className="toggle-hint">Automatically compress large images</span>
              </div>
            </label>
          </div>

          {settings.compress_images && (
            <div className="form-group" style={{ maxWidth: '300px', marginTop: '16px' }}>
              <label>Max Image Dimension (px)</label>
              <input
                type="number"
                min="500"
                max="5000"
                value={settings.image_max_dimension}
                onChange={(e) => updateField('image_max_dimension', parseInt(e.target.value))}
              />
              <span className="field-hint">Images larger than this will be resized</span>
            </div>
          )}
        </div>
      )}

      {/* File Types Tab */}
      {activeTab === 'types' && (
        <div className="settings-section">
          <h2>Allowed File Types</h2>
          <p className="section-description">Select which file types borrowers can upload</p>

          {fieldErrors['allowed_file_types'] && (
            <div className="field-error-banner">{fieldErrors['allowed_file_types']}</div>
          )}

          <div className="file-types-grid">
            {/* Documents */}
            <div className="file-type-category">
              <h4>Documents</h4>
              <div className="file-type-list">
                {(settings.allowed_file_types || [])
                  .filter(t => ['.pdf', '.doc', '.docx', '.txt'].includes(t.extension))
                  .map(type => (
                    <label key={type.extension} className="file-type-item">
                      <input
                        type="checkbox"
                        checked={type.enabled}
                        onChange={() => toggleFileType(type.extension)}
                      />
                      <span className="file-ext">{type.extension}</span>
                      <span className="file-mime">{type.mime_type.split('/')[1]}</span>
                    </label>
                  ))
                }
              </div>
            </div>

            {/* Images */}
            <div className="file-type-category">
              <h4>Images</h4>
              <div className="file-type-list">
                {(settings.allowed_file_types || [])
                  .filter(t => ['.jpg', '.jpeg', '.png', '.gif', '.tiff', '.heic'].includes(t.extension))
                  .map(type => (
                    <label key={type.extension} className="file-type-item">
                      <input
                        type="checkbox"
                        checked={type.enabled}
                        onChange={() => toggleFileType(type.extension)}
                      />
                      <span className="file-ext">{type.extension}</span>
                      <span className="file-mime">{type.mime_type.split('/')[1]}</span>
                    </label>
                  ))
                }
              </div>
            </div>

            {/* Spreadsheets */}
            <div className="file-type-category">
              <h4>Spreadsheets</h4>
              <div className="file-type-list">
                {(settings.allowed_file_types || [])
                  .filter(t => ['.xls', '.xlsx', '.csv'].includes(t.extension))
                  .map(type => (
                    <label key={type.extension} className="file-type-item">
                      <input
                        type="checkbox"
                        checked={type.enabled}
                        onChange={() => toggleFileType(type.extension)}
                      />
                      <span className="file-ext">{type.extension}</span>
                      <span className="file-mime">{type.mime_type.split('/')[1]}</span>
                    </label>
                  ))
                }
              </div>
            </div>
          </div>

          <div className="divider"></div>

          <h2>Document Types</h2>
          <p className="section-description">Configure mortgage document types for classification</p>

          <div className="document-types-grid">
            {categories.map(category => (
              <div key={category.name} className="doc-type-category">
                <h4 style={{ borderLeftColor: category.color }}>
                  {category.display_name}
                </h4>
                <div className="doc-type-list">
                  {(settings.document_types || [])
                    .filter(t => t.category === category.name)
                    .map(type => (
                      <label key={type.type_name} className="doc-type-item">
                        <input
                          type="checkbox"
                          checked={type.enabled}
                          onChange={() => toggleDocumentType(type.type_name)}
                        />
                        <span className="doc-type-name">{type.display_name}</span>
                        {type.requires_period && (
                          <span className="doc-type-badge">Period Required</span>
                        )}
                      </label>
                    ))
                  }
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AI Classification Tab */}
      {activeTab === 'classification' && (
        <div className="settings-section">
          <h2>AI Classification</h2>
          <p className="section-description">Configure automatic document classification with AI</p>

          <label className="toggle-option featured">
            <input
              type="checkbox"
              checked={settings.classification?.enabled}
              onChange={(e) => updateField('classification.enabled', e.target.checked)}
            />
            <div className="toggle-content">
              <span className="toggle-label">Enable AI Classification</span>
              <span className="toggle-hint">Automatically classify uploaded documents using AI</span>
            </div>
          </label>

          {settings.classification?.enabled && (
            <>
              <div className="form-row two-col" style={{ marginTop: '24px' }}>
                <div className="form-group">
                  <label>Confidence Threshold</label>
                  <div className="slider-input">
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={(settings.classification?.confidence_threshold || 0.7) * 100}
                      onChange={(e) => updateField('classification.confidence_threshold', parseInt(e.target.value) / 100)}
                    />
                    <span className="slider-value">{Math.round((settings.classification?.confidence_threshold || 0.7) * 100)}%</span>
                  </div>
                  <span className="field-hint">Minimum confidence for classification suggestions</span>
                </div>

                <div className="form-group">
                  <label>High Confidence Threshold</label>
                  <div className="slider-input">
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={(settings.classification?.high_confidence_threshold || 0.9) * 100}
                      onChange={(e) => updateField('classification.high_confidence_threshold', parseInt(e.target.value) / 100)}
                      className={fieldErrors['classification.high_confidence_threshold'] ? 'has-error' : ''}
                    />
                    <span className="slider-value">{Math.round((settings.classification?.high_confidence_threshold || 0.9) * 100)}%</span>
                  </div>
                  {fieldErrors['classification.high_confidence_threshold'] && (
                    <span className="field-error">{fieldErrors['classification.high_confidence_threshold']}</span>
                  )}
                  <span className="field-hint">Threshold for auto-applying classifications</span>
                </div>
              </div>

              <div className="toggle-options">
                <label className="toggle-option">
                  <input
                    type="checkbox"
                    checked={settings.classification?.auto_apply_high_confidence}
                    onChange={(e) => updateField('classification.auto_apply_high_confidence', e.target.checked)}
                  />
                  <div className="toggle-content">
                    <span className="toggle-label">Auto-apply High Confidence</span>
                    <span className="toggle-hint">Automatically apply classifications above high confidence threshold</span>
                  </div>
                </label>

                <label className="toggle-option">
                  <input
                    type="checkbox"
                    checked={settings.classification?.create_task_on_low_confidence}
                    onChange={(e) => updateField('classification.create_task_on_low_confidence', e.target.checked)}
                  />
                  <div className="toggle-content">
                    <span className="toggle-label">Create Task for Low Confidence</span>
                    <span className="toggle-hint">Create a review task when confidence is below threshold</span>
                  </div>
                </label>
              </div>

              <div className="form-group" style={{ maxWidth: '300px', marginTop: '16px' }}>
                <label>Fallback Document Type</label>
                <select
                  value={settings.classification?.fallback_type || 'OTHER'}
                  onChange={(e) => updateField('classification.fallback_type', e.target.value)}
                >
                  {(settings.document_types || []).filter(t => t.enabled).map(type => (
                    <option key={type.type_name} value={type.type_name}>{type.display_name}</option>
                  ))}
                </select>
                <span className="field-hint">Default type when classification fails</span>
              </div>

              <div className="divider"></div>

              <h3>Test Classification</h3>
              <p className="section-description">Run a test to verify AI classification is working</p>

              <button
                className="btn-secondary"
                onClick={handleTestClassification}
                disabled={testingClassification}
              >
                {testingClassification ? (
                  <>
                    <span className="spinner-sm"></span> Testing...
                  </>
                ) : (
                  <>
                    <i className="fas fa-flask"></i> Run Test Classification
                  </>
                )}
              </button>

              {classificationResults && (
                <div className="test-results">
                  <h4>Test Results</h4>
                  <div className="test-results-list">
                    {classificationResults.test_results?.map((result, i) => (
                      <div key={i} className={`test-result-item ${result.status}`}>
                        <span className="result-filename">{result.filename}</span>
                        <span className="result-type">{result.detected_type}</span>
                        <span className="result-confidence">{Math.round(result.confidence * 100)}%</span>
                        <span className={`result-status ${result.status}`}>
                          {result.status === 'success' ? 'Passed' : 'Low Confidence'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Storage Tab */}
      {activeTab === 'storage' && (
        <div className="settings-section">
          <h2>Storage Configuration</h2>
          <p className="section-description">Configure where documents are stored</p>

          <div className="form-group">
            <label>Storage Provider</label>
            <div className="storage-provider-grid">
              {storageProviders.map(provider => (
                <label
                  key={provider.id}
                  className={`storage-provider-card ${settings.storage?.provider === provider.id ? 'selected' : ''}`}
                >
                  <input
                    type="radio"
                    name="storage_provider"
                    value={provider.id}
                    checked={settings.storage?.provider === provider.id}
                    onChange={(e) => updateField('storage.provider', e.target.value)}
                  />
                  <div className="provider-content">
                    <i className={`fas ${provider.id === 'local' ? 'fa-server' : provider.id === 's3' ? 'fa-aws' : provider.id === 'gcs' ? 'fa-google' : 'fa-microsoft'}`}></i>
                    <span className="provider-name">{provider.name}</span>
                    <span className="provider-desc">{provider.description}</span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {settings.storage?.provider !== 'local' && (
            <div className="form-row two-col">
              <div className="form-group">
                <label>Bucket/Container Name</label>
                <input
                  type="text"
                  value={settings.storage?.bucket_name || ''}
                  onChange={(e) => updateField('storage.bucket_name', e.target.value)}
                  placeholder="my-document-bucket"
                  className={fieldErrors['storage.bucket_name'] ? 'has-error' : ''}
                />
                {fieldErrors['storage.bucket_name'] && (
                  <span className="field-error">{fieldErrors['storage.bucket_name']}</span>
                )}
              </div>

              <div className="form-group">
                <label>Path Prefix</label>
                <input
                  type="text"
                  value={settings.storage?.path_prefix || 'documents'}
                  onChange={(e) => updateField('storage.path_prefix', e.target.value)}
                  placeholder="documents"
                />
              </div>
            </div>
          )}

          <div className="divider"></div>

          <h3>Retention & Security</h3>

          <div className="form-row two-col">
            <div className="form-group">
              <label>Retention Period (Days)</label>
              <input
                type="number"
                min="30"
                max="3650"
                value={settings.storage?.retention_days || 2555}
                onChange={(e) => updateField('storage.retention_days', parseInt(e.target.value))}
              />
              <span className="field-hint">
                {Math.round((settings.storage?.retention_days || 2555) / 365)} years
              </span>
            </div>
          </div>

          <div className="toggle-options">
            <label className="toggle-option">
              <input
                type="checkbox"
                checked={settings.storage?.enable_versioning}
                onChange={(e) => updateField('storage.enable_versioning', e.target.checked)}
              />
              <div className="toggle-content">
                <span className="toggle-label">Enable Versioning</span>
                <span className="toggle-hint">Keep previous versions of documents when updated</span>
              </div>
            </label>

            <label className="toggle-option">
              <input
                type="checkbox"
                checked={settings.storage?.encryption_enabled}
                onChange={(e) => updateField('storage.encryption_enabled', e.target.checked)}
              />
              <div className="toggle-content">
                <span className="toggle-label">Enable Encryption</span>
                <span className="toggle-hint">Encrypt documents at rest</span>
              </div>
            </label>
          </div>
        </div>
      )}

      {/* Notifications Tab */}
      {activeTab === 'notifications' && (
        <div className="settings-section">
          <h2>Document Notifications</h2>
          <p className="section-description">Configure notifications for document events</p>

          <div className="notification-group">
            <h3>Email Notifications</h3>

            <div className="notification-options">
              <label className="notification-option">
                <input
                  type="checkbox"
                  checked={settings.notifications?.email_on_upload}
                  onChange={(e) => updateField('notifications.email_on_upload', e.target.checked)}
                />
                <div className="option-content">
                  <span>Document Uploaded</span>
                  <span className="option-hint">Notify when a new document is uploaded</span>
                </div>
              </label>

              <label className="notification-option">
                <input
                  type="checkbox"
                  checked={settings.notifications?.email_on_classification}
                  onChange={(e) => updateField('notifications.email_on_classification', e.target.checked)}
                />
                <div className="option-content">
                  <span>Classification Complete</span>
                  <span className="option-hint">Notify when AI classification is complete</span>
                </div>
              </label>

              <label className="notification-option">
                <input
                  type="checkbox"
                  checked={settings.notifications?.email_on_expiration}
                  onChange={(e) => updateField('notifications.email_on_expiration', e.target.checked)}
                />
                <div className="option-content">
                  <span>Document Expiring</span>
                  <span className="option-hint">Notify before documents expire</span>
                </div>
              </label>

              <label className="notification-option">
                <input
                  type="checkbox"
                  checked={settings.notifications?.notify_borrower_on_receipt}
                  onChange={(e) => updateField('notifications.notify_borrower_on_receipt', e.target.checked)}
                />
                <div className="option-content">
                  <span>Notify Borrower on Receipt</span>
                  <span className="option-hint">Send confirmation to borrower when document is received</span>
                </div>
              </label>
            </div>

            {settings.notifications?.email_on_expiration && (
              <div className="form-group" style={{ maxWidth: '250px', marginTop: '16px' }}>
                <label>Expiration Warning (Days)</label>
                <input
                  type="number"
                  min="7"
                  max="90"
                  value={settings.notifications?.expiration_warning_days || 30}
                  onChange={(e) => updateField('notifications.expiration_warning_days', parseInt(e.target.value))}
                />
                <span className="field-hint">Days before expiration to send warning</span>
              </div>
            )}
          </div>

          <div className="divider"></div>

          <div className="notification-group">
            <h3>Task Creation</h3>

            <label className="notification-option">
              <input
                type="checkbox"
                checked={settings.notifications?.create_tasks_for_missing_docs}
                onChange={(e) => updateField('notifications.create_tasks_for_missing_docs', e.target.checked)}
              />
              <div className="option-content">
                <span>Create Tasks for Missing Documents</span>
                <span className="option-hint">Automatically create tasks to collect missing documents</span>
              </div>
            </label>
          </div>
        </div>
      )}

      {/* Sticky Save Bar */}
      {hasChanges && (
        <div className="sticky-save-bar">
          <div className="save-bar-content">
            <span>You have unsaved changes</span>
            <div className="save-bar-actions">
              <button className="btn-secondary" onClick={handleDiscard} disabled={submitting}>
                Discard
              </button>
              <button className="btn-primary" onClick={handleSave} disabled={submitting}>
                {submitting ? (
                  <>
                    <span className="spinner-sm"></span> Saving...
                  </>
                ) : (
                  <>
                    <i className="fas fa-check"></i> Save Changes
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default DocumentUploadSettings;
