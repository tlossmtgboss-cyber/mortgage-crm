import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { leadsAPI, activitiesAPI, aiAPI } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import SMSModal from '../components/SMSModal';
import './LeadDetail.css';

function LeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [lead, setLead] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [chatMessage, setChatMessage] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [editing, setEditing] = useState(true); // Always in edit mode
  const [formData, setFormData] = useState({});
  const [emails, setEmails] = useState([]);
  const [activeTab, setActiveTab] = useState('personal');
  const [noteText, setNoteText] = useState('');
  const [noteLoading, setNoteLoading] = useState(false);
  const [borrowers, setBorrowers] = useState([]);
  const [activeBorrower, setActiveBorrower] = useState(0);
  const [saveTimeout, setSaveTimeout] = useState(null);
  const [showSMSModal, setShowSMSModal] = useState(false);

  useEffect(() => {
    loadLeadData();
    loadEmails();
    markLeadAsViewed();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const markLeadAsViewed = () => {
    try {
      // Get viewed leads from localStorage
      const stored = localStorage.getItem('viewedLeads');
      const viewedLeads = stored ? new Set(JSON.parse(stored)) : new Set();

      // Add current lead ID
      viewedLeads.add(String(id));

      // Save back to localStorage
      localStorage.setItem('viewedLeads', JSON.stringify([...viewedLeads]));
    } catch (error) {
      console.error('Error marking lead as viewed:', error);
    }
  };

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
      if (leadData.co_applicant_name) {
        const coborrowerName = String(leadData.co_applicant_name || '');
        const nameParts = coborrowerName.split(' ');
        borrowersList.push({
          id: 1,
          name: leadData.co_applicant_name,
          type: 'co-borrower',
          data: {
            name: leadData.co_applicant_name,
            first_name: nameParts[0] || '',
            last_name: nameParts.slice(1).join(' ') || '',
            email: leadData.co_applicant_email || '',
            phone: leadData.co_applicant_phone || '',
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
      let dataToSave;

      // Check if we're editing the co-borrower
      if (activeBorrower === 1) {
        // Update co-borrower fields
        const coApplicantName = formData.first_name && formData.last_name
          ? `${formData.first_name} ${formData.last_name}`
          : formData.name || '';

        dataToSave = {
          co_applicant_name: coApplicantName,
          co_applicant_email: formData.email || null,
          co_applicant_phone: formData.phone || null
        };
      } else {
        // Update primary borrower fields
        dataToSave = {
          ...formData,
          name: formData.first_name && formData.last_name
            ? `${formData.first_name} ${formData.last_name}`
            : formData.name || ''
        };
      }

      await leadsAPI.update(id, dataToSave);

      // Reload the lead data to sync with backend
      const updatedLead = await leadsAPI.getById(id);
      setLead(updatedLead);

      // Update the borrowers array
      if (activeBorrower === 1 && updatedLead.co_applicant_name) {
        const primaryName = updatedLead.first_name && updatedLead.last_name
          ? `${updatedLead.first_name} ${updatedLead.last_name}`
          : updatedLead.name || 'Primary Borrower';

        const coborrowerParts = (updatedLead.co_applicant_name || '').split(' ');
        const updatedBorrowers = [
          {
            id: 0,
            name: primaryName,
            type: 'primary',
            data: updatedLead
          },
          {
            id: 1,
            name: updatedLead.co_applicant_name,
            type: 'co-borrower',
            data: {
              name: updatedLead.co_applicant_name,
              first_name: coborrowerParts[0] || '',
              last_name: coborrowerParts.slice(1).join(' ') || '',
              email: updatedLead.co_applicant_email || '',
              phone: updatedLead.co_applicant_phone || '',
            }
          }
        ];
        setBorrowers(updatedBorrowers);
        setFormData(updatedBorrowers[1].data);
      }

      setEditing(false);
      alert('Lead updated successfully!');
    } catch (error) {
      console.error('Failed to update lead:', error);
      alert('Failed to update lead');
    }
  };

  const handleCancel = () => {
    // Restore the correct borrower's data based on active borrower
    if (activeBorrower < borrowers.length) {
      setFormData(borrowers[activeBorrower].data);
    } else {
      setFormData(lead);
    }
  };

  // Auto-save function with debounce
  const autoSaveField = async (fieldName, fieldValue) => {
    try {
      let dataToSave;

      // Check if we're editing the co-borrower
      if (activeBorrower === 1) {
        // Update co-borrower fields
        const updatedData = {...formData, [fieldName]: fieldValue};
        const coApplicantName = updatedData.first_name && updatedData.last_name
          ? `${updatedData.first_name} ${updatedData.last_name}`
          : updatedData.name || '';

        dataToSave = {
          co_applicant_name: coApplicantName,
          co_applicant_email: updatedData.email || null,
          co_applicant_phone: updatedData.phone || null
        };
      } else {
        // Update primary borrower field
        dataToSave = {
          [fieldName]: fieldValue
        };

        // If updating first_name or last_name, also update name
        if (fieldName === 'first_name' || fieldName === 'last_name') {
          const updatedData = {...formData, [fieldName]: fieldValue};
          if (updatedData.first_name && updatedData.last_name) {
            dataToSave.name = `${updatedData.first_name} ${updatedData.last_name}`;
          }
        }
      }

      await leadsAPI.update(id, dataToSave);
      console.log(`Field ${fieldName} saved successfully`);

      // Reload to sync with backend
      const updatedLead = await leadsAPI.getById(id);
      setLead(updatedLead);
    } catch (error) {
      console.error('Failed to auto-save field:', error);
      // Silently fail for auto-save to avoid disrupting user
    }
  };

  // Handle field change with debounced auto-save
  const handleFieldChange = (fieldName, fieldValue) => {
    // Update form data immediately for responsive UI
    setFormData({...formData, [fieldName]: fieldValue});

    // Clear existing timeout
    if (saveTimeout) {
      clearTimeout(saveTimeout);
    }

    // Set new timeout for auto-save (wait 1 second after user stops typing)
    const newTimeout = setTimeout(() => {
      autoSaveField(fieldName, fieldValue);
    }, 1000);

    setSaveTimeout(newTimeout);
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
      // Save the first additional borrower as co-borrower
      if (borrowers.length === 1) {
        await leadsAPI.update(id, {
          co_applicant_name: fullName
        });

        // Reload lead data to sync with backend
        const leadData = await leadsAPI.getById(id);
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

        if (leadData.co_applicant_name) {
          const coborrowerParts = (leadData.co_applicant_name || '').split(' ');
          updatedBorrowers.push({
            id: 1,
            name: leadData.co_applicant_name,
            type: 'co-borrower',
            data: {
              name: leadData.co_applicant_name,
              first_name: coborrowerParts[0] || '',
              last_name: coborrowerParts.slice(1).join(' ') || '',
              email: leadData.co_applicant_email || '',
              phone: leadData.co_applicant_phone || '',
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
      case 'call':
        window.open(`tel:${lead.phone}`, '_self');
        break;
      case 'sms':
        setShowSMSModal(true);
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
            <input
              type="number"
              value={formData.loan_amount || ''}
              onChange={(e) => handleFieldChange('loan_amount', e.target.value)}
              placeholder="$"
            />
          </div>

          <div className="loan-field">
            <label>Interest Rate</label>
            <input
              type="number"
              step="0.001"
              value={formData.interest_rate || ''}
              onChange={(e) => handleFieldChange('interest_rate', e.target.value)}
              placeholder="%"
            />
          </div>

          <div className="loan-field">
            <label>Loan Term</label>
            <input
              type="number"
              value={formData.loan_term || ''}
              onChange={(e) => handleFieldChange('loan_term', e.target.value)}
              placeholder="Years"
            />
          </div>

          <div className="loan-field">
            <label>Loan Type</label>
            <select
              value={formData.loan_type || ''}
              onChange={(e) => handleFieldChange('loan_type', e.target.value)}
            >
              <option value="">Select...</option>
              <option value="Conventional">Conventional</option>
              <option value="FHA">FHA</option>
              <option value="VA">VA</option>
              <option value="USDA">USDA</option>
              <option value="Jumbo">Jumbo</option>
              <option value="HELOC">HELOC</option>
            </select>
          </div>

          <div className="loan-field">
            <label>Lock Date</label>
            <input
              type="date"
              value={formData.lock_date || ''}
              onChange={(e) => handleFieldChange('lock_date', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Lock Expiration</label>
            <input
              type="date"
              value={formData.lock_expiration || ''}
              onChange={(e) => handleFieldChange('lock_expiration', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>APR</label>
            <input
              type="number"
              step="0.001"
              value={formData.apr || ''}
              onChange={(e) => handleFieldChange('apr', e.target.value)}
              placeholder="%"
            />
          </div>

          <div className="loan-field">
            <label>Points</label>
            <input
              type="number"
              step="0.125"
              value={formData.points || ''}
              onChange={(e) => handleFieldChange('points', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Lender</label>
            <input
              type="text"
              value={formData.lender || ''}
              onChange={(e) => handleFieldChange('lender', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Loan Officer</label>
            <input
              type="text"
              value={formData.loan_officer || ''}
              onChange={(e) => handleFieldChange('loan_officer', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Processor</label>
            <input
              type="text"
              value={formData.processor || ''}
              onChange={(e) => handleFieldChange('processor', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Underwriter</label>
            <input
              type="text"
              value={formData.underwriter || ''}
              onChange={(e) => handleFieldChange('underwriter', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Closing Date</label>
            <input
              type="date"
              value={formData.closing_date || ''}
              onChange={(e) => handleFieldChange('closing_date', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Appraisal Value</label>
            <input
              type="number"
              value={formData.appraisal_value || ''}
              onChange={(e) => handleFieldChange('appraisal_value', e.target.value)}
              placeholder="$"
            />
          </div>

          <div className="loan-field">
            <label>LTV %</label>
            <input
              type="number"
              step="0.01"
              value={formData.ltv || ''}
              onChange={(e) => handleFieldChange('ltv', e.target.value)}
              placeholder="%"
            />
          </div>

          <div className="loan-field">
            <label>DTI %</label>
            <input
              type="number"
              step="0.01"
              value={formData.dti || ''}
              onChange={(e) => handleFieldChange('dti', e.target.value)}
              placeholder="%"
            />
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
                <input
                  type="text"
                  value={formData.first_name || ''}
                  onChange={(e) => handleFieldChange('first_name', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>Last Name</label>
                <input
                  type="text"
                  value={formData.last_name || ''}
                  onChange={(e) => handleFieldChange('last_name', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>Email</label>
                <input
                  type="email"
                  value={formData.email || ''}
                  onChange={(e) => handleFieldChange('email', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>Phone</label>
                <input
                  type="tel"
                  value={formData.phone || ''}
                  onChange={(e) => handleFieldChange('phone', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>Loan Number</label>
                <input
                  type="text"
                  value={formData.loan_number || ''}
                  onChange={(e) => handleFieldChange('loan_number', e.target.value)}
                />
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
                <input
                  type="text"
                  value={formData.employment_status || ''}
                  onChange={(e) => handleFieldChange('employment_status', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>Employer Name</label>
                <input
                  type="text"
                  value={formData.employer_name || ''}
                  onChange={(e) => handleFieldChange('employer_name', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>Job Title</label>
                <input
                  type="text"
                  value={formData.job_title || ''}
                  onChange={(e) => handleFieldChange('job_title', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>Years at Job</label>
                <input
                  type="number"
                  value={formData.years_at_job || ''}
                  onChange={(e) => handleFieldChange('years_at_job', parseFloat(e.target.value))}
                />
              </div>
              <div className="info-field">
                <label>Annual Income</label>
                <input
                  type="number"
                  value={formData.annual_income || ''}
                  onChange={(e) => handleFieldChange('annual_income', parseFloat(e.target.value))}
                />
              </div>
              <div className="info-field">
                <label>Monthly Income</label>
                <input
                  type="number"
                  value={formData.monthly_income || ''}
                  onChange={(e) => handleFieldChange('monthly_income', parseFloat(e.target.value))}
                />
              </div>
              <div className="info-field">
                <label>Other Income</label>
                <input
                  type="number"
                  value={formData.other_income || ''}
                  onChange={(e) => handleFieldChange('other_income', parseFloat(e.target.value))}
                />
              </div>
              <div className="info-field">
                <label>Income Source</label>
                <input
                  type="text"
                  value={formData.income_source || ''}
                  onChange={(e) => handleFieldChange('income_source', e.target.value)}
                />
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
                <input
                  type="text"
                  value={formData.address || ''}
                  onChange={(e) => handleFieldChange('address', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>City</label>
                <input
                  type="text"
                  value={formData.city || ''}
                  onChange={(e) => handleFieldChange('city', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>State</label>
                <input
                  type="text"
                  value={formData.state || ''}
                  onChange={(e) => handleFieldChange('state', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>Zip Code</label>
                <input
                  type="text"
                  value={formData.zip_code || ''}
                  onChange={(e) => handleFieldChange('zip_code', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>Property Type</label>
                <input
                  type="text"
                  value={formData.property_type || ''}
                  onChange={(e) => handleFieldChange('property_type', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>Property Value</label>
                <input
                  type="number"
                  value={formData.property_value || ''}
                  onChange={(e) => handleFieldChange('property_value', parseFloat(e.target.value))}
                />
              </div>
              <div className="info-field">
                <label>Down Payment</label>
                <input
                  type="number"
                  value={formData.down_payment || ''}
                  onChange={(e) => handleFieldChange('down_payment', parseFloat(e.target.value))}
                />
              </div>
              <div className="info-field">
                <label>Credit Score</label>
                <input
                  type="number"
                  value={formData.credit_score || ''}
                  onChange={(e) => handleFieldChange('credit_score', parseInt(e.target.value))}
                />
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
                className="action-btn call"
                onClick={() => handleAction('call')}
                disabled={!lead.phone}
                title="Click to call using your phone"
              >
                <span className="icon">📞</span>
                <span>Call</span>
              </button>
              <button
                className="action-btn sms"
                onClick={() => handleAction('sms')}
                disabled={!lead.phone}
                title="Send SMS using your phone"
              >
                <span className="icon">💬</span>
                <span>SMS Text</span>
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
                className="action-btn task"
                onClick={() => handleAction('task')}
              >
                <span className="icon">✓</span>
                <span>Create Task</span>
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
                        {(email.description || email.content || '').split('\n')[0] || 'No subject'}
                      </span>
                      <span className="email-date">
                        {new Date(email.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="email-preview">
                      {(email.description || email.content || '').substring(0, 100)}...
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

      {/* SMS Modal */}
      {lead && (
        <SMSModal
          isOpen={showSMSModal}
          onClose={() => setShowSMSModal(false)}
          lead={lead}
        />
      )}
    </div>
  );
}

export default LeadDetail;
