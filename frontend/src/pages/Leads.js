import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { leadsAPI } from '../services/api';
import './Leads.css';

function Leads() {
  const navigate = useNavigate();
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingLead, setEditingLead] = useState(null);
  const [activeFilter, setActiveFilter] = useState('All');
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    phone: '',
    credit_score: '',
    preapproval_amount: '',
    loan_type: '',
    source: '',
    address: '',
    city: '',
    state: '',
    zip_code: '',
    property_type: '',
    property_value: '',
    down_payment: '',
    employment_status: '',
    annual_income: '',
    monthly_debts: '',
    first_time_buyer: false,
    notes: '',
  });

  const filters = [
    'All',
    'New',
    'Attempted Contact',
    'Prospect',
    'Application',
    'Completed',
    'Pre-Qualified',
    'Pre-Approved',
    'Withdrawn',
    'Does Not Qualify',
  ];

  useEffect(() => {
    loadLeads();
  }, []);

  const loadLeads = async () => {
    try {
      const data = await leadsAPI.getAll();
      setLeads(data);
    } catch (err) {
      console.error('Failed to load leads:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredLeads = activeFilter === 'All'
    ? leads
    : leads.filter(lead => lead.stage === activeFilter);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      if (editingLead) {
        await leadsAPI.update(editingLead.id, formData);
      } else {
        await leadsAPI.create(formData);
      }
      setShowModal(false);
      setEditingLead(null);
      resetForm();
      loadLeads();
    } catch (err) {
      console.error('Failed to save lead:', err);
      alert('Failed to save lead');
    }
  };

  const handleEdit = (lead) => {
    setEditingLead(lead);
    setFormData({
      name: lead.name || '',
      email: lead.email || '',
      phone: lead.phone || '',
      credit_score: lead.credit_score || '',
      preapproval_amount: lead.preapproval_amount || '',
      loan_type: lead.loan_type || '',
      source: lead.source || '',
      address: lead.address || '',
      city: lead.city || '',
      state: lead.state || '',
      zip_code: lead.zip_code || '',
      property_type: lead.property_type || '',
      property_value: lead.property_value || '',
      down_payment: lead.down_payment || '',
      employment_status: lead.employment_status || '',
      annual_income: lead.annual_income || '',
      monthly_debts: lead.monthly_debts || '',
      first_time_buyer: lead.first_time_buyer || false,
      notes: lead.notes || '',
    });
    setShowModal(true);
  };

  const handleDelete = async (id) => {
    if (window.confirm('Are you sure you want to delete this lead?')) {
      try {
        await leadsAPI.delete(id);
        loadLeads();
      } catch (err) {
        console.error('Failed to delete lead:', err);
        alert('Failed to delete lead');
      }
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      email: '',
      phone: '',
      credit_score: '',
      preapproval_amount: '',
      loan_type: '',
      source: '',
      address: '',
      city: '',
      state: '',
      zip_code: '',
      property_type: '',
      property_value: '',
      down_payment: '',
      employment_status: '',
      annual_income: '',
      monthly_debts: '',
      first_time_buyer: false,
      notes: '',
    });
  };

  const handleNewLead = () => {
    setEditingLead(null);
    resetForm();
    setShowModal(true);
  };

  if (loading) {
    return <div className="loading">Loading leads...</div>;
  }

  return (
    <div className="leads-page">
      <div className="page-header">
        <div>
          <h1>Leads</h1>
          <p>{leads.length} total leads</p>
        </div>
        <button className="btn-primary" onClick={handleNewLead}>
          + Add Lead
        </button>
      </div>

      <div className="filter-tabs">
        {filters.map((filter) => (
          <button
            key={filter}
            className={`filter-tab ${activeFilter === filter ? 'active' : ''}`}
            onClick={() => setActiveFilter(filter)}
          >
            {filter}
          </button>
        ))}
      </div>

      <div className="table-container">
        <table className="leads-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Status</th>
              <th>Last Contact</th>
              <th>Source</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredLeads.map((lead) => (
              <tr key={lead.id}>
                <td className="lead-name clickable" onClick={() => navigate(`/leads/${lead.id}`)}>
                  {lead.name}
                </td>
                <td>{lead.email || 'N/A'}</td>
                <td>{lead.phone || 'N/A'}</td>
                <td>
                  <span className={`status-badge status-${getStatusColor(lead.stage)}`}>
                    {lead.stage}
                  </span>
                </td>
                <td>{lead.updated_at ? new Date(lead.updated_at).toLocaleDateString() : 'N/A'}</td>
                <td>{lead.source || 'N/A'}</td>
                <td>
                  <div className="table-actions">
                    <button className="btn-icon" onClick={(e) => { e.stopPropagation(); handleEdit(lead); }} title="Edit">
                      ✏️
                    </button>
                    <button className="btn-icon" onClick={(e) => { e.stopPropagation(); handleDelete(lead.id); }} title="Delete">
                      🗑️
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filteredLeads.length === 0 && (
        <div className="empty-state">
          <h3>No leads found</h3>
          <p>Try adjusting your filters or add a new lead</p>
        </div>
      )}

      <div className="legacy-leads-grid" style={{ display: 'none' }}>
        {filteredLeads.map((lead) => (
          <div key={lead.id} className="lead-card">
            <div className="lead-header">
              <h3>{lead.name}</h3>
              <span className={`score-badge score-${getScoreLevel(lead.ai_score)}`}>
                {lead.ai_score}
              </span>
            </div>

            <div className="lead-info">
              <div className="info-row">
                <span className="label">Email:</span>
                <span>{lead.email || 'N/A'}</span>
              </div>
              <div className="info-row">
                <span className="label">Phone:</span>
                <span>{lead.phone || 'N/A'}</span>
              </div>
              <div className="info-row">
                <span className="label">Stage:</span>
                <span className="stage">{lead.stage}</span>
              </div>
              <div className="info-row">
                <span className="label">Source:</span>
                <span>{lead.source || 'N/A'}</span>
              </div>
              {lead.credit_score && (
                <div className="info-row">
                  <span className="label">Credit:</span>
                  <span>{lead.credit_score}</span>
                </div>
              )}
              {lead.preapproval_amount && (
                <div className="info-row">
                  <span className="label">Preapproval:</span>
                  <span>${lead.preapproval_amount.toLocaleString()}</span>
                </div>
              )}
            </div>

            {lead.next_action && (
              <div className="next-action">
                <strong>Next Action:</strong> {lead.next_action}
              </div>
            )}

            <div className="lead-actions">
              <button className="btn-edit" onClick={() => handleEdit(lead)}>
                Edit
              </button>
              <button className="btn-delete" onClick={() => handleDelete(lead.id)}>
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {leads.length === 0 && (
        <div className="empty-state">
          <h3>No leads yet</h3>
          <p>Get started by adding your first lead</p>
          <button className="btn-primary" onClick={handleNewLead}>
            + Add Your First Lead
          </button>
        </div>
      )}

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{editingLead ? 'Edit Lead' : 'New Lead'}</h2>
              <button className="close-btn" onClick={() => setShowModal(false)}>
                ×
              </button>
            </div>

            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>Name *</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Phone</label>
                  <input
                    type="tel"
                    value={formData.phone}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-section-title">Property Information</div>

              <div className="form-group">
                <label>Property Address</label>
                <input
                  type="text"
                  value={formData.address}
                  onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                  placeholder="Street address"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>City</label>
                  <input
                    type="text"
                    value={formData.city}
                    onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>State</label>
                  <input
                    type="text"
                    value={formData.state}
                    onChange={(e) => setFormData({ ...formData, state: e.target.value })}
                    maxLength="2"
                    placeholder="CA"
                  />
                </div>

                <div className="form-group">
                  <label>ZIP Code</label>
                  <input
                    type="text"
                    value={formData.zip_code}
                    onChange={(e) => setFormData({ ...formData, zip_code: e.target.value })}
                    maxLength="10"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Property Type</label>
                  <select
                    value={formData.property_type}
                    onChange={(e) => setFormData({ ...formData, property_type: e.target.value })}
                  >
                    <option value="">Select...</option>
                    <option value="Single Family">Single Family</option>
                    <option value="Condo">Condo</option>
                    <option value="Townhouse">Townhouse</option>
                    <option value="Multi-Family">Multi-Family</option>
                    <option value="Manufactured">Manufactured</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Property Value</label>
                  <input
                    type="number"
                    value={formData.property_value}
                    onChange={(e) => setFormData({ ...formData, property_value: e.target.value })}
                    placeholder="$"
                  />
                </div>

                <div className="form-group">
                  <label>Down Payment</label>
                  <input
                    type="number"
                    value={formData.down_payment}
                    onChange={(e) => setFormData({ ...formData, down_payment: e.target.value })}
                    placeholder="$"
                  />
                </div>
              </div>

              <div className="form-section-title">Financial Information</div>

              <div className="form-row">
                <div className="form-group">
                  <label>Credit Score</label>
                  <input
                    type="number"
                    value={formData.credit_score}
                    onChange={(e) => setFormData({ ...formData, credit_score: e.target.value })}
                    min="300"
                    max="850"
                  />
                </div>

                <div className="form-group">
                  <label>Annual Income</label>
                  <input
                    type="number"
                    value={formData.annual_income}
                    onChange={(e) => setFormData({ ...formData, annual_income: e.target.value })}
                    placeholder="$"
                  />
                </div>

                <div className="form-group">
                  <label>Monthly Debts</label>
                  <input
                    type="number"
                    value={formData.monthly_debts}
                    onChange={(e) => setFormData({ ...formData, monthly_debts: e.target.value })}
                    placeholder="$"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Employment Status</label>
                  <select
                    value={formData.employment_status}
                    onChange={(e) => setFormData({ ...formData, employment_status: e.target.value })}
                  >
                    <option value="">Select...</option>
                    <option value="Full-Time">Full-Time</option>
                    <option value="Part-Time">Part-Time</option>
                    <option value="Self-Employed">Self-Employed</option>
                    <option value="Retired">Retired</option>
                    <option value="Unemployed">Unemployed</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Preapproval Amount</label>
                  <input
                    type="number"
                    value={formData.preapproval_amount}
                    onChange={(e) =>
                      setFormData({ ...formData, preapproval_amount: e.target.value })
                    }
                    placeholder="$"
                  />
                </div>
              </div>

              <div className="form-section-title">Loan Details</div>

              <div className="form-row">
                <div className="form-group">
                  <label>Loan Type</label>
                  <select
                    value={formData.loan_type}
                    onChange={(e) => setFormData({ ...formData, loan_type: e.target.value })}
                  >
                    <option value="">Select...</option>
                    <option value="Purchase">Purchase</option>
                    <option value="Refinance">Refinance</option>
                    <option value="Cash-Out Refi">Cash-Out Refi</option>
                    <option value="HELOC">HELOC</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Source</label>
                  <input
                    type="text"
                    value={formData.source}
                    onChange={(e) => setFormData({ ...formData, source: e.target.value })}
                    placeholder="Website, Referral, etc."
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={formData.first_time_buyer}
                    onChange={(e) => setFormData({ ...formData, first_time_buyer: e.target.checked })}
                  />
                  First-Time Home Buyer
                </label>
              </div>

              <div className="form-group">
                <label>Notes</label>
                <textarea
                  rows="3"
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  placeholder="Additional notes..."
                />
              </div>

              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  {editingLead ? 'Update Lead' : 'Create Lead'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function getScoreLevel(score) {
  if (score >= 80) return 'high';
  if (score >= 60) return 'medium';
  return 'low';
}

function getStatusColor(status) {
  const statusColors = {
    'New': 'new',
    'Attempted Contact': 'attempted',
    'Prospect': 'prospect',
    'Application': 'application',
    'Completed': 'completed',
    'Pre-Qualified': 'qualified',
    'Pre-Approved': 'approved',
    'Withdrawn': 'withdrawn',
    'Does Not Qualify': 'disqualified',
  };
  return statusColors[status] || 'default';
}

export default Leads;
