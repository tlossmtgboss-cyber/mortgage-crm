import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { leadsAPI, activitiesAPI, aiAPI } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import './LeadDetail.css';

function LeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [lead, setLead] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [chatMessage, setChatMessage] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [formData, setFormData] = useState({});
  const [emails, setEmails] = useState([]);
  const [activeTab, setActiveTab] = useState('personal');
  const [noteText, setNoteText] = useState('');
  const [noteLoading, setNoteLoading] = useState(false);
  const [borrowers, setBorrowers] = useState([]);
  const [activeBorrower, setActiveBorrower] = useState(0);

  useEffect(() => {
    loadLeadData();
    loadEmails();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadLeadData = async () => {
    try {
      setLoading(true);
      const [leadData, activitiesData] = await Promise.all([
        leadsAPI.getById(id),
        activitiesAPI.getAll({ lead_id: id })
      ]);
      setLead(leadData);
      setFormData(leadData);
      setActivities(activitiesData || []);

      // Initialize borrowers array
      const primaryName = leadData.first_name && leadData.last_name
        ? `${leadData.first_name} ${leadData.last_name}`
        : leadData.name || 'Primary Borrower';

      const borrowersList = [
        {
          id: 0,
          name: primaryName,
          type: 'primary',
          data: leadData
        }
      ];

      // Add co-borrower if exists
      if (leadData.coborrower_name) {
        borrowersList.push({
          id: 1,
          name: leadData.coborrower_name,
          type: 'co-borrower',
          data: {
            name: leadData.coborrower_name,
            first_name: leadData.coborrower_name ? leadData.coborrower_name.split(' ')[0] : '',
            last_name: leadData.coborrower_name ? leadData.coborrower_name.split(' ').slice(1).join(' ') : '',
            // Co-borrower fields would be stored separately in a real implementation
          }
        });
      }

      setBorrowers(borrowersList);
    } catch (error) {
      console.error('Failed to load lead data:', error);
      alert('Failed to load lead details');
    } finally {
      setLoading(false);
    }
  };

  const loadEmails = async () => {
    try {
      const emailActivities = await activitiesAPI.getAll({
        lead_id: id,
        type: 'email'
      });
      setEmails(emailActivities || []);
    } catch (error) {
      console.error('Failed to load emails:', error);
    }
  };

  const handleSave = async () => {
    try {
      // Combine first_name and last_name into name for backend
      const dataToSave = {
        ...formData,
        name: formData.first_name && formData.last_name
          ? `${formData.first_name} ${formData.last_name}`
          : formData.name || ''
      };

      await leadsAPI.update(id, dataToSave);
      setLead(dataToSave);
      setEditing(false);
      alert('Lead updated successfully!');
    } catch (error) {
      console.error('Failed to update lead:', error);
      alert('Failed to update lead');
    }
  };

  const handleCancel = () => {
    setFormData(lead);
    setEditing(false);
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!chatMessage.trim()) return;

    try {
      setChatLoading(true);
      const response = await aiAPI.chat(chatMessage, { lead_id: id });

      await activitiesAPI.create({
        type: 'ai_chat',
        description: `User: ${chatMessage}\nAI: ${response.message}`,
        lead_id: id
      });

      setChatMessage('');
      loadLeadData();
    } catch (error) {
      console.error('Failed to send AI message:', error);
      alert('Failed to send message');
    } finally {
      setChatLoading(false);
    }
  };

  const handleAddNote = async (e) => {
    e.preventDefault();
    if (!noteText.trim()) return;

    try {
      setNoteLoading(true);
      const noteData = {
        type: 'Note',
        content: noteText,
        lead_id: parseInt(id)
      };
      console.log('Creating note with data:', noteData);

      const result = await activitiesAPI.create(noteData);
      console.log('Note created successfully:', result);

      setNoteText('');
      loadLeadData();
    } catch (error) {
      console.error('Failed to add note:', error);
      console.error('Error response:', error.response?.data);
      const errorMsg = error.response?.data?.detail || 'Failed to add note. Please check console for details.';
      alert(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
    } finally {
      setNoteLoading(false);
    }
  };

  const handleSwitchBorrower = (borrowerIndex) => {
    setActiveBorrower(borrowerIndex);
    const borrower = borrowers[borrowerIndex];
    if (borrower && borrower.data) {
      setFormData(borrower.data);
    }
  };

  const handleAddBorrower = async () => {
    const firstName = prompt('Enter first name:');
    if (!firstName || !firstName.trim()) return;

    const lastName = prompt('Enter last name:');
    if (!lastName || !lastName.trim()) return;

    const fullName = `${firstName.trim()} ${lastName.trim()}`;
    const newBorrower = {
      id: borrowers.length,
      name: fullName,
      type: borrowers.length === 1 ? 'co-borrower' : 'additional',
      data: {
        name: fullName,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        // Initialize with empty fields
      }
    };

    try {
      console.log('Adding borrower:', fullName);
      console.log('Current borrowers count:', borrowers.length);

      // Save the first additional borrower as co-borrower
      if (borrowers.length === 1) {
        console.log('Updating lead with co-borrower name:', fullName);
        await leadsAPI.update(id, {
          coborrower_name: fullName
        });
        console.log('Co-borrower saved to backend');

        // Reload lead data to sync with backend
        const leadData = await leadsAPI.getById(id);
        console.log('Reloaded lead data:', leadData);
        setLead(leadData);

        // Rebuild borrowers array with the new co-borrower
        const primaryName = leadData.first_name && leadData.last_name
          ? `${leadData.first_name} ${leadData.last_name}`
          : leadData.name || 'Primary Borrower';

        const updatedBorrowers = [
          {
            id: 0,
            name: primaryName,
            type: 'primary',
            data: leadData
          }
        ];

        if (leadData.coborrower_name) {
          const coborrowerParts = (leadData.coborrower_name || '').split(' ');
          updatedBorrowers.push({
            id: 1,
            name: leadData.coborrower_name,
            type: 'co-borrower',
            data: {
              name: leadData.coborrower_name,
              first_name: coborrowerParts[0] || '',
              last_name: coborrowerParts.slice(1).join(' ') || '',
            }
          });
        }

        setBorrowers(updatedBorrowers);
        const targetIndex = updatedBorrowers.length > 1 ? 1 : 0;
        setActiveBorrower(targetIndex);
        if (updatedBorrowers[targetIndex]) {
          setFormData(updatedBorrowers[targetIndex].data);
        }
      } else {
        console.log('Adding additional borrower to local state only');
        // For additional borrowers beyond the first co-borrower, store in local state only
        setBorrowers([...borrowers, newBorrower]);
        setActiveBorrower(borrowers.length);
        setFormData(newBorrower.data);
      }

      alert(`${fullName} has been added successfully!`);
    } catch (error) {
      console.error('Failed to add borrower:', error);
      console.error('Error response:', error.response?.data);
      const errorMsg = error.response?.data?.detail || error.message || 'Failed to add borrower. Please check console for details.';
      alert(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
    }
  };

  const handleAction = async (action) => {
    switch(action) {
      case 'sms':
        window.open(`sms:${lead.phone}`, '_blank');
        break;
      case 'email':
        window.open(`mailto:${lead.email}`, '_blank');
        break;
      case 'task':
        navigate('/tasks');
        break;
      case 'calendar':
        navigate('/calendar');
        break;
      default:
        break;
    }
  };

  if (loading) {
    return (
      <div className="lead-detail-page">
        <div className="loading">Loading lead details...</div>
      </div>
    );
  }

  if (!lead) {
    return (
      <div className="lead-detail-page">
        <div className="error">Lead not found</div>
      </div>
    );
  }

  return (
    <div className="lead-detail-page">
      {/* Header */}
      <div className="detail-header">
        <button className="btn-back" onClick={() => navigate('/leads')}>
          ← Back to Leads
        </button>
        <div className="header-actions">
          {editing ? (
            <>
              <button className="btn-save" onClick={handleSave}>Save</button>
              <button className="btn-cancel" onClick={handleCancel}>Cancel</button>
            </>
          ) : (
            <button className="btn-edit-header" onClick={() => setEditing(true)}>
              ✏️ Edit
            </button>
          )}
        </div>
      </div>

      {/* Loan Information Toolbar */}
      <div className="loan-toolbar">
        <div className="toolbar-header">
          <h3>Loan Details</h3>
        </div>
        <div className="loan-fields-grid">
          <div className="loan-field">
            <label>Loan Amount</label>
            {editing ? (
              <input
                type="number"
                value={formData.loan_amount || ''}
                onChange={(e) => setFormData({...formData, loan_amount: e.target.value})}
                placeholder="$"
              />
            ) : (
              <div className="value">
                {formData.loan_amount ? `$${parseFloat(formData.loan_amount).toLocaleString()}` : 'N/A'}
              </div>
            )}
          </div>

          <div className="loan-field">
            <label>Interest Rate</label>
            {editing ? (
              <input
                type="number"
                step="0.001"
                value={formData.interest_rate || ''}
                onChange={(e) => setFormData({...formData, interest_rate: e.target.value})}
                placeholder="%"
              />
            ) : (
              <div className="value">{formData.interest_rate ? `${formData.interest_rate}%` : 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Loan Term</label>
            {editing ? (
              <input
                type="number"
                value={formData.loan_term || ''}
                onChange={(e) => setFormData({...formData, loan_term: e.target.value})}
                placeholder="Years"
              />
            ) : (
              <div className="value">{formData.loan_term ? `${formData.loan_term} years` : 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Loan Type</label>
            {editing ? (
              <select
                value={formData.loan_type || ''}
                onChange={(e) => setFormData({...formData, loan_type: e.target.value})}
              >
                <option value="">Select...</option>
                <option value="Conventional">Conventional</option>
                <option value="FHA">FHA</option>
                <option value="VA">VA</option>
                <option value="USDA">USDA</option>
                <option value="Jumbo">Jumbo</option>
                <option value="HELOC">HELOC</option>
              </select>
            ) : (
              <div className="value">{formData.loan_type || 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Lock Date</label>
            {editing ? (
              <input
                type="date"
                value={formData.lock_date || ''}
                onChange={(e) => setFormData({...formData, lock_date: e.target.value})}
              />
            ) : (
              <div className="value">
                {formData.lock_date ? new Date(formData.lock_date).toLocaleDateString() : 'N/A'}
              </div>
            )}
          </div>

          <div className="loan-field">
            <label>Lock Expiration</label>
            {editing ? (
              <input
                type="date"
                value={formData.lock_expiration || ''}
                onChange={(e) => setFormData({...formData, lock_expiration: e.target.value})}
              />
            ) : (
              <div className="value">
                {formData.lock_expiration ? new Date(formData.lock_expiration).toLocaleDateString() : 'N/A'}
              </div>
            )}
          </div>

          <div className="loan-field">
            <label>APR</label>
            {editing ? (
              <input
                type="number"
                step="0.001"
                value={formData.apr || ''}
                onChange={(e) => setFormData({...formData, apr: e.target.value})}
                placeholder="%"
              />
            ) : (
              <div className="value">{formData.apr ? `${formData.apr}%` : 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Points</label>
            {editing ? (
              <input
                type="number"
                step="0.125"
                value={formData.points || ''}
                onChange={(e) => setFormData({...formData, points: e.target.value})}
              />
            ) : (
              <div className="value">{formData.points || 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Lender</label>
            {editing ? (
              <input
                type="text"
                value={formData.lender || ''}
                onChange={(e) => setFormData({...formData, lender: e.target.value})}
              />
            ) : (
              <div className="value">{formData.lender || 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Loan Officer</label>
            {editing ? (
              <input
                type="text"
                value={formData.loan_officer || ''}
                onChange={(e) => setFormData({...formData, loan_officer: e.target.value})}
              />
            ) : (
              <div className="value">{formData.loan_officer || 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Processor</label>
            {editing ? (
              <input
                type="text"
                value={formData.processor || ''}
                onChange={(e) => setFormData({...formData, processor: e.target.value})}
              />
            ) : (
              <div className="value">{formData.processor || 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Underwriter</label>
            {editing ? (
              <input
                type="text"
                value={formData.underwriter || ''}
                onChange={(e) => setFormData({...formData, underwriter: e.target.value})}
              />
            ) : (
              <div className="value">{formData.underwriter || 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Closing Date</label>
            {editing ? (
              <input
                type="date"
                value={formData.closing_date || ''}
                onChange={(e) => setFormData({...formData, closing_date: e.target.value})}
              />
            ) : (
              <div className="value">
                {formData.closing_date ? new Date(formData.closing_date).toLocaleDateString() : 'N/A'}
              </div>
            )}
          </div>

          <div className="loan-field">
            <label>Appraisal Value</label>
            {editing ? (
              <input
                type="number"
                value={formData.appraisal_value || ''}
                onChange={(e) => setFormData({...formData, appraisal_value: e.target.value})}
                placeholder="$"
              />
            ) : (
              <div className="value">
                {formData.appraisal_value ? `$${parseFloat(formData.appraisal_value).toLocaleString()}` : 'N/A'}
              </div>
            )}
          </div>

          <div className="loan-field">
            <label>LTV %</label>
            {editing ? (
              <input
                type="number"
                step="0.01"
                value={formData.ltv || ''}
                onChange={(e) => setFormData({...formData, ltv: e.target.value})}
                placeholder="%"
              />
            ) : (
              <div className="value">{formData.ltv ? `${formData.ltv}%` : 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>DTI %</label>
            {editing ? (
              <input
                type="number"
                step="0.01"
                value={formData.dti || ''}
                onChange={(e) => setFormData({...formData, dti: e.target.value})}
                placeholder="%"
              />
            ) : (
              <div className="value">{formData.dti ? `${formData.dti}%` : 'N/A'}</div>
            )}
          </div>
        </div>
      </div>

      {/* Borrower Selector */}
      <div className="borrower-selector">
        {borrowers.map((borrower, index) => (
          <button
            key={borrower.id}
            className={`borrower-btn ${activeBorrower === index ? 'active' : ''}`}
            onClick={() => handleSwitchBorrower(index)}
          >
            {borrower.name}
            {borrower.type === 'primary' && <span className="borrower-badge">Primary</span>}
          </button>
        ))}
        <button className="borrower-add-btn" onClick={handleAddBorrower} title="Add Borrower">
          + Add Person
        </button>
      </div>

      {/* Tab Navigation */}
      <div className="profile-tabs">
        <button
          className={`tab-btn ${activeTab === 'personal' ? 'active' : ''}`}
          onClick={() => setActiveTab('personal')}
        >
          Personal
        </button>
        <button
          className={`tab-btn ${activeTab === 'employment' ? 'active' : ''}`}
          onClick={() => setActiveTab('employment')}
        >
          Employment
        </button>
        <button
          className={`tab-btn ${activeTab === 'loan' ? 'active' : ''}`}
          onClick={() => setActiveTab('loan')}
        >
          Loan
        </button>
        <button
          className={`tab-btn ${activeTab === 'conversation' ? 'active' : ''}`}
          onClick={() => setActiveTab('conversation')}
        >
          Conversation Log
        </button>
        <button
          className={`tab-btn ${activeTab === 'circle' ? 'active' : ''}`}
          onClick={() => setActiveTab('circle')}
        >
          Circle
        </button>
        <button
          className={`tab-btn ${activeTab === 'documents' ? 'active' : ''}`}
          onClick={() => setActiveTab('documents')}
        >
          Documents
        </button>
      </div>

      <div className="detail-content">
        {/* Left Column - Lead Information */}
        <div className="left-column">
          {/* Personal Information Tab */}
          {activeTab === 'personal' && (
          <div className="info-section">
            <h2>Personal Information</h2>
            <div className="info-grid compact">
              <div className="info-field">
                <label>First Name</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.first_name || ''}
                    onChange={(e) => setFormData({...formData, first_name: e.target.value})}
                  />
                ) : (
                  <div className="value">{formData.first_name || (formData.name ? formData.name.split(' ')[0] : 'N/A')}</div>
                )}
              </div>
              <div className="info-field">
                <label>Last Name</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.last_name || ''}
                    onChange={(e) => setFormData({...formData, last_name: e.target.value})}
                  />
                ) : (
                  <div className="value">{formData.last_name || (formData.name ? formData.name.split(' ').slice(1).join(' ') : 'N/A')}</div>
                )}
              </div>
              <div className="info-field">
                <label>Email</label>
                {editing ? (
                  <input
                    type="email"
                    value={formData.email || ''}
                    onChange={(e) => setFormData({...formData, email: e.target.value})}
                  />
                ) : (
                  <div className="value">
                    <ClickableEmail email={formData.email} />
                  </div>
                )}
              </div>
              <div className="info-field">
                <label>Phone</label>
                {editing ? (
                  <input
                    type="tel"
                    value={formData.phone || ''}
                    onChange={(e) => setFormData({...formData, phone: e.target.value})}
                  />
                ) : (
                  <div className="value">
                    <ClickablePhone phone={formData.phone} />
                  </div>
                )}
              </div>
              <div className="info-field">
                <label>Loan Number</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.loan_number || ''}
                    onChange={(e) => setFormData({...formData, loan_number: e.target.value})}
                  />
                ) : (
                  <div className="value">{formData.loan_number || 'N/A'}</div>
                )}
              </div>
            </div>
          </div>
          )}

          {/* Employment Tab */}
          {activeTab === 'employment' && (
          <div className="info-section">
            <h2>Employment Information</h2>
            <div className="info-grid compact">
              <div className="info-field">
                <label>Employment Status</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.employment_status || ''}
                    onChange={(e) => setFormData({...formData, employment_status: e.target.value})}
                  />
                ) : (
                  <div className="value">{formData.employment_status || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>Employer Name</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.employer_name || ''}
                    onChange={(e) => setFormData({...formData, employer_name: e.target.value})}
                  />
                ) : (
                  <div className="value">{formData.employer_name || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>Job Title</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.job_title || ''}
                    onChange={(e) => setFormData({...formData, job_title: e.target.value})}
                  />
                ) : (
                  <div className="value">{formData.job_title || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>Years at Job</label>
                {editing ? (
                  <input
                    type="number"
                    value={formData.years_at_job || ''}
                    onChange={(e) => setFormData({...formData, years_at_job: parseFloat(e.target.value)})}
                  />
                ) : (
                  <div className="value">{formData.years_at_job || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>Annual Income</label>
                {editing ? (
                  <input
                    type="number"
                    value={formData.annual_income || ''}
                    onChange={(e) => setFormData({...formData, annual_income: parseFloat(e.target.value)})}
                  />
                ) : (
                  <div className="value">
                    {lead.annual_income ? `$${lead.annual_income.toLocaleString()}` : 'N/A'}
                  </div>
                )}
              </div>
              <div className="info-field">
                <label>Monthly Income</label>
                {editing ? (
                  <input
                    type="number"
                    value={formData.monthly_income || ''}
                    onChange={(e) => setFormData({...formData, monthly_income: parseFloat(e.target.value)})}
                  />
                ) : (
                  <div className="value">
                    {lead.monthly_income ? `$${lead.monthly_income.toLocaleString()}` : 'N/A'}
                  </div>
                )}
              </div>
              <div className="info-field">
                <label>Other Income</label>
                {editing ? (
                  <input
                    type="number"
                    value={formData.other_income || ''}
                    onChange={(e) => setFormData({...formData, other_income: parseFloat(e.target.value)})}
                  />
                ) : (
                  <div className="value">
                    {lead.other_income ? `$${lead.other_income.toLocaleString()}` : 'N/A'}
                  </div>
                )}
              </div>
              <div className="info-field">
                <label>Income Source</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.income_source || ''}
                    onChange={(e) => setFormData({...formData, income_source: e.target.value})}
                  />
                ) : (
                  <div className="value">{formData.income_source || 'N/A'}</div>
                )}
              </div>
            </div>
          </div>
          )}

          {/* Loan Information Tab */}
          {activeTab === 'loan' && (
          <div className="info-section">
            <h2>Loan Information</h2>
            <div className="info-grid compact">
              <div className="info-field">
                <label>Property Address</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.address || ''}
                    onChange={(e) => setFormData({...formData, address: e.target.value})}
                  />
                ) : (
                  <div className="value">{formData.address || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>City</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.city || ''}
                    onChange={(e) => setFormData({...formData, city: e.target.value})}
                  />
                ) : (
                  <div className="value">{formData.city || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>State</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.state || ''}
                    onChange={(e) => setFormData({...formData, state: e.target.value})}
                  />
                ) : (
                  <div className="value">{formData.state || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>Zip Code</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.zip_code || ''}
                    onChange={(e) => setFormData({...formData, zip_code: e.target.value})}
                  />
                ) : (
                  <div className="value">{formData.zip_code || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>Property Type</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.property_type || ''}
                    onChange={(e) => setFormData({...formData, property_type: e.target.value})}
                  />
                ) : (
                  <div className="value">{formData.property_type || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>Property Value</label>
                {editing ? (
                  <input
                    type="number"
                    value={formData.property_value || ''}
                    onChange={(e) => setFormData({...formData, property_value: parseFloat(e.target.value)})}
                  />
                ) : (
                  <div className="value">
                    {formData.property_value ? `$${formData.property_value.toLocaleString()}` : 'N/A'}
                  </div>
                )}
              </div>
              <div className="info-field">
                <label>Down Payment</label>
                {editing ? (
                  <input
                    type="number"
                    value={formData.down_payment || ''}
                    onChange={(e) => setFormData({...formData, down_payment: parseFloat(e.target.value)})}
                  />
                ) : (
                  <div className="value">
                    {lead.down_payment ? `$${lead.down_payment.toLocaleString()}` : 'N/A'}
                  </div>
                )}
              </div>
              <div className="info-field">
                <label>Credit Score</label>
                {editing ? (
                  <input
                    type="number"
                    value={formData.credit_score || ''}
                    onChange={(e) => setFormData({...formData, credit_score: parseInt(e.target.value)})}
                  />
                ) : (
                  <div className="value">{formData.credit_score || 'N/A'}</div>
                )}
              </div>
            </div>
          </div>
          )}

          {/* Conversation Log Tab */}
          {activeTab === 'conversation' && (
          <div className="info-section">
            <h2>Conversation Log</h2>

            {/* Add Note Form */}
            <form onSubmit={handleAddNote} className="add-note-form">
              <textarea
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                placeholder="Add a note to the conversation log..."
                rows="3"
                disabled={noteLoading}
              />
              <button type="submit" disabled={noteLoading || !noteText.trim()}>
                {noteLoading ? 'Adding...' : 'Add Note'}
              </button>
            </form>

            <div className="conversation-log">
              {activities.length > 0 ? (
                activities.map((activity) => (
                  <div key={activity.id} className="activity-item">
                    <div className="activity-header">
                      <span className={`activity-type ${activity.type}`}>
                        {activity.type}
                      </span>
                      <span className="activity-date">
                        {new Date(activity.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="activity-description">{activity.content || activity.description}</div>
                  </div>
                ))
              ) : (
                <div className="empty-state">No activities yet</div>
              )}
            </div>
          </div>
          )}

          {/* Circle Tab */}
          {activeTab === 'circle' && (
          <div className="info-section">
            <h2>Circle</h2>
            <div className="circle-content">
              <p className="circle-description">
                View and manage the borrower's circle of influence - family members, co-borrowers,
                real estate agents, and other key contacts involved in the loan process.
              </p>

              <div className="circle-grid">
                <div className="circle-card">
                  <div className="circle-header">
                    <h3>👥 Co-Borrowers</h3>
                    <button className="btn-add-circle">+ Add</button>
                  </div>
                  <div className="circle-list">
                    <div className="empty-state">No co-borrowers added yet</div>
                  </div>
                </div>

                <div className="circle-card">
                  <div className="circle-header">
                    <h3>🏡 Real Estate Agent</h3>
                    <button className="btn-add-circle">+ Add</button>
                  </div>
                  <div className="circle-list">
                    <div className="empty-state">No agent assigned yet</div>
                  </div>
                </div>

                <div className="circle-card">
                  <div className="circle-header">
                    <h3>👨‍👩‍👧 Family Members</h3>
                    <button className="btn-add-circle">+ Add</button>
                  </div>
                  <div className="circle-list">
                    <div className="empty-state">No family members added yet</div>
                  </div>
                </div>

                <div className="circle-card">
                  <div className="circle-header">
                    <h3>🤝 Other Contacts</h3>
                    <button className="btn-add-circle">+ Add</button>
                  </div>
                  <div className="circle-list">
                    <div className="empty-state">No other contacts added yet</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          )}

          {/* Documents Tab */}
          {activeTab === 'documents' && (
          <div className="info-section">
            <h2>Documents</h2>
            <div className="documents-content">
              <p className="circle-description">
                Manage and organize all loan-related documents including income verification,
                credit reports, property documents, and disclosures.
              </p>

              <div className="documents-upload-area">
                <button className="btn-upload-document">
                  📄 Upload Document
                </button>
              </div>

              <div className="documents-grid">
                <div className="document-category">
                  <div className="category-header">
                    <h3>📋 Income Verification</h3>
                    <span className="doc-count">0 files</span>
                  </div>
                  <div className="document-list">
                    <div className="empty-state">No documents uploaded yet</div>
                  </div>
                </div>

                <div className="document-category">
                  <div className="category-header">
                    <h3>💳 Credit Reports</h3>
                    <span className="doc-count">0 files</span>
                  </div>
                  <div className="document-list">
                    <div className="empty-state">No documents uploaded yet</div>
                  </div>
                </div>

                <div className="document-category">
                  <div className="category-header">
                    <h3>🏠 Property Documents</h3>
                    <span className="doc-count">0 files</span>
                  </div>
                  <div className="document-list">
                    <div className="empty-state">No documents uploaded yet</div>
                  </div>
                </div>

                <div className="document-category">
                  <div className="category-header">
                    <h3>✍️ Disclosures & Forms</h3>
                    <span className="doc-count">0 files</span>
                  </div>
                  <div className="document-list">
                    <div className="empty-state">No documents uploaded yet</div>
                  </div>
                </div>

                <div className="document-category">
                  <div className="category-header">
                    <h3>🏦 Bank Statements</h3>
                    <span className="doc-count">0 files</span>
                  </div>
                  <div className="document-list">
                    <div className="empty-state">No documents uploaded yet</div>
                  </div>
                </div>

                <div className="document-category">
                  <div className="category-header">
                    <h3>📑 Other Documents</h3>
                    <span className="doc-count">0 files</span>
                  </div>
                  <div className="document-list">
                    <div className="empty-state">No documents uploaded yet</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          )}

          {/* AI Chat Assistant - Always Visible */}
          <div className="info-section">
            <h2>AI Chat Assistant</h2>
            <form onSubmit={handleSendMessage} className="ai-chat-form">
              <textarea
                value={chatMessage}
                onChange={(e) => setChatMessage(e.target.value)}
                placeholder="Ask the AI assistant about this lead..."
                rows="3"
                disabled={chatLoading}
              />
              <button type="submit" disabled={chatLoading || !chatMessage.trim()}>
                {chatLoading ? 'Sending...' : 'Send Message'}
              </button>
            </form>
          </div>
        </div>

        {/* Right Column - Actions & Email History */}
        <div className="right-column">
          {/* Action Buttons */}
          <div className="actions-card">
            <h3>Quick Actions</h3>
            <div className="action-buttons">
              <button
                className="action-btn sms"
                onClick={() => handleAction('sms')}
                disabled={!lead.phone}
              >
                <span className="icon">💬</span>
                <span>SMS Text</span>
              </button>
              <button
                className="action-btn task"
                onClick={() => handleAction('task')}
              >
                <span className="icon">✓</span>
                <span>Create Task</span>
              </button>
              <button
                className="action-btn email"
                onClick={() => handleAction('email')}
                disabled={!lead.email}
              >
                <span className="icon">✉️</span>
                <span>Send Email</span>
              </button>
              <button
                className="action-btn calendar"
                onClick={() => handleAction('calendar')}
              >
                <span className="icon">📅</span>
                <span>Set Appointment</span>
              </button>
            </div>
          </div>

          {/* Email History */}
          <div className="email-history-card">
            <h3>Email History</h3>
            <div className="email-list">
              {emails.length > 0 ? (
                emails.map((email) => (
                  <div key={email.id} className="email-item">
                    <div className="email-header">
                      <span className="email-subject">
                        {email.description.split('\n')[0]}
                      </span>
                      <span className="email-date">
                        {new Date(email.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="email-preview">
                      {email.description.substring(0, 100)}...
                    </div>
                  </div>
                ))
              ) : (
                <div className="empty-state">No emails yet</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LeadDetail;
