// VERSION: 2024-11-14-v2 - MOCK DATA FIX
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { loansAPI, activitiesAPI, schedulerAPI, dialerAPI, borrowerApplicationAPI, purlAPI } from '../services/api';
import { toast } from '../utils/toast';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import SMSModal from '../components/SMSModal';
import VideoCallScheduleModal from '../components/VideoCallScheduleModal';
import RecordingModal from '../components/RecordingModal';
import SendVideoModal from '../components/video/SendVideoModal';
import VoicemailDrop from '../components/VoicemailDrop';
import EscalationModal from '../components/EscalationModal';
import CreateTaskModal from '../components/CreateTaskModal';
import EmailComposerModal from '../components/EmailComposerModal';
import TeamAssignment from '../components/TeamAssignment';
import EmploymentTab from '../components/EmploymentTab';
import IncomeTab from '../components/income/IncomeTab';
import ScheduleAppointmentModal from '../components/ScheduleAppointmentModal';
import NeedsListView from '../components/smart-docs/NeedsListView';
import CreditTab from '../components/CreditTab';
import SalesforceConnectionBadge from '../components/SalesforceConnectionBadge';
import CallIntelligenceTab from '../components/call-intelligence/CallIntelligenceTab';
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

function ClientProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [client, setClient] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(true); // Always in edit mode
  const [formData, setFormData] = useState({});
  const [emails, setEmails] = useState([]);
  const [activeTab, setActiveTab] = useState('loan-details');
  const [noteText, setNoteText] = useState('');
  const [noteLoading, setNoteLoading] = useState(false);
  const [borrowers, setBorrowers] = useState([]);
  const [activeBorrower, setActiveBorrower] = useState(0);
  const [saveTimeout, setSaveTimeout] = useState(null);
  const [showSMSModal, setShowSMSModal] = useState(false);
  const [showVideoCall, setShowVideoCall] = useState(false);
  const [showSendVideoModal, setShowSendVideoModal] = useState(false);
  const [showRecordingModal, setShowRecordingModal] = useState(false);
  const [showVoicemailDrop, setShowVoicemailDrop] = useState(false);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [showEscalationModal, setShowEscalationModal] = useState(false);
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [showEmailComposer, setShowEmailComposer] = useState(false);
  const [showApplicationModal, setShowApplicationModal] = useState(false);
  const [applicationLink, setApplicationLink] = useState(null);
  const [applicationLoading, setApplicationLoading] = useState(false);
  const [showClientPortalModal, setShowClientPortalModal] = useState(false);
  const [clientPortalData, setClientPortalData] = useState(null);
  const [clientPortalLoading, setClientPortalLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState('');
  const [customFields, setCustomFields] = useState([]);
  const [showAddFieldModal, setShowAddFieldModal] = useState(false);
  const [newFieldName, setNewFieldName] = useState('');
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);
  const [statusSaving, setStatusSaving] = useState(false);
  const [circleContacts, setCircleContacts] = useState([]);
  const [upcomingAppointments, setUpcomingAppointments] = useState([]);
  const [appointmentsLoading, setAppointmentsLoading] = useState(false);
  const [milestones, setMilestones] = useState([]);
  const [milestonesLoading, setMilestonesLoading] = useState(false);

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
      await loansAPI.update(id, { stage: newStatus });
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
    loadCircleContacts();
    loadUpcomingAppointments();
    loadMilestones();
    markLoanAsViewed();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Handle tab query parameter for deep linking
  useEffect(() => {
    const tabParam = searchParams.get('tab');
    if (tabParam) {
      // Valid tabs: personal, loan-details, employment, income, circle-of-trust, documents, important-dates, communications, call-intelligence
      const validTabs = ['personal', 'loan-details', 'employment', 'income', 'circle-of-trust', 'documents', 'important-dates', 'communications', 'call-intelligence'];
      if (validTabs.includes(tabParam)) {
        setActiveTab(tabParam);
      }
    }
  }, [searchParams]);

  const markLoanAsViewed = () => {
    try {
      // Get viewed leads from localStorage
      const stored = localStorage.getItem('viewedLoans');
      const viewedLoans = stored ? new Set(JSON.parse(stored)) : new Set();

      // Add current lead ID
      viewedLoans.add(String(id));

      // Save back to localStorage
      localStorage.setItem('viewedLoans', JSON.stringify([...viewedLoans]));
    } catch (error) {
      console.error('Error marking lead as viewed:', error);
    }
  };

  const loadClientData = async () => {
    try {
      setLoading(true);
      let loanData = null;
      let activitiesData = [];

      try {
        // Try to fetch from API first
        [loanData, activitiesData] = await Promise.all([
          loansAPI.getById(id),
          activitiesAPI.getAll({ loan_id: id })
        ]);
        console.log('✅ Loaded lead from API:', loanData);
      } catch (apiError) {
        console.log('⚠️ API failed, using mock data. Error:', apiError);
        // Fallback to mock data
        const mockLeads = generateMockLeads();
        console.log('📦 Generated mock leads, total count:', mockLeads.length);
        console.log('🔍 Looking for lead ID:', id, 'Type:', typeof id);
        loanData = mockLeads.find(lead => client.id === parseInt(id));
        console.log('🎯 Found mock lead:', loanData);

        if (!loanData) {
          console.error('❌ Lead not found in mock data');
          toast.error('Lead not found in mock data');
          navigate('/loans');
          return;
        }
        activitiesData = [];
      }

      console.log('✨ Setting lead data:', loanData);
      setClient(loanData);
      setFormData(loanData);
      setActivities(activitiesData || []);

      // Initialize borrowers array
      const primaryName = loanData.first_name && loanData.last_name
        ? `${loanData.first_name} ${loanData.last_name}`
        : loanData.name || 'Primary Borrower';

      const borrowersList = [
        {
          id: 0,
          name: primaryName,
          type: 'primary',
          data: loanData
        }
      ];

      // Add co-borrower if exists
      if (loanData.co_applicant_name) {
        const coborrowerName = String(loanData.co_applicant_name || '');
        const nameParts = coborrowerName.split(' ');
        borrowersList.push({
          id: 1,
          name: loanData.co_applicant_name,
          type: 'co-borrower',
          data: {
            name: loanData.co_applicant_name,
            first_name: nameParts[0] || '',
            last_name: nameParts.slice(1).join(' ') || '',
            email: loanData.co_applicant_email || '',
            phone: loanData.co_applicant_phone || '',
          }
        });
      }

      setBorrowers(borrowersList);
    } catch (error) {
      console.error('Failed to load lead data:', error);
      toast.error('Failed to load lead details');
      navigate('/loans');
    } finally {
      setLoading(false);
    }
  };

  const loadEmails = async () => {
    try {
      const emailActivities = await activitiesAPI.getAll({
        loan_id: id,
        type: 'email'
      });
      setEmails(emailActivities || []);
    } catch (error) {
      console.error('Failed to load emails:', error);
    }
  };

  const loadCircleContacts = async () => {
    try {
      const response = await fetch(`${process.env.REACT_APP_API_URL || ''}/api/v1/leads/${id}/circle-contacts`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setCircleContacts(data.contacts || []);
      }
    } catch (error) {
      console.error('Failed to load circle contacts:', error);
    }
  };

  const loadUpcomingAppointments = async () => {
    try {
      setAppointmentsLoading(true);
      // Get appointments for this loan, filter for upcoming only
      const today = new Date().toISOString().split('T')[0];
      const appointments = await schedulerAPI.getAppointments({
        loan_id: id,
        start_date: today
      });
      // Filter for booked/tentative status and sort by date
      const upcoming = (appointments || [])
        .filter(apt => ['booked', 'tentative'].includes(apt.status))
        .sort((a, b) => new Date(a.scheduled_start) - new Date(b.scheduled_start));
      setUpcomingAppointments(upcoming);
    } catch (error) {
      console.error('Failed to load appointments:', error);
      setUpcomingAppointments([]);
    } finally {
      setAppointmentsLoading(false);
    }
  };

  const loadMilestones = async () => {
    try {
      setMilestonesLoading(true);
      const response = await fetch(`${process.env.REACT_APP_API_URL || ''}/api/portal/loans/${id}/milestones`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setMilestones(data.milestones || []);
      }
    } catch (error) {
      console.error('Failed to load milestones:', error);
      setMilestones([]);
    } finally {
      setMilestonesLoading(false);
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

      await loansAPI.update(id, dataToSave);

      // Reload the lead data to sync with backend
      const updatedLead = await loansAPI.getById(id);
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

      await loansAPI.update(id, dataToSave);
      console.log(`Field ${fieldName} saved successfully`);

      // Reload to sync with backend
      const updatedLead = await loansAPI.getById(id);
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
        loan_id: parseInt(id)
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
        await loansAPI.update(id, {
          co_applicant_name: fullName
        });

        // Reload lead data to sync with backend
        const loanData = await loansAPI.getById(id);
        setClient(loanData);

        // Rebuild borrowers array with the new co-borrower
        const primaryName = loanData.first_name && loanData.last_name
          ? `${loanData.first_name} ${loanData.last_name}`
          : loanData.name || 'Primary Borrower';

        const updatedBorrowers = [
          {
            id: 0,
            name: primaryName,
            type: 'primary',
            data: loanData
          }
        ];

        if (loanData.co_applicant_name) {
          const coborrowerParts = (loanData.co_applicant_name || '').split(' ');
          updatedBorrowers.push({
            id: 1,
            name: loanData.co_applicant_name,
            type: 'co-borrower',
            data: {
              name: loanData.co_applicant_name,
              first_name: coborrowerParts[0] || '',
              last_name: coborrowerParts.slice(1).join(' ') || '',
              email: loanData.co_applicant_email || '',
              phone: loanData.co_applicant_phone || '',
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

  const handleSendApplication = async () => {
    if (!client) return;
    try {
      setApplicationLoading(true);
      const response = await borrowerApplicationAPI.createForLead(client.id || id, {
        send_email: false,
        send_sms: false
      });
      const appUrl = `${window.location.origin}/apply/${response.public_token}`;
      setApplicationLink({
        url: appUrl,
        token: response.public_token,
        application_id: response.id
      });
      setShowApplicationModal(true);
    } catch (err) {
      console.error('Error creating application:', err);
      toast.error('Failed to create application link. Please try again.');
    } finally {
      setApplicationLoading(false);
    }
  };

  const handleClientPortal = async () => {
    if (!client) return;
    try {
      setClientPortalLoading(true);
      let existingWorkspace = null;
      try {
        existingWorkspace = await purlAPI.getWorkspaceByLead(client.id || id);
      } catch (err) {
        const isNotFound = err.response?.status === 404;
        const isNetworkError = err.message === 'Network Error' || !err.response;
        if (!isNotFound && !isNetworkError) throw err;
      }

      if (existingWorkspace && existingWorkspace.workspace) {
        const workspaceId = existingWorkspace.workspace.workspace_id || existingWorkspace.workspace.id;
        const slug = existingWorkspace.workspace.workspace_slug || existingWorkspace.workspace.slug;
        const tokenResponse = await purlAPI.createToken(workspaceId, { scope: 'full', expires_in_days: 90 });
        const fullToken = tokenResponse.token;
        const baseUrl = `${window.location.origin}/portal/${slug}`;
        const portalUrl = fullToken ? `${baseUrl}?token=${fullToken}` : baseUrl;
        setClientPortalData({ workspace_id: workspaceId, url: portalUrl, borrower_name: existingWorkspace.workspace.display_name, status: existingWorkspace.workspace.status, exists: true });
        setShowClientPortalModal(true);
        return;
      }

      const borrowerName = client.borrower_name || client.name || '';
      const createData = { lead_id: client.id || parseInt(id), borrower_name: borrowerName, first_name: client.first_name, last_name: client.last_name, email: client.borrower_email || client.email, phone: client.borrower_phone || client.phone };
      const response = await purlAPI.createWorkspace(createData);
      const newWorkspace = response.workspace || response;
      const tokenResponse = await purlAPI.createToken(newWorkspace.id, { scope: 'full', expires_in_days: 90 });
      const fullToken = tokenResponse.token;
      const baseUrl = `${window.location.origin}/portal/${newWorkspace.slug}`;
      const portalUrl = fullToken ? `${baseUrl}?token=${fullToken}` : baseUrl;
      setClientPortalData({ workspace_id: newWorkspace.id, url: portalUrl, borrower_name: borrowerName, status: newWorkspace.status, exists: false, justCreated: true });
      setShowClientPortalModal(true);
    } catch (err) {
      console.error('[Client Portal] Error:', err);
      const errorMessage = err.response?.data?.detail || (err.message === 'Network Error' ? 'Unable to connect to server.' : err.message || 'Unknown error');
      toast.error(`Failed to access/create client portal: ${errorMessage}`);
    } finally {
      setClientPortalLoading(false);
    }
  };

  const handleAction = async (action) => {
    const phone = client.borrower_phone || client.phone;
    switch(action) {
      case 'call':
        if (!phone) {
          toast.error('No phone number available for this contact');
          return;
        }
        try {
          const cleanPhone = phone.replace(/[^\d+]/g, '');
          const result = await dialerAPI.clickToDial({
            phone_number: cleanPhone,
            contact_name: client.borrower_name || client.name || 'Contact',
            lead_id: client.id || id
          });
          if (result.success) {
            toast.success(`Calling your phone now... You'll be connected to ${client.borrower_name || client.name || 'the contact'}.`);
          } else {
            if (result.error?.includes('cell phone not configured') || result.error?.includes('caller ID')) {
              toast.warning('Click-to-dial not configured. Opening phone app...');
              window.open(`tel:${phone}`, '_self');
            } else {
              toast.error(`Call failed: ${result.error || 'Unknown error'}`);
            }
          }
        } catch (err) {
          console.error('Click-to-dial error:', err);
          toast.warning('Click-to-dial unavailable. Opening phone app...');
          window.open(`tel:${phone}`, '_self');
        }
        break;
      case 'sms':
        setShowSMSModal(true);
        break;
      case 'email':
        setShowEmailComposer(true);
        break;
      case 'task':
        setShowTaskModal(true);
        break;
      case 'calendar':
        setShowScheduleModal(true);
        break;
      case 'video':
        setShowVideoCall(true);
        break;
      case 'voicemail':
        setShowVoicemailDrop(true);
        break;
      case 'send_application':
        handleSendApplication();
        break;
      case 'client_portal':
        handleClientPortal();
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
      <div className="client-profile-page">
        <div className="loading">Loading lead details...</div>
      </div>
    );
  }

  if (!client) {
    return (
      <div className="client-profile-page">
        <div className="error">Lead not found</div>
      </div>
    );
  }

  return (
    <div className="client-profile-page">
      {/* Header */}
      <div className="detail-header">
        <button className="btn-back" onClick={() => navigate('/loans')}>
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

      {/* Client Name + Status Banner */}
      <div style={{
        padding: '12px 24px',
        backgroundColor: '#f8fafc',
        borderBottom: '1px solid #e2e8f0',
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
      }}>
        <h2 style={{ margin: 0, fontSize: '20px', fontWeight: '600', color: '#1a1a2e' }}>
          {formData.borrower_name || client?.borrower_name || client?.name || 'Client'}
        </h2>

        {/* Status Dropdown */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setShowStatusDropdown(!showStatusDropdown)}
            disabled={statusSaving}
            style={{
              backgroundColor: getStatusColor(formData.stage || client?.stage || 'Application'),
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
            {statusSaving ? 'Saving...' : (formData.stage || client?.stage || 'Application')}
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

      {/* Loan Information Toolbar */}
      <div className="loan-toolbar">
        <div className="toolbar-header">
          <h3>Loan Details</h3>
          {/* Salesforce Connection Indicator */}
          <SalesforceConnectionBadge
            entityType="loan"
            entityId={id}
            salesforceId={client?.salesforce_id}
            lastSyncedAt={client?.salesforce_last_synced_at}
          />
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
          className={`tab-btn ${activeTab === 'smart-docs' ? 'active' : ''}`}
          onClick={() => setActiveTab('smart-docs')}
        >
          Smart Docs
        </button>
        <button
          className={`tab-btn ${activeTab === 'credit' ? 'active' : ''}`}
          onClick={() => setActiveTab('credit')}
        >
          Credit
        </button>
        <button
          className={`tab-btn ${activeTab === 'income' ? 'active' : ''}`}
          onClick={() => setActiveTab('income')}
        >
          Income
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
          className={`tab-btn ${activeTab === 'team' ? 'active' : ''}`}
          onClick={() => setActiveTab('team')}
        >
          Team Members
        </button>
        <button
          className={`tab-btn ${activeTab === 'call-intelligence' ? 'active' : ''}`}
          onClick={() => setActiveTab('call-intelligence')}
        >
          Call Intelligence
        </button>
      </div>

      <div className="detail-content">
        {/* Left Column - Lead Information */}
        <div className="left-column">
          {/* Loan Details Tab */}
          {activeTab === 'loan-details' && (
          <div className="info-section">
            <h2>Loan Details</h2>
            <div className="info-grid">
              <div className="info-field">
                <label>Loan Number</label>
                <input
                  type="text"
                  value={formData.loan_number || client?.loan_number || ''}
                  onChange={(e) => handleFieldChange('loan_number', e.target.value)}
                  placeholder="Enter loan number"
                />
              </div>
              <div className="info-field">
                <label>Loan Amount</label>
                <input
                  type="number"
                  value={formData.loan_amount || formData.amount || ''}
                  onChange={(e) => handleFieldChange('loan_amount', e.target.value)}
                  placeholder="$"
                />
              </div>
              <div className="info-field">
                <label>Loan Type</label>
                <select
                  value={formData.loan_type || ''}
                  onChange={(e) => handleFieldChange('loan_type', e.target.value)}
                >
                  <option value="">Select Type</option>
                  <option value="Conventional">Conventional</option>
                  <option value="FHA">FHA</option>
                  <option value="VA">VA</option>
                  <option value="USDA">USDA</option>
                  <option value="Jumbo">Jumbo</option>
                </select>
              </div>
              <div className="info-field">
                <label>Loan Purpose</label>
                <select
                  value={formData.loan_purpose || ''}
                  onChange={(e) => handleFieldChange('loan_purpose', e.target.value)}
                >
                  <option value="">Select Purpose</option>
                  <option value="Purchase">Purchase</option>
                  <option value="Refinance">Refinance</option>
                  <option value="Cash Out">Cash Out Refinance</option>
                </select>
              </div>
              <div className="info-field">
                <label>Interest Rate</label>
                <input
                  type="text"
                  value={formData.interest_rate || ''}
                  onChange={(e) => handleFieldChange('interest_rate', e.target.value)}
                  placeholder="%"
                />
              </div>
              <div className="info-field">
                <label>Loan Term</label>
                <select
                  value={formData.loan_term || ''}
                  onChange={(e) => handleFieldChange('loan_term', e.target.value)}
                >
                  <option value="">Select Term</option>
                  <option value="30">30 Years</option>
                  <option value="20">20 Years</option>
                  <option value="15">15 Years</option>
                  <option value="10">10 Years</option>
                </select>
              </div>
            </div>
          </div>
          )}

          {/* Tasks Tab */}
          {activeTab === 'tasks' && (
          <div className="info-section">
            <h2>Tasks</h2>
            <p style={{ color: '#6b7280', marginBottom: '1rem' }}>View and manage tasks for this client.</p>
            <button
              onClick={() => navigate('/tasks')}
              style={{
                background: '#218D8D',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                padding: '10px 20px',
                cursor: 'pointer'
              }}
            >
              Open Task Manager
            </button>
          </div>
          )}

          {/* Smart Docs Tab */}
          {activeTab === 'smart-docs' && (
          <div className="info-section">
            <h2>Smart Documents</h2>
            <NeedsListView
              borrowerId={client?.id}
              loanId={client?.loan_id || client?.id}
            />
          </div>
          )}

          {/* Credit Tab */}
          {activeTab === 'credit' && (
          <div className="info-section">
            <CreditTab
              leadId={client?.lead_id || parseInt(id)}
              loanId={client?.loan_id || parseInt(id)}
              borrowerId={client?.id}
              formData={formData}
            />
          </div>
          )}

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
              entityType="loans"
            />
          )}

          {/* Income Tab */}
          {activeTab === 'income' && (
            <IncomeTab
              borrowerId={activeBorrower + 1}
              loanId={parseInt(id)}
              onIncomeChange={(monthly, annual) => {
                // Update the loan's qualifying income fields
                handleFieldChange('monthly_income', monthly);
                handleFieldChange('annual_income', annual);
              }}
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

          {/* Call Intelligence Tab */}
          {activeTab === 'call-intelligence' && (
          <div className="info-section call-intelligence-section">
            <CallIntelligenceTab
              clientId={id}
              loanId={client?.loan_id}
              leadId={id}
            />
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
          )}

          {/* Circle Tab */}
          {activeTab === 'circle' && (
          <div className="info-section">
            <h2>Circle of Cash Flow</h2>
            <div className="circle-content">
              <p className="circle-description">
                The borrower's trusted professional network from their Mortgage Planner Questionnaire.
                These are opportunities to build reciprocal referral relationships.
              </p>

              {/* Circle of Cash Flow - Professional Network */}
              <h3 style={{ marginTop: '20px', marginBottom: '15px', color: '#2c3e50' }}>Professional Network</h3>
              <div className="circle-grid">
                {/* Financial Advisor */}
                <div className="circle-card">
                  <div className="circle-header">
                    <h3>💼 Financial Advisor</h3>
                  </div>
                  <div className="circle-list">
                    {circleContacts.filter(c => c.type === 'Financial Advisor').length > 0 ? (
                      circleContacts.filter(c => c.type === 'Financial Advisor').map(contact => (
                        <div key={contact.id} className="circle-contact-item">
                          <div className="contact-name">{contact.name}</div>
                          {contact.notes && <div className="contact-notes">{contact.notes}</div>}
                        </div>
                      ))
                    ) : (
                      <div className="empty-state">Needs a financial advisor - referral opportunity!</div>
                    )}
                  </div>
                </div>

                {/* Accountant */}
                <div className="circle-card">
                  <div className="circle-header">
                    <h3>📊 Accountant / CPA</h3>
                  </div>
                  <div className="circle-list">
                    {circleContacts.filter(c => c.type === 'Accountant').length > 0 ? (
                      circleContacts.filter(c => c.type === 'Accountant').map(contact => (
                        <div key={contact.id} className="circle-contact-item">
                          <div className="contact-name">{contact.name}</div>
                          {contact.notes && <div className="contact-notes">{contact.notes}</div>}
                        </div>
                      ))
                    ) : (
                      <div className="empty-state">Needs an accountant - referral opportunity!</div>
                    )}
                  </div>
                </div>

                {/* Life Insurance Agent */}
                <div className="circle-card">
                  <div className="circle-header">
                    <h3>🛡️ Life Insurance Agent</h3>
                  </div>
                  <div className="circle-list">
                    {circleContacts.filter(c => c.type === 'Life Insurance Agent').length > 0 ? (
                      circleContacts.filter(c => c.type === 'Life Insurance Agent').map(contact => (
                        <div key={contact.id} className="circle-contact-item">
                          <div className="contact-name">{contact.name}</div>
                          {contact.notes && <div className="contact-notes">{contact.notes}</div>}
                        </div>
                      ))
                    ) : (
                      <div className="empty-state">Needs insurance agent - referral opportunity!</div>
                    )}
                  </div>
                </div>

                {/* Estate Planner */}
                <div className="circle-card">
                  <div className="circle-header">
                    <h3>📜 Estate Planner</h3>
                  </div>
                  <div className="circle-list">
                    {circleContacts.filter(c => c.type === 'Estate Planner').length > 0 ? (
                      circleContacts.filter(c => c.type === 'Estate Planner').map(contact => (
                        <div key={contact.id} className="circle-contact-item">
                          <div className="contact-name">{contact.name}</div>
                          {contact.notes && <div className="contact-notes">{contact.notes}</div>}
                        </div>
                      ))
                    ) : (
                      <div className="empty-state">Needs estate planner - referral opportunity!</div>
                    )}
                  </div>
                </div>
              </div>

              {/* Other Circle Members */}
              <h3 style={{ marginTop: '30px', marginBottom: '15px', color: '#2c3e50' }}>Other Circle Members</h3>
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
            <p className="section-subtitle">
              Manage document collection and track outstanding requests for this loan.
              {borrowers.length > 1 && ` Showing documents for ${borrowers[activeBorrower]?.name || 'borrower'}.`}
            </p>
            <NeedsListView
              loanId={parseInt(id)}
              borrowerId={activeBorrower + 1}
              onRequestUpdated={() => {
                // Optionally refresh any related data when documents change
                console.log('Document request updated');
              }}
            />
          </div>
          )}

          {/* Important Dates Tab */}
          {activeTab === 'important-dates' && (
          <div className="tab-content">
            {/* Last Touched Date - auto-updated on any file change */}
            <div className="info-section" style={{
              background: 'linear-gradient(135deg, #f0f4ff 0%, #e8eeff 100%)',
              border: '1px solid #c7d2fe',
              borderRadius: '10px',
              padding: '16px 20px',
              marginBottom: '1.5rem',
              display: 'flex',
              alignItems: 'center',
              gap: '12px'
            }}>
              <div style={{
                width: '40px',
                height: '40px',
                borderRadius: '10px',
                background: '#6366f1',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0
              }}>
                <span style={{ color: '#fff', fontSize: '18px' }}>&#128197;</span>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: '#6366f1', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Last Touched Date
                </div>
                <div style={{ fontSize: '16px', fontWeight: 600, color: '#1e1b4b', marginTop: '2px' }}>
                  {client?.updated_at
                    ? new Date(client.updated_at).toLocaleDateString('en-US', {
                        weekday: 'short',
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })
                    : 'No updates recorded'}
                </div>
              </div>
              <div style={{
                fontSize: '11px',
                color: '#6b7280',
                background: '#fff',
                padding: '4px 10px',
                borderRadius: '6px',
                border: '1px solid #e5e7eb',
                whiteSpace: 'nowrap'
              }}>
                Auto-updated
              </div>
            </div>

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

            {/* ============================================================ */}
            {/* JUNGO/SALESFORCE SLA DATE FIELDS - All 33 Fields */}
            {/* These dates are synced from Salesforce and trigger SLA workflows */}
            {/* ============================================================ */}

            {/* Lead & Application Phase */}
            <div className="info-section" style={{ marginTop: '2rem' }}>
              <h2>Lead & Application Phase</h2>
              <p className="section-subtitle">Initial contact through application submission</p>
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
            <div className="info-section" style={{ marginTop: '1.5rem' }}>
              <h2>Lock Phase</h2>
              <p className="section-subtitle">Rate lock management</p>
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
            <div className="info-section" style={{ marginTop: '1.5rem' }}>
              <h2>Processing & Underwriting</h2>
              <p className="section-subtitle">File processing through underwriting decision</p>
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
            <div className="info-section" style={{ marginTop: '1.5rem' }}>
              <h2>Appraisal</h2>
              <p className="section-subtitle">Property appraisal process</p>
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
            <div className="info-section" style={{ marginTop: '1.5rem' }}>
              <h2>Title & Insurance</h2>
              <p className="section-subtitle">Title and insurance order tracking</p>
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
            <div className="info-section" style={{ marginTop: '1.5rem' }}>
              <h2>Closing Disclosure</h2>
              <p className="section-subtitle">CD preparation and acknowledgment</p>
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
            <div className="info-section" style={{ marginTop: '1.5rem' }}>
              <h2>Clear to Close & Docs</h2>
              <p className="section-subtitle">Final approval and document preparation</p>
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

            {/* Funding Phase */}
            <div className="info-section" style={{ marginTop: '1.5rem' }}>
              <h2>Funding & Closing</h2>
              <p className="section-subtitle">Final funding and closing dates</p>
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
            <div className="info-section" style={{ marginTop: '1.5rem' }}>
              <h2>Post-Closing & Status</h2>
              <p className="section-subtitle">Post-funding and status change dates</p>
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
          )}

          {/* Milestones Tab */}
          {activeTab === 'milestones' && (
          <div className="tab-content">
            <div className="info-section">
              <h2>Loan Milestones</h2>
              <p className="section-subtitle">Track progress through key milestones in the loan process</p>

              {milestonesLoading ? (
                <div style={{ textAlign: 'center', padding: '40px', color: '#666' }}>
                  Loading milestones...
                </div>
              ) : milestones.length > 0 ? (
                <div className="milestones-timeline" style={{
                  position: 'relative',
                  paddingLeft: '2rem',
                  marginTop: '1.5rem'
                }}>
                  <div style={{
                    position: 'absolute',
                    left: '15px',
                    top: 0,
                    bottom: 0,
                    width: '2px',
                    background: '#e2e8f0'
                  }} />

                  {milestones.map((milestone, index) => {
                    const isCompleted = milestone.completed_at || milestone.status === 'completed';
                    const isCurrent = !isCompleted && index === milestones.findIndex(m => !m.completed_at && m.status !== 'completed');

                    return (
                      <div
                        key={milestone.id || index}
                        style={{
                          position: 'relative',
                          paddingBottom: '1.5rem',
                          paddingLeft: '1.5rem'
                        }}
                      >
                        <div style={{
                          position: 'absolute',
                          left: '-2rem',
                          width: '30px',
                          height: '30px',
                          background: isCompleted ? '#22c55e' : isCurrent ? '#3b82f6' : 'white',
                          border: `2px solid ${isCompleted ? '#22c55e' : isCurrent ? '#3b82f6' : '#e2e8f0'}`,
                          borderRadius: '50%',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          color: isCompleted || isCurrent ? 'white' : '#64748b',
                          zIndex: 1
                        }}>
                          {isCompleted ? '✓' : index + 1}
                        </div>

                        <div style={{
                          background: isCurrent ? '#eff6ff' : 'white',
                          border: `1px solid ${isCurrent ? '#3b82f6' : '#e2e8f0'}`,
                          borderRadius: '8px',
                          padding: '1rem'
                        }}>
                          <div style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'flex-start',
                            marginBottom: '0.5rem'
                          }}>
                            <h4 style={{ margin: 0, fontSize: '0.875rem', color: '#1e293b' }}>
                              {milestone.milestone_name || milestone.name}
                            </h4>
                            <span style={{
                              fontSize: '0.625rem',
                              padding: '0.25rem 0.5rem',
                              borderRadius: '4px',
                              fontWeight: 600,
                              textTransform: 'uppercase',
                              background: isCompleted ? '#dcfce7' : isCurrent ? '#dbeafe' : '#f3f4f6',
                              color: isCompleted ? '#166534' : isCurrent ? '#1e40af' : '#64748b'
                            }}>
                              {isCompleted ? 'Completed' : isCurrent ? 'In Progress' : 'Pending'}
                            </span>
                          </div>

                          {milestone.description && (
                            <p style={{
                              margin: '0.5rem 0',
                              fontSize: '0.75rem',
                              color: '#64748b'
                            }}>
                              {milestone.description}
                            </p>
                          )}

                          <div style={{
                            display: 'flex',
                            gap: '1rem',
                            fontSize: '0.75rem',
                            color: '#64748b',
                            marginTop: '0.5rem'
                          }}>
                            {milestone.target_date && (
                              <span>
                                Target: {new Date(milestone.target_date).toLocaleDateString()}
                              </span>
                            )}
                            {milestone.completed_at && (
                              <span style={{ color: '#166534' }}>
                                Completed: {new Date(milestone.completed_at).toLocaleDateString()}
                              </span>
                            )}
                          </div>

                          {milestone.notes && (
                            <p style={{
                              margin: '0.5rem 0 0',
                              fontSize: '0.75rem',
                              color: '#94a3b8',
                              fontStyle: 'italic'
                            }}>
                              {milestone.notes}
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{
                  textAlign: 'center',
                  padding: '40px',
                  background: '#f8fafc',
                  borderRadius: '8px',
                  color: '#64748b'
                }}>
                  <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📋</div>
                  <p>No milestones have been set up for this loan yet.</p>
                </div>
              )}
            </div>
          </div>
          )}

        </div>

        {/* Right Column - Actions & Email History */}
        <div className="right-column">
          {/* Upcoming Appointments */}
          <div className="appointments-card" style={{
            background: '#fff',
            borderRadius: '12px',
            padding: '20px',
            marginBottom: '20px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>📅 Upcoming Appointments</h3>
              <button
                onClick={() => setShowScheduleModal(true)}
                style={{
                  background: '#217F8D',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '6px 12px',
                  fontSize: '12px',
                  cursor: 'pointer'
                }}
              >
                + Schedule
              </button>
            </div>

            {appointmentsLoading ? (
              <div style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
                Loading appointments...
              </div>
            ) : upcomingAppointments.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {upcomingAppointments.slice(0, 5).map(apt => {
                  const aptDate = new Date(apt.scheduled_start);
                  const isToday = aptDate.toDateString() === new Date().toDateString();
                  const isTomorrow = aptDate.toDateString() === new Date(Date.now() + 86400000).toDateString();

                  return (
                    <div
                      key={apt.id}
                      style={{
                        background: isToday ? '#fef3c7' : '#f8fafc',
                        border: isToday ? '1px solid #f59e0b' : '1px solid #e2e8f0',
                        borderRadius: '8px',
                        padding: '12px',
                        position: 'relative'
                      }}
                    >
                      {isToday && (
                        <span style={{
                          position: 'absolute',
                          top: '-8px',
                          right: '8px',
                          background: '#f59e0b',
                          color: 'white',
                          fontSize: '10px',
                          padding: '2px 8px',
                          borderRadius: '10px',
                          fontWeight: 600
                        }}>
                          TODAY
                        </span>
                      )}
                      {isTomorrow && !isToday && (
                        <span style={{
                          position: 'absolute',
                          top: '-8px',
                          right: '8px',
                          background: '#3b82f6',
                          color: 'white',
                          fontSize: '10px',
                          padding: '2px 8px',
                          borderRadius: '10px',
                          fontWeight: 600
                        }}>
                          TOMORROW
                        </span>
                      )}
                      <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: '4px' }}>
                        {apt.title}
                      </div>
                      <div style={{ fontSize: '13px', color: '#64748b', marginBottom: '4px' }}>
                        {aptDate.toLocaleDateString('en-US', {
                          weekday: 'short',
                          month: 'short',
                          day: 'numeric'
                        })} at {aptDate.toLocaleTimeString('en-US', {
                          hour: 'numeric',
                          minute: '2-digit',
                          hour12: true
                        })}
                      </div>
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '12px' }}>
                        <span style={{
                          background: apt.meeting_mode === 'video' ? '#dbeafe' : apt.meeting_mode === 'phone' ? '#dcfce7' : '#f3e8ff',
                          color: apt.meeting_mode === 'video' ? '#1d4ed8' : apt.meeting_mode === 'phone' ? '#166534' : '#7c3aed',
                          padding: '2px 8px',
                          borderRadius: '4px'
                        }}>
                          {apt.meeting_mode === 'video' ? '📹 Video' : apt.meeting_mode === 'phone' ? '📞 Phone' : '👤 In Person'}
                        </span>
                        <span style={{ color: '#94a3b8' }}>
                          {apt.duration_minutes} min
                        </span>
                      </div>
                      {apt.video_link && (
                        <a
                          href={apt.video_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            display: 'inline-block',
                            marginTop: '8px',
                            color: '#217F8D',
                            fontSize: '12px',
                            textDecoration: 'none'
                          }}
                        >
                          🔗 Join Video Call
                        </a>
                      )}
                    </div>
                  );
                })}
                {upcomingAppointments.length > 5 && (
                  <div style={{ textAlign: 'center', fontSize: '13px', color: '#64748b' }}>
                    + {upcomingAppointments.length - 5} more appointments
                  </div>
                )}
              </div>
            ) : (
              <div style={{
                textAlign: 'center',
                padding: '24px 16px',
                color: '#94a3b8',
                background: '#f8fafc',
                borderRadius: '8px'
              }}>
                <div style={{ fontSize: '24px', marginBottom: '8px' }}>📅</div>
                <div style={{ fontSize: '14px' }}>No upcoming appointments</div>
                <button
                  onClick={() => setShowScheduleModal(true)}
                  style={{
                    marginTop: '12px',
                    background: 'none',
                    border: '1px solid #217F8D',
                    color: '#217F8D',
                    borderRadius: '6px',
                    padding: '8px 16px',
                    fontSize: '13px',
                    cursor: 'pointer'
                  }}
                >
                  Schedule Appointment
                </button>
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="actions-card">
            <h3>QUICK ACTIONS</h3>
            <div className="action-buttons">
              <button className="action-btn call" onClick={() => handleAction('call')} disabled={!(client.borrower_phone || client.phone)} title="Click to call">
                <span>Call</span>
              </button>
              <button className="action-btn sms" onClick={() => handleAction('sms')} disabled={!(client.borrower_phone || client.phone)} title="Send SMS">
                <span>SMS Text</span>
              </button>
              <button className="action-btn email" onClick={() => handleAction('email')} disabled={!(client.borrower_email || client.email)} title="Send email">
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
              <button className="action-btn voicemail" onClick={() => handleAction('voicemail')} disabled={!(client.borrower_phone || client.phone)} title="Drop voicemail">
                <span>Voicemail Drop</span>
              </button>
              <button className="action-btn record-video" onClick={() => setShowSendVideoModal(true)} disabled={!clientPortalData?.workspace_id} title={clientPortalData?.workspace_id ? "Record and send a video message" : "No client portal available"}>
                <span>Record Video</span>
              </button>
              <button className="action-btn application" onClick={() => handleAction('send_application')} disabled={applicationLoading} title="Send application link">
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

      {/* Video Call Schedule Modal */}
      <VideoCallScheduleModal
        isOpen={showVideoCall}
        onClose={() => setShowVideoCall(false)}
        borrower={client}
        onStartVideoCall={(data) => {
          console.log('Video call started:', data);
        }}
      />

      {/* Send Video Message Modal */}
      {client && clientPortalData?.workspace_id && (
        <SendVideoModal
          isOpen={showSendVideoModal}
          onClose={() => setShowSendVideoModal(false)}
          recipientType="client"
          recipientId={clientPortalData.workspace_id}
          recipientName={client?.borrower_name || client?.name || 'Client'}
          onSuccess={() => {
            console.log('Video sent successfully');
          }}
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
          phoneNumber={client.borrower_phone || client.phone}
          recipientName={client.borrower_name || client.name}
          onClose={() => setShowVoicemailDrop(false)}
        />
      )}

      {/* Schedule Appointment Modal */}
      {client && (
        <ScheduleAppointmentModal
          isOpen={showScheduleModal}
          onClose={() => setShowScheduleModal(false)}
          onSuccess={() => loadUpcomingAppointments()}
          borrower={client}
        />
      )}

      {/* Escalation Modal */}
      {client && (
        <EscalationModal
          isOpen={showEscalationModal}
          onClose={() => setShowEscalationModal(false)}
          lead={client}
        />
      )}

      {/* Create Task Modal */}
      {client && (
        <CreateTaskModal
          isOpen={showTaskModal}
          onClose={() => setShowTaskModal(false)}
          lead={client}
        />
      )}

      {/* Email Composer Modal */}
      <EmailComposerModal
        isOpen={showEmailComposer}
        onClose={() => setShowEmailComposer(false)}
        recipient={{
          name: client?.borrower_name || client?.name,
          email: client?.borrower_email || client?.email
        }}
        entityType="client"
        entityData={{
          id: client?.id,
          stage: client?.stage,
          loan_amount: client?.loan_amount
        }}
      />

      {/* Application Link Modal */}
      {showApplicationModal && applicationLink && (
        <div className="modal-overlay" onClick={() => setShowApplicationModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '500px' }}>
            <div className="modal-header">
              <h2>Application Link Created</h2>
              <button className="close-button" onClick={() => setShowApplicationModal(false)}>×</button>
            </div>
            <div style={{ padding: '20px' }}>
              <p style={{ marginBottom: '12px' }}>Share this link with the borrower:</p>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <input type="text" readOnly value={applicationLink.url} style={{ flex: 1, padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '13px' }} />
                <button onClick={async () => { try { await navigator.clipboard.writeText(applicationLink.url); toast.success('Link copied!'); } catch { toast.error('Copy failed'); } }} style={{ padding: '8px 16px', backgroundColor: '#218D8D', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', whiteSpace: 'nowrap' }}>Copy</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Client Portal Modal */}
      {showClientPortalModal && clientPortalData && (
        <div className="modal-overlay" onClick={() => setShowClientPortalModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '500px' }}>
            <div className="modal-header">
              <h2>{clientPortalData.justCreated ? 'Portal Created' : 'Client Portal'}</h2>
              <button className="close-button" onClick={() => setShowClientPortalModal(false)}>×</button>
            </div>
            <div style={{ padding: '20px' }}>
              <p style={{ marginBottom: '4px' }}><strong>Borrower:</strong> {clientPortalData.borrower_name}</p>
              <p style={{ marginBottom: '12px' }}><strong>Status:</strong> {clientPortalData.status}</p>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <input type="text" readOnly value={clientPortalData.url} style={{ flex: 1, padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '13px' }} />
                <button onClick={async () => { try { await navigator.clipboard.writeText(clientPortalData.url); toast.success('Link copied!'); } catch { toast.error('Copy failed'); } }} style={{ padding: '8px 16px', backgroundColor: '#218D8D', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', whiteSpace: 'nowrap' }}>Copy</button>
              </div>
              <button onClick={() => window.open(clientPortalData.url, '_blank')} style={{ marginTop: '12px', padding: '8px 16px', backgroundColor: '#3b82f6', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', width: '100%' }}>Open Portal</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ClientProfile;
