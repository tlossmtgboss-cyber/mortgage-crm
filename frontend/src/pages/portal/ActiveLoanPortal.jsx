/**
 * Active Loan Portal
 *
 * Card-based dashboard for borrowers with active loans in progress.
 * Matches the unified portal design:
 * - Header card: borrower info + days until closing countdown
 * - Loan info grid + 6-step progress stepper
 * - Tab bar: Overview, Action Items, Documents, Loan Details, Closing, Contacts
 * - Action items checklist + Recent Activity sidebar
 */

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { api } from '../../lib/api';
import ScheduleAppointmentModal from '../../components/ScheduleAppointmentModal';
import './ActiveLoanPortal.css';
import { toast } from '../../utils/toast';

const formatPhone = (phone) => {
  if (!phone) return '';
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  return phone;
};

const formatCurrency = (amount, decimals = 0) => {
  if (!amount && amount !== 0) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(amount);
};

const formatDate = (dateStr) => {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
};

const formatShortDate = (dateStr) => {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
};

// Days until closing countdown
const DaysUntilClosing = ({ closingDate }) => {
  const days = useMemo(() => {
    if (!closingDate) return null;
    const closing = new Date(closingDate);
    const now = new Date();
    const diff = Math.max(0, Math.ceil((closing - now) / (1000 * 60 * 60 * 24)));
    return diff;
  }, [closingDate]);

  if (days === null) return null;

  const tens = Math.floor(days / 10);
  const ones = days % 10;

  return (
    <div className="days-countdown">
      <span className="countdown-label">DAYS UNTIL CLOSING</span>
      <div className="countdown-circles">
        <div className="countdown-digit">{tens}</div>
        <div className="countdown-digit">{ones}</div>
      </div>
      <span className="countdown-date">Closing {formatDate(closingDate)}</span>
    </div>
  );
};

