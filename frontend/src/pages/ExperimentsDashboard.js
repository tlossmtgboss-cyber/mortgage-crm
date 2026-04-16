import React, { useState, useEffect } from 'react';
import './ExperimentsDashboard.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function ExperimentsDashboard() {
  const [experiments, setExperiments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedExperiment, setSelectedExperiment] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterType, setFilterType] = useState('all');

  // Create experiment form state
  const [newExperiment, setNewExperiment] = useState({
    name: '',
    description: '',
    experiment_type: 'prompt',
    primary_metric: '',
    secondary_metrics: [],
    target_percentage: 100,
    min_sample_size: 100,
    confidence_level: 0.95,
    variants: [
      { name: 'Control', description: '', is_control: true, traffic_allocation: 50, config: {} },
      { name: 'Treatment A', description: '', is_control: false, traffic_allocation: 50, config: {} }
    ]
  });

  useEffect(() => {
    loadExperiments();
  }, [filterStatus, filterType]);

  const loadExperiments = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filterStatus !== 'all') params.append('status_filter', filterStatus);
      if (filterType !== 'all') params.append('experiment_type', filterType);

      const response = await fetch(
        `${API_BASE_URL}/api/v1/experiments?${params.toString()}`,
        {
          headers: {
            'Authorization': `Bearer ${getToken()}`
          }
        }
      );

      if (!response.ok) throw new Error('Failed to load experiments');

      const data = await response.json();
      setExperiments(data.experiments || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadExperimentDetails = async (experimentId) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/experiments/${experimentId}`,
        {
          headers: {
            'Authorization': `Bearer ${getToken()}`
          }
        }
      );

      if (!response.ok) throw new Error('Failed to load experiment details');

      const data = await response.json();
      setSelectedExperiment(data);

      // Load analysis if experiment is running or completed
      if (data.status === 'RUNNING' || data.status === 'COMPLETED') {
        loadAnalysis(experimentId);
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const loadAnalysis = async (experimentId) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/experiments/${experimentId}/analyze`,
        {
          headers: {
            'Authorization': `Bearer ${getToken()}`
          }
        }
      );

      if (!response.ok) {
        setAnalysis(null);
        return;
      }

      const data = await response.json();
      setAnalysis(data);
    } catch (err) {
      setAnalysis(null);
    }
  };

  const createExperiment = async () => {
    try {
      // Validate variants
      const totalAllocation = newExperiment.variants.reduce((sum, v) => sum + parseFloat(v.traffic_allocation), 0);
      if (Math.abs(totalAllocation - 100) > 0.01) {
        toast.error('Variant traffic allocation must sum to 100%');
        return;
      }

      const response = await fetch(
        `${API_BASE_URL}/api/v1/experiments/`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${getToken()}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(newExperiment)
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create experiment');
      }

      toast.success('Experiment created successfully!');
      setShowCreateModal(false);
      resetForm();
      loadExperiments();
    } catch (err) {
      toast.error(`Error: ${err.message}`);
    }
  };

  const startExperiment = async (experimentId) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/experiments/${experimentId}/start`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${getToken()}`
          }
        }
      );

      if (!response.ok) throw new Error('Failed to start experiment');

      toast.success('Experiment started successfully!');
      loadExperiments();
      if (selectedExperiment?.id === experimentId) {
        loadExperimentDetails(experimentId);
      }
    } catch (err) {
      toast.error(`Error: ${err.message}`);
    }
  };

  const stopExperiment = async (experimentId, declareWinner = false) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/experiments/${experimentId}/stop?declare_winner=${declareWinner}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${getToken()}`
          }
        }
      );

      if (!response.ok) throw new Error('Failed to stop experiment');

      toast.success('Experiment stopped successfully!');
      loadExperiments();
      if (selectedExperiment?.id === experimentId) {
        loadExperimentDetails(experimentId);
      }
    } catch (err) {
      toast.error(`Error: ${err.message}`);
    }
  };

  const deleteExperiment = async (experimentId) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/experiments/${experimentId}`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${getToken()}`
          }
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to delete experiment');
      }

      toast.success('Experiment deleted successfully!');
      setSelectedExperiment(null);
      loadExperiments();
    } catch (err) {
      toast.error(`Error: ${err.message}`);
    }
  };

  const resetForm = () => {
    setNewExperiment({
      name: '',
      description: '',
      experiment_type: 'prompt',
      primary_metric: '',
      secondary_metrics: [],
      target_percentage: 100,
      min_sample_size: 100,
      confidence_level: 0.95,
      variants: [
        { name: 'Control', description: '', is_control: true, traffic_allocation: 50, config: {} },
        { name: 'Treatment A', description: '', is_control: false, traffic_allocation: 50, config: {} }
      ]
    });
  };

  const addVariant = () => {
    const currentCount = newExperiment.variants.length;
    const newAllocation = 100 / (currentCount + 1);

    setNewExperiment({
      ...newExperiment,
      variants: [
        ...newExperiment.variants.map(v => ({
          ...v,
          traffic_allocation: newAllocation
        })),
        {
          name: `Treatment ${String.fromCharCode(65 + currentCount - 1)}`,
          description: '',
          is_control: false,
          traffic_allocation: newAllocation,
          config: {}
        }
      ]
    });
  };

  const removeVariant = (index) => {
    if (newExperiment.variants.length <= 2) {
      toast.error('Must have at least 2 variants');
      return;
    }

    const newVariants = newExperiment.variants.filter((_, i) => i !== index);
    const newAllocation = 100 / newVariants.length;

    setNewExperiment({
      ...newExperiment,
      variants: newVariants.map(v => ({
        ...v,
        traffic_allocation: newAllocation
      }))
    });
  };

  const updateVariant = (index, field, value) => {
    const newVariants = [...newExperiment.variants];
    newVariants[index] = {
      ...newVariants[index],
      [field]: value
    };
    setNewExperiment({
      ...newExperiment,
      variants: newVariants
    });
  };

  const getStatusBadgeClass = (status) => {
    const statusMap = {
      'DRAFT': 'status-draft',
      'RUNNING': 'status-running',
      'PAUSED': 'status-paused',
      'COMPLETED': 'status-completed',
      'ARCHIVED': 'status-archived'
    };
    return statusMap[status] || 'status-draft';
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading && experiments.length === 0) {
    return <div className="experiments-dashboard"><div className="loading">Loading experiments...</div></div>;
  }

  return (
    <div className="experiments-dashboard">
      <div className="experiments-header">
        <div className="header-title">
          <h2>🧪 A/B Testing & Experiments</h2>
          <p className="subtitle">Test prompts, models, and features with statistical rigor</p>
        </div>
        <button className="btn-create" onClick={() => setShowCreateModal(true)}>
          + Create Experiment
        </button>
      </div>

      <div className="experiments-filters">
        <div className="filter-group">
          <label>Status:</label>
          <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="all">All Status</option>
            <option value="draft">Draft</option>
            <option value="running">Running</option>
            <option value="paused">Paused</option>
            <option value="completed">Completed</option>
            <option value="archived">Archived</option>
          </select>
        </div>
        <div className="filter-group">
          <label>Type:</label>
          <select value={filterType} onChange={(e) => setFilterType(e.target.value)}>
            <option value="all">All Types</option>
            <option value="prompt">Prompt</option>
            <option value="model">Model</option>
            <option value="agent_config">Agent Config</option>
            <option value="feature">Feature</option>
            <option value="ui">UI</option>
            <option value="workflow">Workflow</option>
          </select>
        </div>
        <div className="experiments-count">
          {experiments.length} experiment{experiments.length !== 1 ? 's' : ''}
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="experiments-content">
        <div className="experiments-list">
          {experiments.length === 0 ? (
            <div className="empty-state">
              <p>No experiments found</p>
              <button onClick={() => setShowCreateModal(true)}>Create your first experiment</button>
            </div>
          ) : (
            experiments.map(exp => (
              <div
                key={exp.id}
                className={`experiment-card ${selectedExperiment?.id === exp.id ? 'selected' : ''}`}
                onClick={() => loadExperimentDetails(exp.id)}
              >
                <div className="experiment-card-header">
                  <h3>{exp.name}</h3>
                  <span className={`status-badge ${getStatusBadgeClass(exp.status)}`}>
                    {exp.status}
                  </span>
                </div>
                <p className="experiment-description">{exp.description}</p>
                <div className="experiment-meta">
                  <span className="meta-item">📊 {exp.type}</span>
                  <span className="meta-item">🎯 {exp.primary_metric}</span>
                  <span className="meta-item">📅 {formatDate(exp.created_at)}</span>
                </div>
              </div>
            ))
          )}
        </div>

        {selectedExperiment && (
          <div className="experiment-details">
            <div className="details-header">
              <div>
                <h2>{selectedExperiment.name}</h2>
                <span className={`status-badge ${getStatusBadgeClass(selectedExperiment.status)}`}>
                  {selectedExperiment.status}
                </span>
              </div>
              <div className="details-actions">
                {selectedExperiment.status === 'DRAFT' && (
                  <button className="btn-start" onClick={() => startExperiment(selectedExperiment.id)}>
                    ▶ Start
                  </button>
                )}
                {selectedExperiment.status === 'RUNNING' && (
                  <>
                    <button className="btn-pause" onClick={() => stopExperiment(selectedExperiment.id, false)}>
                      ⏸ Pause
                    </button>
                    <button className="btn-complete" onClick={() => stopExperiment(selectedExperiment.id, true)}>
                      ✓ Complete & Declare Winner
                    </button>
                  </>
                )}
                {(selectedExperiment.status === 'DRAFT' || selectedExperiment.status === 'ARCHIVED') && (
                  <button className="btn-delete" onClick={() => deleteExperiment(selectedExperiment.id)}>
                    🗑 Delete
                  </button>
                )}
              </div>
            </div>

            <div className="details-info">
              <div className="info-section">
                <h3>Description</h3>
                <p>{selectedExperiment.description}</p>
              </div>

              <div className="info-grid">
                <div className="info-item">
                  <label>Type:</label>
                  <span>{selectedExperiment.type}</span>
                </div>
                <div className="info-item">
                  <label>Primary Metric:</label>
                  <span>{selectedExperiment.primary_metric}</span>
                </div>
                <div className="info-item">
                  <label>Target Users:</label>
                  <span>{selectedExperiment.target_percentage}%</span>
                </div>
                <div className="info-item">
                  <label>Min Sample Size:</label>
                  <span>{selectedExperiment.min_sample_size}</span>
                </div>
                <div className="info-item">
                  <label>Confidence Level:</label>
                  <span>{(selectedExperiment.confidence_level * 100).toFixed(0)}%</span>
                </div>
                <div className="info-item">
                  <label>Created:</label>
                  <span>{formatDate(selectedExperiment.created_at)}</span>
                </div>
                {selectedExperiment.started_at && (
                  <div className="info-item">
                    <label>Started:</label>
                    <span>{formatDate(selectedExperiment.started_at)}</span>
                  </div>
                )}
                {selectedExperiment.ended_at && (
                  <div className="info-item">
                    <label>Ended:</label>
                    <span>{formatDate(selectedExperiment.ended_at)}</span>
                  </div>
                )}
              </div>

              {selectedExperiment.secondary_metrics && selectedExperiment.secondary_metrics.length > 0 && (
                <div className="info-section">
                  <h3>Secondary Metrics</h3>
                  <div className="metrics-list">
                    {selectedExperiment.secondary_metrics.map((metric, idx) => (
                      <span key={idx} className="metric-tag">{metric}</span>
                    ))}
                  </div>
                </div>
              )}

              <div className="info-section">
                <h3>Variants ({selectedExperiment.variants.length})</h3>
                <div className="variants-list">
                  {selectedExperiment.variants.map(variant => (
                    <div key={variant.id} className={`variant-card ${variant.is_control ? 'control' : ''}`}>
                      <div className="variant-header">
                        <h4>
                          {variant.name}
                          {variant.is_control && <span className="control-badge">Control</span>}
                        </h4>
                        <span className="traffic-allocation">{variant.traffic_allocation}%</span>
                      </div>
                      {variant.description && <p>{variant.description}</p>}
                      {selectedExperiment.winning_variant_id === variant.id && (
                        <div className="winner-badge">🏆 Winner</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {analysis && (
                <div className="info-section analysis-section">
                  <h3>📈 Statistical Analysis</h3>
                  <div className="analysis-grid">
                    <div className="analysis-item">
                      <label>P-Value:</label>
                      <span className={analysis.p_value < 0.05 ? 'significant' : ''}>
                        {analysis.p_value ? analysis.p_value.toFixed(4) : 'N/A'}
                      </span>
                    </div>
                    <div className="analysis-item">
                      <label>Statistically Significant:</label>
                      <span className={analysis.is_significant ? 'yes' : 'no'}>
                        {analysis.is_significant ? '✓ Yes' : '✗ No'}
                      </span>
                    </div>
                    <div className="analysis-item">
                      <label>Sample Size:</label>
                      <span>
                        {analysis.current_sample_size} / {analysis.required_sample_size}
                      </span>
                    </div>
                    <div className="analysis-item">
                      <label>Sufficient Data:</label>
                      <span className={analysis.sufficient_sample_size ? 'yes' : 'no'}>
                        {analysis.sufficient_sample_size ? '✓ Yes' : '✗ No'}
                      </span>
                    </div>
                  </div>
                  {analysis.recommendation_reason && (
                    <div className="recommendation">
                      <strong>Recommendation:</strong>
                      <p>{analysis.recommendation_reason}</p>
                      {analysis.recommendation_confidence && (
                        <p className="confidence">
                          Confidence: {(analysis.recommendation_confidence * 100).toFixed(1)}%
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Create Experiment Modal */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create New Experiment</h2>
              <button className="modal-close" onClick={() => setShowCreateModal(false)}>×</button>
            </div>

            <div className="modal-body">
              <div className="form-group">
                <label>Experiment Name *</label>
                <input
                  type="text"
                  value={newExperiment.name}
                  onChange={(e) => setNewExperiment({ ...newExperiment, name: e.target.value })}
                  placeholder="e.g., Lead Qualification Prompt Test"
                />
              </div>

              <div className="form-group">
                <label>Description *</label>
                <textarea
                  value={newExperiment.description}
                  onChange={(e) => setNewExperiment({ ...newExperiment, description: e.target.value })}
                  placeholder="What are you testing and why?"
                  rows="3"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Experiment Type *</label>
                  <select
                    value={newExperiment.experiment_type}
                    onChange={(e) => setNewExperiment({ ...newExperiment, experiment_type: e.target.value })}
                  >
                    <option value="prompt">Prompt</option>
                    <option value="model">Model</option>
                    <option value="agent_config">Agent Config</option>
                    <option value="feature">Feature</option>
                    <option value="ui">UI</option>
                    <option value="workflow">Workflow</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Primary Metric *</label>
                  <input
                    type="text"
                    value={newExperiment.primary_metric}
                    onChange={(e) => setNewExperiment({ ...newExperiment, primary_metric: e.target.value })}
                    placeholder="e.g., resolution_rate"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Target Users (%)</label>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={newExperiment.target_percentage}
                    onChange={(e) => setNewExperiment({ ...newExperiment, target_percentage: parseFloat(e.target.value) })}
                  />
                </div>

                <div className="form-group">
                  <label>Min Sample Size</label>
                  <input
                    type="number"
                    min="10"
                    value={newExperiment.min_sample_size}
                    onChange={(e) => setNewExperiment({ ...newExperiment, min_sample_size: parseInt(e.target.value) })}
                  />
                </div>

                <div className="form-group">
                  <label>Confidence Level</label>
                  <select
                    value={newExperiment.confidence_level}
                    onChange={(e) => setNewExperiment({ ...newExperiment, confidence_level: parseFloat(e.target.value) })}
                  >
                    <option value="0.90">90%</option>
                    <option value="0.95">95%</option>
                    <option value="0.99">99%</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label>
                  Variants ({newExperiment.variants.length})
                  <button type="button" className="btn-add-variant" onClick={addVariant}>
                    + Add Variant
                  </button>
                </label>
                <div className="variants-form">
                  {newExperiment.variants.map((variant, idx) => (
                    <div key={idx} className="variant-form-card">
                      <div className="variant-form-header">
                        <input
                          type="text"
                          value={variant.name}
                          onChange={(e) => updateVariant(idx, 'name', e.target.value)}
                          placeholder="Variant name"
                        />
                        {!variant.is_control && newExperiment.variants.length > 2 && (
                          <button
                            type="button"
                            className="btn-remove-variant"
                            onClick={() => removeVariant(idx)}
                          >
                            ×
                          </button>
                        )}
                      </div>
                      <input
                        type="text"
                        value={variant.description}
                        onChange={(e) => updateVariant(idx, 'description', e.target.value)}
                        placeholder="Description (optional)"
                      />
                      <div className="variant-form-row">
                        <label>
                          <input
                            type="checkbox"
                            checked={variant.is_control}
                            onChange={(e) => updateVariant(idx, 'is_control', e.target.checked)}
                          />
                          Control
                        </label>
                        <input
                          type="number"
                          min="0"
                          max="100"
                          step="0.1"
                          value={variant.traffic_allocation}
                          onChange={(e) => updateVariant(idx, 'traffic_allocation', parseFloat(e.target.value))}
                          placeholder="Traffic %"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-cancel" onClick={() => setShowCreateModal(false)}>
                Cancel
              </button>
              <button
                className="btn-create-confirm"
                onClick={createExperiment}
                disabled={!newExperiment.name || !newExperiment.description || !newExperiment.primary_metric}
              >
                Create Experiment
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ExperimentsDashboard;
