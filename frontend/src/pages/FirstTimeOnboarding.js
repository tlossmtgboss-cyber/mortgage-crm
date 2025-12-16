import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './FirstTimeOnboarding.css';

// API URL configuration
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE_URL = isProduction
  ? 'https://mortgage-crm-production-7a9a.up.railway.app'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// Wizard Steps
const STEPS = {
  WELCOME: 'welcome',
  PROFILE: 'profile',
  ROLE: 'role',
  GOALS: 'goals',
  COMPLETE: 'complete'
};

const STEP_ORDER = [STEPS.WELCOME, STEPS.PROFILE, STEPS.ROLE, STEPS.GOALS, STEPS.COMPLETE];

const STEP_INFO = {
  [STEPS.WELCOME]: { label: 'Welcome', icon: '1' },
  [STEPS.PROFILE]: { label: 'Profile', icon: '2' },
  [STEPS.ROLE]: { label: 'Role', icon: '3' },
  [STEPS.GOALS]: { label: 'Goals', icon: '4' },
  [STEPS.COMPLETE]: { label: 'Complete', icon: '5' }
};

// Available roles
const ROLES = [
  { id: 'loan_officer', name: 'Loan Officer', description: 'Originate loans, manage borrower relationships, handle rate locks', icon: '🏠' },
  { id: 'jr_loan_officer', name: 'Jr. Loan Officer', description: 'Entry-level originator, learning sales and building relationships', icon: '📚' },
  { id: 'loan_officer_assistant', name: 'Loan Officer Assistant', description: 'Support LOs with admin tasks, documents, and communication', icon: '📋' },
  { id: 'processor', name: 'Processor', description: 'Manage loan processing, document verification, and UW submission', icon: '⚙️' },
  { id: 'processing_assistant', name: 'Processing Assistant', description: 'Assist with documentation, condition tracking, file prep', icon: '📁' },
  { id: 'closer', name: 'Closer', description: 'Manage closing coordination, final docs, and funding', icon: '✅' },
  { id: 'underwriter', name: 'Underwriter', description: 'Review applications, assess risk, issue approvals', icon: '🔍' },
  { id: 'team_lead', name: 'Team Lead', description: 'Supervise team members, monitor performance', icon: '👥' },
  { id: 'branch_manager', name: 'Branch Manager', description: 'Oversee branch operations, manage staff', icon: '🏢' },
  { id: 'other', name: 'Other', description: 'Different role not listed above', icon: '💼' }
];

// Departments
const DEPARTMENTS = [
  { id: 'sales', name: 'Sales / Originations' },
  { id: 'operations', name: 'Operations / Processing' },
  { id: 'underwriting', name: 'Underwriting' },
  { id: 'closing', name: 'Closing' },
  { id: 'compliance', name: 'Compliance' },
  { id: 'management', name: 'Management' },
  { id: 'support', name: 'Support / Admin' }
];

// Timezones
const TIMEZONES = [
  { id: 'America/New_York', name: 'Eastern Time (ET)' },
  { id: 'America/Chicago', name: 'Central Time (CT)' },
  { id: 'America/Denver', name: 'Mountain Time (MT)' },
  { id: 'America/Los_Angeles', name: 'Pacific Time (PT)' },
  { id: 'America/Anchorage', name: 'Alaska Time (AKT)' },
  { id: 'Pacific/Honolulu', name: 'Hawaii Time (HT)' }
];