// 6-step progress stepper for active loans
const LoanProgressStepper = ({ currentStep = 0 }) => {
  const steps = [
    { id: 1, label: 'APPLICATION' },
    { id: 2, label: 'PROCESSING' },
    { id: 3, label: 'UNDERWRITING' },
    { id: 4, label: 'APPROVAL' },
    { id: 5, label: 'CLEAR TO\nCLOSE' },
    { id: 6, label: 'CLOSING' },
  ];

  return (
    <div className="loan-stepper">
      <div className="stepper-track">
        {steps.map((step, idx) => {
          const isComplete = idx < currentStep;
          const isCurrent = idx === currentStep;

          return (
            <React.Fragment key={step.id}>
              {idx > 0 && (
                <div className={`stepper-line ${isComplete ? 'complete' : ''}`} />
              )}
              <div className={`stepper-step ${isComplete ? 'complete' : ''} ${isCurrent ? 'current' : ''}`}>
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
    upload: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </svg>
    ),
    document: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
      </svg>
    ),
    sign: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
      </svg>
    ),
    review: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
  };
  return (
    <div className={`action-icon action-icon-${type}`}>
      {icons[type] || icons.document}
    </div>
  );
};


export default function ActiveLoanPortal({ data, slug, subStage, onRefresh }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [tasks, setTasks] = useState([]);
  const [documents, setDocuments] = useState([]);

  // Extract data
  const workspace = data?.workspace;
  const loan = data?.loan;
  const contacts = data?.contacts || [];
  const borrower = contacts.find(c => c.contact_type === 'borrower') || contacts[0];
  const loanOfficer = data?.loan_officer || workspace?.loan_officer;

  // Fetch tasks and documents
  useEffect(() => {
    const fetchData = async () => {
      if (!slug) return;
      try {
        const [tasksRes, docsRes] = await Promise.all([
          api.get(`/api/purl/workspace/${slug}/tasks`).catch(() => ({ tasks: [] })),
          api.get(`/api/purl/workspace/${slug}/documents`).catch(() => ({ documents: [] })),
        ]);
        setTasks(tasksRes?.tasks || []);
        setDocuments(docsRes?.documents || []);
      } catch (err) {
        console.error('Error fetching portal data:', err);
      }
    };
    fetchData();
  }, [slug]);

  // Borrower info
  const borrowerName = borrower
    ? `${borrower.first_name || ''} ${borrower.last_name || ''}`.trim()
    : 'Borrower';
  const borrowerEmail = borrower?.email || '';
  const borrowerPhone = borrower?.phone || '';

  const propertyAddress = useMemo(() => {
    const addr = loan?.property_address;
    if (!addr) return '';
    if (typeof addr === 'string') return addr;
    return [addr.street, addr.city, addr.state, addr.zip].filter(Boolean).join(', ');
  }, [loan]);

  // Loan info
  const loanPurpose = loan?.loan_purpose || 'Purchase';
  const loanType = loan?.loan_type || loan?.product_type || 'Conventional';
  const loanTerm = loan?.term_months ? `${loan.term_months / 12} yr Fixed` : '30 yr Fixed';
  const loanAmount = loan?.loan_amount || 0;
  const interestRate = loan?.interest_rate;
  const rateLock = loan?.lock_expiration_date ? 'Locked' : 'Not Locked';
  const estClosing = loan?.closing_date;
  const scheduledClosing = loan?.scheduled_closing_date || loan?.closing_date;
  const estPayment = loan?.monthly_payment;

  // Determine progress step
  const currentStep = useMemo(() => {
    const stage = loan?.stage?.toUpperCase() || workspace?.status?.toUpperCase() || '';
    if (stage === 'CLOSING' || stage === 'DOCS' || stage === 'DOCS_OUT' || stage === 'FUNDED') return 5;
    if (stage === 'CTC' || stage === 'CLEAR_TO_CLOSE') return 4;
    if (stage === 'APPROVED' || stage === 'CONDITIONAL_APPROVAL') return 3;
    if (stage === 'UNDERWRITING' || stage === 'UW_RECEIVED' || stage === 'SUBMITTED') return 2;
    if (stage === 'PROCESSING' || stage === 'DISCLOSED') return 1;
    return 0;
  }, [loan, workspace]);

  // Days until closing
  const closingDate = estClosing || scheduledClosing;

  // Action items — use real tasks if available, else defaults
  const actionItems = useMemo(() => {
    if (tasks.length > 0) {
      return tasks.map(t => ({
        id: t.id,
        icon: t.task_type === 'upload' ? 'upload' : t.task_type === 'sign' ? 'sign' : t.task_type === 'review' ? 'review' : 'document',
        title: t.title,
        description: t.description || '',
        dueDate: t.due_at || t.due_date,
        status: t.status || 'pending',
      }));
    }
    return [
      { id: 'ins-dec', icon: 'upload', title: 'Upload homeowners insurance declaration', description: 'Upload your homeowners insurance declaration page', dueDate: null, status: 'pending' },
      { id: 'pnl', icon: 'upload', title: 'Upload profit and loss statement', description: "Upload this year's P&L statement", dueDate: null, status: 'pending' },
      { id: 'appraisal', icon: 'review', title: 'Complete appraisal report review', description: 'Review all repairs on your appraisal report', dueDate: null, status: 'pending' },
      { id: 'fha-addendum', icon: 'sign', title: 'Sign FHA Purchase Addendum', description: 'Seller-signed FHA addendum needed', dueDate: null, status: 'pending' },
    ];
  }, [tasks]);

  const pendingItems = actionItems.filter(i => i.status !== 'completed');

  // Recent activity
  const recentActivity = useMemo(() => {
    const activities = [];
    if (loan?.appraisal_received_date) {
      activities.push({ label: 'Appraisal ordered', date: loan.appraisal_received_date });
    }
    if (loan?.initial_disclosures_sent_date) {
      activities.push({ label: 'Disclosures sent', date: loan.initial_disclosures_sent_date });
    }
    if (activities.length === 0) {
      activities.push(
        { label: 'Appraisal ordered', date: '2026-02-10' },
        { label: 'Documents received', date: '2026-02-06' },
        { label: 'Application submitted', date: '2026-01-15' },
      );
    }
    return activities;
  }, [loan]);

  // Contacts
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
    { id: 'action-items', label: 'Action Items' },
    { id: 'documents', label: 'Documents' },
    { id: 'loan-details', label: 'Loan Details' },
    { id: 'closing', label: 'Closing' },
    { id: 'contacts', label: 'Contacts' },
  ];

  return (
    <div className="active-loan-portal">
      {/* Borrower Header Card */}
      <div className="borrower-header-card">
        <div className="borrower-info">
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
        </div>

        <DaysUntilClosing closingDate={closingDate} />

        <div className="header-footer-row">
          <span className="property-address">{propertyAddress || 'Address pending'}</span>
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
            <span className="info-value">{interestRate ? `${interestRate}%` : 'TBD'}</span>
          </div>
          <div className="info-cell">
            <span className="info-label">RATE LOCK</span>
            <span className="info-value">{rateLock}</span>
          </div>
          <div className="info-cell">
            <span className="info-label">EST. CLOSING</span>
            <span className="info-value">{estClosing ? formatDate(estClosing) : 'TBD'}</span>
          </div>
          <div className="info-cell">
            <span className="info-label">SCHEDULED</span>
            <span className="info-value">{scheduledClosing ? formatDate(scheduledClosing) : 'TBD'}</span>
          </div>
          <div className="info-cell">
            <span className="info-label">EST. PAYMENT</span>
            <span className="info-value">{estPayment ? `${formatCurrency(estPayment)}/mo` : 'TBD'}</span>
          </div>
        </div>
        <div className="stepper-container">
          <LoanProgressStepper currentStep={currentStep} />
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
                  {pendingItems.length > 0 && (
                    <span className="items-badge">{pendingItems.length} ITEMS TO COMPLETE</span>
                  )}
                </div>
                <div className="action-items-list">
                  {actionItems.map((item) => (
                    <div key={item.id} className={`action-item ${item.status === 'completed' ? 'completed' : ''}`}>
                      <ActionItemIcon type={item.icon} />
                      <div className="action-item-content">
                        <span className={`action-item-title ${item.status === 'completed' ? 'done' : ''}`}>
                          {item.title}
                        </span>
                        <span className="action-item-description">{item.description}</span>
                      </div>
                      <div className="action-item-meta">
                        {item.status === 'completed' ? (
                          <span className="done-badge">DONE</span>
                        ) : item.dueDate ? (
                          <span className="due-date">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                              <circle cx="12" cy="12" r="10" />
                              <polyline points="12 6 12 12 16 14" />
                            </svg>
                            {formatShortDate(item.dueDate)}
                          </span>
                        ) : null}
                        <button className="view-link" onClick={() => toast.info('Details coming soon')}>
                          View &rsaquo;
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Recent Activity Sidebar */}
            <div className="overview-sidebar">
              <div className="recent-activity-card">
                <h3>Recent Activity</h3>
                <div className="activity-list">
                  {recentActivity.map((activity, idx) => (
                    <div key={idx} className="activity-item">
                      <span className="activity-label">{activity.label}</span>
                      <span className="activity-date"> — {formatShortDate(activity.date)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ===== ACTION ITEMS TAB ===== */}
        {activeTab === 'action-items' && (
          <div className="action-items-full-tab">
            <h2>All Action Items</h2>
            <div className="action-items-card">
              <div className="action-items-list">
                {actionItems.map((item) => (
                  <div key={item.id} className={`action-item ${item.status === 'completed' ? 'completed' : ''}`}>
                    <ActionItemIcon type={item.icon} />
                    <div className="action-item-content">
                      <span className={`action-item-title ${item.status === 'completed' ? 'done' : ''}`}>
                        {item.title}
                      </span>
                      <span className="action-item-description">{item.description}</span>
                    </div>
                    <div className="action-item-meta">
                      {item.status === 'completed' ? (
                        <span className="done-badge">DONE</span>
                      ) : item.dueDate ? (
                        <span className="due-date">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                            <circle cx="12" cy="12" r="10" />
                            <polyline points="12 6 12 12 16 14" />
                          </svg>
                          {formatShortDate(item.dueDate)}
                        </span>
                      ) : null}
                      <button className="view-link" onClick={() => toast.info('Details coming soon')}>
                        View &rsaquo;
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ===== DOCUMENTS TAB ===== */}
        {activeTab === 'documents' && (
          <div className="documents-tab">
            <h2>Documents</h2>
            {documents.length > 0 ? (
              <div className="documents-list">
                {documents.map((doc) => (
                  <div key={doc.id} className="document-row">
                    <div className="doc-icon">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                      </svg>
                    </div>
                    <div className="doc-info">
                      <span className="doc-name">{doc.file_name || doc.doc_type}</span>
                      <span className="doc-meta">{doc.doc_type?.replace(/_/g, ' ')} · {formatShortDate(doc.created_at)}</span>
                    </div>
                    <button className="download-btn" onClick={() => toast.info('Download coming soon')}>
                      Download
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <h3>No Documents Yet</h3>
                <p>Documents related to your loan will appear here as they become available.</p>
              </div>
            )}
          </div>
        )}

        {/* ===== LOAN DETAILS TAB ===== */}
        {activeTab === 'loan-details' && (
          <div className="loan-details-tab">
            <h2>Loan Details</h2>
            <div className="details-grid">
              <div className="detail-row">
                <span className="detail-label">Loan Purpose</span>
                <span className="detail-value">{loanPurpose}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Loan Type</span>
                <span className="detail-value">{loanType}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Loan Amount</span>
                <span className="detail-value">{formatCurrency(loanAmount)}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Interest Rate</span>
                <span className="detail-value">{interestRate ? `${interestRate}%` : 'TBD'}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Term</span>
                <span className="detail-value">{loanTerm}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Rate Lock Status</span>
                <span className="detail-value">{rateLock}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Est. Monthly Payment</span>
                <span className="detail-value">{estPayment ? `${formatCurrency(estPayment)}/mo` : 'TBD'}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Expected Closing</span>
                <span className="detail-value">{estClosing ? formatDate(estClosing) : 'TBD'}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Property Address</span>
                <span className="detail-value">{propertyAddress || 'TBD'}</span>
              </div>
            </div>
          </div>
        )}

        {/* ===== CLOSING TAB ===== */}
        {activeTab === 'closing' && (
          <div className="closing-tab">
            <h2>Closing</h2>
            <div className="closing-info-card">
              <div className="closing-status">
                <LoanProgressStepper currentStep={currentStep} />
              </div>
              <div className="closing-details">
                <div className="detail-row">
                  <span className="detail-label">Closing Date</span>
                  <span className="detail-value">{closingDate ? formatDate(closingDate) : 'TBD'}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Title Company</span>
                  <span className="detail-value">{loan?.title_company || 'TBD'}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Closing Location</span>
                  <span className="detail-value">{loan?.closing_location || 'TBD'}</span>
                </div>
              </div>
            </div>
            {currentStep < 4 && (
              <div className="closing-note">
                <p>Closing details will be finalized once your loan reaches Clear to Close status. Your loan officer will provide specific instructions.</p>
              </div>
            )}
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
