/**
 * Support Page
 * Comprehensive support center with help articles, FAQ, contact options, and ticket submission
 */

import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import { getAuthHeaders } from '../utils/auth';
import { toast } from '../utils/toast';
import './Support.css';

const Support = () => {
  const [activeTab, setActiveTab] = useState('help');
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedArticle, setExpandedArticle] = useState(null);
  const [expandedFaq, setExpandedFaq] = useState(null);
  const [ticketForm, setTicketForm] = useState({
    subject: '',
    category: '',
    priority: 'normal',
    description: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [tickets, setTickets] = useState([]);
  const [loadingTickets, setLoadingTickets] = useState(false);

  const tabs = [
    { id: 'help', label: 'Help Articles', icon: 'fa-book' },
    { id: 'faq', label: 'FAQ', icon: 'fa-question-circle' },
    { id: 'contact', label: 'Contact Support', icon: 'fa-headset' },
    { id: 'tickets', label: 'My Tickets', icon: 'fa-ticket-alt' },
  ];

  const helpContent = {
    'getting-started': {
      title: 'Getting Started',
      icon: '🚀',
      articles: [
        {
          id: 'first-call',
          title: 'Making Your First Call',
          content: `All Twilio calls through Perennia AI are automatically recorded.

**How it works:**
1. Click "Make Call" in the top navigation
2. Enter borrower's phone number
3. Have your conversation normally
4. After the call ends, go to "Meetings" to view:
   - Full transcript with timestamps
   - AI summary of key points
   - Action items automatically extracted
   - Performance analytics and coaching

**Tip:** The AI starts analyzing as soon as the call ends. Give it 1-2 minutes to process.`
        },
        {
          id: 'navigation',
          title: 'Navigating the Dashboard',
          content: `The dashboard is your command center for managing your mortgage pipeline.

**Key areas:**
- **Top Bar:** Quick actions, notifications, and search
- **Left Sidebar:** Main navigation menu
- **Dashboard:** Pipeline overview and key metrics
- **Leads:** Manage prospects and track conversions
- **Loans:** Active loan pipeline management
- **Tasks:** Your to-do list and follow-ups

**Quick Tips:**
- Use keyboard shortcuts (press ? to see all)
- Pin frequently used pages to your favorites
- Customize your dashboard widgets`
        },
        {
          id: 'recording-clips',
          title: 'Recording Video Clips',
          content: `Video clips let you send personalized screen + camera recordings to borrowers.

**To record a clip:**
1. Go to Clips → New Clip
2. Choose a template (optional)
3. Select recording mode:
   - Screen + Camera (recommended)
   - Screen only
   - Camera only
4. Click Record and grant permissions
5. Record your message (up to 10 minutes)
6. Preview and save

**Sharing:**
- Click "Share" to generate a link
- Set expiration (optional)
- Send link via email/SMS
- Get notified when viewed`
        }
      ]
    },
    'pipeline': {
      title: 'Pipeline Management',
      icon: '📊',
      articles: [
        {
          id: 'managing-loans',
          title: 'Managing Your Loan Pipeline',
          content: `Keep your pipeline organized and moving efficiently.

**Loan Stages:**
- **Lead:** Initial contact, not yet applied
- **Application:** Borrower has started application
- **Processing:** Gathering documents and data
- **Underwriting:** Loan under review
- **Approved:** Conditional or final approval
- **Clear to Close:** All conditions satisfied
- **Funded:** Loan has closed

**Best Practices:**
- Update loan status promptly
- Set realistic expected close dates
- Use tasks to track action items
- Review pipeline daily for bottlenecks`
        },
        {
          id: 'documents',
          title: 'Document Management',
          content: `Efficiently collect and manage borrower documents.

**Document Categories:**
- Income: Pay stubs, W-2s, tax returns
- Assets: Bank statements, investment accounts
- Property: Purchase contract, appraisal
- Identity: Driver's license, SSN card

**Features:**
- Drag and drop upload
- Automatic document classification
- Expiration tracking
- Secure borrower upload portal
- Document request templates`
        }
      ]
    },
    'communication': {
      title: 'Communication Tools',
      icon: '💬',
      articles: [
        {
          id: 'email-integration',
          title: 'Email Integration',
          content: `Connect your email for seamless communication tracking.

**Setup:**
1. Go to Settings → Integrations
2. Click "Connect Email"
3. Authorize access (Gmail or Outlook)
4. Select sync options

**Features:**
- Automatic email logging to loans
- Email templates with merge fields
- Track opens and clicks
- Schedule emails for later
- Smart reply suggestions`
        },
        {
          id: 'sms-calling',
          title: 'SMS and Calling',
          content: `Communicate with borrowers via text and phone.

**SMS Features:**
- Send/receive texts from the app
- Templates for common messages
- Scheduled texts
- Compliance-friendly opt-out handling

**Calling Features:**
- Click-to-call from any contact
- Automatic call recording
- AI transcription and analysis
- Local presence dialing
- Power dialer for high-volume calls`
        }
      ]
    },
    'analytics': {
      title: 'Analytics & Coaching',
      icon: '📈',
      articles: [
        {
          id: 'performance-metrics',
          title: 'Understanding Performance Metrics',
          content: `Track and improve your performance with AI-powered analytics.

**Key Metrics:**
- **Engagement Score:** Overall conversation quality (0-1.0)
- **Talk-Listen Ratio:** Balance between speaking/listening (target: 40-60%)
- **Questions Asked:** Discovery questions per call
- **Conversion Rate:** Leads to applications

**AI Coaching:**
You'll receive personalized recommendations after each call, prioritized by impact.`
        },
        {
          id: 'reports',
          title: 'Running Reports',
          content: `Generate insights from your pipeline data.

**Available Reports:**
- Pipeline summary
- Conversion funnel
- Activity tracking
- Revenue forecast
- Marketing attribution

**Export Options:**
- PDF for presentations
- CSV for spreadsheet analysis
- Scheduled email delivery`
        }
      ]
    },
    'troubleshooting': {
      title: 'Troubleshooting',
      icon: '🔧',
      articles: [
        {
          id: 'common-issues',
          title: 'Common Issues & Solutions',
          content: `**Page not loading:**
- Clear browser cache and cookies
- Try a different browser (Chrome recommended)
- Check your internet connection
- Disable browser extensions

**Login problems:**
- Verify email address is correct
- Use "Forgot Password" to reset
- Check if account is locked (contact admin)

**Missing data:**
- Check date range filters
- Verify you have correct permissions
- Try refreshing the page`
        },
        {
          id: 'recording-issues',
          title: 'Recording Issues',
          content: `**Recording doesn't start:**
- Check microphone permissions in browser settings
- Try a different browser (Chrome recommended)
- Disable browser extensions that block media

**Poor audio quality:**
- Use a headset or external microphone
- Check microphone levels in system settings
- Reduce background noise

**Transcript is inaccurate:**
- Speak clearly and at moderate pace
- Reduce overlapping speech
- Use better audio equipment`
        },
        {
          id: 'integration-issues',
          title: 'Integration Troubleshooting',
          content: `**Email not syncing:**
- Check connection in Settings → Integrations
- Re-authorize the connection
- Verify the correct account is connected

**CRM sync issues:**
- Check API credentials are valid
- Review sync logs for errors
- Ensure field mappings are correct

**Calendar not showing:**
- Reconnect calendar integration
- Check calendar permissions
- Verify correct calendar is selected`
        }
      ]
    }
  };

  const faqItems = [
    {
      id: 'pricing',
      question: 'How does pricing work?',
      answer: 'Perennia AI offers flexible pricing based on your team size and usage. Contact your account manager or visit our pricing page for current plans. Enterprise customers can request custom pricing for high-volume needs.'
    },
    {
      id: 'data-security',
      question: 'How is my data secured?',
      answer: 'We use bank-level encryption (AES-256) for data at rest and TLS 1.3 for data in transit. All recordings are stored in SOC 2 Type II compliant data centers. We never share or sell your data. You can request data deletion at any time.'
    },
    {
      id: 'compliance',
      question: 'Is the system compliant with mortgage regulations?',
      answer: 'Yes, Perennia AI is designed with TRID, RESPA, and state-specific compliance in mind. Our disclosure tracking, communication logging, and audit trails help you maintain compliance. Always consult with your compliance team for specific requirements.'
    },
    {
      id: 'mobile',
      question: 'Is there a mobile app?',
      answer: 'Yes! Perennia AI is available on iOS and Android. Download from the App Store or Google Play. The mobile app includes calling, task management, pipeline view, and push notifications. Some advanced features are best used on desktop.'
    },
    {
      id: 'integrations',
      question: 'What systems does Perennia AI integrate with?',
      answer: 'We integrate with major LOS systems (Encompass, BytePro, Calyx), CRMs (Salesforce, HubSpot), email providers (Gmail, Outlook), calendars, and more. Check Settings → Integrations for the full list, or contact us for custom integrations.'
    },
    {
      id: 'training',
      question: 'Do you offer training?',
      answer: 'Yes! We offer live onboarding sessions for new teams, video tutorials in the Help Center, weekly webinars on advanced features, and custom training for enterprise accounts. Your success manager can schedule dedicated training.'
    },
    {
      id: 'support-hours',
      question: 'What are support hours?',
      answer: 'Our support team is available Monday-Friday, 7 AM - 7 PM EST. Enterprise customers have access to 24/7 priority support. Emergency issues (system outages) are monitored around the clock.'
    },
    {
      id: 'cancel',
      question: 'How do I cancel my subscription?',
      answer: 'You can cancel anytime from Settings → Billing → Cancel Subscription. Your data will be available for export for 30 days after cancellation. Contact your account manager if you need an extension or have questions about your contract.'
    }
  ];

  const ticketCategories = [
    { value: '', label: 'Select a category...' },
    { value: 'technical', label: 'Technical Issue' },
    { value: 'billing', label: 'Billing & Account' },
    { value: 'feature', label: 'Feature Request' },
    { value: 'integration', label: 'Integration Help' },
    { value: 'training', label: 'Training Request' },
    { value: 'other', label: 'Other' },
  ];

  useEffect(() => {
    if (activeTab === 'tickets') {
      loadTickets();
    }
  }, [activeTab]);

  const loadTickets = async () => {
    setLoadingTickets(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/support/tickets`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setTickets(data.tickets || []);
      }
    } catch (err) {
      console.error('Error loading tickets:', err);
    } finally {
      setLoadingTickets(false);
    }
  };

  const handleSubmitTicket = async (e) => {
    e.preventDefault();

    if (!ticketForm.subject.trim() || !ticketForm.category || !ticketForm.description.trim()) {
      toast.error('Please fill in all required fields');
      return;
    }

    setSubmitting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/support/tickets`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(ticketForm)
      });

      if (response.ok) {
        toast.success('Support ticket submitted successfully. We\'ll get back to you soon!');
        setTicketForm({ subject: '', category: '', priority: 'normal', description: '' });
        setActiveTab('tickets');
        loadTickets();
      } else {
        throw new Error('Failed to submit ticket');
      }
    } catch (err) {
      toast.error('Failed to submit ticket. Please try again or email support directly.');
    } finally {
      setSubmitting(false);
    }
  };

  const searchArticles = () => {
    if (!searchTerm.trim()) return null;

    const results = [];
    Object.entries(helpContent).forEach(([categoryKey, category]) => {
      category.articles.forEach(article => {
        if (
          article.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
          article.content.toLowerCase().includes(searchTerm.toLowerCase())
        ) {
          results.push({
            ...article,
            category: category.title,
            categoryKey
          });
        }
      });
    });

    return results;
  };

  const renderMarkdown = (content) => {
    return content.split('\n').map((line, idx) => {
      if (line.startsWith('**') && line.endsWith('**')) {
        return <h4 key={idx} className="content-heading">{line.slice(2, -2)}</h4>;
      }
      const boldRegex = /\*\*([^*]+)\*\*/g;
      if (boldRegex.test(line)) {
        const parts = line.split(boldRegex);
        return (
          <p key={idx}>
            {parts.map((part, i) =>
              i % 2 === 1 ? <strong key={i}>{part}</strong> : part
            )}
          </p>
        );
      }
      if (line.startsWith('- ')) {
        return <li key={idx}>{line.slice(2)}</li>;
      }
      if (/^\d+\.\s/.test(line)) {
        return <li key={idx} className="numbered">{line.replace(/^\d+\.\s/, '')}</li>;
      }
      if (!line.trim()) {
        return <br key={idx} />;
      }
      return <p key={idx}>{line}</p>;
    });
  };

  const searchResults = searchTerm ? searchArticles() : null;
  const [activeCategory, setActiveCategory] = useState('getting-started');

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'open': return 'status-open';
      case 'in_progress': return 'status-progress';
      case 'resolved': return 'status-resolved';
      case 'closed': return 'status-closed';
      default: return '';
    }
  };

  return (
    <div className="support-page">
      <div className="page-header">
        <h1>Support Center</h1>
        <p>Get help, find answers, and contact our support team</p>
      </div>

      {/* Quick Actions */}
      <div className="quick-actions">
        <a href="mailto:support@perenniaai.com" className="quick-action-card">
          <i className="fas fa-envelope"></i>
          <div>
            <h3>Email Support</h3>
            <p>support@perenniaai.com</p>
          </div>
        </a>
        <a href="tel:+18005551234" className="quick-action-card">
          <i className="fas fa-phone"></i>
          <div>
            <h3>Phone Support</h3>
            <p>1-800-555-1234</p>
          </div>
        </a>
        <button className="quick-action-card" onClick={() => setActiveTab('tickets')}>
          <i className="fas fa-ticket-alt"></i>
          <div>
            <h3>Submit Ticket</h3>
            <p>Track your requests</p>
          </div>
        </button>
        <a href="https://status.perenniaai.com" target="_blank" rel="noopener noreferrer" className="quick-action-card">
          <i className="fas fa-signal"></i>
          <div>
            <h3>System Status</h3>
            <p>All systems operational</p>
          </div>
        </a>
      </div>

      {/* Tab Navigation */}
      <div className="support-tabs">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <i className={`fas ${tab.icon}`}></i>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="support-content">
        {/* Help Articles Tab */}
        {activeTab === 'help' && (
          <div className="help-section">
            <div className="help-search">
              <i className="fas fa-search"></i>
              <input
                type="text"
                placeholder="Search help articles..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
              {searchTerm && (
                <button className="clear-search" onClick={() => setSearchTerm('')}>
                  <i className="fas fa-times"></i>
                </button>
              )}
            </div>

            {searchResults ? (
              <div className="search-results">
                <h3>{searchResults.length} result{searchResults.length !== 1 ? 's' : ''} for "{searchTerm}"</h3>
                {searchResults.length === 0 ? (
                  <p className="no-results">No articles found. Try different keywords or contact support.</p>
                ) : (
                  <div className="results-list">
                    {searchResults.map(result => (
                      <div
                        key={result.id}
                        className="search-result-item"
                        onClick={() => {
                          setActiveCategory(result.categoryKey);
                          setExpandedArticle(result.id);
                          setSearchTerm('');
                        }}
                      >
                        <h4>{result.title}</h4>
                        <span className="result-category">{result.category}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="help-layout">
                <div className="help-sidebar">
                  {Object.entries(helpContent).map(([key, category]) => (
                    <button
                      key={key}
                      className={`category-button ${activeCategory === key ? 'active' : ''}`}
                      onClick={() => {
                        setActiveCategory(key);
                        setExpandedArticle(null);
                      }}
                    >
                      <span className="category-icon">{category.icon}</span>
                      <span>{category.title}</span>
                    </button>
                  ))}
                </div>

                <div className="help-articles">
                  <h2>
                    <span className="section-icon">{helpContent[activeCategory].icon}</span>
                    {helpContent[activeCategory].title}
                  </h2>
                  <div className="articles-list">
                    {helpContent[activeCategory].articles.map(article => (
                      <div
                        key={article.id}
                        className={`article-card ${expandedArticle === article.id ? 'expanded' : ''}`}
                      >
                        <button
                          className="article-header"
                          onClick={() => setExpandedArticle(
                            expandedArticle === article.id ? null : article.id
                          )}
                        >
                          <h3>{article.title}</h3>
                          <i className={`fas fa-chevron-${expandedArticle === article.id ? 'up' : 'down'}`}></i>
                        </button>
                        {expandedArticle === article.id && (
                          <div className="article-content">
                            {renderMarkdown(article.content)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* FAQ Tab */}
        {activeTab === 'faq' && (
          <div className="faq-section">
            <h2>Frequently Asked Questions</h2>
            <div className="faq-list">
              {faqItems.map(faq => (
                <div
                  key={faq.id}
                  className={`faq-item ${expandedFaq === faq.id ? 'expanded' : ''}`}
                >
                  <button
                    className="faq-question"
                    onClick={() => setExpandedFaq(expandedFaq === faq.id ? null : faq.id)}
                  >
                    <span>{faq.question}</span>
                    <i className={`fas fa-chevron-${expandedFaq === faq.id ? 'up' : 'down'}`}></i>
                  </button>
                  {expandedFaq === faq.id && (
                    <div className="faq-answer">
                      <p>{faq.answer}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Contact Tab */}
        {activeTab === 'contact' && (
          <div className="contact-section">
            <div className="contact-grid">
              <div className="contact-info">
                <h2>Get in Touch</h2>
                <p>Our support team is here to help you succeed with Perennia AI.</p>

                <div className="contact-methods">
                  <div className="contact-method">
                    <div className="method-icon">
                      <i className="fas fa-envelope"></i>
                    </div>
                    <div className="method-details">
                      <h3>Email Support</h3>
                      <p>support@perenniaai.com</p>
                      <span className="response-time">Response within 4 hours</span>
                    </div>
                  </div>

                  <div className="contact-method">
                    <div className="method-icon">
                      <i className="fas fa-phone"></i>
                    </div>
                    <div className="method-details">
                      <h3>Phone Support</h3>
                      <p>1-800-555-1234</p>
                      <span className="response-time">Mon-Fri, 7 AM - 7 PM EST</span>
                    </div>
                  </div>

                  <div className="contact-method">
                    <div className="method-icon">
                      <i className="fas fa-comments"></i>
                    </div>
                    <div className="method-details">
                      <h3>Live Chat</h3>
                      <p>Click the chat icon in the bottom right</p>
                      <span className="response-time">Available during business hours</span>
                    </div>
                  </div>
                </div>

                <div className="support-hours">
                  <h3>Support Hours</h3>
                  <div className="hours-grid">
                    <div className="hours-row">
                      <span>Monday - Friday</span>
                      <span>7:00 AM - 7:00 PM EST</span>
                    </div>
                    <div className="hours-row">
                      <span>Saturday - Sunday</span>
                      <span>Emergency only</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="ticket-form-container">
                <h2>Submit a Support Ticket</h2>
                <form onSubmit={handleSubmitTicket} className="ticket-form">
                  <div className="form-group">
                    <label htmlFor="subject">Subject *</label>
                    <input
                      type="text"
                      id="subject"
                      value={ticketForm.subject}
                      onChange={(e) => setTicketForm({ ...ticketForm, subject: e.target.value })}
                      placeholder="Brief description of your issue"
                      maxLength={100}
                    />
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="category">Category *</label>
                      <select
                        id="category"
                        value={ticketForm.category}
                        onChange={(e) => setTicketForm({ ...ticketForm, category: e.target.value })}
                      >
                        {ticketCategories.map(cat => (
                          <option key={cat.value} value={cat.value}>{cat.label}</option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label htmlFor="priority">Priority</label>
                      <select
                        id="priority"
                        value={ticketForm.priority}
                        onChange={(e) => setTicketForm({ ...ticketForm, priority: e.target.value })}
                      >
                        <option value="low">Low</option>
                        <option value="normal">Normal</option>
                        <option value="high">High</option>
                        <option value="urgent">Urgent</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label htmlFor="description">Description *</label>
                    <textarea
                      id="description"
                      value={ticketForm.description}
                      onChange={(e) => setTicketForm({ ...ticketForm, description: e.target.value })}
                      placeholder="Please describe your issue in detail. Include any error messages, steps to reproduce, and what you've already tried."
                      rows={6}
                    />
                  </div>

                  <button type="submit" className="btn-primary" disabled={submitting}>
                    {submitting ? (
                      <>
                        <i className="fas fa-spinner fa-spin"></i> Submitting...
                      </>
                    ) : (
                      <>
                        <i className="fas fa-paper-plane"></i> Submit Ticket
                      </>
                    )}
                  </button>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* My Tickets Tab */}
        {activeTab === 'tickets' && (
          <div className="tickets-section">
            <div className="tickets-header">
              <h2>My Support Tickets</h2>
              <button className="btn-primary" onClick={() => setActiveTab('contact')}>
                <i className="fas fa-plus"></i> New Ticket
              </button>
            </div>

            {loadingTickets ? (
              <div className="loading-state">
                <i className="fas fa-spinner fa-spin"></i>
                <p>Loading tickets...</p>
              </div>
            ) : tickets.length === 0 ? (
              <div className="empty-state">
                <i className="fas fa-ticket-alt"></i>
                <h3>No tickets yet</h3>
                <p>When you submit a support ticket, it will appear here.</p>
                <button className="btn-primary" onClick={() => setActiveTab('contact')}>
                  Submit Your First Ticket
                </button>
              </div>
            ) : (
              <div className="tickets-list">
                {tickets.map(ticket => (
                  <div key={ticket.id} className="ticket-card">
                    <div className="ticket-header">
                      <span className="ticket-id">#{ticket.id}</span>
                      <span className={`ticket-status ${getStatusBadgeClass(ticket.status)}`}>
                        {ticket.status.replace('_', ' ')}
                      </span>
                    </div>
                    <h3 className="ticket-subject">{ticket.subject}</h3>
                    <p className="ticket-preview">{ticket.description?.substring(0, 150)}...</p>
                    <div className="ticket-meta">
                      <span className="ticket-category">
                        <i className="fas fa-tag"></i> {ticket.category}
                      </span>
                      <span className="ticket-date">
                        <i className="fas fa-clock"></i> {new Date(ticket.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Additional Resources */}
      <section className="additional-resources">
        <h2>Additional Resources</h2>
        <div className="resources-grid">
          <a href="/knowledge-base" className="resource-card">
            <i className="fas fa-database"></i>
            <h3>Knowledge Base</h3>
            <p>Browse our internal documentation and guides</p>
          </a>
          <a href="https://academy.perenniaai.com" target="_blank" rel="noopener noreferrer" className="resource-card">
            <i className="fas fa-graduation-cap"></i>
            <h3>Perennia Academy</h3>
            <p>Video courses and certifications</p>
          </a>
          <a href="https://community.perenniaai.com" target="_blank" rel="noopener noreferrer" className="resource-card">
            <i className="fas fa-users"></i>
            <h3>Community Forum</h3>
            <p>Connect with other users</p>
          </a>
          <a href="https://changelog.perenniaai.com" target="_blank" rel="noopener noreferrer" className="resource-card">
            <i className="fas fa-bullhorn"></i>
            <h3>What's New</h3>
            <p>Latest features and updates</p>
          </a>
        </div>
      </section>
    </div>
  );
};

export default Support;