function FirstTimeOnboarding() {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(STEPS.WELCOME);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [user, setUser] = useState(null);

  // Form data
  const [formData, setFormData] = useState({
    // Profile
    first_name: '',
    last_name: '',
    phone: '',
    timezone: 'America/New_York',
    profile_photo: null,
    // Role
    role: '',
    department: '',
    job_title: '',
    nmls_id: '',
    // Goals
    annual_goal: '',
    monthly_goal: '',
    avg_loan_amount: '350000',
    pull_through_rate: '75'
  });

  // Load user data on mount
  useEffect(() => {
    const userStr = localStorage.getItem('user');
    if (userStr) {
      const userData = JSON.parse(userStr);
      setUser(userData);
      // Pre-fill known data
      setFormData(prev => ({
        ...prev,
        first_name: userData.first_name || userData.full_name?.split(' ')[0] || '',
        last_name: userData.last_name || userData.full_name?.split(' ').slice(1).join(' ') || ''
      }));
    }
  }, []);

  const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  };

  const handleInputChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setError(null);
  };

  const validateStep = () => {
    switch (currentStep) {
      case STEPS.PROFILE:
        if (!formData.first_name.trim()) {
          setError('First name is required');
          return false;
        }
        if (!formData.last_name.trim()) {
          setError('Last name is required');
          return false;
        }
        break;
      case STEPS.ROLE:
        if (!formData.role) {
          setError('Please select your role');
          return false;
        }
        if (!formData.department) {
          setError('Please select your department');
          return false;
        }
        break;
      case STEPS.GOALS:
        // Goals are optional
        break;
      default:
        break;
    }
    return true;
  };

  const goToStep = (step) => {
    if (STEP_ORDER.indexOf(step) <= STEP_ORDER.indexOf(currentStep)) {
      setCurrentStep(step);
    }
  };

  const nextStep = () => {
    if (!validateStep()) return;

    const currentIndex = STEP_ORDER.indexOf(currentStep);
    if (currentIndex < STEP_ORDER.length - 1) {
      setCurrentStep(STEP_ORDER[currentIndex + 1]);
    }
  };

  const prevStep = () => {
    const currentIndex = STEP_ORDER.indexOf(currentStep);
    if (currentIndex > 0) {
      setCurrentStep(STEP_ORDER[currentIndex - 1]);
    }
  };

  const completeOnboarding = async () => {
    setLoading(true);
    setError(null);

    try {
      // Save profile data to backend
      const response = await fetch(`${API_BASE_URL}/api/v1/users/complete-onboarding`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          first_name: formData.first_name,
          last_name: formData.last_name,
          phone: formData.phone,
          timezone: formData.timezone,
          role: formData.role,
          department: formData.department,
          job_title: formData.job_title,
          nmls_id: formData.nmls_id,
          annual_goal: formData.annual_goal ? parseFloat(formData.annual_goal) : null,
          monthly_goal: formData.monthly_goal ? parseFloat(formData.monthly_goal) : null,
          avg_loan_amount: formData.avg_loan_amount ? parseFloat(formData.avg_loan_amount) : 350000,
          pull_through_rate: formData.pull_through_rate ? parseFloat(formData.pull_through_rate) : 75
        })
      });

      if (!response.ok) {
        throw new Error('Failed to save onboarding data');
      }

      // Update local user data
      const updatedUser = { ...user, onboarding_completed: true, ...formData };
      localStorage.setItem('user', JSON.stringify(updatedUser));

      // Also save goals to localStorage for Goal Tracker
      localStorage.setItem('goalTrackerInputs', JSON.stringify({
        annualClosingsDollarGoal: formData.annual_goal ? parseFloat(formData.annual_goal) : 12000000,
        monthlyClosingsDollarGoal: formData.monthly_goal ? parseFloat(formData.monthly_goal) : 1000000,
        avgLoanAmount: formData.avg_loan_amount ? parseFloat(formData.avg_loan_amount) : 350000,
        pullThroughRate: formData.pull_through_rate ? parseFloat(formData.pull_through_rate) / 100 : 0.75
      }));

      // Move to complete step
      setCurrentStep(STEPS.COMPLETE);

    } catch (err) {
      console.error('Onboarding error:', err);
      setError(err.message || 'Failed to complete onboarding. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const goToDashboard = () => {
    // Clear any cached dashboard data
    localStorage.removeItem('dashboard_data');
    localStorage.removeItem('dashboard_data_time');
    navigate('/dashboard');
  };

  // Render progress bar
  const renderProgress = () => {
    const currentIndex = STEP_ORDER.indexOf(currentStep);
    const progress = ((currentIndex) / (STEP_ORDER.length - 1)) * 100;

    return (
      <div className="onboarding-progress">
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${progress}%` }}></div>
        </div>
        <div className="progress-steps">
          {STEP_ORDER.map((step, idx) => (
            <div
              key={step}
              className={`progress-step ${idx <= currentIndex ? 'active' : ''} ${idx < currentIndex ? 'completed' : ''}`}
              onClick={() => goToStep(step)}
            >
              <div className="step-dot">
                {idx < currentIndex ? '✓' : STEP_INFO[step].icon}
              </div>
              <div className="step-label">{STEP_INFO[step].label}</div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  // Render Welcome Step
  const renderWelcome = () => (
    <div className="onboarding-step welcome-step">
      <div className="welcome-icon">🚀</div>
      <h1>Welcome to Perennia AI!</h1>
      <p className="welcome-subtitle">
        Let's get your account set up in just a few minutes.
      </p>
      <div className="welcome-features">
        <div className="feature-item">
          <span className="feature-icon">📊</span>
          <span>Track your pipeline and production</span>
        </div>
        <div className="feature-item">
          <span className="feature-icon">🤖</span>
          <span>AI-powered task management</span>
        </div>
        <div className="feature-item">
          <span className="feature-icon">📈</span>
          <span>Set and monitor your goals</span>
        </div>
        <div className="feature-item">
          <span className="feature-icon">💬</span>
          <span>Smart client communication</span>
        </div>
      </div>
      <button className="btn-primary btn-large" onClick={nextStep}>
        Get Started
      </button>
    </div>
  );

  // Render Profile Step
  const renderProfile = () => (
    <div className="onboarding-step profile-step">
      <h2>Tell us about yourself</h2>
      <p className="step-description">This information will be used across the platform.</p>

      <div className="form-grid">
        <div className="form-group">
          <label>First Name *</label>
          <input
            type="text"
            value={formData.first_name}
            onChange={(e) => handleInputChange('first_name', e.target.value)}
            placeholder="Enter your first name"
          />
        </div>

        <div className="form-group">
          <label>Last Name *</label>
          <input
            type="text"
            value={formData.last_name}
            onChange={(e) => handleInputChange('last_name', e.target.value)}
            placeholder="Enter your last name"
          />
        </div>

        <div className="form-group">
          <label>Phone Number</label>
          <input
            type="tel"
            value={formData.phone}
            onChange={(e) => handleInputChange('phone', e.target.value)}
            placeholder="(555) 555-5555"
          />
        </div>

        <div className="form-group">
          <label>Time Zone</label>
          <select
            value={formData.timezone}
            onChange={(e) => handleInputChange('timezone', e.target.value)}
          >
            {TIMEZONES.map(tz => (
              <option key={tz.id} value={tz.id}>{tz.name}</option>
            ))}
          </select>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="step-actions">
        <button className="btn-secondary" onClick={prevStep}>Back</button>
        <button className="btn-primary" onClick={nextStep}>Continue</button>
      </div>
    </div>
  );

  // Render Role Step
  const renderRole = () => (
    <div className="onboarding-step role-step">
      <h2>What's your role?</h2>
      <p className="step-description">This helps us customize your experience.</p>

      <div className="role-grid">
        {ROLES.map(role => (
          <div
            key={role.id}
            className={`role-card ${formData.role === role.id ? 'selected' : ''}`}
            onClick={() => handleInputChange('role', role.id)}
          >
            <div className="role-icon">{role.icon}</div>
            <div className="role-name">{role.name}</div>
            <div className="role-description">{role.description}</div>
          </div>
        ))}
      </div>

      <div className="form-row">
        <div className="form-group">
          <label>Department *</label>
          <select
            value={formData.department}
            onChange={(e) => handleInputChange('department', e.target.value)}
          >
            <option value="">Select your department</option>
            {DEPARTMENTS.map(dept => (
              <option key={dept.id} value={dept.id}>{dept.name}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label>Job Title</label>
          <input
            type="text"
            value={formData.job_title}
            onChange={(e) => handleInputChange('job_title', e.target.value)}
            placeholder="e.g., Senior Loan Officer"
          />
        </div>

        <div className="form-group">
          <label>NMLS ID (if applicable)</label>
          <input
            type="text"
            value={formData.nmls_id}
            onChange={(e) => handleInputChange('nmls_id', e.target.value)}
            placeholder="e.g., 123456"
          />
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="step-actions">
        <button className="btn-secondary" onClick={prevStep}>Back</button>
        <button className="btn-primary" onClick={nextStep}>Continue</button>
      </div>
    </div>
  );

  // Render Goals Step
  const renderGoals = () => (
    <div className="onboarding-step goals-step">
      <h2>Set your production goals</h2>
      <p className="step-description">We'll help you track progress toward these targets. You can change these later.</p>

      <div className="goals-grid">
        <div className="goal-card">
          <label>Annual Closing Goal ($)</label>
          <input
            type="number"
            value={formData.annual_goal}
            onChange={(e) => handleInputChange('annual_goal', e.target.value)}
            placeholder="e.g., 12000000"
          />
          <span className="goal-hint">Total dollar volume you aim to close this year</span>
        </div>

        <div className="goal-card">
          <label>Monthly Closing Goal ($)</label>
          <input
            type="number"
            value={formData.monthly_goal}
            onChange={(e) => handleInputChange('monthly_goal', e.target.value)}
            placeholder="e.g., 1000000"
          />
          <span className="goal-hint">Your monthly target volume</span>
        </div>

        <div className="goal-card">
          <label>Average Loan Amount ($)</label>
          <input
            type="number"
            value={formData.avg_loan_amount}
            onChange={(e) => handleInputChange('avg_loan_amount', e.target.value)}
            placeholder="350000"
          />
          <span className="goal-hint">Typical loan size in your market</span>
        </div>

        <div className="goal-card">
          <label>Pull-Through Rate (%)</label>
          <input
            type="number"
            value={formData.pull_through_rate}
            onChange={(e) => handleInputChange('pull_through_rate', e.target.value)}
            placeholder="75"
            min="0"
            max="100"
          />
          <span className="goal-hint">Percentage of applications that fund</span>
        </div>
      </div>

      <div className="skip-note">
        <span>Don't know these numbers yet?</span>
        <button className="btn-link" onClick={completeOnboarding}>Skip for now</button>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="step-actions">
        <button className="btn-secondary" onClick={prevStep}>Back</button>
        <button className="btn-primary" onClick={completeOnboarding} disabled={loading}>
          {loading ? 'Saving...' : 'Complete Setup'}
        </button>
      </div>
    </div>
  );

  // Render Complete Step
  const renderComplete = () => (
    <div className="onboarding-step complete-step">
      <div className="complete-icon">🎉</div>
      <h1>You're all set!</h1>
      <p className="complete-subtitle">
        Welcome to Perennia AI, {formData.first_name}!
      </p>

      <div className="complete-summary">
        <h3>Your Profile</h3>
        <div className="summary-grid">
          <div className="summary-item">
            <span className="label">Name</span>
            <span className="value">{formData.first_name} {formData.last_name}</span>
          </div>
          <div className="summary-item">
            <span className="label">Role</span>
            <span className="value">{ROLES.find(r => r.id === formData.role)?.name || formData.role}</span>
          </div>
          <div className="summary-item">
            <span className="label">Department</span>
            <span className="value">{DEPARTMENTS.find(d => d.id === formData.department)?.name || formData.department}</span>
          </div>
          {formData.annual_goal && (
            <div className="summary-item">
              <span className="label">Annual Goal</span>
              <span className="value">${parseInt(formData.annual_goal).toLocaleString()}</span>
            </div>
          )}
        </div>
      </div>

      <div className="next-steps">
        <h3>What's Next?</h3>
        <ul>
          <li>Explore your personalized dashboard</li>
          <li>Add your first lead or import your pipeline</li>
          <li>Chat with your AI assistant for help</li>
        </ul>
      </div>

      <button className="btn-primary btn-large" onClick={goToDashboard}>
        Go to Dashboard
      </button>
    </div>
  );

  // Render current step
  const renderStep = () => {
    switch (currentStep) {
      case STEPS.WELCOME:
        return renderWelcome();
      case STEPS.PROFILE:
        return renderProfile();
      case STEPS.ROLE:
        return renderRole();
      case STEPS.GOALS:
        return renderGoals();
      case STEPS.COMPLETE:
        return renderComplete();
      default:
        return renderWelcome();
    }
  };

  return (
    <div className="first-time-onboarding">
      <div className="onboarding-container">
        <div className="onboarding-header">
          <div className="logo">Perennia AI</div>
        </div>

        {currentStep !== STEPS.COMPLETE && renderProgress()}

        <div className="onboarding-content">
          {renderStep()}
        </div>
      </div>
    </div>
  );
}

export default FirstTimeOnboarding;
