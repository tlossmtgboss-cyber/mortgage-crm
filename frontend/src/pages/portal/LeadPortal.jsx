/**
 * Lead Portal
 *
 * Portal view for leads who haven't yet submitted a loan application.
 * Focuses on engagement and conversion to application.
 *
 * Features:
 * - Welcome message with LO introduction
 * - Quick application start CTA
 * - Payment calculator
 * - Resource links (guides, FAQs)
 * - Contact/Schedule meeting options
 * - Loan officer contact card
 */

import React, { useState } from 'react';
import ScheduleAppointmentModal from '../../components/ScheduleAppointmentModal';
import PaymentCalculator from '../../components/PaymentCalculator';
import './LeadPortal.css';

// Helper function to format phone number
const formatPhone = (phone) => {
  if (!phone) return '';
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  return phone;
};

// Loan Officer Contact Card
const LOContactCard = ({ loanOfficer, onSchedule, onMessage }) => {
  if (!loanOfficer) {
    return null;
  }

  return (
    <div className="lo-contact-card">
      <div className="lo-header">
        <div className="lo-avatar">
          {loanOfficer.photo_url ? (
            <img src={loanOfficer.photo_url} alt={loanOfficer.name} />
          ) : (
            <span className="avatar-placeholder">
              {loanOfficer.name?.charAt(0) || 'LO'}
            </span>
          )}
        </div>
        <div className="lo-info">
          <h3>{loanOfficer.name || 'Your Loan Officer'}</h3>
          {loanOfficer.title && <p className="lo-title">{loanOfficer.title}</p>}
          {loanOfficer.nmls_id && <p className="lo-nmls">NMLS# {loanOfficer.nmls_id}</p>}
        </div>
      </div>

      <div className="lo-contact-details">
        {loanOfficer.email && (
          <a href={`mailto:${loanOfficer.email}`} className="contact-link">
            <span className="contact-icon">✉️</span>
            {loanOfficer.email}
          </a>
        )}
        {loanOfficer.phone && (
          <a href={`tel:${loanOfficer.phone}`} className="contact-link">
            <span className="contact-icon">📞</span>
            {formatPhone(loanOfficer.phone)}
          </a>
        )}
      </div>

      <div className="lo-actions">
        <button className="lo-action-btn primary" onClick={onSchedule}>
          <span>📅</span> Schedule a Call
        </button>
        {loanOfficer.email && (
          <a href={`mailto:${loanOfficer.email}`} className="lo-action-btn secondary">
            <span>✉️</span> Send Email
          </a>
        )}
      </div>
    </div>
  );
};

// Resource Card Component
const ResourceCard = ({ icon, title, description, linkText, linkUrl, onClick }) => (
  <div className="resource-card" onClick={onClick}>
    <div className="resource-icon">{icon}</div>
    <div className="resource-content">
      <h4>{title}</h4>
      <p>{description}</p>
    </div>
    <div className="resource-action">
      {linkUrl ? (
        <a href={linkUrl} target="_blank" rel="noopener noreferrer">
          {linkText || 'Learn More'} →
        </a>
      ) : (
        <span className="resource-link">{linkText || 'Learn More'} →</span>
      )}
    </div>
  </div>
);

// Quick Stats Display
const QuickStats = () => (
  <div className="quick-stats">
    <div className="stat-item">
      <span className="stat-value">15 min</span>
      <span className="stat-label">Average Application Time</span>
    </div>
    <div className="stat-item">
      <span className="stat-value">24 hrs</span>
      <span className="stat-label">Pre-Approval Turnaround</span>
    </div>
    <div className="stat-item">
      <span className="stat-value">100%</span>
      <span className="stat-label">Digital Process</span>
    </div>
  </div>
);

// Application Steps Overview
const ApplicationSteps = () => (
  <div className="application-steps">
    <h3>What to Expect</h3>
    <div className="steps-list">
      <div className="step">
        <div className="step-number">1</div>
        <div className="step-content">
          <h4>Complete Application</h4>
          <p>Answer a few questions about your finances and the home you're looking for.</p>
        </div>
      </div>
      <div className="step">
        <div className="step-number">2</div>
        <div className="step-content">
          <h4>Upload Documents</h4>
          <p>Securely upload income verification, bank statements, and ID.</p>
        </div>
      </div>
      <div className="step">
        <div className="step-number">3</div>
        <div className="step-content">
          <h4>Get Pre-Approved</h4>
          <p>Receive your pre-approval letter, typically within 24 hours.</p>
        </div>
      </div>
    </div>
  </div>
);

/**
 * Lead Portal Component
 *
 * Props from PortalContainer:
 * - data: Workspace data (workspace, contacts, loan_officer info)
 * - slug: Workspace slug
 * - onRefresh: Callback to refresh data
 */
export default function LeadPortal({ data, slug, onRefresh }) {
  const [activeSection, setActiveSection] = useState('overview');
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [showCalculator, setShowCalculator] = useState(false);

  // Extract data
  const workspace = data?.workspace;
  const contacts = data?.contacts || [];
  const borrower = contacts.find(c => c.contact_type === 'borrower') || contacts[0];
  const loanOfficer = data?.loan_officer || workspace?.loan_officer;

  // Get borrower's first name for personalization
  const borrowerName = borrower?.first_name || 'there';

  // Handle start application - navigate to application form
  const handleStartApplication = () => {
    // Redirect to application form within the portal
    window.location.href = `/portal/${slug}/apply`;
  };

  return (
    <div className="lead-portal">
      {/* Hero Section */}
      <header className="lead-hero">
        <div className="hero-content">
          <h1>Welcome{borrowerName !== 'there' ? `, ${borrowerName}` : ''}!</h1>
          <p className="hero-subtitle">
            You're one step closer to your dream home. Let's get you pre-approved.
          </p>

          <div className="hero-cta">
            <button className="cta-primary" onClick={handleStartApplication}>
              Start Your Application
            </button>
            <button className="cta-secondary" onClick={() => setShowScheduleModal(true)}>
              Talk to an Expert First
            </button>
          </div>

          <QuickStats />
        </div>
      </header>

      {/* Navigation */}
      <nav className="lead-nav">
        <button
          className={`nav-btn ${activeSection === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveSection('overview')}
        >
          Overview
        </button>
        <button
          className={`nav-btn ${activeSection === 'calculator' ? 'active' : ''}`}
          onClick={() => setActiveSection('calculator')}
        >
          Calculator
        </button>
        <button
          className={`nav-btn ${activeSection === 'resources' ? 'active' : ''}`}
          onClick={() => setActiveSection('resources')}
        >
          Resources
        </button>
      </nav>

      {/* Main Content */}
      <main className="lead-content">
        {/* Overview Section */}
        {activeSection === 'overview' && (
          <div className="overview-section">
            <div className="overview-grid">
              {/* Left Column - Steps & Info */}
              <div className="overview-main">
                <ApplicationSteps />

                {/* Ready to Apply Card */}
                <div className="ready-card">
                  <div className="ready-icon">🏠</div>
                  <div className="ready-content">
                    <h3>Ready to Get Started?</h3>
                    <p>
                      Our streamlined application takes about 15 minutes to complete.
                      You'll need basic information about your income, assets, and the
                      property you're interested in.
                    </p>
                    <button className="cta-primary" onClick={handleStartApplication}>
                      Begin Application
                    </button>
                  </div>
                </div>

                {/* What You'll Need */}
                <div className="checklist-preview">
                  <h3>What You'll Need</h3>
                  <ul className="needs-list">
                    <li>
                      <span className="check-icon">📋</span>
                      <div>
                        <strong>Personal Information</strong>
                        <p>Name, address, SSN, date of birth</p>
                      </div>
                    </li>
                    <li>
                      <span className="check-icon">💼</span>
                      <div>
                        <strong>Employment Details</strong>
                        <p>Employer name, position, income</p>
                      </div>
                    </li>
                    <li>
                      <span className="check-icon">🏦</span>
                      <div>
                        <strong>Asset Information</strong>
                        <p>Bank accounts, investments, other assets</p>
                      </div>
                    </li>
                    <li>
                      <span className="check-icon">🏡</span>
                      <div>
                        <strong>Property Details</strong>
                        <p>Address (if known), estimated value, loan amount needed</p>
                      </div>
                    </li>
                  </ul>
                </div>
              </div>

              {/* Right Column - LO Card & Quick Actions */}
              <div className="overview-sidebar">
                <LOContactCard
                  loanOfficer={loanOfficer}
                  onSchedule={() => setShowScheduleModal(true)}
                />

                {/* Quick Calculator Preview */}
                <div className="calculator-preview-card">
                  <h4>Estimate Your Payment</h4>
                  <p>Use our calculator to see what your monthly payment might look like.</p>
                  <button
                    className="preview-btn"
                    onClick={() => setActiveSection('calculator')}
                  >
                    Open Calculator →
                  </button>
                </div>

                {/* FAQ Preview */}
                <div className="faq-preview">
                  <h4>Common Questions</h4>
                  <details>
                    <summary>How long does pre-approval take?</summary>
                    <p>Most pre-approvals are completed within 24 hours of submitting a complete application with all required documents.</p>
                  </details>
                  <details>
                    <summary>Will this affect my credit score?</summary>
                    <p>We perform a soft credit pull initially, which doesn't affect your score. A hard pull only happens when you're ready to proceed with a formal application.</p>
                  </details>
                  <details>
                    <summary>What if I'm self-employed?</summary>
                    <p>Self-employed borrowers are welcome! You'll need to provide 2 years of tax returns and may need additional documentation.</p>
                  </details>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Calculator Section */}
        {activeSection === 'calculator' && (
          <div className="calculator-section">
            <div className="calculator-header">
              <h2>Payment Calculator</h2>
              <p>Estimate your monthly mortgage payment based on different scenarios.</p>
            </div>
            <PaymentCalculator
              initialHomeValue={400000}
              initialDownPayment={80000}
              initialCreditScore={720}
              initialLoanType="conventional"
              compact={false}
              showAdvancedOptions={true}
            />

            <div className="calculator-cta">
              <p>Like what you see? Let's make it happen.</p>
              <button className="cta-primary" onClick={handleStartApplication}>
                Start Your Application
              </button>
            </div>
          </div>
        )}

        {/* Resources Section */}
        {activeSection === 'resources' && (
          <div className="resources-section">
            <h2>Helpful Resources</h2>
            <p className="resources-intro">
              We're here to help you navigate the home buying process.
            </p>

            <div className="resources-grid">
              <ResourceCard
                icon="📚"
                title="First-Time Buyer Guide"
                description="Everything you need to know about buying your first home, from pre-approval to closing."
                linkText="Read Guide"
              />
              <ResourceCard
                icon="📊"
                title="Understanding Credit Scores"
                description="Learn how your credit score affects your mortgage rate and what you can do to improve it."
                linkText="Learn More"
              />
              <ResourceCard
                icon="💰"
                title="Down Payment Options"
                description="Explore different down payment assistance programs and low down payment loan options."
                linkText="Explore Options"
              />
              <ResourceCard
                icon="📝"
                title="Document Checklist"
                description="Get prepared with our complete list of documents you'll need for your application."
                linkText="View Checklist"
              />
              <ResourceCard
                icon="🏠"
                title="Loan Types Explained"
                description="Conventional, FHA, VA, USDA - learn which loan type might be best for your situation."
                linkText="Compare Loans"
              />
              <ResourceCard
                icon="❓"
                title="FAQs"
                description="Get answers to the most common questions about the mortgage process."
                linkText="View FAQs"
              />
            </div>

            {/* Contact Section in Resources */}
            <div className="resources-contact">
              <h3>Still Have Questions?</h3>
              <p>Our team is here to help you every step of the way.</p>
              <div className="contact-buttons">
                <button className="cta-primary" onClick={() => setShowScheduleModal(true)}>
                  Schedule a Consultation
                </button>
                {loanOfficer?.email && (
                  <a href={`mailto:${loanOfficer.email}`} className="cta-secondary">
                    Send an Email
                  </a>
                )}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Schedule Appointment Modal */}
      <ScheduleAppointmentModal
        isOpen={showScheduleModal}
        onClose={() => setShowScheduleModal(false)}
        onSuccess={() => {
          setShowScheduleModal(false);
        }}
        borrower={borrower ? {
          id: borrower.id,
          first_name: borrower.first_name,
          last_name: borrower.last_name,
          email: borrower.email,
          phone: borrower.phone,
        } : null}
      />

      {/* Footer */}
      <footer className="lead-footer">
        <p>Your information is secure and protected.</p>
        <p className="footer-links">
          <a href="/privacy">Privacy Policy</a>
          <span>•</span>
          <a href="/terms">Terms of Service</a>
        </p>
      </footer>
    </div>
  );
}
