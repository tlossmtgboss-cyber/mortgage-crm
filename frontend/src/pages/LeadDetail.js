// VERSION: 2024-11-14-v2 - MOCK DATA FIX
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { leadsAPI, activitiesAPI, circleOfCashflowAPI } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import SMSModal from '../components/SMSModal';
import TeamsModal from '../components/TeamsModal';
import RecordingModal from '../components/RecordingModal';
import VoicemailModal from '../components/VoicemailModal';
import EscalationModal from '../components/EscalationModal';
import VoicemailDrop from '../components/VoicemailDrop';
import CreateTaskModal from '../components/CreateTaskModal';
import AppointmentModal from '../components/AppointmentModal';
import TeamAssignment from '../components/TeamAssignment';
import EmploymentTab from '../components/EmploymentTab';
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
  const [showVoicemailDrop, setShowVoicemailDrop] = useState(false);
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [showAppointmentModal, setShowAppointmentModal] = useState(false);
  const [showEscalationModal, setShowEscalationModal] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState('');

  // Circle of Cashflow state
  const [cashflowOpportunities, setCashflowOpportunities] = useState([]);
  const [cashflowReferrals, setCashflowReferrals] = useState([]);
  const [cashflowPartners, setCashflowPartners] = useState([]);
  const [cashflowLoading, setCashflowLoading] = useState(false);

  // Circle of Influence state
  const [circleContacts, setCircleContacts] = useState([]);
  const [showCircleModal, setShowCircleModal] = useState(false);
  const [circleForm, setCircleForm] = useState({
    name: '',
    email: '',
    phone: '',
    type: 'Co-Borrower',
    notes: ''
  });
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [showSearchResults, setShowSearchResults] = useState(false);

  const circleContactTypes = [
    { value: 'Co-Borrower', icon: '👥' },
    { value: 'Real Estate Agent', icon: '🏡' },
    { value: 'Family Member', icon: '👨‍👩‍👧' },
    { value: 'Attorney', icon: '⚖️' },
    { value: 'Financial Advisor', icon: '💼' },
    { value: 'Insurance Agent', icon: '🛡️' },
    { value: 'Accountant', icon: '📊' },
    { value: 'Other Contact', icon: '🤝' }
  ];

  // Custom fields state
  const [customFields, setCustomFields] = useState([]);
  const [showAddFieldModal, setShowAddFieldModal] = useState(false);
  const [newFieldName, setNewFieldName] = useState('');

  const handleAddCustomField = () => {
    if (!newFieldName.trim()) return;
    const fieldKey = newFieldName.toLowerCase().replace(/\s+/g, '_');
    setCustomFields([...customFields, { key: fieldKey, label: newFieldName }]);
    setNewFieldName('');
    setShowAddFieldModal(false);
  };

  const handleRemoveCustomField = (fieldKey) => {
    setCustomFields(customFields.filter(f => f.key !== fieldKey));
  };

  const searchContacts = async (query) => {
    if (query.length < 2) {
      setSearchResults([]);
      setShowSearchResults(false);
      return;
    }
    setSearchLoading(true);
    try {
      const response = await leadsAPI.search(query);
      setSearchResults(response.leads || []);
      setShowSearchResults(true);
    } catch (error) {
      console.error('Search error:', error);
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  };

  const handleNameChange = (e) => {
    const value = e.target.value;
    setCircleForm({...circleForm, name: value});
    searchContacts(value);
  };

  const selectSearchResult = (contact) => {
    setCircleForm({
      ...circleForm,
      name: contact.name,
      email: contact.email || '',
      phone: contact.phone || ''
    });
    setShowSearchResults(false);
    setSearchResults([]);
  };

  const handleAddCircleContact = () => {
    if (!circleForm.name.trim()) return;
    const newContact = {
      id: Date.now(),
      ...circleForm
    };
    setCircleContacts([...circleContacts, newContact]);
    setCircleForm({ name: '', email: '', phone: '', type: 'Co-Borrower', notes: '' });
    setShowCircleModal(false);
  };

  const handleDeleteCircleContact = (contactId) => {
    setCircleContacts(circleContacts.filter(c => c.id !== contactId));
  };

  const handleEditCircleContact = (contact) => {
    setCircleForm({
      name: contact.name,
      email: contact.email || '',
      phone: contact.phone || '',
      type: contact.type,
      notes: contact.notes || '',
      editId: contact.id,
      leadId: contact.leadId
    });
    setShowCircleModal(true);
  };

  const handleAddCircleContactSubmit = () => {
    if (!circleForm.name.trim()) return;

    if (circleForm.editId) {
      // Editing existing contact
      setCircleContacts(circleContacts.map(c =>
        c.id === circleForm.editId
          ? { ...c, name: circleForm.name, email: circleForm.email, phone: circleForm.phone, type: circleForm.type, notes: circleForm.notes }
          : c
      ));
    } else {
      // Adding new contact
      const newContact = {
        id: Date.now(),
        leadId: searchResults.find(r => r.name === circleForm.name)?.id || null,
        ...circleForm
      };
      setCircleContacts([...circleContacts, newContact]);
    }

    setCircleForm({ name: '', email: '', phone: '', type: 'Co-Borrower', notes: '' });
    setShowCircleModal(false);
    setShowSearchResults(false);
  };

  const getContactIcon = (type) => {
    const found = circleContactTypes.find(t => t.value === type);
    return found ? found.icon : '🤝';
  };

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
      let leadData = null;
      let activitiesData = [];

      try {
        // Try to fetch from API first
        const leadIdInt = parseInt(id);
        [leadData, activitiesData] = await Promise.all([
          leadsAPI.getById(leadIdInt),
          activitiesAPI.getAll({ lead_id: leadIdInt })
        ]);
        console.log('✅ Loaded lead from API:', leadData);
        console.log('✅ Loaded activities from API:', activitiesData);
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

      // Split name into first_name and last_name if not already present
      let processedData = { ...leadData };
      if (leadData.name && (!leadData.first_name || !leadData.last_name)) {
        const nameParts = leadData.name.split(' ');
        processedData.first_name = nameParts[0] || '';
        processedData.last_name = nameParts.slice(1).join(' ') || '';
      }

      setFormData(processedData);
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

  const loadCircleOfCashflow = async () => {
    try {
      setCashflowLoading(true);
      const [oppsData, refsData, partnersData] = await Promise.all([
        circleOfCashflowAPI.getOpportunities(id),
        circleOfCashflowAPI.getReferrals(id),
        circleOfCashflowAPI.getPartners()
      ]);
      setCashflowOpportunities(oppsData.opportunities || []);
      setCashflowReferrals(refsData.referrals || []);
      setCashflowPartners(partnersData.partners || []);
    } catch (error) {
      console.error('Failed to load Circle of Cashflow data:', error);
    } finally {
      setCashflowLoading(false);
    }
  };

  // Load Circle of Cashflow data when Circle tab is selected
  useEffect(() => {
    if (activeTab === 'circle') {
      loadCircleOfCashflow();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

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

  const handleVoiceCommand = () => {
    // Check if browser supports Web Speech API
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert('Sorry, your browser does not support speech recognition. Please try Chrome or Edge.');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      setIsListening(true);
      console.log('Voice recognition started. Speak now...');
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setVoiceTranscript(transcript);
      console.log('Voice command received:', transcript);

      // Send the transcript to the SmartAI chat
      // The SmartAI component will need to handle this
      window.dispatchEvent(new CustomEvent('voiceCommand', {
        detail: { transcript, leadId: lead.id }
      }));
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
      if (event.error === 'no-speech') {
        alert('No speech detected. Please try again.');
      } else {
        alert(`Error occurred: ${event.error}`);
      }
    };

    recognition.onend = () => {
      setIsListening(false);
      console.log('Voice recognition ended');
    };

    recognition.start();
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
        setShowTaskModal(true);
        break;
      case 'calendar':
        setShowAppointmentModal(true);
        break;
      case 'teams':
        setShowTeamsModal(true);
        break;
      case 'record':
        setShowRecordingModal(true);
        break;
      case 'voicemail':
        setShowVoicemailDrop(true);
        break;
      case 'voice':
        handleVoiceCommand();
        break;
      case 'escalation':
        setShowEscalationModal(true);
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
          Property
        </button>
        <button
          className={`tab-btn ${activeTab === 'team' ? 'active' : ''}`}
          onClick={() => setActiveTab('team')}
        >
          Team Members
        </button>
        <button
          className={`tab-btn ${activeTab === 'marketing' ? 'active' : ''}`}
          onClick={() => setActiveTab('marketing')}
        >
          Marketing
        </button>
        <button
          className={`tab-btn ${activeTab === 'email' ? 'active' : ''}`}
          onClick={() => setActiveTab('email')}
        >
          Email
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
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h2 style={{ margin: 0 }}>Personal Information</h2>
              <button
                onClick={() => setShowAddFieldModal(true)}
                style={{
                  background: '#007bff',
                  color: 'white',
                  border: 'none',
                  borderRadius: '50%',
                  width: '32px',
                  height: '32px',
                  fontSize: '20px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  lineHeight: 1
                }}
                title="Add custom field"
              >
                +
              </button>
            </div>
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
              {/* Custom Fields */}
              {customFields.map((field) => (
                <div className="info-field" key={field.key}>
                  <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    {field.label}
                    <button
                      onClick={() => handleRemoveCustomField(field.key)}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: '#dc3545',
                        cursor: 'pointer',
                        fontSize: '14px',
                        padding: '0 4px'
                      }}
                      title="Remove field"
                    >
                      ×
                    </button>
                  </label>
                  <input
                    type="text"
                    value={formData[field.key] || ''}
                    onChange={(e) => handleFieldChange(field.key, e.target.value)}
                  />
                </div>
              ))}
            </div>

            {/* Add Field Modal */}
            {showAddFieldModal && (
              <div className="modal-overlay" onClick={() => setShowAddFieldModal(false)}>
                <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '400px' }}>
                  <div className="modal-header">
                    <h3>Add Custom Field</h3>
                    <button className="modal-close" onClick={() => setShowAddFieldModal(false)}>×</button>
                  </div>
                  <div className="modal-body">
                    <div className="form-group">
                      <label>Field Name</label>
                      <input
                        type="text"
                        value={newFieldName}
                        onChange={e => setNewFieldName(e.target.value)}
                        className="form-control"
                        placeholder="Enter field name"
                        autoFocus
                      />
                    </div>
                  </div>
                  <div className="modal-footer">
                    <button className="btn-secondary" onClick={() => setShowAddFieldModal(false)}>Cancel</button>
                    <button
                      className="btn-primary"
                      onClick={handleAddCustomField}
                      disabled={!newFieldName.trim()}
                    >
                      Add Field
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
          )}

          {/* Employment Tab */}
          {activeTab === 'employment' && (
            <EmploymentTab
              leadId={id}
              formData={formData}
              onFieldChange={handleFieldChange}
              entityType="leads"
            />
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
            <TeamAssignment leadId={id} />
          </div>
          )}

          {/* Marketing Tab */}
          {activeTab === 'marketing' && (
          <div className="info-section">
            <h2>Marketing</h2>
            <div className="marketing-content">
              <p className="section-description" style={{ color: '#666', marginBottom: '20px' }}>
                View and manage marketing campaigns, drip sequences, and promotional content for this lead.
              </p>

              <div className="marketing-campaigns" style={{ marginBottom: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 style={{ margin: 0 }}>Active Campaigns</h3>
                  <button className="btn-primary" style={{ padding: '8px 16px', fontSize: '14px' }}>
                    + Add to Campaign
                  </button>
                </div>
                <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px', textAlign: 'center', color: '#666' }}>
                  No active campaigns. Add this lead to a marketing campaign to start automated outreach.
                </div>
              </div>

              <div className="drip-sequences" style={{ marginBottom: '24px' }}>
                <h3 style={{ marginBottom: '16px' }}>Drip Sequences</h3>
                <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px', textAlign: 'center', color: '#666' }}>
                  No drip sequences assigned. Set up automated follow-up sequences in Settings.
                </div>
              </div>

              <div className="marketing-history">
                <h3 style={{ marginBottom: '16px' }}>Marketing History</h3>
                <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px', textAlign: 'center', color: '#666' }}>
                  No marketing activities recorded yet.
                </div>
              </div>
            </div>
          </div>
          )}

          {/* Email Tab */}
          {activeTab === 'email' && (
          <div className="info-section">
            <h2>Email</h2>
            <div className="email-content">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <p className="section-description" style={{ color: '#666', margin: 0 }}>
                  View all email communications with this lead.
                </p>
                <button
                  className="btn-primary"
                  style={{ padding: '8px 16px', fontSize: '14px' }}
                  onClick={() => lead?.email && window.open(`mailto:${lead.email}`, '_blank')}
                  disabled={!lead?.email}
                >
                  + Compose Email
                </button>
              </div>

              {/* Email History */}
              <div className="email-history-section">
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
              {/* Circle of Cashflow Section */}
              <div className="cashflow-section" style={{ marginBottom: '30px' }}>
                <h3 style={{ marginBottom: '15px', color: '#2e7d32' }}>Circle of Cashflow - Referral Opportunities</h3>

                {cashflowLoading ? (
                  <p>Loading referral data...</p>
                ) : (
                  <>
                    {/* Opportunities */}
                    {cashflowOpportunities.length > 0 ? (
                      <div className="circle-grid" style={{ marginBottom: '20px' }}>
                        {cashflowOpportunities.map(opp => (
                          <div key={opp.id} className="circle-card" style={{ borderLeft: '4px solid #ff9800' }}>
                            <div className="circle-header">
                              <h3>💡 {opp.category.replace('_', ' ').toUpperCase()}</h3>
                              <span style={{
                                padding: '4px 8px',
                                borderRadius: '4px',
                                fontSize: '12px',
                                backgroundColor: opp.status === 'detected' ? '#fff3e0' : opp.status === 'sent' ? '#e8f5e9' : '#e3f2fd',
                                color: opp.status === 'detected' ? '#e65100' : opp.status === 'sent' ? '#2e7d32' : '#1565c0'
                              }}>
                                {opp.status}
                              </span>
                            </div>
                            <div className="circle-list">
                              <p style={{ fontSize: '14px', color: '#666', margin: '8px 0' }}>{opp.ai_reasoning}</p>
                              <p style={{ fontSize: '12px', color: '#999' }}>Priority: {opp.priority}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p style={{ color: '#999', fontStyle: 'italic', marginBottom: '20px' }}>
                        No referral opportunities detected. Submit a financial questionnaire to identify opportunities.
                      </p>
                    )}

                    {/* Referral History */}
                    {cashflowReferrals.length > 0 && (
                      <div style={{ marginBottom: '20px' }}>
                        <h4 style={{ marginBottom: '10px' }}>Referral History</h4>
                        <div className="circle-grid">
                          {cashflowReferrals.map(ref => (
                            <div key={ref.id} className="circle-card" style={{ borderLeft: '4px solid #4caf50' }}>
                              <div className="circle-header">
                                <h3>📤 {ref.partner_name || 'Partner'}</h3>
                                <span style={{ fontSize: '12px', color: '#666' }}>{ref.status}</span>
                              </div>
                              <div className="circle-list">
                                <p style={{ fontSize: '14px' }}>{ref.category.replace('_', ' ')}</p>
                                <p style={{ fontSize: '12px', color: '#999' }}>{new Date(ref.referral_date).toLocaleDateString()}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Available Partners */}
                    {cashflowPartners.length > 0 && (
                      <div>
                        <h4 style={{ marginBottom: '10px' }}>Partner Network ({cashflowPartners.length})</h4>
                        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                          {cashflowPartners.slice(0, 6).map(partner => (
                            <div key={partner.id} style={{
                              padding: '8px 12px',
                              backgroundColor: '#f5f5f5',
                              borderRadius: '6px',
                              fontSize: '13px'
                            }}>
                              <strong>{partner.business_name}</strong>
                              <span style={{ color: '#666', marginLeft: '8px' }}>{partner.category.replace('_', ' ')}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>

              {/* Circle of Influence Section */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                <h3 style={{ margin: 0 }}>Circle of Influence</h3>
                <button
                  className="btn-add-circle"
                  onClick={() => setShowCircleModal(true)}
                  style={{ padding: '8px 16px' }}
                >
                  + Add Contact
                </button>
              </div>
              <p className="circle-description">
                Add and manage the borrower's circle of influence - family members, co-borrowers,
                real estate agents, and other key contacts involved in the loan process.
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {circleContacts.length === 0 ? (
                  <div style={{ padding: '20px', textAlign: 'center', color: '#999', backgroundColor: '#f8f9fa', borderRadius: '8px', border: '1px solid #e9ecef' }}>
                    No contacts added yet. Click "+ Add Contact" to add someone to the circle of influence.
                  </div>
                ) : (
                  circleContacts.map(contact => (
                    <div key={contact.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 12px', backgroundColor: '#f8f9fa', borderRadius: '6px', border: '1px solid #e9ecef' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
                        <span style={{ fontSize: '18px' }}>{getContactIcon(contact.type)}</span>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            {contact.leadId ? (
                              <span
                                onClick={() => navigate(`/leads/${contact.leadId}`)}
                                style={{ fontWeight: '500', color: '#217f8d', cursor: 'pointer', textDecoration: 'none' }}
                                onMouseEnter={e => e.target.style.textDecoration = 'underline'}
                                onMouseLeave={e => e.target.style.textDecoration = 'none'}
                              >
                                {contact.name}
                              </span>
                            ) : (
                              <span style={{ fontWeight: '500' }}>{contact.name}</span>
                            )}
                            <span style={{ fontSize: '12px', padding: '2px 8px', backgroundColor: '#e0f2f1', color: '#00695c', borderRadius: '12px' }}>{contact.type}</span>
                          </div>
                          <div style={{ fontSize: '13px', color: '#666' }}>
                            {contact.email && <span>{contact.email}</span>}
                            {contact.email && contact.phone && <span> • </span>}
                            {contact.phone && <span>{contact.phone}</span>}
                          </div>
                          {contact.notes && <div style={{ fontSize: '12px', color: '#999', fontStyle: 'italic' }}>{contact.notes}</div>}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '4px' }}>
                        <button
                          onClick={() => handleEditCircleContact(contact)}
                          style={{ background: 'none', border: 'none', color: '#217f8d', cursor: 'pointer', fontSize: '14px', padding: '4px 8px' }}
                          title="Edit contact"
                        >
                          ✏️
                        </button>
                        <button
                          onClick={() => handleDeleteCircleContact(contact.id)}
                          style={{ background: 'none', border: 'none', color: '#dc3545', cursor: 'pointer', fontSize: '16px', padding: '4px 8px' }}
                          title="Remove contact"
                        >
                          ×
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* Add Referral Partner Modal */}
              {showCircleModal && (
                <div className="modal-overlay" onClick={() => { setShowCircleModal(false); setShowSearchResults(false); }}>
                  <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '500px' }}>
                    <div className="modal-header">
                      <h3>{circleForm.editId ? 'Edit Referral Partner' : 'Add Referral Partner'}</h3>
                      <button className="modal-close" onClick={() => { setShowCircleModal(false); setShowSearchResults(false); setCircleForm({ name: '', email: '', phone: '', type: 'Co-Borrower', notes: '' }); }}>×</button>
                    </div>
                    <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      <div className="form-group">
                        <label>Contact Type *</label>
                        <select
                          value={circleForm.type}
                          onChange={e => setCircleForm({...circleForm, type: e.target.value})}
                          className="form-control"
                        >
                          {circleContactTypes.map(type => (
                            <option key={type.value} value={type.value}>{type.value}</option>
                          ))}
                        </select>
                      </div>
                      <div className="form-group" style={{ position: 'relative' }}>
                        <label>Name *</label>
                        <input
                          type="text"
                          value={circleForm.name}
                          onChange={handleNameChange}
                          onFocus={() => circleForm.name.length >= 2 && setShowSearchResults(true)}
                          className="form-control"
                          placeholder="Start typing to search..."
                          autoComplete="off"
                        />
                        {searchLoading && (
                          <div style={{ position: 'absolute', right: '10px', top: '35px', color: '#999', fontSize: '12px' }}>
                            Searching...
                          </div>
                        )}
                        {showSearchResults && searchResults.length > 0 && (
                          <div style={{
                            position: 'absolute',
                            top: '100%',
                            left: 0,
                            right: 0,
                            backgroundColor: 'white',
                            border: '1px solid #ddd',
                            borderRadius: '4px',
                            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                            maxHeight: '200px',
                            overflowY: 'auto',
                            zIndex: 1000
                          }}>
                            {searchResults.map(result => (
                              <div
                                key={result.id}
                                onClick={() => selectSearchResult(result)}
                                style={{
                                  padding: '10px 12px',
                                  cursor: 'pointer',
                                  borderBottom: '1px solid #eee',
                                  transition: 'background-color 0.15s'
                                }}
                                onMouseEnter={e => e.target.style.backgroundColor = '#f5f5f5'}
                                onMouseLeave={e => e.target.style.backgroundColor = 'white'}
                              >
                                <div style={{ fontWeight: '500' }}>{result.name}</div>
                                <div style={{ fontSize: '12px', color: '#666' }}>
                                  {result.email && <span>{result.email}</span>}
                                  {result.email && result.phone && <span> • </span>}
                                  {result.phone && <span>{result.phone}</span>}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="form-group">
                        <label>Email</label>
                        <input
                          type="email"
                          value={circleForm.email}
                          onChange={e => setCircleForm({...circleForm, email: e.target.value})}
                          className="form-control"
                          placeholder="Enter email address"
                        />
                      </div>
                      <div className="form-group">
                        <label>Phone</label>
                        <input
                          type="tel"
                          value={circleForm.phone}
                          onChange={e => setCircleForm({...circleForm, phone: e.target.value})}
                          className="form-control"
                          placeholder="Enter phone number"
                        />
                      </div>
                      <div className="form-group">
                        <label>Notes</label>
                        <textarea
                          value={circleForm.notes}
                          onChange={e => setCircleForm({...circleForm, notes: e.target.value})}
                          className="form-control"
                          placeholder="Add any notes about this contact"
                          rows={3}
                        />
                      </div>
                    </div>
                    <div className="modal-footer">
                      <button className="btn-secondary" onClick={() => setShowCircleModal(false)}>Cancel</button>
                      <button
                        className="btn-primary"
                        onClick={handleAddCircleContactSubmit}
                        disabled={!circleForm.name.trim()}
                      >
                        {circleForm.editId ? 'Save Changes' : 'Add Contact'}
                      </button>
                    </div>
                  </div>
                </div>
              )}
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
              <button
                className={`action-btn voice ${isListening ? 'listening' : ''}`}
                onClick={() => handleAction('voice')}
                title="Give voice command to AI assistant"
              >
                <span className="icon">🎤</span>
                <span>{isListening ? 'Listening...' : 'Voice Command'}</span>
              </button>
              <button
                className="action-btn escalation"
                onClick={() => handleAction('escalation')}
                title="Escalate issue to team member"
              >
                <span className="icon">🚨</span>
                <span>Escalation</span>
              </button>
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

      {/* Voicemail Drop */}
      {lead && showVoicemailDrop && (
        <VoicemailDrop
          phoneNumber={lead.phone}
          recipientName={lead.name}
          onClose={() => setShowVoicemailDrop(false)}
        />
      )}

      {/* Escalation Modal */}
      {lead && (
        <EscalationModal
          isOpen={showEscalationModal}
          onClose={() => setShowEscalationModal(false)}
          lead={lead}
        />
      )}

      {/* Create Task Modal */}
      {lead && (
        <CreateTaskModal
          isOpen={showTaskModal}
          onClose={() => setShowTaskModal(false)}
          lead={lead}
        />
      )}

      {/* Appointment Modal */}
      {lead && (
        <AppointmentModal
          isOpen={showAppointmentModal}
          onClose={() => setShowAppointmentModal(false)}
          lead={lead}
        />
      )}
    </div>
  );
}

export default LeadDetail;
