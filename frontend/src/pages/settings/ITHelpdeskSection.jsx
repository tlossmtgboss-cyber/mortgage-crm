import React, { useState, useEffect } from 'react';
import { toast } from '../../utils/toast';
import { API_BASE_URL } from './shared/constants';
import { getToken } from '../../utils/tokenStore';

const ITHelpdeskSection = () => {
  const [itTickets, setItTickets] = useState([]);
  const [loadingTickets, setLoadingTickets] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [ticketStatusFilter, setTicketStatusFilter] = useState('all');
  const [newTicket, setNewTicket] = useState({
    title: '', description: '', category: 'dev_env', urgency: 'normal',
    affected_system: '', affected_project: '', logs_attached: []
  });
  const [submittingTicket, setSubmittingTicket] = useState(false);
  const [resolutionNotes, setResolutionNotes] = useState('');

  useEffect(() => {
    fetchItTickets();
  }, [ticketStatusFilter]);

  const fetchItTickets = async () => {
    setLoadingTickets(true);
    try {
      const token = getToken();
      const statusParam = ticketStatusFilter !== 'all' ? `?status=${ticketStatusFilter}` : '';
      const response = await fetch(`${API_BASE_URL}/api/v1/it-helpdesk/tickets${statusParam}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setItTickets(data.tickets || []);
      } else {
        setItTickets([]);
      }
    } catch (error) {
      console.error('Error fetching IT tickets:', error);
      setItTickets([]);
    } finally {
      setLoadingTickets(false);
    }
  };

  const submitItTicket = async () => {
    if (!newTicket.description.trim()) { toast.error('Please describe the problem'); return; }
    setSubmittingTicket(true);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/it-helpdesk/submit`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(newTicket)
      });
      if (response.ok) {
        const data = await response.json();
        toast.success(`Ticket created! AI diagnosis: ${data.root_cause}`);
        setNewTicket({ title: '', description: '', category: 'dev_env', urgency: 'normal', affected_system: '', affected_project: '', logs_attached: [] });
        fetchItTickets();
      } else {
        const error = await response.json();
        toast.error(`Failed to submit ticket: ${error.detail || 'Unknown error'}`);
      }
    } catch (error) {
      toast.error('Error submitting ticket. Please try again.');
    } finally {
      setSubmittingTicket(false);
    }
  };

  const approveTicket = async (ticketId) => {
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/it-helpdesk/tickets/${ticketId}/approve`, {
        method: 'POST', headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) { toast.success('Fix approved!'); fetchItTickets(); }
      else { toast.error('Failed to approve fix'); }
    } catch (error) { toast.error('Error approving ticket'); }
  };

  const resolveTicket = async (ticketId) => {
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/it-helpdesk/tickets/${ticketId}/resolve`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolution_notes: resolutionNotes })
      });
      if (response.ok) { toast.success('Ticket marked as resolved!'); setResolutionNotes(''); setSelectedTicket(null); fetchItTickets(); }
      else { toast.error('Failed to resolve ticket'); }
    } catch (error) { toast.error('Error resolving ticket'); }
  };

  return (
    <div className="it-helpdesk-section">
      <h2>AI IT Helpdesk</h2>
      <p className="section-description">
        Get AI-powered help for technical issues. Describe your problem and the AI will diagnose it and propose a fix.
      </p>

      {/* Submit New Ticket */}
      <div className="helpdesk-submit-card">
        <h3>Submit IT Issue</h3>
        <div className="form-group">
          <label>Title (optional)</label>
          <input type="text" placeholder="Brief summary of the issue" value={newTicket.title}
            onChange={(e) => setNewTicket({...newTicket, title: e.target.value})} className="input-field" />
        </div>
        <div className="form-group">
          <label>Describe the problem *</label>
          <textarea placeholder="What's happening? Include any error messages you're seeing..." value={newTicket.description}
            onChange={(e) => setNewTicket({...newTicket, description: e.target.value})} className="textarea-field" rows="5" />
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>Category</label>
            <select value={newTicket.category} onChange={(e) => setNewTicket({...newTicket, category: e.target.value})} className="select-field">
              <option value="dev_env">Development Environment</option>
              <option value="build_deploy">Build & Deployment</option>
              <option value="git">Git Issues</option>
              <option value="vscode">VS Code</option>
              <option value="os">Operating System</option>
              <option value="network">Network Issues</option>
              <option value="saas_config">SaaS Configuration</option>
            </select>
          </div>
          <div className="form-group">
            <label>Urgency</label>
            <select value={newTicket.urgency} onChange={(e) => setNewTicket({...newTicket, urgency: e.target.value})} className="select-field">
              <option value="low">Low</option><option value="normal">Normal</option>
              <option value="high">High</option><option value="critical">Critical</option>
            </select>
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>System (optional)</label>
            <input type="text" placeholder="e.g., Vercel, Railway, GitHub" value={newTicket.affected_system}
              onChange={(e) => setNewTicket({...newTicket, affected_system: e.target.value})} className="input-field" />
          </div>
          <div className="form-group">
            <label>Project (optional)</label>
            <input type="text" placeholder="e.g., mortgage-crm" value={newTicket.affected_project}
              onChange={(e) => setNewTicket({...newTicket, affected_project: e.target.value})} className="input-field" />
          </div>
        </div>
        <button onClick={submitItTicket} className="btn-submit-ticket" disabled={submittingTicket || !newTicket.description.trim()}>
          {submittingTicket ? 'Analyzing...' : 'Submit Issue →'}
        </button>
      </div>

      {/* Ticket List */}
      <div className="helpdesk-tickets-card">
        <div className="tickets-header">
          <h3>Your IT Tickets</h3>
          <div className="ticket-filters">
            {['all', 'awaiting_approval', 'approved', 'resolved'].map(filter => (
              <button key={filter} className={`filter-btn ${ticketStatusFilter === filter ? 'active' : ''}`}
                onClick={() => setTicketStatusFilter(filter)}>
                {filter === 'all' ? 'All' : filter === 'awaiting_approval' ? 'Awaiting Approval' : filter.charAt(0).toUpperCase() + filter.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {loadingTickets ? (
          <p>Loading tickets...</p>
        ) : itTickets.length === 0 ? (
          <div className="empty-state"><p>No IT tickets yet.</p><p className="empty-hint">Submit an issue above to get AI-powered help.</p></div>
        ) : (
          <div className="tickets-list">
            {itTickets.map((ticket) => (
              <div key={ticket.id} className={`ticket-item ${selectedTicket?.id === ticket.id ? 'selected' : ''}`}
                onClick={() => setSelectedTicket(ticket)}>
                <div className="ticket-header">
                  <div className="ticket-title">{ticket.title || ticket.description.substring(0, 50) + '...'}</div>
                  <span className={`ticket-status status-${ticket.status}`}>
                    {ticket.status === 'analyzing' && 'Analyzing'}
                    {ticket.status === 'awaiting_approval' && 'Awaiting Approval'}
                    {ticket.status === 'approved' && 'Approved'}
                    {ticket.status === 'resolved' && 'Resolved'}
                  </span>
                </div>
                <div className="ticket-meta">
                  <span>{new Date(ticket.created_at).toLocaleString()}</span>
                  {ticket.root_cause && <span> &bull; {ticket.root_cause}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Ticket Details */}
      {selectedTicket && (
        <div className="helpdesk-details-card">
          <h3>Ticket #{selectedTicket.id}: {selectedTicket.title || 'IT Issue'}</h3>
          <div className="detail-section"><h4>Problem Description</h4><p>{selectedTicket.description}</p></div>

          {selectedTicket.ai_diagnosis && (
            <div className="detail-section">
              <h4>AI Diagnosis</h4>
              <p><strong>Root Cause:</strong> {selectedTicket.root_cause}</p>
              <p>{selectedTicket.ai_diagnosis}</p>
            </div>
          )}

          {selectedTicket.proposed_fix && (
            <div className="detail-section">
              <h4>Proposed Fix ({selectedTicket.proposed_fix.risk_level} risk)</h4>
              {selectedTicket.proposed_fix.steps && (
                <div><p><strong>Steps:</strong></p><ol>{selectedTicket.proposed_fix.steps.map((step, i) => (<li key={i}>{step}</li>))}</ol></div>
              )}
              {selectedTicket.proposed_fix.commands && selectedTicket.proposed_fix.commands.length > 0 && (
                <div className="commands-section">
                  <p><strong>Commands to Run:</strong></p>
                  {selectedTicket.proposed_fix.commands.map((cmd, i) => (
                    <div key={i} className="command-block">
                      <p className="command-description">{cmd.description}</p>
                      <div className="command-display">
                        <code>{cmd.command}</code>
                        <button onClick={() => { navigator.clipboard.writeText(cmd.command); toast.success('Command copied!'); }} className="btn-copy-cmd">Copy</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {selectedTicket.status === 'awaiting_approval' && (
                <div className="action-buttons">
                  <button onClick={() => approveTicket(selectedTicket.id)} className="btn-approve">Approve Fix</button>
                  <button onClick={() => setSelectedTicket(null)} className="btn-dismiss">Dismiss</button>
                </div>
              )}
            </div>
          )}

          {selectedTicket.status === 'approved' && (
            <div className="detail-section">
              <h4>Mark as Resolved</h4>
              <p>After running the commands above, describe the result:</p>
              <textarea placeholder="What happened when you ran the commands?" value={resolutionNotes}
                onChange={(e) => setResolutionNotes(e.target.value)} className="textarea-field" rows="3" />
              <button onClick={() => resolveTicket(selectedTicket.id)} className="btn-resolve" disabled={!resolutionNotes.trim()}>
                Mark as Resolved
              </button>
            </div>
          )}

          {selectedTicket.status === 'resolved' && selectedTicket.resolution_notes && (
            <div className="detail-section">
              <h4>Resolution</h4>
              <p>{selectedTicket.resolution_notes}</p>
              <p className="resolved-date">Resolved on {new Date(selectedTicket.resolved_at).toLocaleString()}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ITHelpdeskSection;
