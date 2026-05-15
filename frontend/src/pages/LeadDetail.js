import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useLead } from '../hooks/useQueries';
import { leadsAPI, activitiesAPI, circleOfCashflowAPI, tasksAPI, loansAPI, borrowerApplicationAPI, purlAPI, partnersAPI, API_BASE_URL } from '../services/api';
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
import UnifiedIncomeCalculator from '../components/income/UnifiedIncomeCalculator';
import IncomeCalculator from '../components/IncomeCalculator';
import CreditTab from '../components/CreditTab';
import VideoCallScheduleModal from '../components/VideoCallScheduleModal';
import EmailComposerModal from '../components/EmailComposerModal';
import CalendarSidebar from '../components/CalendarSidebar';
import NeedsListView from '../components/smart-docs/NeedsListView';
import SendVideoModal from '../components/video/SendVideoModal';
import SalesforceConnectionBadge from '../components/SalesforceConnectionBadge';
import SMSAccordionPanel from '../components/sms/SMSAccordionPanel';
import AIActivityTab from '../components/ai/AIActivityTab';
import './LeadDetail.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

// Extracted tab components
import {
  LoanDetailsTab,
  PersonalTab,
  PropertyTab,
  TasksTab,
  ConversationLogTab,
  CircleTab,
  ConditionsTab,
  SLADatesTab,
  statusOptions,
  getStatusColor,
} from './lead-detail';


function LeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  // Use React Query for cached lead fetching - instant on revisit!
  const { data: leadQueryData, isLoading: leadQueryLoading, error: leadQueryError, refetch: refetchLead } = useLead(id);

  const [lead, setLead] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(true); // Always in edit mode
  const [formData, setFormData] = useState({});
  const [emails, setEmails] = useState([]);
  const [activeTab, setActiveTab] = useState('loan-details');
  const [incomeCalcMode, setIncomeCalcMode] = useState('unified');
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

  // Client File state
  const [clientFileLoading, setClientFileLoading] = useState(false);

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

  // Referral Partners state
  const [referralPartners, setReferralPartners] = useState([]);

  // Archive state
  const [archiveSubTab, setArchiveSubTab] = useState('notes');
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

  // Custom fields state
  const [customFields, setCustomFields] = useState([]);

  // Workflow tasks state
  const [workflowTasks, setWorkflowTasks] = useState([]);
  const [workflowTasksLoading, setWorkflowTasksLoading] = useState(false);

  // Lead navigation state
  const [leadsList, setLeadsList] = useState([]);
  const [currentLeadIndex, setCurrentLeadIndex] = useState(-1);

  // ---------------------------------------------------------------------------
  // Circle contact helpers
  // ---------------------------------------------------------------------------

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

  const handleAddCircleContactSubmit = () => {
    if (!circleForm.name.trim()) return;

    if (circleForm.editId) {
      setCircleContacts(circleContacts.map(c =>
        c.id === circleForm.editId
          ? { ...c, name: circleForm.name, email: circleForm.email, phone: circleForm.phone, type: circleForm.type, notes: circleForm.notes }
          : c
      ));
    } else {
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

  // ---------------------------------------------------------------------------
  // Client portal data loader
  // ---------------------------------------------------------------------------

  const loadClientPortalData = async (leadId) => {
    try {
      const existingWorkspace = await purlAPI.getWorkspaceByLead(leadId);
      if (existingWorkspace && existingWorkspace.workspace) {
        const workspaceId = existingWorkspace.workspace.workspace_id || existingWorkspace.workspace.id;
        const slug = existingWorkspace.workspace.workspace_slug || existingWorkspace.workspace.slug;
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
      console.log('[Client Portal] No existing workspace for this lead');
    }
  };

  // ---------------------------------------------------------------------------
  // Process lead data from React Query cache
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (leadQueryData) {
      const leadData = leadQueryData;
      setLead(leadData);

      let processedData = { ...leadData };
      if (leadData.name && (!leadData.first_name || !leadData.last_name)) {
        const nameParts = leadData.name.split(' ');
        processedData.first_name = nameParts[0] || '';
        processedData.last_name = nameParts.slice(1).join(' ') || '';
      }
      setFormData(processedData);

      const primaryName = leadData.first_name && leadData.last_name
        ? `${leadData.first_name} ${leadData.last_name}`
        : leadData.name || 'Primary Borrower';

      const borrowersList = [
        { id: 0, name: primaryName, type: 'primary', data: leadData }
      ];

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
      setLoading(false);
    } else if (leadQueryError) {
      const errorMessage = leadQueryError?.message || 'Failed to load lead';
      if (errorMessage.includes('404')) {
        setError('Lead not found. It may have been deleted.');
      } else {
        setError(errorMessage);
      }
      setLoading(false);
    } else if (!leadQueryLoading) {
      setLoading(false);
    }
  }, [leadQueryData, leadQueryError, leadQueryLoading]);

  useEffect(() => {
    const action = location.state?.openAction;
    if (lead && action) {
      navigate(location.pathname, { replace: true, state: {} });
      setTimeout(() => handleAction(action), 0);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lead, location.state?.openAction]);

  // Load auxiliary data when id changes
  useEffect(() => {
    loadActivities();
    loadEmails();
    loadEmailDrafts();
    markLeadAsViewed();
    loadLeadsList();
    loadReferralPartners();
    loadClientPortalData(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // ---------------------------------------------------------------------------
  // Data loading functions
  // ---------------------------------------------------------------------------

  const loadReferralPartners = async () => {
    try {
      const partners = await partnersAPI.getAll();
      setReferralPartners(partners || []);
    } catch (error) {
      console.error('Error loading referral partners:', error);
    }
  };

  const loadLeadsList = async () => {
    try {
      let leads = [];
      try {
        const response = await leadsAPI.getAll();
        leads = response.leads || response || [];
      } catch (apiError) {
        console.error('Failed to load leads list:', apiError);
        leads = [];
      }
      setLeadsList(leads);
      const currentId = parseInt(id);
      const index = leads.findIndex(l => l.id === currentId);
      setCurrentLeadIndex(index);
    } catch (error) {
      console.error('Error loading leads list:', error);
    }
  };

  const handleViewNextLead = () => {
    if (leadsList.length === 0) return;
    let nextIndex = currentLeadIndex + 1;
    if (nextIndex >= leadsList.length) nextIndex = 0;
    const nextLead = leadsList[nextIndex];
    if (nextLead && nextLead.id) navigate(`/leads/${nextLead.id}`);
  };

  // ---------------------------------------------------------------------------
  // Status change
  // ---------------------------------------------------------------------------

  const handleStatusChange = async (newStatus) => {
    if (DispositionNoteModal.REQUIRES_NOTE.includes(newStatus)) {
      setShowStatusDropdown(false);
      setDispositionModal({ show: true, status: newStatus });
      return;
    }
    await executeStatusChange(newStatus);
  };

  const executeStatusChange = async (newStatus) => {
    setStatusSaving(true);
    setShowStatusDropdown(false);

    try {
      if (newStatus === 'Disclosed' || newStatus === 'Funded') {
        const timestamp = Date.now().toString(36).toUpperCase();
        const loanNumber = `LEAD-${id}-${timestamp}`;
        const constructedName = `${formData?.first_name || lead?.first_name || ''} ${formData?.last_name || lead?.last_name || ''}`.trim();
        const borrowerName = constructedName || lead?.name || formData?.name || 'Unknown Borrower';
        const loanAmount = parseFloat(lead?.loan_amount || formData?.loan_amount || lead?.amount || formData?.amount) || 1;

        const loanData = {
          loan_number: loanNumber,
          borrower_name: borrowerName,
          borrower_email: lead?.email || formData?.email,
          borrower_phone: lead?.phone || formData?.phone,
          amount: loanAmount,
          stage: newStatus,
          property_address: lead?.property_address || formData?.property_address,
        };

        try {
          const newLoan = await loansAPI.create(loanData, true);
          try {
            await leadsAPI.update(id, { stage: newStatus });
          } catch (leadUpdateError) {
            console.warn('Could not update lead stage (loan was created successfully):', leadUpdateError);
          }

          localStorage.removeItem('leads_data');
          localStorage.removeItem('leads_data_time');
          localStorage.removeItem('loans_data');
          localStorage.removeItem('loans_data_time');

          const clientName = borrowerName || 'Client';
          if (newStatus === 'Funded') {
            toast.success(
              `${clientName} has been moved to Funded. <a href="/portfolio" style="color: white; font-weight: bold; text-decoration: underline;">View in Portfolio &rarr;</a>`,
              { duration: 8000 }
            );
            navigate('/leads');
          } else {
            toast.success(
              `${clientName} has been moved to ${newStatus}. <a href="/loans/${newLoan.id}" style="color: white; font-weight: bold; text-decoration: underline;">View Loan &rarr;</a>`,
              { duration: 8000 }
            );
            loadLeadData();
          }
          return;
        } catch (loanError) {
          console.error('Error creating loan:', loanError);
          let errorMessage = 'Failed to create loan';
          if (loanError.response?.data?.detail) errorMessage = loanError.response.data.detail;
          else if (loanError.response?.status === 401) errorMessage = 'Session expired. Please log in again.';
          else if (loanError.response?.status === 400) errorMessage = loanError.response.data?.detail || 'Invalid loan data';
          else if (loanError.message === 'Network Error') errorMessage = 'Unable to connect to server. Please check your connection and try again.';
          else errorMessage = loanError.message || 'Unknown error';
          toast.error(`Could not convert lead to ${newStatus}: ${errorMessage}`);
          setStatusSaving(false);
          return;
        }
      }

      setFormData(prev => ({ ...prev, stage: newStatus }));
      setLead(prev => ({ ...prev, stage: newStatus }));
      const updatedLead = await leadsAPI.update(id, { stage: newStatus });

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

      localStorage.removeItem('leads_data');
      localStorage.removeItem('leads_data_time');
    } catch (error) {
      console.error('Error updating status:', error);
      toast.error(`Error updating status: ${error.message || 'Unknown error'}`);
      setFormData(prev => ({ ...prev, stage: lead?.stage }));
      setLead(prev => ({ ...prev, stage: lead?.stage }));
    } finally {
      setStatusSaving(false);
    }
  };

  const markLeadAsViewed = () => {
    try {
      const stored = localStorage.getItem('viewedLeads');
      const viewedLeads = stored ? new Set(JSON.parse(stored)) : new Set();
      viewedLeads.add(String(id));
      localStorage.setItem('viewedLeads', JSON.stringify([...viewedLeads]));
    } catch (error) {
      console.error('Error marking lead as viewed:', error);
    }
  };

  const loadLeadData = useCallback(() => {
    refetchLead();
    loadActivities();
  }, [refetchLead, id]);

  const loadActivities = async () => {
    try {
      const activitiesData = await activitiesAPI.getAll({ lead_id: parseInt(id) });
      setActivities(activitiesData || []);
    } catch (actError) {
      console.warn('Failed to load activities, continuing without them:', actError?.message);
      setActivities([]);
    }
  };

  const loadEmails = async () => {
    try {
      const emailActivities = await activitiesAPI.getAll({ lead_id: id, type: 'email' });
      setEmails(emailActivities || []);
    } catch (error) {
      console.error('Failed to load emails:', error);
    }
  };

  const loadEmailDrafts = async () => {
    try {
      const token = getToken();
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
      const response = await fetch(`${API_BASE}/api/v1/email-drafts?lead_id=${id}&status=draft`, {
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (response.ok) {
        const data = await response.json();
        setEmailDrafts(data.drafts || data || []);
      }
    } catch (error) {
      console.error('Failed to load email drafts:', error);
    }
  };

  const loadStageHistory = async () => {
    if (!id) return;
    setStageHistoryLoading(true);
    try {
      const token = getToken();
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
      const response = await fetch(`${API_BASE}/api/v1/leads/${id}/stage-history`, {
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
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

  useEffect(() => {
    if (activeTab === 'important-dates' && id) {
      loadStageHistory();
      loadSlaData();
    }
  }, [activeTab, id]);

  const loadSlaData = async () => {
    if (!id) return;
    setSlaLoading(true);
    try {
      const token = getToken();
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      const measuresResponse = await fetch(`${API_BASE}/api/v1/sla/measures?active_only=true`, {
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      const milestonesResponse = await fetch(`${API_BASE}/api/v1/sla/milestones/lead/${id}`, {
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });

      if (measuresResponse.ok) {
        const measuresData = await measuresResponse.json();
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

  // ---------------------------------------------------------------------------
  // Email draft functions
  // ---------------------------------------------------------------------------

  const searchCcContacts = async (query) => {
    if (!query || query.length < 2) { setCcSearchResults([]); return; }
    setCcSearchLoading(true);
    try {
      const token = getToken();
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
      const response = await fetch(`${API_BASE}/api/v1/contacts/search?q=${encodeURIComponent(query)}`, {
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
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

  const addCcRecipient = (contact) => {
    if (!ccRecipients.find(c => c.email === contact.email)) {
      setCcRecipients([...ccRecipients, contact]);
    }
    setCcSearchQuery('');
    setCcSearchResults([]);
  };

  const removeCcRecipient = (email) => {
    setCcRecipients(ccRecipients.filter(c => c.email !== email));
  };

  const openDraft = (draft) => {
    setSelectedDraft({ ...draft, body_html: draft.body_html || '', subject: draft.subject || '' });
    setCcRecipients(draft.cc_emails || []);
    setShowDraftModal(true);
  };

  const saveDraft = async () => {
    if (!selectedDraft) return;
    setDraftLoading(true);
    try {
      const token = getToken();
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
      const response = await fetch(`${API_BASE}/api/v1/email-drafts/${selectedDraft.id}`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: selectedDraft.subject, body_html: selectedDraft.body_html, cc_emails: ccRecipients })
      });
      if (response.ok) {
        await loadEmailDrafts();
        toast.success('Draft saved successfully!');
      } else { throw new Error('Failed to save draft'); }
    } catch (error) {
      console.error('Error saving draft:', error);
      toast.error('Failed to save draft');
    } finally { setDraftLoading(false); }
  };

  const deleteDraft = async () => {
    if (!selectedDraft) return;
    setDraftLoading(true);
    try {
      const token = getToken();
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
      const response = await fetch(`${API_BASE}/api/v1/email-drafts/${selectedDraft.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (response.ok) {
        setShowDraftModal(false);
        setSelectedDraft(null);
        await loadEmailDrafts();
        toast.success('Draft deleted');
      } else { throw new Error('Failed to delete draft'); }
    } catch (error) {
      console.error('Error deleting draft:', error);
      toast.error('Failed to delete draft');
    } finally { setDraftLoading(false); }
  };

  const sendDraft = async () => {
    if (!selectedDraft) return;
    setDraftLoading(true);
    try {
      const token = getToken();
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
      await fetch(`${API_BASE}/api/v1/email-drafts/${selectedDraft.id}`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: selectedDraft.subject, body_html: selectedDraft.body_html, cc_emails: ccRecipients })
      });
      const response = await fetch(`${API_BASE}/api/v1/email-drafts/${selectedDraft.id}/send`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
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
    } finally { setDraftLoading(false); }
  };

  // ---------------------------------------------------------------------------
  // Circle of Cashflow data loader
  // ---------------------------------------------------------------------------

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
    } finally { setCashflowLoading(false); }
  };

  useEffect(() => {
    if (activeTab === 'circle') loadCircleOfCashflow();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // ---------------------------------------------------------------------------
  // Workflow tasks loader
  // ---------------------------------------------------------------------------

  const loadWorkflowTasks = async () => {
    if (!lead?.id) return;
    setWorkflowTasksLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflow-config/leads/${lead.id}/workflow-tasks`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      if (response.ok) {
        const data = await response.json();
        if (data.tasks && data.tasks.length > 0) {
          const daysInStage = data.days_in_stage || 1;
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
                daysFromNow,
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
        } else { setWorkflowTasks([]); }
      } else { setWorkflowTasks([]); }
    } catch (error) {
      console.error('Error loading workflow tasks:', error);
      setWorkflowTasks([]);
    } finally { setWorkflowTasksLoading(false); }
  };

  useEffect(() => {
    if (activeTab === 'tasks' && lead) loadWorkflowTasks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, lead?.stage]);

  // ---------------------------------------------------------------------------
  // Documents & Conditions loaders
  // ---------------------------------------------------------------------------

  const loadDocuments = async () => {
    if (!id) return;
    setDocumentsLoading(true);
    setDocumentsError(null);
    try {
      const response = await leadsAPI.getDocuments(id);
      if (response && response.documents) setDocuments(response.documents);
    } catch (error) {
      console.error('Failed to load documents:', error);
      setDocumentsError('Failed to load documents');
    } finally { setDocumentsLoading(false); }
  };

  useEffect(() => {
    if (activeTab === 'documents' && id) { loadDocuments(); loadConditions(); }
    if (activeTab === 'conditions' && id) loadConditions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, id]);

  // SMS Archive loader
  useEffect(() => {
    if (archiveSubTab !== 'sms' || !lead?.phone) return;
    const fetchSmsArchive = async () => {
      setArchiveLoading(true);
      try {
        const token = getToken();
        const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
        const API_BASE = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
        const phone = encodeURIComponent(lead.phone);
        const res = await fetch(`${API_BASE}/api/v1/sms/conversations/${phone}?limit=100`, {
          headers: { 'Authorization': `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setSmsArchive(data.messages || data || []);
        }
      } catch (err) {
        console.error('Error loading SMS archive:', err);
      } finally { setArchiveLoading(false); }
    };
    fetchSmsArchive();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [archiveSubTab, lead?.phone]);

  const loadConditions = async () => {
    if (!id) return;
    setConditionsLoading(true);
    try {
      const token = getToken();
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
      const response = await fetch(`${API_BASE}/api/v1/leads/${id}/conditions`, {
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (response.ok) {
        const data = await response.json();
        setConditions(data.conditions || []);
      }
    } catch (error) {
      console.error('Failed to load conditions:', error);
    } finally { setConditionsLoading(false); }
  };

  const handleAddCondition = async (e) => {
    e.preventDefault();
    if (!newCondition.name.trim()) return;
    setAddingCondition(true);
    try {
      const token = getToken();
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
      const response = await fetch(`${API_BASE}/api/v1/leads/${id}/conditions`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...newCondition, lead_id: id, status: 'pending', notify_client: true })
      });
      if (response.ok) {
        const data = await response.json();
        setConditions(prev => [...prev, data.condition]);
        setShowAddConditionModal(false);
        setNewCondition({ name: '', description: '', category: 'income_verification', priority: 'required', due_date: '' });
      }
    } catch (error) {
      console.error('Failed to add condition:', error);
    } finally { setAddingCondition(false); }
  };

  const updateConditionStatus = async (conditionId, newStatus) => {
    try {
      const token = getToken();
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
      const response = await fetch(`${API_BASE}/api/v1/leads/${id}/conditions/${conditionId}`, {
        method: 'PATCH',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });
      if (response.ok) {
        setConditions(prev => prev.map(c => c.id === conditionId ? { ...c, status: newStatus } : c));
      }
    } catch (error) {
      console.error('Failed to update condition:', error);
    }
  };

  // ---------------------------------------------------------------------------
  // Client file navigation
  // ---------------------------------------------------------------------------

  const handleOpenClientFile = async () => {
    try {
      setClientFileLoading(true);
      const token = getToken();
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
      const response = await fetch(`${API_BASE}/api/v1/leads/${id}/client-file-id`, {
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (!response.ok) throw new Error(`Server returned ${response.status}`);
      const data = await response.json();
      navigate(`/clients/${data.client_file_id}`);
    } catch (error) {
      console.error('Failed to open client file:', error);
      toast.error('Could not open client file. Please try again.');
    } finally { setClientFileLoading(false); }
  };

  // ---------------------------------------------------------------------------
  // Save / Cancel / Field change handlers
  // ---------------------------------------------------------------------------

  const handleSave = async () => {
    try {
      let dataToSave;
      if (activeBorrower === 1) {
        const coApplicantName = formData.first_name && formData.last_name
          ? `${formData.first_name} ${formData.last_name}` : formData.name || '';
        dataToSave = { co_applicant_name: coApplicantName, co_applicant_email: formData.email || null, co_applicant_phone: formData.phone || null };
      } else {
        dataToSave = { ...formData, name: formData.first_name && formData.last_name ? `${formData.first_name} ${formData.last_name}` : formData.name || '' };
      }
      await leadsAPI.update(id, dataToSave);
      const updatedLead = await leadsAPI.getById(id);
      setLead(updatedLead);

      if (activeBorrower === 1 && updatedLead.co_applicant_name) {
        const primaryName = updatedLead.first_name && updatedLead.last_name ? `${updatedLead.first_name} ${updatedLead.last_name}` : updatedLead.name || 'Primary Borrower';
        const coborrowerParts = (updatedLead.co_applicant_name || '').split(' ');
        const updatedBorrowers = [
          { id: 0, name: primaryName, type: 'primary', data: updatedLead },
          { id: 1, name: updatedLead.co_applicant_name, type: 'co-borrower', data: { name: updatedLead.co_applicant_name, first_name: coborrowerParts[0] || '', last_name: coborrowerParts.slice(1).join(' ') || '', email: updatedLead.co_applicant_email || '', phone: updatedLead.co_applicant_phone || '' } }
        ];
        setBorrowers(updatedBorrowers);
        setFormData(updatedBorrowers[1].data);
      }
      toast.success('Lead updated successfully!');
    } catch (error) {
      console.error('Failed to update lead:', error);
      toast.error('Failed to update lead');
    }
  };

  const handleCancel = () => {
    if (activeBorrower < borrowers.length) setFormData(borrowers[activeBorrower].data);
    else setFormData(lead);
  };

  const autoSaveField = async (fieldName, fieldValue) => {
    try {
      let dataToSave;
      if (activeBorrower === 1) {
        const updatedData = {...formData, [fieldName]: fieldValue};
        const coApplicantName = updatedData.first_name && updatedData.last_name ? `${updatedData.first_name} ${updatedData.last_name}` : updatedData.name || '';
        dataToSave = { co_applicant_name: coApplicantName, co_applicant_email: updatedData.email || null, co_applicant_phone: updatedData.phone || null };
      } else {
        dataToSave = { [fieldName]: fieldValue };
        if (fieldName === 'first_name' || fieldName === 'last_name') {
          const updatedData = {...formData, [fieldName]: fieldValue};
          if (updatedData.first_name && updatedData.last_name) dataToSave.name = `${updatedData.first_name} ${updatedData.last_name}`;
        }
      }
      await leadsAPI.update(id, dataToSave);
      const updatedLead = await leadsAPI.getById(id);
      setLead(updatedLead);
    } catch (error) {
      console.error('Failed to auto-save field:', error);
    }
  };

  const handleFieldChange = (fieldName, fieldValue) => {
    setFormData({...formData, [fieldName]: fieldValue});
    if (saveTimeout) clearTimeout(saveTimeout);
    const newTimeout = setTimeout(() => { autoSaveField(fieldName, fieldValue); }, 1000);
    setSaveTimeout(newTimeout);
  };

  const handleIncomeChange = useCallback((monthly, annual) => {
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
      await activitiesAPI.create({ type: 'Note', content: noteText, lead_id: parseInt(id) });
      setNoteText('');
      loadLeadData();
    } catch (error) {
      console.error('Failed to add note:', error);
      const errorMsg = error.response?.data?.detail || 'Failed to add note. Please check console for details.';
      toast.error(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
    } finally { setNoteLoading(false); }
  };

  const handleSwitchBorrower = (borrowerIndex) => {
    setActiveBorrower(borrowerIndex);
    const borrower = borrowers[borrowerIndex];
    if (borrower && borrower.data) setFormData(borrower.data);
  };

  const handleAddBorrower = async () => {
    const firstName = prompt('Enter first name:');
    if (!firstName || !firstName.trim()) return;
    const lastName = prompt('Enter last name:');
    if (!lastName || !lastName.trim()) return;

    const fullName = `${firstName.trim()} ${lastName.trim()}`;
    try {
      if (borrowers.length === 1) {
        await leadsAPI.update(id, { co_applicant_name: fullName });
        const leadData = await leadsAPI.getById(id);
        setLead(leadData);
        const primaryName = leadData.first_name && leadData.last_name ? `${leadData.first_name} ${leadData.last_name}` : leadData.name || 'Primary Borrower';
        const updatedBorrowers = [{ id: 0, name: primaryName, type: 'primary', data: leadData }];
        if (leadData.co_applicant_name) {
          const coborrowerParts = (leadData.co_applicant_name || '').split(' ');
          updatedBorrowers.push({ id: 1, name: leadData.co_applicant_name, type: 'co-borrower', data: { name: leadData.co_applicant_name, first_name: coborrowerParts[0] || '', last_name: coborrowerParts.slice(1).join(' ') || '', email: leadData.co_applicant_email || '', phone: leadData.co_applicant_phone || '' } });
        }
        setBorrowers(updatedBorrowers);
        const targetIndex = updatedBorrowers.length > 1 ? 1 : 0;
        setActiveBorrower(targetIndex);
        if (updatedBorrowers[targetIndex]) setFormData(updatedBorrowers[targetIndex].data);
      } else {
        const newBorrower = { id: borrowers.length, name: fullName, type: borrowers.length === 1 ? 'co-borrower' : 'additional', data: { name: fullName, first_name: firstName.trim(), last_name: lastName.trim() } };
        setBorrowers([...borrowers, newBorrower]);
        setActiveBorrower(borrowers.length);
        setFormData(newBorrower.data);
      }
      toast.success(`${fullName} has been added successfully!`);
    } catch (error) {
      console.error('Failed to add borrower:', error);
      const errorMsg = error.response?.data?.detail || error.message || 'Failed to add borrower.';
      toast.error(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
    }
  };

  // ---------------------------------------------------------------------------
  // Voice command
  // ---------------------------------------------------------------------------

  const handleVoiceCommand = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) { toast.error('Sorry, your browser does not support speech recognition. Please try Chrome or Edge.'); return; }
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
    recognition.onstart = () => setIsListening(true);
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setVoiceTranscript(transcript);
      window.dispatchEvent(new CustomEvent('voiceCommand', { detail: { transcript, leadId: lead.id } }));
    };
    recognition.onerror = (event) => {
      setIsListening(false);
      if (event.error === 'no-speech') toast.error('No speech detected. Please try again.');
      else toast.error(`Error occurred: ${event.error}`);
    };
    recognition.onend = () => setIsListening(false);
    recognition.start();
  };

  // ---------------------------------------------------------------------------
  // Application link
  // ---------------------------------------------------------------------------

  const handleSendApplication = async () => {
    if (!lead) return;
    try {
      setApplicationLoading(true);
      const response = await borrowerApplicationAPI.createForLead(lead.id, { send_email: false, send_sms: false });
      const appUrl = `${window.location.origin}/apply/${response.public_token}`;
      setApplicationLink({ url: appUrl, token: response.public_token, application_id: response.id });
      setShowApplicationModal(true);
    } catch (err) {
      console.error('Error creating application:', err);
      toast.error('Failed to create application link. Please try again.');
    } finally { setApplicationLoading(false); }
  };

  const copyApplicationLink = async () => {
    if (!applicationLink?.url) return;
    try { await navigator.clipboard.writeText(applicationLink.url); toast.success('Application link copied to clipboard!'); }
    catch (err) {
      const textArea = document.createElement('textarea');
      textArea.value = applicationLink.url;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      toast.success('Application link copied to clipboard!');
    }
  };

  // ---------------------------------------------------------------------------
  // Client portal
  // ---------------------------------------------------------------------------

  const handleClientPortal = async () => {
    if (!lead) return;
    try {
      setClientPortalLoading(true);
      let existingWorkspace = null;
      try {
        existingWorkspace = await purlAPI.getWorkspaceByLead(lead.id);
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
      const borrowerName = lead.name || `${lead.first_name || ''} ${lead.last_name || ''}`.trim();
      const createData = { lead_id: lead.id, borrower_name: borrowerName, first_name: lead.first_name, last_name: lead.last_name, email: lead.email, phone: lead.phone };
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
      let errorMessage = 'Unknown error occurred';
      if (err.response?.data?.detail) errorMessage = err.response.data.detail;
      else if (err.message === 'Network Error') errorMessage = 'Unable to connect to server.';
      else if (err.message) errorMessage = err.message;
      toast.error(`Failed to access/create client portal: ${errorMessage}`);
    } finally { setClientPortalLoading(false); }
  };

  const copyClientPortalLink = async () => {
    if (!clientPortalData?.url) return;
    try { await navigator.clipboard.writeText(clientPortalData.url); toast.success('Client portal link copied to clipboard!'); }
    catch (err) {
      const textArea = document.createElement('textarea');
      textArea.value = clientPortalData.url;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      toast.success('Client portal link copied to clipboard!');
    }
  };

  // ---------------------------------------------------------------------------
  // Action dispatcher
  // ---------------------------------------------------------------------------

  const handleAction = async (action) => {
    switch(action) {
      case 'call':
        if (!lead.phone) { toast.error('No phone number available for this lead'); return; }
        { const cleanPhone = lead.phone.replace(/[^\d+]/g, '');
          const dialNumber = cleanPhone.startsWith('+') ? cleanPhone : `+1${cleanPhone}`;
          window.open(`https://teams.microsoft.com/l/call/0/0?users=4:${encodeURIComponent(dialNumber)}`, '_blank'); }
        break;
      case 'sms': setShowSMSModal(true); break;
      case 'email': setShowEmailComposer(true); break;
      case 'task': setShowTaskModal(true); break;
      case 'calendar': setShowScheduleModal(true); break;
      case 'teams': setShowTeamsModal(true); break;
      case 'video': setShowVideoMeetings(true); break;
      case 'record': setShowRecordingModal(true); break;
      case 'voicemail': setShowVoicemailDrop(true); break;
      case 'voice': handleVoiceCommand(); break;
      case 'escalation': setShowEscalationModal(true); break;
      case 'send_application': handleSendApplication(); break;
      case 'client_portal': handleClientPortal(); break;
      default: break;
    }
  };

  // ===========================================================================
  // RENDER
  // ===========================================================================

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
            style={{ padding: '12px 24px', backgroundColor: '#3b82f6', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px' }}
          >
            &larr; Back to Leads
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
              &larr; Back to Leads
            </button>
          <button className="btn-next" onClick={handleViewNextLead} disabled={leadsList.length === 0}>
            View Next Lead &rarr;
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
              <span style={{ fontSize: '10px' }}>&#x25BC;</span>
            </button>

            {showStatusDropdown && (
              <>
                <div
                  className="status-dropdown-overlay"
                  onClick={() => setShowStatusDropdown(false)}
                  style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 999 }}
                />
                <div
                  className="status-dropdown-menu"
                  style={{
                    position: 'absolute', top: '100%', left: 0, backgroundColor: 'white',
                    borderRadius: '8px', boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
                    zIndex: 1000, minWidth: '200px', marginTop: '4px', maxHeight: '400px', overflowY: 'auto'
                  }}
                >
                  {statusOptions.map((status, idx) => (
                    status.isHeader ? (
                      <div
                        key={status.label}
                        style={{
                          padding: '8px 16px', fontSize: '11px', fontWeight: 600,
                          textTransform: 'uppercase', color: '#6b7280',
                          borderTop: idx > 0 ? '1px solid #e5e7eb' : 'none',
                          marginTop: idx > 0 ? '4px' : 0, letterSpacing: '0.05em', background: '#fafafa',
                        }}
                      >
                        {status.label}
                      </div>
                    ) : (
                      <button
                        key={status}
                        onClick={() => handleStatusChange(status)}
                        style={{
                          display: 'block', width: '100%',
                          padding: '12px 16px', border: 'none',
                          background: (formData.stage || lead?.stage) === status ? '#f0f0f0' : 'white',
                          cursor: 'pointer', textAlign: 'left', fontSize: '14px',
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
          <button
            className="btn-client-file"
            onClick={handleOpenClientFile}
            disabled={clientFileLoading}
            style={{
              background: '#B8924A', color: 'white', border: 'none', padding: '8px 16px',
              borderRadius: '8px', cursor: 'pointer', fontWeight: '500', fontSize: '13px',
              opacity: clientFileLoading ? 0.7 : 1,
            }}
          >
            {clientFileLoading ? 'Opening...' : 'Open in Client File'}
          </button>
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
        padding: '12px 24px', backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between'
      }}>
        <h2 style={{ margin: 0, fontSize: '20px', fontWeight: '600', color: '#1a1a2e' }}>
          {formData.first_name || formData.last_name
            ? `${formData.first_name || ''} ${formData.last_name || ''}`.trim()
            : lead?.first_name || lead?.last_name
              ? `${lead?.first_name || ''} ${lead?.last_name || ''}`.trim()
              : 'Unknown Client'}
        </h2>
        <SalesforceConnectionBadge entityType="lead" entityId={id} salesforceId={lead?.salesforce_id} lastSyncedAt={lead?.salesforce_last_synced_at} />
      </div>

      {/* Tab Navigation */}
      <div className="profile-tabs">
        {[
          ['loan-details', 'Loan Details'],
          ['personal', 'Personal'],
          ['loan', 'Property'],
          ['tasks', 'Tasks'],
          ['conversation', 'Conversation Log'],
          ['circle', 'Circle'],
          ['smart-docs', 'Smart Docs'],
          ['income', 'Income'],
          ['credit', 'Credit'],
          ['documents', 'Conditions'],
          ['important-dates', 'SLA Dates'],
          ['team', 'Team Members'],
          ['ai-activity', 'AI Activity'],
        ].map(([key, label]) => (
          <button
            key={key}
            className={`tab-btn ${activeTab === key ? 'active' : ''}`}
            onClick={() => setActiveTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="detail-content">
        <div className="left-column">

          {/* Loan Details Tab */}
          {activeTab === 'loan-details' && (
            <LoanDetailsTab formData={formData} handleFieldChange={handleFieldChange} />
          )}

          {/* Personal Tab */}
          {activeTab === 'personal' && (
            <PersonalTab
              id={id}
              lead={lead}
              formData={formData}
              handleFieldChange={handleFieldChange}
              handleIncomeChange={handleIncomeChange}
              borrowers={borrowers}
              activeBorrower={activeBorrower}
              handleSwitchBorrower={handleSwitchBorrower}
              handleAddBorrower={handleAddBorrower}
              customFields={customFields}
              setCustomFields={setCustomFields}
              referralPartners={referralPartners}
            />
          )}

          {/* Property Tab */}
          {activeTab === 'loan' && (
            <PropertyTab formData={formData} handleFieldChange={handleFieldChange} />
          )}

          {/* Team Members Tab */}
          {activeTab === 'team' && (
            <div className="info-section">
              <h2>Team Members</h2>
              <div style={{ marginBottom: '24px' }}>
                <WorkflowRoleAssignment onUpdate={() => {}} />
              </div>
              <div style={{ marginTop: '24px' }}>
                <h3 style={{ marginBottom: '16px', color: '#333', fontSize: '16px' }}>General Team Assignments</h3>
                <TeamAssignment leadId={id} />
              </div>
            </div>
          )}

          {/* AI Activity Tab */}
          {activeTab === 'ai-activity' && (
            <div className="info-section">
              <AIActivityTab
                loanId={lead?.id?.toString()}
                borrowerName={lead?.name || lead?.first_name}
                loanNumber={lead?.loan_number}
                loanAmount={lead?.loan_amount}
                loanStatus={lead?.stage}
                onClickToDial={() => handleAction('call')}
              />
            </div>
          )}

          {/* Tasks Tab */}
          {activeTab === 'tasks' && (
            <TasksTab
              lead={lead}
              workflowTasks={workflowTasks}
              workflowTasksLoading={workflowTasksLoading}
              onShowTaskModal={() => setShowTaskModal(true)}
            />
          )}

          {/* Conversation Log Tab */}
          {activeTab === 'conversation' && (
            <ConversationLogTab
              activities={activities}
              noteText={noteText}
              setNoteText={setNoteText}
              noteLoading={noteLoading}
              handleAddNote={handleAddNote}
              emailArchive={emailArchive}
              smsArchive={smsArchive}
              callArchive={callArchive}
              archiveLoading={archiveLoading}
              archiveSubTab={archiveSubTab}
              setArchiveSubTab={setArchiveSubTab}
              onShowEmailComposer={() => setShowEmailComposer(true)}
              onShowSMSModal={() => setShowSMSModal(true)}
              onShowRecordingModal={() => setShowRecordingModal(true)}
            />
          )}

          {/* Circle Tab */}
          {activeTab === 'circle' && (
            <CircleTab
              circleContacts={circleContacts}
              setCircleContacts={setCircleContacts}
              showCircleModal={showCircleModal}
              setShowCircleModal={setShowCircleModal}
              circleForm={circleForm}
              setCircleForm={setCircleForm}
              searchResults={searchResults}
              setSearchResults={setSearchResults}
              showSearchResults={showSearchResults}
              setShowSearchResults={setShowSearchResults}
              searchLoading={searchLoading}
              cashflowOpportunities={cashflowOpportunities}
              cashflowReferrals={cashflowReferrals}
              cashflowLoading={cashflowLoading}
              onNameChange={handleNameChange}
              onSelectSearchResult={selectSearchResult}
              onSubmit={handleAddCircleContactSubmit}
            />
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
                  <button className={`tab-btn ${incomeCalcMode === 'unified' ? 'active' : ''}`} onClick={() => setIncomeCalcMode('unified')} style={{ padding: '8px 16px', fontSize: '13px' }}>All 14 Types</button>
                  <button className={`tab-btn ${incomeCalcMode === 'basic' ? 'active' : ''}`} onClick={() => setIncomeCalcMode('basic')} style={{ padding: '8px 16px', fontSize: '13px' }}>Quick Calc</button>
                </div>
              </div>
              {incomeCalcMode === 'unified' ? (
                <UnifiedIncomeCalculator loanId={null} leadId={parseInt(id)} borrowerId={borrowers[activeBorrower]?.id || 1} onIncomeCalculated={(result) => console.log('Unified income calculated:', result)} />
              ) : (
                <IncomeCalculator loanId={null} leadId={parseInt(id)} borrowerId={borrowers[activeBorrower]?.id || 1} onIncomeCalculated={(result) => console.log('Income calculated:', result)} />
              )}
            </div>
          )}

          {/* Credit Tab */}
          {activeTab === 'credit' && (
            <div className="info-section">
              <CreditTab leadId={parseInt(id)} loanId={null} borrowerId={borrowers[activeBorrower]?.id || 1} formData={formData} />
            </div>
          )}

          {/* Conditions Tab */}
          {activeTab === 'documents' && (
            <ConditionsTab
              conditions={conditions}
              conditionsLoading={conditionsLoading}
              updateConditionStatus={updateConditionStatus}
              showAddConditionModal={showAddConditionModal}
              setShowAddConditionModal={setShowAddConditionModal}
              newCondition={newCondition}
              setNewCondition={setNewCondition}
              addingCondition={addingCondition}
              handleAddCondition={handleAddCondition}
            />
          )}

          {/* SLA Dates Tab */}
          {activeTab === 'important-dates' && (
            <SLADatesTab
              formData={formData}
              handleFieldChange={handleFieldChange}
              stageHistory={stageHistory}
              stageHistoryLoading={stageHistoryLoading}
            />
          )}

        </div>
      </div>

      {/* Client Portal Modal */}
      {showClientPortalModal && clientPortalData && (
        <div className="modal-overlay" onClick={() => setShowClientPortalModal(false)}>
          <div className="modal-content application-link-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{clientPortalData.justCreated ? 'Client Portal Created' : 'Client Portal'}</h2>
              <button className="close-btn" onClick={() => setShowClientPortalModal(false)}>x</button>
            </div>
            <div className="modal-body">
              {clientPortalData.justCreated ? (
                <p>A new client portal has been created for <strong>{clientPortalData.borrower_name || lead?.name}</strong>.</p>
              ) : (
                <p>Client portal for <strong>{clientPortalData.borrower_name || lead?.name}</strong> is ready.</p>
              )}
              <div className="application-link-container">
                <input type="text" value={clientPortalData.url || 'Loading...'} readOnly className="link-input" />
                <button className="copy-btn" onClick={copyClientPortalLink}>Copy Link</button>
              </div>
              <div className="link-actions" style={{ marginTop: '16px', display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                <a href={clientPortalData.url} target="_blank" rel="noopener noreferrer" className="btn btn-primary"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '8px 16px', backgroundColor: '#3b82f6', color: 'white', borderRadius: '6px', textDecoration: 'none' }}>
                  Open Portal
                </a>
                <button onClick={async () => {
                  try { await purlAPI.resendInvite(clientPortalData.workspace_id); toast.success('Invitation email sent to borrower!'); }
                  catch (err) { toast.error('Failed to send invitation: ' + (err.response?.data?.detail || err.message)); }
                }}
                  className="btn btn-secondary"
                  style={{ padding: '8px 16px', backgroundColor: '#6b7280', color: 'white', borderRadius: '6px', border: 'none', cursor: 'pointer' }}>
                  Send Invite Email
                </button>
              </div>
              <p style={{ marginTop: '16px', fontSize: '14px', color: '#6b7280' }}>
                The borrower can use this portal to securely upload documents, track their application progress, and communicate with your team.
              </p>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowClientPortalModal(false)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Disposition Note Modal */}
      <DispositionNoteModal
        isOpen={dispositionModal.show}
        onClose={() => setDispositionModal({ show: false, status: null })}
        onConfirm={async (status) => { await executeStatusChange(status); }}
        lead={lead}
        newStatus={dispositionModal.status}
      />

      {/* Send Application Modal */}
      {showApplicationModal && applicationLink && (
        <SendApplicationModal lead={lead} applicationLink={applicationLink} onClose={() => setShowApplicationModal(false)} onSent={() => setShowApplicationModal(false)} />
      )}

      {/* SMS Modal */}
      {lead && <SMSModal isOpen={showSMSModal} onClose={() => setShowSMSModal(false)} lead={lead} />}
      {/* Teams Modal */}
      {lead && <TeamsModal isOpen={showTeamsModal} onClose={() => setShowTeamsModal(false)} lead={lead} />}
      {/* Recording Modal */}
      {lead && <RecordingModal isOpen={showRecordingModal} onClose={() => setShowRecordingModal(false)} lead={lead} />}
      {/* Voicemail Drop */}
      {lead && showVoicemailDrop && <VoicemailDrop phoneNumber={lead.phone} recipientName={lead.name} onClose={() => setShowVoicemailDrop(false)} />}
      {/* Escalation Modal */}
      {lead && <EscalationModal isOpen={showEscalationModal} onClose={() => setShowEscalationModal(false)} lead={lead} />}
      {/* Create Task Modal */}
      {lead && <CreateTaskModal isOpen={showTaskModal} onClose={() => setShowTaskModal(false)} lead={lead} />}
      {/* Appointment Modal (legacy) */}
      {lead && <AppointmentModal isOpen={showAppointmentModal} onClose={() => setShowAppointmentModal(false)} lead={lead} />}
      {/* Schedule Appointment Modal */}
      {lead && <ScheduleAppointmentModal isOpen={showScheduleModal} onClose={() => setShowScheduleModal(false)} onSuccess={() => setCalendarRefreshKey(prev => prev + 1)} borrower={lead} />}
      {/* Video Call Schedule Modal */}
      <VideoCallScheduleModal isOpen={showVideoMeetings} onClose={() => setShowVideoMeetings(false)} borrower={lead} onStartVideoCall={(data) => console.log('Video call started:', data)} />
      {/* Send Video Message Modal */}
      {lead && clientPortalData?.workspace_id && (
        <SendVideoModal isOpen={showSendVideoModal} onClose={() => setShowSendVideoModal(false)} recipientType="client" recipientId={clientPortalData.workspace_id}
          recipientName={`${lead.first_name || ''} ${lead.last_name || lead.name || 'Client'}`.trim()} onSuccess={() => console.log('Video sent successfully')} />
      )}
      {/* Email Composer Modal */}
      <EmailComposerModal isOpen={showEmailComposer} onClose={() => setShowEmailComposer(false)}
        recipient={{ name: lead?.name, email: lead?.email }} entityType="lead"
        entityData={{ id: lead?.id, stage: lead?.stage, source: lead?.source, loan_amount: lead?.loan_amount }} />

      {/* Email Draft Modal */}
      {showDraftModal && selectedDraft && (
        <div className="modal-overlay" onClick={() => setShowDraftModal(false)}>
          <div className="modal-content draft-modal" onClick={(e) => e.stopPropagation()} style={{
            maxWidth: '800px', width: '90%', maxHeight: '90vh', overflow: 'auto',
            backgroundColor: 'white', borderRadius: '12px', padding: '24px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ margin: 0 }}>
                <span style={{ backgroundColor: '#fef3c7', color: '#d97706', padding: '4px 10px', borderRadius: '6px', fontSize: '14px', marginRight: '10px' }}>DRAFT</span>
                Edit Email Draft
              </h2>
              <button onClick={() => setShowDraftModal(false)} style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: '#666' }}>x</button>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '600', color: '#374151' }}>To:</label>
              <input type="text" value={selectedDraft.recipient_email || ''} readOnly style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px', backgroundColor: '#f9fafb' }} />
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '600', color: '#374151' }}>CC Recipients:</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
                {ccRecipients.map((recipient, index) => (
                  <span key={index} style={{ display: 'flex', alignItems: 'center', gap: '4px', backgroundColor: '#e5e7eb', padding: '4px 10px', borderRadius: '20px', fontSize: '14px' }}>
                    {recipient.name || recipient.email}
                    <button onClick={() => removeCcRecipient(recipient.email)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: '0 2px' }}>x</button>
                  </span>
                ))}
              </div>
              <div style={{ display: 'flex', gap: '8px', position: 'relative' }}>
                <input type="text" value={ccSearchQuery} onChange={(e) => { setCcSearchQuery(e.target.value); searchCcContacts(e.target.value); }}
                  placeholder="Search contacts to add CC..." style={{ flex: 1, padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }} />
                <button onClick={() => { if (ccSearchQuery && ccSearchQuery.includes('@')) addCcRecipient({ email: ccSearchQuery, name: ccSearchQuery }); }}
                  style={{ padding: '10px 16px', backgroundColor: '#3b82f6', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '18px' }} title="Add CC recipient">+</button>
              </div>
              {ccSearchResults.length > 0 && (
                <div style={{ position: 'absolute', backgroundColor: 'white', border: '1px solid #d1d5db', borderRadius: '6px', boxShadow: '0 4px 6px rgba(0,0,0,0.1)', maxHeight: '200px', overflow: 'auto', zIndex: 1000, width: 'calc(100% - 80px)' }}>
                  {ccSearchResults.map((contact, index) => (
                    <div key={index} onClick={() => addCcRecipient(contact)}
                      style={{ padding: '10px', cursor: 'pointer', borderBottom: '1px solid #e5e7eb' }}
                      onMouseEnter={(e) => e.target.style.backgroundColor = '#f3f4f6'} onMouseLeave={(e) => e.target.style.backgroundColor = 'white'}>
                      <div style={{ fontWeight: '600' }}>{contact.name}</div>
                      <div style={{ fontSize: '12px', color: '#6b7280' }}>{contact.email}</div>
                    </div>
                  ))}
                </div>
              )}
              {ccSearchLoading && <div style={{ marginTop: '8px', color: '#6b7280', fontSize: '14px' }}>Searching...</div>}
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '600', color: '#374151' }}>Subject:</label>
              <input type="text" value={selectedDraft.subject || ''} onChange={(e) => setSelectedDraft({ ...selectedDraft, subject: e.target.value })}
                style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }} />
            </div>

            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '600', color: '#374151' }}>Body:</label>
              <textarea value={selectedDraft.body_html?.replace(/<[^>]*>/g, '') || selectedDraft.body_text || ''}
                onChange={(e) => setSelectedDraft({ ...selectedDraft, body_html: e.target.value, body_text: e.target.value })} rows={12}
                style={{ width: '100%', padding: '12px', border: '1px solid #d1d5db', borderRadius: '6px', resize: 'vertical', fontFamily: 'inherit', lineHeight: '1.5' }} />
            </div>

            {selectedDraft.action_items && selectedDraft.action_items.length > 0 && (
              <div style={{ marginBottom: '20px', padding: '16px', backgroundColor: '#f9fafb', borderRadius: '8px' }}>
                <h4 style={{ margin: '0 0 12px 0', color: '#374151' }}>Action Items:</h4>
                <ul style={{ margin: 0, paddingLeft: '20px' }}>
                  {selectedDraft.action_items.map((item, index) => <li key={index} style={{ marginBottom: '8px', color: '#4b5563' }}>{item}</li>)}
                </ul>
              </div>
            )}

            {selectedDraft.recording_url && (
              <div style={{ marginBottom: '20px', padding: '12px', backgroundColor: '#fef3c7', borderRadius: '8px' }}>
                <span style={{ color: '#d97706' }}>Recording attached: </span>
                <a href={selectedDraft.recording_url} target="_blank" rel="noopener noreferrer" style={{ color: '#2563eb' }}>View Recording</a>
              </div>
            )}

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button onClick={deleteDraft} disabled={draftLoading}
                style={{ padding: '10px 20px', backgroundColor: '#fee2e2', color: '#dc2626', border: 'none', borderRadius: '6px', cursor: draftLoading ? 'not-allowed' : 'pointer', fontWeight: '600' }}>
                Delete
              </button>
              <button onClick={saveDraft} disabled={draftLoading}
                style={{ padding: '10px 20px', backgroundColor: '#f3f4f6', color: '#374151', border: '1px solid #d1d5db', borderRadius: '6px', cursor: draftLoading ? 'not-allowed' : 'pointer', fontWeight: '600' }}>
                {draftLoading ? 'Saving...' : 'Save Draft'}
              </button>
              <button onClick={sendDraft} disabled={draftLoading}
                style={{ padding: '10px 24px', backgroundColor: '#3b82f6', color: 'white', border: 'none', borderRadius: '6px', cursor: draftLoading ? 'not-allowed' : 'pointer', fontWeight: '600' }}>
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
          <button className="action-btn sms" onClick={() => handleAction('sms')} disabled={!lead.phone} title="Send SMS"><span>SMS Text</span></button>
          <button className="action-btn email" onClick={() => handleAction('email')} disabled={!lead.email} title="Send email"><span>Send Email</span></button>
          <button className="action-btn task" onClick={() => handleAction('task')} title="Create task"><span>Create Task</span></button>
          <button className="action-btn calendar" onClick={() => handleAction('calendar')} title="Set appointment"><span>Set Appointment</span></button>
          <button className="action-btn video" onClick={() => handleAction('video')} title="Start video call"><span>Video Call</span></button>
          <button className="action-btn voicemail" onClick={() => handleAction('voicemail')} disabled={!lead.phone} title="Drop voicemail"><span>Voicemail Drop</span></button>
          <button className="action-btn record-video" onClick={() => setShowSendVideoModal(true)} disabled={!clientPortalData?.workspace_id} title={clientPortalData?.workspace_id ? "Record and send a video message" : "Create a Client Portal first to enable video messaging"}><span>Record Video</span></button>
          <button className="action-btn application" onClick={() => handleAction('send_application')} disabled={applicationLoading} title="Send application link"><span>{applicationLoading ? 'Creating...' : 'Send Application'}</span></button>
          <button className="action-btn portal" onClick={() => handleAction('client_portal')} disabled={clientPortalLoading} title="Access portals"><span>{clientPortalLoading ? 'Loading...' : 'Portals'}</span></button>
          <button className="action-btn escalation" onClick={() => handleAction('escalation')} title="Escalate issue"><span>Escalation</span></button>
        </div>
      </div>
    </CalendarSidebar>
      {lead && lead.phone && (
        <SMSAccordionPanel
          contactId={lead.id}
          contactName={lead.name || `${lead.first_name || ''} ${lead.last_name || ''}`.trim()}
          phone={lead.phone}
          pageType="client"
          assignedUser={lead.owner_id}
          borrowers={borrowers.filter(b => b.data?.phone).map(b => ({ id: b.id, name: b.name, phone: b.data.phone, type: b.type }))}
        />
      )}
    </div>
  );
}

export default LeadDetail;
