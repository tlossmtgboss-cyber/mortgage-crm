/**
 * Application Preview
 *
 * Renders a single stage of the application for preview purposes.
 * Used by the Application Slides Editor to show live previews.
 */

import React, { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import './ApplicationPreview.css';

// Stage content components - simplified versions for preview
const StagePreview = ({ stage, appType }) => {
  const stageContent = useMemo(() => {
    switch (stage.id) {
      case 'account':
        return <AccountStagePreview />;
      case 'declarations':
        return <DeclarationsStagePreview appType={appType} />;
      case 'planning':
        return <PlanningStagePreview appType={appType} />;
      case 'profile':
        return <ProfileStagePreview />;
      case 'income':
        return <IncomeStagePreview />;
      case 'assets':
        return <AssetsStagePreview />;
      case 'property':
        return <PropertyStagePreview appType={appType} />;
      case 'goals':
        return <GoalsStagePreview />;
      case 'review':
        return <ReviewStagePreview />;
      case 'schedule':
        return <ScheduleStagePreview />;
      default:
        return <GenericStagePreview stage={stage} />;
    }
  }, [stage, appType]);

  return (
    <div className="stage-preview-container">
      <div className="stage-preview-header">
        <h1>{stage.label}</h1>
        <p className="stage-description">{stage.description}</p>
      </div>
      <div className="stage-preview-content">
        {stageContent}
      </div>
    </div>
  );
};

// Individual stage preview components
const AccountStagePreview = () => (
  <div className="preview-form">
    <div className="form-section">
      <h3>Create Your Account</h3>
      <div className="preview-field">
        <label>Email Address</label>
        <input type="email" placeholder="you@example.com" disabled />
      </div>
      <div className="preview-field">
        <label>Password</label>
        <input type="password" placeholder="••••••••" disabled />
      </div>
      <button className="preview-btn-primary" disabled>Create Account</button>
      <div className="social-auth-preview">
        <p>Or continue with:</p>
        <div className="social-buttons">
          <button className="social-btn google" disabled>Google</button>
          <button className="social-btn facebook" disabled>Facebook</button>
          <button className="social-btn apple" disabled>Apple</button>
        </div>
      </div>
    </div>
  </div>
);

const DeclarationsStagePreview = ({ appType }) => (
  <div className="preview-form">
    <div className="form-section">
      <h3>Quick Questions</h3>
      <p className="section-description">Help us personalize your experience</p>

      <div className="preview-question">
        <label>How many people will be on this loan?</label>
        <div className="choice-options">
          <button className="choice-btn selected" disabled>Just Me</button>
          <button className="choice-btn" disabled>2 People</button>
          <button className="choice-btn" disabled>3+ People</button>
        </div>
      </div>

      <div className="preview-question">
        <label>What is your citizenship status?</label>
        <div className="choice-options">
          <button className="choice-btn selected" disabled>US Citizen</button>
          <button className="choice-btn" disabled>Permanent Resident</button>
          <button className="choice-btn" disabled>Non-Permanent Resident</button>
        </div>
      </div>

      {appType === 'purchase' && (
        <div className="preview-question">
          <label>Is this your first home purchase?</label>
          <div className="choice-options">
            <button className="choice-btn selected" disabled>Yes</button>
            <button className="choice-btn" disabled>No</button>
          </div>
        </div>
      )}

      <div className="preview-question">
        <label>Have you served in the military?</label>
        <div className="choice-options">
          <button className="choice-btn" disabled>Yes</button>
          <button className="choice-btn selected" disabled>No</button>
        </div>
      </div>
    </div>
  </div>
);

const PlanningStagePreview = ({ appType }) => (
  <div className="preview-form">
    <div className="form-section">
      <h3>{appType === 'refinance' ? 'Your Refinance Goals' : 'Your Preferences'}</h3>

      {appType === 'refinance' ? (
        <>
          <div className="preview-question">
            <label>What's your main goal for refinancing?</label>
            <div className="choice-options vertical">
              <button className="choice-btn selected" disabled>Lower my monthly payment</button>
              <button className="choice-btn" disabled>Get cash out</button>
              <button className="choice-btn" disabled>Shorten my loan term</button>
              <button className="choice-btn" disabled>Remove mortgage insurance</button>
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="preview-question">
            <label>What's most important to you?</label>
            <div className="choice-options vertical">
              <button className="choice-btn selected" disabled>Lowest monthly payment</button>
              <button className="choice-btn" disabled>Pay off the loan faster</button>
              <button className="choice-btn" disabled>Most cash at closing</button>
              <button className="choice-btn" disabled>Fixed predictable payment</button>
            </div>
          </div>
        </>
      )}
    </div>
  </div>
);

const ProfileStagePreview = () => (
  <div className="preview-form">
    <div className="form-section">
      <h3>About You</h3>

      <div className="form-row">
        <div className="preview-field">
          <label>First Name</label>
          <input type="text" placeholder="John" disabled />
        </div>
        <div className="preview-field">
          <label>Last Name</label>
          <input type="text" placeholder="Smith" disabled />
        </div>
      </div>

      <div className="form-row">
        <div className="preview-field">
          <label>Date of Birth</label>
          <input type="date" disabled />
        </div>
        <div className="preview-field">
          <label>SSN (Last 4)</label>
          <input type="text" placeholder="••••" disabled />
        </div>
      </div>

      <div className="preview-field">
        <label>Current Address</label>
        <input type="text" placeholder="123 Main St" disabled />
      </div>

      <div className="form-row">
        <div className="preview-field">
          <label>City</label>
          <input type="text" placeholder="City" disabled />
        </div>
        <div className="preview-field">
          <label>State</label>
          <select disabled><option>Select State</option></select>
        </div>
        <div className="preview-field">
          <label>ZIP</label>
          <input type="text" placeholder="12345" disabled />
        </div>
      </div>
    </div>
  </div>
);

const IncomeStagePreview = () => (
  <div className="preview-form">
    <div className="form-section">
      <h3>Your Income</h3>

      <div className="preview-question">
        <label>Employment Status</label>
        <div className="choice-options">
          <button className="choice-btn selected" disabled>Employed</button>
          <button className="choice-btn" disabled>Self-Employed</button>
          <button className="choice-btn" disabled>Retired</button>
        </div>
      </div>

      <div className="preview-field">
        <label>Employer Name</label>
        <input type="text" placeholder="Company Name" disabled />
      </div>

      <div className="form-row">
        <div className="preview-field">
          <label>Job Title</label>
          <input type="text" placeholder="Your Position" disabled />
        </div>
        <div className="preview-field">
          <label>Years at Job</label>
          <input type="number" placeholder="3" disabled />
        </div>
      </div>

      <div className="preview-field">
        <label>Annual Income</label>
        <div className="currency-input">
          <span className="currency-symbol">$</span>
          <input type="text" placeholder="75,000" disabled />
        </div>
      </div>
    </div>
  </div>
);

const AssetsStagePreview = () => (
  <div className="preview-form">
    <div className="form-section">
      <h3>Your Assets</h3>
      <p className="section-description">Where will your down payment come from?</p>

      <div className="asset-card">
        <div className="asset-header">
          <span className="asset-icon">🏦</span>
          <span className="asset-type">Checking Account</span>
        </div>
        <div className="preview-field">
          <label>Bank Name</label>
          <input type="text" placeholder="Bank Name" disabled />
        </div>
        <div className="preview-field">
          <label>Account Balance</label>
          <div className="currency-input">
            <span className="currency-symbol">$</span>
            <input type="text" placeholder="25,000" disabled />
          </div>
        </div>
      </div>

      <button className="add-asset-btn" disabled>+ Add Another Account</button>

      <div className="preview-question">
        <label>Will you receive gift funds?</label>
        <div className="choice-options">
          <button className="choice-btn" disabled>Yes</button>
          <button className="choice-btn selected" disabled>No</button>
        </div>
      </div>
    </div>
  </div>
);

const PropertyStagePreview = ({ appType }) => (
  <div className="preview-form">
    <div className="form-section">
      <h3>{appType === 'refinance' ? 'Current Home' : 'New Home'}</h3>

      <div className="preview-field">
        <label>Property Address</label>
        <input type="text" placeholder="123 New Home Dr" disabled />
      </div>

      <div className="form-row">
        <div className="preview-field">
          <label>City</label>
          <input type="text" placeholder="City" disabled />
        </div>
        <div className="preview-field">
          <label>State</label>
          <select disabled><option>Select State</option></select>
        </div>
        <div className="preview-field">
          <label>ZIP</label>
          <input type="text" placeholder="12345" disabled />
        </div>
      </div>

      <div className="preview-question">
        <label>Property Type</label>
        <div className="choice-options">
          <button className="choice-btn selected" disabled>Single Family</button>
          <button className="choice-btn" disabled>Condo</button>
          <button className="choice-btn" disabled>Townhouse</button>
          <button className="choice-btn" disabled>Multi-Family</button>
        </div>
      </div>

      {appType === 'purchase' && (
        <div className="form-row">
          <div className="preview-field">
            <label>Purchase Price</label>
            <div className="currency-input">
              <span className="currency-symbol">$</span>
              <input type="text" placeholder="450,000" disabled />
            </div>
          </div>
          <div className="preview-field">
            <label>Down Payment</label>
            <div className="currency-input">
              <span className="currency-symbol">$</span>
              <input type="text" placeholder="90,000" disabled />
            </div>
          </div>
        </div>
      )}
    </div>
  </div>
);

const GoalsStagePreview = () => (
  <div className="preview-form">
    <div className="form-section">
      <h3>Refinance Options</h3>

      <div className="preview-question">
        <label>How much cash do you need?</label>
        <div className="currency-input large">
          <span className="currency-symbol">$</span>
          <input type="text" placeholder="50,000" disabled />
        </div>
      </div>

      <div className="preview-question">
        <label>What will you use the cash for?</label>
        <div className="choice-options vertical">
          <button className="choice-btn" disabled>Home Improvements</button>
          <button className="choice-btn" disabled>Debt Consolidation</button>
          <button className="choice-btn" disabled>Investment</button>
          <button className="choice-btn" disabled>Other</button>
        </div>
      </div>
    </div>
  </div>
);

const ReviewStagePreview = () => (
  <div className="preview-form">
    <div className="form-section">
      <h3>Review Your Application</h3>
      <p className="section-description">Please review your information before submitting</p>

      <div className="review-section">
        <h4>Personal Information</h4>
        <div className="review-row">
          <span className="review-label">Name</span>
          <span className="review-value">John Smith</span>
        </div>
        <div className="review-row">
          <span className="review-label">Email</span>
          <span className="review-value">john@example.com</span>
        </div>
      </div>

      <div className="review-section">
        <h4>Income</h4>
        <div className="review-row">
          <span className="review-label">Employer</span>
          <span className="review-value">Acme Corp</span>
        </div>
        <div className="review-row">
          <span className="review-label">Annual Income</span>
          <span className="review-value">$75,000</span>
        </div>
      </div>

      <div className="review-section">
        <h4>Property</h4>
        <div className="review-row">
          <span className="review-label">Address</span>
          <span className="review-value">123 New Home Dr, City, ST</span>
        </div>
        <div className="review-row">
          <span className="review-label">Purchase Price</span>
          <span className="review-value">$450,000</span>
        </div>
      </div>

      <div className="consent-section">
        <label className="checkbox-label">
          <input type="checkbox" disabled checked />
          <span>I certify the information provided is true and accurate</span>
        </label>
      </div>
    </div>
  </div>
);

const ScheduleStagePreview = () => (
  <div className="preview-form">
    <div className="form-section">
      <h3>Schedule a Call</h3>
      <p className="section-description">Pick a time that works best for you</p>

      <div className="calendar-preview">
        <div className="calendar-header">
          <button className="cal-nav" disabled>‹</button>
          <span>December 2025</span>
          <button className="cal-nav" disabled>›</button>
        </div>
        <div className="calendar-grid">
          <div className="cal-day header">S</div>
          <div className="cal-day header">M</div>
          <div className="cal-day header">T</div>
          <div className="cal-day header">W</div>
          <div className="cal-day header">T</div>
          <div className="cal-day header">F</div>
          <div className="cal-day header">S</div>
          {[...Array(31)].map((_, i) => (
            <div key={i} className={`cal-day ${i === 14 ? 'selected' : ''} ${i < 7 ? 'available' : ''}`}>
              {i + 1}
            </div>
          ))}
        </div>
      </div>

      <div className="time-slots">
        <h4>Available Times</h4>
        <div className="time-slot-grid">
          <button className="time-slot" disabled>9:00 AM</button>
          <button className="time-slot selected" disabled>10:00 AM</button>
          <button className="time-slot" disabled>11:00 AM</button>
          <button className="time-slot" disabled>2:00 PM</button>
          <button className="time-slot" disabled>3:00 PM</button>
        </div>
      </div>
    </div>
  </div>
);

const GenericStagePreview = ({ stage }) => (
  <div className="preview-form">
    <div className="form-section">
      <h3>{stage.label}</h3>
      <p className="section-description">{stage.description}</p>
      <div className="generic-preview-placeholder">
        <span className="placeholder-icon">📋</span>
        <p>Custom stage content will appear here</p>
        <p className="stage-id-display">Stage ID: {stage.id}</p>
      </div>
    </div>
  </div>
);

// Default stages configuration
const DEFAULT_STAGES = {
  purchase: [
    { id: 'account', label: 'Get Started', description: 'Create your account' },
    { id: 'declarations', label: 'Your Story', description: 'Quick questions to personalize' },
    { id: 'planning', label: 'Your Goals', description: 'Mortgage preferences' },
    { id: 'profile', label: 'About You', description: 'The basics about you' },
    { id: 'income', label: 'Your Income', description: 'How you earn' },
    { id: 'assets', label: 'Your Assets', description: 'Down payment funds' },
    { id: 'property', label: 'New Home', description: 'Property details' },
    { id: 'review', label: 'Review', description: 'Review your info' },
    { id: 'schedule', label: 'Schedule', description: 'Book a call' },
  ],
  refinance: [
    { id: 'account', label: 'Get Started', description: 'Create your account' },
    { id: 'declarations', label: 'Your Story', description: 'Quick questions' },
    { id: 'planning', label: 'Planning', description: 'Your preferences' },
    { id: 'profile', label: 'About You', description: 'The basics' },
    { id: 'income', label: 'Your Income', description: 'How you earn' },
    { id: 'property', label: 'Current Home', description: 'Property details' },
    { id: 'goals', label: 'Refi Goals', description: 'Refinance options' },
    { id: 'review', label: 'Review', description: 'Review your info' },
    { id: 'schedule', label: 'Submit', description: 'Complete application' },
  ]
};

const ApplicationPreview = () => {
  const [searchParams] = useSearchParams();
  const stageId = searchParams.get('stage');
  const appType = searchParams.get('type') || 'purchase';

  const [stage, setStage] = useState(null);

  useEffect(() => {
    // Find the stage from default stages
    const stages = DEFAULT_STAGES[appType] || DEFAULT_STAGES.purchase;
    const foundStage = stages.find(s => s.id === stageId);
    setStage(foundStage || { id: stageId, label: stageId, description: 'Custom stage' });
  }, [stageId, appType]);

  if (!stage) {
    return (
      <div className="preview-loading">
        <div className="spinner"></div>
        <p>Loading preview...</p>
      </div>
    );
  }

  return (
    <div className="application-preview">
      <div className="preview-banner">
        <span className="preview-badge">PREVIEW MODE</span>
        <span className="preview-stage-name">{stage.label}</span>
        <span className="preview-app-type">{appType === 'purchase' ? 'Purchase' : 'Refinance'}</span>
      </div>

      <div className="preview-wrapper">
        <div className="preview-phone-frame">
          <div className="phone-notch"></div>
          <div className="phone-screen">
            <StagePreview stage={stage} appType={appType} />
          </div>
          <div className="phone-home-indicator"></div>
        </div>
      </div>

      <div className="preview-nav-demo">
        <button className="nav-btn back" disabled>← Back</button>
        <div className="progress-dots">
          {[...Array(5)].map((_, i) => (
            <span key={i} className={`dot ${i === 2 ? 'active' : ''}`}></span>
          ))}
        </div>
        <button className="nav-btn next" disabled>Continue →</button>
      </div>
    </div>
  );
};

export default ApplicationPreview;
