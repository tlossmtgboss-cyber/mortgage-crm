/**
 * IT Tickets Page
 * Support ticket management with active and completed ticket views
 */

import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import { getAuthHeaders } from '../utils/auth';
import { toast } from '../utils/toast';
import './Support.css';

const Support = () => {
  const [activeTab, setActiveTab] = useState('active');
  const [ticketForm, setTicketForm] = useState({
    subject: '',
    category: '',
    priority: 'normal',
    description: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [tickets, setTickets] = useState([]);
  const [loadingTickets, setLoadingTickets] = useState(false);
  const [showNewTicketForm, setShowNewTicketForm] = useState(false);
  const [completingTicketId, setCompletingTicketId] = useState(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [screenshots, setScreenshots] = useState([]);
  const [uploadingScreenshot, setUploadingScreenshot] = useState(false);

  const tabs = [
    { id: 'active', label: 'Active Tickets', icon: 'fa-ticket-alt' },
    { id: 'completed', label: 'Completed Tickets', icon: 'fa-check-circle' },
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

  // Load tickets on component mount
  useEffect(() => {
    loadTickets();
  }, []);

  const loadTickets = async () => {
    setLoadingTickets(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/support/tickets`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setTickets(data.tickets || []);
        setIsAdmin(data.is_admin || false);
      }
    } catch (err) {
      console.error('Error loading tickets:', err);
    } finally {
      setLoadingTickets(false);
    }
  };

  const handleScreenshotUpload = async (e) => {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;

    // Limit to 5 screenshots
    if (screenshots.length + files.length > 5) {
      toast.error('Maximum 5 screenshots allowed');
      return;
    }

    setUploadingScreenshot(true);
    try {
      const newScreenshots = await Promise.all(
        files.map(async (file) => {
          // Validate file type
          if (!file.type.startsWith('image/')) {
            throw new Error(`${file.name} is not an image`);
          }
          // Validate file size (max 5MB)
          if (file.size > 5 * 1024 * 1024) {
            throw new Error(`${file.name} is too large (max 5MB)`);
          }

          return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
              resolve({
                name: file.name,
                type: file.type,
                size: file.size,
                data: reader.result,
              });
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
          });
        })
      );

      setScreenshots([...screenshots, ...newScreenshots]);
    } catch (err) {
      toast.error(err.message || 'Failed to upload screenshot');
    } finally {
      setUploadingScreenshot(false);
      e.target.value = ''; // Reset input
    }
  };

  const removeScreenshot = (index) => {
    setScreenshots(screenshots.filter((_, i) => i !== index));
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
        body: JSON.stringify({
          ...ticketForm,
          attachments: screenshots.map(s => ({
            name: s.name,
            type: s.type,
            data: s.data,
          }))
        })
      });

      if (response.ok) {
        toast.success('Support ticket submitted successfully. We\'ll get back to you soon!');
        setTicketForm({ subject: '', category: '', priority: 'normal', description: '' });
        setScreenshots([]);
        setShowNewTicketForm(false);
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

  const handleCompleteTicket = async (ticketId) => {
    setCompletingTicketId(ticketId);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/support/tickets/${ticketId}/complete`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
        body: JSON.stringify({ status: 'resolved' })
      });

      if (response.ok) {
        toast.success('Ticket marked as completed');
        loadTickets();
      } else {
        throw new Error('Failed to complete ticket');
      }
    } catch (err) {
      toast.error('Failed to complete ticket. Please try again.');
    } finally {
      setCompletingTicketId(null);
    }
  };

  // Filter tickets by status
  const activeTickets = tickets.filter(t => t.status === 'open' || t.status === 'in_progress');
  const completedTickets = tickets.filter(t => t.status === 'resolved' || t.status === 'closed');

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'open': return 'status-open';
      case 'in_progress': return 'status-progress';
      case 'resolved': return 'status-resolved';
      case 'closed': return 'status-closed';
      default: return '';
    }
  };

  // Render a ticket card
  const renderTicketCard = (ticket, showCompleteButton = false) => (
    <div key={ticket.id} className="ticket-card">
      <div className="ticket-header">
        <span className="ticket-id">#{ticket.id}</span>
        <span className={`ticket-status ${getStatusBadgeClass(ticket.status)}`}>
          {ticket.status.replace('_', ' ')}
        </span>
      </div>
      <h3 className="ticket-subject">{ticket.subject}</h3>
      {/* Show submitter info for admins */}
      {isAdmin && (ticket.user_name || ticket.user_email) && (
        <div className="ticket-submitter">
          <i className="fas fa-user"></i>
          <span>{ticket.user_name || ticket.user_email}</span>
          {ticket.organization_name && (
            <span className="ticket-org">
              <i className="fas fa-building"></i> {ticket.organization_name}
            </span>
          )}
        </div>
      )}
      <p className="ticket-preview">{ticket.description?.substring(0, 150)}...</p>
      {ticket.attachment_count > 0 && (
        <div className="ticket-attachments">
          <i className="fas fa-paperclip"></i>
          <span>{ticket.attachment_count} attachment{ticket.attachment_count > 1 ? 's' : ''}</span>
        </div>
      )}
      <div className="ticket-meta">
        <span className="ticket-category">
          <i className="fas fa-tag"></i> {ticket.category}
        </span>
        <span className="ticket-priority">
          <i className="fas fa-flag"></i> {ticket.priority}
        </span>
        <span className="ticket-date">
          <i className="fas fa-clock"></i> {new Date(ticket.created_at).toLocaleDateString()}
        </span>
        {showCompleteButton && (
          <button
            className="btn-complete-ticket"
            onClick={() => handleCompleteTicket(ticket.id)}
            disabled={completingTicketId === ticket.id}
          >
            {completingTicketId === ticket.id ? (
              <><i className="fas fa-spinner fa-spin"></i> Completing...</>
            ) : (
              <><i className="fas fa-check"></i> Mark Complete</>
            )}
          </button>
        )}
      </div>
    </div>
  );

  return (
    <div className="support-page">
      <div className="page-header">
        <h1>IT Tickets</h1>
        <p>Manage and track support tickets</p>
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
            {tab.id === 'active' && activeTickets.length > 0 && (
              <span className="tab-badge">{activeTickets.length}</span>
            )}
            {tab.id === 'completed' && completedTickets.length > 0 && (
              <span className="tab-badge completed">{completedTickets.length}</span>
            )}
          </button>
        ))}
        <button
          className="btn-primary new-ticket-btn"
          onClick={() => setShowNewTicketForm(!showNewTicketForm)}
        >
          <i className={`fas ${showNewTicketForm ? 'fa-times' : 'fa-plus'}`}></i>
          {showNewTicketForm ? 'Cancel' : 'New Ticket'}
        </button>
      </div>

      {/* New Ticket Form */}
      {showNewTicketForm && (
        <div className="new-ticket-form-section">
          <div className="ticket-form-container">
            <h2>Submit a New Ticket</h2>
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

              <div className="form-group">
                <label>Screenshots (optional)</label>
                <div className="screenshot-upload-area">
                  <input
                    type="file"
                    id="screenshot-upload"
                    accept="image/*"
                    multiple
                    onChange={handleScreenshotUpload}
                    disabled={uploadingScreenshot || screenshots.length >= 5}
                    style={{ display: 'none' }}
                  />
                  <label htmlFor="screenshot-upload" className={`screenshot-upload-btn ${screenshots.length >= 5 ? 'disabled' : ''}`}>
                    {uploadingScreenshot ? (
                      <><i className="fas fa-spinner fa-spin"></i> Uploading...</>
                    ) : (
                      <><i className="fas fa-camera"></i> Add Screenshots</>
                    )}
                  </label>
                  <span className="screenshot-hint">Max 5 images, 5MB each</span>
                </div>
                {screenshots.length > 0 && (
                  <div className="screenshot-previews">
                    {screenshots.map((screenshot, index) => (
                      <div key={index} className="screenshot-preview">
                        <img src={screenshot.data} alt={screenshot.name} />
                        <button
                          type="button"
                          className="remove-screenshot"
                          onClick={() => removeScreenshot(index)}
                        >
                          <i className="fas fa-times"></i>
                        </button>
                        <span className="screenshot-name">{screenshot.name}</span>
                      </div>
                    ))}
                  </div>
                )}
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
      )}

      {/* Tab Content */}
      <div className="support-content">
        {/* Active Tickets Tab */}
        {activeTab === 'active' && (
          <div className="tickets-section">
            {loadingTickets ? (
              <div className="loading-state">
                <i className="fas fa-spinner fa-spin"></i>
                <p>Loading tickets...</p>
              </div>
            ) : activeTickets.length === 0 ? (
              <div className="empty-state">
                <i className="fas fa-ticket-alt"></i>
                <h3>No active tickets</h3>
                <p>All your tickets have been resolved or you haven't submitted any yet.</p>
                <button className="btn-primary" onClick={() => setShowNewTicketForm(true)}>
                  Submit a Ticket
                </button>
              </div>
            ) : (
              <div className="tickets-list">
                {activeTickets.map(ticket => renderTicketCard(ticket, true))}
              </div>
            )}
          </div>
        )}

        {/* Completed Tickets Tab */}
        {activeTab === 'completed' && (
          <div className="tickets-section">
            {loadingTickets ? (
              <div className="loading-state">
                <i className="fas fa-spinner fa-spin"></i>
                <p>Loading tickets...</p>
              </div>
            ) : completedTickets.length === 0 ? (
              <div className="empty-state">
                <i className="fas fa-check-circle"></i>
                <h3>No completed tickets</h3>
                <p>Tickets marked as complete will appear here.</p>
              </div>
            ) : (
              <div className="tickets-list">
                {completedTickets.map(ticket => renderTicketCard(ticket, false))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default Support;
