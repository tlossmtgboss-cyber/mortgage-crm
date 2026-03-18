/**
 * AdminOnboarding - Admin Subscription Signup Wizard
 *
 * Quick Start flow for administrators signing up via subscription invitation.
 * 5 Steps: Welcome/Password → Company Profile → Your Profile → Team Invites → Modules → Complete
 * Updated: 2026-01-12 - Fixed token storage, removed industry dropdown
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { loadStripe } from '@stripe/stripe-js';
import { Elements, CardElement, useStripe, useElements } from '@stripe/react-stripe-js';
import {
  validateAdminInvite,
  startAdminOnboarding,
  saveCompanyProfile,
  saveAdminProfile,
  queueTeamInvites,
  createAdminSubscription,
  completeAdminOnboarding
} from '../services/onboardingApi';
import { API_BASE_URL } from '../services/api';
import './AdminOnboarding.css';

// Initialize Stripe only if key is available (prevents IntegrationError on empty key)
const stripePromise = process.env.REACT_APP_STRIPE_PUBLISHABLE_KEY
  ? loadStripe(process.env.REACT_APP_STRIPE_PUBLISHABLE_KEY)
  : Promise.resolve(null);

// Timezone options
const TIMEZONES = [
  { value: 'America/New_York', label: 'Eastern Time (ET)' },
  { value: 'America/Chicago', label: 'Central Time (CT)' },
  { value: 'America/Denver', label: 'Mountain Time (MT)' },
  { value: 'America/Los_Angeles', label: 'Pacific Time (PT)' },
  { value: 'America/Phoenix', label: 'Arizona Time' },
  { value: 'America/Anchorage', label: 'Alaska Time' },
  { value: 'Pacific/Honolulu', label: 'Hawaii Time' }
];

// Default role options for team invites (will be replaced by API data)
const DEFAULT_TEAM_ROLES = [
  { value: 'loan_officer', label: 'Loan Officer' },
  { value: 'processor', label: 'Processor' },
  { value: 'underwriter', label: 'Underwriter' },
  { value: 'closer', label: 'Closer' },
  { value: 'admin', label: 'Admin Staff' },
  { value: 'manager', label: 'Manager' }
];

// Phone number formatting utility
const formatPhoneNumber = (value) => {
  if (!value) return value;
  const phoneNumber = value.replace(/[^\d]/g, '');
  const phoneNumberLength = phoneNumber.length;
  if (phoneNumberLength < 4) return phoneNumber;
  if (phoneNumberLength < 7) {
    return `(${phoneNumber.slice(0, 3)}) ${phoneNumber.slice(3)}`;
  }
  return `(${phoneNumber.slice(0, 3)}) ${phoneNumber.slice(3, 6)}-${phoneNumber.slice(6, 10)}`;
};

function AdminOnboarding() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const inviteToken = searchParams.get('invite');
  const urlPromoCode = searchParams.get('promo');

  // Wizard state
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  // Invitation data
  const [invitation, setInvitation] = useState(null);

  // Promo code validation state (validated server-side only)
  const [promoValidated, setPromoValidated] = useState(false);

  // Step 1: Welcome/Password
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [passwordStrength, setPasswordStrength] = useState({ score: 0, feedback: [] });

  // Step 2: Company Profile
  const [companyName, setCompanyName] = useState('');
  const [companyPhone, setCompanyPhone] = useState('');
  const [companyAddress, setCompanyAddress] = useState('');
  const [logoUrl, setLogoUrl] = useState('');

  // Step 3: Your Profile
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [jobTitle, setJobTitle] = useState('');
  const [phone, setPhone] = useState('');
  const [nmlsNumber, setNmlsNumber] = useState('');
  const [timezone, setTimezone] = useState('America/New_York');
  const [headshotUrl, setHeadshotUrl] = useState('');

  // Step 4: Team Invites
  const [teamInvites, setTeamInvites] = useState([]);
  const [newInvite, setNewInvite] = useState({ email: '', role: 'loan_officer', first_name: '', last_name: '' });
  const [teamRoles, setTeamRoles] = useState(DEFAULT_TEAM_ROLES);
  const [rolesLoading, setRolesLoading] = useState(false);

  // Step 5: Module Selection
  const [availableModules, setAvailableModules] = useState([]);
  const [selectedModules, setSelectedModules] = useState([]);
  const [modulesLoading, setModulesLoading] = useState(false);

  // Fetch available roles for team invites
  const fetchTeamRoles = useCallback(async () => {
    setRolesLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/admin-onboarding/available-roles`);
      if (response.ok) {
        const data = await response.json();
        if (data.data?.roles && data.data.roles.length > 0) {
          setTeamRoles(data.data.roles.map(role => ({
            value: role.value,
            label: role.name,
            description: role.description
          })));
        }
      }
    } catch (err) {
      console.error('Failed to fetch roles:', err);
      // Keep default roles on error
    } finally {
      setRolesLoading(false);
    }
  }, []);

  // Fetch available modules when entering step 4
  const fetchModules = useCallback(async () => {
    setModulesLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/modules/public/list`);
      if (response.ok) {
        const modules = await response.json();
        setAvailableModules(modules);
      }
    } catch (err) {
      console.error('Failed to fetch modules:', err);
      // Fallback module data
      setAvailableModules([
        { module_key: 'ai_assistant', module_name: 'AI Assistant', description: 'AI-powered underwriting, chat, and email assistance', monthly_price: 149, icon: '🤖', included_features: ['ai_underwriter', 'ai_chat', 'email_training'] },
        { module_key: 'partner_portals', module_name: 'Partner Portals', description: 'Realtor portal, listing portal, and personalized URLs', monthly_price: 99, icon: '🤝', included_features: ['realtor_portal', 'listing_portal', 'purl'] },
        { module_key: 'video_os', module_name: 'Video OS', description: 'Create personalized videos with AI avatars', monthly_price: 79, icon: '🎬', included_features: ['video_creation', 'ai_avatars', 'templates'] },
        // { module_key: 'recruiting_suite', module_name: 'Recruiting Suite', description: 'Full recruiting pipeline with DISC assessments', monthly_price: 199, icon: '👥', included_features: ['candidates', 'disc_assessment', 'onboarding'] },  // DEPRECATED: Premium feature deregistered — not yet launched
        { module_key: 'conversation_intelligence', module_name: 'Conversation Intelligence', description: 'Call recording, transcription, and QA scoring', monthly_price: 129, icon: '📞', included_features: ['call_recording', 'transcription', 'qa_scoring'] },
        { module_key: 'advanced_analytics', module_name: 'Advanced Analytics', description: 'Profitability analysis and market insights', monthly_price: 149, icon: '📊', included_features: [/* 'decision_lab', */ 'profitability', 'market_data'] }, // DEPRECATED: decision_lab experimental feature deregistered
        { module_key: 'integrations', module_name: 'Integrations', description: 'Connect to Salesforce, HubSpot, Encompass and more', monthly_price: 79, icon: '🔗', included_features: ['salesforce', 'hubspot', 'encompass'] },
      ]);
    } finally {
      setModulesLoading(false);
    }
  }, []);

  // Toggle module selection
  const toggleModule = (moduleKey) => {
    setSelectedModules(prev => {
      if (prev.includes(moduleKey)) {
        return prev.filter(k => k !== moduleKey);
      }
      return [...prev, moduleKey];
    });
  };

  // Calculate module pricing
  const calculateModuleTotal = useCallback(() => {
    const basePrice = 99; // Base package
    const modulePrice = selectedModules.reduce((total, key) => {
      const mod = availableModules.find(m => m.module_key === key);
      return total + (mod?.monthly_price || 0);
    }, 0);
    return { basePrice, modulePrice, total: basePrice + modulePrice };
  }, [selectedModules, availableModules]);

  // Step 6: Payment
  const [paymentProcessing, setPaymentProcessing] = useState(false);
  const [paymentComplete, setPaymentComplete] = useState(false);
  const [billingAddress, setBillingAddress] = useState({ line1: '', city: '', state: '', postal_code: '' });
  // Initialize promo code from URL parameter (if present)
  const [promoCode, setPromoCode] = useState(urlPromoCode || '');

  // Whether server has confirmed this promo code grants free access
  const isFreeAccess = promoValidated;

  // Step 7: Complete
  const [completionData, setCompletionData] = useState(null);

  const STEPS = [
    { id: 0, name: 'Welcome', title: 'Welcome & Set Password' },
    { id: 1, name: 'Company', title: 'Company Profile' },
    { id: 2, name: 'Profile', title: 'Your Profile' },
    { id: 3, name: 'Team', title: 'Invite Your Team' },
    { id: 4, name: 'Modules', title: 'Choose Your Modules' },
    { id: 5, name: 'Payment', title: 'Payment' },
    { id: 6, name: 'Complete', title: 'Setup Complete!' }
  ];

  // Validate invitation on mount
  useEffect(() => {
    const validateInvitation = async () => {
      if (!inviteToken) {
        setError('No invitation token provided. Please use the link from your invitation email.');
        setLoading(false);
        return;
      }

      try {
        const result = await validateAdminInvite(inviteToken);
        if (!result.valid) {
          setError(result.error || 'Invalid or expired invitation');
          setLoading(false);
          return;
        }

        setInvitation(result);
        setCompanyName(result.company_name || '');
        setLoading(false);
      } catch (err) {
        setError('Failed to validate invitation. Please try again.');
        setLoading(false);
      }
    };

    validateInvitation();
  }, [inviteToken]);

  // Fetch team roles when entering team invites step
  useEffect(() => {
    if (currentStep === 3) {
      fetchTeamRoles();
    }
  }, [currentStep, fetchTeamRoles]);

  // Password strength checker
  useEffect(() => {
    const checkPasswordStrength = () => {
      const feedback = [];
      let score = 0;

      if (password.length >= 8) score++;
      else feedback.push('At least 8 characters');

      if (/[A-Z]/.test(password)) score++;
      else feedback.push('One uppercase letter');

      if (/[a-z]/.test(password)) score++;
      else feedback.push('One lowercase letter');

      if (/[0-9]/.test(password)) score++;
      else feedback.push('One number');

      if (/[^A-Za-z0-9]/.test(password)) score++;
      else feedback.push('One special character (optional)');

      setPasswordStrength({ score, feedback });
    };

    if (password) {
      checkPasswordStrength();
    } else {
      setPasswordStrength({ score: 0, feedback: [] });
    }
  }, [password]);

  // Step handlers
  const handleStep1Submit = async () => {
    setError('');

    if (!password || password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    if (passwordStrength.score < 4) {
      setError('Password is too weak. Please include uppercase, lowercase, and numbers.');
      return;
    }
    if (!acceptTerms) {
      setError('Please accept the terms of service');
      return;
    }

    setSaving(true);
    try {
      const result = await startAdminOnboarding({
        invite_token: inviteToken,
        email: invitation.email,
        password: password,
        accept_terms: true
      });

      // Store the access token for subsequent API calls
      if (result.data?.access_token) {
        localStorage.setItem('token', result.data.access_token);
      } else if (result.data?.token) {
        localStorage.setItem('token', result.data.token);
      }

      setCurrentStep(1);
    } catch (err) {
      setError(err.message || 'Failed to create account');
    } finally {
      setSaving(false);
    }
  };

  const handleStep2Submit = async () => {
    setError('');

    if (!companyName || companyName.length < 2) {
      setError('Company name is required');
      return;
    }

    setSaving(true);
    try {
      await saveCompanyProfile({
        company_name: companyName,
        company_phone: companyPhone || null,
        company_address: companyAddress || null,
        logo_url: logoUrl || null
      });
      setCurrentStep(2);
    } catch (err) {
      setError(err.message || 'Failed to save company profile');
    } finally {
      setSaving(false);
    }
  };

  const handleStep3Submit = async () => {
    setError('');

    if (!firstName || !lastName) {
      setError('First name and last name are required');
      return;
    }

    setSaving(true);
    try {
      await saveAdminProfile({
        first_name: firstName,
        last_name: lastName,
        job_title: jobTitle || null,
        phone: phone || null,
        nmls_number: nmlsNumber || null,
        timezone: timezone,
        headshot_url: headshotUrl || null
      });
      setCurrentStep(3);
    } catch (err) {
      setError(err.message || 'Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  const handleAddTeamInvite = () => {
    if (!newInvite.email) {
      setError('Email is required');
      return;
    }
    if (teamInvites.find(t => t.email === newInvite.email)) {
      setError('This email is already added');
      return;
    }
    if (teamInvites.length >= (invitation?.seats || 10) - 1) {
      setError(`You've reached the maximum of ${invitation?.seats - 1} team members`);
      return;
    }

    setTeamInvites([...teamInvites, { ...newInvite, id: Date.now() }]);
    setNewInvite({ email: '', role: 'loan_officer', first_name: '', last_name: '' });
    setError('');
  };

  const handleRemoveTeamInvite = (id) => {
    setTeamInvites(teamInvites.filter(t => t.id !== id));
  };

  const handleStep4Submit = async (skip = false) => {
    setSaving(true);
    try {
      await queueTeamInvites({
        invites: skip ? [] : teamInvites.map(({ email, role, first_name, last_name }) => ({
          email, role, first_name, last_name
        })),
        skip: skip
      });
      // Fetch modules before moving to module selection step
      fetchModules();
      setCurrentStep(4);
    } catch (err) {
      setError(err.message || 'Failed to save team invites');
    } finally {
      setSaving(false);
    }
  };

  // Handle module selection step submit
  const handleStep5Submit = () => {
    // Move to payment step - modules are already saved in state
    setCurrentStep(5);
  };

  const handleGoBack = () => {
    if (currentStep > 0 && currentStep < 6) {
      setCurrentStep(currentStep - 1);
    }
  };

  // Loading screen
  if (loading) {
    return (
      <div className="admin-onboarding">
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Validating your invitation...</p>
        </div>
      </div>
    );
  }

  // Error screen (no valid invitation)
  if (error && !invitation) {
    return (
      <div className="admin-onboarding">
        <div className="error-container">
          <div className="error-icon">!</div>
          <h2>Unable to Access Signup</h2>
          <p>{error}</p>
          <button onClick={() => navigate('/login')} className="btn-primary">
            Go to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-onboarding">
      {/* Header */}
      <header className="onboarding-header">
        <div className="logo">
          <span className="logo-text">Perennia</span>
          <span className="logo-ai">AI</span>
        </div>
        {currentStep < 6 && (
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${((currentStep + 1) / STEPS.length) * 100}%` }}
            ></div>
          </div>
        )}
      </header>

      {/* Steps indicator */}
      {currentStep < 6 && (
        <nav className="steps-nav">
          {STEPS.slice(0, -1).map((step, index) => (
            <div
              key={step.id}
              className={`step-indicator ${index === currentStep ? 'active' : ''} ${index < currentStep ? 'completed' : ''}`}
            >
              <div className="step-number">
                {index < currentStep ? '✓' : index + 1}
              </div>
              <span className="step-name">{step.name}</span>
            </div>
          ))}
        </nav>
      )}

      {/* Step content */}
      <main className="step-content">
        {error && currentStep < 6 && (
          <div className="error-banner">
            {error}
            <button onClick={() => setError('')} className="dismiss">×</button>
          </div>
        )}

        {/* Step 1: Welcome & Password */}
        {currentStep === 0 && (
          <div className="step-panel welcome-step">
            <div className="step-header">
              <h1>Welcome to Perennia AI</h1>
              <p>Let's get your account set up in just a few minutes.</p>
            </div>

            <div className="plan-card">
              <div className="plan-badge">{invitation?.plan || 'Professional'}</div>
              <div className="plan-details">
                <span className="company-name">{invitation?.company_name}</span>
                <span className="plan-seats">{invitation?.seats || 10} seats included</span>
              </div>
            </div>

            <form onSubmit={(e) => { e.preventDefault(); handleStep1Submit(); }}>
              <div className="form-group">
                <label>Email Address</label>
                <input type="email" value={invitation?.email || ''} disabled className="input-disabled" />
              </div>

              <div className="form-group">
                <label>Create Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter a strong password"
                  autoComplete="new-password"
                />
                {password && (
                  <div className="password-strength">
                    <div className="strength-bar">
                      <div
                        className={`strength-fill strength-${passwordStrength.score}`}
                        style={{ width: `${(passwordStrength.score / 5) * 100}%` }}
                      ></div>
                    </div>
                    {passwordStrength.feedback.length > 0 && (
                      <div className="strength-feedback">
                        Need: {passwordStrength.feedback.join(', ')}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="form-group">
                <label>Confirm Password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm your password"
                  autoComplete="new-password"
                />
                {confirmPassword && password !== confirmPassword && (
                  <div className="validation-error">Passwords don't match</div>
                )}
              </div>

              <div className="form-group checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={acceptTerms}
                    onChange={(e) => setAcceptTerms(e.target.checked)}
                  />
                  <span>I accept the <a href="/terms" target="_blank">Terms of Service</a> and <a href="/privacy" target="_blank">Privacy Policy</a></span>
                </label>
              </div>

              <button type="submit" className="btn-primary btn-full" disabled={saving}>
                {saving ? 'Creating Account...' : 'Continue'}
              </button>
            </form>
          </div>
        )}

        {/* Step 2: Company Profile */}
        {currentStep === 1 && (
          <div className="step-panel company-step">
            <div className="step-header">
              <h1>Company Profile</h1>
              <p>Tell us about your organization.</p>
            </div>

            <form onSubmit={(e) => { e.preventDefault(); handleStep2Submit(); }}>
              <div className="form-group">
                <label>Company Name *</label>
                <input
                  type="text"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="Your company name"
                />
              </div>

              <div className="form-group">
                <label>Company Phone</label>
                <input
                  type="tel"
                  value={companyPhone}
                  onChange={(e) => setCompanyPhone(formatPhoneNumber(e.target.value))}
                  placeholder="(555) 555-5555"
                  maxLength={14}
                />
              </div>

              <div className="form-group">
                <label>Company Address (Optional)</label>
                <input
                  type="text"
                  value={companyAddress}
                  onChange={(e) => setCompanyAddress(e.target.value)}
                  placeholder="123 Main St, City, State ZIP"
                />
              </div>

              <div className="form-group">
                <label>Company Logo (Optional)</label>
                <div className="logo-upload">
                  {logoUrl ? (
                    <div className="logo-preview">
                      <img src={logoUrl} alt="Company logo" />
                      <button type="button" onClick={() => setLogoUrl('')}>Remove</button>
                    </div>
                  ) : (
                    <div className="upload-placeholder">
                      <span>Drag & drop or click to upload</span>
                      <input
                        type="file"
                        accept="image/*"
                        onChange={(e) => {
                          // For now, just use a placeholder. Real implementation would upload to S3
                          if (e.target.files?.[0]) {
                            setLogoUrl(URL.createObjectURL(e.target.files[0]));
                          }
                        }}
                      />
                    </div>
                  )}
                </div>
              </div>

              <div className="button-row">
                <button type="button" className="btn-secondary" onClick={handleGoBack}>
                  Back
                </button>
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? 'Saving...' : 'Continue'}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Step 3: Your Profile */}
        {currentStep === 2 && (
          <div className="step-panel profile-step">
            <div className="step-header">
              <h1>Your Profile</h1>
              <p>Tell us a bit about yourself.</p>
            </div>

            <form onSubmit={(e) => { e.preventDefault(); handleStep3Submit(); }}>
              <div className="form-row">
                <div className="form-group">
                  <label>First Name *</label>
                  <input
                    type="text"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    placeholder="First name"
                  />
                </div>

                <div className="form-group">
                  <label>Last Name *</label>
                  <input
                    type="text"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    placeholder="Last name"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Job Title</label>
                  <input
                    type="text"
                    value={jobTitle}
                    onChange={(e) => setJobTitle(e.target.value)}
                    placeholder="e.g., Branch Manager"
                  />
                </div>

                <div className="form-group">
                  <label>Phone Number</label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(formatPhoneNumber(e.target.value))}
                    placeholder="(555) 555-5555"
                    maxLength={14}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>NMLS Number</label>
                  <input
                    type="text"
                    value={nmlsNumber}
                    onChange={(e) => setNmlsNumber(e.target.value)}
                    placeholder="NMLS #"
                  />
                </div>

                <div className="form-group">
                  <label>Timezone</label>
                  <select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
                    {TIMEZONES.map(tz => (
                      <option key={tz.value} value={tz.value}>{tz.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="button-row">
                <button type="button" className="btn-secondary" onClick={handleGoBack}>
                  Back
                </button>
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? 'Saving...' : 'Continue'}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Step 4: Team Invites */}
        {currentStep === 3 && (
          <div className="step-panel team-step">
            <div className="step-header">
              <h1>Invite Your Team</h1>
              <p>Add team members now or invite them later from Settings.</p>
              <div className="seats-info">
                <span className="seats-used">{teamInvites.length}</span>
                <span className="seats-divider">/</span>
                <span className="seats-total">{(invitation?.seats || 10) - 1}</span>
                <span className="seats-label">seats used</span>
              </div>
            </div>

            <div className="invite-form">
              <div className="form-row">
                <div className="form-group flex-2">
                  <label>Email *</label>
                  <input
                    type="email"
                    value={newInvite.email}
                    onChange={(e) => setNewInvite({...newInvite, email: e.target.value})}
                    placeholder="team@example.com"
                  />
                </div>
                <div className="form-group flex-1">
                  <label>Role</label>
                  <select
                    value={newInvite.role}
                    onChange={(e) => setNewInvite({...newInvite, role: e.target.value})}
                    disabled={rolesLoading}
                  >
                    {rolesLoading ? (
                      <option>Loading roles...</option>
                    ) : (
                      teamRoles.map(role => (
                        <option key={role.value} value={role.value}>{role.label}</option>
                      ))
                    )}
                  </select>
                </div>
                <div className="form-group btn-col">
                  <button type="button" className="btn-add" onClick={handleAddTeamInvite}>
                    + Add
                  </button>
                </div>
              </div>
            </div>

            {teamInvites.length > 0 && (
              <div className="team-list">
                {teamInvites.map(invite => (
                  <div key={invite.id} className="team-member">
                    <div className="member-info">
                      <span className="member-email">{invite.email}</span>
                      <span className="member-role">{teamRoles.find(r => r.value === invite.role)?.label || invite.role}</span>
                    </div>
                    <button
                      type="button"
                      className="btn-remove"
                      onClick={() => handleRemoveTeamInvite(invite.id)}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="button-row">
              <button type="button" className="btn-secondary" onClick={handleGoBack}>
                Back
              </button>
              <button
                type="button"
                className="btn-text"
                onClick={() => handleStep4Submit(true)}
                disabled={saving}
              >
                Skip for now
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={() => handleStep4Submit(false)}
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Continue'}
              </button>
            </div>
          </div>
        )}

        {/* Step 5: Module Selection */}
        {currentStep === 4 && (
          <div className="step-panel modules-step">
            <div className="step-header">
              <h1>Choose Your Modules</h1>
              <p>Start with the essentials and add premium features as needed.</p>
            </div>

            {/* Base Package - Always Included */}
            <div className="base-package">
              <div className="package-header">
                <div className="package-badge included">Included</div>
                <h3>Core CRM</h3>
                <div className="package-price">$99<span>/month</span></div>
              </div>
              <div className="package-features">
                <span>Lead Management</span>
                <span>Active Loans</span>
                <span>Portfolio</span>
                <span>Tasks</span>
                <span>Smart Docs</span>
                <span>Calendar</span>
              </div>
            </div>

            {/* Premium Modules */}
            <div className="modules-section">
              <h3>Premium Add-Ons</h3>
              <p className="modules-hint">Select modules to customize your experience</p>

              {modulesLoading ? (
                <div className="modules-loading">
                  <div className="loading-spinner"></div>
                  <p>Loading available modules...</p>
                </div>
              ) : (
                <div className="modules-grid">
                  {availableModules.filter(m => m.module_key !== 'base').map(module => (
                    <div
                      key={module.module_key}
                      className={`module-card ${selectedModules.includes(module.module_key) ? 'selected' : ''}`}
                      onClick={() => toggleModule(module.module_key)}
                    >
                      <div className="module-checkbox">
                        {selectedModules.includes(module.module_key) ? '✓' : ''}
                      </div>
                      <div className="module-icon">{module.icon}</div>
                      <div className="module-info">
                        <h4>{module.module_name}</h4>
                        <p>{module.description}</p>
                        <div className="module-features">
                          {module.included_features?.slice(0, 3).map((f, i) => (
                            <span key={i} className="feature-tag">{f.replace(/_/g, ' ')}</span>
                          ))}
                        </div>
                      </div>
                      <div className="module-price">
                        +${module.monthly_price}<span>/mo</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Pricing Summary */}
            <div className="pricing-summary">
              <div className="summary-row">
                <span>Core CRM (base)</span>
                <span>${calculateModuleTotal().basePrice}/mo</span>
              </div>
              {selectedModules.length > 0 && (
                <div className="summary-row">
                  <span>Premium Modules ({selectedModules.length})</span>
                  <span>+${calculateModuleTotal().modulePrice}/mo</span>
                </div>
              )}
              <div className="summary-row total">
                <span>Total</span>
                <span>${calculateModuleTotal().total}/month</span>
              </div>
            </div>

            <div className="button-row">
              <button type="button" className="btn-secondary" onClick={handleGoBack}>
                Back
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={handleStep5Submit}
              >
                Continue to Payment
              </button>
            </div>
          </div>
        )}

        {/* Step 6: Payment */}
        {currentStep === 5 && (
          <Elements stripe={stripePromise}>
            <PaymentStep
              invitation={invitation}
              teamInvites={teamInvites}
              selectedModules={selectedModules}
              availableModules={availableModules}
              billingAddress={billingAddress}
              setBillingAddress={setBillingAddress}
              promoCode={promoCode}
              setPromoCode={setPromoCode}
              promoValidated={promoValidated}
              setPromoValidated={setPromoValidated}
              isFreeAccess={isFreeAccess}
              onBack={handleGoBack}
              onComplete={(data) => {
                setPaymentComplete(true);
                setCompletionData(data);
                setCurrentStep(6);
              }}
              onError={setError}
            />
          </Elements>
        )}

        {/* Step 7: Complete */}
        {currentStep === 6 && (
          <div className="step-panel complete-step">
            <div className="success-animation">
              <div className="checkmark">✓</div>
            </div>

            <div className="step-header">
              <h1>You're All Set!</h1>
              <p>Your account is ready to go.</p>
            </div>

            <div className="completion-summary">
              <div className="summary-item">
                <span className="summary-icon">🏢</span>
                <span className="summary-text">{companyName} account created</span>
              </div>
              {teamInvites.length > 0 && (
                <div className="summary-item">
                  <span className="summary-icon">📧</span>
                  <span className="summary-text">{teamInvites.length} team invite{teamInvites.length > 1 ? 's' : ''} sent</span>
                </div>
              )}
              <div className="summary-item">
                <span className="summary-icon">✅</span>
                <span className="summary-text">{invitation?.plan} plan activated</span>
              </div>
            </div>

            <div className="whats-next">
              <h3>What's Next?</h3>
              <div className="next-cards">
                <a href="/settings/integrations" className="next-card">
                  <span className="card-icon">🔗</span>
                  <span className="card-title">Connect Integrations</span>
                  <span className="card-desc">Link your email, calendar & CRM</span>
                </a>
                <a href="/leads/import" className="next-card">
                  <span className="card-icon">📥</span>
                  <span className="card-title">Import Leads</span>
                  <span className="card-desc">Bring in your existing data</span>
                </a>
                <a href="/ai/assistant" className="next-card">
                  <span className="card-icon">🤖</span>
                  <span className="card-title">Explore AI Features</span>
                  <span className="card-desc">See what Perennia can do</span>
                </a>
              </div>
            </div>

            <button
              className="btn-primary btn-large"
              onClick={() => navigate('/dashboard')}
            >
              Go to Dashboard
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

// Payment Step Component (uses Stripe hooks)
function PaymentStep({
  invitation,
  teamInvites,
  selectedModules = [],
  availableModules = [],
  billingAddress,
  setBillingAddress,
  promoCode,
  setPromoCode,
  promoValidated = false,
  setPromoValidated,
  isFreeAccess = false,
  onBack,
  onComplete,
  onError
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [processing, setProcessing] = useState(false);
  const [cardComplete, setCardComplete] = useState(false);

  // Calculate pricing based on base + selected modules
  const basePrice = 99; // Core CRM base price
  const modulesPrice = selectedModules.reduce((total, key) => {
    const mod = availableModules.find(m => m.module_key === key);
    return total + (mod?.monthly_price || 0);
  }, 0);
  const totalPrice = isFreeAccess ? 0 : basePrice + modulesPrice;

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!stripe || !elements) {
      onError('Payment system not loaded. Please refresh and try again.');
      return;
    }

    setProcessing(true);
    onError('');

    try {
      // Create payment method
      const cardElement = elements.getElement(CardElement);
      const { error, paymentMethod } = await stripe.createPaymentMethod({
        type: 'card',
        card: cardElement,
        billing_details: {
          address: {
            line1: billingAddress.line1,
            city: billingAddress.city,
            state: billingAddress.state,
            postal_code: billingAddress.postal_code,
            country: 'US'
          }
        }
      });

      if (error) {
        onError(error.message);
        setProcessing(false);
        return;
      }

      // Create subscription with selected modules
      const result = await createAdminSubscription({
        payment_method_id: paymentMethod.id,
        billing_address: billingAddress,
        promo_code: promoCode || null,
        selected_modules: selectedModules
      });

      // Complete onboarding
      await completeAdminOnboarding();

      onComplete(result.data);
    } catch (err) {
      onError(err.message || 'Payment failed. Please try again.');
    } finally {
      setProcessing(false);
    }
  };

  // Demo mode - skip payment in development
  const handleDemoComplete = async () => {
    setProcessing(true);
    try {
      await createAdminSubscription({
        payment_method_id: 'demo_mode',
        billing_address: {},
        promo_code: null,
        selected_modules: selectedModules
      });
      await completeAdminOnboarding();
      onComplete({ demo: true });
    } catch (err) {
      onError(err.message);
    } finally {
      setProcessing(false);
    }
  };

  // Free access mode - bypass payment with promo code
  const handleFreeAccessComplete = async () => {
    setProcessing(true);
    onError('');
    try {
      await createAdminSubscription({
        payment_method_id: 'free_access_promo',
        billing_address: {},
        promo_code: promoCode,
        selected_modules: selectedModules
      });
      await completeAdminOnboarding();
      onComplete({ freeAccess: true, promoCode });
    } catch (err) {
      onError(err.message || 'Failed to activate free access. Please try again.');
    } finally {
      setProcessing(false);
    }
  };

  // If user has free access, show simplified activation UI
  if (isFreeAccess) {
    return (
      <div className="step-panel payment-step">
        <div className="step-header">
          <h1>Activate Your Free Business Plan</h1>
          <p>Your promo code has been applied!</p>
        </div>

        <div className="free-access-card" style={{
          background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
          borderRadius: '16px',
          padding: '32px',
          color: 'white',
          textAlign: 'center',
          marginBottom: '32px'
        }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>🎉</div>
          <h2 style={{ margin: '0 0 8px 0', fontSize: '24px' }}>Free Business Plan Access</h2>
          <p style={{ margin: 0, opacity: 0.9 }}>
            Promo code <strong>{promoCode}</strong> applied successfully!
          </p>
          <div style={{ marginTop: '24px', padding: '16px', background: 'rgba(255,255,255,0.2)', borderRadius: '12px' }}>
            <div style={{ fontSize: '32px', fontWeight: 'bold' }}>$0/month</div>
            <div style={{ opacity: 0.9, fontSize: '14px' }}>Full Business Plan - No Payment Required</div>
          </div>
        </div>

        <div className="included-features" style={{ marginBottom: '32px' }}>
          <h3 style={{ marginBottom: '16px' }}>What's Included:</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
            {['Full CRM Platform', 'AI Assistant', 'Advanced Automation', 'Unlimited Leads', 'Email Integration', 'Team Collaboration'].map(feature => (
              <div key={feature} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ color: '#10b981' }}>✓</span>
                <span>{feature}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="button-row">
          <button type="button" className="btn-secondary" onClick={onBack} disabled={processing}>
            Back
          </button>
          <button
            type="button"
            className="btn-primary btn-pay"
            onClick={handleFreeAccessComplete}
            disabled={processing}
            style={{ background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)' }}
          >
            {processing ? 'Activating...' : 'Activate Free Access'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="step-panel payment-step">
      <div className="step-header">
        <h1>Complete Your Subscription</h1>
        <p>Secure payment powered by Stripe</p>
      </div>

      <div className="payment-layout">
        <div className="payment-form">
          <form onSubmit={handleSubmit}>
            <div className="form-section">
              <h3>Promo Code (Optional)</h3>
              <div className="promo-input" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <input
                  type="text"
                  placeholder="Enter code"
                  value={promoCode}
                  onChange={(e) => { setPromoCode(e.target.value.toUpperCase()); setPromoValidated(false); }}
                />
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ whiteSpace: 'nowrap' }}
                  disabled={!promoCode || processing}
                  onClick={async () => {
                    try {
                      const token = localStorage.getItem('token');
                      const resp = await fetch(`${API_BASE_URL}/api/v1/admin-onboarding/validate-promo`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                        body: JSON.stringify({ promo_code: promoCode })
                      });
                      const data = await resp.json();
                      if (resp.ok && data.data?.valid) {
                        setPromoValidated(true);
                        onError('');
                      } else {
                        setPromoValidated(false);
                        onError(data.data?.message || 'Invalid promo code');
                      }
                    } catch { setPromoValidated(false); onError('Failed to validate promo code'); }
                  }}
                >
                  Apply
                </button>
                {promoValidated && <span style={{ color: '#10b981', fontWeight: 'bold' }}>Valid - No payment required!</span>}
              </div>
            </div>

            {!promoValidated && (
              <>
                <div className="form-section">
                  <h3>Card Information</h3>
                  <div className="card-element-container">
                    <CardElement
                      options={{
                        style: {
                          base: {
                            fontSize: '16px',
                            color: '#424770',
                            '::placeholder': { color: '#aab7c4' }
                          },
                          invalid: { color: '#9e2146' }
                        }
                      }}
                      onChange={(e) => setCardComplete(e.complete)}
                    />
                  </div>
                </div>

                <div className="form-section">
                  <h3>Billing Address</h3>
                  <div className="form-group">
                    <input
                      type="text"
                      placeholder="Street Address"
                      value={billingAddress.line1}
                      onChange={(e) => setBillingAddress({...billingAddress, line1: e.target.value})}
                    />
                  </div>
                  <div className="form-row">
                    <div className="form-group">
                      <input
                        type="text"
                        placeholder="City"
                        value={billingAddress.city}
                        onChange={(e) => setBillingAddress({...billingAddress, city: e.target.value})}
                      />
                    </div>
                    <div className="form-group">
                      <input
                        type="text"
                        placeholder="State"
                        value={billingAddress.state}
                        onChange={(e) => setBillingAddress({...billingAddress, state: e.target.value})}
                        maxLength={2}
                      />
                    </div>
                    <div className="form-group">
                      <input
                        type="text"
                        placeholder="ZIP"
                        value={billingAddress.postal_code}
                        onChange={(e) => setBillingAddress({...billingAddress, postal_code: e.target.value})}
                        maxLength={10}
                      />
                    </div>
                  </div>
                </div>
              </>
            )}

            <div className="button-row">
              <button type="button" className="btn-secondary" onClick={onBack} disabled={processing}>
                Back
              </button>
              {promoValidated ? (
                <button
                  type="button"
                  className="btn-primary btn-pay"
                  onClick={handleFreeAccessComplete}
                  disabled={processing}
                  style={{ background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)' }}
                >
                  {processing ? 'Activating...' : 'Activate Free Access'}
                </button>
              ) : (
                <button
                  type="submit"
                  className="btn-primary btn-pay"
                  disabled={processing || !stripe || !cardComplete}
                >
                  {processing ? 'Processing...' : `Pay $${totalPrice}/month`}
                </button>
              )}
            </div>
          </form>

          {/* Demo mode option */}
          {(!stripe || !process.env.REACT_APP_STRIPE_PUBLISHABLE_KEY) && (
            <div className="demo-mode">
              <p>Stripe not configured. Use demo mode?</p>
              <button
                type="button"
                className="btn-demo"
                onClick={handleDemoComplete}
                disabled={processing}
              >
                Continue in Demo Mode
              </button>
            </div>
          )}
        </div>

        <div className="order-summary">
          <h3>Order Summary</h3>
          <div className="summary-line">
            <span>Core CRM (Base)</span>
            <span>${basePrice}/mo</span>
          </div>
          {selectedModules.length > 0 && (
            <>
              <div className="summary-divider">Premium Modules</div>
              {selectedModules.map(key => {
                const mod = availableModules.find(m => m.module_key === key);
                return mod ? (
                  <div key={key} className="summary-line module-line">
                    <span>{mod.module_name}</span>
                    <span>+${mod.monthly_price}/mo</span>
                  </div>
                ) : null;
              })}
            </>
          )}
          <div className="summary-line">
            <span>Seats</span>
            <span>{invitation?.seats || 10}</span>
          </div>
          {teamInvites.length > 0 && (
            <div className="summary-line faded">
              <span>Team invites queued</span>
              <span>{teamInvites.length}</span>
            </div>
          )}
          <div className="summary-total">
            <span>Total</span>
            <span>${totalPrice}/month</span>
          </div>
          <div className="secure-badge">
            <span>🔒 Secure checkout</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AdminOnboarding;
