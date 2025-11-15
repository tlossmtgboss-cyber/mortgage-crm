// VERSION: 2024-11-14-v2 - MOCK DATA FIX
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { leadsAPI, activitiesAPI, aiAPI, teamAPI } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import SMSModal from '../components/SMSModal';
import TeamsModal from '../components/TeamsModal';
import RecordingModal from '../components/RecordingModal';
import VoicemailModal from '../components/VoicemailModal';
import SmartAIChat from '../components/SmartAIChat';
import './LeadDetail.css';

// Mock lead data generator (same as Leads.js)
const generateMockLeads = () => {
  const currentDate = new Date();

  return [
    { id: 1, name: 'Sarah Johnson', email: 'sarah.johnson@email.com', phone: '(555) 123-4567', stage: 'New', source: 'Website', credit_score: 720, loan_amount: 425000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 2 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 85, next_action: 'Initial Contact' },
    { id: 2, name: 'Michael Chen', email: 'mchen@email.com', phone: '(555) 234-5678', stage: 'New', source: 'Referral - Amy Smith', credit_score: 695, loan_amount: 380000, property_type: 'Condo', created_at: new Date(currentDate.getTime() - 1 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 78, next_action: 'Call to Schedule Meeting' },
    { id: 3, name: 'Emily Rodriguez', email: 'emily.r@email.com', phone: '(555) 345-6789', stage: 'New', source: 'Social Media', credit_score: 0, loan_amount: 295000, property_type: 'Townhouse', created_at: new Date(currentDate.getTime() - 3 * 60 * 60 * 1000).toISOString(), ai_score: 72, next_action: 'Send Pre-Qual Email' },
    { id: 4, name: 'David Martinez', email: 'david.m@email.com', phone: '(555) 456-7890', stage: 'Attempted Contact', source: 'Zillow', credit_score: 710, loan_amount: 550000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 4 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 80, next_action: 'Follow-up Call', contact_attempts: 2 },
    { id: 5, name: 'Jennifer Lee', email: 'jlee@email.com', phone: '(555) 567-8901', stage: 'Attempted Contact', source: 'Facebook', credit_score: 685, loan_amount: 340000, property_type: 'Condo', created_at: new Date(currentDate.getTime() - 5 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 65, next_action: 'Send SMS', contact_attempts: 1 },
    { id: 6, name: 'Robert Taylor', email: 'rtaylor@email.com', phone: '(555) 678-9012', stage: 'Prospect', source: 'Referral - Bob Johnson', credit_score: 745, loan_amount: 620000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 92, next_action: 'Schedule Pre-Approval Meeting' },
    { id: 7, name: 'Amanda Wilson', email: 'awilson@email.com', phone: '(555) 789-0123', stage: 'Prospect', source: 'Website', credit_score: 702, loan_amount: 415000, property_type: 'Townhouse', created_at: new Date(currentDate.getTime() - 8 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 88, next_action: 'Send Rate Quote' },
    { id: 8, name: 'James Anderson', email: 'j.anderson@email.com', phone: '(555) 890-1234', stage: 'Prospect', source: 'Realtor.com', credit_score: 678, loan_amount: 365000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 9 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 74, next_action: 'Discuss Programs' },
    { id: 9, name: 'Lisa Brown', email: 'lbrown@email.com', phone: '(555) 901-2345', stage: 'Pre-Qualified', source: 'Referral - Amy Smith', credit_score: 725, loan_amount: 485000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 12 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 90, next_action: 'Start Application' },
    { id: 10, name: 'Christopher Davis', email: 'cdavis@email.com', phone: '(555) 012-3456', stage: 'Pre-Qualified', source: 'Website', credit_score: 698, loan_amount: 395000, property_type: 'Condo', created_at: new Date(currentDate.getTime() - 14 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 82, next_action: 'Find Realtor' },
    { id: 11, name: 'Michelle Garcia', email: 'mgarcia@email.com', phone: '(555) 123-7890', stage: 'Application', source: 'Zillow', credit_score: 715, loan_amount: 535000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 16 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 87, next_action: 'Collect Documents' },
    { id: 12, name: 'Daniel Moore', email: 'dmoore@email.com', phone: '(555) 234-8901', stage: 'Application', source: 'Referral - Bob Johnson', credit_score: 735, loan_amount: 455000, property_type: 'Townhouse', created_at: new Date(currentDate.getTime() - 18 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 91, next_action: 'Review Application' },
    { id: 13, name: 'Patricia Thompson', email: 'pthompson@email.com', phone: '(555) 345-9012', stage: 'Pre-Approved', source: 'Facebook', credit_score: 740, loan_amount: 575000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 21 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 94, next_action: 'House Hunting' },
    { id: 14, name: 'Kevin White', email: 'kwhite@email.com', phone: '(555) 456-0123', stage: 'Pre-Approved', source: 'Website', credit_score: 708, loan_amount: 410000, property_type: 'Condo', created_at: new Date(currentDate.getTime() - 24 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 86, next_action: 'Check-in Weekly' },
    { id: 15, name: 'Nancy Harris', email: 'nharris@email.com', phone: '(555) 567-1234', stage: 'Withdrawn', source: 'Zillow', credit_score: 690, loan_amount: 325000, property_type: 'Townhouse', created_at: new Date(currentDate.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 45, next_action: 'None', withdrawal_reason: 'Found another lender' },
    { id: 16, name: 'Brian Clark', email: 'bclark@email.com', phone: '(555) 678-2345', stage: 'Does Not Qualify', source: 'Social Media', credit_score: 580, loan_amount: 285000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 35 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 30, next_action: 'Credit Repair Referral', disqualification_reason: 'Credit score too low' },
  ];
};

function LeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [lead, setLead] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
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
  const [showTeamsModal, setShowTeamsModal] = useState(false);
  const [showRecordingModal, setShowRecordingModal] = useState(false);
  const [showVoicemailModal, setShowVoicemailModal] = useState(false);
  const [teamMembers, setTeamMembers] = useState([]);
  const [assignedTeamMembers, setAssignedTeamMembers] = useState({});

  useEffect(() => {
    loadLeadData();
    loadEmails();
    loadTeamMembers();
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
      let leadData = null;
      let activitiesData = [];

      try {
        // Try to fetch from API first
        [leadData, activitiesData] = await Promise.all([
          leadsAPI.getById(id),
          activitiesAPI.getAll({ lead_id: id })
        ]);
        console.log('✅ Loaded lead from API:', leadData);
      } catch (apiError) {
        console.log('⚠️ API failed, using mock data. Error:', apiError);
        // Fallback to mock data
        const mockLeads = generateMockLeads();
        console.log('📦 Generated mock leads, total count:', mockLeads.length);
        console.log('🔍 Looking for lead ID:', id, 'Type:', typeof id);
        leadData = mockLeads.find(lead => lead.id === parseInt(id));
        console.log('🎯 Found mock lead:', leadData);

        if (!leadData) {
          console.error('❌ Lead not found in mock data');
          alert('Lead not found in mock data');
          navigate('/leads');
          return;
        }
        activitiesData = [];
      }

      console.log('✨ Setting lead data:', leadData);
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
      navigate('/leads');
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

  const loadTeamMembers = async () => {
    try {
      const members = await teamAPI.getMembers();
      setTeamMembers(Array.isArray(members) ? members : []);
    } catch (error) {
      console.error('Failed to load team members:', error);
      setTeamMembers([]);
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
      case 'teams':
        setShowTeamsModal(true);
        break;
      case 'record':
        setShowRecordingModal(true);
        break;
      case 'voicemail':
        setShowVoicemailModal(true);
        break;
      default:
        break;
    }
  };

  // Group team members by role
  const getTeamMembersByRole = () => {
    const grouped = {};
    teamMembers.forEach(member => {
      const role = member.role || 'Other';
      if (!grouped[role]) {
        grouped[role] = [];
      }
      grouped[role].push(member);
    });
    return grouped;
  };

  // Handle team member assignment
  const handleAssignTeamMember = async (role, member) => {
    try {
      const updatedAssignments = {
        ...assignedTeamMembers,
        [role]: member
      };
      setAssignedTeamMembers(updatedAssignments);

      // Save to backend - store as JSON or separate fields
      const teamAssignmentData = {
        [`team_${role.toLowerCase().replace(/\s+/g, '_')}_id`]: member.id,
        [`team_${role.toLowerCase().replace(/\s+/g, '_')}_name`]: `${member.first_name} ${member.last_name}`,
        [`team_${role.toLowerCase().replace(/\s+/g, '_')}_email`]: member.email
      };

      await leadsAPI.update(id, teamAssignmentData);
      alert(`${member.first_name} ${member.last_name} assigned as ${role}`);
    } catch (error) {
      console.error('Failed to assign team member:', error);
      alert('Failed to assign team member');
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
          className={`tab-btn ${activeTab === 'team' ? 'active' : ''}`}
          onClick={() => setActiveTab('team')}
        >
          Team Members
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
        <button
          className={`tab-btn ${activeTab === 'important-dates' ? 'active' : ''}`}
          onClick={() => setActiveTab('important-dates')}
        >
          Important Dates
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

          {/* Team Members Tab */}
          {activeTab === 'team' && (
          <div className="info-section">
            <h2>Team Members</h2>
            <div className="team-description">
              <p>Assign internal team members who are working on this lead/loan.</p>
            </div>

            {Object.keys(getTeamMembersByRole()).length === 0 ? (
              <div className="empty-state">
                <p>No team members have been created yet.</p>
                <p>Go to Settings → Team Members to add your team.</p>
              </div>
            ) : (
              <div className="team-roles-list">
                {Object.entries(getTeamMembersByRole()).map(([role, members]) => (
                  <div key={role} className="team-role-section">
                    <div className="team-role-header">
                      <h3>{role}</h3>
                      <span className="member-count">{members.length} available</span>
                    </div>

                    {assignedTeamMembers[role] ? (
                      <div className="assigned-member">
                        <div className="member-info">
                          <div className="member-name">
                            {assignedTeamMembers[role].first_name} {assignedTeamMembers[role].last_name}
                          </div>
                          <div className="member-contact">
                            {assignedTeamMembers[role].email && (
                              <span className="member-email">{assignedTeamMembers[role].email}</span>
                            )}
                            {assignedTeamMembers[role].phone && (
                              <span className="member-phone">{assignedTeamMembers[role].phone}</span>
                            )}
                          </div>
                        </div>
                        <button
                          className="btn-change-member"
                          onClick={() => setAssignedTeamMembers({...assignedTeamMembers, [role]: null})}
                        >
                          Change
                        </button>
                      </div>
                    ) : (
                      <div className="member-selection">
                        <select
                          className="member-select"
                          onChange={(e) => {
                            const member = members.find(m => m.id === parseInt(e.target.value));
                            if (member) handleAssignTeamMember(role, member);
                          }}
                          defaultValue=""
                        >
                          <option value="" disabled>Select a team member...</option>
                          {members.map(member => (
                            <option key={member.id} value={member.id}>
                              {member.first_name} {member.last_name}
                              {member.title && ` - ${member.title}`}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
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

          {/* Important Dates Tab */}
          {activeTab === 'important-dates' && (
          <div className="tab-content">
            <div className="info-section">
              <h2>Lead Stage Dates</h2>
              <p className="section-subtitle">Track key milestone dates throughout the lead journey</p>

              <div className="dates-grid">
                <div className="date-field">
                  <label>Lead Created Date</label>
                  <input
                    type="date"
                    value={formData.lead_created_date || ''}
                    onChange={(e) => handleFieldChange('lead_created_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>First Contact Attempt Date</label>
                  <input
                    type="date"
                    value={formData.first_contact_attempt_date || ''}
                    onChange={(e) => handleFieldChange('first_contact_attempt_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>First Contact Successful Date</label>
                  <input
                    type="date"
                    value={formData.first_contact_successful_date || ''}
                    onChange={(e) => handleFieldChange('first_contact_successful_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Lead Qualification Date</label>
                  <input
                    type="date"
                    value={formData.lead_qualification_date || ''}
                    onChange={(e) => handleFieldChange('lead_qualification_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Application Link Sent Date</label>
                  <input
                    type="date"
                    value={formData.application_link_sent_date || ''}
                    onChange={(e) => handleFieldChange('application_link_sent_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Application Started Date</label>
                  <input
                    type="date"
                    value={formData.application_started_date || ''}
                    onChange={(e) => handleFieldChange('application_started_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Application Completed Date</label>
                  <input
                    type="date"
                    value={formData.application_completed_date || ''}
                    onChange={(e) => handleFieldChange('application_completed_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Credit Pulled Date</label>
                  <input
                    type="date"
                    value={formData.credit_pulled_date || ''}
                    onChange={(e) => handleFieldChange('credit_pulled_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Pre-Approval Submission Date</label>
                  <input
                    type="date"
                    value={formData.preapproval_submission_date || ''}
                    onChange={(e) => handleFieldChange('preapproval_submission_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Pre-Approval Issued Date</label>
                  <input
                    type="date"
                    value={formData.preapproval_issued_date || ''}
                    onChange={(e) => handleFieldChange('preapproval_issued_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Realtor Referral Date</label>
                  <input
                    type="date"
                    value={formData.realtor_referral_date || ''}
                    onChange={(e) => handleFieldChange('realtor_referral_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Pre-Approval Expiration Date</label>
                  <input
                    type="date"
                    value={formData.preapproval_expiration_date || ''}
                    onChange={(e) => handleFieldChange('preapproval_expiration_date', e.target.value)}
                  />
                  <small className="field-hint">Typically 90 days from credit pull</small>
                </div>

                <div className="date-field">
                  <label>Rate Watch Enrollment Date</label>
                  <input
                    type="date"
                    value={formData.rate_watch_enrollment_date || ''}
                    onChange={(e) => handleFieldChange('rate_watch_enrollment_date', e.target.value)}
                  />
                  <small className="field-hint">For shopping-phase automation</small>
                </div>
              </div>
            </div>
          </div>
          )}

          {/* Smart AI Assistant - Always Visible */}
          <div className="smart-chat-card">
            <SmartAIChat leadId={lead.id} />
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
              <button
                className="action-btn teams"
                onClick={() => handleAction('teams')}
                title="Create Microsoft Teams meeting"
              >
                <span className="icon">👥</span>
                <span>Teams Meeting</span>
              </button>
              <button
                className="action-btn record"
                onClick={() => handleAction('record')}
                title="Record meeting with Recall.ai bot"
              >
                <span className="icon">🎥</span>
                <span>Record Meeting</span>
              </button>
              <button
                className="action-btn voicemail"
                onClick={() => handleAction('voicemail')}
                disabled={!lead.phone}
                title="Drop voicemail message"
              >
                <span className="icon">📞</span>
                <span>Voicemail Drop</span>
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

      {/* Teams Modal */}
      {lead && (
        <TeamsModal
          isOpen={showTeamsModal}
          onClose={() => setShowTeamsModal(false)}
          lead={lead}
        />
      )}

      {/* Recording Modal */}
      {lead && (
        <RecordingModal
          isOpen={showRecordingModal}
          onClose={() => setShowRecordingModal(false)}
          lead={lead}
        />
      )}

      {/* Voicemail Modal */}
      {lead && (
        <VoicemailModal
          isOpen={showVoicemailModal}
          onClose={() => setShowVoicemailModal(false)}
          lead={lead}
        />
      )}
    </div>
  );
}

export default LeadDetail;
