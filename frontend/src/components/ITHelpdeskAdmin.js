import React, { useState, useEffect, useCallback } from 'react';
import { getAuthHeaders } from '../utils/auth';
import './ITHelpdeskAdmin.css';
import { toast } from '../utils/toast';

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

function ITHelpdeskAdmin() {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [urgencyFilter, setUrgencyFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [stats, setStats] = useState({
    total: 0,
    open: 0,
    awaiting_approval: 0,
    resolved: 0,
    critical: 0
  });
  const [adminNotes, setAdminNotes] = useState('');
  const [assignedTo, setAssignedTo] = useState('');
  const [teamMembers, setTeamMembers] = useState([]);

  const fetchTickets = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.append('status', statusFilter);
      if (urgencyFilter !== 'all') params.append('urgency', urgencyFilter);
      if (categoryFilter !== 'all') params.append('category', categoryFilter);
      if (searchQuery) params.append('search', searchQuery);

      const response = await fetch(`${API_BASE}/api/v1/it-helpdesk/admin/tickets?${params}`, {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setTickets(data.tickets || []);
        setStats(data.stats || {
          total: data.tickets?.length || 0,
          open: 0,
          awaiting_approval: 0,
          resolved: 0,
          critical: 0
        });
      } else {
        console.error('Failed to fetch admin tickets');
        setTickets([]);
      }
    } catch (error) {
      console.error('Error fetching admin tickets:', error);
      setTickets([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, urgencyFilter, categoryFilter, searchQuery]);

  const fetchTeamMembers = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/users`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setTeamMembers(data || []);
      }
    } catch (error) {
      console.error('Error fetching team members:', error);
    }
  };

  useEffect(() => {
    fetchTickets();
    fetchTeamMembers();
  }, [fetchTickets]);

  const updateTicketStatus = async (ticketId, newStatus) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/it-helpdesk/admin/tickets/${ticketId}/status`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({ status: newStatus })
      });

      if (response.ok) {
        fetchTickets();
        if (selectedTicket?.id === ticketId) {
          setSelectedTicket({ ...selectedTicket, status: newStatus });
        }
      } else {
        toast.error('Failed to update ticket status');
      }
    } catch (error) {
      console.error('Error updating ticket status:', error);
      toast.error('Error updating ticket status');
    }
  };

  const assignTicket = async (ticketId) => {
    if (!assignedTo) {
      toast.error('Please select a team member to assign');
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/api/v1/it-helpdesk/admin/tickets/${ticketId}/assign`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({ assigned_to: assignedTo })
      });

      if (response.ok) {
        toast.success('Ticket assigned successfully');
        fetchTickets();
        setAssignedTo('');
      } else {
        toast.error('Failed to assign ticket');
      }
    } catch (error) {
      console.error('Error assigning ticket:', error);
      toast.error('Error assigning ticket');
    }
  };

  const addAdminNote = async (ticketId) => {
    if (!adminNotes.trim()) {
      toast.error('Please enter a note');
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/api/v1/it-helpdesk/admin/tickets/${ticketId}/notes`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ note: adminNotes })
      });

      if (response.ok) {
        toast.success('Note added successfully');
        setAdminNotes('');
        fetchTickets();
      } else {
        toast.error('Failed to add note');
      }
    } catch (error) {
      console.error('Error adding note:', error);
      toast.error('Error adding note');
    }
  };

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'analyzing': return 'status-analyzing';
      case 'awaiting_approval': return 'status-awaiting';
      case 'approved': return 'status-approved';
      case 'fixing': return 'status-fixing';
      case 'resolved': return 'status-resolved';
      case 'failed': return 'status-failed';
      default: return '';
    }
  };

  const getUrgencyBadgeClass = (urgency) => {
    switch (urgency) {
      case 'critical': return 'urgency-critical';
      case 'high': return 'urgency-high';
      case 'normal': return 'urgency-normal';
      case 'low': return 'urgency-low';
      default: return '';
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleString();
  };

  return (
    <div className="it-admin-container">
      <div className="it-admin-header">
        <h2>IT Helpdesk Administration</h2>
        <p className="section-description">
          Manage all IT support tickets across the organization
        </p>
      </div>

      {/* Stats Cards */}
      <div className="it-admin-stats">
        <div className="stat-card">
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">Total Tickets</div>
        </div>
        <div className="stat-card open">
          <div className="stat-value">{stats.open || tickets.filter(t => t.status !== 'resolved').length}</div>
          <div className="stat-label">Open Tickets</div>
        </div>
        <div className="stat-card awaiting">
          <div className="stat-value">{stats.awaiting_approval || tickets.filter(t => t.status === 'awaiting_approval').length}</div>
          <div className="stat-label">Awaiting Approval</div>
        </div>
        <div className="stat-card critical">
          <div className="stat-value">{stats.critical || tickets.filter(t => t.urgency === 'critical').length}</div>
          <div className="stat-label">Critical</div>
        </div>
        <div className="stat-card resolved">
          <div className="stat-value">{stats.resolved || tickets.filter(t => t.status === 'resolved').length}</div>
          <div className="stat-label">Resolved</div>
        </div>
      </div>

      {/* Filters */}
      <div className="it-admin-filters">
        <div className="filter-group">
          <label>Search</label>
          <input
            type="text"
            placeholder="Search tickets..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="filter-input"
          />
        </div>
        <div className="filter-group">
          <label>Status</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Statuses</option>
            <option value="analyzing">Analyzing</option>
            <option value="awaiting_approval">Awaiting Approval</option>
            <option value="approved">Approved</option>
            <option value="fixing">Fixing</option>
            <option value="resolved">Resolved</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        <div className="filter-group">
          <label>Urgency</label>
          <select
            value={urgencyFilter}
            onChange={(e) => setUrgencyFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Urgencies</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="normal">Normal</option>
            <option value="low">Low</option>
          </select>
        </div>
        <div className="filter-group">
          <label>Category</label>
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Categories</option>
            <option value="dev_env">Development Environment</option>
            <option value="build_deploy">Build & Deployment</option>
            <option value="git">Git Issues</option>
            <option value="vscode">VS Code</option>
            <option value="os">Operating System</option>
            <option value="network">Network Issues</option>
            <option value="saas_config">SaaS Configuration</option>
          </select>
        </div>
        <button onClick={fetchTickets} className="btn-refresh">
          Refresh
        </button>
      </div>

      <div className="it-admin-content">
        {/* Ticket List */}
        <div className="tickets-panel">
          <h3>All Tickets ({tickets.length})</h3>

          {loading ? (
            <div className="loading-state">Loading tickets...</div>
          ) : tickets.length === 0 ? (
            <div className="empty-state">
              <p>No tickets found matching your filters.</p>
            </div>
          ) : (
            <div className="tickets-list">
              {tickets.map((ticket) => (
                <div
                  key={ticket.id}
                  className={`ticket-card ${selectedTicket?.id === ticket.id ? 'selected' : ''}`}
                  onClick={() => setSelectedTicket(ticket)}
                >
                  <div className="ticket-card-header">
                    <span className="ticket-id">#{ticket.id}</span>
                    <span className={`urgency-badge ${getUrgencyBadgeClass(ticket.urgency)}`}>
                      {ticket.urgency}
                    </span>
                  </div>
                  <div className="ticket-title">
                    {ticket.title || ticket.description?.substring(0, 50) + '...'}
                  </div>
                  <div className="ticket-meta">
                    <span className={`status-badge ${getStatusBadgeClass(ticket.status)}`}>
                      {ticket.status?.replace('_', ' ')}
                    </span>
                    <span className="category">{ticket.category?.replace('_', ' ')}</span>
                  </div>
                  <div className="ticket-footer">
                    <span className="submitter">By: {ticket.user_name || `User #${ticket.user_id}`}</span>
                    <span className="date">{formatDate(ticket.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Ticket Details */}
        <div className="details-panel">
          {selectedTicket ? (
            <>
              <div className="details-header">
                <h3>Ticket #{selectedTicket.id}</h3>
                <span className={`status-badge large ${getStatusBadgeClass(selectedTicket.status)}`}>
                  {selectedTicket.status?.replace('_', ' ')}
                </span>
              </div>

              <div className="details-section">
                <h4>Ticket Information</h4>
                <div className="info-grid">
                  <div className="info-item">
                    <label>Title</label>
                    <span>{selectedTicket.title || 'No title'}</span>
                  </div>
                  <div className="info-item">
                    <label>Submitted By</label>
                    <span>{selectedTicket.user_name || `User #${selectedTicket.user_id}`}</span>
                  </div>
                  <div className="info-item">
                    <label>Category</label>
                    <span>{selectedTicket.category?.replace('_', ' ')}</span>
                  </div>
                  <div className="info-item">
                    <label>Urgency</label>
                    <span className={`urgency-badge ${getUrgencyBadgeClass(selectedTicket.urgency)}`}>
                      {selectedTicket.urgency}
                    </span>
                  </div>
                  <div className="info-item">
                    <label>Created</label>
                    <span>{formatDate(selectedTicket.created_at)}</span>
                  </div>
                  <div className="info-item">
                    <label>System</label>
                    <span>{selectedTicket.affected_system || '-'}</span>
                  </div>
                  <div className="info-item">
                    <label>Project</label>
                    <span>{selectedTicket.affected_project || '-'}</span>
                  </div>
                  <div className="info-item">
                    <label>Assigned To</label>
                    <span>{selectedTicket.assigned_to_name || 'Unassigned'}</span>
                  </div>
                </div>
              </div>

              <div className="details-section">
                <h4>Problem Description</h4>
                <div className="description-box">
                  {selectedTicket.description}
                </div>
              </div>

              {selectedTicket.ai_diagnosis && (
                <div className="details-section">
                  <h4>AI Diagnosis</h4>
                  <div className="diagnosis-box">
                    <p><strong>Root Cause:</strong> {selectedTicket.root_cause}</p>
                    <p>{selectedTicket.ai_diagnosis}</p>
                  </div>
                </div>
              )}

              {selectedTicket.proposed_fix && (
                <div className="details-section">
                  <h4>Proposed Fix</h4>
                  <div className="fix-box">
                    <p className="risk-level">
                      Risk Level: <span className={`risk-${selectedTicket.proposed_fix.risk_level}`}>
                        {selectedTicket.proposed_fix.risk_level}
                      </span>
                    </p>

                    {selectedTicket.proposed_fix.steps && (
                      <div className="fix-steps">
                        <p><strong>Steps:</strong></p>
                        <ol>
                          {selectedTicket.proposed_fix.steps.map((step, i) => (
                            <li key={i}>{step}</li>
                          ))}
                        </ol>
                      </div>
                    )}

                    {selectedTicket.proposed_fix.commands && selectedTicket.proposed_fix.commands.length > 0 && (
                      <div className="fix-commands">
                        <p><strong>Commands:</strong></p>
                        {selectedTicket.proposed_fix.commands.map((cmd, i) => (
                          <div key={i} className="command-item">
                            <p className="command-desc">{cmd.description}</p>
                            <code>{cmd.command}</code>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {selectedTicket.admin_notes && selectedTicket.admin_notes.length > 0 && (
                <div className="details-section">
                  <h4>Admin Notes</h4>
                  <div className="notes-list">
                    {selectedTicket.admin_notes.map((note, i) => (
                      <div key={i} className="note-item">
                        <p>{note.note}</p>
                        <span className="note-meta">
                          {note.added_by_name} - {formatDate(note.added_at)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Admin Actions */}
              <div className="details-section">
                <h4>Admin Actions</h4>

                <div className="action-group">
                  <label>Update Status</label>
                  <div className="action-row">
                    <select
                      className="action-select"
                      value={selectedTicket.status}
                      onChange={(e) => updateTicketStatus(selectedTicket.id, e.target.value)}
                    >
                      <option value="analyzing">Analyzing</option>
                      <option value="awaiting_approval">Awaiting Approval</option>
                      <option value="approved">Approved</option>
                      <option value="fixing">Fixing</option>
                      <option value="resolved">Resolved</option>
                      <option value="failed">Failed</option>
                    </select>
                  </div>
                </div>

                <div className="action-group">
                  <label>Assign To</label>
                  <div className="action-row">
                    <select
                      className="action-select"
                      value={assignedTo}
                      onChange={(e) => setAssignedTo(e.target.value)}
                    >
                      <option value="">Select team member...</option>
                      {teamMembers.map((member) => (
                        <option key={member.id} value={member.id}>
                          {member.full_name || member.email}
                        </option>
                      ))}
                    </select>
                    <button onClick={() => assignTicket(selectedTicket.id)} className="btn-action">
                      Assign
                    </button>
                  </div>
                </div>

                <div className="action-group">
                  <label>Add Note</label>
                  <div className="action-row vertical">
                    <textarea
                      className="note-input"
                      placeholder="Add an admin note..."
                      value={adminNotes}
                      onChange={(e) => setAdminNotes(e.target.value)}
                      rows="3"
                    />
                    <button onClick={() => addAdminNote(selectedTicket.id)} className="btn-action">
                      Add Note
                    </button>
                  </div>
                </div>
              </div>

              {selectedTicket.resolution_notes && (
                <div className="details-section">
                  <h4>Resolution</h4>
                  <div className="resolution-box">
                    <p>{selectedTicket.resolution_notes}</p>
                    <span className="resolution-meta">
                      Resolved: {formatDate(selectedTicket.resolved_at)}
                    </span>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="no-selection">
              <p>Select a ticket from the list to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ITHelpdeskAdmin;
