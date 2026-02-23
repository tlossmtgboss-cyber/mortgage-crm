/**
 * Lead Portal
 *
 * Pre-application borrower portal matching the card-based dashboard design:
 * - Header card: Borrower name, email, phone, address
 * - Loan info grid + circular progress stepper
 * - Tab bar: Overview, Application, Documents, Loan Comparison, Pre-Approval, Contacts
 * - Action items checklist + Recent Activity sidebar
 */

import React, { useState, useMemo } from 'react';
import ScheduleAppointmentModal from '../../components/ScheduleAppointmentModal';
import './LeadPortal.css';
import { toast } from '../../utils/toast';

const formatPhone = (phone) => {
  if (!phone) return '';
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  return phone;
};

const formatCurrency = (amount) => {
  if (!amount && amount !== 0) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
};

// Circular progress stepper matching the mockup
const ProgressStepper = ({ currentStep = 1 }) => {
  const steps = [
    { id: 1, label: 'APP\nCOMPLETED' },
    { id: 2, label: 'DOCS\nREQUESTED' },
    { id: 3, label: 'DOCS\nAPPROVED' },
    { id: 4, label: 'PRE-\nAPPROVED' },
  ];

  return (
    <div className="progress-stepper">
      <div className="stepper-track">
        {steps.map((step, idx) => {
          const isComplete = idx < currentStep;
          const isCurrent = idx === currentStep;
          const isUpcoming = idx > currentStep;

          return (
            <React.Fragment key={step.id}>
              {idx > 0 && (
                <div className={`stepper-line ${isComplete ? 'complete' : ''}`} />
              )}
              <div className={`stepper-step ${isComplete ? 'complete' : ''} ${isCurrent ? 'current' : ''} ${isUpcoming ? 'upcoming' : ''}`}>
                <div className="step-circle">
                  {isComplete ? (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  ) : (
                    <span>{step.id}</span>
                  )}
                </div>
                <span className="step-label">{step.label}</span>
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

// Action item icon
const ActionItemIcon = ({ type }) => {
  const icons = {
    document: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
      </svg>
    ),
    alert: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
    ),
  };
  return (
    <div className={`action-icon action-icon-${type}`}>
      {icons[type] || icons.document}
    </div>
  );
};

export default function LeadPortal({ data, slug, onRefresh }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [showScheduleModal, setShowScheduleModal] = useState(false);

  // Extract data
  const workspace = data?.workspace;
  const contacts = data?.contacts || [];
  const borrower = contacts.find(c => c.contact_type === 'borrower') || contacts[0];
  const loanOfficer = data?.loan_officer || workspace?.loan_officer;
  const loan = data?.loan;
  const application = data?.application;

  const borrowerName = borrower
    ? `${borrower.first_name || ''} ${borrower.last_name || ''}`.trim()
    : 'New Lead';
  const borrowerEmail = borrower?.email || '';
  const borrowerPhone = borrower?.phone || '';
  const propertyAddress = useMemo(() => {
    const addr = loan?.property_address || application?.property_address;
    if (!addr) return 'Address pending';
    if (typeof addr === 'string') return addr;
    return [addr.street, addr.city, addr.state, addr.zip].filter(Boolean).join(', ');
  }, [loan, application]);

  // Loan info for the grid
  const loanPurpose = loan?.loan_purpose || application?.loan_purpose || 'Purchase';
  const loanType = loan?.loan_type || application?.loan_type || 'Conventional';
  const loanTerm = loan?.term_months ? `${loan.term_months / 12} Years` : '30 Years';
  const loanAmount = loan?.loan_amount || application?.loan_amount || 0;
  const interestRate = loan?.interest_rate || 'TBD';
  const rateLock = loan?.lock_expiration_date ? 'Locked' : 'Not Locked';
  const estClosing = loan?.closing_date || 'TBD';
  const scheduled = loan?.scheduled_closing_date || 'TBD';
  const estPayment = loan?.monthly_payment || 'TBD';

  // Determine progress step based on application status
  const currentStep = useMemo(() => {
    const status = application?.status?.toLowerCase() || workspace?.status?.toLowerCase() || '';
    if (status === 'pre_approved' || status === 'preapproved') return 4;
    if (status === 'docs_approved' || status === 'processing') return 3;
    if (status === 'docs_requested' || status === 'documents') return 2;
    if (status === 'application' || status === 'submitted') return 1;
    return 0;
  }, [application, workspace]);

  // Action items for leads
  const actionItems = [
    {
      id: 'read-process',
      icon: 'document',
      title: 'Read the 7 Step Process',
      description: 'Learn about each step of your mortgage journey',
    },
    {
      id: 'bulletproof',
      icon: 'alert',
      title: 'Be a Bullet Proof Buyer',
      description: 'Tips to make your offer stand out',
    },
    {
      id: 'documents',
      icon: 'document',
      title: 'Review Documents Needed',
      description: 'See what documents you need to upload',
    },
  ];

  // Contacts list
  const allContacts = useMemo(() => {
    const list = [];
    if (borrower) {
      list.push({
        name: `${borrower.first_name || ''} ${borrower.last_name || ''}`.trim(),
        role: 'Borrower',
        email: borrower.email,
        phone: borrower.phone,
      });
    }
    const coborrower = contacts.find(c => c.contact_type === 'coborrower');
    if (coborrower) {
      list.push({
        name: `${coborrower.first_name || ''} ${coborrower.last_name || ''}`.trim(),
        role: 'Co-Borrower',
        email: coborrower.email,
        phone: coborrower.phone,
      });
    }
    if (loanOfficer) {
      list.push({
        name: loanOfficer.name || 'Loan Officer',
        role: 'Loan Officer',
        email: loanOfficer.email,
        phone: loanOfficer.phone,
        nmls: loanOfficer.nmls_id,
      });
    }
    return list;
  }, [contacts, borrower, loanOfficer]);

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'application', label: 'Application' },
    { id: 'documents', label: 'Documents' },
    { id: 'loan-comparison', label: 'Loan Comparison' },
    { id: 'pre-approval', label: 'Pre-Approval' },
    { id: 'contacts', label: 'Contacts' },
  ];

  return (
    <div className="lead-portal">
      {/* Borrower Header Card */}
      <div className="borrower-header-card">
        <h1 className="borrower-name">{borrowerName}</h1>
        {borrowerEmail && (
          <div className="borrower-contact-row">
            <svg className="contact-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
              <polyline points="22,6 12,13 2,6" />
            </svg>
            <span>{borrowerEmail}</span>
          </div>
        )}
        {borrowerPhone && (
          <div className="borrower-contact-row">
            <svg className="contact-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
            </svg>
            <span>{formatPhone(borrowerPhone)}</span>
          </div>
        )}
        <div className="address-row">
          <span className="property-address">{propertyAddress}</span>
        </div>
      </div>

      {/* Loan Info + Progress Stepper */}
      <div className="loan-info-card">
        <div className="loan-info-grid">
          <div className="info-cell">
            <span className="info-label">PURPOSE</span>
            <span className="info-value">{loanPurpose}</span>
          </div>
          <div className="info-cell">
            <span className="info-label">LOAN TYPE</span>
            <span className="info-value">{loanType}</span>
          </div>
          <div className="info-cell">
            <span className="info-label">TERM</span>
            <span className="info-value">{loanTerm}</span>
          </div>
          <div className="info-cell">
            <span className="info-label">LOAN AMOUNT</span>
            <span className="info-value">{loanAmount ? formatCurrency(loanAmount) : '$0'}</span>
          </div>
          <div className="info-cell">
            <span className="info-label">INTEREST RATE</span>
            <span className="info-value">{typeof interestRate === 'number' ? `${interestRate}%` : interestRate}</span>
          </div>
          <div className="info-cell">
            <span className="info-label">RATE LOCK</span>
            <span className="info-value">{rateLock}</span>
          </div>
          <div className="info-cell">
            <span className="info-label">EST. CLOSING</span>
            <span className="info-value">{typeof estClosing === 'string' && estClosing !== 'TBD' ? new Date(estClosing).toLocaleDateString() : 'TBD'}</span>
          </div>
          <div className="info-cell">
            <span className="info-label">SCHEDULED</span>
            <span className="info-value">{typeof scheduled === 'string' && scheduled !== 'TBD' ? new Date(scheduled).toLocaleDateString() : 'TBD'}</span>
          </div>
          <div className="info-cell">
            <span className="info-label">EST. PAYMENT</span>
            <span className="info-value">{typeof estPayment === 'number' ? formatCurrency(estPayment) : estPayment}</span>
          </div>
        </div>
        <div className="stepper-container">
          <ProgressStepper currentStep={currentStep} />
        </div>
      </div>

      {/* Tab Bar */}
      <nav className="portal-tab-bar">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Tab Content */}
      <div className="portal-tab-content">

        {/* ===== OVERVIEW TAB ===== */}
        {activeTab === 'overview' && (
          <div className="overview-layout">
            <div className="overview-main">
              {/* Questions / CTA */}
              <div className="questions-card">
                <div className="questions-left">
                  <h3>Questions about your loan?</h3>
                  <p>Your loan officer is here to help guide you through the process.</p>
                </div>
                <div className="questions-buttons">
                  <button className="btn-schedule" onClick={() => setShowScheduleModal(true)}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                      <line x1="16" y1="2" x2="16" y2="6" />
                      <line x1="8" y1="2" x2="8" y2="6" />
                      <line x1="3" y1="10" x2="21" y2="10" />
                    </svg>
                    Schedule a Call
                  </button>
                </div>
              </div>

              {/* Action Items */}
              <div className="action-items-card">
                <div className="action-items-header">
                  <h3>Your Action Items</h3>
                  <span className="items-badge">{actionItems.length} ITEMS TO COMPLETE</span>
                </div>
                <div className="action-items-list">
                  {actionItems.map((item) => (
                    <div key={item.id} className="action-item">
                      <ActionItemIcon type={item.icon} />
                      <div className="action-item-content">
                        <span className="action-item-title">{item.title}</span>
                        <span className="action-item-description">{item.description}</span>
                      </div>
                      <div className="action-item-meta">
                        <button className="view-link" onClick={() => toast.info('Coming soon')}>
                          View &rsaquo;
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Sidebar */}
            <div className="overview-sidebar">
              <div className="recent-activity-card">
                <h3>Recent Activity</h3>
                <p className="no-activity">No recent activity</p>
              </div>
            </div>
          </div>
        )}

        {/* ===== APPLICATION TAB ===== */}
        {activeTab === 'application' && (
          <div className="application-tab">
            <div className="empty-state">
              <h3>Application</h3>
              <p>Your application details will appear here once submitted. Contact your loan officer to get started.</p>
              <button className="btn-schedule-sm" onClick={() => setShowScheduleModal(true)}>
                Schedule a Call
              </button>
            </div>
          </div>
        )}

        {/* ===== DOCUMENTS TAB ===== */}
        {activeTab === 'documents' && (
          <div className="documents-tab">
            <h2>Documents</h2>
            <div className="empty-state">
              <h3>No Documents Yet</h3>
              <p>Documents needed for your loan application will appear here. Your loan officer will let you know what to upload.</p>
            </div>
          </div>
        )}

        {/* ===== LOAN COMPARISON TAB ===== */}
        {activeTab === 'loan-comparison' && (
          <div className="loan-comparison-tab">
            <h2>Loan Comparison</h2>
            <div className="empty-state">
              <h3>No Loan Options Yet</h3>
              <p>Once your application is processed, your loan officer will present different loan options for you to compare here.</p>
            </div>
          </div>
        )}

        {/* ===== PRE-APPROVAL TAB ===== */}
        {activeTab === 'pre-approval' && (
          <div className="preapproval-tab">
            <h2>Pre-Approval</h2>
            <div className="empty-state">
              <h3>Pre-Approval Status</h3>
              <p>Your pre-approval letter and details will appear here once your application is approved.</p>
              <div className="preapproval-status">
                <ProgressStepper currentStep={currentStep} />
              </div>
            </div>
          </div>
        )}

        {/* ===== CONTACTS TAB ===== */}
        {activeTab === 'contacts' && (
          <div className="contacts-tab">
            <h2>Your Contacts</h2>
            <div className="contacts-list">
              {allContacts.map((contact, idx) => (
                <div key={idx} className="contact-card">
                  <div className="contact-avatar">
                    {contact.name?.charAt(0) || '?'}
                  </div>
                  <div className="contact-info">
                    <span className="contact-name">{contact.name}</span>
                    <span className="contact-role">{contact.role}</span>
                    {contact.nmls && <span className="contact-nmls">NMLS# {contact.nmls}</span>}
                  </div>
                  <div className="contact-actions">
                    {contact.email && (
                      <a href={`mailto:${contact.email}`} className="contact-action-link">{contact.email}</a>
                    )}
                    {contact.phone && (
                      <a href={`tel:${contact.phone}`} className="contact-action-link">{formatPhone(contact.phone)}</a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Schedule Modal */}
      <ScheduleAppointmentModal
        isOpen={showScheduleModal}
        onClose={() => setShowScheduleModal(false)}
        onSuccess={() => setShowScheduleModal(false)}
        borrower={borrower ? {
          id: borrower.id,
          first_name: borrower.first_name,
          last_name: borrower.last_name,
          email: borrower.email,
          phone: borrower.phone,
        } : null}
      />
    </div>
  );
}
