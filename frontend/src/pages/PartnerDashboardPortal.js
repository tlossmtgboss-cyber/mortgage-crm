/**
 * Partner Dashboard Portal - Redesigned
 *
 * Full-featured portal for referral partners with:
 * - Dashboard overview with stats
 * - Loan programs education
 * - Marketing support requests
 * - AI Assistant for pre-approval letters
 * - Client tracking (leads, active, closed)
 */

import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { partnersAPI } from '../services/api';
import './PartnerDashboardPortal.css';

// Tab configuration
const TABS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'programs', label: 'Programs' },
  { id: 'marketing', label: 'Marketing' },
  { id: 'assistant', label: 'AI Assistant' },
  { id: 'clients', label: 'Clients' },
];

// Loan program data
const LOAN_PROGRAMS = [
  {
    id: 'conventional',
    name: 'Conventional',
    color: '#3b82f6',
    minCredit: 620,
    minDown: '3%',
    maxDTI: '45%',
    highlights: ['Most common loan type', 'PMI removed at 20% equity', 'Fixed & ARM options'],
    bestFor: 'Buyers with good credit and stable income',
  },
  {
    id: 'fha',
    name: 'FHA',
    color: '#10b981',
    minCredit: 580,
    minDown: '3.5%',
    maxDTI: '50%',
    highlights: ['Lower credit requirements', 'Gift funds allowed', 'Assumable loans'],
    bestFor: 'First-time buyers or those rebuilding credit',
  },
  {
    id: 'va',
    name: 'VA',
    color: '#8b5cf6',
    minCredit: 580,
    minDown: '0%',
    maxDTI: '41%',
    highlights: ['No down payment', 'No PMI', 'Competitive rates'],
    bestFor: 'Veterans, active military, and eligible spouses',
  },
  {
    id: 'usda',
    name: 'USDA',
    color: '#f59e0b',
    minCredit: 640,
    minDown: '0%',
    maxDTI: '41%',
    highlights: ['No down payment', 'Rural areas', 'Income limits apply'],
    bestFor: 'Buyers in eligible rural areas',
  },
  {
    id: 'jumbo',
    name: 'Jumbo',
    color: '#ec4899',
    minCredit: 700,
    minDown: '10%',
    maxDTI: '43%',
    highlights: ['Higher loan amounts', 'Luxury properties', 'Custom terms'],
    bestFor: 'High-value property purchases',
  },
  {
    id: 'nonqm',
    name: 'Non-QM',
    color: '#64748b',
    minCredit: 620,
    minDown: '10%',
    maxDTI: '50%',
    highlights: ['Bank statements', 'Asset depletion', 'DSCR for investors'],
    bestFor: 'Self-employed or non-traditional income',
  },
];

// Marketing materials
const MARKETING_CATEGORIES = [
  {
    id: 'flyers',
    name: 'Co-Branded Flyers',
    items: ['Rate Sheet', 'Open House Flyer', 'Just Listed/Sold', 'Buyer Guide'],
  },
  {
    id: 'digital',
    name: 'Digital Assets',
    items: ['Social Media Graphics', 'Email Templates', 'Website Banner', 'Video Content'],
  },
  {
    id: 'print',
    name: 'Print Materials',
    items: ['Business Cards', 'Brochures', 'Postcards', 'Door Hangers'],
  },
  {
    id: 'events',
    name: 'Event Support',
    items: ['Open House Setup', 'Lunch & Learn', 'Client Appreciation', 'Seminar Materials'],
  },
];

