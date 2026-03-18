// VERSION: 2024-11-14-v2 - MOCK DATA FIX
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { leadsAPI, activitiesAPI, circleOfCashflowAPI, tasksAPI, loansAPI, dialerAPI, borrowerApplicationAPI, purlAPI, partnersAPI, API_BASE_URL } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import SMSModal from '../components/SMSModal';
import TeamsModal from '../components/TeamsModal';
import RecordingModal from '../components/RecordingModal';
import EscalationModal from '../components/EscalationModal';
import VoicemailDrop from '../components/VoicemailDrop';
import SendApplicationModal from '../components/SendApplicationModal';
import DispositionNoteModal from '../components/DispositionNoteModal';
import CreateTaskModal from '../components/CreateTaskModal';
import AppointmentModal from '../components/AppointmentModal';
import ScheduleAppointmentModal from '../components/ScheduleAppointmentModal';
import TeamAssignment from '../components/TeamAssignment';
import WorkflowRoleAssignment from '../components/WorkflowRoleAssignment';
import EmploymentTab from '../components/EmploymentTab';
import IncomeTab from '../components/income/IncomeTab';
import UnifiedIncomeCalculator from '../components/income/UnifiedIncomeCalculator';
import IncomeCalculator from '../components/IncomeCalculator';
import CreditTab from '../components/CreditTab';
import CallIntelligenceTab from '../components/call-intelligence/CallIntelligenceTab';
import VideoMeetings from '../components/VideoMeetings';
import VideoCallScheduleModal from '../components/VideoCallScheduleModal';
import EmailComposerModal from '../components/EmailComposerModal';
import CalendarSidebar from '../components/CalendarSidebar';
import NeedsListView from '../components/smart-docs/NeedsListView';
import SendVideoModal from '../components/video/SendVideoModal';
import SalesforceConnectionBadge from '../components/SalesforceConnectionBadge';
import { formatPhoneNumber } from '../utils/phoneUtils';
import CurrencyInput from '../components/common/CurrencyInput';
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

function LeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [lead, setLead] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(true); // Always in edit mode
  const [formData, setFormData] = useState({});
  const [emails, setEmails] = useState([]);
  const [activeTab, setActiveTab] = useState('loan-details');
  const [personalSubTab, setPersonalSubTab] = useState('info'); // 'info', 'employment', or 'assets'
  const [propertySubTab, setPropertySubTab] = useState('property'); // 'property', 'insurance', or 'legal'
  const [incomeCalcMode, setIncomeCalcMode] = useState('unified'); // 'unified', 'basic'
  const [noteText, setNoteText] = useState('');
  const [noteLoading, setNoteLoading] = useState(false);
  const [borrowers, setBorrowers] = useState([]);
  const [activeBorrower, setActiveBorrower] = useState(0);
  const [saveTimeout, setSaveTimeout] = useState(null);
  const [showSMSModal, setShowSMSModal] = useState(false);
  const [showTeamsModal, setShowTeamsModal] = useState(false);
  const [showRecordingModal, setShowRecordingModal] = useState(false);
  const [showVoicemailDrop, setShowVoicemailDrop] = useState(false);
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [showAppointmentModal, setShowAppointmentModal] = useState(false);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [calendarRefreshKey, setCalendarRefreshKey] = useState(0);
  const [showEscalationModal, setShowEscalationModal] = useState(false);
  const [showVideoMeetings, setShowVideoMeetings] = useState(false);
  const [showEmailComposer, setShowEmailComposer] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState('');
  const [showApplicationModal, setShowApplicationModal] = useState(false);
  const [applicationLink, setApplicationLink] = useState(null);
  const [dispositionModal, setDispositionModal] = useState({ show: false, status: null });
  const [applicationLoading, setApplicationLoading] = useState(false);

  // Client Portal (PURL) state
  const [showClientPortalModal, setShowClientPortalModal] = useState(false);
  const [clientPortalData, setClientPortalData] = useState(null);
  const [clientPortalLoading, setClientPortalLoading] = useState(false);

  // Video message modal state
  const [showSendVideoModal, setShowSendVideoModal] = useState(false);

  // Email drafts state
  const [emailDrafts, setEmailDrafts] = useState([]);
  const [selectedDraft, setSelectedDraft] = useState(null);
  const [showDraftModal, setShowDraftModal] = useState(false);
  const [draftLoading, setDraftLoading] = useState(false);
  const [ccRecipients, setCcRecipients] = useState([]);
  const [ccSearchQuery, setCcSearchQuery] = useState('');
  const [ccSearchResults, setCcSearchResults] = useState([]);
  const [ccSearchLoading, setCcSearchLoading] = useState(false);

  // Circle of Cashflow state
  const [cashflowOpportunities, setCashflowOpportunities] = useState([]);
  const [cashflowReferrals, setCashflowReferrals] = useState([]);
  const [cashflowPartners, setCashflowPartners] = useState([]);
  const [cashflowLoading, setCashflowLoading] = useState(false);

  // Stage History state
  const [stageHistory, setStageHistory] = useState([]);
  const [stageHistoryLoading, setStageHistoryLoading] = useState(false);

  // SLA Tracking state
  const [slaMeasures, setSlaMeasures] = useState([]);
  const [slaMilestones, setSlaMilestones] = useState([]);
  const [slaLoading, setSlaLoading] = useState(false);

  // Referral Partners state (for assigning lead to a partner)
  const [referralPartners, setReferralPartners] = useState([]);

  // Archive state
  const [archiveSubTab, setArchiveSubTab] = useState('notes'); // 'notes', 'email', 'sms', 'calls'
  const [emailArchive, setEmailArchive] = useState([]);
  const [smsArchive, setSmsArchive] = useState([]);
  const [callArchive, setCallArchive] = useState([]);
  const [archiveLoading, setArchiveLoading] = useState(false);

  // Documents state
  const [documents, setDocuments] = useState({
    income_verification: [],
    credit_reports: [],
    property_documents: [],
    disclosures_forms: [],
    bank_statements: [],
    other: [],
  });
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState(null);

  // Conditions state
  const [conditions, setConditions] = useState([]);
  const [conditionsLoading, setConditionsLoading] = useState(false);
  const [showAddConditionModal, setShowAddConditionModal] = useState(false);
  const [newCondition, setNewCondition] = useState({
    name: '',
    description: '',
    category: 'income_verification',
    priority: 'required',
    due_date: ''
  });
  const [addingCondition, setAddingCondition] = useState(false);

  // Status dropdown state
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);
  const [statusSaving, setStatusSaving] = useState(false);

  // Status options — all stages across Lead, Active Loan, and MUM
  const statusOptions = [
    // Lead stages
    { label: 'Lead Stages', isHeader: true },
    'New',
    'Attempted Contact',
    'Prospect',
    'Application',
    'Pre-Qualified',
    'Pre-Approved',
    'Long-Term Nurture',
    'Credit Repair',
    'Withdrawn',
    'Does Not Qualify',
    'Do Not Call',
    // Active Loan stages
    { label: 'Active Loan Stages', isHeader: true },
    'Disclosed',
    'Processing',
    'Submitted',
    'Underwriting',
    'UW Received',
    'Conditional Approval',
    'Approved',
    'Suspended',
    'CTC',
    'Clear to Close',
    'Closing',
    'Docs',
    'Docs Out',
    'Cancelled',
    'Denied',
    'Dead',
    // MUM (Funded)
    { label: 'MUM / Closed', isHeader: true },
    'Funded',
  ];

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
    { value: 'Life Insurance Agent', icon: '🛡️' },
    { value: 'Accountant', icon: '📊' },
    { value: 'Estate Planner', icon: '📜' },
    { value: 'Other Contact', icon: '🤝' }
  ];

  // Custom fields state
  const [customFields, setCustomFields] = useState([]);
  const [showAddFieldModal, setShowAddFieldModal] = useState(false);
  const [newFieldName, setNewFieldName] = useState('');

  // Workflow tasks state
  const [workflowTasks, setWorkflowTasks] = useState([]);
  const [workflowTasksLoading, setWorkflowTasksLoading] = useState(false);

  // Lead navigation state
  const [leadsList, setLeadsList] = useState([]);
  const [currentLeadIndex, setCurrentLeadIndex] = useState(-1);

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

  // Auto-load client portal workspace data on page load (for Record Video button)
  const loadClientPortalData = async (leadId) => {
    try {
      const existingWorkspace = await purlAPI.getWorkspaceByLead(leadId);
      if (existingWorkspace && existingWorkspace.workspace) {
        const workspaceId = existingWorkspace.workspace.workspace_id || existingWorkspace.workspace.id;
        const slug = existingWorkspace.workspace.workspace_slug || existingWorkspace.workspace.slug;

        // Build portal URL (without token for display purposes)
        const baseUrl = `${window.location.origin}/portal/${slug}`;

        setClientPortalData({
          workspace_id: workspaceId,
          url: baseUrl,
          borrower_name: existingWorkspace.workspace.display_name,
          status: existingWorkspace.workspace.status,
          exists: true
        });
      }
    } catch (err) {
      // Silently fail - workspace may not exist yet, which is fine
      console.log('[Client Portal] No existing workspace for this lead');
    }
  };

  useEffect(() => {
    loadLeadData();
    loadEmails();
    loadEmailDrafts();
    markLeadAsViewed();
    loadLeadsList();
    loadReferralPartners();
    loadClientPortalData(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Load referral partners for assignment dropdown
  const loadReferralPartners = async () => {
    try {
      const partners = await partnersAPI.getAll();
      setReferralPartners(partners || []);
    } catch (error) {
      console.error('Error loading referral partners:', error);
    }
  };

  // Load list of leads for navigation
  const loadLeadsList = async () => {
    try {
      let leads = [];
      try {
        const response = await leadsAPI.getAll();
        leads = response.leads || response || [];
      } catch (apiError) {
        // Fallback to mock data
        leads = generateMockLeads();
      }
      setLeadsList(leads);
      // Find current lead index
      const currentId = parseInt(id);
      const index = leads.findIndex(l => l.id === currentId);
      setCurrentLeadIndex(index);
    } catch (error) {
      console.error('Error loading leads list:', error);
    }
  };

  // Navigate to next lead
  const handleViewNextLead = () => {
    if (leadsList.length === 0) return;

    let nextIndex = currentLeadIndex + 1;
    if (nextIndex >= leadsList.length) {
      nextIndex = 0; // Loop back to first lead
    }

    const nextLead = leadsList[nextIndex];
    if (nextLead && nextLead.id) {
      navigate(`/leads/${nextLead.id}`);
    }
  };

  // Handle status change with auto-save
  const handleStatusChange = async (newStatus) => {
    // Statuses that require a disposition note
    if (DispositionNoteModal.REQUIRES_NOTE.includes(newStatus)) {
      setShowStatusDropdown(false);
      setDispositionModal({ show: true, status: newStatus });
      return;
    }

    await executeStatusChange(newStatus);
  };

  // Actual status change execution (called directly or after disposition note)
  const executeStatusChange = async (newStatus) => {
    setStatusSaving(true);
    setShowStatusDropdown(false);

    try {
      // Special handling for "Disclosed" or "Funded" - converts lead to loan
      if (newStatus === 'Disclosed' || newStatus === 'Funded') {
        // Generate a unique loan number from lead ID and timestamp
        const timestamp = Date.now().toString(36).toUpperCase();
        const loanNumber = `LEAD-${id}-${timestamp}`;

        // Build borrower name from available data — prefer first+last over lead.name
        const constructedName = `${formData?.first_name || lead?.first_name || ''} ${formData?.last_name || lead?.last_name || ''}`.trim();
        const borrowerName = constructedName || lead?.name || formData?.name || 'Unknown Borrower';

        // Get loan amount - default to 1 if not set (required field)
        const loanAmount = parseFloat(lead?.loan_amount || formData?.loan_amount || lead?.amount || formData?.amount) || 1;

        // Create a new loan from the lead data
        const loanData = {
          loan_number: loanNumber,
          borrower_name: borrowerName,
          borrower_email: lead?.email || formData?.email,
          borrower_phone: lead?.phone || formData?.phone,
          amount: loanAmount,
          stage: newStatus,  // Use selected stage (Disclosed or Funded)
          property_address: lead?.property_address || formData?.property_address,
        };

        console.log(`Converting lead to ${newStatus} loan with data:`, loanData);

        try {
          // Skip duplicate check when converting lead - user explicitly wants to create this loan
          const newLoan = await loansAPI.create(loanData, true);
          console.log('Loan created:', newLoan);

          // Try to update lead stage - but don't fail the whole conversion if this errors
          // (user might not have edit permission on the lead, but loan was created successfully)
          try {
            await leadsAPI.update(id, { stage: newStatus });
          } catch (leadUpdateError) {
            console.warn('Could not update lead stage (loan was created successfully):', leadUpdateError);
            // Continue with navigation - the loan was created which is the important part
          }

          // Clear caches
          localStorage.removeItem('leads_data');
          localStorage.removeItem('leads_data_time');
          localStorage.removeItem('loans_data');
          localStorage.removeItem('loans_data_time');

          // Show success toast with link to the new record
          const clientName = borrowerName || 'Client';
          if (newStatus === 'Funded') {
            toast.success(
              `${clientName} has been moved to Funded. <a href="/portfolio" style="color: white; font-weight: bold; text-decoration: underline;">View in Portfolio &rarr;</a>`,
              { duration: 8000 }
            );
          } else {
            toast.success(
              `${clientName} has been moved to ${newStatus}. <a href="/loans/${newLoan.id}" style="color: white; font-weight: bold; text-decoration: underline;">View Loan &rarr;</a>`,
              { duration: 8000 }
            );
          }

          // Funded leads move to portfolio — redirect to leads list
          if (newStatus === 'Funded') {
            navigate('/leads');
          } else {
            loadLeadData();
          }
          return;
        } catch (loanError) {
          console.error('Error creating loan:', loanError);
          console.error('Error details:', {
            message: loanError.message,
            response: loanError.response?.data,
            status: loanError.response?.status,
            config: loanError.config
          });

          let errorMessage = 'Failed to create loan';
          if (loanError.response?.data?.detail) {
            errorMessage = loanError.response.data.detail;
          } else if (loanError.response?.status === 401) {
            errorMessage = 'Session expired. Please log in again.';
          } else if (loanError.response?.status === 400) {
            errorMessage = loanError.response.data?.detail || 'Invalid loan data';
          } else if (loanError.message === 'Network Error') {
            errorMessage = 'Unable to connect to server. Please check your connection and try again.';
          } else {
            errorMessage = loanError.message || 'Unknown error';
          }

          toast.error(`Could not convert lead to ${newStatus}: ${errorMessage}`);
          setStatusSaving(false);
          return;
        }
      }

      // Update local state immediately
      setFormData(prev => ({ ...prev, stage: newStatus }));
      setLead(prev => ({ ...prev, stage: newStatus }));

      // Save to backend — response includes updated SLA dates
      const updatedLead = await leadsAPI.update(id, { stage: newStatus });

      // Update local state with SLA dates from response
      if (updatedLead) {
        const slaFields = [
          'lead_received_date', 'first_contact_attempt_date', 'first_contact_successful_date',
          'lead_qualification_date', 'initial_consultation_date', 'application_started_date',
          'application_completed_date', 'credit_pulled_date', 'preapproval_issued_date',
          'stage_changed_at',
        ];
        const slaUpdates = {};
        slaFields.forEach(f => {
          if (updatedLead[f] !== undefined) slaUpdates[f] = updatedLead[f];
        });
        if (Object.keys(slaUpdates).length > 0) {
          setFormData(prev => ({ ...prev, ...slaUpdates }));
          setLead(prev => ({ ...prev, ...slaUpdates }));
        }
      }

      // Clear leads cache so list view reflects the change
      localStorage.removeItem('leads_data');
      localStorage.removeItem('leads_data_time');

      console.log(`Status updated to: ${newStatus}`);
    } catch (error) {
      console.error('Error updating status:', error);
      toast.error(`Error updating status: ${error.message || 'Unknown error'}`);
      // Revert on error
      setFormData(prev => ({ ...prev, stage: lead?.stage }));
      setLead(prev => ({ ...prev, stage: lead?.stage }));
    } finally {
      setStatusSaving(false);
    }
  };

  // Get color for status badge
  const getStatusColor = (status) => {
    const colors = {
      // Lead stages
      'New': '#2196F3',
      'Attempted Contact': '#FF9800',
      'Prospect': '#9C27B0',
      'Application': '#00BCD4',
      'Pre-Qualified': '#4CAF50',
      'Pre-Approved': '#8BC34A',
      'Long-Term Nurture': '#607D8B',
      'Withdrawn': '#F44336',
      'Does Not Qualify': '#795548',
      // Active Loan stages
      'Disclosed': '#00C853',
      'Processing': '#FF9800',
      'Submitted': '#FF9800',
      'Underwriting': '#FFC107',
      'UW Received': '#FFC107',
      'Conditional Approval': '#00BCD4',
      'Approved': '#4CAF50',
      'Suspended': '#F44336',
      'CTC': '#4CAF50',
      'Clear to Close': '#4CAF50',
      'Closing': '#4CAF50',
      'Docs': '#4CAF50',
      'Docs Out': '#4CAF50',
      'Cancelled': '#F44336',
      'Denied': '#F44336',
      'Dead': '#9E9E9E',
      // MUM
      'Funded': '#FFD700',
    };
    return colors[status] || '#999';
  };

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
        // Load lead data first — activities failure should not block the page
        try {
          leadData = await leadsAPI.getById(leadIdInt);
          console.log('✅ Loaded lead from API:', leadData);
        } catch (leadError) {
          console.log('⚠️ Lead API failed. Error:', leadError);
          if (leadError?.response?.status === 404) {
            console.error('❌ Lead not found in database');
            setError('Lead not found. It may have been deleted.');
            setLoading(false);
            return;
          }
          const errorMessage = leadError?.response?.data?.detail || leadError?.message || 'Failed to load lead';
          console.error('❌ API Error:', errorMessage);
          setError(errorMessage);
          setLoading(false);
          return;
        }
        // Load activities separately — don't block lead display on failure
        try {
          activitiesData = await activitiesAPI.getAll({ lead_id: parseInt(id) });
          console.log('✅ Loaded activities from API:', activitiesData);
        } catch (actError) {
          console.warn('⚠️ Failed to load activities, continuing without them:', actError?.message);
          activitiesData = [];
        }
      } catch (apiError) {
        console.log('⚠️ API failed. Error:', apiError);
        const errorMessage = apiError?.response?.data?.detail || apiError?.message || 'Failed to load lead';
        console.error('❌ API Error:', errorMessage);
        setError(errorMessage);
        setLoading(false);
        return;
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
      toast.error('Failed to load lead details');
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

  // Load email drafts for this lead
  const loadEmailDrafts = async () => {
    try {
      const token = localStorage.getItem('token');
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction
        ? 'https://api.perenniaai.com'
        : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      const response = await fetch(`${API_BASE}/api/v1/email-drafts?lead_id=${id}&status=draft`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setEmailDrafts(data.drafts || data || []);
      }
    } catch (error) {
      console.error('Failed to load email drafts:', error);
    }
  };

  // Load stage history for Important Dates tab
  const loadStageHistory = async () => {
    if (!id) return;
    setStageHistoryLoading(true);
    try {
      const token = localStorage.getItem('token');
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction
        ? 'https://api.perenniaai.com'
        : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      const response = await fetch(`${API_BASE}/api/v1/leads/${id}/stage-history`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setStageHistory(data.stage_history || []);
      }
    } catch (error) {
      console.error('Failed to load stage history:', error);
    } finally {
      setStageHistoryLoading(false);
    }
  };

  // Load stage history when Important Dates tab is opened
  useEffect(() => {
    if (activeTab === 'important-dates' && id) {
      loadStageHistory();
      loadSlaData();
    }
  }, [activeTab, id]);

  // Load SLA measures and milestones for Important Dates tab
  const loadSlaData = async () => {
    if (!id) return;
    setSlaLoading(true);
    try {
      const token = localStorage.getItem('token');
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction
        ? 'https://api.perenniaai.com'
        : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      // Fetch SLA measures (configuration)
      const measuresResponse = await fetch(`${API_BASE}/api/v1/sla/measures?active_only=true`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      // Fetch milestone history for this lead
      const milestonesResponse = await fetch(`${API_BASE}/api/v1/sla/milestones/lead/${id}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (measuresResponse.ok) {
        const measuresData = await measuresResponse.json();
        // Filter for lead-stage measures only (those that apply during lead phase)
        const leadMeasures = measuresData.filter(m =>
          m.stage_type === 'lead' ||
          ['lead_response', 'pre_qualified', 'preapproval', 'documents_requested', 'documents_received', 'application_complete'].includes(m.milestone_type?.toLowerCase())
        );
        setSlaMeasures(leadMeasures);
      }

      if (milestonesResponse.ok) {
        const milestonesData = await milestonesResponse.json();
        setSlaMilestones(milestonesData || []);
      }
    } catch (error) {
      console.error('Failed to load SLA data:', error);
    } finally {
      setSlaLoading(false);
    }
  };

  // Search contacts for CC autocomplete
  const searchCcContacts = async (query) => {
    if (!query || query.length < 2) {
      setCcSearchResults([]);
      return;
    }

    setCcSearchLoading(true);
    try {
      const token = localStorage.getItem('token');
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction
        ? 'https://api.perenniaai.com'
        : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      const response = await fetch(`${API_BASE}/api/v1/contacts/search?q=${encodeURIComponent(query)}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setCcSearchResults(data.results || data || []);
      }
    } catch (error) {
      console.error('Failed to search contacts:', error);
    } finally {
      setCcSearchLoading(false);
    }
  };

  // Add CC recipient
  const addCcRecipient = (contact) => {
    if (!ccRecipients.find(c => c.email === contact.email)) {
      setCcRecipients([...ccRecipients, contact]);
    }
    setCcSearchQuery('');
    setCcSearchResults([]);
  };

  // Remove CC recipient
  const removeCcRecipient = (email) => {
    setCcRecipients(ccRecipients.filter(c => c.email !== email));
  };

  // Open draft for editing
  const openDraft = (draft) => {
    setSelectedDraft({
      ...draft,
      body_html: draft.body_html || '',
      subject: draft.subject || ''
    });
    setCcRecipients(draft.cc_emails || []);
    setShowDraftModal(true);
  };

  // Save draft changes
  const saveDraft = async () => {
    if (!selectedDraft) return;

    setDraftLoading(true);
    try {
      const token = localStorage.getItem('token');
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction
        ? 'https://api.perenniaai.com'
        : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      const response = await fetch(`${API_BASE}/api/v1/email-drafts/${selectedDraft.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          subject: selectedDraft.subject,
          body_html: selectedDraft.body_html,
          cc_emails: ccRecipients
        })
      });

      if (response.ok) {
        await loadEmailDrafts();
        toast.success('Draft saved successfully!');
      } else {
        throw new Error('Failed to save draft');
      }
    } catch (error) {
      console.error('Error saving draft:', error);
      toast.error('Failed to save draft');
    } finally {
      setDraftLoading(false);
    }
  };

  // Delete draft
  const deleteDraft = async () => {
    if (!selectedDraft) return;

    setDraftLoading(true);
    try {
      const token = localStorage.getItem('token');
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction
        ? 'https://api.perenniaai.com'
        : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      const response = await fetch(`${API_BASE}/api/v1/email-drafts/${selectedDraft.id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        setShowDraftModal(false);
        setSelectedDraft(null);
        await loadEmailDrafts();
        toast.success('Draft deleted');
      } else {
        throw new Error('Failed to delete draft');
      }
    } catch (error) {
      console.error('Error deleting draft:', error);
      toast.error('Failed to delete draft');
    } finally {
      setDraftLoading(false);
    }
  };

  // Send draft email
  const sendDraft = async () => {
    if (!selectedDraft) return;

    setDraftLoading(true);
    try {
      const token = localStorage.getItem('token');
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction
        ? 'https://api.perenniaai.com'
        : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      // First save any changes
      await fetch(`${API_BASE}/api/v1/email-drafts/${selectedDraft.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          subject: selectedDraft.subject,
          body_html: selectedDraft.body_html,
          cc_emails: ccRecipients
        })
      });

      // Then send
      const response = await fetch(`${API_BASE}/api/v1/email-drafts/${selectedDraft.id}/send`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        setShowDraftModal(false);
        setSelectedDraft(null);
        await loadEmailDrafts();
        await loadEmails();
        toast.success('Email sent successfully!');
      } else {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to send email');
      }
    } catch (error) {
      console.error('Error sending email:', error);
      toast.error('Failed to send email: ' + error.message);
    } finally {
      setDraftLoading(false);
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

  // Load workflow tasks when Tasks tab is selected
  const loadWorkflowTasks = async () => {
    if (!lead?.id) return;

    setWorkflowTasksLoading(true);
    try {
      // Use the new endpoint that handles stage-to-workflow mapping and day calculations
      const response = await fetch(`${API_BASE_URL}/api/v1/workflow-config/leads/${lead.id}/workflow-tasks`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();

        if (data.tasks && data.tasks.length > 0) {
          // Calculate due dates based on days_in_stage from API
          const daysInStage = data.days_in_stage || 1;

          // Filter to show tasks within the next 14 days and transform to match UI expectations
          const upcomingTasks = data.tasks
            .filter(task => task.day_value >= daysInStage && task.day_value <= daysInStage + 14)
            .map((task) => {
              const daysFromNow = task.day_value - daysInStage;
              const dueDate = new Date();
              dueDate.setDate(dueDate.getDate() + daysFromNow);

              return {
                id: task.id,
                dayLabel: task.day_label,
                dayValue: task.day_value,
                dueDate: dueDate.toISOString(),
                dueDateFormatted: dueDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }),
                daysFromNow: daysFromNow,
                taskDescription: task.task_description || `Day ${task.day_value} tasks`,
                phoneEnabled: task.communication_methods?.includes('phone') || false,
                textEnabled: task.communication_methods?.includes('text') || false,
                emailEnabled: task.communication_methods?.includes('email') || false,
                status: task.status === 'completed' ? 'completed' :
                        task.status === 'due_today' ? 'due_today' :
                        task.status === 'due_tomorrow' ? 'upcoming' : 'upcoming',
                workflowName: data.workflow?.name,
                workflowColor: data.workflow?.color
              };
            });

          setWorkflowTasks(upcomingTasks);
        } else {
          setWorkflowTasks([]);
        }
      } else {
        setWorkflowTasks([]);
      }
    } catch (error) {
      console.error('Error loading workflow tasks:', error);
      setWorkflowTasks([]);
    } finally {
      setWorkflowTasksLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'tasks' && lead) {
      loadWorkflowTasks();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, lead?.stage]);

  // Load documents when Documents tab is selected
  const loadDocuments = async () => {
    if (!id) return;

    setDocumentsLoading(true);
    setDocumentsError(null);
    try {
      const response = await leadsAPI.getDocuments(id);
      if (response && response.documents) {
        setDocuments(response.documents);
      }
    } catch (error) {
      console.error('Failed to load documents:', error);
      setDocumentsError('Failed to load documents');
    } finally {
      setDocumentsLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'documents' && id) {
      loadDocuments();
      loadConditions();
    }
    if (activeTab === 'conditions' && id) {
      loadConditions();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, id]);

  // Load conditions for the lead
  const loadConditions = async () => {
    if (!id) return;
    setConditionsLoading(true);
    try {
      const token = localStorage.getItem('token');
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction
        ? 'https://api.perenniaai.com'
        : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      const response = await fetch(`${API_BASE}/api/v1/leads/${id}/conditions`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      if (response.ok) {
        const data = await response.json();
        setConditions(data.conditions || []);
      }
    } catch (error) {
      console.error('Failed to load conditions:', error);
    } finally {
      setConditionsLoading(false);
    }
  };

  // Add a new condition
  const handleAddCondition = async (e) => {
    e.preventDefault();
    if (!newCondition.name.trim()) return;

    setAddingCondition(true);
    try {
      const token = localStorage.getItem('token');
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction
        ? 'https://api.perenniaai.com'
        : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      const response = await fetch(`${API_BASE}/api/v1/leads/${id}/conditions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          ...newCondition,
          lead_id: id,
          status: 'pending',
          notify_client: true
        })
      });

      if (response.ok) {
        const data = await response.json();
        setConditions(prev => [...prev, data.condition]);
        setShowAddConditionModal(false);
        setNewCondition({
          name: '',
          description: '',
          category: 'income_verification',
          priority: 'required',
          due_date: ''
        });
      }
    } catch (error) {
      console.error('Failed to add condition:', error);
    } finally {
      setAddingCondition(false);
    }
  };

  // Update condition status
  const updateConditionStatus = async (conditionId, newStatus) => {
    try {
      const token = localStorage.getItem('token');
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction
        ? 'https://api.perenniaai.com'
        : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      const response = await fetch(`${API_BASE}/api/v1/leads/${id}/conditions/${conditionId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ status: newStatus })
      });

      if (response.ok) {
        setConditions(prev => prev.map(c =>
          c.id === conditionId ? { ...c, status: newStatus } : c
        ));
      }
    } catch (error) {
      console.error('Failed to update condition:', error);
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

      // Keep editing mode active so user can continue making changes
      // setEditing(false);  // Removed - stay in edit mode after save

      // Show a brief success indicator instead of alert
      console.log('Lead updated successfully!');
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

  // Stable callback for income changes to prevent infinite loops
  const handleIncomeChange = useCallback((monthly, annual) => {
    // Only update if values actually changed
    setFormData(prev => {
      if (prev.monthly_income !== monthly || prev.annual_income !== annual) {
        return { ...prev, monthly_income: monthly, annual_income: annual };
      }
      return prev;
    });
  }, []);

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
        detail: { transcript, leadId: lead.id }
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

  // Handle sending application link to lead
  const handleSendApplication = async () => {
    if (!lead) return;

    try {
      setApplicationLoading(true);

      // Create application for this lead
      const response = await borrowerApplicationAPI.createForLead(lead.id, {
        send_email: false,  // Don't auto-send email, show modal first
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

  // Copy application link to clipboard
  const copyApplicationLink = async () => {
    if (!applicationLink?.url) return;

    try {
      await navigator.clipboard.writeText(applicationLink.url);
      toast.success('Application link copied to clipboard!');
    } catch (err) {
      console.error('Failed to copy:', err);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = applicationLink.url;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      toast.success('Application link copied to clipboard!');
    }
  };

  // Handle opening/creating client portal
  const handleClientPortal = async () => {
    if (!lead) return;

    try {
      setClientPortalLoading(true);
      console.log('[Client Portal] Starting for lead:', lead.id);

      // First check if a portal already exists for this lead
      let existingWorkspace = null;
      try {
        console.log('[Client Portal] Checking for existing workspace...');
        existingWorkspace = await purlAPI.getWorkspaceByLead(lead.id);
        console.log('[Client Portal] Workspace check result:', existingWorkspace);
      } catch (err) {
        // 404 means no workspace exists - we'll create one
        // Network errors also mean we should try to create a new one
        const isNotFound = err.response?.status === 404;
        const isNetworkError = err.message === 'Network Error' || !err.response;

        console.log('[Client Portal] Workspace check error:', {
          status: err.response?.status,
          message: err.message,
          isNotFound,
          isNetworkError
        });

        if (!isNotFound && !isNetworkError) {
          // Unexpected error - throw it
          throw err;
        }
        // Otherwise continue to create a new workspace
      }

      // If workspace exists, use it
      if (existingWorkspace && existingWorkspace.workspace) {
        console.log('[Client Portal] Using existing workspace');
        const workspaceId = existingWorkspace.workspace.workspace_id || existingWorkspace.workspace.id;
        const slug = existingWorkspace.workspace.workspace_slug || existingWorkspace.workspace.slug;

        // Create a new token so we have the full token string for the URL
        const tokenResponse = await purlAPI.createToken(workspaceId, {
          scope: 'full',
          expires_in_days: 90
        });
        const fullToken = tokenResponse.token;

        // Build portal URL with token
        const baseUrl = `${window.location.origin}/portal/${slug}`;
        const portalUrl = fullToken ? `${baseUrl}?token=${fullToken}` : baseUrl;

        setClientPortalData({
          workspace_id: workspaceId,
          url: portalUrl,
          borrower_name: existingWorkspace.workspace.display_name,
          status: existingWorkspace.workspace.status,
          exists: true
        });
        setShowClientPortalModal(true);
        return;
      }

      // Create new portal for this lead
      console.log('[Client Portal] Creating new workspace...');
      const borrowerName = lead.name || `${lead.first_name || ''} ${lead.last_name || ''}`.trim();
      const createData = {
        lead_id: lead.id,
        borrower_name: borrowerName,
        first_name: lead.first_name,
        last_name: lead.last_name,
        email: lead.email,
        phone: lead.phone
      };

      console.log('[Client Portal] Create data:', createData);
      const response = await purlAPI.createWorkspace(createData);
      console.log('[Client Portal] Workspace created:', response);
      const newWorkspace = response.workspace || response;

      // Create an access token for the workspace and capture the full token
      const tokenResponse = await purlAPI.createToken(newWorkspace.id, {
        scope: 'full',
        expires_in_days: 90
      });
      const fullToken = tokenResponse.token;

      // Build portal URL with token included
      const baseUrl = `${window.location.origin}/portal/${newWorkspace.slug}`;
      const portalUrl = fullToken ? `${baseUrl}?token=${fullToken}` : baseUrl;

      setClientPortalData({
        workspace_id: newWorkspace.id,
        url: portalUrl,
        borrower_name: borrowerName,
        status: newWorkspace.status,
        exists: false,
        justCreated: true
      });
      setShowClientPortalModal(true);
    } catch (err) {
      console.error('[Client Portal] Error:', err);

      // Provide more helpful error messages
      let errorMessage = 'Unknown error occurred';
      if (err.response?.data?.detail) {
        errorMessage = err.response.data.detail;
      } else if (err.message === 'Network Error') {
        errorMessage = 'Unable to connect to server. Please check your internet connection and try again.';
      } else if (err.message) {
        errorMessage = err.message;
      }

      toast.error(`Failed to access/create client portal: ${errorMessage}`);
    } finally {
      setClientPortalLoading(false);
    }
  };

  // Copy client portal link to clipboard
  const copyClientPortalLink = async () => {
    if (!clientPortalData?.url) return;

    try {
      await navigator.clipboard.writeText(clientPortalData.url);
      toast.success('Client portal link copied to clipboard!');
    } catch (err) {
      console.error('Failed to copy:', err);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = clientPortalData.url;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      toast.success('Client portal link copied to clipboard!');
    }
  };

  const handleAction = async (action) => {
    switch(action) {
      case 'call':
        // Use click-to-dial - calls your phone first, then bridges to the contact
        if (!lead.phone) {
          toast.error('No phone number available for this lead');
          return;
        }
        try {
          // Clean up phone number (remove formatting)
          const cleanPhone = lead.phone.replace(/[^\d+]/g, '');
          const result = await dialerAPI.clickToDial({
            phone_number: cleanPhone,
            contact_name: lead.name || 'Contact',
            lead_id: lead.id
          });
          if (result.success) {
            toast.success(`Calling your phone now... When you answer, you'll be connected to ${lead.name || 'the contact'}.`);
          } else {
            // If click-to-dial fails (no settings configured), fall back to tel: link
            if (result.error?.includes('cell phone not configured') || result.error?.includes('caller ID')) {
              toast.error('Click-to-dial is not configured. Please set up your phone number in Settings > Telephony.\n\nFalling back to phone app...');
              window.open(`tel:${lead.phone}`, '_self');
            } else {
              toast.error(`Call failed: ${result.error || 'Unknown error'}`);
            }
          }
        } catch (err) {
          console.error('Click-to-dial error:', err);
          // Fall back to tel: link if API call fails
          toast.error('Click-to-dial service unavailable. Opening phone app instead...');
          window.open(`tel:${lead.phone}`, '_self');
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
      case 'escalation':
        setShowEscalationModal(true);
        break;
      case 'send_application':
        handleSendApplication();
        break;
      case 'client_portal':
        handleClientPortal();
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

  if (error) {
    return (
      <div className="lead-detail-page">
        <div className="error-container" style={{ padding: '40px', textAlign: 'center' }}>
          <h2 style={{ color: '#ef4444', marginBottom: '16px' }}>Error Loading Lead</h2>
          <p style={{ color: '#6b7280', marginBottom: '24px' }}>{error}</p>
          <button
            onClick={() => navigate('/leads')}
            style={{
              padding: '12px 24px',
              backgroundColor: '#3b82f6',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '14px'
            }}
          >
            ← Back to Leads
          </button>
        </div>
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
    <div className="lead-detail-page-wrapper">
      <div className="lead-detail-page">
        {/* Header */}
        <div className="detail-header">
          <div className="nav-buttons">
            <button className="btn-back" onClick={() => navigate('/leads')}>
              ← Back to Leads
            </button>
          <button className="btn-next" onClick={handleViewNextLead} disabled={leadsList.length === 0}>
            View Next Lead →
          </button>

          {/* Status Dropdown */}
          <div className="status-dropdown-container">
            <button
              className="btn-status"
              onClick={() => setShowStatusDropdown(!showStatusDropdown)}
              disabled={statusSaving}
              style={{
                backgroundColor: getStatusColor(formData.stage || lead?.stage || 'New'),
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: '500',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                minWidth: '150px',
                justifyContent: 'space-between'
              }}
            >
              {statusSaving ? 'Saving...' : (formData.stage || lead?.stage || 'New')}
              <span style={{ fontSize: '10px' }}>▼</span>
            </button>

            {showStatusDropdown && (
              <>
                <div
                  className="status-dropdown-overlay"
                  onClick={() => setShowStatusDropdown(false)}
                  style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    zIndex: 999
                  }}
                />
                <div
                  className="status-dropdown-menu"
                  style={{
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
                    overflowY: 'auto'
                  }}
                >
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
                          padding: '12px 16px',
                          border: 'none',
                          background: (formData.stage || lead?.stage) === status ? '#f0f0f0' : 'white',
                          cursor: 'pointer',
                          textAlign: 'left',
                          fontSize: '14px',
                          borderLeft: `4px solid ${getStatusColor(status)}`,
                          transition: 'background 0.2s'
                        }}
                        onMouseEnter={(e) => e.target.style.background = '#f5f5f5'}
                        onMouseLeave={(e) => e.target.style.background = (formData.stage || lead?.stage) === status ? '#f0f0f0' : 'white'}
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
        justifyContent: 'space-between'
      }}>
        <h2 style={{
          margin: 0,
          fontSize: '20px',
          fontWeight: '600',
          color: '#1a1a2e'
        }}>
          {formData.first_name || formData.last_name
            ? `${formData.first_name || ''} ${formData.last_name || ''}`.trim()
            : lead?.first_name || lead?.last_name
              ? `${lead?.first_name || ''} ${lead?.last_name || ''}`.trim()
              : 'Unknown Client'}
        </h2>
        {/* Salesforce Connection Indicator */}
        <SalesforceConnectionBadge
          entityType="lead"
          entityId={id}
          salesforceId={lead?.salesforce_id}
          lastSyncedAt={lead?.salesforce_last_synced_at}
        />
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
          className={`tab-btn ${activeTab === 'income' ? 'active' : ''}`}
          onClick={() => setActiveTab('income')}
        >
          Income
        </button>
        <button
          className={`tab-btn ${activeTab === 'credit' ? 'active' : ''}`}
          onClick={() => setActiveTab('credit')}
        >
          Credit
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
                  <CurrencyInput
                    value={formData.purchase_price || ''}
                    onChange={(value) => handleFieldChange('purchase_price', value)}
                    placeholder="$0"
                  />
                </div>
              )}

              <div className="info-field">
                <label>Loan Amount</label>
                <CurrencyInput
                  value={formData.loan_amount || ''}
                  onChange={(value) => handleFieldChange('loan_amount', value)}
                  placeholder="$0"
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
                <CurrencyInput
                  value={formData.appraisal_value || ''}
                  onChange={(value) => handleFieldChange('appraisal_value', value)}
                  placeholder="$0"
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

              <div className="info-field">
                <label>CLTV %</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.cltv || ''}
                  onChange={(e) => handleFieldChange('cltv', e.target.value)}
                  placeholder="%"
                />
              </div>
            </div>

            {/* 1st Loan Financial Details - Salesforce Sync */}
            <h3 style={{ margin: '2rem 0 1rem 0', fontSize: '16px', fontWeight: '600', color: '#333', borderTop: '1px solid #e0e0e0', paddingTop: '1.5rem' }}>
              1st Loan Financial Details
              <span style={{ fontSize: '12px', fontWeight: '400', color: '#666', marginLeft: '8px' }}>(Synced from Salesforce)</span>
            </h3>
            <div className="info-grid">
              <div className="info-field">
                <label>Rate Type</label>
                <select
                  value={formData.rate_type || ''}
                  onChange={(e) => handleFieldChange('rate_type', e.target.value)}
                >
                  <option value="">Select...</option>
                  <option value="Fixed">Fixed</option>
                  <option value="ARM">ARM</option>
                  <option value="5/1 ARM">5/1 ARM</option>
                  <option value="7/1 ARM">7/1 ARM</option>
                  <option value="10/1 ARM">10/1 ARM</option>
                </select>
              </div>
              <div className="info-field">
                <label>Monthly P&I Payment</label>
                <CurrencyInput
                  value={formData.monthly_payment || ''}
                  onChange={(value) => handleFieldChange('monthly_payment', value)}
                  placeholder="$0"
                />
              </div>
              <div className="info-field">
                <label>Property Tax (Annual)</label>
                <CurrencyInput
                  value={formData.property_tax || ''}
                  onChange={(value) => handleFieldChange('property_tax', value)}
                  placeholder="$0"
                />
              </div>
              <div className="info-field">
                <label>Hazard Insurance (Monthly)</label>
                <CurrencyInput
                  value={formData.hazard_insurance || ''}
                  onChange={(value) => handleFieldChange('hazard_insurance', value)}
                  placeholder="$0"
                />
              </div>
              <div className="info-field">
                <label>Mortgage Insurance (Monthly)</label>
                <CurrencyInput
                  value={formData.mortgage_insurance || ''}
                  onChange={(value) => handleFieldChange('mortgage_insurance', value)}
                  placeholder="$0"
                />
              </div>
              <div className="info-field">
                <label>HOA (Monthly)</label>
                <CurrencyInput
                  value={formData.hoa_amount || ''}
                  onChange={(value) => handleFieldChange('hoa_amount', value)}
                  placeholder="$0"
                />
              </div>
              <div className="info-field">
                <label>Origination Fee</label>
                <CurrencyInput
                  value={formData.origination_fee || ''}
                  onChange={(value) => handleFieldChange('origination_fee', value)}
                  placeholder="$0"
                />
              </div>
              <div className="info-field">
                <label>Est. Prepaid Interest</label>
                <CurrencyInput
                  value={formData.estimated_prepaid_interest || ''}
                  onChange={(value) => handleFieldChange('estimated_prepaid_interest', value)}
                  placeholder="$0"
                />
              </div>
            </div>

            {/* ARM Details - Only show if Rate Type is ARM */}
            {formData.rate_type && formData.rate_type.includes('ARM') && (
              <>
                <h4 style={{ margin: '1.5rem 0 1rem 0', fontSize: '14px', fontWeight: '600', color: '#666' }}>ARM Details</h4>
                <div className="info-grid">
                  <div className="info-field">
                    <label>Index Rate</label>
                    <input
                      type="number"
                      step="0.001"
                      value={formData.index_rate || ''}
                      onChange={(e) => handleFieldChange('index_rate', parseFloat(e.target.value))}
                      placeholder="%"
                    />
                  </div>
                  <div className="info-field">
                    <label>Margin</label>
                    <input
                      type="number"
                      step="0.001"
                      value={formData.margin || ''}
                      onChange={(e) => handleFieldChange('margin', parseFloat(e.target.value))}
                      placeholder="%"
                    />
                  </div>
                </div>
              </>
            )}

            {/* Present vs Proposed Section */}
            <h3 style={{ margin: '2rem 0 1rem 0', fontSize: '16px', fontWeight: '600', color: '#333', borderTop: '1px solid #e0e0e0', paddingTop: '1.5rem' }}>
              Present vs Proposed Housing
            </h3>
            <div className="info-grid">
              <div className="info-field">
                <label>Present Monthly Payment</label>
                <CurrencyInput
                  value={formData.present_monthly_payment || ''}
                  onChange={(value) => handleFieldChange('present_monthly_payment', value)}
                  placeholder="$0"
                />
              </div>
              <div className="info-field">
                <label>Proposed Monthly Payment</label>
                <CurrencyInput
                  value={formData.proposed_monthly_payment || ''}
                  onChange={(value) => handleFieldChange('proposed_monthly_payment', value)}
                  placeholder="$0"
                />
              </div>
              <div className="info-field">
                <label>Present Housing Expense</label>
                <CurrencyInput
                  value={formData.present_housing_expense || ''}
                  onChange={(value) => handleFieldChange('present_housing_expense', value)}
                  placeholder="$0"
                />
              </div>
              <div className="info-field">
                <label>Proposed Housing Expense</label>
                <CurrencyInput
                  value={formData.proposed_housing_expense || ''}
                  onChange={(value) => handleFieldChange('proposed_housing_expense', value)}
                  placeholder="$0"
                />
              </div>
            </div>

            {/* 2nd Loan Details */}
            <h3 style={{ margin: '2rem 0 1rem 0', fontSize: '16px', fontWeight: '600', color: '#333', borderTop: '1px solid #e0e0e0', paddingTop: '1.5rem' }}>
              2nd Loan Details
              <span style={{ fontSize: '12px', fontWeight: '400', color: '#666', marginLeft: '8px' }}>(If Applicable)</span>
            </h3>
            <div className="info-grid">
              <div className="info-field">
                <label>2nd Loan Amount</label>
                <CurrencyInput
                  value={formData.second_loan_amount || ''}
                  onChange={(value) => handleFieldChange('second_loan_amount', value)}
                  placeholder="$0"
                />
              </div>
              <div className="info-field">
                <label>2nd Loan Rate</label>
                <input
                  type="number"
                  step="0.001"
                  value={formData.second_loan_rate || ''}
                  onChange={(e) => handleFieldChange('second_loan_rate', parseFloat(e.target.value))}
                  placeholder="%"
                />
              </div>
              <div className="info-field">
                <label>2nd Loan Payment</label>
                <CurrencyInput
                  value={formData.second_loan_payment || ''}
                  onChange={(value) => handleFieldChange('second_loan_payment', value)}
                  placeholder="$0"
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

            {/* Sub-tabs for Personal Information and Employment */}
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
                onClick={() => setPersonalSubTab('income')}
                style={{
                  padding: '10px 20px',
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: personalSubTab === 'income' ? '600' : '400',
                  color: personalSubTab === 'income' ? '#1a73e8' : '#5f6368',
                  borderBottom: personalSubTab === 'income' ? '2px solid #1a73e8' : '2px solid transparent',
                  marginBottom: '-1px'
                }}
              >
                Income
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
                  onChange={(e) => handleFieldChange('phone', formatPhoneNumber(e.target.value))}
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
              <div className="info-field">
                <label>Referral Partner</label>
                <select
                  value={formData.referral_partner_id || ''}
                  onChange={(e) => handleFieldChange('referral_partner_id', e.target.value ? parseInt(e.target.value) : null)}
                  style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ddd', fontSize: '14px' }}
                >
                  <option value="">-- No Partner Assigned --</option>
                  {referralPartners.map(partner => (
                    <option key={partner.id} value={partner.id}>
                      {partner.name} {partner.company ? `(${partner.company})` : ''}
                    </option>
                  ))}
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
                entityType="leads"
              />
            )}

            {/* Income Sub-tab Content */}
            {personalSubTab === 'income' && (
              <IncomeTab
                borrowerId={parseInt(id)}
                loanId={lead?.loan_id || parseInt(id)}
                onIncomeChange={handleIncomeChange}
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
                      <label>Real Estate (Other Properties)</label>
                      <input
                        type="text"
                        value={formData.other_real_estate_value || ''}
                        onChange={(e) => handleFieldChange('other_real_estate_value', e.target.value)}
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
                      <label>Life Insurance Cash Value</label>
                      <input
                        type="text"
                        value={formData.life_insurance_value || ''}
                        onChange={(e) => handleFieldChange('life_insurance_value', e.target.value)}
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

                {/* Gift Funds Section */}
                <div style={{ marginBottom: '2rem' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Gift Funds</h3>
                  <div className="info-grid compact">
                    <div className="info-field">
                      <label>Gift Amount</label>
                      <input
                        type="text"
                        value={formData.gift_amount || ''}
                        onChange={(e) => handleFieldChange('gift_amount', e.target.value)}
                        placeholder="$0.00"
                      />
                    </div>
                    <div className="info-field">
                      <label>Gift Donor Name</label>
                      <input
                        type="text"
                        value={formData.gift_donor_name || ''}
                        onChange={(e) => handleFieldChange('gift_donor_name', e.target.value)}
                        placeholder="Donor's full name"
                      />
                    </div>
                    <div className="info-field">
                      <label>Gift Donor Relationship</label>
                      <select
                        value={formData.gift_donor_relationship || ''}
                        onChange={(e) => handleFieldChange('gift_donor_relationship', e.target.value)}
                        style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ddd', fontSize: '14px' }}
                      >
                        <option value="">-- Select Relationship --</option>
                        <option value="parent">Parent</option>
                        <option value="grandparent">Grandparent</option>
                        <option value="sibling">Sibling</option>
                        <option value="spouse">Spouse</option>
                        <option value="other_relative">Other Relative</option>
                        <option value="employer">Employer</option>
                        <option value="other">Other</option>
                      </select>
                    </div>
                  </div>
                </div>

                {/* Total Assets Summary */}
                <div style={{
                  background: '#f8f9fa',
                  padding: '1rem',
                  borderRadius: '8px',
                  marginTop: '1rem',
                  border: '1px solid #e0e0e0'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: '600', color: '#333' }}>Total Assets</span>
                    <span style={{ fontWeight: '700', fontSize: '18px', color: '#1a73e8' }}>
                      ${(
                        parseFloat((formData.checking_balance || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.savings_balance || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.money_market_balance || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.cd_balance || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.stocks_bonds_value || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.mutual_funds_value || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.brokerage_value || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.retirement_401k || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.ira_balance || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.roth_ira_balance || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.pension_value || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.other_real_estate_value || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.vehicle_value || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.life_insurance_value || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.other_assets_value || '0').replace(/[^0-9.-]/g, '')) +
                        parseFloat((formData.gift_amount || '0').replace(/[^0-9.-]/g, ''))
                      ).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
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
                    <CurrencyInput
                      value={formData.property_value || ''}
                      onChange={(value) => handleFieldChange('property_value', value)}
                      placeholder="$0"
                    />
                  </div>
                  <div className="info-field">
                    <label>Down Payment</label>
                    <CurrencyInput
                      value={formData.down_payment || ''}
                      onChange={(value) => handleFieldChange('down_payment', value)}
                      placeholder="$0"
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
                        onChange={(e) => handleFieldChange('homeowner_insurance_phone', formatPhoneNumber(e.target.value))}
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
                          onChange={(e) => handleFieldChange('flood_insurance_phone', formatPhoneNumber(e.target.value))}
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
                        onChange={(e) => handleFieldChange('closing_phone', formatPhoneNumber(e.target.value))}
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
                        onChange={(e) => handleFieldChange('closing_fax', formatPhoneNumber(e.target.value))}
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

          {/* Team Members Tab */}
          {activeTab === 'team' && (
          <div className="info-section">
            <h2>Team Members</h2>

            {/* Workflow Role Assignments */}
            <div style={{ marginBottom: '24px' }}>
              <WorkflowRoleAssignment
                onUpdate={() => {
                  // Optionally refresh data when assignments change
                }}
              />
            </div>

            <div style={{ marginTop: '24px' }}>
              <h3 style={{ marginBottom: '16px', color: '#333', fontSize: '16px' }}>General Team Assignments</h3>
              <TeamAssignment leadId={id} />
            </div>
          </div>
          )}

          {/* Call Intelligence Tab */}
          {activeTab === 'call-intelligence' && (
          <div className="info-section call-intelligence-section">
            <CallIntelligenceTab
              clientId={id}
              loanId={lead?.loan_id}
              leadId={id}
            />
          </div>
          )}

          {/* Tasks Tab */}
          {activeTab === 'tasks' && (
          <div className="info-section">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h2 style={{ margin: 0 }}>Tasks</h2>
              <button
                onClick={() => setShowTaskModal(true)}
                style={{
                  background: 'linear-gradient(135deg, #218D8D 0%, #10b981 100%)',
                  color: 'white',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: '8px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '14px',
                  transition: 'transform 0.2s, box-shadow 0.2s'
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(33, 141, 141, 0.3)';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              >
                <span style={{ fontSize: '18px' }}>+</span> Add Task
              </button>
            </div>
            <div className="tasks-content">
              <p className="section-description" style={{ color: '#666', marginBottom: '20px' }}>
                Upcoming tasks for the next 2 weeks based on status: <strong>{lead?.stage || 'Unknown'}</strong>
              </p>

              {workflowTasksLoading ? (
                <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '40px', textAlign: 'center', color: '#666' }}>
                  Loading workflow tasks...
                </div>
              ) : workflowTasks.length === 0 ? (
                <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '40px', textAlign: 'center', color: '#666' }}>
                  <p style={{ marginBottom: '12px' }}>No upcoming tasks for this stage.</p>
                  <p style={{ fontSize: '13px' }}>Configure workflows in <strong>Settings &gt; Workflow Configuration</strong></p>
                </div>
              ) : (
                <div className="workflow-tasks-list">
                  {workflowTasks.map((task) => (
                    <div
                      key={task.id}
                      style={{
                        backgroundColor: task.status === 'due_today' ? '#fff8e1' : task.status === 'overdue' ? '#ffebee' : '#fff',
                        border: `1px solid ${task.status === 'due_today' ? '#ffca28' : task.status === 'overdue' ? '#ef5350' : '#e0e0e0'}`,
                        borderRadius: '8px',
                        padding: '16px',
                        marginBottom: '12px',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                          <span style={{
                            backgroundColor: task.status === 'due_today' ? '#ff9800' : task.status === 'overdue' ? '#f44336' : '#1976d2',
                            color: '#fff',
                            padding: '4px 10px',
                            borderRadius: '12px',
                            fontSize: '12px',
                            fontWeight: '600'
                          }}>
                            {task.status === 'due_today' ? 'Due Today' : task.status === 'overdue' ? 'Overdue' : task.dueDateFormatted}
                          </span>
                          <span style={{
                            backgroundColor: '#e3f2fd',
                            color: '#1976d2',
                            padding: '4px 10px',
                            borderRadius: '12px',
                            fontSize: '12px',
                            fontWeight: '600'
                          }}>
                            {task.dayLabel}
                          </span>
                        </div>
                        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                          {task.phoneEnabled && (
                            <span title={`Phone call${task.phoneAmEnabled ? ' (AM)' : ''}${task.phonePmEnabled ? ' (PM)' : ''}`} style={{ fontSize: '16px' }}>📞</span>
                          )}
                          {task.textEnabled && (
                            <span title={`Text message${task.textAmEnabled ? ' (AM)' : ''}${task.textPmEnabled ? ' (PM)' : ''}`} style={{ fontSize: '16px' }}>💬</span>
                          )}
                          {task.emailEnabled && (
                            <span title="Email" style={{ fontSize: '16px' }}>📧</span>
                          )}
                          {task.referralPartnerEnabled && (
                            <span title="Referral partner" style={{ fontSize: '16px' }}>🤝</span>
                          )}
                        </div>
                      </div>
                      <p style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#333', lineHeight: '1.5' }}>
                        {task.taskDescription}
                      </p>
                      {Object.keys(task.roleResponsibilities || {}).length > 0 && (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                          {Object.entries(task.roleResponsibilities).map(([role, isResponsible]) =>
                            isResponsible && (
                              <span
                                key={role}
                                style={{
                                  backgroundColor: '#f5f5f5',
                                  color: '#555',
                                  padding: '3px 8px',
                                  borderRadius: '4px',
                                  fontSize: '11px'
                                }}
                              >
                                {role.replace(/_/g, ' ')}
                              </span>
                            )
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          )}

          {/* Conversation Log Tab */}
          {activeTab === 'conversation' && (
          <div className="info-section">
            <h2>Conversation Log</h2>

            {/* Archive Sub-Tabs */}
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

            {/* Notes Sub-Tab */}
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

            {/* Email Archive Sub-Tab */}
            {archiveSubTab === 'email' && (
              <div className="archive-content">
                <div className="archive-header">
                  <h3>Email History</h3>
                  <p className="archive-description">All emails sent to and received from this lead</p>
                </div>
                {archiveLoading ? (
                  <div className="loading-state">Loading emails...</div>
                ) : emailArchive.length > 0 ? (
                  <div className="archive-list">
                    {emailArchive.map((email, idx) => (
                      <div key={email.id || idx} className="archive-item email-item">
                        <div className="archive-item-header">
                          <span className={`archive-direction ${email.direction || 'outbound'}`}>
                            {email.direction === 'inbound' ? '📥 Received' : '📤 Sent'}
                          </span>
                          <span className="archive-date">
                            {new Date(email.sent_at || email.created_at).toLocaleString()}
                          </span>
                        </div>
                        <div className="archive-item-subject">
                          <strong>Subject:</strong> {email.subject || 'No Subject'}
                        </div>
                        <div className="archive-item-preview">
                          {email.body_text?.substring(0, 200) || email.body?.substring(0, 200) || 'No content'}
                          {(email.body_text?.length > 200 || email.body?.length > 200) && '...'}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <div className="empty-icon">📧</div>
                    <p>No emails found for this lead</p>
                    <button
                      className="compose-btn"
                      onClick={() => setShowEmailComposer(true)}
                    >
                      Compose Email
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* SMS Archive Sub-Tab */}
            {archiveSubTab === 'sms' && (
              <div className="archive-content">
                <div className="archive-header">
                  <h3>SMS History</h3>
                  <p className="archive-description">All text messages exchanged with this lead</p>
                </div>
                {archiveLoading ? (
                  <div className="loading-state">Loading messages...</div>
                ) : smsArchive.length > 0 ? (
                  <div className="archive-list sms-thread">
                    {smsArchive.map((sms, idx) => (
                      <div
                        key={sms.id || idx}
                        className={`archive-item sms-item ${sms.direction || 'outbound'}`}
                      >
                        <div className="sms-bubble">
                          <div className="sms-message">{sms.message || sms.body}</div>
                          <div className="sms-meta">
                            <span className="sms-status">{sms.status || 'sent'}</span>
                            <span className="sms-time">
                              {new Date(sms.sent_at || sms.created_at).toLocaleString()}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <div className="empty-icon">💬</div>
                    <p>No SMS messages found for this lead</p>
                    <button
                      className="compose-btn"
                      onClick={() => setShowSMSModal(true)}
                    >
                      Send SMS
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Recorded Calls Sub-Tab */}
            {archiveSubTab === 'calls' && (
              <div className="archive-content">
                <div className="archive-header">
                  <h3>Recorded Calls</h3>
                  <p className="archive-description">All recorded phone calls with this lead</p>
                </div>
                {archiveLoading ? (
                  <div className="loading-state">Loading recordings...</div>
                ) : callArchive.length > 0 ? (
                  <div className="archive-list">
                    {callArchive.map((call, idx) => (
                      <div key={call.id || idx} className="archive-item call-item">
                        <div className="archive-item-header">
                          <span className={`archive-direction ${call.direction || 'outbound'}`}>
                            {call.direction === 'inbound' ? '📲 Incoming' : '📞 Outgoing'}
                          </span>
                          <span className="call-duration">
                            {call.duration ? `${Math.floor(call.duration / 60)}:${(call.duration % 60).toString().padStart(2, '0')}` : 'N/A'}
                          </span>
                          <span className="archive-date">
                            {new Date(call.call_time || call.created_at).toLocaleString()}
                          </span>
                        </div>
                        <div className="call-details">
                          <span className="call-status">{call.status || 'completed'}</span>
                          {call.disposition && <span className="call-disposition">{call.disposition}</span>}
                        </div>
                        {call.recording_url && (
                          <div className="call-recording">
                            <audio controls src={call.recording_url}>
                              Your browser does not support audio playback.
                            </audio>
                          </div>
                        )}
                        {call.transcription && (
                          <div className="call-transcription">
                            <strong>Transcription:</strong>
                            <p>{call.transcription.substring(0, 300)}{call.transcription.length > 300 && '...'}</p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <div className="empty-icon">🎙️</div>
                    <p>No recorded calls found for this lead</p>
                    <button
                      className="compose-btn"
                      onClick={() => setShowRecordingModal(true)}
                    >
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
                          onChange={e => setCircleForm({...circleForm, phone: formatPhoneNumber(e.target.value)})}
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

          {/* Smart Docs Tab */}
          {activeTab === 'smart-docs' && (
          <div className="info-section">
            <h2>Smart Documents</h2>
            <NeedsListView
              borrowerId={lead?.id}
              loanId={lead?.loan_id || lead?.id}
              borrowerEmail={lead?.email || ''}
              borrowerName={lead?.name || `${lead?.first_name || ''} ${lead?.last_name || ''}`.trim()}
              borrowerPhone={lead?.phone || ''}
            />
          </div>
          )}

          {/* Income Tab */}
          {activeTab === 'income' && (
          <div className="info-section">
            <div className="income-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h2 style={{ margin: 0 }}>Income Calculator</h2>
                <p className="circle-description" style={{ margin: '8px 0 0 0' }}>
                  Calculate qualifying income following agency guidelines for all 14 income types.
                </p>
              </div>
              <div className="income-calc-toggle" style={{ display: 'flex', gap: '8px' }}>
                <button
                  className={`tab-btn ${incomeCalcMode === 'unified' ? 'active' : ''}`}
                  onClick={() => setIncomeCalcMode('unified')}
                  style={{ padding: '8px 16px', fontSize: '13px' }}
                >
                  All 14 Types
                </button>
                <button
                  className={`tab-btn ${incomeCalcMode === 'basic' ? 'active' : ''}`}
                  onClick={() => setIncomeCalcMode('basic')}
                  style={{ padding: '8px 16px', fontSize: '13px' }}
                >
                  Quick Calc
                </button>
              </div>
            </div>

            {incomeCalcMode === 'unified' ? (
              <UnifiedIncomeCalculator
                loanId={null}
                leadId={parseInt(id)}
                borrowerId={borrowers[activeBorrower]?.id || 1}
                onIncomeCalculated={(result) => {
                  console.log('Unified income calculated:', result);
                }}
              />
            ) : (
              <IncomeCalculator
                loanId={null}
                leadId={parseInt(id)}
                borrowerId={borrowers[activeBorrower]?.id || 1}
                onIncomeCalculated={(result) => {
                  console.log('Income calculated:', result);
                }}
              />
            )}
          </div>
          )}

          {/* Credit Tab */}
          {activeTab === 'credit' && (
          <div className="info-section">
            <CreditTab
              leadId={parseInt(id)}
              loanId={null}
              borrowerId={borrowers[activeBorrower]?.id || 1}
              formData={formData}
            />
          </div>
          )}

          {/* Conditions Tab */}
          {activeTab === 'documents' && (
          <div className="info-section">
            <h2>Conditions</h2>
            <div className="conditions-content">
              <p className="circle-description">
                Track and manage loan conditions. Items added here will appear in the client portal's
                Needs List. Clients will be notified when new conditions are requested.
              </p>

              <div className="conditions-header-actions">
                <button
                  className="btn-add-condition"
                  onClick={() => setShowAddConditionModal(true)}
                >
                  + Add Condition
                </button>
                <div className="conditions-summary">
                  <span className="condition-count pending">
                    {conditions.filter(c => c.status === 'pending').length} Pending
                  </span>
                  <span className="condition-count received">
                    {conditions.filter(c => c.status === 'received').length} Received
                  </span>
                  <span className="condition-count approved">
                    {conditions.filter(c => c.status === 'approved').length} Approved
                  </span>
                </div>
              </div>

              {conditionsLoading ? (
                <div className="loading-state">Loading conditions...</div>
              ) : conditions.length === 0 ? (
                <div className="empty-conditions">
                  <div className="empty-icon">📋</div>
                  <h3>No Conditions Yet</h3>
                  <p>When the applicant completes their application, the needs list will be populated automatically.</p>
                  <p>You can also manually add conditions using the button above.</p>
                </div>
              ) : (
              <div className="conditions-list">
                {conditions.map(condition => (
                  <div key={condition.id} className={`condition-item status-${condition.status}`}>
                    <div className="condition-checkbox">
                      <input
                        type="checkbox"
                        checked={condition.status === 'approved'}
                        onChange={() => updateConditionStatus(
                          condition.id,
                          condition.status === 'approved' ? 'pending' : 'approved'
                        )}
                      />
                    </div>
                    <div className="condition-info">
                      <div className="condition-name">
                        {condition.name}
                        {condition.is_new && <span className="new-badge">NEW</span>}
                      </div>
                      {condition.description && (
                        <div className="condition-description">{condition.description}</div>
                      )}
                      <div className="condition-meta">
                        <span className="condition-category">{condition.category?.replace(/_/g, ' ')}</span>
                        {condition.due_date && (
                          <span className="condition-due">Due: {new Date(condition.due_date).toLocaleDateString()}</span>
                        )}
                        <span className={`condition-priority priority-${condition.priority}`}>
                          {condition.priority}
                        </span>
                      </div>
                    </div>
                    <div className="condition-status">
                      <select
                        value={condition.status}
                        onChange={(e) => updateConditionStatus(condition.id, e.target.value)}
                        className={`status-select status-${condition.status}`}
                      >
                        <option value="pending">Pending</option>
                        <option value="requested">Requested</option>
                        <option value="received">Received</option>
                        <option value="approved">Approved</option>
                        <option value="waived">Waived</option>
                      </select>
                    </div>
                  </div>
                ))}
              </div>
              )}

              {/* Add Condition Modal */}
              {showAddConditionModal && (
                <div className="modal-overlay" onClick={() => setShowAddConditionModal(false)}>
                  <div className="modal-content condition-modal" onClick={e => e.stopPropagation()}>
                    <div className="modal-header">
                      <h3>Add Condition</h3>
                      <button className="modal-close" onClick={() => setShowAddConditionModal(false)}>&times;</button>
                    </div>
                    <form onSubmit={handleAddCondition}>
                      <div className="modal-body">
                        <div className="form-group">
                          <label>Condition Name *</label>
                          <input
                            type="text"
                            value={newCondition.name}
                            onChange={(e) => setNewCondition({...newCondition, name: e.target.value})}
                            placeholder="e.g., Most Recent Pay Stub"
                            required
                          />
                        </div>
                        <div className="form-group">
                          <label>Description</label>
                          <textarea
                            value={newCondition.description}
                            onChange={(e) => setNewCondition({...newCondition, description: e.target.value})}
                            placeholder="Additional details or instructions for the client"
                            rows={3}
                          />
                        </div>
                        <div className="form-row">
                          <div className="form-group">
                            <label>Category</label>
                            <select
                              value={newCondition.category}
                              onChange={(e) => setNewCondition({...newCondition, category: e.target.value})}
                            >
                              <option value="income_verification">Income Verification</option>
                              <option value="asset_verification">Asset Verification</option>
                              <option value="employment_verification">Employment Verification</option>
                              <option value="credit_documentation">Credit Documentation</option>
                              <option value="property_documentation">Property Documentation</option>
                              <option value="identity_verification">Identity Verification</option>
                              <option value="other">Other</option>
                            </select>
                          </div>
                          <div className="form-group">
                            <label>Priority</label>
                            <select
                              value={newCondition.priority}
                              onChange={(e) => setNewCondition({...newCondition, priority: e.target.value})}
                            >
                              <option value="required">Required</option>
                              <option value="recommended">Recommended</option>
                              <option value="optional">Optional</option>
                            </select>
                          </div>
                        </div>
                        <div className="form-group">
                          <label>Due Date</label>
                          <input
                            type="date"
                            value={newCondition.due_date}
                            onChange={(e) => setNewCondition({...newCondition, due_date: e.target.value})}
                          />
                        </div>
                        <div className="form-group notification-toggle">
                          <label className="toggle-label">
                            <input type="checkbox" defaultChecked />
                            <span>Notify client via email and portal</span>
                          </label>
                        </div>
                      </div>
                      <div className="modal-footer">
                        <button type="button" className="btn-secondary" onClick={() => setShowAddConditionModal(false)}>
                          Cancel
                        </button>
                        <button type="submit" className="btn-primary" disabled={addingCondition}>
                          {addingCondition ? 'Adding...' : 'Add Condition'}
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </div>
          </div>
          )}

          {/* SLA Dates Tab */}
          {activeTab === 'important-dates' && (
          <div className="tab-content sla-dates-tab">
            <div className="sla-dates-compact">
              <div className="sla-section-header">SLA Milestone Dates</div>
              <div className="dates-grid">
                <div className="date-field">
                  <label>New Lead</label>
                  <input
                    type="datetime-local"
                    value={formData.lead_received_date ? formData.lead_received_date.slice(0, 16) : ''}
                    onChange={(e) => handleFieldChange('lead_received_date', e.target.value)}
                  />
                </div>
                <div className="date-field">
                  <label>Attempted Contact</label>
                  <input
                    type="datetime-local"
                    value={formData.first_contact_attempt_date ? formData.first_contact_attempt_date.slice(0, 16) : ''}
                    onChange={(e) => handleFieldChange('first_contact_attempt_date', e.target.value)}
                  />
                </div>
                <div className="date-field">
                  <label>Application Complete</label>
                  <input
                    type="datetime-local"
                    value={formData.application_completed_date ? formData.application_completed_date.slice(0, 16) : ''}
                    onChange={(e) => handleFieldChange('application_completed_date', e.target.value)}
                  />
                </div>
                <div className="date-field">
                  <label>Initial Consultation</label>
                  <input
                    type="datetime-local"
                    value={formData.initial_consultation_date ? formData.initial_consultation_date.slice(0, 16) : ''}
                    onChange={(e) => handleFieldChange('initial_consultation_date', e.target.value)}
                  />
                </div>
                <div className="date-field">
                  <label>Pre-Qualified</label>
                  <input
                    type="datetime-local"
                    value={formData.lead_qualification_date ? formData.lead_qualification_date.slice(0, 16) : ''}
                    onChange={(e) => handleFieldChange('lead_qualification_date', e.target.value)}
                  />
                </div>
                <div className="date-field">
                  <label>Pre-Approved</label>
                  <input
                    type="datetime-local"
                    value={formData.preapproval_issued_date ? formData.preapproval_issued_date.slice(0, 16) : ''}
                    onChange={(e) => handleFieldChange('preapproval_issued_date', e.target.value)}
                  />
                </div>
              </div>

              <div className="sla-section-header" style={{ marginTop: '8px' }}>Status History</div>
              {stageHistoryLoading ? (
                <div className="loading-state" style={{ fontSize: '11px', padding: '6px' }}>Loading...</div>
              ) : stageHistory.length === 0 ? (
                <div className="empty-timeline">
                  <p>No status changes recorded yet.</p>
                </div>
              ) : (
                <div className="status-timeline status-timeline-compact">
                  {stageHistory.slice(0, 5).map((entry, index) => (
                    <div key={entry.id || index} className="timeline-entry" style={{ padding: '2px 0', fontSize: '11px' }}>
                      <span className="stage-change" style={{ marginRight: '8px' }}>
                        {entry.from_stage ? (
                          <>{entry.from_stage} → {entry.to_stage}</>
                        ) : (
                          <>Started: {entry.to_stage}</>
                        )}
                      </span>
                      <span style={{ color: '#888', fontSize: '10px' }}>
                        {new Date(entry.changed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          )}

        </div>
      </div>

      {/* Client Portal Modal */}
      {showClientPortalModal && clientPortalData && (
        <div className="modal-overlay" onClick={() => setShowClientPortalModal(false)}>
          <div className="modal-content application-link-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{clientPortalData.justCreated ? 'Client Portal Created' : 'Client Portal'}</h2>
              <button className="close-btn" onClick={() => setShowClientPortalModal(false)}>×</button>
            </div>
            <div className="modal-body">
              {clientPortalData.justCreated ? (
                <p>A new client portal has been created for <strong>{clientPortalData.borrower_name || lead?.name}</strong>.</p>
              ) : (
                <p>Client portal for <strong>{clientPortalData.borrower_name || lead?.name}</strong> is ready.</p>
              )}

              <div className="application-link-container">
                <input
                  type="text"
                  value={clientPortalData.url || 'Loading...'}
                  readOnly
                  className="link-input"
                />
                <button className="copy-btn" onClick={copyClientPortalLink}>
                  Copy Link
                </button>
              </div>

              <div className="link-actions" style={{ marginTop: '16px', display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                <a
                  href={clientPortalData.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-primary"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '8px 16px', backgroundColor: '#3b82f6', color: 'white', borderRadius: '6px', textDecoration: 'none' }}
                >
                  Open Portal
                </a>
                <button
                  onClick={async () => {
                    try {
                      await purlAPI.resendInvite(clientPortalData.workspace_id);
                      toast.success('Invitation email sent to borrower!');
                    } catch (err) {
                      toast.error('Failed to send invitation: ' + (err.response?.data?.detail || err.message));
                    }
                  }}
                  className="btn btn-secondary"
                  style={{ padding: '8px 16px', backgroundColor: '#6b7280', color: 'white', borderRadius: '6px', border: 'none', cursor: 'pointer' }}
                >
                  Send Invite Email
                </button>
              </div>

              <p style={{ marginTop: '16px', fontSize: '14px', color: '#6b7280' }}>
                The borrower can use this portal to securely upload documents, track their application progress, and communicate with your team.
              </p>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowClientPortalModal(false)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Disposition Note Modal */}
      <DispositionNoteModal
        isOpen={dispositionModal.show}
        onClose={() => setDispositionModal({ show: false, status: null })}
        onConfirm={async (status) => {
          await executeStatusChange(status);
        }}
        lead={lead}
        newStatus={dispositionModal.status}
      />

      {/* Send Application Modal */}
      {showApplicationModal && applicationLink && (
        <SendApplicationModal
          lead={lead}
          applicationLink={applicationLink}
          onClose={() => setShowApplicationModal(false)}
          onSent={() => {
            setShowApplicationModal(false);
          }}
        />
      )}

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

      {/* Appointment Modal (legacy) */}
      {lead && (
        <AppointmentModal
          isOpen={showAppointmentModal}
          onClose={() => setShowAppointmentModal(false)}
          lead={lead}
        />
      )}

      {/* Schedule Appointment Modal (Redfin-style) */}
      {lead && (
        <ScheduleAppointmentModal
          isOpen={showScheduleModal}
          onClose={() => setShowScheduleModal(false)}
          onSuccess={() => setCalendarRefreshKey(prev => prev + 1)}
          borrower={lead}
        />
      )}

      {/* UVIP Video Call Schedule Modal */}
      <VideoCallScheduleModal
        isOpen={showVideoMeetings}
        onClose={() => setShowVideoMeetings(false)}
        borrower={lead}
        onStartVideoCall={(data) => {
          console.log('Video call started:', data);
        }}
      />

      {/* Send Video Message Modal */}
      {lead && clientPortalData?.workspace_id && (
        <SendVideoModal
          isOpen={showSendVideoModal}
          onClose={() => setShowSendVideoModal(false)}
          recipientType="client"
          recipientId={clientPortalData.workspace_id}
          recipientName={`${lead.first_name || ''} ${lead.last_name || lead.name || 'Client'}`.trim()}
          onSuccess={() => {
            console.log('Video sent successfully');
          }}
        />
      )}

      {/* Email Composer Modal */}
      <EmailComposerModal
        isOpen={showEmailComposer}
        onClose={() => setShowEmailComposer(false)}
        recipient={{
          name: lead?.name,
          email: lead?.email
        }}
        entityType="lead"
        entityData={{
          id: lead?.id,
          stage: lead?.stage,
          source: lead?.source,
          loan_amount: lead?.loan_amount
        }}
      />

      {/* Email Draft Modal */}
      {showDraftModal && selectedDraft && (
        <div className="modal-overlay" onClick={() => setShowDraftModal(false)}>
          <div className="modal-content draft-modal" onClick={(e) => e.stopPropagation()} style={{
            maxWidth: '800px',
            width: '90%',
            maxHeight: '90vh',
            overflow: 'auto',
            backgroundColor: 'white',
            borderRadius: '12px',
            padding: '24px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ margin: 0 }}>
                <span style={{
                  backgroundColor: '#fef3c7',
                  color: '#d97706',
                  padding: '4px 10px',
                  borderRadius: '6px',
                  fontSize: '14px',
                  marginRight: '10px'
                }}>DRAFT</span>
                Edit Email Draft
              </h2>
              <button
                onClick={() => setShowDraftModal(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '24px',
                  cursor: 'pointer',
                  color: '#666'
                }}
              >×</button>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '600', color: '#374151' }}>To:</label>
              <input
                type="text"
                value={selectedDraft.recipient_email || ''}
                readOnly
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  backgroundColor: '#f9fafb'
                }}
              />
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '600', color: '#374151' }}>
                CC Recipients:
              </label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
                {ccRecipients.map((recipient, index) => (
                  <span
                    key={index}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      backgroundColor: '#e5e7eb',
                      padding: '4px 10px',
                      borderRadius: '20px',
                      fontSize: '14px'
                    }}
                  >
                    {recipient.name || recipient.email}
                    <button
                      onClick={() => removeCcRecipient(recipient.email)}
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        color: '#6b7280',
                        padding: '0 2px'
                      }}
                    >×</button>
                  </span>
                ))}
              </div>
              <div style={{ display: 'flex', gap: '8px', position: 'relative' }}>
                <input
                  type="text"
                  value={ccSearchQuery}
                  onChange={(e) => {
                    setCcSearchQuery(e.target.value);
                    searchCcContacts(e.target.value);
                  }}
                  placeholder="Search contacts to add CC..."
                  style={{
                    flex: 1,
                    padding: '10px',
                    border: '1px solid #d1d5db',
                    borderRadius: '6px'
                  }}
                />
                <button
                  onClick={() => {
                    if (ccSearchQuery && ccSearchQuery.includes('@')) {
                      addCcRecipient({ email: ccSearchQuery, name: ccSearchQuery });
                    }
                  }}
                  style={{
                    padding: '10px 16px',
                    backgroundColor: '#3b82f6',
                    color: 'white',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontSize: '18px'
                  }}
                  title="Add CC recipient"
                >+</button>
              </div>
              {ccSearchResults.length > 0 && (
                <div style={{
                  position: 'absolute',
                  backgroundColor: 'white',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
                  maxHeight: '200px',
                  overflow: 'auto',
                  zIndex: 1000,
                  width: 'calc(100% - 80px)'
                }}>
                  {ccSearchResults.map((contact, index) => (
                    <div
                      key={index}
                      onClick={() => addCcRecipient(contact)}
                      style={{
                        padding: '10px',
                        cursor: 'pointer',
                        borderBottom: '1px solid #e5e7eb'
                      }}
                      onMouseEnter={(e) => e.target.style.backgroundColor = '#f3f4f6'}
                      onMouseLeave={(e) => e.target.style.backgroundColor = 'white'}
                    >
                      <div style={{ fontWeight: '600' }}>{contact.name}</div>
                      <div style={{ fontSize: '12px', color: '#6b7280' }}>{contact.email}</div>
                    </div>
                  ))}
                </div>
              )}
              {ccSearchLoading && (
                <div style={{ marginTop: '8px', color: '#6b7280', fontSize: '14px' }}>
                  Searching...
                </div>
              )}
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '600', color: '#374151' }}>Subject:</label>
              <input
                type="text"
                value={selectedDraft.subject || ''}
                onChange={(e) => setSelectedDraft({ ...selectedDraft, subject: e.target.value })}
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px'
                }}
              />
            </div>

            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '600', color: '#374151' }}>Body:</label>
              <textarea
                value={selectedDraft.body_html?.replace(/<[^>]*>/g, '') || selectedDraft.body_text || ''}
                onChange={(e) => setSelectedDraft({
                  ...selectedDraft,
                  body_html: e.target.value,
                  body_text: e.target.value
                })}
                rows={12}
                style={{
                  width: '100%',
                  padding: '12px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  resize: 'vertical',
                  fontFamily: 'inherit',
                  lineHeight: '1.5'
                }}
              />
            </div>

            {selectedDraft.action_items && selectedDraft.action_items.length > 0 && (
              <div style={{ marginBottom: '20px', padding: '16px', backgroundColor: '#f9fafb', borderRadius: '8px' }}>
                <h4 style={{ margin: '0 0 12px 0', color: '#374151' }}>Action Items:</h4>
                <ul style={{ margin: 0, paddingLeft: '20px' }}>
                  {selectedDraft.action_items.map((item, index) => (
                    <li key={index} style={{ marginBottom: '8px', color: '#4b5563' }}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            {selectedDraft.recording_url && (
              <div style={{ marginBottom: '20px', padding: '12px', backgroundColor: '#fef3c7', borderRadius: '8px' }}>
                <span style={{ color: '#d97706' }}>Recording attached: </span>
                <a href={selectedDraft.recording_url} target="_blank" rel="noopener noreferrer" style={{ color: '#2563eb' }}>
                  View Recording
                </a>
              </div>
            )}

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button
                onClick={deleteDraft}
                disabled={draftLoading}
                style={{
                  padding: '10px 20px',
                  backgroundColor: '#fee2e2',
                  color: '#dc2626',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: draftLoading ? 'not-allowed' : 'pointer',
                  fontWeight: '600'
                }}
              >
                Delete
              </button>
              <button
                onClick={saveDraft}
                disabled={draftLoading}
                style={{
                  padding: '10px 20px',
                  backgroundColor: '#f3f4f6',
                  color: '#374151',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  cursor: draftLoading ? 'not-allowed' : 'pointer',
                  fontWeight: '600'
                }}
              >
                {draftLoading ? 'Saving...' : 'Save Draft'}
              </button>
              <button
                onClick={sendDraft}
                disabled={draftLoading}
                style={{
                  padding: '10px 24px',
                  backgroundColor: '#3b82f6',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: draftLoading ? 'not-allowed' : 'pointer',
                  fontWeight: '600'
                }}
              >
                {draftLoading ? 'Sending...' : 'Send Email'}
              </button>
            </div>
          </div>
        </div>
      )}
      </div>

      {/* Fixed Sidebar */}
      <CalendarSidebar leadId={id} key={calendarRefreshKey}>
      {/* Quick Actions */}
      <div className="actions-card">
        <h3>QUICK ACTIONS</h3>
        <div className="action-buttons">
          <button className="action-btn call" onClick={() => handleAction('call')} disabled={!lead.phone} title="Click to call">
            <span>Call</span>
          </button>
          <button className="action-btn sms" onClick={() => handleAction('sms')} disabled={!lead.phone} title="Send SMS">
            <span>SMS Text</span>
          </button>
          <button className="action-btn email" onClick={() => handleAction('email')} disabled={!lead.email} title="Send email">
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
          <button className="action-btn voicemail" onClick={() => handleAction('voicemail')} disabled={!lead.phone} title="Drop voicemail">
            <span>Voicemail Drop</span>
          </button>
          <button className="action-btn record-video" onClick={() => setShowSendVideoModal(true)} disabled={!clientPortalData?.workspace_id} title={clientPortalData?.workspace_id ? "Record and send a video message" : "Create a Client Portal first to enable video messaging"}>
            <span>Record Video</span>
          </button>
          <button className="action-btn application" onClick={() => handleAction('send_application')} disabled={applicationLoading} title="Send application link">
            <span>{applicationLoading ? 'Creating...' : 'Send Application'}</span>
          </button>
          <button className="action-btn portal" onClick={() => handleAction('client_portal')} disabled={clientPortalLoading} title="Access portals">
            <span>{clientPortalLoading ? 'Loading...' : 'Portals'}</span>
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

export default LeadDetail;
