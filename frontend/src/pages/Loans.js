import React, { useState, useEffect } from 'react';
import { loansAPI } from '../services/api';
import './Loans.css';

function Loans() {
  const [loans, setLoans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState({
    loan_number: '',
    borrower_name: '',
    amount: '',
    program: '',
    rate: '',
    closing_date: '',
  });

  useEffect(() => {
    loadLoans();
  }, []);

  const loadLoans = async () => {
    try {
      const data = await loansAPI.getAll();
      setLoans(data);
    } catch (err) {
      console.error('Failed to load loans:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await loansAPI.create(formData);
      setShowModal(false);
      resetForm();
      loadLoans();
    } catch (err) {
      console.error('Failed to create loan:', err);
      alert('Failed to create loan');
    }
  };

  const handleDelete = async (id) => {
    if (window.confirm('Are you sure you want to delete this loan?')) {
      try {
        await loansAPI.delete(id);
        loadLoans();
      } catch (err) {
        alert('Failed to delete loan');
      }
    }
  };

  const resetForm = () => {
    setFormData({
      loan_number: '',
      borrower_name: '',
      amount: '',
      program: '',
      rate: '',
      closing_date: '',
    });
  };

  if (loading) return <div className="loading">Loading loans...</div>;

  return (
    <div className="loans-page">
      <div className="page-header">
        <div>
          <h1>Loan Pipeline</h1>
          <p>{loans.length} active loans</p>
        </div>
        <button className="btn-primary" onClick={() => setShowModal(true)}>
          + New Loan
        </button>
      </div>

      <div className="loans-grid">
        {loans.map((loan) => (
          <div key={loan.id} className="loan-card">
            <div className="loan-header">
              <div>
                <h3>{loan.borrower_name}</h3>
                <span className="loan-number">{loan.loan_number}</span>
              </div>
              <span className={`status-badge status-${loan.sla_status}`}>
                {loan.stage}
              </span>
            </div>

            <div className="loan-details">
              <div className="detail-row">
                <span>Amount:</span>
                <strong>${loan.amount.toLocaleString()}</strong>
              </div>
              {loan.program && (
                <div className="detail-row">
                  <span>Program:</span>
                  <span>{loan.program}</span>
                </div>
              )}
              {loan.rate && (
                <div className="detail-row">
                  <span>Rate:</span>
                  <span>{loan.rate}%</span>
                </div>
              )}
              <div className="detail-row">
                <span>Days in Stage:</span>
                <span>{loan.days_in_stage}</span>
              </div>
              {loan.closing_date && (
                <div className="detail-row">
                  <span>Closing:</span>
                  <span>{new Date(loan.closing_date).toLocaleDateString()}</span>
                </div>
              )}
            </div>

            <div className="loan-actions">
              <button className="btn-delete" onClick={() => handleDelete(loan.id)}>
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {loans.length === 0 && (
        <div className="empty-state">
          <h3>No loans yet</h3>
          <p>Start your pipeline by adding a loan</p>
        </div>
      )}

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>New Loan</h2>
              <button className="close-btn" onClick={() => setShowModal(false)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>Loan Number *</label>
                <input
                  type="text"
                  value={formData.loan_number}
                  onChange={(e) => setFormData({ ...formData, loan_number: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label>Borrower Name *</label>
                <input
                  type="text"
                  value={formData.borrower_name}
                  onChange={(e) => setFormData({ ...formData, borrower_name: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label>Loan Amount *</label>
                <input
                  type="number"
                  value={formData.amount}
                  onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                  required
                />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Program</label>
                  <select
                    value={formData.program}
                    onChange={(e) => setFormData({ ...formData, program: e.target.value })}
                  >
                    <option value="">Select...</option>
                    <option value="Conventional">Conventional</option>
                    <option value="FHA">FHA</option>
                    <option value="VA">VA</option>
                    <option value="USDA">USDA</option>
                    <option value="Jumbo">Jumbo</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Interest Rate %</label>
                  <input
                    type="number"
                    step="0.001"
                    value={formData.rate}
                    onChange={(e) => setFormData({ ...formData, rate: e.target.value })}
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Closing Date</label>
                <input
                  type="date"
                  value={formData.closing_date}
                  onChange={(e) => setFormData({ ...formData, closing_date: e.target.value })}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">Create Loan</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default Loans;
