/**
 * SmartDocs Page - Clean Queue View
 *
 * Simple, focused interface showing document collection status:
 * - Client name
 * - Completion percentage with progress bar
 * - Documents requested / received counts
 * - SLA status (row turns red when breached)
 *
 * Click a row to open the client's document portal
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import './SmartDocs.css';

function SmartDocs() {
  const navigate = useNavigate();
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [slaFilter, setSlaFilter] = useState('all');
  const [stats, setStats] = useState({ total: 0, breached: 0, atRisk: 0, onTrack: 0 });

  // Fetch queue data
  const fetchQueueData = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

      // Try queue endpoint first
      let response = await fetch('/api/v1/smart-docs/queue', { headers });

      if (response.ok) {
        const data = await response.json();
        setClients(data.queue || []);
        setStats({
          total: data.total || 0,
          breached: data.summary?.with_breaches || 0,
          atRisk: data.summary?.at_risk || 0,
          onTrack: (data.total || 0) - (data.summary?.with_breaches || 0) - (data.summary?.at_risk || 0)
        });
      } else {
        // Fallback: fetch loans and calculate stats
        response = await fetch('/api/v1/smart-docs/loans', { headers });
        if (!response.ok) {
          response = await fetch('/api/v1/loans/', { headers });
        }

        if (response.ok) {
          const data = await response.json();
          const loans = data.loans || (Array.isArray(data) ? data : []);

          // Transform to queue format
          const queueData = loans
            .filter(loan => {
              const stage = (loan.stage || '').toLowerCase();
              return stage !== 'funded' && stage !== 'closed';
            })
            .map(loan => {
              const docsRequested = loan.docs_requested || 8;
              const docsReceived = loan.docs_received || 0;
              const completionPct = docsRequested > 0 ? Math.round((docsReceived / docsRequested) * 100) : 0;
              const daysWaiting = loan.created_at
                ? Math.floor((new Date() - new Date(loan.created_at)) / (1000 * 60 * 60 * 24))
                : 0;
              const slaStatus = daysWaiting > 5 ? 'BREACHED' : daysWaiting > 3 ? 'AT_RISK' : 'GOOD';

              return {
                loan_id: loan.id,
                client_name: loan.borrower_name || loan.primary_borrower_name || 'Unknown',
                borrower_email: loan.borrower_email,
                docs_requested: docsRequested,
                docs_received: docsReceived,
                completion_percentage: completionPct,
                sla_status: slaStatus,
                has_sla_breach: slaStatus === 'BREACHED',
                last_activity: loan.updated_at || loan.created_at
              };
            });

          setClients(queueData);
          setStats({
            total: queueData.length,
            breached: queueData.filter(c => c.sla_status === 'BREACHED').length,
            atRisk: queueData.filter(c => c.sla_status === 'AT_RISK').length,
            onTrack: queueData.filter(c => c.sla_status === 'GOOD').length
          });
        }
      }
    } catch (err) {
      console.error('Error fetching queue data:', err);
      setClients([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchQueueData();
  }, [fetchQueueData]);

  // Filter clients based on search and SLA filter
  const filteredClients = clients.filter(client => {
    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      const nameMatch = client.client_name?.toLowerCase().includes(query);
      const emailMatch = client.borrower_email?.toLowerCase().includes(query);
      if (!nameMatch && !emailMatch) return false;
    }

    // SLA filter
    if (slaFilter !== 'all' && client.sla_status !== slaFilter) {
      return false;
    }

    return true;
  });

  // Navigate to client document portal
  const handleClientClick = (loanId) => {
    navigate(`/smart-docs/client/${loanId}`);
  };

  return (
    <div className="smart-docs-page">
      {/* Header */}
      <div className="smart-docs-header">
        <div className="header-content">
          <h1>Smart Docs</h1>
          <p className="subtitle">Document collection queue</p>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="stats-cards">
        <div className="stat-card total">
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">Total Clients</div>
        </div>
        <div className="stat-card breached" onClick={() => setSlaFilter(slaFilter === 'BREACHED' ? 'all' : 'BREACHED')}>
          <div className="stat-value">{stats.breached}</div>
          <div className="stat-label">SLA Breached</div>
        </div>
        <div className="stat-card at-risk" onClick={() => setSlaFilter(slaFilter === 'AT_RISK' ? 'all' : 'AT_RISK')}>
          <div className="stat-value">{stats.atRisk}</div>
          <div className="stat-label">At Risk</div>
        </div>
        <div className="stat-card on-track" onClick={() => setSlaFilter(slaFilter === 'GOOD' ? 'all' : 'GOOD')}>
          <div className="stat-value">{stats.onTrack}</div>
          <div className="stat-label">On Track</div>
        </div>
      </div>

      {/* Search and Filter */}
      <div className="search-filter-bar">
        <div className="search-input-wrapper">
          <span className="search-icon">🔍</span>
          <input
            type="text"
            className="search-input"
            placeholder="Search by client name or email..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="clear-search" onClick={() => setSearchQuery('')}>×</button>
          )}
        </div>
        <select
          className="sla-filter"
          value={slaFilter}
          onChange={(e) => setSlaFilter(e.target.value)}
        >
          <option value="all">All Status</option>
          <option value="BREACHED">SLA Breached</option>
          <option value="AT_RISK">At Risk</option>
          <option value="GOOD">On Track</option>
        </select>
      </div>

      {/* Client Queue Table */}
      <div className="queue-table-container">
        {loading ? (
          <div className="loading-state">
            <div className="spinner" />
            <p>Loading clients...</p>
          </div>
        ) : filteredClients.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">📄</span>
            <h3>{searchQuery ? 'No matching clients' : 'No clients in queue'}</h3>
            <p>{searchQuery ? 'Try a different search term' : 'All documents have been collected'}</p>
          </div>
        ) : (
          <table className="queue-table">
            <thead>
              <tr>
                <th className="col-client">Client</th>
                <th className="col-progress">Progress</th>
                <th className="col-requested">Requested</th>
                <th className="col-received">Received</th>
                <th className="col-status">Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredClients.map((client) => (
                <tr
                  key={client.loan_id}
                  className={`queue-row ${client.has_sla_breach ? 'sla-breached-row' : ''} ${client.sla_status === 'AT_RISK' ? 'sla-at-risk-row' : ''}`}
                  onClick={() => handleClientClick(client.loan_id)}
                >
                  <td className="col-client">
                    <div className="client-info">
                      <span className="client-name">{client.client_name || client.borrower_name}</span>
                      {client.borrower_email && (
                        <span className="client-email">{client.borrower_email}</span>
                      )}
                    </div>
                  </td>
                  <td className="col-progress">
                    <div className="progress-cell">
                      <div className="progress-bar-container">
                        <div
                          className={`progress-bar-fill ${client.completion_percentage === 100 ? 'complete' : ''}`}
                          style={{ width: `${client.completion_percentage}%` }}
                        />
                      </div>
                      <span className="progress-text">{client.completion_percentage}%</span>
                    </div>
                  </td>
                  <td className="col-requested">
                    <span className="count-badge requested">{client.docs_requested || client.total_requested || 0}</span>
                  </td>
                  <td className="col-received">
                    <span className="count-badge received">{client.docs_received || client.received_valid || 0}</span>
                  </td>
                  <td className="col-status">
                    <span className={`status-badge status-${client.sla_status?.toLowerCase()}`}>
                      {client.sla_status === 'BREACHED' ? 'Breached' :
                       client.sla_status === 'AT_RISK' ? 'At Risk' : 'On Track'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default SmartDocs;
