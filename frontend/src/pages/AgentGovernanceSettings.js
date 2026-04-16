/**
 * Perennia AI - Agent Governance Settings
 *
 * Proof-of-concept implementation demonstrating comprehensive error handling:
 * - Field-level validation with inline errors
 * - Loading states for all operations
 * - Toast notifications for success/error feedback
 * - Cost estimation with warnings
 * - Structured API responses
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAsyncOperation, useFormSubmit } from '../hooks/useAsyncOperation';
import { APIError, ValidationError } from '../utils/api/errors';
import { usePermissions } from '../contexts/PermissionContext';
import { toast } from '../utils/toast';
import { API_BASE_URL } from '../services/api';
import './AgentGovernanceSettings.css';
import { getToken } from '../utils/tokenStore';

// Model configurations with cost info
const MODEL_OPTIONS = [
  { value: 'claude-3-opus', label: 'Claude 3 Opus', costPer1k: 0.015, description: 'Most capable, highest cost' },
  { value: 'claude-3-sonnet', label: 'Claude 3 Sonnet', costPer1k: 0.003, description: 'Balanced performance/cost' },
  { value: 'claude-3-haiku', label: 'Claude 3 Haiku', costPer1k: 0.00025, description: 'Fastest, lowest cost' },
  { value: 'gpt-4-turbo', label: 'GPT-4 Turbo', costPer1k: 0.01, description: 'OpenAI flagship model' },
  { value: 'gpt-4o', label: 'GPT-4o', costPer1k: 0.005, description: 'Optimized GPT-4' },
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini', costPer1k: 0.00015, description: 'Fast and affordable' },
];

// Validation functions
const validateSettings = (settings) => {
  const errors = {};

  if (!settings.displayName?.trim()) {
    errors.displayName = 'Display name is required';
  } else if (settings.displayName.length > 100) {
    errors.displayName = 'Display name must be 100 characters or less';
  }

  if (settings.maxTokens < 100) {
    errors.maxTokens = 'Max tokens must be at least 100';
  } else if (settings.maxTokens > 128000) {
    errors.maxTokens = 'Max tokens cannot exceed 128,000';
  }

  if (settings.temperature < 0 || settings.temperature > 2) {
    errors.temperature = 'Temperature must be between 0 and 2';
  }

  if (settings.contextWindowSize < 1000) {
    errors.contextWindowSize = 'Context window must be at least 1,000 tokens';
  }

  if (settings.maxDailyExecutions < 0) {
    errors.maxDailyExecutions = 'Daily execution limit cannot be negative';
  }

  return errors;
};

// Cost estimation helper
const calculateMonthlyCost = (settings, avgExecutions = 100) => {
  const model = MODEL_OPTIONS.find(m => m.value === settings.model);
  if (!model) return null;

  const tokensPerExecution = settings.maxTokens * 0.7; // Assume 70% average usage
  const monthlyTokens = avgExecutions * 30 * tokensPerExecution;
  const monthlyCost = (monthlyTokens / 1000) * model.costPer1k;

  return {
    monthlyCost: monthlyCost.toFixed(2),
    tokensPerDay: Math.round(avgExecutions * tokensPerExecution),
    isHigh: monthlyCost > 100,
    isVeryHigh: monthlyCost > 500,
  };
};

function AgentGovernanceSettings() {
  const { agentId } = useParams();
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - require admin access
  const canAccessGovernance = isAdmin || hasAnyPermission(['admin.manage', 'agents.manage', 'system.admin']) || userRole === 'admin';

  // State
  const [agent, setAgent] = useState(null);
  const [settings, setSettings] = useState({
    displayName: '',
    model: 'claude-3-sonnet',
    maxTokens: 4096,
    temperature: 0.7,
    contextWindowSize: 16000,
    maxDailyExecutions: 1000,
    enabled: true,
    systemPrompt: '',
    safetyGuardrails: {
      maxResponseLength: 4000,
      blockPii: true,
      requireApproval: false,
      allowedActions: [],
    },
  });
  const [warnings, setWarnings] = useState([]);
  const [costEstimate, setCostEstimate] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);
  const [testResult, setTestResult] = useState(null);

  // API helper
  const apiRequest = async (url, options = {}) => {
    const token = getToken();
    const response = await fetch(`${API_BASE_URL}${url}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...options.headers,
      },
    });

    const data = await response.json();

    if (!response.ok) {
      // Handle structured error response
      if (data.error) {
        const error = new APIError(
          data.error.message || 'Request failed',
          data.error.code || 'UNKNOWN_ERROR',
          {
            details: data.error.details,
            statusCode: response.status,
          }
        );

        // Handle field errors
        if (data.error.field_errors) {
          error.fieldErrors = data.error.field_errors;
        }

        throw error;
      }
      throw new APIError(data.detail || 'Request failed', 'SERVER_ERROR', { statusCode: response.status });
    }

    return data;
  };

  // Fetch agent settings
  const { execute: fetchAgent, isLoading: isLoadingAgent } = useAsyncOperation(
    async () => {
      const data = await apiRequest(`/api/v1/agent-governance-settings/agents/${agentId}`);
      return data.data;
    },
    {
      showErrorToast: true,
      errorMessage: 'Failed to load agent settings',
    }
  );

  // Save settings
  const {
    submit: saveSettings,
    isSubmitting,
    fieldErrors,
    clearFieldError
  } = useFormSubmit({
    onSubmit: async (data) => {
      const response = await apiRequest(`/api/v1/agent-governance-settings/agents/${agentId}`, {
        method: 'PUT',
        body: JSON.stringify({
          display_name: data.displayName,
          model: data.model,
          max_tokens: data.maxTokens,
          temperature: data.temperature,
          context_window_size: data.contextWindowSize,
          max_daily_executions: data.maxDailyExecutions,
          enabled: data.enabled,
          system_prompt: data.systemPrompt,
          safety_guardrails: data.safetyGuardrails,
        }),
      });
      return response;
    },
    validate: validateSettings,
    showSuccessToast: true,
    successMessage: 'Agent settings saved successfully',
    onSuccess: (response) => {
      setHasChanges(false);
      if (response.data?.warnings) {
        setWarnings(response.data.warnings);
      }
      if (response.data?.cost_estimate) {
        setCostEstimate(response.data.cost_estimate);
      }
    },
  });

  // Test configuration
  const { execute: testConfig, isLoading: isTesting } = useAsyncOperation(
    async () => {
      const response = await apiRequest(`/api/v1/agent-governance-settings/agents/${agentId}/test`, {
        method: 'POST',
        body: JSON.stringify({ test_prompt: 'Hello, can you confirm you are working?' }),
      });
      return response.data;
    },
    {
      showSuccessToast: false,
      showErrorToast: true,
      errorMessage: 'Configuration test failed',
      onSuccess: (result) => {
        setTestResult(result);
        if (result.success) {
          toast.success('Configuration test passed!');
        } else {
          toast.warning('Configuration test completed with warnings');
        }
      },
    }
  );

  // Load agent on mount
  useEffect(() => {
    if (agentId) {
      loadAgent();
    }
  }, [agentId]);

  const loadAgent = async () => {
    try {
      const data = await fetchAgent();
      if (data) {
        setAgent(data);
        setSettings({
          displayName: data.display_name || '',
          model: data.model || 'claude-3-sonnet',
          maxTokens: data.max_tokens || 4096,
          temperature: data.temperature || 0.7,
          contextWindowSize: data.context_window_size || 16000,
          maxDailyExecutions: data.max_daily_executions || 1000,
          enabled: data.enabled ?? true,
          systemPrompt: data.system_prompt || '',
          safetyGuardrails: data.safety_guardrails || {
            maxResponseLength: 4000,
            blockPii: true,
            requireApproval: false,
            allowedActions: [],
          },
        });
      }
    } catch (error) {
      // Error already handled by hook
    }
  };

  // Update settings and track changes
  const updateSetting = useCallback((field, value) => {
    setSettings(prev => {
      const newSettings = { ...prev, [field]: value };

      // Calculate cost estimate on model or token changes
      if (field === 'model' || field === 'maxTokens') {
        const estimate = calculateMonthlyCost(newSettings);
        setCostEstimate(estimate);
      }

      return newSettings;
    });
    setHasChanges(true);

    // Clear field error when user edits
    if (fieldErrors[field]) {
      clearFieldError(field);
    }
  }, [fieldErrors, clearFieldError]);

  // Handle form submission
  const handleSave = async (e) => {
    e.preventDefault();
    try {
      await saveSettings(settings);
    } catch (error) {
      // Error handled by hook
    }
  };

  // Handle test configuration
  const handleTest = async () => {
    setTestResult(null);
    try {
      await testConfig();
    } catch (error) {
      // Error handled by hook
    }
  };

  // Loading state
  if (isLoadingAgent) {
    return (
      <div className="agent-settings-page">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading agent settings...</p>
        </div>
      </div>
    );
  }

  // Error state - agent not found
  if (!agent && !isLoadingAgent) {
    return (
      <div className="agent-settings-page">
        <div className="error-state">
          <i className="fas fa-exclamation-triangle"></i>
          <h2>Agent Not Found</h2>
          <p>The requested agent could not be found or you don't have permission to view it.</p>
          <button onClick={() => navigate('/agents')} className="btn-primary">
            Back to Agents
          </button>
        </div>
      </div>
    );
  }

  // Access denied if user doesn't have admin permissions
  if (!canAccessGovernance) {
    return (
      <div className="agent-settings-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to manage agent governance settings.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="agent-settings-page">
      {/* Header */}
      <div className="settings-header">
        <div className="header-left">
          <button onClick={() => navigate(-1)} className="back-btn">
            <i className="fas fa-arrow-left"></i>
          </button>
          <div>
            <h1>{agent?.display_name || 'Agent Settings'}</h1>
            <p className="subtitle">Configure agent behavior and limits</p>
          </div>
        </div>
        <div className="header-actions">
          <button
            onClick={handleTest}
            disabled={isTesting || isSubmitting}
            className="btn-secondary"
          >
            {isTesting ? (
              <>
                <i className="fas fa-spinner fa-spin"></i> Testing...
              </>
            ) : (
              <>
                <i className="fas fa-vial"></i> Test Configuration
              </>
            )}
          </button>
          <button
            onClick={handleSave}
            disabled={isSubmitting || !hasChanges}
            className="btn-primary"
          >
            {isSubmitting ? (
              <>
                <i className="fas fa-spinner fa-spin"></i> Saving...
              </>
            ) : (
              <>
                <i className="fas fa-save"></i> Save Changes
              </>
            )}
          </button>
        </div>
      </div>

      {/* Warnings Banner */}
      {warnings.length > 0 && (
        <div className="warnings-banner">
          <i className="fas fa-exclamation-triangle"></i>
          <div>
            <strong>Configuration Warnings</strong>
            <ul>
              {warnings.map((warning, idx) => (
                <li key={idx}>{warning}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Test Result */}
      {testResult && (
        <div className={`test-result ${testResult.success ? 'success' : 'warning'}`}>
          <div className="test-header">
            <i className={`fas ${testResult.success ? 'fa-check-circle' : 'fa-exclamation-circle'}`}></i>
            <strong>{testResult.success ? 'Test Passed' : 'Test Completed with Issues'}</strong>
          </div>
          {testResult.response_time_ms && (
            <p>Response time: {testResult.response_time_ms}ms</p>
          )}
          {testResult.issues?.length > 0 && (
            <ul>
              {testResult.issues.map((issue, idx) => (
                <li key={idx}>{issue}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <form onSubmit={handleSave}>
        {/* Basic Settings Section */}
        <section className="settings-section">
          <h2>Basic Settings</h2>

          <div className="form-row">
            <label htmlFor="displayName">Display Name</label>
            <input
              id="displayName"
              type="text"
              value={settings.displayName}
              onChange={(e) => updateSetting('displayName', e.target.value)}
              className={fieldErrors.displayName ? 'has-error' : ''}
              placeholder="Enter agent display name"
            />
            {fieldErrors.displayName && (
              <span className="field-error">{fieldErrors.displayName}</span>
            )}
          </div>

          <div className="form-row">
            <label htmlFor="enabled">Status</label>
            <div className="toggle-group">
              <button
                type="button"
                className={`toggle-btn ${settings.enabled ? 'active' : ''}`}
                onClick={() => updateSetting('enabled', true)}
              >
                <i className="fas fa-check"></i> Enabled
              </button>
              <button
                type="button"
                className={`toggle-btn ${!settings.enabled ? 'active' : ''}`}
                onClick={() => updateSetting('enabled', false)}
              >
                <i className="fas fa-pause"></i> Disabled
              </button>
            </div>
          </div>
        </section>

        {/* Model Settings Section */}
        <section className="settings-section">
          <h2>Model Configuration</h2>

          <div className="form-row">
            <label htmlFor="model">AI Model</label>
            <select
              id="model"
              value={settings.model}
              onChange={(e) => updateSetting('model', e.target.value)}
            >
              {MODEL_OPTIONS.map(option => (
                <option key={option.value} value={option.value}>
                  {option.label} - {option.description}
                </option>
              ))}
            </select>
          </div>

          <div className="form-row">
            <label htmlFor="maxTokens">Max Tokens</label>
            <input
              id="maxTokens"
              type="number"
              value={settings.maxTokens}
              onChange={(e) => updateSetting('maxTokens', parseInt(e.target.value) || 0)}
              min="100"
              max="128000"
              step="100"
              className={fieldErrors.maxTokens ? 'has-error' : ''}
            />
            {fieldErrors.maxTokens && (
              <span className="field-error">{fieldErrors.maxTokens}</span>
            )}
            <span className="field-hint">Maximum tokens per response (100 - 128,000)</span>
          </div>

          <div className="form-row">
            <label htmlFor="temperature">Temperature</label>
            <div className="range-input">
              <input
                id="temperature"
                type="range"
                value={settings.temperature}
                onChange={(e) => updateSetting('temperature', parseFloat(e.target.value))}
                min="0"
                max="2"
                step="0.1"
              />
              <span className="range-value">{settings.temperature}</span>
            </div>
            <span className="field-hint">
              Lower = more focused, Higher = more creative (0 - 2)
            </span>
          </div>

          <div className="form-row">
            <label htmlFor="contextWindowSize">Context Window</label>
            <input
              id="contextWindowSize"
              type="number"
              value={settings.contextWindowSize}
              onChange={(e) => updateSetting('contextWindowSize', parseInt(e.target.value) || 0)}
              min="1000"
              max="200000"
              step="1000"
              className={fieldErrors.contextWindowSize ? 'has-error' : ''}
            />
            {fieldErrors.contextWindowSize && (
              <span className="field-error">{fieldErrors.contextWindowSize}</span>
            )}
          </div>

          {/* Cost Estimate Card */}
          {costEstimate && (
            <div className={`cost-estimate-card ${costEstimate.isVeryHigh ? 'very-high' : costEstimate.isHigh ? 'high' : ''}`}>
              <div className="cost-header">
                <i className={`fas ${costEstimate.isVeryHigh ? 'fa-exclamation-triangle' : 'fa-calculator'}`}></i>
                <strong>Estimated Monthly Cost</strong>
              </div>
              <div className="cost-value">${costEstimate.monthlyCost}</div>
              <div className="cost-details">
                Based on ~100 executions/day at current token limits
              </div>
              {costEstimate.isHigh && (
                <div className="cost-warning">
                  Consider using a more cost-effective model or reducing token limits
                </div>
              )}
            </div>
          )}
        </section>

        {/* Execution Limits Section */}
        <section className="settings-section">
          <h2>Execution Limits</h2>

          <div className="form-row">
            <label htmlFor="maxDailyExecutions">Max Daily Executions</label>
            <input
              id="maxDailyExecutions"
              type="number"
              value={settings.maxDailyExecutions}
              onChange={(e) => updateSetting('maxDailyExecutions', parseInt(e.target.value) || 0)}
              min="0"
              max="100000"
              className={fieldErrors.maxDailyExecutions ? 'has-error' : ''}
            />
            {fieldErrors.maxDailyExecutions && (
              <span className="field-error">{fieldErrors.maxDailyExecutions}</span>
            )}
            <span className="field-hint">Set to 0 for unlimited (not recommended)</span>
          </div>
        </section>

        {/* Safety Guardrails Section */}
        <section className="settings-section">
          <h2>Safety Guardrails</h2>

          <div className="form-row">
            <label htmlFor="maxResponseLength">Max Response Length</label>
            <input
              id="maxResponseLength"
              type="number"
              value={settings.safetyGuardrails.maxResponseLength}
              onChange={(e) => updateSetting('safetyGuardrails', {
                ...settings.safetyGuardrails,
                maxResponseLength: parseInt(e.target.value) || 0,
              })}
              min="100"
              max="50000"
            />
          </div>

          <div className="form-row checkbox-row">
            <label>
              <input
                type="checkbox"
                checked={settings.safetyGuardrails.blockPii}
                onChange={(e) => updateSetting('safetyGuardrails', {
                  ...settings.safetyGuardrails,
                  blockPii: e.target.checked,
                })}
              />
              Block PII in Responses
              <span className="checkbox-hint">Prevents agent from outputting sensitive personal data</span>
            </label>
          </div>

          <div className="form-row checkbox-row">
            <label>
              <input
                type="checkbox"
                checked={settings.safetyGuardrails.requireApproval}
                onChange={(e) => updateSetting('safetyGuardrails', {
                  ...settings.safetyGuardrails,
                  requireApproval: e.target.checked,
                })}
              />
              Require Human Approval
              <span className="checkbox-hint">High-risk actions require manager approval before execution</span>
            </label>
          </div>
        </section>

        {/* System Prompt Section */}
        <section className="settings-section">
          <h2>System Prompt</h2>
          <p className="section-description">
            Define the agent's base behavior and personality
          </p>

          <div className="form-row">
            <textarea
              value={settings.systemPrompt}
              onChange={(e) => updateSetting('systemPrompt', e.target.value)}
              placeholder="Enter the system prompt that defines this agent's behavior..."
              rows={8}
            />
            <div className="char-count">
              {settings.systemPrompt.length} / 10,000 characters
            </div>
          </div>
        </section>

        {/* Sticky Save Bar */}
        {hasChanges && (
          <div className="sticky-save-bar">
            <div className="save-bar-content">
              <span>You have unsaved changes</span>
              <div className="save-bar-actions">
                <button
                  type="button"
                  onClick={loadAgent}
                  className="btn-secondary"
                  disabled={isSubmitting}
                >
                  Discard
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          </div>
        )}
      </form>
    </div>
  );
}

export default AgentGovernanceSettings;
