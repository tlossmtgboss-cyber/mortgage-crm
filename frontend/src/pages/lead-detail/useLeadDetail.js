import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { leadsAPI, activitiesAPI, loansAPI, borrowerApplicationAPI, purlAPI, partnersAPI } from '../../services/api';
import { apiFetch } from './shared/api';
import { generateMockLeads } from './shared/constants';
import DispositionNoteModal from '../../components/DispositionNoteModal';
import { toast } from '../../utils/toast';

export default function useLeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [lead, setLead] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(true);
  const [formData, setFormData] = useState({});
  const [emails, setEmails] = useState([]);
  const [activeTab, setActiveTab] = useState('loan-details');
  const [personalSubTab, setPersonalSubTab] = useState('info');
  const [propertySubTab, setPropertySubTab] = useState('property');
  const [incomeCalcMode, setIncomeCalcMode] = useState('unified');
  const [noteText, setNoteText] = useState('');
  const [noteLoading, setNoteLoading] = useState(false);
  const [borrowers, setBorrowers] = useState([]);
  const [activeBorrower, setActiveBorrower] = useState(0);
  const [saveTimeout, setSaveTimeout] = useState(null);

  // Modal visibility state
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
  const [showSendVideoModal, setShowSendVideoModal] = useState(false);

  // Client Portal state
  const [showClientPortalModal, setShowClientPortalModal] = useState(false);
  const [clientPortalData, setClientPortalData] = useState(null);
  const [clientPortalLoading, setClientPortalLoading] = useState(false);

  // Email drafts state
  const [emailDrafts, setEmailDrafts] = useState([]);
  const [selectedDraft, setSelectedDraft] = useState(null);
  const [showDraftModal, setShowDraftModal] = useState(false);
  const [draftLoading, setDraftLoading] = useState(false);
  const [ccRecipients, setCcRecipients] = useState([]);
  const [ccSearchQuery, setCcSearchQuery] = useState('');
  const [ccSearchResults, setCcSearchResults] = useState([]);
  const [ccSearchLoading, setCcSearchLoading] = useState(false);

  // Status dropdown state
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);
  const [statusSaving, setStatusSaving] = useState(false);

  // Referral Partners state
  const [referralPartners, setReferralPartners] = useState([]);

  // Custom fields state
  const [customFields, setCustomFields] = useState([]);
  const [showAddFieldModal, setShowAddFieldModal] = useState(false);
  const [newFieldName, setNewFieldName] = useState('');

  // Lead navigation state
  const [leadsList, setLeadsList] = useState([]);
  const [currentLeadIndex, setCurrentLeadIndex] = useState(-1);

  // ── Data Loading ─────────────────────────────────────────────

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
        leads = generateMockLeads();
      }
      setLeadsList(leads);
      const currentId = parseInt(id);
      const index = leads.findIndex(l => l.id === currentId);
      setCurrentLeadIndex(index);
    } catch (error) {
      console.error('Error loading leads list:', error);
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

  const loadLeadData = async () => {
    try {
      setLoading(true);
      let leadData = null;
      let activitiesData = [];

      try {
        const leadIdInt = parseInt(id);
        try {
          leadData = await leadsAPI.getById(leadIdInt);
        } catch (leadError) {
          if (leadError?.response?.status === 404) {
            setError('Lead not found. It may have been deleted.');
            setLoading(false);
            return;
          }
          const errorMessage = leadError?.response?.data?.detail || leadError?.message || 'Failed to load lead';
          setError(errorMessage);
          setLoading(false);
          return;
        }
        try {
          activitiesData = await activitiesAPI.getAll({ lead_id: parseInt(id) });
        } catch (actError) {
          console.warn('Failed to load activities, continuing without them:', actError?.message);
          activitiesData = [];
        }
      } catch (apiError) {
        const errorMessage = apiError?.response?.data?.detail || apiError?.message || 'Failed to load lead';
        setError(errorMessage);
        setLoading(false);
        return;
      }

      setLead(leadData);

      let processedData = { ...leadData };
      if (leadData.name && (!leadData.first_name || !leadData.last_name)) {
        const nameParts = leadData.name.split(' ');
        processedData.first_name = nameParts[0] || '';
        processedData.last_name = nameParts.slice(1).join(' ') || '';
      }

      setFormData(processedData);
      setActivities(activitiesData || []);

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
      const emailActivities = await activitiesAPI.getAll({ lead_id: id, type: 'email' });
      setEmails(emailActivities || []);
    } catch (error) {
      console.error('Failed to load emails:', error);
    }
  };

  const loadEmailDrafts = async () => {
    try {
      const response = await apiFetch(`/api/v1/email-drafts?lead_id=${id}&status=draft`);
      if (response.ok) {
        const data = await response.json();
        setEmailDrafts(data.drafts || data || []);
      }
    } catch (error) {
      console.error('Failed to load email drafts:', error);
    }
  };

  // ── Status Change ────────────────────────────────────────────

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

  // ── Field Change / Auto-Save ─────────────────────────────────

  const autoSaveField = async (fieldName, fieldValue) => {
    try {
      let dataToSave;
      if (activeBorrower === 1) {
        const updatedData = {...formData, [fieldName]: fieldValue};
        const coApplicantName = updatedData.first_name && updatedData.last_name
          ? `${updatedData.first_name} ${updatedData.last_name}` : updatedData.name || '';
        dataToSave = {
          co_applicant_name: coApplicantName,
          co_applicant_email: updatedData.email || null,
          co_applicant_phone: updatedData.phone || null
        };
      } else {
        dataToSave = { [fieldName]: fieldValue };
        if (fieldName === 'first_name' || fieldName === 'last_name') {
          const updatedData = {...formData, [fieldName]: fieldValue};
          if (updatedData.first_name && updatedData.last_name) {
            dataToSave.name = `${updatedData.first_name} ${updatedData.last_name}`;
          }
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
    const newTimeout = setTimeout(() => {
      autoSaveField(fieldName, fieldValue);
    }, 1000);
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

  // ── Save / Cancel ────────────────────────────────────────────

  const handleSave = async () => {
    try {
      let dataToSave;
      if (activeBorrower === 1) {
        const coApplicantName = formData.first_name && formData.last_name
          ? `${formData.first_name} ${formData.last_name}` : formData.name || '';
        dataToSave = {
          co_applicant_name: coApplicantName,
          co_applicant_email: formData.email || null,
          co_applicant_phone: formData.phone || null
        };
      } else {
        dataToSave = {
          ...formData,
          name: formData.first_name && formData.last_name
            ? `${formData.first_name} ${formData.last_name}` : formData.name || ''
        };
      }

      await leadsAPI.update(id, dataToSave);
      const updatedLead = await leadsAPI.getById(id);
      setLead(updatedLead);

      if (activeBorrower === 1 && updatedLead.co_applicant_name) {
        const primaryName = updatedLead.first_name && updatedLead.last_name
          ? `${updatedLead.first_name} ${updatedLead.last_name}` : updatedLead.name || 'Primary Borrower';
        const coborrowerParts = (updatedLead.co_applicant_name || '').split(' ');
        const updatedBorrowers = [
          { id: 0, name: primaryName, type: 'primary', data: updatedLead },
          {
            id: 1, name: updatedLead.co_applicant_name, type: 'co-borrower',
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
    } catch (error) {
      console.error('Failed to update lead:', error);
      toast.error('Failed to update lead');
    }
  };

  const handleCancel = () => {
    if (activeBorrower < borrowers.length) {
      setFormData(borrowers[activeBorrower].data);
    } else {
      setFormData(lead);
    }
  };

  // ── Notes ────────────────────────────────────────────────────

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
    } finally {
      setNoteLoading(false);
    }
  };

  // ── Borrower Switching ───────────────────────────────────────

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

        const primaryName = leadData.first_name && leadData.last_name
          ? `${leadData.first_name} ${leadData.last_name}` : leadData.name || 'Primary Borrower';
        const updatedBorrowers = [{ id: 0, name: primaryName, type: 'primary', data: leadData }];

        if (leadData.co_applicant_name) {
          const coborrowerParts = (leadData.co_applicant_name || '').split(' ');
          updatedBorrowers.push({
            id: 1, name: leadData.co_applicant_name, type: 'co-borrower',
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
        if (updatedBorrowers[targetIndex]) setFormData(updatedBorrowers[targetIndex].data);
      } else {
        const newBorrower = {
          id: borrowers.length,
          name: fullName,
          type: 'additional',
          data: { name: fullName, first_name: firstName.trim(), last_name: lastName.trim() }
        };
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

  // ── Navigation ───────────────────────────────────────────────

  const handleViewNextLead = () => {
    if (leadsList.length === 0) return;
    let nextIndex = currentLeadIndex + 1;
    if (nextIndex >= leadsList.length) nextIndex = 0;
    const nextLead = leadsList[nextIndex];
    if (nextLead && nextLead.id) navigate(`/leads/${nextLead.id}`);
  };

  // ── Voice Command ────────────────────────────────────────────

  const handleVoiceCommand = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      toast.error('Sorry, your browser does not support speech recognition. Please try Chrome or Edge.');
      return;
    }
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

  // ── Application / Client Portal ──────────────────────────────

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
    } finally {
      setApplicationLoading(false);
    }
  };

  const copyApplicationLink = async () => {
    if (!applicationLink?.url) return;
    try {
      await navigator.clipboard.writeText(applicationLink.url);
      toast.success('Application link copied to clipboard!');
    } catch (err) {
      const textArea = document.createElement('textarea');
      textArea.value = applicationLink.url;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      toast.success('Application link copied to clipboard!');
    }
  };

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
      const response = await purlAPI.createWorkspace({ lead_id: lead.id, borrower_name: borrowerName, first_name: lead.first_name, last_name: lead.last_name, email: lead.email, phone: lead.phone });
      const newWorkspace = response.workspace || response;
      const tokenResponse = await purlAPI.createToken(newWorkspace.id, { scope: 'full', expires_in_days: 90 });
      const fullToken = tokenResponse.token;
      const baseUrl = `${window.location.origin}/portal/${newWorkspace.slug}`;
      const portalUrl = fullToken ? `${baseUrl}?token=${fullToken}` : baseUrl;
      setClientPortalData({ workspace_id: newWorkspace.id, url: portalUrl, borrower_name: borrowerName, status: newWorkspace.status, exists: false, justCreated: true });
      setShowClientPortalModal(true);
    } catch (err) {
      let errorMessage = 'Unknown error occurred';
      if (err.response?.data?.detail) errorMessage = err.response.data.detail;
      else if (err.message === 'Network Error') errorMessage = 'Unable to connect to server.';
      else if (err.message) errorMessage = err.message;
      toast.error(`Failed to access/create client portal: ${errorMessage}`);
    } finally {
      setClientPortalLoading(false);
    }
  };

  const copyClientPortalLink = async () => {
    if (!clientPortalData?.url) return;
    try {
      await navigator.clipboard.writeText(clientPortalData.url);
      toast.success('Client portal link copied to clipboard!');
    } catch (err) {
      const textArea = document.createElement('textarea');
      textArea.value = clientPortalData.url;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      toast.success('Client portal link copied to clipboard!');
    }
  };

  // ── Email Draft Management ───────────────────────────────────

  const searchCcContacts = async (query) => {
    if (!query || query.length < 2) { setCcSearchResults([]); return; }
    setCcSearchLoading(true);
    try {
      const response = await apiFetch(`/api/v1/contacts/search?q=${encodeURIComponent(query)}`);
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
    if (!ccRecipients.find(c => c.email === contact.email)) setCcRecipients([...ccRecipients, contact]);
    setCcSearchQuery('');
    setCcSearchResults([]);
  };

  const removeCcRecipient = (email) => { setCcRecipients(ccRecipients.filter(c => c.email !== email)); };

  const openDraft = (draft) => {
    setSelectedDraft({ ...draft, body_html: draft.body_html || '', subject: draft.subject || '' });
    setCcRecipients(draft.cc_emails || []);
    setShowDraftModal(true);
  };

  const saveDraft = async () => {
    if (!selectedDraft) return;
    setDraftLoading(true);
    try {
      const response = await apiFetch(`/api/v1/email-drafts/${selectedDraft.id}`, {
        method: 'PUT',
        body: JSON.stringify({ subject: selectedDraft.subject, body_html: selectedDraft.body_html, cc_emails: ccRecipients })
      });
      if (response.ok) { await loadEmailDrafts(); toast.success('Draft saved successfully!'); }
      else throw new Error('Failed to save draft');
    } catch (error) {
      console.error('Error saving draft:', error);
      toast.error('Failed to save draft');
    } finally {
      setDraftLoading(false);
    }
  };

  const deleteDraft = async () => {
    if (!selectedDraft) return;
    setDraftLoading(true);
    try {
      const response = await apiFetch(`/api/v1/email-drafts/${selectedDraft.id}`, { method: 'DELETE' });
      if (response.ok) { setShowDraftModal(false); setSelectedDraft(null); await loadEmailDrafts(); toast.success('Draft deleted'); }
      else throw new Error('Failed to delete draft');
    } catch (error) {
      console.error('Error deleting draft:', error);
      toast.error('Failed to delete draft');
    } finally {
      setDraftLoading(false);
    }
  };

  const sendDraft = async () => {
    if (!selectedDraft) return;
    setDraftLoading(true);
    try {
      await apiFetch(`/api/v1/email-drafts/${selectedDraft.id}`, {
        method: 'PUT',
        body: JSON.stringify({ subject: selectedDraft.subject, body_html: selectedDraft.body_html, cc_emails: ccRecipients })
      });
      const response = await apiFetch(`/api/v1/email-drafts/${selectedDraft.id}/send`, { method: 'POST' });
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

  // ── Custom Fields ────────────────────────────────────────────

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

  // ── Action Handler ───────────────────────────────────────────

  const handleAction = async (action) => {
    switch(action) {
      case 'call':
        if (!lead.phone) { toast.error('No phone number available for this lead'); return; }
        {
          const cleanPhone = lead.phone.replace(/[^\d+]/g, '');
          const dialNumber = cleanPhone.startsWith('+') ? cleanPhone : `+1${cleanPhone}`;
          window.open(`https://teams.microsoft.com/l/call/0/0?users=4:${encodeURIComponent(dialNumber)}`, '_blank');
        }
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

  return {
    // Core data
    id, navigate, lead, setLead, activities, loading, error, editing, setEditing,
    formData, setFormData, emails, activeTab, setActiveTab,
    personalSubTab, setPersonalSubTab, propertySubTab, setPropertySubTab,
    incomeCalcMode, setIncomeCalcMode,
    noteText, setNoteText, noteLoading, borrowers, activeBorrower,

    // Modal state
    showSMSModal, setShowSMSModal, showTeamsModal, setShowTeamsModal,
    showRecordingModal, setShowRecordingModal, showVoicemailDrop, setShowVoicemailDrop,
    showTaskModal, setShowTaskModal, showAppointmentModal, setShowAppointmentModal,
    showScheduleModal, setShowScheduleModal, calendarRefreshKey, setCalendarRefreshKey,
    showEscalationModal, setShowEscalationModal,
    showVideoMeetings, setShowVideoMeetings, showEmailComposer, setShowEmailComposer,
    isListening, voiceTranscript,
    showApplicationModal, setShowApplicationModal, applicationLink,
    dispositionModal, setDispositionModal, applicationLoading,
    showSendVideoModal, setShowSendVideoModal,

    // Client portal
    showClientPortalModal, setShowClientPortalModal, clientPortalData, clientPortalLoading,
    copyClientPortalLink,

    // Email drafts
    emailDrafts, selectedDraft, setSelectedDraft, showDraftModal, setShowDraftModal,
    draftLoading, ccRecipients, setCcRecipients, ccSearchQuery, setCcSearchQuery,
    ccSearchResults, ccSearchLoading, openDraft, saveDraft, deleteDraft, sendDraft,
    searchCcContacts, addCcRecipient, removeCcRecipient,

    // Status
    showStatusDropdown, setShowStatusDropdown, statusSaving,
    handleStatusChange, executeStatusChange,

    // Referral partners
    referralPartners,

    // Custom fields
    customFields, showAddFieldModal, setShowAddFieldModal, newFieldName, setNewFieldName,
    handleAddCustomField, handleRemoveCustomField,

    // Lead navigation
    leadsList, handleViewNextLead,

    // Handlers
    handleFieldChange, handleIncomeChange, handleSave, handleCancel,
    handleAddNote, handleSwitchBorrower, handleAddBorrower,
    handleAction, loadLeadData, copyApplicationLink,
  };
}
