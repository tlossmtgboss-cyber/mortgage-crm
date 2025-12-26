import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { leadsAPI } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import SMSModal from '../components/SMSModal';
import CalendarSidebar from '../components/CalendarSidebar';
import './Leads.css';

function Leads() {
  const navigate = useNavigate();
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingLead, setEditingLead] = useState(null);
  const [activeFilter, setActiveFilter] = useState('New');
  const [activeBorrower, setActiveBorrower] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [viewedLeads, setViewedLeads] = useState(() => {
    // Load viewed leads from localStorage
    const stored = localStorage.getItem('viewedLeads');
    return stored ? new Set(JSON.parse(stored)) : new Set();
  });
  const [showSMSModal, setShowSMSModal] = useState(false);
  const [selectedLeadForSMS, setSelectedLeadForSMS] = useState(null);
  const [statusDropdown, setStatusDropdown] = useState({ show: false, leadId: null, position: { top: 0, left: 0 } });
  const [duplicateMap, setDuplicateMap] = useState({});  // Map of lead_id -> duplicate info
  const [duplicateTasksCreated, setDuplicateTasksCreated] = useState(false);
  const [selectedLeads, setSelectedLeads] = useState(new Set());
  const [isMasterUser, setIsMasterUser] = useState(false);

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
    stage: 'New',
    notes: '',
  });

  const filters = [
    'New',
    'Attempted Contact',
    'Prospect',
    'Application',
    'Pre-Qualified',
    'Pre-Approved',
    'Nurture',
    'Withdrawn',
    'Does Not Qualify',
  ];

  const statusOptions = [
    'New',
    'Attempted Contact',
    'Prospect',
    'Application',
    'Pre-Qualified',
    'Pre-Approved',
    'Long-Term Nurture',
    'Withdrawn',
    'Does Not Qualify',
  ];

  useEffect(() => {
    loadLeads();
    // Check if master user (user ID 1)
    const checkMasterUser = () => {
      const token = localStorage.getItem('token');
      if (token) {
        try {
          const payload = JSON.parse(atob(token.split('.')[1]));
          // Check if user ID is 1 or email is admin
          setIsMasterUser(payload.user_id === 1 || payload.sub === 'admin@perenniaai.com');
        } catch (e) {
          console.error('Error parsing token:', e);
        }
      }
    };
    checkMasterUser();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadLeads = async () => {
    try {
      // OPTIMIZED: Check cache first (cache for 30 seconds)
      const cacheKey = 'leads_data';
      const cacheTimeKey = 'leads_data_time';
      const cachedData = localStorage.getItem(cacheKey);
      const cachedTime = localStorage.getItem(cacheTimeKey);
      const now = Date.now();

      if (cachedData && cachedTime && (now - parseInt(cachedTime)) < 30000) {
        const data = JSON.parse(cachedData);
        setLeads(data);
        detectDuplicates(data);
        setLoading(false);
        return;
      }

      const data = await leadsAPI.getAll();
      // Use API data if available
      if (Array.isArray(data)) {
        setLeads(data);
        detectDuplicates(data);
        // Cache the response
        localStorage.setItem(cacheKey, JSON.stringify(data));
        localStorage.setItem(cacheTimeKey, now.toString());
      } else {
        setLeads([]);
      }
    } catch (err) {
      console.error('Failed to load leads:', err);
      setLeads([]);
    } finally {
      setLoading(false);
    }
  };

  // Detect duplicates based on email
  const detectDuplicates = (leadsList) => {
    const emailGroups = {};
    leadsList.forEach(lead => {
      if (lead.email) {
        const email = lead.email.toLowerCase();
        if (!emailGroups[email]) {
          emailGroups[email] = [];
        }
        emailGroups[email].push({
          id: lead.id,
          name: lead.name || `${lead.first_name || ''} ${lead.last_name || ''}`.trim(),
          stage: lead.stage,
        });
      }
    });

    // Only keep entries with duplicates
    const duplicates = {};
    Object.entries(emailGroups).forEach(([email, leads]) => {
      if (leads.length > 1) {
        leads.forEach(lead => {
          duplicates[lead.id] = {
            email,
            count: leads.length,
            otherLeads: leads.filter(l => l.id !== lead.id),
          };
        });
      }
    });
    setDuplicateMap(duplicates);
  };

  // Check if lead has duplicates
  const hasDuplicate = (leadId) => duplicateMap[leadId] !== undefined;
  const getDuplicateInfo = (leadId) => duplicateMap[leadId];
  const getTotalDuplicates = () => {
    const uniqueEmails = new Set(Object.values(duplicateMap).map(d => d.email));
    return uniqueEmails.size;
  };

  // Create tasks for duplicates
  const handleCreateDuplicateTasks = async () => {
    try {
      const token = localStorage.getItem('token');
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction
        ? 'https://api.perenniaai.com'
        : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      const response = await fetch(`${API_BASE}/api/v1/duplicates/create-tasks`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const data = await response.json();
        setDuplicateTasksCreated(true);
        alert(`Created ${data.tasks_created} tasks to review duplicate records.`);
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail || 'Failed to create tasks'}`);
      }
    } catch (err) {
      console.error('Error creating duplicate tasks:', err);
      alert('Failed to create duplicate tasks');
    }
  };

  // Ensure leads is always an array before filtering
  const safeLeads = Array.isArray(leads) ? leads : [];

  // Filter by stage
  let filteredLeads = activeFilter === 'Nurture'
    ? safeLeads.filter(lead => lead.stage === 'Nurture' || lead.stage === 'Long-Term Nurture')
    : safeLeads.filter(lead => lead.stage === activeFilter);

  // Filter by search query
  if (searchQuery.trim()) {
    const query = searchQuery.toLowerCase();
    filteredLeads = filteredLeads.filter(lead =>
      lead.name?.toLowerCase().includes(query) ||
      lead.email?.toLowerCase().includes(query) ||
      lead.phone?.toLowerCase().includes(query) ||
      lead.source?.toLowerCase().includes(query)
    );
  }

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
        // Always include name, first_time_buyer, and stage
        if (key === 'name' || key === 'first_time_buyer' || key === 'stage') {
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
      // Clear cache to ensure new lead appears immediately
      localStorage.removeItem('leads_data');
      localStorage.removeItem('leads_data_time');
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
      stage: lead.stage || 'New',
      notes: lead.notes || '',
    });

    setActiveBorrower(0);
    setShowModal(true);
  };

  const handleDelete = async (id) => {
    // Find the lead name for the confirmation
    const lead = leads.find(l => l.id === id);
    const leadName = lead?.name || `Lead #${id}`;

    if (!window.confirm(`Are you sure you want to delete "${leadName}"? This action cannot be undone.`)) {
      return;
    }

    try {
      console.log('Deleting lead:', id);
      await leadsAPI.delete(id);
      console.log('Lead deleted successfully');
      // Clear cache and reload
      localStorage.removeItem('leads_data');
      localStorage.removeItem('leads_data_time');
      loadLeads();
    } catch (err) {
      console.error('Failed to delete lead:', err);
      alert('Failed to delete lead: ' + (err.response?.data?.detail || err.message));
    }
  };

  // Bulk selection handlers
  const handleSelectLead = (leadId, e) => {
    e.stopPropagation();
    const newSelected = new Set(selectedLeads);
    if (newSelected.has(leadId)) {
      newSelected.delete(leadId);
    } else {
      newSelected.add(leadId);
    }
    setSelectedLeads(newSelected);
  };

  const handleSelectAll = (e) => {
    e.stopPropagation();
    if (selectedLeads.size === filteredLeads.length) {
      // Deselect all
      setSelectedLeads(new Set());
    } else {
      // Select all visible leads
      setSelectedLeads(new Set(filteredLeads.map(lead => lead.id)));
    }
  };

  const handleBulkDelete = async () => {
    if (selectedLeads.size === 0) return;

    const count = selectedLeads.size;
    if (!window.confirm(`Are you sure you want to delete ${count} lead${count > 1 ? 's' : ''}? This action cannot be undone.`)) {
      return;
    }

    try {
      const leadIds = Array.from(selectedLeads);
      console.log('Bulk deleting leads:', leadIds);
      const result = await leadsAPI.bulkDelete(leadIds);
      console.log('Bulk delete result:', result);

      // Clear selection
      setSelectedLeads(new Set());

      // Clear cache and reload
      localStorage.removeItem('leads_data');
      localStorage.removeItem('leads_data_time');
      loadLeads();

      alert(result.message || `Successfully deleted ${result.deleted_count} leads`);
    } catch (err) {
      console.error('Failed to bulk delete leads:', err);
      const errorDetail = err.response?.data?.detail;
      const errorMessage = typeof errorDetail === 'string'
        ? errorDetail
        : (errorDetail?.message || err.message || 'Unknown error');
      alert('Failed to delete leads: ' + errorMessage);
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
      stage: 'New',
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
    if (borrowers.length > 1) {
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
      'Attempted Contact': 'teal',
      'Prospect': 'yellow',
      'Application': 'orange',
      'Pre-Qualified': 'teal',
      'Pre-Approved': 'cyan',
      'Nurture': 'purple',
      'Long-Term Nurture': 'purple',
      'Withdrawn': 'red',
      'Does Not Qualify': 'gray',
    };
    return colors[status] || 'gray';
  };

  const isNewLead = (createdAt) => {
    if (!createdAt) return false;
    const leadDate = new Date(createdAt);
    const now = new Date();
    const hoursDiff = (now - leadDate) / (1000 * 60 * 60);
    return hoursDiff <= 48; // Lead is "new" if created within last 48 hours
  };

  const isLeadUnviewed = (leadId) => {
    return !viewedLeads.has(String(leadId));
  };

  const handleLeadClick = (leadId) => {
    console.log('Lead clicked:', leadId);

    // Mark lead as viewed
    const newViewedLeads = new Set(viewedLeads);
    newViewedLeads.add(String(leadId));
    setViewedLeads(newViewedLeads);

    // Save to localStorage
    localStorage.setItem('viewedLeads', JSON.stringify([...newViewedLeads]));

    // Navigate to lead detail
    console.log('Navigating to:', `/leads/${leadId}`);
    navigate(`/leads/${leadId}`);
  };

  const handleStatusClick = (e, leadId) => {
    e.stopPropagation(); // Prevent row click
    const rect = e.target.getBoundingClientRect();
    setStatusDropdown({
      show: true,
      leadId,
      position: {
        top: rect.bottom + window.scrollY + 5,
        left: rect.left + window.scrollX,
      },
    });
  };

  const handleStatusChange = async (newStatus) => {
    const leadId = statusDropdown.leadId;
    setStatusDropdown({ show: false, leadId: null, position: { top: 0, left: 0 } });

    try {
      await leadsAPI.update(leadId, { stage: newStatus });
      // Update local state
      setLeads(leads.map(lead =>
        lead.id === leadId ? { ...lead, stage: newStatus } : lead
      ));
      // Clear cache
      localStorage.removeItem('leads_data');
      localStorage.removeItem('leads_data_time');
    } catch (err) {
      console.error('Failed to update status:', err);
      alert('Failed to update status');
    }
  };

  const closeStatusDropdown = () => {
    setStatusDropdown({ show: false, leadId: null, position: { top: 0, left: 0 } });
  };

  if (loading) {
    return <div className="loading">Loading leads...</div>;
  }

  const currentBorrower = borrowers[activeBorrower] || borrowers[0];

  return (
    <div className="leads-page-wrapper">
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

      <div className="search-bar-container">
        <input
          type="text"
          className="search-bar"
          placeholder="Search leads by name, email, phone, or source..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchQuery && (
          <button className="clear-search" onClick={() => setSearchQuery('')}>
            ×
          </button>
        )}
      </div>

      {/* Bulk Delete Bar - Only for master user */}
      {isMasterUser && selectedLeads.size > 0 && (
        <div className="bulk-actions-bar">
          <span className="selected-count">{selectedLeads.size} lead{selectedLeads.size > 1 ? 's' : ''} selected</span>
          <button className="btn-danger" onClick={handleBulkDelete}>
            🗑️ Delete Selected
          </button>
          <button className="btn-secondary" onClick={() => setSelectedLeads(new Set())}>
            Cancel
          </button>
        </div>
      )}

      {/* Duplicate Warning Banner */}
      {getTotalDuplicates() > 0 && (
        <div className="duplicate-warning-banner">
          <div className="duplicate-warning-content">
            <span className="duplicate-icon">⚠️</span>
            <span className="duplicate-text">
              <strong>{getTotalDuplicates()} potential duplicate{getTotalDuplicates() > 1 ? 's' : ''} detected</strong>
              {' '}- Leads with the same email address found. Review and merge to avoid confusion.
            </span>
          </div>
          {!duplicateTasksCreated && (
            <button className="create-tasks-btn" onClick={handleCreateDuplicateTasks}>
              Create Merge Tasks
            </button>
          )}
          {duplicateTasksCreated && (
            <span className="tasks-created-badge">✓ Tasks Created</span>
          )}
        </div>
      )}

      <div className="table-container">
        <table className="leads-table">
          <thead>
            <tr>
              {isMasterUser && (
                <th className="checkbox-column">
                  <input
                    type="checkbox"
                    checked={filteredLeads.length > 0 && selectedLeads.size === filteredLeads.length}
                    onChange={handleSelectAll}
                    title="Select All"
                  />
                </th>
              )}
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
              <tr
                key={lead.id}
                className={`${isNewLead(lead.created_at) && isLeadUnviewed(lead.id) ? 'new-lead-row' : ''} ${hasDuplicate(lead.id) ? 'has-duplicate' : ''} ${selectedLeads.has(lead.id) ? 'selected-row' : ''}`}
                onClick={() => handleLeadClick(lead.id)}
              >
                {isMasterUser && (
                  <td className="checkbox-column">
                    <input
                      type="checkbox"
                      checked={selectedLeads.has(lead.id)}
                      onChange={(e) => handleSelectLead(lead.id, e)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </td>
                )}
                <td className="lead-name">
                  <div className="borrower-info">
                    <span>{lead.name}</span>
                    {isNewLead(lead.created_at) && isLeadUnviewed(lead.id) && <span className="new-lead-badge">NEW</span>}
                    {hasDuplicate(lead.id) && (
                      <span
                        className="duplicate-badge"
                        title={`Duplicate: Same email as ${getDuplicateInfo(lead.id).otherLeads.map(l => l.name).join(', ')}`}
                      >
                        DUPLICATE
                      </span>
                    )}
                  </div>
                </td>
                <td><ClickableEmail email={lead.email} /></td>
                <td>
                  <ClickablePhone
                    phone={lead.phone}
                    showActions={true}
                    contactName={lead.name || `${lead.first_name || ''} ${lead.last_name || ''}`.trim()}
                    leadId={lead.id}
                    onSMSClick={() => {
                      setSelectedLeadForSMS(lead);
                      setShowSMSModal(true);
                    }}
                  />
                </td>
                <td>
                  <span
                    className={`status-badge status-${getStatusColor(lead.stage)} status-clickable`}
                    onClick={(e) => handleStatusClick(e, lead.id)}
                    title="Click to change status"
                  >
                    {lead.stage}
                  </span>
                </td>
                <td>{lead.updated_at ? new Date(lead.updated_at).toLocaleDateString() : 'N/A'}</td>
                <td>{lead.source || 'N/A'}</td>
                <td>
                  <div className="table-actions">
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

              <div className="form-row">
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
                  <label>Lead Status</label>
                  <select
                    value={loanData.stage}
                    onChange={(e) => setLoanData({ ...loanData, stage: e.target.value })}
                  >
                    <option value="New">New</option>
                    <option value="Attempted Contact">Attempted Contact</option>
                    <option value="Prospect">Prospect</option>
                    <option value="Application">Application</option>
                    <option value="Pre-Qualified">Pre-Qualified</option>
                    <option value="Pre-Approved">Pre-Approved</option>
                    <option value="Long-Term Nurture">Nurture</option>
                    <option value="Withdrawn">Withdrawn</option>
                    <option value="Does Not Qualify">Does Not Qualify</option>
                  </select>
                </div>
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

      {/* SMS Modal */}
      {selectedLeadForSMS && (
        <SMSModal
          isOpen={showSMSModal}
          onClose={() => {
            setShowSMSModal(false);
            setSelectedLeadForSMS(null);
          }}
          lead={selectedLeadForSMS}
        />
      )}

      {/* Status Dropdown Popup */}
      {statusDropdown.show && (
        <>
          <div className="status-dropdown-overlay" onClick={closeStatusDropdown} />
          <div
            className="status-dropdown-popup"
            style={{
              top: statusDropdown.position.top,
              left: statusDropdown.position.left,
            }}
          >
            <div className="status-dropdown-header">Change Status</div>
            <div className="status-dropdown-options">
              {statusOptions.map((status) => (
                <button
                  key={status}
                  className={`status-dropdown-option status-${getStatusColor(status)}`}
                  onClick={() => handleStatusChange(status)}
                >
                  {status}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
      </div>
      <CalendarSidebar />
    </div>
  );
}

export default Leads;
