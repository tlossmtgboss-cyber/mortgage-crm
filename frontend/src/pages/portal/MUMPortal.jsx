/**
 * MUM Portal (Mortgages Under Management)
 *
 * Post-close borrower portal matching the design mockup:
 * - Header card with borrower info + Est. Property Value + Est. Net Worth
 * - Loan stats grid (term, balance, rate, payment, taxes, insurance)
 * - Tab navigation: Overview, Referrals, Documents, Loan Details, Contacts
 * - Action items checklist with due dates and status
 * - Recent Activity sidebar
 */

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { mumPortalAPI } from '../../services/api';
import { api } from '../../lib/api';
import ScheduleAppointmentModal from '../../components/ScheduleAppointmentModal';
import './MUMPortal.css';
import { toast } from '../../utils/toast';

// Helper functions
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

const formatPhone = (phone) => {
  if (!phone) return '';
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  return phone;
};

// Default post-close action items
const getDefaultActionItems = (postcloseData) => {
  const items = [
    {
      id: 'autopay',
      icon: 'document',
      title: 'Set up autopay for mortgage',
      description: 'Ensure on-time payments with automatic billing',
      dueDate: null,
      status: 'pending',
      priority: 'high',
    },
    {
      id: 'homestead',
      icon: 'document',
      title: 'File homestead exemption',
      description: 'Reduce your property taxes — deadline varies by county',
      dueDate: null,
      status: 'pending',
      priority: 'high',
    },
    {
      id: 'insurance',
      icon: 'shield',
      title: 'Update homeowners insurance policy',
      description: 'Confirm dwelling coverage matches property value',
      dueDate: null,
      status: 'pending',
      priority: 'medium',
    },
    {
      id: 'review',
      icon: 'star',
      title: 'Leave a review for your loan team',
      description: 'Share your experience to help future homebuyers',
      dueDate: null,
      status: 'pending',
      priority: 'low',
    },
    {
      id: 'referral',
      icon: 'gift',
      title: 'Refer a friend — earn $500',
      description: 'Share your unique link with anyone buying a home',
      dueDate: null,
      status: 'pending',
      priority: 'low',
    },
    {
      id: 'closing-docs',
      icon: 'alert',
      title: 'Review your closing documents',
      description: 'Verify all final figures match your Closing Disclosure',
      dueDate: null,
      status: 'pending',
      priority: 'high',
    },
    {
      id: 'escrow',
      icon: 'calendar',
      title: 'Confirm escrow account setup',
      description: 'Verify that taxes and insurance are escrowed correctly',
      dueDate: null,
      status: 'pending',
      priority: 'medium',
    },
    {
      id: 'save-docs',
      icon: 'check',
      title: 'Save your mortgage documents',
      description: 'Download and store all loan documents securely',
      dueDate: null,
      status: 'completed',
      priority: 'low',
    },
  ];

  // Merge with real tasks from API if available
  if (postcloseData?.tasks?.length > 0) {
    return postcloseData.tasks.map(t => ({
      id: t.id,
      icon: t.priority === 'high' ? 'alert' : 'document',
      title: t.title,
      description: t.description || '',
      dueDate: t.due_at,
      status: t.status || 'pending',
      priority: t.priority || 'medium',
    }));
  }

  return items;
};

// Icon component for action items
const ActionItemIcon = ({ type }) => {
  const icons = {
    document: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
      </svg>
    ),
    shield: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
    star: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
    ),
    gift: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 12 20 22 4 22 4 12" />
        <rect x="2" y="7" width="20" height="5" />
        <line x1="12" y1="22" x2="12" y2="7" />
        <path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z" />
        <path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z" />
      </svg>
    ),
    alert: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
    ),
    calendar: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="8" y1="2" x2="8" y2="6" />
        <line x1="3" y1="10" x2="21" y2="10" />
      </svg>
    ),
    check: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
        <polyline points="22 4 12 14.01 9 11.01" />
      </svg>
    ),
  };

  return (
    <div className={`action-icon action-icon-${type}`}>
      {icons[type] || icons.document}
    </div>
  );
};


/**
 * MUM Portal Component
 */
