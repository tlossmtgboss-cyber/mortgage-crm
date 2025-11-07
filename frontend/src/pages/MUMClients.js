import { useState, useEffect } from 'react';
import { mumAPI } from '../services/api';
import './MUMClients.css';

function MUMClients() {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [filterView, setFilterView] = useState('all');

  useEffect(() => {
    loadClients();
  }, []);

  const loadClients = async () => {
    try {
      setLoading(true);
      const data = await mumAPI.getAll();
      setClients(data);
    } catch (error) {
      console.error('Failed to load MUM clients:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddClient = async (clientData) => {
    try {
      await mumAPI.create(clientData);
      loadClients();
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
      loadClients();
    } catch (error) {
      console.error('Failed to delete client:', error);
    }
  };

  const filteredClients = filterView === 'all'
    ? clients
    : filterView === 'opportunities'
    ? clients.filter(c => c.refinance_opportunity)
    : clients;

  const getDaysSinceFundingColor = (days) => {
    if (days < 180) return 'recent';
    if (days < 365) return 'medium';
    return 'old';
  };

  return (
    <div className="mum-clients-page">
      <div className="page-header">
        <div>
          <h1>Move-Up Market (MUM) Clients</h1>
          <p>{clients.length} closed clients • {clients.filter(c => c.refinance_opportunity).length} refinance opportunities</p>
        </div>
        <button className="btn-add" onClick={() => setShowAddModal(true)}>
          + Add Client
        </button>
      </div>

      <div className="filter-bar">
        <button
          className={filterView === 'all' ? 'active' : ''}
          onClick={() => setFilterView('all')}
        >
          All Clients ({clients.length})
        </button>
        <button
          className={filterView === 'opportunities' ? 'active' : ''}
          onClick={() => setFilterView('opportunities')}
        >
          Refinance Opportunities ({clients.filter(c => c.refinance_opportunity).length})
        </button>
      </div>

      {loading ? (
        <div className="loading">Loading clients...</div>
      ) : (
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
              {filteredClients.map((client) => (
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

          {filteredClients.length === 0 && (
            <div className="empty-state">
              No clients found. Add your first MUM client to track post-closing opportunities.
            </div>
          )}
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

export default MUMClients;
