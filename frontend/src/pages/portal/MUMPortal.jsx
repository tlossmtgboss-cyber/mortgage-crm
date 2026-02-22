/**
 * MUM Portal (Mortgages Under Management)
 *
 * Portal view for funded/closed loans - homeowner stage.
 * Focus on relationship maintenance, home value tracking, and refinance opportunities.
 *
 * Features:
 * - Home value intelligence (Zestimate-style with mock data)
 * - Equity tracker
 * - Refinance opportunity alerts
 * - Annual review scheduling
 * - Loan servicing information
 * - Resource center for homeowners
 * - Video messages from loan officer
 * - Document repository for important files
 */

import React, { useState, useMemo, useEffect } from 'react';
import { mumPortalAPI } from '../../services/api';
import ScheduleAppointmentModal from '../../components/ScheduleAppointmentModal';
import './MUMPortal.css';
import { toast } from '../../utils/toast';

// Helper functions
const formatCurrency = (amount) => {
  if (!amount) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
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

const formatPercent = (value, decimals = 2) => {
  if (value === null || value === undefined) return '-';
  return `${value.toFixed(decimals)}%`;
};

// Generate mock home value data based on loan info
const generateMockHomeData = (loan, workspace) => {
  const purchasePrice = loan?.purchase_price || loan?.loan_amount / 0.8 || 400000;
  const loanAmount = loan?.loan_amount || 320000;
  const purchaseDate = loan?.funded_at || loan?.closing_date || new Date(Date.now() - 365 * 24 * 60 * 60 * 1000).toISOString();

  // Calculate time since purchase
  const daysSincePurchase = Math.floor((Date.now() - new Date(purchaseDate)) / (1000 * 60 * 60 * 24));
  const yearsSincePurchase = daysSincePurchase / 365;

  // Mock appreciation (3-5% annually with some randomness)
  const appreciationRate = 0.04 + (Math.random() * 0.02 - 0.01);
  const currentValue = Math.round(purchasePrice * Math.pow(1 + appreciationRate, yearsSincePurchase));

  // Mock remaining balance (assume 30yr, estimate based on time)
  const monthsElapsed = Math.floor(daysSincePurchase / 30);
  const rate = loan?.interest_rate || 6.5;
  const monthlyRate = rate / 100 / 12;
  const totalPayments = 360; // 30 years
  const monthlyPayment = loanAmount * (monthlyRate * Math.pow(1 + monthlyRate, totalPayments)) / (Math.pow(1 + monthlyRate, totalPayments) - 1);

  // Estimate remaining balance (simplified)
  let remainingBalance = loanAmount;
  for (let i = 0; i < monthsElapsed; i++) {
    const interestPayment = remainingBalance * monthlyRate;
    const principalPayment = monthlyPayment - interestPayment;
    remainingBalance -= principalPayment;
  }
  remainingBalance = Math.max(0, remainingBalance);

  // Calculate equity
  const equity = currentValue - remainingBalance;
  const equityPercent = (equity / currentValue) * 100;
  const ltv = (remainingBalance / currentValue) * 100;

  // Mock value history (last 12 months)
  const valueHistory = [];
  for (let i = 11; i >= 0; i--) {
    const monthsAgo = i;
    const historicalValue = currentValue * Math.pow(1 - appreciationRate / 12, monthsAgo);
    const date = new Date();
    date.setMonth(date.getMonth() - monthsAgo);
    valueHistory.push({
      month: date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
      value: Math.round(historicalValue),
    });
  }

  // Mock comparable sales
  const comparables = [
    {
      address: '123 Oak Street',
      distance: '0.2 mi',
      soldPrice: Math.round(currentValue * (0.95 + Math.random() * 0.1)),
      soldDate: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toLocaleDateString(),
      sqft: Math.round(1800 + Math.random() * 400),
      beds: 3,
      baths: 2,
    },
    {
      address: '456 Maple Ave',
      distance: '0.4 mi',
      soldPrice: Math.round(currentValue * (0.9 + Math.random() * 0.15)),
      soldDate: new Date(Date.now() - 45 * 24 * 60 * 60 * 1000).toLocaleDateString(),
      sqft: Math.round(1700 + Math.random() * 500),
      beds: 4,
      baths: 2.5,
    },
    {
      address: '789 Elm Court',
      distance: '0.5 mi',
      soldPrice: Math.round(currentValue * (0.92 + Math.random() * 0.12)),
      soldDate: new Date(Date.now() - 60 * 24 * 60 * 60 * 1000).toLocaleDateString(),
      sqft: Math.round(1900 + Math.random() * 300),
      beds: 3,
      baths: 2,
    },
  ];

  return {
    currentValue,
    purchasePrice,
    appreciation: currentValue - purchasePrice,
    appreciationPercent: ((currentValue - purchasePrice) / purchasePrice) * 100,
    remainingBalance: Math.round(remainingBalance),
    equity: Math.round(equity),
    equityPercent,
    ltv,
    monthlyPayment: Math.round(monthlyPayment),
    valueHistory,
    comparables,
    lastUpdated: new Date().toISOString(),
    confidenceLevel: 'Medium-High',
    valueRange: {
      low: Math.round(currentValue * 0.95),
      high: Math.round(currentValue * 1.05),
    },
  };
};

// Check if refinance might benefit the homeowner
const checkRefinanceOpportunity = (loan, homeData) => {
  const currentRate = loan?.interest_rate || 7;
  const marketRate = 6.5; // Mock current market rate

  const opportunities = [];

  // Rate reduction opportunity
  if (currentRate - marketRate >= 0.5) {
    const monthlySavings = Math.round(homeData.monthlyPayment * (currentRate - marketRate) / 100 * 10);
    opportunities.push({
      type: 'rate_reduction',
      title: 'Lower Your Rate',
      description: `Rates have dropped! You could save ~${formatCurrency(monthlySavings)}/month by refinancing.`,
      savings: monthlySavings * 12,
      priority: 'high',
    });
  }

  // Cash-out opportunity
  if (homeData.equityPercent >= 30) {
    const availableEquity = Math.round(homeData.equity * 0.8 - homeData.remainingBalance * 0.2);
    if (availableEquity > 50000) {
      opportunities.push({
        type: 'cash_out',
        title: 'Access Your Equity',
        description: `You have significant equity. Consider a cash-out refinance for home improvements or debt consolidation.`,
        equity: availableEquity,
        priority: 'medium',
      });
    }
  }

  // Remove PMI opportunity
  if (homeData.ltv < 80 && loan?.has_pmi) {
    opportunities.push({
      type: 'remove_pmi',
      title: 'Remove PMI',
      description: `Your LTV is ${homeData.ltv.toFixed(1)}%. You may be eligible to remove PMI and save monthly.`,
      priority: 'medium',
    });
  }

  return opportunities;
};

// Home Value Card Component
const HomeValueCard = ({ homeData, address }) => {
  const valueChange = homeData.appreciationPercent;
  const isPositive = valueChange >= 0;

  return (
    <div className="home-value-card">
      <div className="value-header">
        <div className="value-icon">🏠</div>
        <div className="value-address">
          <h3>Your Home</h3>
          <p>{address || 'Your Property'}</p>
        </div>
      </div>

      <div className="value-main">
        <div className="estimated-value">
          <span className="value-label">Estimated Value</span>
          <span className="value-amount">{formatCurrency(homeData.currentValue)}</span>
          <span className="value-range">
            Range: {formatCurrency(homeData.valueRange.low)} - {formatCurrency(homeData.valueRange.high)}
          </span>
        </div>

        <div className="value-change">
          <span className={`change-badge ${isPositive ? 'positive' : 'negative'}`}>
            {isPositive ? '↑' : '↓'} {formatCurrency(Math.abs(homeData.appreciation))}
            <span className="change-percent">({formatPercent(Math.abs(valueChange))})</span>
          </span>
          <span className="change-label">Since Purchase</span>
        </div>
      </div>

      <div className="value-confidence">
        <span>Confidence: {homeData.confidenceLevel}</span>
        <span className="last-updated">Updated: {formatDate(homeData.lastUpdated)}</span>
      </div>
    </div>
  );
};

// Equity Tracker Component
const EquityTracker = ({ homeData }) => {
  const equityWidth = Math.min(100, homeData.equityPercent);
  const debtWidth = 100 - equityWidth;

  return (
    <div className="equity-tracker">
      <h3>Your Equity Position</h3>

      <div className="equity-visual">
        <div className="equity-bar">
          <div className="equity-portion" style={{ width: `${equityWidth}%` }}>
            <span>Equity</span>
          </div>
          <div className="debt-portion" style={{ width: `${debtWidth}%` }}>
            <span>Mortgage</span>
          </div>
        </div>
      </div>

      <div className="equity-details">
        <div className="equity-stat">
          <span className="stat-value positive">{formatCurrency(homeData.equity)}</span>
          <span className="stat-label">Your Equity</span>
        </div>
        <div className="equity-stat">
          <span className="stat-value">{formatCurrency(homeData.remainingBalance)}</span>
          <span className="stat-label">Remaining Balance</span>
        </div>
        <div className="equity-stat">
          <span className="stat-value">{formatPercent(homeData.equityPercent)}</span>
          <span className="stat-label">Equity %</span>
        </div>
        <div className="equity-stat">
          <span className="stat-value">{formatPercent(homeData.ltv)}</span>
          <span className="stat-label">Loan-to-Value</span>
        </div>
      </div>
    </div>
  );
};

// Opportunity Card Component
const OpportunityCard = ({ opportunity, onSchedule }) => {
  const priorityColors = {
    high: 'emerald',
    medium: 'blue',
    low: 'gray',
  };

  return (
    <div className={`opportunity-card priority-${priorityColors[opportunity.priority]}`}>
      <div className="opportunity-badge">{opportunity.priority === 'high' ? 'Recommended' : 'Available'}</div>
      <h4>{opportunity.title}</h4>
      <p>{opportunity.description}</p>
      <div className="opportunity-actions">
        <button className="learn-more-btn" onClick={onSchedule}>
          Learn More
        </button>
      </div>
    </div>
  );
};

// Loan Details Component
const LoanDetailsCard = ({ loan }) => (
  <div className="loan-details-card">
    <h3>Your Loan Details</h3>
    <div className="loan-details-grid">
      <div className="detail-item">
        <span className="detail-label">Loan Type</span>
        <span className="detail-value">{loan?.product_type || 'Conventional'}</span>
      </div>
      <div className="detail-item">
        <span className="detail-label">Interest Rate</span>
        <span className="detail-value">{loan?.interest_rate ? `${loan.interest_rate}%` : '-'}</span>
      </div>
      <div className="detail-item">
        <span className="detail-label">Original Amount</span>
        <span className="detail-value">{formatCurrency(loan?.loan_amount)}</span>
      </div>
      <div className="detail-item">
        <span className="detail-label">Closing Date</span>
        <span className="detail-value">{formatDate(loan?.funded_at || loan?.closing_date)}</span>
      </div>
    </div>

    {loan?.servicer && (
      <div className="servicer-info">
        <h4>Loan Servicer</h4>
        <p>{loan.servicer}</p>
        {loan?.servicer_phone && <p className="servicer-contact">Contact: {loan.servicer_phone}</p>}
      </div>
    )}
  </div>
);

// Comparables Component
const ComparablesCard = ({ comparables }) => (
  <div className="comparables-card">
    <h3>Recent Sales Nearby</h3>
    <p className="comparables-subtitle">These recent sales help determine your home's value.</p>

    <div className="comparables-list">
      {comparables.map((comp, index) => (
        <div key={index} className="comparable-item">
          <div className="comp-address">
            <strong>{comp.address}</strong>
            <span className="comp-distance">{comp.distance}</span>
          </div>
          <div className="comp-details">
            <span>{comp.beds} bed • {comp.baths} bath • {comp.sqft.toLocaleString()} sqft</span>
            <span className="comp-date">Sold {comp.soldDate}</span>
          </div>
          <div className="comp-price">{formatCurrency(comp.soldPrice)}</div>
        </div>
      ))}
    </div>
  </div>
);

// Resources Section
const HomeownerResources = () => (
  <div className="homeowner-resources">
    <h3>Homeowner Resources</h3>
    <div className="resources-grid">
      <button type="button" className="resource-link" onClick={() => window.open('https://www.houselogic.com/organize-maintain/home-maintenance-tips/', '_blank')}>
        <span className="resource-icon">🔧</span>
        <span>Home Maintenance Tips</span>
      </button>
      <button type="button" className="resource-link" onClick={() => window.open('https://www.irs.gov/credits-deductions/individuals', '_blank')}>
        <span className="resource-icon">📋</span>
        <span>Tax Deduction Guide</span>
      </button>
      <button type="button" className="resource-link" onClick={() => toast.info('Insurance review coming soon!')}>
        <span className="resource-icon">🛡️</span>
        <span>Insurance Review</span>
      </button>
      <button type="button" className="resource-link" onClick={() => toast.info('Renovation calculator coming soon!')}>
        <span className="resource-icon">🏗️</span>
        <span>Renovation ROI Calculator</span>
      </button>
    </div>
  </div>
);

/**
 * MUM Portal Component
 *
 * Props from PortalContainer:
 * - data: Workspace data including loan info
 * - slug: Workspace slug
 * - onRefresh: Callback to refresh data
 */
export default function MUMPortal({ data, slug, onRefresh }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [showScheduleModal, setShowScheduleModal] = useState(false);

  // Messages, Videos, Documents state
  const [videos, setVideos] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [messages, setMessages] = useState([]);
  const [loadingMedia, setLoadingMedia] = useState(false);

  // Fetch videos, documents, and messages
  useEffect(() => {
    const fetchMediaContent = async () => {
      if (!slug) return;

      setLoadingMedia(true);
      try {
        const [videosRes, docsRes, msgsRes] = await Promise.all([
          mumPortalAPI.getVideos(slug).catch(() => ({ videos: [] })),
          mumPortalAPI.getDocuments(slug).catch(() => ({ documents: [] })),
          mumPortalAPI.getMessages(slug).catch(() => ({ messages: [] })),
        ]);

        setVideos(videosRes.videos || []);
        setDocuments(docsRes.documents || []);
        setMessages(msgsRes.messages || []);
      } catch (error) {
        console.error('Error fetching MUM portal content:', error);
      } finally {
        setLoadingMedia(false);
      }
    };

    fetchMediaContent();
  }, [slug]);

  // Handle video viewed
  const handleVideoViewed = async (videoId) => {
    try {
      await mumPortalAPI.markVideoViewed(slug, videoId);
      setVideos(prev => prev.map(v =>
        v.id === videoId ? { ...v, is_viewed: true, viewed_at: new Date().toISOString() } : v
      ));
    } catch (error) {
      console.error('Error marking video viewed:', error);
    }
  };

  // Handle message read
  const handleMessageRead = async (messageId) => {
    try {
      await mumPortalAPI.markMessageRead(slug, messageId);
      setMessages(prev => prev.map(m =>
        m.id === messageId ? { ...m, is_read: true } : m
      ));
    } catch (error) {
      console.error('Error marking message read:', error);
    }
  };

  // Extract data
  const workspace = data?.workspace;
  const loan = data?.loan;
  const contacts = data?.contacts || [];
  const borrower = contacts.find(c => c.contact_type === 'borrower') || contacts[0];
  const loanOfficer = data?.loan_officer || workspace?.loan_officer;

  // Generate mock home value data
  const homeData = useMemo(() => generateMockHomeData(loan, workspace), [loan, workspace]);

  // Check for refinance opportunities
  const opportunities = useMemo(() => checkRefinanceOpportunity(loan, homeData), [loan, homeData]);

  // Format property address
  const propertyAddress = useMemo(() => {
    const addr = loan?.property_address;
    if (!addr) return 'Your Property';
    if (typeof addr === 'string') return addr;
    return [addr.street, addr.city, addr.state].filter(Boolean).join(', ');
  }, [loan]);

  const borrowerName = borrower?.first_name || 'Homeowner';

  return (
    <div className="mum-portal">
      {/* Header */}
      <header className="mum-header">
        <div className="header-content">
          <div className="welcome-message">
            <h1>Welcome back, {borrowerName}!</h1>
            <p>Here's your home value intelligence dashboard.</p>
          </div>

          <div className="header-actions">
            <button className="schedule-btn" onClick={() => setShowScheduleModal(true)}>
              <span>📅</span> Annual Review
            </button>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="mum-nav">
        <button
          className={`nav-btn ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`nav-btn ${activeTab === 'equity' ? 'active' : ''}`}
          onClick={() => setActiveTab('equity')}
        >
          Equity & Value
        </button>
        <button
          className={`nav-btn ${activeTab === 'opportunities' ? 'active' : ''}`}
          onClick={() => setActiveTab('opportunities')}
        >
          Opportunities
          {opportunities.length > 0 && <span className="nav-badge">{opportunities.length}</span>}
        </button>
        <button
          className={`nav-btn ${activeTab === 'loan' ? 'active' : ''}`}
          onClick={() => setActiveTab('loan')}
        >
          Loan Details
        </button>
        <button
          className={`nav-btn ${activeTab === 'messages' ? 'active' : ''}`}
          onClick={() => setActiveTab('messages')}
        >
          Messages
          {(videos.length + messages.length) > 0 && (
            <span className="nav-badge">{videos.length + messages.length}</span>
          )}
        </button>
        <button
          className={`nav-btn ${activeTab === 'documents' ? 'active' : ''}`}
          onClick={() => setActiveTab('documents')}
        >
          Documents
          {documents.length > 0 && <span className="nav-badge">{documents.length}</span>}
        </button>
      </nav>

      {/* Main Content */}
      <main className="mum-content">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="overview-tab">
            <div className="overview-grid">
              {/* Main Column */}
              <div className="main-column">
                <HomeValueCard homeData={homeData} address={propertyAddress} />
                <EquityTracker homeData={homeData} />

                {/* Opportunity Highlights */}
                {opportunities.length > 0 && (
                  <div className="opportunity-highlight">
                    <h3>Opportunities For You</h3>
                    <div className="opportunities-preview">
                      {opportunities.slice(0, 2).map((opp, index) => (
                        <OpportunityCard
                          key={index}
                          opportunity={opp}
                          onSchedule={() => setShowScheduleModal(true)}
                        />
                      ))}
                    </div>
                    {opportunities.length > 2 && (
                      <button className="view-all-btn" onClick={() => setActiveTab('opportunities')}>
                        View All {opportunities.length} Opportunities →
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* Sidebar */}
              <div className="sidebar-column">
                {/* Quick Stats */}
                <div className="quick-stats-card">
                  <h3>At a Glance</h3>
                  <div className="stat-row">
                    <span className="stat-label">Monthly Payment</span>
                    <span className="stat-value">{formatCurrency(homeData.monthlyPayment)}</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Next Payment</span>
                    <span className="stat-value">Jan 1, 2025</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Remaining Term</span>
                    <span className="stat-value">28 years</span>
                  </div>
                </div>

                {/* Contact Card */}
                {loanOfficer && (
                  <div className="lo-card">
                    <h4>Your Loan Officer</h4>
                    <p className="lo-name">{loanOfficer.name}</p>
                    {loanOfficer.email && (
                      <a href={`mailto:${loanOfficer.email}`} className="lo-contact">
                        {loanOfficer.email}
                      </a>
                    )}
                    {loanOfficer.phone && (
                      <a href={`tel:${loanOfficer.phone}`} className="lo-contact">
                        {loanOfficer.phone}
                      </a>
                    )}
                    <button
                      className="contact-lo-btn"
                      onClick={() => setShowScheduleModal(true)}
                    >
                      Schedule a Call
                    </button>
                  </div>
                )}

                <HomeownerResources />
              </div>
            </div>
          </div>
        )}

        {/* Equity & Value Tab */}
        {activeTab === 'equity' && (
          <div className="equity-tab">
            <HomeValueCard homeData={homeData} address={propertyAddress} />

            {/* Value History Chart Placeholder */}
            <div className="value-history-card">
              <h3>Value History</h3>
              <div className="value-chart">
                {homeData.valueHistory.map((point, index) => (
                  <div key={index} className="chart-bar-container">
                    <div
                      className="chart-bar"
                      style={{
                        height: `${((point.value - homeData.purchasePrice * 0.9) / (homeData.currentValue * 0.2)) * 100}%`,
                      }}
                    />
                    <span className="chart-label">{point.month}</span>
                  </div>
                ))}
              </div>
            </div>

            <EquityTracker homeData={homeData} />
            <ComparablesCard comparables={homeData.comparables} />
          </div>
        )}

        {/* Opportunities Tab */}
        {activeTab === 'opportunities' && (
          <div className="opportunities-tab">
            <div className="opportunities-header">
              <h2>Your Opportunities</h2>
              <p>Based on your current home value and market conditions.</p>
            </div>

            {opportunities.length === 0 ? (
              <div className="no-opportunities">
                <div className="no-opp-icon">✓</div>
                <h3>You're in Great Shape!</h3>
                <p>No immediate refinance opportunities at this time. We'll notify you when market conditions change.</p>
              </div>
            ) : (
              <div className="opportunities-list">
                {opportunities.map((opp, index) => (
                  <div key={index} className="opportunity-detail-card">
                    <div className="opp-header">
                      <h3>{opp.title}</h3>
                      <span className={`opp-priority priority-${opp.priority}`}>
                        {opp.priority === 'high' ? 'Recommended' : 'Available'}
                      </span>
                    </div>
                    <p>{opp.description}</p>
                    {opp.savings && (
                      <div className="opp-savings">
                        <span>Potential Annual Savings:</span>
                        <strong>{formatCurrency(opp.savings)}</strong>
                      </div>
                    )}
                    {opp.equity && (
                      <div className="opp-equity">
                        <span>Available Equity:</span>
                        <strong>{formatCurrency(opp.equity)}</strong>
                      </div>
                    )}
                    <button
                      className="opp-action-btn"
                      onClick={() => setShowScheduleModal(true)}
                    >
                      Schedule Consultation
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Loan Details Tab */}
        {activeTab === 'loan' && (
          <div className="loan-tab">
            <LoanDetailsCard loan={loan} />

            <div className="payment-history">
              <h3>Payment Information</h3>
              <div className="payment-info">
                <p>
                  Your loan is currently serviced by{' '}
                  <strong>{loan?.servicer || 'your loan servicer'}</strong>.
                  Contact them directly for payment questions or to make a payment.
                </p>
                {loan?.servicer_portal && (
                  <a
                    href={loan.servicer_portal}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="servicer-portal-btn"
                  >
                    Go to Servicer Portal →
                  </a>
                )}
              </div>
            </div>

            <div className="documents-section">
              <h3>Important Documents</h3>
              <div className="document-links">
                <button type="button" className="doc-link" onClick={() => toast.info('Document access coming soon!')}>
                  <span>📄</span> Closing Disclosure
                </button>
                <button type="button" className="doc-link" onClick={() => toast.info('Document access coming soon!')}>
                  <span>📄</span> Promissory Note
                </button>
                <button type="button" className="doc-link" onClick={() => toast.info('Document access coming soon!')}>
                  <span>📄</span> Deed of Trust
                </button>
                <button type="button" className="doc-link" onClick={() => toast.info('Document access coming soon!')}>
                  <span>📄</span> Title Insurance Policy
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Messages Tab - Videos and Text Messages from LO */}
        {activeTab === 'messages' && (
          <div className="messages-tab">
            <div className="messages-header">
              <h2>Messages From Your Loan Officer</h2>
              <p>Stay connected with personalized video and text updates from your team.</p>
            </div>

            {loadingMedia ? (
              <div className="messages-loading">
                <div className="spinner"></div>
                <p>Loading messages...</p>
              </div>
            ) : (
              <>
                {/* Video Messages Section */}
                {videos.length > 0 && (
                  <div className="video-messages-section">
                    <h3>Video Messages</h3>
                    <div className="video-grid">
                      {videos.map((video) => (
                        <div key={video.id} className={`video-card ${video.is_viewed ? 'viewed' : 'unviewed'}`}>
                          <div className="video-thumbnail" onClick={() => handleVideoViewed(video.id)}>
                            {video.thumbnail_url ? (
                              <img src={video.thumbnail_url} alt={video.title} />
                            ) : (
                              <div className="video-placeholder">
                                <span className="play-icon">▶</span>
                              </div>
                            )}
                            {!video.is_viewed && <span className="new-badge">NEW</span>}
                            {video.duration_seconds && (
                              <span className="video-duration">
                                {Math.floor(video.duration_seconds / 60)}:{String(video.duration_seconds % 60).padStart(2, '0')}
                              </span>
                            )}
                          </div>
                          <div className="video-info">
                            <h4>{video.title || 'Video Message'}</h4>
                            {video.description && <p>{video.description}</p>}
                            <div className="video-meta">
                              <span className="sender">{video.sender_name || loanOfficer?.name || 'Your Loan Officer'}</span>
                              <span className="date">{formatDate(video.created_at)}</span>
                            </div>
                          </div>
                          {video.video_url && (
                            <a
                              href={video.video_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="watch-btn"
                              onClick={() => handleVideoViewed(video.id)}
                            >
                              Watch Video
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Text Messages Section */}
                {messages.length > 0 && (
                  <div className="text-messages-section">
                    <h3>Updates & Announcements</h3>
                    <div className="messages-list">
                      {messages.map((message) => (
                        <div
                          key={message.id}
                          className={`message-card ${message.is_read ? 'read' : 'unread'}`}
                          onClick={() => !message.is_read && handleMessageRead(message.id)}
                        >
                          <div className="message-icon">
                            {message.message_type === 'update' ? '📢' :
                             message.message_type === 'alert' ? '⚠️' :
                             message.message_type === 'announcement' ? '📣' : '💬'}
                          </div>
                          <div className="message-content">
                            <p>{message.content}</p>
                            <span className="message-date">{formatDate(message.created_at)}</span>
                          </div>
                          {!message.is_read && <span className="unread-dot"></span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Empty State */}
                {videos.length === 0 && messages.length === 0 && (
                  <div className="no-messages">
                    <div className="no-messages-icon">💬</div>
                    <h3>No Messages Yet</h3>
                    <p>Your loan officer will share video messages and updates here.</p>
                    <p className="hint">Check back soon for personalized content!</p>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Documents Tab */}
        {activeTab === 'documents' && (
          <div className="documents-tab">
            <div className="documents-header">
              <h2>Your Documents</h2>
              <p>Access your important mortgage documents anytime.</p>
            </div>

            {loadingMedia ? (
              <div className="documents-loading">
                <div className="spinner"></div>
                <p>Loading documents...</p>
              </div>
            ) : documents.length > 0 ? (
              <div className="documents-grid">
                {documents.map((doc) => (
                  <div key={doc.id} className="document-card">
                    <div className="doc-icon">
                      {doc.doc_category === 'closing' ? '📋' :
                       doc.doc_category === 'tax' ? '📊' :
                       doc.doc_category === 'insurance' ? '🛡️' :
                       doc.doc_category === 'legal' ? '⚖️' : '📄'}
                    </div>
                    <div className="doc-info">
                      <h4>{doc.file_name || doc.doc_type}</h4>
                      <p className="doc-type">{doc.doc_type?.replace(/_/g, ' ')}</p>
                      <span className="doc-date">Added {formatDate(doc.created_at)}</span>
                      {doc.size_bytes && (
                        <span className="doc-size">
                          {(doc.size_bytes / 1024 / 1024).toFixed(1)} MB
                        </span>
                      )}
                    </div>
                    <button className="download-btn" onClick={() => toast.info('Document download coming soon!')}>
                      Download
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="no-documents">
                <div className="no-docs-icon">📂</div>
                <h3>No Documents Available</h3>
                <p>Your important mortgage documents will appear here.</p>
                <p className="hint">Contact your loan officer if you need specific documents.</p>
              </div>
            )}

            {/* Standard Documents Section */}
            <div className="standard-documents">
              <h3>Common Mortgage Documents</h3>
              <p>Looking for specific closing documents? Contact your loan officer:</p>
              <div className="standard-doc-list">
                <div className="standard-doc">
                  <span>📄</span>
                  <div>
                    <strong>Closing Disclosure</strong>
                    <p>Final loan terms and closing costs</p>
                  </div>
                </div>
                <div className="standard-doc">
                  <span>📄</span>
                  <div>
                    <strong>Promissory Note</strong>
                    <p>Your promise to repay the loan</p>
                  </div>
                </div>
                <div className="standard-doc">
                  <span>📄</span>
                  <div>
                    <strong>Deed of Trust</strong>
                    <p>Security instrument for your loan</p>
                  </div>
                </div>
                <div className="standard-doc">
                  <span>📄</span>
                  <div>
                    <strong>Title Insurance Policy</strong>
                    <p>Protection against title defects</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

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

      {/* Footer */}
      <footer className="mum-footer">
        <p>
          Home value estimates are for informational purposes only and may not reflect actual market value.
        </p>
        <p className="footer-links">
          <a href="/privacy">Privacy Policy</a>
          <span>•</span>
          <a href="/terms">Terms of Service</a>
        </p>
      </footer>
    </div>
  );
}
