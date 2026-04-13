import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { usePermissions } from '../contexts/PermissionContext';
import CategoryTasksModal from '../components/CategoryTasksModal';
import PermissionsStep from '../components/onboarding/steps/PermissionsStep';
import FeatureSelection from '../components/FeatureSelection';
import { getAuthHeaders } from '../utils/auth';
import './UserCreationWizard.css';

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE_URL = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// Wizard Steps
const STEPS = {
  BASIC_INFO: 'basic_info',
  ROLE_BUILDER: 'role_builder',
  PERMISSIONS: 'permissions',
  FEATURES: 'features',
  REVIEW: 'review',
  SCORECARD: 'scorecard',
  ACTIVATION: 'activation'
};

const STEP_ORDER = [
  STEPS.BASIC_INFO,
  STEPS.ROLE_BUILDER,
  STEPS.PERMISSIONS,
  STEPS.FEATURES,
  STEPS.REVIEW,
  STEPS.SCORECARD,
  STEPS.ACTIVATION
];

const STEP_LABELS = {
  [STEPS.BASIC_INFO]: 'Basic Info',
  [STEPS.ROLE_BUILDER]: 'Role Builder',
  [STEPS.PERMISSIONS]: 'Permissions',
  [STEPS.FEATURES]: 'Features',
  [STEPS.REVIEW]: 'Review',
  [STEPS.SCORECARD]: 'Scorecard',
  [STEPS.ACTIVATION]: 'Activation'
};