export default function PartnerDashboardPortal() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [partner, setPartner] = useState(null);
  const [referrals, setReferrals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadPartnerData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadPartnerData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [partnerData, referralsData] = await Promise.all([
        partnersAPI.getById(id),
        partnersAPI.getReferrals(id),
      ]);

      if (!partnerData) {
        throw new Error('Partner not found');
      }

      setPartner(partnerData);
      setReferrals(referralsData.referrals || []);
    } catch (err) {
      console.error('Failed to load partner data:', err);
      setError(err.message || 'Failed to load partner portal');
    } finally {
      setLoading(false);
    }
  };

  const categorizeReferrals = () => {
    return {
      leads: referrals.filter((r) =>
        ['New', 'Attempted Contact', 'Prospect'].includes(r.stage)
      ),
      active: referrals.filter((r) =>
        ['Application', 'Pre-Qualified', 'Pre-Approved', 'Processing', 'Under Contract'].includes(r.stage)
      ),
      closed: referrals.filter((r) => r.stage === 'Completed' || r.stage === 'Funded'),
    };
  };

  if (loading) {
    return (
      <div className="partner-portal-v2 loading-state">
        <div className="loading-content">
          <div className="loading-spinner" />
          <p>Loading your partner portal...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="partner-portal-v2 error-state">
        <div className="error-content">
          <h1>Unable to Load Portal</h1>
          <p>{error}</p>
          <button onClick={() => navigate('/referral-partners')}>Back to Partners</button>
        </div>
      </div>
    );
  }

  const categories = categorizeReferrals();
  const stats = {
    totalReferrals: referrals.length,
    activeLeads: categories.leads.length,
    inProgress: categories.active.length,
    closedLoans: categories.closed.length,
    conversionRate:
      referrals.length > 0
        ? ((categories.closed.length / referrals.length) * 100).toFixed(1)
        : 0,
    totalVolume: categories.closed.reduce((sum, r) => sum + (r.loan_amount || 0), 0),
  };

  return (
    <div className="partner-portal-v2">
      {/* Sidebar */}
      <aside className="portal-sidebar">
        <div className="sidebar-header">
          <div className="partner-avatar-lg">
            {partner.name?.charAt(0)?.toUpperCase() || 'P'}
          </div>
          <div className="partner-info-sidebar">
            <h2>{partner.name}</h2>
            <p>{partner.company || 'Independent Partner'}</p>
            <TierBadge tier={partner.loyalty_tier} />
          </div>
        </div>

        <nav className="sidebar-nav">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              className={`nav-item ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <span className="nav-label">{tab.label}</span>
              {tab.id === 'clients' && categories.leads.length > 0 && (
                <span className="nav-badge">{categories.leads.length}</span>
              )}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button className="back-to-admin" onClick={() => navigate(`/referral-partners/${id}`)}>
            ← Admin View
          </button>
          <div className="lo-contact-mini">
            <span className="lo-label">Your Loan Officer</span>
            <span className="lo-name">{partner.assigned_lo_name || 'Contact Us'}</span>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="portal-main-content">
        {activeTab === 'dashboard' && (
          <DashboardTab partner={partner} stats={stats} categories={categories} />
        )}
        {activeTab === 'programs' && <ProgramsTab />}
        {activeTab === 'marketing' && <MarketingTab partner={partner} />}
        {activeTab === 'assistant' && <AIAssistantTab partner={partner} />}
        {activeTab === 'clients' && (
          <ClientsTab categories={categories} partnerId={id} navigate={navigate} />
        )}
      </main>
    </div>
  );
}

// ============================================================================
// DASHBOARD TAB
// ============================================================================
function DashboardTab({ partner, stats, categories }) {
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  return (
    <div className="tab-content dashboard-tab">
      <div className="tab-header">
        <h1>Welcome back, {partner.name?.split(' ')[0]}!</h1>
        <p>Here's an overview of your partnership performance</p>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        <div className="stat-card primary">
          <div className="stat-details">
            <span className="stat-value">{stats.totalReferrals}</span>
            <span className="stat-label">Total Referrals</span>
          </div>
        </div>
        <div className="stat-card warning">
          <div className="stat-details">
            <span className="stat-value">{stats.activeLeads}</span>
            <span className="stat-label">Active Leads</span>
          </div>
        </div>
        <div className="stat-card info">
          <div className="stat-details">
            <span className="stat-value">{stats.inProgress}</span>
            <span className="stat-label">In Progress</span>
          </div>
        </div>
        <div className="stat-card success">
          <div className="stat-details">
            <span className="stat-value">{stats.closedLoans}</span>
            <span className="stat-label">Closed Loans</span>
          </div>
        </div>
        <div className="stat-card purple">
          <div className="stat-details">
            <span className="stat-value">{stats.conversionRate}%</span>
            <span className="stat-label">Conversion Rate</span>
          </div>
        </div>
        <div className="stat-card gold">
          <div className="stat-details">
            <span className="stat-value">{formatCurrency(stats.totalVolume)}</span>
            <span className="stat-label">Closed Volume</span>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <section className="dashboard-section">
        <h2>Quick Actions</h2>
        <div className="quick-actions-grid">
          <QuickActionCard
            title="Submit a Referral"
            description="Send us a new client referral"
            color="#3b82f6"
          />
          <QuickActionCard
            title="Request Pre-Approval"
            description="Generate a pre-approval letter"
            color="#10b981"
          />
          <QuickActionCard
            title="Order Marketing"
            description="Request co-branded materials"
            color="#f59e0b"
          />
          <QuickActionCard
            title="Contact LO"
            description="Message your loan officer"
            color="#8b5cf6"
          />
        </div>
      </section>

      {/* Recent Activity */}
      <section className="dashboard-section">
        <h2>Recent Activity</h2>
        <div className="activity-list">
          {categories.leads.slice(0, 3).map((lead) => (
            <ActivityItem key={lead.id} lead={lead} type="new_lead" />
          ))}
          {categories.active.slice(0, 2).map((client) => (
            <ActivityItem key={client.id} lead={client} type="progress" />
          ))}
          {categories.leads.length === 0 && categories.active.length === 0 && (
            <div className="empty-activity">
              <p>No recent activity. Submit a referral to get started!</p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function QuickActionCard({ title, description, color }) {
  return (
    <button className="quick-action-card" style={{ '--accent-color': color }}>
      <h3>{title}</h3>
      <p>{description}</p>
    </button>
  );
}

function ActivityItem({ lead, type }) {
  const typeConfig = {
    new_lead: { label: 'New Lead' },
    progress: { label: 'In Progress' },
    closed: { label: 'Closed' },
  };
  const config = typeConfig[type] || typeConfig.new_lead;

  return (
    <div className="activity-item">
      <div className="activity-type-badge">{config.label}</div>
      <div className="activity-details">
        <span className="activity-name">{lead.name}</span>
        <span className="activity-status">{lead.stage}</span>
      </div>
      <span className="activity-time">
        {new Date(lead.updated_at || lead.created_at).toLocaleDateString()}
      </span>
    </div>
  );
}

// ============================================================================
// PROGRAMS TAB
// ============================================================================
function ProgramsTab() {
  const [selectedProgram, setSelectedProgram] = useState(null);

  return (
    <div className="tab-content programs-tab">
      <div className="tab-header">
        <h1>Loan Programs</h1>
        <p>Learn about our available mortgage programs to better serve your clients</p>
      </div>

      <div className="programs-grid">
        {LOAN_PROGRAMS.map((program) => (
          <div
            key={program.id}
            className={`program-card ${selectedProgram === program.id ? 'selected' : ''}`}
            style={{ '--program-color': program.color }}
            onClick={() => setSelectedProgram(selectedProgram === program.id ? null : program.id)}
          >
            <div className="program-header">
              <h3>{program.name}</h3>
            </div>

            <div className="program-quick-stats">
              <div className="quick-stat">
                <span className="qs-label">Min Credit</span>
                <span className="qs-value">{program.minCredit}</span>
              </div>
              <div className="quick-stat">
                <span className="qs-label">Min Down</span>
                <span className="qs-value">{program.minDown}</span>
              </div>
              <div className="quick-stat">
                <span className="qs-label">Max DTI</span>
                <span className="qs-value">{program.maxDTI}</span>
              </div>
            </div>

            {selectedProgram === program.id && (
              <div className="program-details">
                <div className="detail-section">
                  <h4>Key Benefits</h4>
                  <ul>
                    {program.highlights.map((h, i) => (
                      <li key={i}>{h}</li>
                    ))}
                  </ul>
                </div>
                <div className="detail-section">
                  <h4>Best For</h4>
                  <p>{program.bestFor}</p>
                </div>
                <button className="learn-more-btn">Download Full Guidelines</button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Comparison Table */}
      <section className="comparison-section">
        <h2>Quick Comparison</h2>
        <div className="comparison-table-wrapper">
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Program</th>
                <th>Min Credit</th>
                <th>Min Down</th>
                <th>Max DTI</th>
                <th>PMI</th>
              </tr>
            </thead>
            <tbody>
              {LOAN_PROGRAMS.map((p) => (
                <tr key={p.id}>
                  <td>
                    <span className="program-name-cell">
                      {p.name}
                    </span>
                  </td>
                  <td>{p.minCredit}</td>
                  <td>{p.minDown}</td>
                  <td>{p.maxDTI}</td>
                  <td>{p.id === 'va' ? 'No' : p.id === 'conventional' ? 'Until 20%' : 'MIP/GF'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

// ============================================================================
// MARKETING TAB
// ============================================================================
function MarketingTab({ partner }) {
  const [selectedItems, setSelectedItems] = useState([]);
  const [requestNotes, setRequestNotes] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const toggleItem = (categoryId, item) => {
    const key = `${categoryId}-${item}`;
    setSelectedItems((prev) =>
      prev.includes(key) ? prev.filter((i) => i !== key) : [...prev, key]
    );
  };

  const handleSubmit = () => {
    // In production, this would send to backend
    console.log('Marketing request:', { selectedItems, requestNotes, partner: partner.name });
    setSubmitted(true);
    setTimeout(() => {
      setSubmitted(false);
      setSelectedItems([]);
      setRequestNotes('');
    }, 3000);
  };

  return (
    <div className="tab-content marketing-tab">
      <div className="tab-header">
        <h1>Marketing Support</h1>
        <p>Request co-branded marketing materials to promote our partnership</p>
      </div>

      {submitted ? (
        <div className="submission-success">
          <h2>Request Submitted!</h2>
          <p>Our marketing team will prepare your materials within 2-3 business days.</p>
        </div>
      ) : (
        <>
          <div className="marketing-categories">
            {MARKETING_CATEGORIES.map((category) => (
              <div key={category.id} className="marketing-category">
                <div className="category-header">
                  <h3>{category.name}</h3>
                </div>
                <div className="category-items">
                  {category.items.map((item) => {
                    const key = `${category.id}-${item}`;
                    const isSelected = selectedItems.includes(key);
                    return (
                      <button
                        key={item}
                        className={`material-item ${isSelected ? 'selected' : ''}`}
                        onClick={() => toggleItem(category.id, item)}
                      >
                        <span className="item-check">{isSelected ? '✓' : ''}</span>
                        <span className="item-name">{item}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          <div className="request-form">
            <h3>Additional Details</h3>
            <textarea
              placeholder="Any specific requirements, colors, messaging, or deadlines?"
              value={requestNotes}
              onChange={(e) => setRequestNotes(e.target.value)}
              rows={4}
            />
            <div className="form-actions">
              <span className="selected-count">
                {selectedItems.length} item{selectedItems.length !== 1 ? 's' : ''} selected
              </span>
              <button
                className="submit-request-btn"
                disabled={selectedItems.length === 0}
                onClick={handleSubmit}
              >
                Submit Request
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ============================================================================
// AI ASSISTANT TAB
// ============================================================================
function AIAssistantTab({ partner }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: `Hi ${partner.name?.split(' ')[0] || 'there'}! I'm your AI Assistant. I can help you:\n\n• Generate pre-approval letters\n• Answer loan program questions\n• Create client communications\n• Explain guidelines\n\nHow can I help you today?`,
    },
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [preApprovalData, setPreApprovalData] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
    setIsTyping(true);

    // Simulate AI response
    setTimeout(() => {
      let response = '';
      const lowerInput = userMessage.toLowerCase();

      if (lowerInput.includes('pre-approval') || lowerInput.includes('preapproval')) {
        response = `I'd be happy to help generate a pre-approval letter! Please provide:\n\n1. Buyer's full name\n2. Pre-approved loan amount\n3. Loan program (Conventional, FHA, VA, etc.)\n4. Property address (if known)\n\nOnce you provide these details, I'll create the letter for you.`;
        setPreApprovalData({ step: 'collecting' });
      } else if (lowerInput.includes('fha')) {
        response = `**FHA Loan Overview:**\n\n• Min Credit Score: 580 (3.5% down) or 500 (10% down)\n• Max DTI: 50%\n• Upfront MIP: 1.75%\n• Monthly MIP: 0.55% annually\n• Great for first-time buyers and credit rebuilding\n\nWould you like more details on FHA guidelines?`;
      } else if (lowerInput.includes('conventional')) {
        response = `**Conventional Loan Overview:**\n\n• Min Credit Score: 620\n• Min Down: 3% (first-time buyers) or 5%\n• PMI required below 20% equity\n• Max DTI: 45-50%\n• Most flexible loan type\n\nWould you like information on specific conventional products?`;
      } else if (preApprovalData?.step === 'collecting') {
        response = `Great! Based on your information, I've generated the pre-approval letter.\n\n**Pre-Approval Letter Ready**\n\nClick the button below to:\n• Download PDF\n• Email to client\n• Email to agent`;
        setPreApprovalData({ step: 'ready', data: userMessage });
      } else {
        response = `I can help with that! For pre-approval letters, loan program questions, or client communications, just let me know what you need.\n\nSome things I can do:\n• "Generate pre-approval letter"\n• "Explain FHA requirements"\n• "What's the max DTI for VA loans?"`;
      }

      setMessages((prev) => [...prev, { role: 'assistant', content: response }]);
      setIsTyping(false);
    }, 1500);
  };

  return (
    <div className="tab-content assistant-tab">
      <div className="chat-container">
        <div className="chat-header">
          <div className="chat-title">
            <h2>AI Assistant</h2>
            <span className="online-status">Online</span>
          </div>
        </div>

        <div className="chat-messages">
          {messages.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              <div className="message-content">
                {msg.content.split('\n').map((line, j) => (
                  <p key={j}>{line}</p>
                ))}
                {msg.role === 'assistant' && preApprovalData?.step === 'ready' && i === messages.length - 1 && (
                  <div className="letter-actions">
                    <button className="letter-btn download">
                      Download PDF
                    </button>
                    <button className="letter-btn email">
                      Email to Client
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
          {isTyping && (
            <div className="message assistant typing">
              <div className="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-area">
          <div className="quick-prompts">
            <button onClick={() => setInput('Generate a pre-approval letter')}>
              Pre-Approval Letter
            </button>
            <button onClick={() => setInput('Explain FHA loan requirements')}>
              FHA Requirements
            </button>
            <button onClick={() => setInput('What programs allow gift funds?')}>
              Gift Funds
            </button>
          </div>
          <div className="chat-input-wrapper">
            <input
              type="text"
              placeholder="Ask me anything about loans, pre-approvals, or guidelines..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSend()}
            />
            <button className="send-btn" onClick={handleSend} disabled={!input.trim()}>
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// CLIENTS TAB
// ============================================================================
function ClientsTab({ categories, partnerId, navigate }) {
  const [activeFilter, setActiveFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');

  const allClients = [
    ...categories.leads.map((c) => ({ ...c, category: 'lead' })),
    ...categories.active.map((c) => ({ ...c, category: 'active' })),
    ...categories.closed.map((c) => ({ ...c, category: 'closed' })),
  ];

  const filteredClients = allClients.filter((client) => {
    const matchesFilter = activeFilter === 'all' || client.category === activeFilter;
    const matchesSearch =
      !searchTerm ||
      client.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      client.email?.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  const handleViewDetails = (client) => {
    const clientId = client.loan_id || client.id;
    navigate(`/partner-portal/${partnerId}/client/${clientId}`);
  };

  return (
    <div className="tab-content clients-tab">
      <div className="tab-header">
        <h1>Client Pipeline</h1>
        <p>Track all your referrals from lead to close</p>
      </div>

      {/* Filter Bar */}
      <div className="clients-toolbar">
        <div className="filter-tabs">
          <button
            className={`filter-tab ${activeFilter === 'all' ? 'active' : ''}`}
            onClick={() => setActiveFilter('all')}
          >
            All ({allClients.length})
          </button>
          <button
            className={`filter-tab ${activeFilter === 'lead' ? 'active' : ''}`}
            onClick={() => setActiveFilter('lead')}
          >
            Leads ({categories.leads.length})
          </button>
          <button
            className={`filter-tab ${activeFilter === 'active' ? 'active' : ''}`}
            onClick={() => setActiveFilter('active')}
          >
            Active ({categories.active.length})
          </button>
          <button
            className={`filter-tab ${activeFilter === 'closed' ? 'active' : ''}`}
            onClick={() => setActiveFilter('closed')}
          >
            Closed ({categories.closed.length})
          </button>
        </div>
        <div className="search-box">
          <input
            type="text"
            placeholder="Search clients..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      {/* Clients List */}
      <div className="clients-list">
        {filteredClients.length === 0 ? (
          <div className="empty-clients">
            <h3>No clients found</h3>
            <p>
              {activeFilter === 'all'
                ? 'Submit a referral to get started!'
                : `No ${activeFilter} clients at this time.`}
            </p>
          </div>
        ) : (
          filteredClients.map((client) => (
            <ClientCard
              key={client.id}
              client={client}
              onViewDetails={() => handleViewDetails(client)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function ClientCard({ client, onViewDetails }) {
  const formatCurrency = (amount) => {
    if (!amount) return 'TBD';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
    }).format(amount);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const categoryColors = {
    lead: '#f59e0b',
    active: '#3b82f6',
    closed: '#10b981',
  };

  return (
    <div
      className="client-card"
      style={{ '--category-color': categoryColors[client.category] || '#64748b' }}
    >
      <div className="client-avatar">{client.name?.charAt(0)?.toUpperCase() || '?'}</div>
      <div className="client-info">
        <h3>{client.name || 'Unknown'}</h3>
        <p>{client.email || 'No email'}</p>
      </div>
      <div className="client-details">
        <div className="detail">
          <span className="label">Loan Amount</span>
          <span className="value">{formatCurrency(client.loan_amount)}</span>
        </div>
        <div className="detail">
          <span className="label">Status</span>
          <span className="value">{client.stage}</span>
        </div>
        <div className="detail">
          <span className="label">Updated</span>
          <span className="value">{formatDate(client.updated_at)}</span>
        </div>
      </div>
      <button className="view-btn" onClick={onViewDetails}>
        View →
      </button>
    </div>
  );
}

// ============================================================================
// SHARED COMPONENTS
// ============================================================================
function TierBadge({ tier }) {
  const tierClass = tier?.toLowerCase() || 'bronze';
  return (
    <span className={`tier-badge-v2 tier-${tierClass}`}>
      {tier || 'Bronze'}
    </span>
  );
}
