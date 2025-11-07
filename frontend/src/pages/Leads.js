import React, { useState, useEffect } from 'react';
import { leadsAPI } from '../services/api';
import './Leads.css';

function Leads() {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingLead, setEditingLead] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    phone: '',
    credit_score: '',
    preapproval_amount: '',
    loan_type: '',
    source: '',
  });

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

      <div className="leads-grid">
        {leads.map((lead) => (
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
                  <label>Preapproval Amount</label>
                  <input
                    type="number"
                    value={formData.preapproval_amount}
                    onChange={(e) =>
                      setFormData({ ...formData, preapproval_amount: e.target.value })
                    }
                  />
                </div>
              </div>

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

export default Leads;