function UserCreationWizard() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - only admins/managers can create users
  const canCreateUsers = isAdmin || hasAnyPermission(['admin.manage', 'users.manage', 'users.create', 'team.manage', 'system.admin']) ||
    userRole === 'admin' || userRole === 'site_admin' || userRole === 'management';

  const [currentStep, setCurrentStep] = useState(STEPS.BASIC_INFO);
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Reference data from API
  const [roles, setRoles] = useState([]);
  const [categories, setCategories] = useState([]);
  const [responsibilities, setResponsibilities] = useState([]);
  const [permissionTemplates, setPermissionTemplates] = useState([]);

  // Permission mode state (template vs custom)
  const [permissionMode, setPermissionMode] = useState('template');

  // Category tasks modal state
  const [selectedCategoryForTasks, setSelectedCategoryForTasks] = useState(null);
  const [showCategoryTasksModal, setShowCategoryTasksModal] = useState(false);

  // Form data
  const [formData, setFormData] = useState({
    // Basic Info
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    department: '',
    job_title: '',
    // Role Builder
    role_id: null,
    selected_categories: [],
    selected_responsibilities: [],
    // Permissions
    permission_template_id: null,
    custom_permissions: {},
    // Stage-based permissions
    stages: [],
    features: {},
    // Feature Selection - enabled feature keys
    selected_features: [],
    // Generated data
    scorecard: null,
    created_user_id: null,
    activation_token: null
  });

  // Load reference data on mount
  useEffect(() => {
    loadReferenceData();
  }, []);

  // Default roles for the mortgage industry
  const DEFAULT_ROLES = [
    { id: 1, display_name: 'Loan Officer', description: 'Originates loans, manages borrower relationships, handles rate locks and pre-approvals' },
    { id: 2, display_name: 'Jr. Loan Officer', description: 'Entry-level loan originator, learning the sales process and building client relationships' },
    { id: 3, display_name: 'Loan Officer Assistant', description: 'Supports Loan Officers with administrative tasks, document collection, and client communication' },
    { id: 4, display_name: 'Application Analyst', description: 'Reviews and analyzes loan applications for completeness, accuracy, and initial qualification' },
    { id: 5, display_name: 'Processor', description: 'Manages complete loan processing, document verification, and underwriting submission' },
    { id: 6, display_name: 'Processing Assistant', description: 'Assists processors with documentation, condition tracking, and file preparation' },
    { id: 7, display_name: 'Production Assistant 1', description: 'Entry-level production support, handles initial document intake and data entry' },
    { id: 8, display_name: 'Production Assistant 2', description: 'Mid-level production support, manages pipeline updates and borrower follow-ups' },
    { id: 9, display_name: 'Concierge', description: 'Provides white-glove client service, coordinates communications, and ensures exceptional borrower experience' },
    { id: 10, display_name: 'Closer', description: 'Manages closing coordination, final document preparation, and funding' },
    { id: 11, display_name: 'Underwriter', description: 'Reviews loan applications, assesses risk, and issues approval decisions' },
    { id: 12, display_name: 'Team Lead', description: 'Supervises team members, monitors performance metrics, and ensures quality standards' },
    { id: 13, display_name: 'Branch Manager', description: 'Oversees branch operations, manages staff, and drives business development' },
    { id: 14, display_name: 'Area Manager', description: 'Manages multiple branches within a geographic area, drives regional performance' },
    { id: 15, display_name: 'Regional Manager', description: 'Oversees multiple areas, sets regional strategy, and reports to executive leadership' }
  ];

  // Default categories
  const DEFAULT_CATEGORIES = [
    { id: 1, display_name: 'Lead Generation', description: 'Prospecting and acquiring new leads', workflow_key: 'prospect' },
    { id: 2, display_name: 'Pre-Qualification', description: 'Initial borrower qualification and assessment', workflow_key: 'pre_qualification' },
    { id: 3, display_name: 'Pre-Approval', description: 'Full credit analysis and conditional approval', workflow_key: 'pre_approval' },
    { id: 4, display_name: 'Application Support', description: 'Assisting with loan applications', workflow_key: 'application' },
    { id: 5, display_name: 'Processing Assistance', description: 'Supporting loan processing activities', workflow_key: 'processing' },
    { id: 6, display_name: 'Document Collection', description: 'Gathering and organizing loan documents', workflow_key: 'document_collection' },
    { id: 7, display_name: 'Condition Management', description: 'Tracking and clearing underwriting conditions', workflow_key: 'condition_management' },
    { id: 8, display_name: 'Client Communication', description: 'Maintaining borrower relationships and updates', workflow_key: 'client_communication' },
    { id: 9, display_name: 'Pipeline Management', description: 'Monitoring and managing loan pipeline', workflow_key: 'pipeline_management' },
    { id: 10, display_name: 'Closing Coordination', description: 'Managing the closing process', workflow_key: 'closing' },
    { id: 11, display_name: 'Post-Closing Follow-up', description: 'Client retention and referral generation', workflow_key: 'post_closing' }
  ];

  // Default permission templates
  const DEFAULT_PERMISSION_TEMPLATES = [
    { id: 1, name: 'Full Access', description: 'Complete access to all system features', permissions: { view_all: true, edit_all: true, admin: true } },
    { id: 2, name: 'Standard Loan Officer', description: 'Lead management, pipeline access, client communication', permissions: { leads: true, pipeline: true, clients: true } },
    { id: 3, name: 'Read Only', description: 'View-only access to data', permissions: { view_only: true } },
    { id: 4, name: 'Processing Team', description: 'Access to processing functions and documents', permissions: { processing: true, documents: true, pipeline: true } }
  ];

  const loadReferenceData = async () => {
    setLoading(true);
    try {
      const [rolesRes, categoriesRes, responsibilitiesRes, templatesRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/v1/admin/users/roles`, { headers: getAuthHeaders() }).catch(() => ({ data: null })),
        axios.get(`${API_BASE_URL}/api/v1/admin/users/categories`, { headers: getAuthHeaders() }).catch(() => ({ data: null })),
        axios.get(`${API_BASE_URL}/api/v1/admin/users/responsibilities`, { headers: getAuthHeaders() }).catch(() => ({ data: null })),
        axios.get(`${API_BASE_URL}/api/v1/admin/users/permission-templates`, { headers: getAuthHeaders() }).catch(() => ({ data: null }))
      ]);

      // Handle nested response structure: { success: true, data: { roles: [...] } }
      const extractData = (res, field, defaultVal) => {
        if (res.data?.data?.[field]) return res.data.data[field];
        if (res.data?.[field]) return res.data[field];
        if (Array.isArray(res.data)) return res.data;
        return defaultVal;
      };

      // Map API response fields to expected frontend fields
      const mapRoles = (apiRoles) => apiRoles.map(r => ({
        id: r.id,
        display_name: r.display_name || r.name || r.role_name,
        description: r.description
      }));

      const mapCategories = (apiCats) => apiCats.map(c => ({
        id: c.id,
        display_name: c.display_name || c.name,
        description: c.description
      }));

      const apiRoles = extractData(rolesRes, 'roles', null);
      const apiCategories = extractData(categoriesRes, 'categories', null);
      const apiResponsibilities = extractData(responsibilitiesRes, 'responsibilities', []);
      const apiTemplates = extractData(templatesRes, 'templates', null);

      setRoles(apiRoles ? mapRoles(apiRoles) : DEFAULT_ROLES);
      setCategories(apiCategories ? mapCategories(apiCategories) : DEFAULT_CATEGORIES);
      setResponsibilities(apiResponsibilities || []);
      setPermissionTemplates(apiTemplates || DEFAULT_PERMISSION_TEMPLATES);
    } catch (err) {
      console.error('Error loading reference data:', err);
      // Use defaults if API fails
      setRoles(DEFAULT_ROLES);
      setCategories(DEFAULT_CATEGORIES);
      setResponsibilities([]);
      setPermissionTemplates(DEFAULT_PERMISSION_TEMPLATES);
    } finally {
      setLoading(false);
    }
  };

  const goToStep = (step) => {
    setCurrentStep(step);
    setError(null);
  };

  const nextStep = () => {
    const currentIndex = STEP_ORDER.indexOf(currentStep);
    if (currentIndex < STEP_ORDER.length - 1) {
      setCurrentStep(STEP_ORDER[currentIndex + 1]);
      setError(null);
    }
  };

  const prevStep = () => {
    const currentIndex = STEP_ORDER.indexOf(currentStep);
    if (currentIndex > 0) {
      setCurrentStep(STEP_ORDER[currentIndex - 1]);
      setError(null);
    }
  };

  const updateFormData = (updates) => {
    setFormData(prev => ({ ...prev, ...updates }));
  };

  // When role is selected, auto-populate categories and responsibilities
  const handleRoleSelect = async (roleId) => {
    updateFormData({ role_id: roleId });

    if (roleId) {
      try {
        const response = await axios.get(
          `${API_BASE_URL}/api/v1/admin/users/roles/${roleId}/defaults`,
          { headers: getAuthHeaders() }
        );
        const defaults = response.data;
        updateFormData({
          selected_categories: defaults.category_ids || [],
          selected_responsibilities: defaults.responsibility_ids || []
        });
      } catch (err) {
        console.error('Error loading role defaults:', err);
      }
    }
  };

  // Create user and generate scorecard
  const handleCreateUser = async () => {
    setLoading(true);
    setError(null);

    try {
      const payload = {
        first_name: formData.first_name,
        last_name: formData.last_name,
        email: formData.email,
        phone: formData.phone || null,
        department: formData.department || null,
        job_title: formData.job_title || null,
        role_id: formData.role_id,
        category_ids: formData.selected_categories,
        responsibility_ids: formData.selected_responsibilities,
        permission_template_id: formData.permission_template_id,
        custom_permissions: formData.custom_permissions
      };

      const response = await axios.post(
        `${API_BASE_URL}/api/v1/admin/users/create`,
        payload,
        { headers: getAuthHeaders() }
      );

      const result = response.data;
      updateFormData({
        created_user_id: result.user_id,
        scorecard: result.scorecard,
        activation_token: result.activation_token
      });

      nextStep(); // Move to scorecard step
    } catch (err) {
      console.error('Error creating user:', err);
      setError(err.response?.data?.detail || 'Failed to create user. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Send activation email
  const handleSendActivation = async () => {
    setLoading(true);
    setError(null);

    try {
      await axios.post(
        `${API_BASE_URL}/api/v1/admin/users/${formData.created_user_id}/resend-activation`,
        {},
        { headers: getAuthHeaders() }
      );

      nextStep(); // Move to activation confirmation
    } catch (err) {
      console.error('Error sending activation:', err);
      setError(err.response?.data?.detail || 'Failed to send activation email.');
    } finally {
      setLoading(false);
    }
  };

  const renderStepIndicator = () => (
    <div className="wizard-steps">
      {STEP_ORDER.map((step, index) => {
        const isActive = step === currentStep;
        const isPast = STEP_ORDER.indexOf(currentStep) > index;
        return (
          <div
            key={step}
            className={`wizard-step ${isActive ? 'active' : ''} ${isPast ? 'completed' : ''}`}
            onClick={() => isPast && goToStep(step)}
          >
            <div className="step-number">{isPast ? '✓' : index + 1}</div>
            <div className="step-label">{STEP_LABELS[step]}</div>
          </div>
        );
      })}
    </div>
  );

  const renderBasicInfo = () => (
    <div className="wizard-content">
      <h2>Basic Information</h2>
      <p className="step-description">Enter the new team member's basic information.</p>

      <div className="form-grid">
        <div className="form-group">
          <label>First Name *</label>
          <input
            type="text"
            value={formData.first_name}
            onChange={(e) => updateFormData({ first_name: e.target.value })}
            placeholder="Enter first name"
            required
          />
        </div>

        <div className="form-group">
          <label>Last Name *</label>
          <input
            type="text"
            value={formData.last_name}
            onChange={(e) => updateFormData({ last_name: e.target.value })}
            placeholder="Enter last name"
            required
          />
        </div>

        <div className="form-group full-width">
          <label>Email Address *</label>
          <input
            type="email"
            value={formData.email}
            onChange={(e) => updateFormData({ email: e.target.value })}
            placeholder="Enter email address"
            required
          />
        </div>

        <div className="form-group">
          <label>Phone Number</label>
          <input
            type="tel"
            value={formData.phone}
            onChange={(e) => updateFormData({ phone: e.target.value })}
            placeholder="(555) 555-5555"
          />
        </div>

        <div className="form-group">
          <label>Department</label>
          <input
            type="text"
            value={formData.department}
            onChange={(e) => updateFormData({ department: e.target.value })}
            placeholder="e.g., Operations, Sales"
          />
        </div>

        <div className="form-group full-width">
          <label>Job Title</label>
          <input
            type="text"
            value={formData.job_title}
            onChange={(e) => updateFormData({ job_title: e.target.value })}
            placeholder="e.g., Senior Loan Officer"
          />
        </div>
      </div>

      <div className="wizard-actions">
        <button className="btn-secondary" disabled>Back</button>
        <button
          className="btn-primary"
          onClick={nextStep}
          disabled={!formData.first_name || !formData.last_name || !formData.email}
        >
          Continue to Role Builder
        </button>
      </div>
    </div>
  );

  const renderRoleBuilder = () => {
    const selectedRole = roles.find(r => r.id === formData.role_id);

    // Group responsibilities by category
    const responsibilitiesByCategory = {};
    formData.selected_categories.forEach(catId => {
      const cat = categories.find(c => c.id === catId);
      if (cat) {
        responsibilitiesByCategory[catId] = {
          category: cat,
          responsibilities: responsibilities.filter(r => r.category_id === catId)
        };
      }
    });

    return (
      <div className="wizard-content">
        <h2>Role Builder</h2>
        <p className="step-description">Select a role template, then customize categories and responsibilities.</p>

        {/* Role Selection */}
        <div className="section">
          <h3>Select Role Template</h3>
          <div className="role-grid">
            {roles.map(role => (
              <div
                key={role.id}
                className={`role-card ${formData.role_id === role.id ? 'selected' : ''}`}
                onClick={() => handleRoleSelect(role.id)}
              >
                <h4>{role.display_name}</h4>
                <p>{role.description}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Categories Selection */}
        {selectedRole && (
          <div className="section">
            <h3>Assign Categories</h3>
            <p className="section-hint">Select the functional areas this user will work in. Click on a selected category to view and manage tasks.</p>
            <div className="checkbox-grid">
              {categories.map(category => {
                const isSelected = formData.selected_categories.includes(category.id);
                return (
                  <div
                    key={category.id}
                    className={`checkbox-card clickable ${isSelected ? 'selected' : ''}`}
                    onClick={() => {
                      if (isSelected) {
                        // If already selected, open tasks modal
                        setSelectedCategoryForTasks(category);
                        setShowCategoryTasksModal(true);
                      } else {
                        // If not selected, select it
                        const updated = [...formData.selected_categories, category.id];
                        updateFormData({ selected_categories: updated });
                      }
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={(e) => {
                        e.stopPropagation();
                        const updated = e.target.checked
                          ? [...formData.selected_categories, category.id]
                          : formData.selected_categories.filter(id => id !== category.id);
                        updateFormData({ selected_categories: updated });
                      }}
                      onClick={(e) => e.stopPropagation()}
                    />
                    <div className="checkbox-content">
                      <span className="checkbox-title">{category.display_name}</span>
                      <span className="checkbox-desc">{category.description}</span>
                      {isSelected && (
                        <span className="view-tasks-hint">Click to view tasks</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Responsibilities Selection */}
        {Object.keys(responsibilitiesByCategory).length > 0 && (
          <div className="section">
            <h3>Assign Responsibilities</h3>
            <p className="section-hint">Select specific tasks and duties within each category.</p>

            {Object.entries(responsibilitiesByCategory).map(([catId, data]) => (
              <div key={catId} className="responsibility-group">
                <h4>{data.category.display_name}</h4>
                <div className="checkbox-list">
                  {data.responsibilities.map(resp => (
                    <label key={resp.id} className="checkbox-item">
                      <input
                        type="checkbox"
                        checked={formData.selected_responsibilities.includes(resp.id)}
                        onChange={(e) => {
                          const updated = e.target.checked
                            ? [...formData.selected_responsibilities, resp.id]
                            : formData.selected_responsibilities.filter(id => id !== resp.id);
                          updateFormData({ selected_responsibilities: updated });
                        }}
                      />
                      <span>{resp.display_name}</span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="wizard-actions">
          <button className="btn-secondary" onClick={prevStep}>Back</button>
          <button
            className="btn-primary"
            onClick={nextStep}
            disabled={!formData.role_id || formData.selected_categories.length === 0}
          >
            Continue to Permissions
          </button>
        </div>
      </div>
    );
  };

  const renderPermissions = () => {
    const handlePermissionsComplete = (data) => {
      updateFormData({
        stages: data.stages,
        features: data.features,
        custom_permissions: data.customPermissions || {}
      });
      nextStep();
    };

    return (
      <PermissionsStep
        isAdminMode={true}
        initialStages={formData.stages}
        initialFeatures={formData.features}
        onComplete={handlePermissionsComplete}
        onBack={prevStep}
      />
    );
  };

  const renderFeatures = () => {
    const handleFeaturesChange = (selectedFeatureKeys) => {
      updateFormData({ selected_features: selectedFeatureKeys });
    };

    return (
      <div className="wizard-content">
        <h2>Feature Access</h2>
        <p className="step-description">Select which platform features this user will have access to.</p>

        <FeatureSelection
          companyId={1}
          selectedFeatures={formData.selected_features}
          onFeaturesChange={handleFeaturesChange}
          showPricing={false}
        />

        <div className="wizard-actions">
          <button className="btn-secondary" onClick={prevStep}>
            Back
          </button>
          <button
            className="btn-primary"
            onClick={nextStep}
          >
            Continue
          </button>
        </div>
      </div>
    );
  };

  const renderReview = () => {
    const selectedRole = roles.find(r => r.id === formData.role_id);
    const selectedTemplate = permissionTemplates.find(t => t.id === formData.permission_template_id);
    const selectedCats = categories.filter(c => formData.selected_categories.includes(c.id));
    const selectedResps = responsibilities.filter(r => formData.selected_responsibilities.includes(r.id));

    return (
      <div className="wizard-content">
        <h2>Review & Confirm</h2>
        <p className="step-description">Review all information before creating the user account.</p>

        <div className="review-sections">
          <div className="review-section">
            <h3>Basic Information</h3>
            <div className="review-grid">
              <div className="review-item">
                <span className="review-label">Name</span>
                <span className="review-value">{formData.first_name} {formData.last_name}</span>
              </div>
              <div className="review-item">
                <span className="review-label">Email</span>
                <span className="review-value">{formData.email}</span>
              </div>
              {formData.phone && (
                <div className="review-item">
                  <span className="review-label">Phone</span>
                  <span className="review-value">{formData.phone}</span>
                </div>
              )}
              {formData.department && (
                <div className="review-item">
                  <span className="review-label">Department</span>
                  <span className="review-value">{formData.department}</span>
                </div>
              )}
              {formData.job_title && (
                <div className="review-item">
                  <span className="review-label">Job Title</span>
                  <span className="review-value">{formData.job_title}</span>
                </div>
              )}
            </div>
          </div>

          <div className="review-section">
            <h3>Role & Responsibilities</h3>
            <div className="review-item">
              <span className="review-label">Role</span>
              <span className="review-value">{selectedRole?.display_name || 'None selected'}</span>
            </div>
            <div className="review-item">
              <span className="review-label">Categories</span>
              <div className="review-tags">
                {selectedCats.map(cat => (
                  <span key={cat.id} className="review-tag">{cat.display_name}</span>
                ))}
              </div>
            </div>
            <div className="review-item">
              <span className="review-label">Responsibilities</span>
              <div className="review-tags">
                {selectedResps.map(resp => (
                  <span key={resp.id} className="review-tag small">{resp.display_name}</span>
                ))}
              </div>
            </div>
          </div>

          <div className="review-section">
            <h3>Loan Stage Access</h3>
            <div className="review-item">
              <span className="review-label">Enabled Stages</span>
              <div className="review-tags">
                {formData.stages?.filter(s => s.enabled).map(stage => (
                  <span key={stage.stageCode} className="review-tag">
                    {stage.stageCode === 'lead' ? 'Lead Management' :
                     stage.stageCode === 'active_loan' ? 'Active Loan' :
                     stage.stageCode === 'portfolio' ? 'Portfolio' : stage.stageCode}
                    {stage.templateCode && ` (${stage.templateCode.replace(/_/g, ' ')})`}
                  </span>
                ))}
                {(!formData.stages || formData.stages.filter(s => s.enabled).length === 0) && (
                  <span className="review-value">No stages selected</span>
                )}
              </div>
            </div>
          </div>

          <div className="review-section">
            <h3>Feature Access</h3>
            <div className="review-item">
              <span className="review-label">Enabled Features</span>
              <div className="review-tags">
                {formData.features && Object.entries(formData.features)
                  .filter(([_, enabled]) => enabled)
                  .map(([featureCode]) => (
                    <span key={featureCode} className="review-tag small">
                      {featureCode.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    </span>
                  ))}
                {(!formData.features || Object.values(formData.features).filter(Boolean).length === 0) && (
                  <span className="review-value" style={{ color: '#6B7280', fontStyle: 'italic' }}>
                    No additional features enabled (standard access)
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        {error && <div className="error-message">{error}</div>}

        <div className="wizard-actions">
          <button className="btn-secondary" onClick={prevStep}>Back</button>
          <button
            className="btn-primary"
            onClick={handleCreateUser}
            disabled={loading}
          >
            {loading ? 'Creating User...' : 'Create User & Generate Scorecard'}
          </button>
        </div>
      </div>
    );
  };

  const renderScorecard = () => {
    const scorecard = formData.scorecard;

    return (
      <div className="wizard-content">
        <h2>KPI Scorecard Generated</h2>
        <p className="step-description">
          Based on the assigned responsibilities, we've generated a personalized KPI scorecard for this user.
        </p>

        <div className="scorecard-preview">
          <div className="scorecard-header">
            <h3>{formData.first_name} {formData.last_name}'s Scorecard</h3>
            <span className="scorecard-badge">{scorecard?.kpis?.length || 0} KPIs</span>
          </div>

          <div className="kpi-list">
            {scorecard?.kpis?.map((kpi, index) => (
              <div key={index} className="kpi-item">
                <div className="kpi-header">
                  <h4>{kpi.name}</h4>
                  <span className={`kpi-weight weight-${kpi.weight > 20 ? 'high' : kpi.weight > 10 ? 'medium' : 'low'}`}>
                    {kpi.weight}% weight
                  </span>
                </div>
                <p className="kpi-description">{kpi.description}</p>
                <div className="kpi-targets">
                  <span className="target">
                    <span className="target-label">Target:</span> {kpi.target} {kpi.unit}
                  </span>
                  {kpi.frequency && (
                    <span className="frequency">{kpi.frequency}</span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {(!scorecard?.kpis || scorecard.kpis.length === 0) && (
            <div className="empty-scorecard">
              <p>No KPIs were generated. The user's responsibilities may not have associated KPI definitions yet.</p>
            </div>
          )}
        </div>

        <div className="wizard-actions">
          <button className="btn-secondary" onClick={() => goToStep(STEPS.REVIEW)}>
            Back to Review
          </button>
          <button className="btn-primary" onClick={handleSendActivation} disabled={loading}>
            {loading ? 'Sending...' : 'Send Activation Email'}
          </button>
        </div>
      </div>
    );
  };

  const renderActivation = () => (
    <div className="wizard-content activation-complete">
      <div className="success-icon">✓</div>
      <h2>User Created Successfully!</h2>
      <p className="step-description">
        An activation email has been sent to <strong>{formData.email}</strong>.
      </p>

      <div className="activation-details">
        <div className="detail-item">
          <span className="detail-label">User ID</span>
          <span className="detail-value">{formData.created_user_id}</span>
        </div>
        <div className="detail-item">
          <span className="detail-label">Status</span>
          <span className="detail-value status-pending">Pending Activation</span>
        </div>
        <div className="detail-item">
          <span className="detail-label">Activation Link Expires</span>
          <span className="detail-value">7 days from now</span>
        </div>
      </div>

      <div className="next-steps">
        <h3>Next Steps</h3>
        <ul>
          <li>The user will receive an email with instructions to set their password</li>
          <li>Once activated, they can log in and access their dashboard</li>
          <li>Their KPI scorecard will be available immediately upon login</li>
        </ul>
      </div>

      <div className="wizard-actions centered">
        <button className="btn-secondary" onClick={() => window.location.href = '/users'}>
          Back to Users
        </button>
        <button
          className="btn-primary"
          onClick={() => {
            setCurrentStep(STEPS.BASIC_INFO);
            setFormData({
              first_name: '',
              last_name: '',
              email: '',
              phone: '',
              department: '',
              job_title: '',
              role_id: null,
              selected_categories: [],
              selected_responsibilities: [],
              permission_template_id: null,
              custom_permissions: {},
              selected_features: [],
              scorecard: null,
              created_user_id: null,
              activation_token: null
            });
          }}
        >
          Create Another User
        </button>
      </div>
    </div>
  );

  const renderCurrentStep = () => {
    switch (currentStep) {
      case STEPS.BASIC_INFO:
        return renderBasicInfo();
      case STEPS.ROLE_BUILDER:
        return renderRoleBuilder();
      case STEPS.PERMISSIONS:
        return renderPermissions();
      case STEPS.FEATURES:
        return renderFeatures();
      case STEPS.REVIEW:
        return renderReview();
      case STEPS.SCORECARD:
        return renderScorecard();
      case STEPS.ACTIVATION:
        return renderActivation();
      default:
        return renderBasicInfo();
    }
  };

  if (loading && roles.length === 0) {
    return (
      <div className="user-creation-wizard">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading wizard...</p>
        </div>
      </div>
    );
  }

  // Access denied if user doesn't have user creation permissions
  if (!canCreateUsers) {
    return (
      <div className="user-creation-wizard">
        <div style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to create users.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')} style={{ marginTop: '16px' }}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="user-creation-wizard">
      <div className="wizard-header">
        <h1>Create New User</h1>
        <p>Add a new team member to your organization</p>
      </div>

      {renderStepIndicator()}

      <div className="wizard-body">
        {renderCurrentStep()}
      </div>

      {/* Category Tasks Modal */}
      <CategoryTasksModal
        isOpen={showCategoryTasksModal}
        onClose={() => {
          setShowCategoryTasksModal(false);
          setSelectedCategoryForTasks(null);
        }}
        category={selectedCategoryForTasks}
        selectedRoleId={formData.role_id}
        onTasksChange={() => {
          // Optional: refresh data if needed
        }}
      />
    </div>
  );
}

export default UserCreationWizard;
