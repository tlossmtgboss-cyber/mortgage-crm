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
  const [activeBorrower, setActiveBorrower] = useState(0);

  // Borrowers array - each borrower has their own contact info
  const [borrowers, setBorrowers] = useState([
    {
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      credit_score: '',
      employment_status: '',
      annual_income: '',
      monthly_debts: '',
    }
  ]);

  // Shared property and loan data
  const [propertyData, setPropertyData] = useState({
    address: '',
    city: '',
    state: '',
    zip_code: '',
    property_type: '',
    property_value: '',
    down_payment: '',
    first_time_buyer: false,
  });

  const [loanData, setLoanData] = useState({
    loan_type: '',
    loan_number: '',
    preapproval_amount: '',
    source: '',
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      // Combine primary borrower data with property and loan data
      const primaryBorrower = borrowers[0];

      // Validate required fields
      const fullName = `${primaryBorrower.first_name || ''} ${primaryBorrower.last_name || ''}`.trim();
      if (!fullName) {
        alert('Please enter at least a first name or last name');
        return;
      }

      const rawData = {
        name: fullName,
        email: primaryBorrower.email,
        phone: primaryBorrower.phone,
        credit_score: primaryBorrower.credit_score,
        employment_status: primaryBorrower.employment_status,
        annual_income: primaryBorrower.annual_income,
        monthly_debts: primaryBorrower.monthly_debts,
        ...propertyData,
        ...loanData,
      };

      // Clean up data - convert empty strings to null for numeric fields
      const formData = Object.entries(rawData).reduce((acc, [key, value]) => {
        // Always include name and first_time_buyer
        if (key === 'name' || key === 'first_time_buyer') {
          acc[key] = value;
          return acc;
        }
        // Skip empty values for other fields
        if (value === '' || value === undefined || value === null) {
          return acc;
        }
        // Convert numeric strings to numbers for numeric fields
        if (['credit_score', 'annual_income', 'monthly_debts', 'property_value',
             'down_payment', 'preapproval_amount'].includes(key)) {
          const num = parseFloat(value);
          if (!isNaN(num)) {
            acc[key] = num;
          }
        } else {
          acc[key] = value;
        }
        return acc;
      }, {});

      console.log('Submitting lead data:', formData);

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
      console.error('Error response:', err.response?.data);
      const errorMsg = err.response?.data?.detail
        ? (typeof err.response.data.detail === 'string'
           ? err.response.data.detail
           : JSON.stringify(err.response.data.detail))
        : err.message;
      alert('Failed to save lead: ' + errorMsg);
    }
  };

  const handleEdit = (lead) => {
    setEditingLead(lead);

    // Parse name into first and last name
    const nameParts = (lead.name || '').split(' ');
    const firstName = nameParts[0] || '';
    const lastName = nameParts.slice(1).join(' ') || '';

    setBorrowers([{
      first_name: firstName,
      last_name: lastName,
      email: lead.email || '',
      phone: lead.phone || '',
      credit_score: lead.credit_score || '',
      employment_status: lead.employment_status || '',
      annual_income: lead.annual_income || '',
      monthly_debts: lead.monthly_debts || '',
    }]);

    setPropertyData({
      address: lead.address || '',
      city: lead.city || '',
      state: lead.state || '',
      zip_code: lead.zip_code || '',
      property_type: lead.property_type || '',
      property_value: lead.property_value || '',
      down_payment: lead.down_payment || '',
      first_time_buyer: lead.first_time_buyer || false,
    });

    setLoanData({
      loan_type: lead.loan_type || '',
      loan_number: lead.loan_number || '',
      preapproval_amount: lead.preapproval_amount || '',
      source: lead.source || '',
      notes: lead.notes || '',
    });

    setActiveBorrower(0);
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
    setBorrowers([{
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      credit_score: '',
      employment_status: '',
      annual_income: '',
      monthly_debts: '',
    }]);

    setPropertyData({
      address: '',
      city: '',
      state: '',
      zip_code: '',
      property_type: '',
      property_value: '',
      down_payment: '',
      first_time_buyer: false,
    });

    setLoanData({
      loan_type: '',
      loan_number: '',
      preapproval_amount: '',
      source: '',
      notes: '',
    });

    setActiveBorrower(0);
  };

  const handleNewLead = () => {
    setEditingLead(null);
    resetForm();
    setShowModal(true);
  };

  const addBorrower = () => {
    setBorrowers([...borrowers, {
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      credit_score: '',
      employment_status: '',
      annual_income: '',
      monthly_debts: '',
    }]);
    setActiveBorrower(borrowers.length);
  };

  const removeBorrower = (index) => {
    if (borrowers.length > 1 && window.confirm('Remove this borrower?')) {
      const newBorrowers = borrowers.filter((_, i) => i !== index);
      setBorrowers(newBorrowers);
      setActiveBorrower(Math.max(0, index - 1));
    }
  };

  const updateBorrower = (index, field, value) => {
    const newBorrowers = [...borrowers];
    newBorrowers[index] = { ...newBorrowers[index], [field]: value };
    setBorrowers(newBorrowers);
  };

  const getStatusColor = (status) => {
    const colors = {
      'New': 'blue',
      'Attempted Contact': 'purple',
      'Prospect': 'yellow',
      'Application': 'orange',
      'Completed': 'green',
      'Pre-Qualified': 'teal',
      'Pre-Approved': 'cyan',
      'Withdrawn': 'red',
      'Does Not Qualify': 'gray',
    };
    return colors[status] || 'gray';
  };

  if (loading) {
    return <div className="loading">Loading leads...</div>;
  }

  const currentBorrower = borrowers[activeBorrower] || borrowers[0];

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
          <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{editingLead ? 'Edit Lead' : 'New Lead'}</h2>
              <button className="close-btn" onClick={() => setShowModal(false)}>
                ×
              </button>
            </div>

            <form onSubmit={handleSubmit}>
              {/* Borrower Tabs */}
              <div className="borrower-tabs">
                <div className="tabs-row">
                  {borrowers.map((borrower, index) => (
                    <div
                      key={index}
                      className={`borrower-tab ${activeBorrower === index ? 'active' : ''}`}
                      onClick={() => setActiveBorrower(index)}
                    >
                      <span>Borrower {index + 1}</span>
                      {index > 0 && (
                        <button
                          type="button"
                          className="remove-borrower-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            removeBorrower(index);
                          }}
                          title="Remove borrower"
                        >
                          ×
                        </button>
                      )}
                    </div>
                  ))}
                  <button
                    type="button"
                    className="add-borrower-btn"
                    onClick={addBorrower}
                    title="Add another borrower"
                  >
                    +
                  </button>
                </div>
              </div>

              {/* Borrower Information */}
              <div className="form-section-title">Borrower {activeBorrower + 1} Information</div>

              <div className="form-row">
                <div className="form-group">
                  <label>First Name *</label>
                  <input
                    type="text"
                    value={currentBorrower.first_name}
                    onChange={(e) => updateBorrower(activeBorrower, 'first_name', e.target.value)}
                    required={activeBorrower === 0}
                  />
                </div>

                <div className="form-group">
                  <label>Last Name *</label>
                  <input
                    type="text"
                    value={currentBorrower.last_name}
                    onChange={(e) => updateBorrower(activeBorrower, 'last_name', e.target.value)}
                    required={activeBorrower === 0}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    value={currentBorrower.email}
                    onChange={(e) => updateBorrower(activeBorrower, 'email', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label>Phone</label>
                  <input
                    type="tel"
                    value={currentBorrower.phone}
                    onChange={(e) => updateBorrower(activeBorrower, 'phone', e.target.value)}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Credit Score</label>
                  <input
                    type="number"
                    value={currentBorrower.credit_score}
                    onChange={(e) => updateBorrower(activeBorrower, 'credit_score', e.target.value)}
                    min="300"
                    max="850"
                  />
                </div>

                <div className="form-group">
                  <label>Employment Status</label>
                  <select
                    value={currentBorrower.employment_status}
                    onChange={(e) => updateBorrower(activeBorrower, 'employment_status', e.target.value)}
                  >
                    <option value="">Select...</option>
                    <option value="Full-Time">Full-Time</option>
                    <option value="Part-Time">Part-Time</option>
                    <option value="Self-Employed">Self-Employed</option>
                    <option value="Retired">Retired</option>
                    <option value="Unemployed">Unemployed</option>
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Annual Income</label>
                  <input
                    type="number"
                    value={currentBorrower.annual_income}
                    onChange={(e) => updateBorrower(activeBorrower, 'annual_income', e.target.value)}
                    placeholder="$"
                  />
                </div>

                <div className="form-group">
                  <label>Monthly Debts</label>
                  <input
                    type="number"
                    value={currentBorrower.monthly_debts}
                    onChange={(e) => updateBorrower(activeBorrower, 'monthly_debts', e.target.value)}
                    placeholder="$"
                  />
                </div>
              </div>

              {/* Property Information (shared across all borrowers) */}
              <div className="form-section-title">Property Information</div>

              <div className="form-group">
                <label>Property Address</label>
                <input
                  type="text"
                  value={propertyData.address}
                  onChange={(e) => setPropertyData({ ...propertyData, address: e.target.value })}
                  placeholder="Street address"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>City</label>
                  <input
                    type="text"
                    value={propertyData.city}
                    onChange={(e) => setPropertyData({ ...propertyData, city: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>State</label>
                  <input
                    type="text"
                    value={propertyData.state}
                    onChange={(e) => setPropertyData({ ...propertyData, state: e.target.value })}
                    maxLength="2"
                    placeholder="CA"
                  />
                </div>

                <div className="form-group">
                  <label>ZIP Code</label>
                  <input
                    type="text"
                    value={propertyData.zip_code}
                    onChange={(e) => setPropertyData({ ...propertyData, zip_code: e.target.value })}
                    maxLength="10"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Property Type</label>
                  <select
                    value={propertyData.property_type}
                    onChange={(e) => setPropertyData({ ...propertyData, property_type: e.target.value })}
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
                    value={propertyData.property_value}
                    onChange={(e) => setPropertyData({ ...propertyData, property_value: e.target.value })}
                    placeholder="$"
                  />
                </div>

                <div className="form-group">
                  <label>Down Payment</label>
                  <input
                    type="number"
                    value={propertyData.down_payment}
                    onChange={(e) => setPropertyData({ ...propertyData, down_payment: e.target.value })}
                    placeholder="$"
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={propertyData.first_time_buyer}
                    onChange={(e) => setPropertyData({ ...propertyData, first_time_buyer: e.target.checked })}
                  />
                  First-Time Home Buyer
                </label>
              </div>

              {/* Loan Details (shared) */}
              <div className="form-section-title">Loan Details</div>

              <div className="form-row">
                <div className="form-group">
                  <label>Loan Type</label>
                  <select
                    value={loanData.loan_type}
                    onChange={(e) => setLoanData({ ...loanData, loan_type: e.target.value })}
                  >
                    <option value="">Select...</option>
                    <option value="Purchase">Purchase</option>
                    <option value="Refinance">Refinance</option>
                    <option value="Cash-Out Refi">Cash-Out Refi</option>
                    <option value="HELOC">HELOC</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Loan Number</label>
                  <input
                    type="text"
                    value={loanData.loan_number}
                    onChange={(e) => setLoanData({ ...loanData, loan_number: e.target.value })}
                    placeholder="Optional loan number"
                  />
                </div>

                <div className="form-group">
                  <label>Preapproval Amount</label>
                  <input
                    type="number"
                    value={loanData.preapproval_amount}
                    onChange={(e) => setLoanData({ ...loanData, preapproval_amount: e.target.value })}
                    placeholder="$"
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Source</label>
                <input
                  type="text"
                  value={loanData.source}
                  onChange={(e) => setLoanData({ ...loanData, source: e.target.value })}
                  placeholder="Website, Referral, etc."
                />
              </div>

              <div className="form-group">
                <label>Notes</label>
                <textarea
                  rows="3"
                  value={loanData.notes}
                  onChange={(e) => setLoanData({ ...loanData, notes: e.target.value })}
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

export default Leads;
