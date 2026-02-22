// VERSION: 2024-11-14-v2 - MOCK DATA FIX
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { mumAPI, activitiesAPI } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import SMSModal from '../components/SMSModal';
import TeamsModal from '../components/TeamsModal';
import RecordingModal from '../components/RecordingModal';
import VoicemailDrop from '../components/VoicemailDrop';
import TeamAssignment from '../components/TeamAssignment';
import EmploymentTab from '../components/EmploymentTab';
import VideoMeetings from '../components/VideoMeetings';
import AppointmentModal from '../components/AppointmentModal';
import ScheduleAppointmentModal from '../components/ScheduleAppointmentModal';
import EmailComposerModal from '../components/EmailComposerModal';
import EscalationModal from '../components/EscalationModal';
import CalendarSidebar from '../components/CalendarSidebar';
import RateMonitorWidget from '../components/RateMonitorWidget';
import './LeadDetail.css';
import { toast } from '../utils/toast';

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

function MumClientDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [client, setClient] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(true); // Always in edit mode
  const [formData, setFormData] = useState({});
  const [emails, setEmails] = useState([]);
  const [activeTab, setActiveTab] = useState('loan-details');
  const [noteText, setNoteText] = useState('');
  const [noteLoading, setNoteLoading] = useState(false);
  const [isFundedLoan, setIsFundedLoan] = useState(false);
  const [loanId, setLoanId] = useState(null);

  // Archive state
  const [archiveSubTab, setArchiveSubTab] = useState('notes'); // 'notes', 'email', 'sms', 'calls'
  const [emailArchive, setEmailArchive] = useState([]);
  const [smsArchive, setSmsArchive] = useState([]);
  const [callArchive, setCallArchive] = useState([]);
  const [archiveLoading, setArchiveLoading] = useState(false);

  // Personal tab sub-tabs state
  const [personalSubTab, setPersonalSubTab] = useState('info'); // 'info', 'employment', 'assets'
  const [propertySubTab, setPropertySubTab] = useState('property'); // 'property', 'insurance', 'legal'

  const [borrowers, setBorrowers] = useState([]);
  const [activeBorrower, setActiveBorrower] = useState(0);
  const [saveTimeout, setSaveTimeout] = useState(null);
  const [showSMSModal, setShowSMSModal] = useState(false);
  const [showTeamsModal, setShowTeamsModal] = useState(false);
  const [showRecordingModal, setShowRecordingModal] = useState(false);
  const [showVoicemailDrop, setShowVoicemailDrop] = useState(false);
  const [showVideoMeetings, setShowVideoMeetings] = useState(false);
  const [showAppointmentModal, setShowAppointmentModal] = useState(false);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [calendarRefreshKey, setCalendarRefreshKey] = useState(0);
  const [showEmailComposer, setShowEmailComposer] = useState(false);
  const [showEscalationModal, setShowEscalationModal] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState('');
  const [customFields, setCustomFields] = useState([]);
  const [showAddFieldModal, setShowAddFieldModal] = useState(false);
  const [newFieldName, setNewFieldName] = useState('');

  // Status dropdown state
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);
  const [statusSaving, setStatusSaving] = useState(false);

  // Client navigation state
  const [clientsList, setClientsList] = useState([]);
  const [currentClientIndex, setCurrentClientIndex] = useState(-1);

  // Status options — all stages across Lead, Active Loan, and MUM
  const statusOptions = [
    { label: 'Lead Stages', isHeader: true },
    'New', 'Attempted Contact', 'Prospect', 'Application',
    'Pre-Qualified', 'Pre-Approved', 'Long-Term Nurture',
    'Withdrawn', 'Does Not Qualify',
    { label: 'Active Loan Stages', isHeader: true },
    'Disclosed', 'Processing', 'Submitted', 'Underwriting',
    'UW Received', 'Conditional Approval', 'Approved', 'Suspended',
    'CTC', 'Clear to Close', 'Closing', 'Docs', 'Docs Out',
    'Cancelled', 'Denied', 'Dead',
    { label: 'MUM / Closed', isHeader: true },
    'Funded',
  ];

  const getStatusColor = (status) => {
    const colors = {
      'New': '#2196F3', 'Attempted Contact': '#FF9800', 'Prospect': '#9C27B0',
      'Application': '#00BCD4', 'Pre-Qualified': '#4CAF50', 'Pre-Approved': '#8BC34A',
      'Long-Term Nurture': '#607D8B', 'Withdrawn': '#F44336', 'Does Not Qualify': '#795548',
      'Disclosed': '#00C853', 'Processing': '#FF9800', 'Submitted': '#FF9800',
      'Underwriting': '#FFC107', 'UW Received': '#FFC107', 'Conditional Approval': '#00BCD4',
      'Approved': '#4CAF50', 'Suspended': '#F44336', 'CTC': '#4CAF50',
      'Clear to Close': '#4CAF50', 'Closing': '#4CAF50', 'Docs': '#4CAF50',
      'Docs Out': '#4CAF50', 'Cancelled': '#F44336', 'Denied': '#F44336',
      'Dead': '#9E9E9E', 'Funded': '#FFD700',
    };
    return colors[status] || '#999';
  };

  const handleStatusChange = async (newStatus) => {
    setShowStatusDropdown(false);
    setStatusSaving(true);
    try {
      await mumAPI.update(id, { stage: newStatus });
      setFormData(prev => ({ ...prev, stage: newStatus }));
      setClient(prev => prev ? { ...prev, stage: newStatus } : prev);
      toast.success(`Status updated to ${newStatus}`);
    } catch (err) {
      console.error('Failed to update status:', err);
      toast.error('Failed to update status');
    } finally {
      setStatusSaving(false);
    }
  };

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

  useEffect(() => {
    loadClientData();
    loadEmails();
    markClientAsViewed();
    loadClientsList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Load clients list for navigation
  const loadClientsList = async () => {
    try {
      let clients = [];
      try {
        const response = await mumAPI.getAll();
        clients = response.clients || response || [];
      } catch (apiError) {
        console.log('API failed, using empty clients list for navigation');
        clients = [];
      }
      setClientsList(clients);

      // Find the current client index in the list
      const currentId = parseInt(id);
      const index = clients.findIndex(c => c.id === currentId);
      setCurrentClientIndex(index);
    } catch (error) {
      console.error('Error loading clients list:', error);
    }
  };

  // Navigate to the next client
  const handleViewNextClient = () => {
    if (clientsList.length === 0) return;

    let nextIndex = currentClientIndex + 1;
    // Loop back to the first client if we're at the end
    if (nextIndex >= clientsList.length) {
      nextIndex = 0;
    }

    const nextClient = clientsList[nextIndex];
    if (nextClient && nextClient.id) {
      navigate(`/portfolio/${nextClient.id}`);
    }
  };

  const markClientAsViewed = () => {
    try {
      // Get viewed leads from localStorage
      const stored = localStorage.getItem('viewedMumClients');
      const viewedMumClients = stored ? new Set(JSON.parse(stored)) : new Set();

      // Add current lead ID
      viewedMumClients.add(String(id));

      // Save back to localStorage
      localStorage.setItem('viewedMumClients', JSON.stringify([...viewedMumClients]));
    } catch (error) {
      console.error('Error marking lead as viewed:', error);
    }
  };

  const loadClientData = async () => {
    try {
      setLoading(true);
      let clientData = null;
      let activitiesData = [];

      // Check if this is a funded loan (ID starts with "loan_")
      if (id && id.toString().startsWith('loan_')) {
        const actualLoanId = id.replace('loan_', '');
        setIsFundedLoan(true);
        setLoanId(actualLoanId);

        // Redirect to loan detail page instead
        console.log('🔄 Redirecting to loan detail page for funded loan:', actualLoanId);
        navigate(`/loans/${actualLoanId}`);
        return;
      }

      try {
        // Try to fetch from API first
        [clientData, activitiesData] = await Promise.all([
          mumAPI.getById(id),
          activitiesAPI.getAll({ mum_client_id: id })
        ]);
        console.log('✅ Loaded lead from API:', clientData);
      } catch (apiError) {
        console.log('⚠️ API failed, using mock data. Error:', apiError);
        // Fallback to mock data
        const mockLeads = generateMockLeads();
        console.log('📦 Generated mock leads, total count:', mockLeads.length);
        console.log('🔍 Looking for lead ID:', id, 'Type:', typeof id);
        clientData = mockLeads.find(lead => client.id === parseInt(id));
        console.log('🎯 Found mock lead:', clientData);

        if (!clientData) {
          console.error('❌ Lead not found in mock data');
          toast.error('Failed to load lead details');
          navigate('/portfolio');
          return;
        }
        activitiesData = [];
      }

      console.log('✨ Setting lead data:', clientData);
      setClient(clientData);
      setFormData(clientData);
      setActivities(activitiesData || []);

      // Initialize borrowers array
      const primaryName = clientData.first_name && clientData.last_name
        ? `${clientData.first_name} ${clientData.last_name}`
        : clientData.name || 'Primary Borrower';

      const borrowersList = [
        {
          id: 0,
          name: primaryName,
          type: 'primary',
          data: clientData
        }
      ];

      // Add co-borrower if exists
      if (clientData.co_applicant_name) {
        const coborrowerName = String(clientData.co_applicant_name || '');
        const nameParts = coborrowerName.split(' ');
        borrowersList.push({
          id: 1,
          name: clientData.co_applicant_name,
          type: 'co-borrower',
          data: {
            name: clientData.co_applicant_name,
            first_name: nameParts[0] || '',
            last_name: nameParts.slice(1).join(' ') || '',
            email: clientData.co_applicant_email || '',
            phone: clientData.co_applicant_phone || '',
          }
        });
      }

      setBorrowers(borrowersList);
    } catch (error) {
      console.error('Failed to load lead data:', error);
      toast.error('Failed to load lead details');
      navigate('/mum');
    } finally {
      setLoading(false);
    }
  };

  const loadEmails = async () => {
    try {
      const emailActivities = await activitiesAPI.getAll({
        mum_client_id: id,
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

      await mumAPI.update(id, dataToSave);

      // Reload the lead data to sync with backend
      const updatedLead = await mumAPI.getById(id);
      setClient(updatedLead);

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
      toast.success('Lead updated successfully!');
    } catch (error) {
      console.error('Failed to update lead:', error);
      toast.error('Failed to update lead');
    }
  };

  const handleCancel = () => {
    // Restore the correct borrower's data based on active borrower
    if (activeBorrower < borrowers.length) {
      setFormData(borrowers[activeBorrower].data);
    } else {
      setFormData(client);
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

      await mumAPI.update(id, dataToSave);
      console.log(`Field ${fieldName} saved successfully`);

      // Reload to sync with backend
      const updatedLead = await mumAPI.getById(id);
      setClient(updatedLead);
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
        mum_client_id: parseInt(id)
      };
      console.log('Creating note with data:', noteData);

      const result = await activitiesAPI.create(noteData);
      console.log('Note created successfully:', result);

      setNoteText('');
      loadClientData();
    } catch (error) {
      console.error('Failed to add note:', error);
      console.error('Error response:', error.response?.data);
      const errorMsg = error.response?.data?.detail || 'Failed to add note. Please check console for details.';
      toast.error(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
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
        await mumAPI.update(id, {
          co_applicant_name: fullName
        });

        // Reload lead data to sync with backend
        const clientData = await mumAPI.getById(id);
        setClient(clientData);

        // Rebuild borrowers array with the new co-borrower
        const primaryName = clientData.first_name && clientData.last_name
          ? `${clientData.first_name} ${clientData.last_name}`
          : clientData.name || 'Primary Borrower';

        const updatedBorrowers = [
          {
            id: 0,
            name: primaryName,
            type: 'primary',
            data: clientData
          }
        ];

        if (clientData.co_applicant_name) {
          const coborrowerParts = (clientData.co_applicant_name || '').split(' ');
          updatedBorrowers.push({
            id: 1,
            name: clientData.co_applicant_name,
            type: 'co-borrower',
            data: {
              name: clientData.co_applicant_name,
              first_name: coborrowerParts[0] || '',
              last_name: coborrowerParts.slice(1).join(' ') || '',
              email: clientData.co_applicant_email || '',
              phone: clientData.co_applicant_phone || '',
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

      toast.success(`${fullName} has been added successfully!`);
    } catch (error) {
      console.error('Failed to add borrower:', error);
      console.error('Error response:', error.response?.data);
      const errorMsg = error.response?.data?.detail || error.message || 'Failed to add borrower. Please check console for details.';
      toast.error(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
    }
  };

  const handleVoiceCommand = () => {
    // Check if browser supports Web Speech API
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      toast.error('Sorry, your browser does not support speech recognition. Please try Chrome or Edge.');
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
        detail: { transcript, leadId: client.id }
      }));
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
      if (event.error === 'no-speech') {
        toast.error('No speech detected. Please try again.');
      } else {
        toast.error(`Error occurred: ${event.error}`);
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
        window.open(`tel:${client.phone}`, '_self');
        break;
      case 'sms':
        setShowSMSModal(true);
        break;
      case 'email':
        setShowEmailComposer(true);
        break;
      case 'task':
        navigate('/tasks');
        break;
      case 'calendar':
        setShowScheduleModal(true);
        break;
      case 'teams':
        setShowTeamsModal(true);
        break;
      case 'video':
        setShowVideoMeetings(true);
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
      case 'send_application':
        // For MUM clients, typically for refinance applications
        if (client.email) {
          const appUrl = `${window.location.origin}/apply/refinance`;
          window.open(appUrl, '_blank');
        } else {
          toast.error('Client email is required to send application');
        }
        break;
      case 'client_portal':
        // Open or create client portal for this MUM client
        try {
          const portalData = await mumAPI.getOrCreatePortal(client.id);
          if (portalData.portal_url) {
            window.open(portalData.portal_url, '_blank');
          } else if (portalData.slug) {
            // Uses /portal/ route which auto-routes to MUMPortal based on workspace status
            window.open(`${window.location.origin}/portal/${portalData.slug}`, '_blank');
          }
        } catch (error) {
          console.error('Failed to open client portal:', error);
          toast.error('Failed to open client portal. Please try again.');
        }
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

  if (!client) {
    return (
      <div className="lead-detail-page">
        <div className="error">Lead not found</div>
      </div>
    );
  }

  return (
    <div className="lead-detail-page-wrapper">
      <div className="lead-detail-page">
        {/* Header */}
        <div className="detail-header">
          <div className="nav-buttons">
            <button className="btn-back" onClick={() => navigate('/portfolio')}>
              ← Back to Portfolio
            </button>
          <button
            className="btn-next"
            onClick={handleViewNextClient}
            disabled={clientsList.length === 0}
          >
            View Next Client →
          </button>
        </div>
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

      {/* Client Name Banner */}
      <div className="client-name-banner" style={{
        padding: '12px 24px',
        backgroundColor: '#f8fafc',
        borderBottom: '1px solid #e2e8f0',
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
      }}>
        <h2 style={{
          margin: 0,
          fontSize: '20px',
          fontWeight: '600',
          color: '#1a1a2e'
        }}>
          {formData.first_name || formData.last_name
            ? `${formData.first_name || ''} ${formData.last_name || ''}`.trim()
            : client?.first_name || client?.last_name
              ? `${client?.first_name || ''} ${client?.last_name || ''}`.trim()
              : client?.name || 'Unknown Client'}
        </h2>

        {/* Status Dropdown */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setShowStatusDropdown(!showStatusDropdown)}
            disabled={statusSaving}
            style={{
              backgroundColor: getStatusColor(formData.stage || client?.stage || 'Funded'),
              color: 'white',
              border: 'none',
              padding: '6px 16px',
              borderRadius: '16px',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '13px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            {statusSaving ? 'Saving...' : (formData.stage || client?.stage || 'Funded')}
            <span style={{ fontSize: '10px' }}>▼</span>
          </button>

          {showStatusDropdown && (
            <>
              <div
                onClick={() => setShowStatusDropdown(false)}
                style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 999 }}
              />
              <div style={{
                position: 'absolute',
                top: '100%',
                left: 0,
                backgroundColor: 'white',
                borderRadius: '8px',
                boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
                zIndex: 1000,
                minWidth: '200px',
                marginTop: '4px',
                maxHeight: '400px',
                overflowY: 'auto',
              }}>
                {statusOptions.map((status, idx) => (
                  status.isHeader ? (
                    <div
                      key={status.label}
                      style={{
                        padding: '8px 16px',
                        fontSize: '11px',
                        fontWeight: 600,
                        textTransform: 'uppercase',
                        color: '#6b7280',
                        borderTop: idx > 0 ? '1px solid #e5e7eb' : 'none',
                        marginTop: idx > 0 ? '4px' : 0,
                        letterSpacing: '0.05em',
                        background: '#fafafa',
                      }}
                    >
                      {status.label}
                    </div>
                  ) : (
                    <button
                      key={status}
                      onClick={() => handleStatusChange(status)}
                      style={{
                        display: 'block',
                        width: '100%',
                        padding: '10px 16px',
                        border: 'none',
                        background: (formData.stage || client?.stage) === status ? '#f0f0f0' : 'white',
                        cursor: 'pointer',
                        textAlign: 'left',
                        fontSize: '13px',
                        borderLeft: `4px solid ${getStatusColor(status)}`,
                        transition: 'background 0.2s',
                      }}
                      onMouseEnter={(e) => e.target.style.background = '#f5f5f5'}
                      onMouseLeave={(e) => e.target.style.background = (formData.stage || client?.stage) === status ? '#f0f0f0' : 'white'}
                    >
                      {status}
                    </button>
                  )
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="profile-tabs">
        <button
          className={`tab-btn ${activeTab === 'loan-details' ? 'active' : ''}`}
          onClick={() => setActiveTab('loan-details')}
        >
          Loan Details
        </button>
        <button
          className={`tab-btn ${activeTab === 'personal' ? 'active' : ''}`}
          onClick={() => setActiveTab('personal')}
        >
          Personal
        </button>
        <button
          className={`tab-btn ${activeTab === 'loan' ? 'active' : ''}`}
          onClick={() => setActiveTab('loan')}
        >
          Property
        </button>
        <button
          className={`tab-btn ${activeTab === 'tasks' ? 'active' : ''}`}
          onClick={() => setActiveTab('tasks')}
        >
          Tasks
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
          Conditions
        </button>
        <button
          className={`tab-btn ${activeTab === 'important-dates' ? 'active' : ''}`}
          onClick={() => setActiveTab('important-dates')}
        >
          SLA Dates
        </button>
        <button
          className={`tab-btn ${activeTab === 'rate-monitor' ? 'active' : ''}`}
          onClick={() => setActiveTab('rate-monitor')}
        >
          Rate Monitor
        </button>
        <button
          className={`tab-btn ${activeTab === 'team' ? 'active' : ''}`}
          onClick={() => setActiveTab('team')}
        >
          Team Members
        </button>
      </div>

      <div className="detail-content">
        {/* Left Column - Lead Information */}
        <div className="left-column">
          {/* Loan Details Tab */}
          {activeTab === 'loan-details' && (
          <div className="info-section">
            <h2>Loan Details</h2>

            {/* Transaction Type Toggle */}
            <div className="transaction-type-toggle" style={{ marginBottom: '1.5rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '600', color: '#374151' }}>Transaction Type</label>
              <div style={{ display: 'flex', gap: '0', borderRadius: '8px', overflow: 'hidden', border: '1px solid #d1d5db', width: 'fit-content' }}>
                <button
                  type="button"
                  onClick={() => handleFieldChange('loan_purpose', 'Purchase')}
                  style={{
                    padding: '0.75rem 1.5rem',
                    border: 'none',
                    background: (formData.loan_purpose === 'Purchase' || !formData.loan_purpose) ? '#3b82f6' : '#f3f4f6',
                    color: (formData.loan_purpose === 'Purchase' || !formData.loan_purpose) ? 'white' : '#374151',
                    fontWeight: '600',
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                >
                  Purchase
                </button>
                <button
                  type="button"
                  onClick={() => handleFieldChange('loan_purpose', 'Refinance')}
                  style={{
                    padding: '0.75rem 1.5rem',
                    border: 'none',
                    borderLeft: '1px solid #d1d5db',
                    background: formData.loan_purpose === 'Refinance' ? '#3b82f6' : '#f3f4f6',
                    color: formData.loan_purpose === 'Refinance' ? 'white' : '#374151',
                    fontWeight: '600',
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                >
                  Refinance
                </button>
              </div>
            </div>

            <div className="info-grid">
              <div className="info-field">
                <label>Loan Number</label>
                <input
                  type="text"
                  value={formData.loan_number || ''}
                  onChange={(e) => handleFieldChange('loan_number', e.target.value)}
                  placeholder="Enter loan number"
                />
              </div>

              {/* Purchase Price - only show for Purchase transactions */}
              {(formData.loan_purpose === 'Purchase' || !formData.loan_purpose) && (
                <div className="info-field">
                  <label>Purchase Price</label>
                  <input
                    type="number"
                    value={formData.purchase_price || ''}
                    onChange={(e) => handleFieldChange('purchase_price', e.target.value)}
                    placeholder="$"
                  />
                </div>
              )}

              <div className="info-field">
                <label>Loan Amount</label>
                <input
                  type="number"
                  value={formData.loan_amount || ''}
                  onChange={(e) => handleFieldChange('loan_amount', e.target.value)}
                  placeholder="$"
                />
              </div>

              <div className="info-field">
                <label>Interest Rate</label>
                <input
                  type="number"
                  step="0.001"
                  value={formData.interest_rate || ''}
                  onChange={(e) => handleFieldChange('interest_rate', e.target.value)}
                  placeholder="%"
                />
              </div>

              <div className="info-field">
                <label>Loan Term</label>
                <input
                  type="number"
                  value={formData.loan_term || ''}
                  onChange={(e) => handleFieldChange('loan_term', e.target.value)}
                  placeholder="Months"
                />
              </div>

              <div className="info-field">
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

              <div className="info-field">
                <label>Lock Date</label>
                <input
                  type="date"
                  value={formData.lock_date || ''}
                  onChange={(e) => handleFieldChange('lock_date', e.target.value)}
                />
              </div>

              <div className="info-field">
                <label>Lock Expiration</label>
                <input
                  type="date"
                  value={formData.lock_expiration || ''}
                  onChange={(e) => handleFieldChange('lock_expiration', e.target.value)}
                />
              </div>

              <div className="info-field">
                <label>APR</label>
                <input
                  type="number"
                  step="0.001"
                  value={formData.apr || ''}
                  onChange={(e) => handleFieldChange('apr', e.target.value)}
                  placeholder="%"
                />
              </div>

              <div className="info-field">
                <label>Points</label>
                <input
                  type="number"
                  step="0.125"
                  value={formData.points || ''}
                  onChange={(e) => handleFieldChange('points', e.target.value)}
                />
              </div>

              <div className="info-field">
                <label>Closing Date</label>
                <input
                  type="date"
                  value={formData.closing_date || ''}
                  onChange={(e) => handleFieldChange('closing_date', e.target.value)}
                />
              </div>

              <div className="info-field">
                <label>Appraisal Value</label>
                <input
                  type="number"
                  value={formData.appraisal_value || ''}
                  onChange={(e) => handleFieldChange('appraisal_value', e.target.value)}
                  placeholder="$"
                />
              </div>

              <div className="info-field">
                <label>LTV %</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.ltv || ''}
                  onChange={(e) => handleFieldChange('ltv', e.target.value)}
                  placeholder="%"
                />
              </div>

              <div className="info-field">
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
          )}

          {/* Personal Information Tab */}
          {activeTab === 'personal' && (
          <div className="info-section">
            {/* Borrower Selector - moved inside Personal Information */}
            <div className="borrower-selector" style={{ marginBottom: '1.5rem' }}>
              <div className="borrower-buttons-group">
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
              </div>
              <button className="borrower-add-btn" onClick={handleAddBorrower} title="Add Borrower">
                + Add Person
              </button>
            </div>

            {/* Sub-tabs for Personal Information, Employment, and Assets */}
            <div style={{ display: 'flex', gap: '0', marginBottom: '1.5rem', borderBottom: '1px solid #e0e0e0' }}>
              <button
                onClick={() => setPersonalSubTab('info')}
                style={{
                  padding: '10px 20px',
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: personalSubTab === 'info' ? '600' : '400',
                  color: personalSubTab === 'info' ? '#1a73e8' : '#5f6368',
                  borderBottom: personalSubTab === 'info' ? '2px solid #1a73e8' : '2px solid transparent',
                  marginBottom: '-1px'
                }}
              >
                Personal Information
              </button>
              <button
                onClick={() => setPersonalSubTab('employment')}
                style={{
                  padding: '10px 20px',
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: personalSubTab === 'employment' ? '600' : '400',
                  color: personalSubTab === 'employment' ? '#1a73e8' : '#5f6368',
                  borderBottom: personalSubTab === 'employment' ? '2px solid #1a73e8' : '2px solid transparent',
                  marginBottom: '-1px'
                }}
              >
                Employment
              </button>
              <button
                onClick={() => setPersonalSubTab('assets')}
                style={{
                  padding: '10px 20px',
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: personalSubTab === 'assets' ? '600' : '400',
                  color: personalSubTab === 'assets' ? '#1a73e8' : '#5f6368',
                  borderBottom: personalSubTab === 'assets' ? '2px solid #1a73e8' : '2px solid transparent',
                  marginBottom: '-1px'
                }}
              >
                Assets
              </button>
            </div>

            {/* Personal Information Sub-tab Content */}
            {personalSubTab === 'info' && (
            <>
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
              <div className="info-field">
                <label>Preferred Communication</label>
                <select
                  value={formData.preferred_communication || ''}
                  onChange={(e) => handleFieldChange('preferred_communication', e.target.value)}
                  style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ddd', fontSize: '14px' }}
                >
                  <option value="">-- Select Preference --</option>
                  <option value="email">Email</option>
                  <option value="phone">Phone Call</option>
                  <option value="text">Text Message</option>
                  <option value="voicemail">Voicemail</option>
                </select>
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
            </>
            )}

            {/* Employment Sub-tab Content */}
            {personalSubTab === 'employment' && (
              <EmploymentTab
                leadId={id}
                formData={formData}
                onFieldChange={handleFieldChange}
                entityType="mum"
              />
            )}

            {/* Assets Sub-tab Content */}
            {personalSubTab === 'assets' && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <h2 style={{ margin: 0 }}>Assets</h2>
                </div>

                {/* Bank Accounts Section */}
                <div style={{ marginBottom: '2rem' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Bank Accounts</h3>
                  <div className="info-grid compact">
                    <div className="info-field">
                      <label>Checking Account Balance</label>
                      <input
                        type="text"
                        value={formData.checking_balance || ''}
                        onChange={(e) => handleFieldChange('checking_balance', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>Savings Account Balance</label>
                      <input
                        type="text"
                        value={formData.savings_balance || ''}
                        onChange={(e) => handleFieldChange('savings_balance', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>Money Market Balance</label>
                      <input
                        type="text"
                        value={formData.money_market_balance || ''}
                        onChange={(e) => handleFieldChange('money_market_balance', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>CD Balance</label>
                      <input
                        type="text"
                        value={formData.cd_balance || ''}
                        onChange={(e) => handleFieldChange('cd_balance', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                  </div>
                </div>

                {/* Investment Accounts Section */}
                <div style={{ marginBottom: '2rem' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Investment Accounts</h3>
                  <div className="info-grid compact">
                    <div className="info-field">
                      <label>Stocks/Bonds Value</label>
                      <input
                        type="text"
                        value={formData.stocks_bonds_value || ''}
                        onChange={(e) => handleFieldChange('stocks_bonds_value', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>Mutual Funds Value</label>
                      <input
                        type="text"
                        value={formData.mutual_funds_value || ''}
                        onChange={(e) => handleFieldChange('mutual_funds_value', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>Brokerage Account Value</label>
                      <input
                        type="text"
                        value={formData.brokerage_value || ''}
                        onChange={(e) => handleFieldChange('brokerage_value', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                  </div>
                </div>

                {/* Retirement Accounts Section */}
                <div style={{ marginBottom: '2rem' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Retirement Accounts</h3>
                  <div className="info-grid compact">
                    <div className="info-field">
                      <label>401(k) Balance</label>
                      <input
                        type="text"
                        value={formData.retirement_401k || ''}
                        onChange={(e) => handleFieldChange('retirement_401k', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>IRA Balance</label>
                      <input
                        type="text"
                        value={formData.ira_balance || ''}
                        onChange={(e) => handleFieldChange('ira_balance', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>Roth IRA Balance</label>
                      <input
                        type="text"
                        value={formData.roth_ira_balance || ''}
                        onChange={(e) => handleFieldChange('roth_ira_balance', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>Pension Value</label>
                      <input
                        type="text"
                        value={formData.pension_value || ''}
                        onChange={(e) => handleFieldChange('pension_value', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                  </div>
                </div>

                {/* Other Assets Section */}
                <div style={{ marginBottom: '2rem' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Other Assets</h3>
                  <div className="info-grid compact">
                    <div className="info-field">
                      <label>Real Estate Value</label>
                      <input
                        type="text"
                        value={formData.real_estate_value || ''}
                        onChange={(e) => handleFieldChange('real_estate_value', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>Vehicle Value</label>
                      <input
                        type="text"
                        value={formData.vehicle_value || ''}
                        onChange={(e) => handleFieldChange('vehicle_value', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>Business Value</label>
                      <input
                        type="text"
                        value={formData.business_value || ''}
                        onChange={(e) => handleFieldChange('business_value', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>Other Assets</label>
                      <input
                        type="text"
                        value={formData.other_assets_value || ''}
                        onChange={(e) => handleFieldChange('other_assets_value', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
          )}

          {/* Property Tab with Sub-tabs */}
          {activeTab === 'loan' && (
          <div className="info-section">
            {/* Sub-tabs for Property, Insurance, and Legal */}
            <div style={{ display: 'flex', gap: '0', marginBottom: '1.5rem', borderBottom: '1px solid #e0e0e0' }}>
              <button
                onClick={() => setPropertySubTab('property')}
                style={{
                  padding: '10px 20px',
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: propertySubTab === 'property' ? '600' : '400',
                  color: propertySubTab === 'property' ? '#1a73e8' : '#5f6368',
                  borderBottom: propertySubTab === 'property' ? '2px solid #1a73e8' : '2px solid transparent',
                  marginBottom: '-1px'
                }}
              >
                Property
              </button>
              <button
                onClick={() => setPropertySubTab('insurance')}
                style={{
                  padding: '10px 20px',
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: propertySubTab === 'insurance' ? '600' : '400',
                  color: propertySubTab === 'insurance' ? '#1a73e8' : '#5f6368',
                  borderBottom: propertySubTab === 'insurance' ? '2px solid #1a73e8' : '2px solid transparent',
                  marginBottom: '-1px'
                }}
              >
                Insurance
              </button>
              <button
                onClick={() => setPropertySubTab('legal')}
                style={{
                  padding: '10px 20px',
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: propertySubTab === 'legal' ? '600' : '400',
                  color: propertySubTab === 'legal' ? '#1a73e8' : '#5f6368',
                  borderBottom: propertySubTab === 'legal' ? '2px solid #1a73e8' : '2px solid transparent',
                  marginBottom: '-1px'
                }}
              >
                Legal
              </button>
            </div>

            {/* Property Sub-tab Content */}
            {propertySubTab === 'property' && (
              <>
                <h2 style={{ margin: '0 0 1rem 0' }}>Property</h2>
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
              </>
            )}

            {/* Insurance Sub-tab Content */}
            {propertySubTab === 'insurance' && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <h2 style={{ margin: 0 }}>Insurance</h2>
                </div>

                {/* Homeowner's Insurance Section */}
                <div style={{ marginBottom: '2rem' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Homeowner's Insurance</h3>
                  <div className="info-grid compact">
                    <div className="info-field">
                      <label>Insurance Company</label>
                      <input
                        type="text"
                        value={formData.homeowner_insurance_company || ''}
                        onChange={(e) => handleFieldChange('homeowner_insurance_company', e.target.value)}
                        placeholder="Company name"
                      />
                    </div>
                    <div className="info-field">
                      <label>Agent Name</label>
                      <input
                        type="text"
                        value={formData.homeowner_insurance_agent || ''}
                        onChange={(e) => handleFieldChange('homeowner_insurance_agent', e.target.value)}
                        placeholder="Agent name"
                      />
                    </div>
                    <div className="info-field">
                      <label>Agent Phone</label>
                      <input
                        type="tel"
                        value={formData.homeowner_insurance_phone || ''}
                        onChange={(e) => handleFieldChange('homeowner_insurance_phone', e.target.value)}
                        placeholder="(555) 555-5555"
                      />
                    </div>
                    <div className="info-field">
                      <label>Agent Email</label>
                      <input
                        type="email"
                        value={formData.homeowner_insurance_email || ''}
                        onChange={(e) => handleFieldChange('homeowner_insurance_email', e.target.value)}
                        placeholder="agent@insurance.com"
                      />
                    </div>
                    <div className="info-field">
                      <label>Policy Number</label>
                      <input
                        type="text"
                        value={formData.homeowner_insurance_policy || ''}
                        onChange={(e) => handleFieldChange('homeowner_insurance_policy', e.target.value)}
                        placeholder="Policy number"
                      />
                    </div>
                    <div className="info-field">
                      <label>Annual Premium</label>
                      <input
                        type="text"
                        value={formData.homeowner_insurance_premium || ''}
                        onChange={(e) => handleFieldChange('homeowner_insurance_premium', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>Coverage Amount</label>
                      <input
                        type="text"
                        value={formData.homeowner_insurance_coverage || ''}
                        onChange={(e) => handleFieldChange('homeowner_insurance_coverage', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>Effective Date</label>
                      <input
                        type="date"
                        value={formData.homeowner_insurance_effective_date || ''}
                        onChange={(e) => handleFieldChange('homeowner_insurance_effective_date', e.target.value)}
                      />
                    </div>
                  </div>
                </div>

                {/* Flood Insurance Section */}
                <div style={{ marginBottom: '2rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                    <h3 style={{ fontSize: '16px', fontWeight: '600', margin: 0, color: '#333' }}>Flood Insurance</h3>
                    {!formData.has_flood_insurance && (
                      <button
                        onClick={() => handleFieldChange('has_flood_insurance', true)}
                        style={{
                          background: '#1a73e8',
                          color: 'white',
                          border: 'none',
                          borderRadius: '6px',
                          padding: '8px 16px',
                          fontSize: '13px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px'
                        }}
                      >
                        + Add Flood Insurance
                      </button>
                    )}
                  </div>

                  {formData.has_flood_insurance ? (
                    <div className="info-grid compact">
                      <div className="info-field">
                        <label>Insurance Company</label>
                        <input
                          type="text"
                          value={formData.flood_insurance_company || ''}
                          onChange={(e) => handleFieldChange('flood_insurance_company', e.target.value)}
                          placeholder="Company name"
                        />
                      </div>
                      <div className="info-field">
                        <label>Agent Name</label>
                        <input
                          type="text"
                          value={formData.flood_insurance_agent || ''}
                          onChange={(e) => handleFieldChange('flood_insurance_agent', e.target.value)}
                          placeholder="Agent name"
                        />
                      </div>
                      <div className="info-field">
                        <label>Agent Phone</label>
                        <input
                          type="tel"
                          value={formData.flood_insurance_phone || ''}
                          onChange={(e) => handleFieldChange('flood_insurance_phone', e.target.value)}
                          placeholder="(555) 555-5555"
                        />
                      </div>
                      <div className="info-field">
                        <label>Agent Email</label>
                        <input
                          type="email"
                          value={formData.flood_insurance_email || ''}
                          onChange={(e) => handleFieldChange('flood_insurance_email', e.target.value)}
                          placeholder="agent@insurance.com"
                        />
                      </div>
                      <div className="info-field">
                        <label>Policy Number</label>
                        <input
                          type="text"
                          value={formData.flood_insurance_policy || ''}
                          onChange={(e) => handleFieldChange('flood_insurance_policy', e.target.value)}
                          placeholder="Policy number"
                        />
                      </div>
                      <div className="info-field">
                        <label>Annual Premium</label>
                        <input
                          type="text"
                          value={formData.flood_insurance_premium || ''}
                          onChange={(e) => handleFieldChange('flood_insurance_premium', e.target.value)}
                          placeholder="$0.00"
                        />
                      </div>
                      <div className="info-field">
                        <label>Coverage Amount</label>
                        <input
                          type="text"
                          value={formData.flood_insurance_coverage || ''}
                          onChange={(e) => handleFieldChange('flood_insurance_coverage', e.target.value)}
                          placeholder="$0.00"
                        />
                      </div>
                      <div className="info-field">
                        <label>Flood Zone</label>
                        <select
                          value={formData.flood_zone || ''}
                          onChange={(e) => handleFieldChange('flood_zone', e.target.value)}
                          style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ddd', fontSize: '14px' }}
                        >
                          <option value="">-- Select Zone --</option>
                          <option value="A">Zone A (High Risk)</option>
                          <option value="AE">Zone AE (High Risk)</option>
                          <option value="AH">Zone AH (High Risk)</option>
                          <option value="AO">Zone AO (High Risk)</option>
                          <option value="V">Zone V (Coastal High Risk)</option>
                          <option value="VE">Zone VE (Coastal High Risk)</option>
                          <option value="X">Zone X (Moderate/Low Risk)</option>
                          <option value="B">Zone B (Moderate Risk)</option>
                          <option value="C">Zone C (Low Risk)</option>
                        </select>
                      </div>
                      <div className="info-field" style={{ gridColumn: 'span 2' }}>
                        <button
                          onClick={() => handleFieldChange('has_flood_insurance', false)}
                          style={{
                            background: 'none',
                            color: '#dc3545',
                            border: '1px solid #dc3545',
                            borderRadius: '6px',
                            padding: '8px 16px',
                            fontSize: '13px',
                            cursor: 'pointer',
                            marginTop: '8px'
                          }}
                        >
                          Remove Flood Insurance
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div style={{
                      background: '#f8f9fa',
                      padding: '1.5rem',
                      borderRadius: '8px',
                      textAlign: 'center',
                      color: '#666'
                    }}>
                      <p style={{ margin: 0 }}>No flood insurance added. Click "Add Flood Insurance" if required.</p>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* Legal Sub-tab Content */}
            {propertySubTab === 'legal' && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <h2 style={{ margin: 0 }}>Legal</h2>
                </div>

                {/* Title Company / Closing Attorney Section */}
                <div style={{ marginBottom: '2rem' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Title Company / Closing Attorney</h3>
                  <div className="info-grid compact">
                    <div className="info-field">
                      <label>Company/Firm Type</label>
                      <select
                        value={formData.closing_entity_type || ''}
                        onChange={(e) => handleFieldChange('closing_entity_type', e.target.value)}
                        style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ddd', fontSize: '14px' }}
                      >
                        <option value="">-- Select Type --</option>
                        <option value="title_company">Title Company</option>
                        <option value="closing_attorney">Closing Attorney</option>
                      </select>
                    </div>
                    <div className="info-field">
                      <label>Company/Firm Name</label>
                      <input
                        type="text"
                        value={formData.closing_company_name || ''}
                        onChange={(e) => handleFieldChange('closing_company_name', e.target.value)}
                        placeholder="Company or firm name"
                      />
                    </div>
                    <div className="info-field">
                      <label>Contact Name</label>
                      <input
                        type="text"
                        value={formData.closing_contact_name || ''}
                        onChange={(e) => handleFieldChange('closing_contact_name', e.target.value)}
                        placeholder="Primary contact name"
                      />
                    </div>
                    <div className="info-field">
                      <label>Phone</label>
                      <input
                        type="tel"
                        value={formData.closing_phone || ''}
                        onChange={(e) => handleFieldChange('closing_phone', e.target.value)}
                        placeholder="(555) 555-5555"
                      />
                    </div>
                    <div className="info-field">
                      <label>Email</label>
                      <input
                        type="email"
                        value={formData.closing_email || ''}
                        onChange={(e) => handleFieldChange('closing_email', e.target.value)}
                        placeholder="contact@company.com"
                      />
                    </div>
                    <div className="info-field">
                      <label>Fax</label>
                      <input
                        type="tel"
                        value={formData.closing_fax || ''}
                        onChange={(e) => handleFieldChange('closing_fax', e.target.value)}
                        placeholder="(555) 555-5555"
                      />
                    </div>
                  </div>
                </div>

                {/* Address Section */}
                <div style={{ marginBottom: '2rem' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Address</h3>
                  <div className="info-grid compact">
                    <div className="info-field" style={{ gridColumn: 'span 2' }}>
                      <label>Street Address</label>
                      <input
                        type="text"
                        value={formData.closing_address || ''}
                        onChange={(e) => handleFieldChange('closing_address', e.target.value)}
                        placeholder="Street address"
                      />
                    </div>
                    <div className="info-field">
                      <label>City</label>
                      <input
                        type="text"
                        value={formData.closing_city || ''}
                        onChange={(e) => handleFieldChange('closing_city', e.target.value)}
                        placeholder="City"
                      />
                    </div>
                    <div className="info-field">
                      <label>State</label>
                      <input
                        type="text"
                        value={formData.closing_state || ''}
                        onChange={(e) => handleFieldChange('closing_state', e.target.value)}
                        placeholder="State"
                      />
                    </div>
                    <div className="info-field">
                      <label>Zip Code</label>
                      <input
                        type="text"
                        value={formData.closing_zip || ''}
                        onChange={(e) => handleFieldChange('closing_zip', e.target.value)}
                        placeholder="Zip code"
                      />
                    </div>
                  </div>
                </div>

                {/* Title/Closing Details Section */}
                <div style={{ marginBottom: '2rem' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Title & Closing Details</h3>
                  <div className="info-grid compact">
                    <div className="info-field">
                      <label>Title Order Number</label>
                      <input
                        type="text"
                        value={formData.title_order_number || ''}
                        onChange={(e) => handleFieldChange('title_order_number', e.target.value)}
                        placeholder="Order number"
                      />
                    </div>
                    <div className="info-field">
                      <label>Title Order Date</label>
                      <input
                        type="date"
                        value={formData.title_order_date || ''}
                        onChange={(e) => handleFieldChange('title_order_date', e.target.value)}
                      />
                    </div>
                    <div className="info-field">
                      <label>Preliminary Title Received</label>
                      <input
                        type="date"
                        value={formData.preliminary_title_date || ''}
                        onChange={(e) => handleFieldChange('preliminary_title_date', e.target.value)}
                      />
                    </div>
                    <div className="info-field">
                      <label>Closing Scheduled</label>
                      <input
                        type="datetime-local"
                        value={formData.closing_scheduled || ''}
                        onChange={(e) => handleFieldChange('closing_scheduled', e.target.value)}
                      />
                    </div>
                    <div className="info-field" style={{ gridColumn: 'span 2' }}>
                      <label>Notes</label>
                      <textarea
                        value={formData.closing_notes || ''}
                        onChange={(e) => handleFieldChange('closing_notes', e.target.value)}
                        placeholder="Additional notes about title or closing..."
                        style={{
                          padding: '10px',
                          borderRadius: '6px',
                          border: '1px solid #ddd',
                          fontSize: '14px',
                          minHeight: '80px',
                          resize: 'vertical'
                        }}
                      />
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
          )}

          {/* Rate Monitor Tab */}
          {activeTab === 'rate-monitor' && (
          <div className="info-section">
            <h2>Rate Monitor</h2>
            <p className="section-description">Track refinance opportunities for this client. Set rate targets and get notified when market rates hit your thresholds.</p>
            <RateMonitorWidget mumClientId={id} />
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
                View and manage marketing campaigns, drip sequences, and promotional content for this client.
              </p>

              <div className="marketing-campaigns" style={{ marginBottom: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 style={{ margin: 0 }}>Active Campaigns</h3>
                  <button className="btn-primary" style={{ padding: '8px 16px', fontSize: '14px' }}>
                    + Add to Campaign
                  </button>
                </div>
                <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px', textAlign: 'center', color: '#666' }}>
                  No active campaigns. Add this client to a marketing campaign to start automated outreach.
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
                  View all email communications with this client.
                </p>
                <button
                  className="btn-primary"
                  style={{ padding: '8px 16px', fontSize: '14px' }}
                  onClick={() => client?.email && window.open(`mailto:${client.email}`, '_blank')}
                  disabled={!client?.email}
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

            {/* Archive Sub-tabs */}
            <div className="archive-sub-tabs">
              <button
                className={`archive-sub-tab ${archiveSubTab === 'notes' ? 'active' : ''}`}
                onClick={() => setArchiveSubTab('notes')}
              >
                Notes
              </button>
              <button
                className={`archive-sub-tab ${archiveSubTab === 'email' ? 'active' : ''}`}
                onClick={() => setArchiveSubTab('email')}
              >
                Email Archive
              </button>
              <button
                className={`archive-sub-tab ${archiveSubTab === 'sms' ? 'active' : ''}`}
                onClick={() => setArchiveSubTab('sms')}
              >
                SMS Archive
              </button>
              <button
                className={`archive-sub-tab ${archiveSubTab === 'calls' ? 'active' : ''}`}
                onClick={() => setArchiveSubTab('calls')}
              >
                Recorded Calls
              </button>
            </div>

            {/* Notes Sub-tab */}
            {archiveSubTab === 'notes' && (
              <>
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
              </>
            )}

            {/* Email Archive Sub-tab */}
            {archiveSubTab === 'email' && (
              <div className="archive-section">
                {archiveLoading ? (
                  <div className="loading-state">Loading email archive...</div>
                ) : emailArchive.length > 0 ? (
                  <div className="email-archive-list">
                    {emailArchive.map((email) => (
                      <div key={email.id} className="email-archive-item">
                        <div className="email-archive-header">
                          <span className={`email-direction ${email.direction || 'inbound'}`}>
                            {email.direction === 'outbound' ? 'Sent' : 'Received'}
                          </span>
                          <span className="email-date">
                            {new Date(email.date || email.created_at).toLocaleString()}
                          </span>
                        </div>
                        <div className="email-subject">{email.subject || '(No Subject)'}</div>
                        <div className="email-preview">{email.preview || email.body?.substring(0, 150) || ''}</div>
                        <div className="email-participants">
                          <span>From: {email.from || email.sender}</span>
                          <span>To: {email.to || email.recipient}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-archive-state">
                    <div className="empty-icon">📧</div>
                    <h3>No Emails Archived</h3>
                    <p>Emails associated with this client will appear here.</p>
                    <button className="sync-archive-btn" onClick={() => setShowEmailComposer(true)}>
                      Compose Email
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* SMS Archive Sub-tab */}
            {archiveSubTab === 'sms' && (
              <div className="archive-section">
                {archiveLoading ? (
                  <div className="loading-state">Loading SMS archive...</div>
                ) : smsArchive.length > 0 ? (
                  <div className="sms-thread">
                    {smsArchive.map((sms) => (
                      <div key={sms.id} className={`sms-item ${sms.direction || 'inbound'}`}>
                        <div className="sms-bubble">
                          <div className="sms-content">{sms.content || sms.message}</div>
                          <div className="sms-time">
                            {new Date(sms.sent_at || sms.created_at).toLocaleString()}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-archive-state">
                    <div className="empty-icon">💬</div>
                    <h3>No SMS Messages</h3>
                    <p>SMS conversations with this client will appear here.</p>
                    <button className="sync-archive-btn" onClick={() => setShowSMSModal(true)}>
                      Send SMS
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Recorded Calls Sub-tab */}
            {archiveSubTab === 'calls' && (
              <div className="archive-section">
                {archiveLoading ? (
                  <div className="loading-state">Loading call recordings...</div>
                ) : callArchive.length > 0 ? (
                  <div className="calls-archive-list">
                    {callArchive.map((call) => (
                      <div key={call.id} className="call-archive-item">
                        <div className="call-archive-header">
                          <span className={`call-direction ${call.direction || 'inbound'}`}>
                            {call.direction === 'outbound' ? 'Outgoing' : 'Incoming'}
                          </span>
                          <span className="call-duration">{call.duration || '0:00'}</span>
                          <span className="call-date">
                            {new Date(call.call_time || call.created_at).toLocaleString()}
                          </span>
                        </div>
                        <div className="call-participants">
                          <span>{call.caller_name || 'Unknown'} - {call.phone_number}</span>
                        </div>
                        {call.recording_url && (
                          <div className="call-recording">
                            <audio controls src={call.recording_url}>
                              Your browser does not support the audio element.
                            </audio>
                          </div>
                        )}
                        {call.transcription && (
                          <div className="call-transcription">
                            <strong>Transcription:</strong>
                            <p>{call.transcription}</p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-archive-state">
                    <div className="empty-icon">📞</div>
                    <h3>No Recorded Calls</h3>
                    <p>Call recordings with this client will appear here.</p>
                    <button className="sync-archive-btn" onClick={() => setShowRecordingModal(true)}>
                      Start Recording
                    </button>
                  </div>
                )}
              </div>
            )}
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
            {/* Custom Byte Mapping SLA Dates — synced from Salesforce */}
            <div className="info-section">
              <h2>Custom Byte Mapping SLA Dates</h2>
              <p className="section-subtitle">Loan processing timeline dates synced from Salesforce</p>

              {/* Lead & Application Phase */}
              <div className="dates-section" style={{ marginBottom: '24px' }}>
                <h3 className="dates-section-title">Lead & Application Phase</h3>
                <div className="dates-grid">
                  <div className="date-field">
                    <label>Prospect Date</label>
                    <input type="date" value={formData.prospect_date || ''} onChange={(e) => handleFieldChange('prospect_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Application Date</label>
                    <input type="date" value={formData.application_date || ''} onChange={(e) => handleFieldChange('application_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>LE Pending Date</label>
                    <input type="date" value={formData.le_pending_date || ''} onChange={(e) => handleFieldChange('le_pending_date', e.target.value)} />
                    <small className="field-hint">Loan Estimate disclosure</small>
                  </div>
                  <div className="date-field">
                    <label>Credit Only Date</label>
                    <input type="date" value={formData.credit_only_date || ''} onChange={(e) => handleFieldChange('credit_only_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>File Received Date</label>
                    <input type="date" value={formData.file_received_date || ''} onChange={(e) => handleFieldChange('file_received_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Pre-Approval Date</label>
                    <input type="date" value={formData.preapproval_date || ''} onChange={(e) => handleFieldChange('preapproval_date', e.target.value)} />
                  </div>
                </div>
              </div>

              {/* Lock Phase */}
              <div className="dates-section" style={{ marginBottom: '24px' }}>
                <h3 className="dates-section-title">Lock Phase</h3>
                <div className="dates-grid">
                  <div className="date-field">
                    <label>Lock Date</label>
                    <input type="date" value={formData.lock_date || ''} onChange={(e) => handleFieldChange('lock_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Lock Expiration Date</label>
                    <input type="date" value={formData.lock_expiration_date || ''} onChange={(e) => handleFieldChange('lock_expiration_date', e.target.value)} />
                  </div>
                </div>
              </div>

              {/* Processing & Underwriting Phase */}
              <div className="dates-section" style={{ marginBottom: '24px' }}>
                <h3 className="dates-section-title">Processing & Underwriting</h3>
                <div className="dates-grid">
                  <div className="date-field">
                    <label>UW Received Date</label>
                    <input type="date" value={formData.uw_received_date || ''} onChange={(e) => handleFieldChange('uw_received_date', e.target.value)} />
                    <small className="field-hint">File received by underwriting</small>
                  </div>
                  <div className="date-field">
                    <label>Conditions for Review Date</label>
                    <input type="date" value={formData.conditions_for_review_date || ''} onChange={(e) => handleFieldChange('conditions_for_review_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Suspended Date</label>
                    <input type="date" value={formData.suspended_date || ''} onChange={(e) => handleFieldChange('suspended_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Loan Approved Date</label>
                    <input type="date" value={formData.loan_approved_date || ''} onChange={(e) => handleFieldChange('loan_approved_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Approved Not Accepted Date</label>
                    <input type="date" value={formData.approved_not_accepted_date || ''} onChange={(e) => handleFieldChange('approved_not_accepted_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Approval Expires Date</label>
                    <input type="date" value={formData.approval_expires_date || ''} onChange={(e) => handleFieldChange('approval_expires_date', e.target.value)} />
                  </div>
                </div>
              </div>

              {/* Appraisal Phase */}
              <div className="dates-section" style={{ marginBottom: '24px' }}>
                <h3 className="dates-section-title">Appraisal</h3>
                <div className="dates-grid">
                  <div className="date-field">
                    <label>Appraisal Ordered Date</label>
                    <input type="date" value={formData.appraisal_ordered_date || ''} onChange={(e) => handleFieldChange('appraisal_ordered_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Appraisal Received Date</label>
                    <input type="date" value={formData.appraisal_received_date || ''} onChange={(e) => handleFieldChange('appraisal_received_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Appraisal Docs Expire Date</label>
                    <input type="date" value={formData.appraisal_docs_expire_date || ''} onChange={(e) => handleFieldChange('appraisal_docs_expire_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Appraisal Scheduled Date</label>
                    <input type="date" value={formData.appraisal_scheduled_date || ''} onChange={(e) => handleFieldChange('appraisal_scheduled_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Appraisal Completed Date</label>
                    <input type="date" value={formData.appraisal_completed_date || ''} onChange={(e) => handleFieldChange('appraisal_completed_date', e.target.value)} />
                  </div>
                </div>
              </div>

              {/* Title & Insurance Phase */}
              <div className="dates-section" style={{ marginBottom: '24px' }}>
                <h3 className="dates-section-title">Title & Insurance</h3>
                <div className="dates-grid">
                  <div className="date-field">
                    <label>Title Ordered Date</label>
                    <input type="date" value={formData.title_ordered_date || ''} onChange={(e) => handleFieldChange('title_ordered_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Title Received Date</label>
                    <input type="date" value={formData.title_received_date || ''} onChange={(e) => handleFieldChange('title_received_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Insurance Ordered Date</label>
                    <input type="date" value={formData.insurance_ordered_date || ''} onChange={(e) => handleFieldChange('insurance_ordered_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Insurance Received Date</label>
                    <input type="date" value={formData.insurance_received_date || ''} onChange={(e) => handleFieldChange('insurance_received_date', e.target.value)} />
                  </div>
                </div>
              </div>

              {/* Closing Disclosure Phase */}
              <div className="dates-section" style={{ marginBottom: '24px' }}>
                <h3 className="dates-section-title">Closing Disclosure</h3>
                <div className="dates-grid">
                  <div className="date-field">
                    <label>CD Requested Date</label>
                    <input type="date" value={formData.cd_requested_date || ''} onChange={(e) => handleFieldChange('cd_requested_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>CD Sent to Borrower Date</label>
                    <input type="date" value={formData.cd_sent_to_borrower_date || ''} onChange={(e) => handleFieldChange('cd_sent_to_borrower_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>CD Acknowledged Date</label>
                    <input type="date" value={formData.cd_acknowledged_date || ''} onChange={(e) => handleFieldChange('cd_acknowledged_date', e.target.value)} />
                  </div>
                </div>
              </div>

              {/* Clear to Close & Docs Phase */}
              <div className="dates-section" style={{ marginBottom: '24px' }}>
                <h3 className="dates-section-title">Clear to Close & Docs</h3>
                <div className="dates-grid">
                  <div className="date-field">
                    <label>Clear to Close Date</label>
                    <input type="date" value={formData.clear_to_close_date || ''} onChange={(e) => handleFieldChange('clear_to_close_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Docs Ordered Date</label>
                    <input type="date" value={formData.docs_ordered_date || ''} onChange={(e) => handleFieldChange('docs_ordered_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Docs Out Date</label>
                    <input type="date" value={formData.docs_out_date || ''} onChange={(e) => handleFieldChange('docs_out_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Credit Docs Expire Date</label>
                    <input type="date" value={formData.credit_docs_expire_date || ''} onChange={(e) => handleFieldChange('credit_docs_expire_date', e.target.value)} />
                  </div>
                </div>
              </div>

              {/* Funding & Closing Phase */}
              <div className="dates-section" style={{ marginBottom: '24px' }}>
                <h3 className="dates-section-title">Funding & Closing</h3>
                <div className="dates-grid">
                  <div className="date-field">
                    <label>Scheduled Closing Date</label>
                    <input type="date" value={formData.scheduled_closing_date || ''} onChange={(e) => handleFieldChange('scheduled_closing_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Scheduled Funding Date</label>
                    <input type="date" value={formData.scheduled_funding_date || ''} onChange={(e) => handleFieldChange('scheduled_funding_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Funds Ordered Date</label>
                    <input type="date" value={formData.funds_ordered_date || ''} onChange={(e) => handleFieldChange('funds_ordered_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Funds Sent Date</label>
                    <input type="date" value={formData.funds_sent_date || ''} onChange={(e) => handleFieldChange('funds_sent_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Funded Date</label>
                    <input type="date" value={formData.funded_date || ''} onChange={(e) => handleFieldChange('funded_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Closing Date</label>
                    <input type="date" value={formData.closing_date || ''} onChange={(e) => handleFieldChange('closing_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>First Payment Date</label>
                    <input type="date" value={formData.first_payment_date || ''} onChange={(e) => handleFieldChange('first_payment_date', e.target.value)} />
                  </div>
                </div>
              </div>

              {/* Post-Closing & Status */}
              <div className="dates-section" style={{ marginBottom: '24px' }}>
                <h3 className="dates-section-title">Post-Closing & Status</h3>
                <div className="dates-grid">
                  <div className="date-field">
                    <label>Investor Purchased Date</label>
                    <input type="date" value={formData.investor_purchased_date || ''} onChange={(e) => handleFieldChange('investor_purchased_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Withdrawn Date</label>
                    <input type="date" value={formData.withdrawn_date || ''} onChange={(e) => handleFieldChange('withdrawn_date', e.target.value)} />
                  </div>
                  <div className="date-field">
                    <label>Contract Received Date</label>
                    <input type="date" value={formData.contract_received_date || ''} onChange={(e) => handleFieldChange('contract_received_date', e.target.value)} />
                  </div>
                </div>
              </div>
            </div>

            <div className="info-section" style={{ marginTop: '2rem' }}>
              <h2>Portfolio Servicing Dates</h2>
              <p className="section-subtitle">Track key dates for portfolio management and client retention</p>

              {/* Loan History Dates */}
              <div className="dates-section" style={{ marginBottom: '24px' }}>
                <h3 className="dates-section-title">Loan History</h3>
                <div className="dates-grid">
                  <div className="date-field">
                    <label>Loan Origination Date</label>
                    <input
                      type="date"
                      value={formData.loan_origination_date || formData.closing_date || ''}
                      onChange={(e) => handleFieldChange('loan_origination_date', e.target.value)}
                    />
                    <small className="field-hint">Date the loan was funded</small>
                  </div>

                  <div className="date-field">
                    <label>First Payment Date</label>
                    <input
                      type="date"
                      value={formData.first_payment_date || ''}
                      onChange={(e) => handleFieldChange('first_payment_date', e.target.value)}
                    />
                  </div>

                  <div className="date-field">
                    <label>Last Payment Date</label>
                    <input
                      type="date"
                      value={formData.last_payment_date || ''}
                      onChange={(e) => handleFieldChange('last_payment_date', e.target.value)}
                    />
                  </div>

                  <div className="date-field">
                    <label>Maturity Date</label>
                    <input
                      type="date"
                      value={formData.maturity_date || ''}
                      onChange={(e) => handleFieldChange('maturity_date', e.target.value)}
                    />
                    <small className="field-hint">When the loan will be paid off</small>
                  </div>
                </div>
              </div>

              {/* Annual Review Dates */}
              <div className="dates-section" style={{ marginBottom: '24px' }}>
                <h3 className="dates-section-title">Annual Review Schedule</h3>
                <div className="dates-grid">
                  <div className="date-field">
                    <label>Next Annual Review Date</label>
                    <input
                      type="date"
                      value={formData.next_annual_review_date || ''}
                      onChange={(e) => handleFieldChange('next_annual_review_date', e.target.value)}
                    />
                    <small className="field-hint">Scheduled check-in with client</small>
                  </div>

                  <div className="date-field">
                    <label>Last Annual Review Date</label>
                    <input
                      type="date"
                      value={formData.last_annual_review_date || ''}
                      onChange={(e) => handleFieldChange('last_annual_review_date', e.target.value)}
                    />
                  </div>

                  <div className="date-field">
                    <label>Birthday</label>
                    <input
                      type="date"
                      value={formData.birthday || ''}
                      onChange={(e) => handleFieldChange('birthday', e.target.value)}
                    />
                    <small className="field-hint">For client relationship management</small>
                  </div>

                  <div className="date-field">
                    <label>Close Anniversary Date</label>
                    <input
                      type="date"
                      value={formData.close_anniversary_date || formData.closing_date || ''}
                      onChange={(e) => handleFieldChange('close_anniversary_date', e.target.value)}
                    />
                    <small className="field-hint">Annual closing anniversary</small>
                  </div>
                </div>
              </div>

              {/* Credit & Insurance Dates */}
              <div className="dates-section" style={{ marginBottom: '24px' }}>
                <h3 className="dates-section-title">Credit & Insurance</h3>
                <div className="dates-grid">
                  <div className="date-field">
                    <label>Credit Refresh Date</label>
                    <input
                      type="date"
                      value={formData.credit_refresh_date || ''}
                      onChange={(e) => handleFieldChange('credit_refresh_date', e.target.value)}
                    />
                    <small className="field-hint">Next credit score update</small>
                  </div>

                  <div className="date-field">
                    <label>Insurance Renewal Date</label>
                    <input
                      type="date"
                      value={formData.insurance_renewal_date || ''}
                      onChange={(e) => handleFieldChange('insurance_renewal_date', e.target.value)}
                    />
                    <small className="field-hint">Homeowner's insurance renewal</small>
                  </div>

                  <div className="date-field">
                    <label>Tax Escrow Review Date</label>
                    <input
                      type="date"
                      value={formData.tax_escrow_review_date || ''}
                      onChange={(e) => handleFieldChange('tax_escrow_review_date', e.target.value)}
                    />
                  </div>

                  <div className="date-field">
                    <label>PMI Removal Eligible Date</label>
                    <input
                      type="date"
                      value={formData.pmi_removal_eligible_date || ''}
                      onChange={(e) => handleFieldChange('pmi_removal_eligible_date', e.target.value)}
                    />
                    <small className="field-hint">When LTV reaches 80%</small>
                  </div>
                </div>
              </div>

              {/* Opportunity Dates */}
              <div className="dates-section">
                <h3 className="dates-section-title">Opportunity Tracking</h3>
                <div className="dates-grid">
                  <div className="date-field">
                    <label>Refinance Eligibility Date</label>
                    <input
                      type="date"
                      value={formData.refinance_eligibility_date || ''}
                      onChange={(e) => handleFieldChange('refinance_eligibility_date', e.target.value)}
                    />
                    <small className="field-hint">After seasoning period</small>
                  </div>

                  <div className="date-field">
                    <label>HELOC Eligibility Date</label>
                    <input
                      type="date"
                      value={formData.heloc_eligibility_date || ''}
                      onChange={(e) => handleFieldChange('heloc_eligibility_date', e.target.value)}
                    />
                  </div>

                  <div className="date-field">
                    <label>Rate Watch Start Date</label>
                    <input
                      type="date"
                      value={formData.rate_watch_start_date || ''}
                      onChange={(e) => handleFieldChange('rate_watch_start_date', e.target.value)}
                    />
                    <small className="field-hint">Monitoring for rate drop opportunities</small>
                  </div>

                  <div className="date-field">
                    <label>Last Contact Date</label>
                    <input
                      type="date"
                      value={formData.last_contact_date || ''}
                      onChange={(e) => handleFieldChange('last_contact_date', e.target.value)}
                    />
                    <small className="field-hint">Most recent client interaction</small>
                  </div>
                </div>
              </div>
            </div>
          </div>
          )}

        </div>
      </div>

      {/* SMS Modal */}
      {client && (
        <SMSModal
          isOpen={showSMSModal}
          onClose={() => setShowSMSModal(false)}
          lead={client}
        />
      )}

      {/* Teams Modal */}
      {client && (
        <TeamsModal
          isOpen={showTeamsModal}
          onClose={() => setShowTeamsModal(false)}
          lead={client}
        />
      )}

      {/* Recording Modal */}
      {client && (
        <RecordingModal
          isOpen={showRecordingModal}
          onClose={() => setShowRecordingModal(false)}
          lead={client}
        />
      )}

      {/* Voicemail Drop */}
      {client && showVoicemailDrop && (
        <VoicemailDrop
          phoneNumber={client.phone}
          recipientName={client.name}
          onClose={() => setShowVoicemailDrop(false)}
        />
      )}

      {/* Appointment Modal (legacy) */}
      {client && (
        <AppointmentModal
          isOpen={showAppointmentModal}
          onClose={() => setShowAppointmentModal(false)}
          lead={client}
        />
      )}

      {/* Schedule Appointment Modal (Redfin-style) */}
      {client && (
        <ScheduleAppointmentModal
          isOpen={showScheduleModal}
          onClose={() => setShowScheduleModal(false)}
          onSuccess={() => setCalendarRefreshKey(prev => prev + 1)}
          borrower={client}
        />
      )}

      {/* UVIP Video Meetings Modal */}
      {showVideoMeetings && (
        <div className="modal-overlay" onClick={() => setShowVideoMeetings(false)}>
          <div className="modal-content video-meetings-modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close-btn" onClick={() => setShowVideoMeetings(false)}>×</button>
            <VideoMeetings
              onClose={() => setShowVideoMeetings(false)}
              contactId={client?.id}
            />
          </div>
        </div>
      )}

      {/* Email Composer Modal */}
      <EmailComposerModal
        isOpen={showEmailComposer}
        onClose={() => setShowEmailComposer(false)}
        recipient={{
          name: client?.name,
          email: client?.email
        }}
        entityType="mum"
        entityData={client}
      />

      {/* Escalation Modal */}
      <EscalationModal
        isOpen={showEscalationModal}
        onClose={() => setShowEscalationModal(false)}
        entityType="mum"
        entityId={id}
        entityData={client}
      />
      </div>

      {/* Fixed Sidebar */}
      <CalendarSidebar key={calendarRefreshKey}>
      {/* Quick Actions */}
      <div className="actions-card">
        <h3>QUICK ACTIONS</h3>
        <div className="action-buttons">
          <button className="action-btn call" onClick={() => handleAction('call')} disabled={!client.phone} title="Click to call">
            <span>Call</span>
          </button>
          <button className="action-btn sms" onClick={() => handleAction('sms')} disabled={!client.phone} title="Send SMS">
            <span>SMS Text</span>
          </button>
          <button className="action-btn email" onClick={() => handleAction('email')} disabled={!client.email} title="Send email">
            <span>Send Email</span>
          </button>
          <button className="action-btn task" onClick={() => handleAction('task')} title="Create task">
            <span>Create Task</span>
          </button>
          <button className="action-btn calendar" onClick={() => handleAction('calendar')} title="Set appointment">
            <span>Set Appointment</span>
          </button>
          <button className="action-btn video" onClick={() => handleAction('video')} title="Start video call">
            <span>Video Call</span>
          </button>
          <button className="action-btn voicemail" onClick={() => handleAction('voicemail')} disabled={!client.phone} title="Drop voicemail">
            <span>Voicemail Drop</span>
          </button>
          <button className="action-btn record-video" onClick={() => handleAction('record')} title="Record and send a video message">
            <span>Record Video</span>
          </button>
          <button className="action-btn application" onClick={() => handleAction('send_application')} title="Send application link">
            <span>Send Application</span>
          </button>
          <button className="action-btn portal" onClick={() => handleAction('client_portal')} title="Access portals">
            <span>Portals</span>
          </button>
          <button className="action-btn escalation" onClick={() => handleAction('escalation')} title="Escalate issue">
            <span>Escalation</span>
          </button>
        </div>
      </div>
    </CalendarSidebar>
    </div>
  );
}

export default MumClientDetail;
