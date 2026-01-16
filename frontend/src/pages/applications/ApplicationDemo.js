/**
 * ApplicationDemo - Demo landing page for mortgage applications
 * Allows users to try the application flow without backend integration
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import './ApplicationDemo.css';

const ApplicationDemo = () => {
  const navigate = useNavigate();

  const handleStartPurchase = () => {
    navigate('/apply/v2/purchase?demo=true');
  };

  const handleStartRefinance = () => {
    navigate('/apply/v2/refinance?demo=true');
  };

  return (
    <div className="demo-page">
      <div className="demo-container">
        {/* Header */}
        <div className="demo-header">
          <div className="demo-badge">Demo Mode</div>
          <h1 className="demo-title">Mortgage Application Demo</h1>
          <p className="demo-subtitle">
            Experience our streamlined mortgage application process.
            No account required - your progress is saved locally.
          </p>
        </div>

        {/* Application Options */}
        <div className="demo-options">
          <div className="demo-card" onClick={handleStartPurchase}>
            <div className="card-icon purchase-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                <polyline points="9,22 9,12 15,12 15,22"/>
              </svg>
            </div>
            <h2 className="card-title">Home Purchase</h2>
            <p className="card-description">
              Buying a new home? Start your purchase application and get pre-approved.
            </p>
            <ul className="card-features">
              <li>First-time buyer programs</li>
              <li>Down payment assistance options</li>
              <li>Competitive rates</li>
            </ul>
            <button className="card-button purchase-button">
              Start Purchase Application
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="arrow-icon">
                <line x1="5" y1="12" x2="19" y2="12"/>
                <polyline points="12,5 19,12 12,19"/>
              </svg>
            </button>
          </div>

          <div className="demo-card" onClick={handleStartRefinance}>
            <div className="card-icon refinance-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
                <path d="M21 3v5h-5"/>
                <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
                <path d="M8 16H3v5"/>
              </svg>
            </div>
            <h2 className="card-title">Refinance</h2>
            <p className="card-description">
              Lower your rate, tap equity, or change your loan term with a refinance.
            </p>
            <ul className="card-features">
              <li>Rate & term refinance</li>
              <li>Cash-out options</li>
              <li>Debt consolidation</li>
            </ul>
            <button className="card-button refinance-button">
              Start Refinance Application
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="arrow-icon">
                <line x1="5" y1="12" x2="19" y2="12"/>
                <polyline points="12,5 19,12 12,19"/>
              </svg>
            </button>
          </div>
        </div>

        {/* Features */}
        <div className="demo-features">
          <h3 className="features-title">What to Expect</h3>
          <div className="features-grid">
            <div className="feature-item">
              <div className="feature-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"/>
                  <polyline points="12,6 12,12 16,14"/>
                </svg>
              </div>
              <h4>Quick Process</h4>
              <p>Complete in about 10-15 minutes</p>
            </div>
            <div className="feature-item">
              <div className="feature-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                  <polyline points="17,21 17,13 7,13 7,21"/>
                  <polyline points="7,3 7,8 15,8"/>
                </svg>
              </div>
              <h4>Auto-Save</h4>
              <p>Progress saved automatically</p>
            </div>
            <div className="feature-item">
              <div className="feature-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
              </div>
              <h4>Secure</h4>
              <p>Bank-level encryption</p>
            </div>
            <div className="feature-item">
              <div className="feature-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                  <polyline points="14,2 14,8 20,8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/>
                  <line x1="16" y1="17" x2="8" y2="17"/>
                </svg>
              </div>
              <h4>Smart Checklist</h4>
              <p>Personalized document list</p>
            </div>
          </div>
        </div>

        {/* Demo Notice */}
        <div className="demo-notice">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="notice-icon">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="16" x2="12" y2="12"/>
            <line x1="12" y1="8" x2="12.01" y2="8"/>
          </svg>
          <p>
            <strong>Demo Mode:</strong> This is a demonstration of the application flow.
            Data is stored locally in your browser and not submitted to any server.
            For a real application, contact your loan officer.
          </p>
        </div>
      </div>
    </div>
  );
};

export default ApplicationDemo;
