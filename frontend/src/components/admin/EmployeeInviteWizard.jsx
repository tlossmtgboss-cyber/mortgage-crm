import React, { useState, useEffect } from 'react';
import api from '../../services/api';
import { toast } from '../../utils/toast';
import './EmployeeInviteWizard.css';

const EmployeeInviteWizard = ({ onComplete, onCancel }) => {
  const [currentStep, setCurrentStep] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [options, setOptions] = useState({ roles: [], branches: [], pages: [], responsibilities: [] });
  const [rolePermissions, setRolePermissions] = useState({ permissions: [], responsibilities: [] });
  const [inviteResult, setInviteResult] = useState(null);
  const [error, setError] = useState(null);

  const [formData, setFormData] = useState({
    // Step 1: Basic Info
    email: '',
    first_name: '',
    last_name: '',
    job_title: '',
    // Step 2: Role & Branch
    permission_role: 'sales',
    branch_id: null,
    // Step 3: Permissions (overrides)
    page_permissions: [],
    // Step 4: Responsibilities
    responsibilities: [],
    // Step 5: Review & Send
    send_email: true,
    custom_message: ''
  });

  const [errors, setErrors] = useState({});

  // Load options on mount
  useEffect(() => {
    loadOptions();
  }, []);

  // Load role permissions when role changes
  useEffect(() => {
    if (formData.permission_role) {
      loadRolePermissions(formData.permission_role);
    }
  }, [formData.permission_role]);

  const loadOptions = async () => {
    try {
      const response = await api.get('/api/user-onboarding/options');
      setOptions(response.data);
    } catch (error) {
      console.error('Error loading options:', error);
    }
  };

  const loadRolePermissions = async (role) => {
    try {
      const response = await api.get(`/api/user-onboarding/permissions-preview/${role}`);
      setRolePermissions(response.data);
    } catch (error) {
      console.error('Error loading role permissions:', error);
    }
  };

  const checkEmailAvailability = async (email) => {
    try {
      const response = await api.get(`/api/admin/users/check-email?email=${encodeURIComponent(email)}`);
      return response.data;
    } catch (error) {
      console.error('Error checking email:', error);
      toast.warning('Could not verify email availability — you may proceed, but the invite may fail if the email is already in use.');
      return { available: true, reason: null };
    }
  };

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: null }));
    }
  };

  const handlePermissionChange = (pageKey, level) => {
    setFormData(prev => {
      const existing = prev.page_permissions.filter(p => p.page_key !== pageKey);
      if (level) {
        return { ...prev, page_permissions: [...existing, { page_key: pageKey, level }] };
      }
      return { ...prev, page_permissions: existing };
    });
  };

  const handleResponsibilityToggle = (respKey) => {
    setFormData(prev => {
      const existing = prev.responsibilities || [];
      if (existing.includes(respKey)) {
        return { ...prev, responsibilities: existing.filter(r => r !== respKey) };
      }
      return { ...prev, responsibilities: [...existing, respKey] };
    });
  };

  const validateStep = async (step) => {
    const newErrors = {};

    if (step === 1) {
      if (!formData.email?.trim()) {
        newErrors.email = 'Email is required';
      } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
        newErrors.email = 'Invalid email format';
      } else {
        const availability = await checkEmailAvailability(formData.email);
        if (!availability.available) {
          newErrors.email = availability.reason;
        }
      }

      if (!formData.first_name?.trim()) {
        newErrors.first_name = 'First name is required';
      }
      if (!formData.last_name?.trim()) {
        newErrors.last_name = 'Last name is required';
      }
    }

    if (step === 2) {
      if (!formData.permission_role) {
        newErrors.permission_role = 'Role is required';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleNext = async () => {
    setIsLoading(true);
    const isValid = await validateStep(currentStep);
    setIsLoading(false);

    if (isValid) {
      setCurrentStep(prev => prev + 1);
    }
  };

  const handleBack = () => {
    setCurrentStep(prev => prev - 1);
  };

  const handleSubmit = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await api.post('/api/admin/users/onboarding', {
        email: formData.email,
        first_name: formData.first_name,
        last_name: formData.last_name,
        job_title: formData.job_title,
        permission_role: formData.permission_role,
        branch_id: formData.branch_id,
        page_permissions: formData.page_permissions,
        responsibilities: formData.responsibilities
      });

      setInviteResult(response.data);
      setCurrentStep(6); // Success step
    } catch (error) {
      console.error('Error creating invite:', error);
      setError(error.response?.data?.detail || 'Failed to create invite. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const copyInviteLink = () => {
    if (inviteResult?.invite_url) {
      navigator.clipboard.writeText(inviteResult.invite_url);
    }
  };

  const stepTitles = [
    'Basic Information',
    'Role & Branch',
    'Page Permissions',
    'Responsibilities',
    'Review & Send',
    'Invite Sent'
  ];

  return (
    <div className="employee-invite-wizard">
      <div className="wizard-header">
        <h2>Invite New Employee</h2>
        <div className="step-indicator">
          {[1, 2, 3, 4, 5].map(step => (
            <div key={step} className={`step-dot ${currentStep >= step ? 'active' : ''} ${currentStep > step ? 'completed' : ''}`}>
              {currentStep > step ? '✓' : step}
            </div>
          ))}
        </div>
        <p className="step-title">{stepTitles[currentStep - 1]}</p>
      </div>

      <div className="wizard-content">
        {/* Step 1: Basic Info */}
        {currentStep === 1 && (
          <div className="wizard-step">
            <div className="form-group">
              <label>Email Address *</label>
              <input
                type="email"
                value={formData.email}
                onChange={(e) => handleChange('email', e.target.value)}
                placeholder="employee@company.com"
                className={errors.email ? 'error' : ''}
              />
              {errors.email && <span className="error-message">{errors.email}</span>}
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>First Name *</label>
                <input
                  type="text"
                  value={formData.first_name}
                  onChange={(e) => handleChange('first_name', e.target.value)}
                  placeholder="John"
                  className={errors.first_name ? 'error' : ''}
                />
                {errors.first_name && <span className="error-message">{errors.first_name}</span>}
              </div>

              <div className="form-group">
                <label>Last Name *</label>
                <input
                  type="text"
                  value={formData.last_name}
                  onChange={(e) => handleChange('last_name', e.target.value)}
                  placeholder="Smith"
                  className={errors.last_name ? 'error' : ''}
                />
                {errors.last_name && <span className="error-message">{errors.last_name}</span>}
              </div>
            </div>

            <div className="form-group">
              <label>Job Title</label>
              <input
                type="text"
                value={formData.job_title}
                onChange={(e) => handleChange('job_title', e.target.value)}
                placeholder="Loan Officer"
              />
            </div>
          </div>
        )}

        {/* Step 2: Role & Branch */}
        {currentStep === 2 && (
          <div className="wizard-step">
            <div className="form-group">
              <label>Permission Role *</label>
              <div className="role-cards">
                {options.roles.map(role => (
                  <div
                    key={role.value}
                    className={`role-card ${formData.permission_role === role.value ? 'selected' : ''}`}
                    onClick={() => handleChange('permission_role', role.value)}
                  >
                    <div className="role-name">{role.label}</div>
                    <div className="role-description">{role.description}</div>
                  </div>
                ))}
              </div>
              {errors.permission_role && <span className="error-message">{errors.permission_role}</span>}
            </div>

            {options.branches.length > 0 && (
              <div className="form-group">
                <label>Branch (Optional)</label>
                <select
                  value={formData.branch_id || ''}
                  onChange={(e) => handleChange('branch_id', e.target.value ? parseInt(e.target.value) : null)}
                >
                  <option value="">No specific branch</option>
                  {options.branches.map(branch => (
                    <option key={branch.id} value={branch.id}>{branch.name}</option>
                  ))}
                </select>
              </div>
            )}

            <div className="role-preview">
              <h4>Default Permissions for {options.roles.find(r => r.value === formData.permission_role)?.label}</h4>
              <p className="preview-note">You can customize these in the next step</p>
              <div className="preview-list">
                {rolePermissions.permissions.slice(0, 5).map(perm => (
                  <span key={perm.page_key} className="preview-badge">
                    {perm.page_key}: {perm.level}
                  </span>
                ))}
                {rolePermissions.permissions.length > 5 && (
                  <span className="preview-badge more">+{rolePermissions.permissions.length - 5} more</span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Step 3: Permissions */}
        {currentStep === 3 && (
          <div className="wizard-step">
            <p className="step-description">
              Customize page access for this employee. Leave unchanged to use role defaults.
            </p>

            <div className="permissions-grid">
              {Object.entries(
                options.pages.reduce((acc, page) => {
                  const cat = page.category || 'Other';
                  if (!acc[cat]) acc[cat] = [];
                  acc[cat].push(page);
                  return acc;
                }, {})
              ).map(([category, pages]) => (
                <div key={category} className="permission-category">
                  <h4>{category}</h4>
                  {pages.map(page => {
                    const roleDefault = rolePermissions.permissions.find(p => p.page_key === page.key);
                    const override = formData.page_permissions.find(p => p.page_key === page.key);
                    const currentLevel = override?.level || roleDefault?.level || 'none';

                    return (
                      <div key={page.key} className="permission-row">
                        <span className="page-label">{page.label}</span>
                        <select
                          value={override ? override.level : ''}
                          onChange={(e) => handlePermissionChange(page.key, e.target.value)}
                          className={override ? 'overridden' : ''}
                        >
                          <option value="">Default ({currentLevel})</option>
                          <option value="none">No Access</option>
                          <option value="read">Read Only</option>
                          <option value="write">Read & Write</option>
                          <option value="admin">Full Admin</option>
                        </select>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Step 4: Responsibilities */}
        {currentStep === 4 && (
          <div className="wizard-step">
            <p className="step-description">
              Select which responsibilities this employee will have.
            </p>

            <div className="responsibilities-grid">
              {Object.entries(
                options.responsibilities.reduce((acc, resp) => {
                  const cat = resp.category || 'Other';
                  if (!acc[cat]) acc[cat] = [];
                  acc[cat].push(resp);
                  return acc;
                }, {})
              ).map(([category, resps]) => (
                <div key={category} className="responsibility-category">
                  <h4>{category}</h4>
                  {resps.map(resp => {
                    const isRoleDefault = rolePermissions.responsibilities.some(r => r.key === resp.key);
                    const isSelected = formData.responsibilities.includes(resp.key);

                    return (
                      <label key={resp.key} className={`responsibility-item ${isRoleDefault ? 'role-default' : ''}`}>
                        <input
                          type="checkbox"
                          checked={isSelected || isRoleDefault}
                          onChange={() => handleResponsibilityToggle(resp.key)}
                          disabled={isRoleDefault}
                        />
                        <span>{resp.label}</span>
                        {isRoleDefault && <span className="default-badge">Role Default</span>}
                      </label>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Step 5: Review */}
        {currentStep === 5 && (
          <div className="wizard-step review-step">
            <div className="review-section">
              <h4>Employee Details</h4>
              <div className="review-grid">
                <div className="review-item">
                  <span className="label">Name</span>
                  <span className="value">{formData.first_name} {formData.last_name}</span>
                </div>
                <div className="review-item">
                  <span className="label">Email</span>
                  <span className="value">{formData.email}</span>
                </div>
                <div className="review-item">
                  <span className="label">Job Title</span>
                  <span className="value">{formData.job_title || 'Not specified'}</span>
                </div>
                <div className="review-item">
                  <span className="label">Role</span>
                  <span className="value">{options.roles.find(r => r.value === formData.permission_role)?.label}</span>
                </div>
                {formData.branch_id && (
                  <div className="review-item">
                    <span className="label">Branch</span>
                    <span className="value">{options.branches.find(b => b.id === formData.branch_id)?.name}</span>
                  </div>
                )}
              </div>
            </div>

            {formData.page_permissions.length > 0 && (
              <div className="review-section">
                <h4>Permission Overrides</h4>
                <div className="override-list">
                  {formData.page_permissions.map(perm => (
                    <span key={perm.page_key} className="override-badge">
                      {perm.page_key}: {perm.level}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {formData.responsibilities.length > 0 && (
              <div className="review-section">
                <h4>Additional Responsibilities</h4>
                <div className="responsibility-list">
                  {formData.responsibilities.map(resp => (
                    <span key={resp} className="responsibility-badge">{resp}</span>
                  ))}
                </div>
              </div>
            )}

            {error && (
              <div className="error-banner">
                {error}
              </div>
            )}
          </div>
        )}

        {/* Step 6: Success */}
        {currentStep === 6 && inviteResult && (
          <div className="wizard-step success-step">
            <div className="success-icon">✓</div>
            <h3>Invite Created Successfully!</h3>
            <p>An invitation has been created for {formData.first_name} {formData.last_name}</p>

            <div className="invite-link-box">
              <label>Invite Link</label>
              <div className="link-container">
                <input type="text" value={inviteResult.invite_url} readOnly />
                <button onClick={copyInviteLink} className="copy-btn">Copy</button>
              </div>
              <p className="expires-note">Expires: {new Date(inviteResult.expires_at).toLocaleDateString()}</p>
            </div>

            <div className="success-actions">
              <button className="btn-secondary" onClick={() => onComplete && onComplete()}>
                Done
              </button>
              <button className="btn-primary" onClick={() => {
                setCurrentStep(1);
                setFormData({
                  email: '', first_name: '', last_name: '', job_title: '',
                  permission_role: 'sales', branch_id: null,
                  page_permissions: [], responsibilities: [],
                  send_email: true, custom_message: ''
                });
                setInviteResult(null);
              }}>
                Invite Another
              </button>
            </div>
          </div>
        )}
      </div>

      {currentStep < 6 && (
        <div className="wizard-footer">
          <button className="btn-cancel" onClick={onCancel}>
            Cancel
          </button>
          <div className="footer-right">
            {currentStep > 1 && (
              <button className="btn-back" onClick={handleBack} disabled={isLoading}>
                Back
              </button>
            )}
            {currentStep < 5 ? (
              <button className="btn-next" onClick={handleNext} disabled={isLoading}>
                {isLoading ? 'Validating...' : 'Next'}
              </button>
            ) : (
              <button className="btn-submit" onClick={handleSubmit} disabled={isLoading}>
                {isLoading ? 'Sending...' : 'Send Invite'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default EmployeeInviteWizard;