export default function MUMPortal({ data, slug, onRefresh }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [showScheduleModal, setShowScheduleModal] = useState(false);

  // Documents state
  const [documents, setDocuments] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(false);

  // Post-close real data from API
  const [postcloseData, setPostcloseData] = useState(null);

  // Fetch post-close data from API
  const fetchPostcloseData = useCallback(async () => {
    if (!slug) return;
    try {
      const result = await api.getPostcloseData(slug);
      setPostcloseData(result);
    } catch (err) {
      console.warn('Could not fetch post-close data:', err);
    }
  }, [slug]);

  // Fetch documents and post-close data
  useEffect(() => {
    const fetchDocs = async () => {
      if (!slug) return;
      setLoadingDocs(true);
      try {
        const docsRes = await mumPortalAPI.getDocuments(slug).catch(() => ({ documents: [] }));
        setDocuments(docsRes.documents || []);
      } catch (error) {
        console.error('Error fetching documents:', error);
      } finally {
        setLoadingDocs(false);
      }
    };

    fetchDocs();
    fetchPostcloseData();
  }, [slug, fetchPostcloseData]);

  // Extract data
  const workspace = data?.workspace;
  const loan = data?.loan;
  const contacts = data?.contacts || [];
  const borrower = contacts.find(c => c.contact_type === 'borrower') || contacts[0];
  const loanOfficer = data?.loan_officer || workspace?.loan_officer;

  // Compute property value and equity
  const propertyValue = useMemo(() => {
    if (postcloseData?.estimated_value) return postcloseData.estimated_value;
    const purchasePrice = loan?.purchase_price || loan?.loan_amount / 0.8 || 0;
    const daysSince = loan?.funded_at
      ? Math.floor((Date.now() - new Date(loan.funded_at)) / (1000 * 60 * 60 * 24))
      : 365;
    return Math.round(purchasePrice * Math.pow(1.035, daysSince / 365));
  }, [loan, postcloseData]);

  const currentBalance = useMemo(() => {
    if (postcloseData?.current_balance) return postcloseData.current_balance;
    return loan?.loan_amount || 0;
  }, [loan, postcloseData]);

  const netWorth = useMemo(() => {
    return propertyValue - currentBalance;
  }, [propertyValue, currentBalance]);

  const monthlyPayment = useMemo(() => {
    if (postcloseData?.monthly_payment) return postcloseData.monthly_payment;
    const amount = loan?.loan_amount || 0;
    const rate = (loan?.interest_rate || 6.5) / 100 / 12;
    const n = (loan?.term_months || 360);
    if (rate === 0) return amount / n;
    return Math.round(amount * (rate * Math.pow(1 + rate, n)) / (Math.pow(1 + rate, n) - 1));
  }, [loan, postcloseData]);

  // Loan term display
  const loanTerm = useMemo(() => {
    const months = loan?.term_months || 360;
    const years = months / 12;
    const type = loan?.product_type || loan?.loan_type || 'Fixed';
    return `${years} yr ${type}`;
  }, [loan]);

  // Anniversary date
  const anniversaryDate = useMemo(() => {
    if (postcloseData?.anniversary_date) return postcloseData.anniversary_date;
    if (loan?.funded_at) {
      const funded = new Date(loan.funded_at);
      const next = new Date(funded);
      next.setFullYear(next.getFullYear() + 1);
      while (next < new Date()) {
        next.setFullYear(next.getFullYear() + 1);
      }
      return next.toISOString();
    }
    return null;
  }, [loan, postcloseData]);

  // Action items
  const actionItems = useMemo(() => getDefaultActionItems(postcloseData), [postcloseData]);
  const pendingItems = actionItems.filter(i => i.status !== 'completed');

  // Property address
  const propertyAddress = useMemo(() => {
    const addr = loan?.property_address;
    if (!addr) return '';
    if (typeof addr === 'string') return addr;
    return [addr.street, addr.city, addr.state, addr.zip].filter(Boolean).join(', ');
  }, [loan]);

  // Recent activity (mock for now, can be fed from API)
  const recentActivity = useMemo(() => {
    const activities = [];
    if (loan?.appraisal_received_date) {
      activities.push({ label: 'Appraisal ordered', date: loan.appraisal_received_date });
    }
    if (postcloseData?.funded_date) {
      activities.push({ label: 'Loan funded', date: postcloseData.funded_date });
    }
    // Add some defaults if we have no real data
    if (activities.length === 0) {
      activities.push(
        { label: 'Appraisal ordered', date: '2026-02-10' },
        { label: 'Documents received', date: '2026-02-06' },
        { label: 'Application submitted', date: '2026-01-15' },
      );
    }
    return activities;
  }, [loan, postcloseData]);

  // Borrower info
  const borrowerName = borrower
    ? `${borrower.first_name || ''} ${borrower.last_name || ''}`.trim()
    : 'Homeowner';
  const borrowerEmail = borrower?.email || '';
  const borrowerPhone = borrower?.phone || '';

  // Contact list for Contacts tab
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
    // Co-borrower
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
    { id: 'referrals', label: 'Referrals' },
    { id: 'documents', label: 'Documents' },
    { id: 'loan-details', label: 'Loan Details' },
    { id: 'contacts', label: 'Contacts' },
  ];

  return (
    <div className="mum-portal">
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

        <div className="property-values">
          <div className="value-block">
            <span className="value-label">EST. PROPERTY VALUE</span>
            <span className="value-amount">{formatCurrency(propertyValue)}</span>
          </div>
          <div className="value-block net-worth">
            <span className="value-label">EST. NET WORTH</span>
            <span className="value-amount positive">{formatCurrency(netWorth)}</span>
          </div>
        </div>

        <div className="header-footer-row">
          <span className="property-address">{propertyAddress}</span>
          {anniversaryDate && (
            <span className="loan-anniversary">Loan Anniversary: {formatDate(anniversaryDate)}</span>
          )}
        </div>
      </div>

      {/* Loan Stats Grid */}
      <div className="loan-stats-grid">
        <div className="stat-cell">
          <span className="stat-label">TERM</span>
          <span className="stat-value">{loanTerm}</span>
        </div>
        <div className="stat-cell">
          <span className="stat-label">CURRENT BALANCE</span>
          <span className="stat-value">{formatCurrency(currentBalance, 2)}</span>
        </div>
        <div className="stat-cell">
          <span className="stat-label">INTEREST RATE</span>
          <span className="stat-value">{loan?.interest_rate ? `${loan.interest_rate}%` : '—'}</span>
        </div>
        <div className="stat-cell">
          <span className="stat-label">EST. PAYMENT</span>
          <span className="stat-value">{formatCurrency(monthlyPayment)}/mo</span>
        </div>
        <div className="stat-cell">
          <span className="stat-label">PROPERTY TAXES</span>
          <span className="stat-value">{loan?.property_taxes ? `${formatCurrency(loan.property_taxes)}/mo` : '—'}</span>
        </div>
        <div className="stat-cell">
          <span className="stat-label">HOMEOWNERS INSURANCE</span>
          <span className="stat-value">{loan?.homeowners_insurance ? `${formatCurrency(loan.homeowners_insurance)}/mo` : '—'}</span>
        </div>
        {loan?.flood_insurance && (
          <div className="stat-cell">
            <span className="stat-label">FLOOD INSURANCE</span>
            <span className="stat-value">{formatCurrency(loan.flood_insurance)}/mo</span>
          </div>
        )}
      </div>

      {/* Tab Navigation */}
      <nav className="mum-tab-bar">
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
      <div className="mum-tab-content">

        {/* ===== OVERVIEW TAB ===== */}
        {activeTab === 'overview' && (
          <div className="overview-layout">
            <div className="overview-main">
              {/* Questions / CTA Section */}
              <div className="questions-card">
                <div className="questions-left">
                  <h3>Questions about your loan?</h3>
                  <p>Your loan officer is here to help guide you through the process.</p>
                </div>
                <div className="questions-buttons">
                  <button
                    className="btn-payment"
                    onClick={() => {
                      const url = postcloseData?.servicer_portal || loan?.servicer_portal;
                      if (url) {
                        window.open(url, '_blank');
                      } else {
                        toast.info('Contact your servicer to make a payment');
                      }
                    }}
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="12" y1="1" x2="12" y2="23" />
                      <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
                    </svg>
                    Make a Payment
                  </button>
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
                      <span className="activity-date">— {formatShortDate(activity.date)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ===== REFERRALS TAB ===== */}
        {activeTab === 'referrals' && (
          <div className="referrals-tab">
            <div className="referral-hero">
              <h2>Refer a Friend, Earn $500</h2>
              <p>Know someone buying or refinancing? Share your unique referral link and earn a reward when they close.</p>
              <div className="referral-link-box">
                <input
                  type="text"
                  readOnly
                  value={`${window.location.origin}/refer/${slug}`}
                  className="referral-link-input"
                />
                <button
                  className="copy-btn"
                  onClick={() => {
                    navigator.clipboard.writeText(`${window.location.origin}/refer/${slug}`);
                    toast.success('Referral link copied!');
                  }}
                >
                  Copy Link
                </button>
              </div>
            </div>

            <div className="referral-stats">
              <div className="ref-stat">
                <span className="ref-stat-value">0</span>
                <span className="ref-stat-label">Referrals Sent</span>
              </div>
              <div className="ref-stat">
                <span className="ref-stat-value">0</span>
                <span className="ref-stat-label">In Progress</span>
              </div>
              <div className="ref-stat">
                <span className="ref-stat-value">$0</span>
                <span className="ref-stat-label">Earned</span>
              </div>
            </div>
          </div>
        )}

        {/* ===== DOCUMENTS TAB ===== */}
        {activeTab === 'documents' && (
          <div className="documents-tab">
            <h2>Your Documents</h2>
            <p className="tab-subtitle">Access your important mortgage documents anytime.</p>

            {loadingDocs ? (
              <div className="loading-state">
                <div className="spinner"></div>
                <p>Loading documents...</p>
              </div>
            ) : documents.length > 0 ? (
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
                      <span className="doc-meta">{doc.doc_type?.replace(/_/g, ' ')} · Added {formatShortDate(doc.created_at)}</span>
                    </div>
                    <button className="download-btn" onClick={() => toast.info('Document download coming soon')}>
                      Download
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <h3>No Documents Available</h3>
                <p>Your important mortgage documents will appear here. Contact your loan officer if you need specific documents.</p>
              </div>
            )}

            <div className="standard-docs-section">
              <h3>Common Mortgage Documents</h3>
              <div className="standard-docs-grid">
                {['Closing Disclosure', 'Promissory Note', 'Deed of Trust', 'Title Insurance Policy'].map(doc => (
                  <div key={doc} className="standard-doc-item">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="20" height="20">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                    </svg>
                    <span>{doc}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ===== LOAN DETAILS TAB ===== */}
        {activeTab === 'loan-details' && (
          <div className="loan-details-tab">
            <h2>Loan Details</h2>

            <div className="details-grid">
              <div className="detail-row">
                <span className="detail-label">Loan Type</span>
                <span className="detail-value">{loan?.product_type || loan?.loan_type || 'Conventional'}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Interest Rate</span>
                <span className="detail-value">{loan?.interest_rate ? `${loan.interest_rate}%` : '—'}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Original Loan Amount</span>
                <span className="detail-value">{formatCurrency(loan?.loan_amount)}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Current Balance</span>
                <span className="detail-value">{formatCurrency(currentBalance, 2)}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Purchase Price</span>
                <span className="detail-value">{formatCurrency(loan?.purchase_price)}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Closing Date</span>
                <span className="detail-value">{formatDate(loan?.funded_at || loan?.closing_date)}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Loan Term</span>
                <span className="detail-value">{loanTerm}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Monthly Payment</span>
                <span className="detail-value">{formatCurrency(monthlyPayment)}/mo</span>
              </div>
            </div>

            {/* Servicer Info */}
            <div className="servicer-card">
              <h3>Loan Servicer</h3>
              <p className="servicer-name">{postcloseData?.servicer || loan?.servicer || 'Contact your loan officer for servicer information'}</p>
              {(postcloseData?.servicer_phone || loan?.servicer_phone) && (
                <p className="servicer-phone">
                  <a href={`tel:${postcloseData?.servicer_phone || loan?.servicer_phone}`}>
                    {postcloseData?.servicer_phone || loan?.servicer_phone}
                  </a>
                </p>
              )}
              {(postcloseData?.servicer_portal || loan?.servicer_portal) && (
                <a
                  href={postcloseData?.servicer_portal || loan?.servicer_portal}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="servicer-link"
                >
                  Go to Servicer Portal →
                </a>
              )}
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
