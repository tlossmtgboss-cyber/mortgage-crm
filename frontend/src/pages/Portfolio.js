import React, { useState, useEffect } from 'react';
import { portfolioAPI, mumAPI } from '../services/api';
import './Portfolio.css';

function Portfolio() {
  const [activeTab, setActiveTab] = useState('loans');
  const [portfolioData, setPortfolioData] = useState({
    totalLoans: 0,
    totalVolume: 0,
    activeLoans: 0,
    closedLoans: 0,
    loans: []
  });
  const [mumClients, setMumClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [filterView, setFilterView] = useState('all');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [stats, loans, mum] = await Promise.all([
        portfolioAPI.getStats(),
        portfolioAPI.getAll(),
        mumAPI.getAll()
      ]);

      setPortfolioData({
        totalLoans: stats.total_loans || 0,
        totalVolume: stats.total_volume || 0,
        activeLoans: stats.active_loans || 0,
        closedLoans: stats.closed_loans || 0,
        loans: loans.map(loan => ({
          id: loan.id,
          borrower: loan.client_name || loan.borrower_name || 'Unknown',
          loanAmount: loan.loan_amount || 0,
          loanType: loan.loan_type || 'N/A',
          status: loan.status || 'Unknown',
          closeDate: loan.close_date || loan.created_at,
          rate: loan.interest_rate || 0
        }))
      });

      setMumClients(mum || []);
    } catch (error) {
      console.error('Failed to load portfolio data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddClient = async (clientData) => {
    try {
      await mumAPI.create(clientData);
      loadData();
      setShowAddModal(false);
    } catch (error) {
      console.error('Failed to create client:', error);
      alert('Failed to create MUM client. Please try again.');
    }
  };

  const handleDeleteClient = async (id) => {
    if (!window.confirm('Delete this client?')) return;
    try {
      await mumAPI.delete(id);
      loadData();
    } catch (error) {
      console.error('Failed to delete client:', error);
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0
    }).format(amount);
  };

  const filteredMumClients = filterView === 'all'
    ? mumClients
    : filterView === 'opportunities'
    ? mumClients.filter(c => c.refinance_opportunity)
    : mumClients;

  const getDaysSinceFundingColor = (days) => {
    if (days < 180) return 'recent';
    if (days < 365) return 'medium';
    return 'old';
  };

  if (loading) {
    return (
      <div className="portfolio-container">
        <div className="loading">Loading portfolio...</div>
      </div>
    );
  }

  return (
    <div className="portfolio-container">
      <div className="portfolio-header">
        <h1 className="portfolio-title">Portfolio</h1>
        {activeTab === 'mum' && (
          <button className="btn-add" onClick={() => setShowAddModal(true)}>
            + Add MUM Client
          </button>
        )}
      </div>

      <div className="portfolio-stats">
        <div className="stat-card">
          <div className="stat-icon">💼</div>
          <div className="stat-info">
            <div className="stat-value">{portfolioData.totalLoans}</div>
            <div className="stat-label">Total Loans</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">💰</div>
          <div className="stat-info">
            <div className="stat-value">{formatCurrency(portfolioData.totalVolume)}</div>
            <div className="stat-label">Total Volume</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">🔄</div>
          <div className="stat-info">
            <div className="stat-value">{portfolioData.activeLoans}</div>
            <div className="stat-label">Active Loans</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">✅</div>
          <div className="stat-info">
            <div className="stat-value">{portfolioData.closedLoans}</div>
            <div className="stat-label">Closed Loans</div>
          </div>
        </div>
      </div>

      {/* CLIENT FOR LIFE ENGINE (MUM) TASKS */}
      <div className="mum-tasks-widget">
        <div className="mum-widget-header">
          <h3>♻️ Client for Life Engine (MUM)</h3>
          <span className="mum-count-badge">3 actions</span>
        </div>
        <div className="mum-tasks-list">
          <div className="mum-task-item">
            <div className="mum-task-icon">📅</div>
            <div className="mum-task-content">
              <div className="mum-task-title">Annual review due</div>
              <div className="mum-task-client">Tom Wilson</div>
            </div>
            <button className="btn-mum-action">Schedule</button>
          </div>
          <div className="mum-task-item">
            <div className="mum-task-icon">📉</div>
            <div className="mum-task-content">
              <div className="mum-task-title">Rate drop opportunity</div>
              <div className="mum-task-client">Lisa Brown</div>
            </div>
            <button className="btn-mum-action">Send alert</button>
          </div>
          <div className="mum-task-item">
            <div className="mum-task-icon">🎂</div>
            <div className="mum-task-content">
              <div className="mum-task-title">Home anniversary</div>
              <div className="mum-task-client">Mark Taylor</div>
            </div>
            <button className="btn-mum-action">Send card</button>
          </div>
        </div>
      </div>

      <div className="portfolio-tabs">
        <button
          className={activeTab === 'loans' ? 'active' : ''}
          onClick={() => setActiveTab('loans')}
        >
          Loan History
        </button>
        <button
          className={activeTab === 'mum' ? 'active' : ''}
          onClick={() => setActiveTab('mum')}
        >
          MUM Clients ({mumClients.length})
        </button>
      </div>

      {activeTab === 'loans' && (
        <div className="loans-table-container">
          <h2>Closed Loans</h2>
          <table className="loans-table">
            <thead>
              <tr>
                <th>Borrower</th>
                <th>Loan Amount</th>
                <th>Type</th>
                <th>Rate</th>
                <th>Status</th>
                <th>Close Date</th>
              </tr>
            </thead>
            <tbody>
              {portfolioData.loans.map((loan) => (
                <tr key={loan.id}>
                  <td>{loan.borrower}</td>
                  <td>{formatCurrency(loan.loanAmount)}</td>
                  <td>{loan.loanType}</td>
                  <td>{loan.rate}%</td>
                  <td>
                    <span className={`status-badge status-${loan.status.toLowerCase()}`}>
                      {loan.status}
                    </span>
                  </td>
                  <td>{new Date(loan.closeDate).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {portfolioData.loans.length === 0 && (
            <div className="empty-state">No closed loans found.</div>
          )}
        </div>
      )}

      {activeTab === 'mum' && (
        <div className="mum-section">
          <div className="mum-header">
            <p className="mum-subtitle">
              {mumClients.length} closed clients • {mumClients.filter(c => c.refinance_opportunity).length} refinance opportunities
            </p>
            <div className="filter-bar">
              <button
                className={filterView === 'all' ? 'active' : ''}
                onClick={() => setFilterView('all')}
              >
                All Clients ({mumClients.length})
              </button>
              <button
                className={filterView === 'opportunities' ? 'active' : ''}
                onClick={() => setFilterView('opportunities')}
              >
                Refinance Opportunities ({mumClients.filter(c => c.refinance_opportunity).length})
              </button>
            </div>
          </div>

          <div className="clients-table">
            <table>
              <thead>
                <tr>
                  <th>Client Name</th>
                  <th>Loan Number</th>
                  <th>Closed Date</th>
                  <th>Days Since Funding</th>
                  <th>Original Rate</th>
                  <th>Current Rate</th>
                  <th>Loan Balance</th>
                  <th>Opportunity</th>
                  <th>Est. Savings</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredMumClients.map((client) => (
                  <tr key={client.id}>
                    <td>
                      <strong>{client.name}</strong>
                    </td>
                    <td>{client.loan_number}</td>
                    <td>
                      {new Date(client.original_close_date).toLocaleDateString()}
                    </td>
                    <td>
                      <span className={`days-badge ${getDaysSinceFundingColor(client.days_since_funding)}`}>
                        {client.days_since_funding} days
                      </span>
                    </td>
                    <td>{client.original_rate ? `${client.original_rate}%` : 'N/A'}</td>
                    <td>{client.current_rate ? `${client.current_rate}%` : 'N/A'}</td>
                    <td>${client.loan_balance?.toLocaleString() || 0}</td>
                    <td>
                      {client.refinance_opportunity ? (
                        <span className="opportunity-yes">Yes</span>
                      ) : (
                        <span className="opportunity-no">No</span>
                      )}
                    </td>
                    <td>
                      {client.estimated_savings ? (
                        <span className="savings">${client.estimated_savings.toLocaleString()}</span>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td>
                      <div className="action-buttons">
                        <button className="btn-contact">Contact</button>
                        <button
                          className="btn-delete-small"
                          onClick={() => handleDeleteClient(client.id)}
                        >
                          ×
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {filteredMumClients.length === 0 && (
              <div className="empty-state">
                No clients found. Add your first MUM client to track post-closing opportunities.
              </div>
            )}
          </div>
        </div>
      )}

      {showAddModal && (
        <AddClientModal
          onClose={() => setShowAddModal(false)}
          onAdd={handleAddClient}
        />
      )}
    </div>
  );
}

function AddClientModal({ onClose, onAdd }) {
  const [formData, setFormData] = useState({
    name: '',
    loan_number: '',
    original_close_date: '',
    original_rate: '',
    loan_balance: '',
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onAdd({
      ...formData,
      original_rate: parseFloat(formData.original_rate),
      loan_balance: parseFloat(formData.loan_balance),
      original_close_date: new Date(formData.original_close_date).toISOString(),
    });
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <h3>Add MUM Client</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Client Name *</label>
            <input
              type="text"
              required
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Loan Number *</label>
            <input
              type="text"
              required
              value={formData.loan_number}
              onChange={(e) => setFormData({ ...formData, loan_number: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Original Close Date *</label>
            <input
              type="date"
              required
              value={formData.original_close_date}
              onChange={(e) => setFormData({ ...formData, original_close_date: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Original Interest Rate (%) *</label>
            <input
              type="number"
              step="0.001"
              required
              value={formData.original_rate}
              onChange={(e) => setFormData({ ...formData, original_rate: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Current Loan Balance ($) *</label>
            <input
              type="number"
              required
              value={formData.loan_balance}
              onChange={(e) => setFormData({ ...formData, loan_balance: e.target.value })}
            />
          </div>
          <div className="form-actions">
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Add Client</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default Portfolio;
