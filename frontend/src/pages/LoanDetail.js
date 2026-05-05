import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { loansAPI, activitiesAPI, circleOfCashflowAPI, partnersAPI, salesforceAPI, borrowerApplicationAPI } from '../services/api';
import { toast } from '../utils/toast';
import VoicemailDrop from '../components/VoicemailDrop';
import SMSModal from '../components/SMSModal';
import TeamsModal from '../components/TeamsModal';
import RecordingModal from '../components/RecordingModal';
import CreateTaskModal from '../components/CreateTaskModal';
import AppointmentModal from '../components/AppointmentModal';
import ScheduleAppointmentModal from '../components/ScheduleAppointmentModal';
import EscalationModal from '../components/EscalationModal';
import EmploymentTab from '../components/EmploymentTab';
import VideoCallScheduleModal from '../components/VideoCallScheduleModal';
import EmailComposerModal from '../components/EmailComposerModal';
import CalendarSidebar from '../components/CalendarSidebar';
import AddressAutocomplete from '../components/AddressAutocomplete';
import SmartDocumentUpload from '../components/smart-docs/SmartDocumentUpload';
import LoanSmartDocsTab from '../components/smart-docs/LoanSmartDocsTab';
import IncomeCalculator from '../components/IncomeCalculator';
import UnifiedIncomeCalculator from '../components/income/UnifiedIncomeCalculator';
import PortalSelectorModal from '../components/PortalSelectorModal';
import SendVideoModal from '../components/video/SendVideoModal';
import CreditTab from '../components/CreditTab';
import WorkflowRoleAssignment from '../components/WorkflowRoleAssignment';
import SalesforceConnectionBadge from '../components/SalesforceConnectionBadge';
import { formatPhoneNumber } from '../utils/phoneUtils';
import CurrencyInput from '../components/common/CurrencyInput';
import SMSAccordionPanel from '../components/sms/SMSAccordionPanel';
import AIActivityTab from '../components/ai/AIActivityTab';
import './LeadDetail.css';
import { getToken } from '../utils/tokenStore';

// Mock loans data (same as Loans.js)
const generateMockLoans = () => {
  const currentDate = new Date();
  const currentMonth = currentDate.getMonth();
  const currentYear = currentDate.getFullYear();

  return [
    { id: 1, borrower_name: 'John Anderson', borrower: 'John Anderson', amount: 425000, property_address: '123 Oak St, Austin TX', stage: 'Funded This Month', days_in_process: 28, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 5).toISOString(), funded_date: new Date(currentYear, currentMonth, 5).toISOString() },
    { id: 2, borrower_name: 'Maria Garcia', borrower: 'Maria Garcia', amount: 380000, property_address: '456 Pine Ave, Dallas TX', stage: 'Funded This Month', days_in_process: 32, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth, 8).toISOString(), funded_date: new Date(currentYear, currentMonth, 8).toISOString() },
    { id: 3, borrower_name: 'Robert Kim', borrower: 'Robert Kim', amount: 520000, property_address: '789 Elm Dr, Houston TX', stage: 'Funded This Month', days_in_process: 25, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 12).toISOString(), funded_date: new Date(currentYear, currentMonth, 12).toISOString() },
    { id: 4, borrower_name: 'Lisa Chen', borrower: 'Lisa Chen', amount: 295000, property_address: '321 Maple Rd, San Antonio TX', stage: 'Funded This Month', days_in_process: 30, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 15).toISOString(), funded_date: new Date(currentYear, currentMonth, 15).toISOString() },
    { id: 5, borrower_name: 'David Martinez', borrower: 'David Martinez', amount: 615000, property_address: '654 Cedar Ln, Fort Worth TX', stage: 'Funded This Month', days_in_process: 27, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth, 18).toISOString(), funded_date: new Date(currentYear, currentMonth, 18).toISOString() },
    { id: 6, borrower_name: 'Amy Wilson', borrower: 'Amy Wilson', amount: 340000, property_address: '987 Birch St, Arlington TX', stage: 'Funded This Month', days_in_process: 29, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 20).toISOString(), funded_date: new Date(currentYear, currentMonth, 20).toISOString() },
    { id: 7, borrower_name: 'James Brown', borrower: 'James Brown', amount: 450000, property_address: '147 Spruce Ave, Plano TX', stage: 'Funded This Month', days_in_process: 31, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 22).toISOString(), funded_date: new Date(currentYear, currentMonth, 22).toISOString() },
    { id: 8, borrower_name: 'Jennifer Lee', borrower: 'Jennifer Lee', amount: 385000, property_address: '258 Walnut Dr, Irving TX', stage: 'Funded This Month', days_in_process: 26, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth, 25).toISOString(), funded_date: new Date(currentYear, currentMonth, 25).toISOString() },
    { id: 9, borrower_name: 'Michael Davis', borrower: 'Michael Davis', amount: 495000, property_address: '369 Ash Rd, Frisco TX', stage: 'Funded This Month', days_in_process: 28, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 27).toISOString(), funded_date: new Date(currentYear, currentMonth, 27).toISOString() },
    { id: 10, borrower_name: 'Thomas White', borrower: 'Thomas White', amount: 410000, property_address: '741 Cherry Ln, McKinney TX', stage: 'Funded Prior Month', days_in_process: 30, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth - 1, 5).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 5).toISOString() },
    { id: 11, borrower_name: 'Susan Taylor', borrower: 'Susan Taylor', amount: 375000, property_address: '852 Poplar St, Denton TX', stage: 'Funded Prior Month', days_in_process: 29, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth - 1, 10).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 10).toISOString() },
    { id: 12, borrower_name: 'Daniel Moore', borrower: 'Daniel Moore', amount: 530000, property_address: '963 Hickory Ave, Allen TX', stage: 'Funded Prior Month', days_in_process: 32, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth - 1, 12).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 12).toISOString() },
    { id: 13, borrower_name: 'Patricia Johnson', borrower: 'Patricia Johnson', amount: 325000, property_address: '159 Willow Dr, Carrollton TX', stage: 'Funded Prior Month', days_in_process: 27, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth - 1, 15).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 15).toISOString() },
    { id: 14, borrower_name: 'Kevin Anderson', borrower: 'Kevin Anderson', amount: 445000, property_address: '357 Magnolia Rd, Richardson TX', stage: 'Funded Prior Month', days_in_process: 28, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth - 1, 18).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 18).toISOString() },
    { id: 15, borrower_name: 'Nancy Thomas', borrower: 'Nancy Thomas', amount: 365000, property_address: '486 Sycamore Ln, Lewisville TX', stage: 'Funded Prior Month', days_in_process: 31, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth - 1, 20).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 20).toISOString() },
    { id: 16, borrower_name: 'Emily Davis', borrower: 'Emily Davis', amount: 520000, property_address: '890 Second St, Houston TX', stage: 'In Processing', days_in_process: 12, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 18).toISOString() },
    { id: 17, borrower_name: 'Rachel Martinez', borrower: 'Rachel Martinez', amount: 345000, property_address: '234 Oak Lane, Austin TX', stage: 'In Processing', days_in_process: 8, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 22).toISOString() },
    { id: 18, borrower_name: 'Tom Wilson', borrower: 'Tom Wilson', amount: 295000, property_address: '123 Third Dr, San Antonio TX', stage: 'In Underwriting', days_in_process: 18, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 12).toISOString() },
    { id: 19, borrower_name: 'Carlos Rodriguez', borrower: 'Carlos Rodriguez', amount: 475000, property_address: '567 Elm Street, Dallas TX', stage: 'In Underwriting', days_in_process: 15, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth, 15).toISOString() },
    { id: 20, borrower_name: 'Jessica Parker', borrower: 'Jessica Parker', amount: 525000, property_address: '789 Maple Ave, Plano TX', stage: 'Approved', days_in_process: 20, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 10).toISOString() },
    { id: 21, borrower_name: 'Mark Stevens', borrower: 'Mark Stevens', amount: 395000, property_address: '321 Pine Dr, Fort Worth TX', stage: 'Approved', days_in_process: 19, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 11).toISOString() },
    { id: 22, borrower_name: 'Lisa Brown', borrower: 'Lisa Brown', amount: 615000, property_address: '456 Fourth Rd, Fort Worth TX', stage: 'Clear to Close', days_in_process: 22, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth, 8).toISOString() },
    { id: 23, borrower_name: 'Anna Thompson', borrower: 'Anna Thompson', amount: 410000, property_address: '654 Cedar Blvd, Irving TX', stage: 'Clear to Close', days_in_process: 24, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 6).toISOString() },
    { id: 24, borrower_name: 'Brian Foster', borrower: 'Brian Foster', amount: 285000, property_address: '987 Birch Ct, Arlington TX', stage: 'Suspended', days_in_process: 45, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth - 1, 25).toISOString() },
    { id: 25, borrower_name: 'Michelle Cooper', borrower: 'Michelle Cooper', amount: 330000, property_address: '147 Willow Way, Richardson TX', stage: 'Suspended', days_in_process: 38, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth - 1, 28).toISOString() },
  ];
};

function LoanDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [loan, setLoan] = useState(null);
  const [activities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(true);
  const [formData, setFormData] = useState({});
  const [activeTab, setActiveTab] = useState('loan-details');
  const [borrowers, setBorrowers] = useState([]);
  const [activeBorrower, setActiveBorrower] = useState(0);
  const [saveTimeout, setSaveTimeout] = useState(null);
  const [showVoicemailDrop, setShowVoicemailDrop] = useState(false);
  const [showSMSModal, setShowSMSModal] = useState(false);
  const [showTeamsModal, setShowTeamsModal] = useState(false);
  const [showRecordingModal, setShowRecordingModal] = useState(false);
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [showAppointmentModal, setShowAppointmentModal] = useState(false);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [calendarRefreshKey, setCalendarRefreshKey] = useState(0);
  const [showEscalationModal, setShowEscalationModal] = useState(false);
  const [showVideoCall, setShowVideoCall] = useState(false);
  const [showEmailComposer, setShowEmailComposer] = useState(false);
  const [showApplicationModal, setShowApplicationModal] = useState(false);
  const [applicationLink, setApplicationLink] = useState(null);
  const [applicationLoading, setApplicationLoading] = useState(false);
  const [showPortalSelector, setShowPortalSelector] = useState(false);
  const [showSendVideoModal, setShowSendVideoModal] = useState(false);
  const [clientPortalWorkspaceId, setClientPortalWorkspaceId] = useState(null);
  const [, setIsListening] = useState(false);
  const [emailHistory, setEmailHistory] = useState([]);
  const [, setSelectedEmail] = useState(null);
  const [noteText, setNoteText] = useState('');
  const [noteLoading, setNoteLoading] = useState(false);

  // Salesforce sync state
  const [salesforceStatus, setSalesforceStatus] = useState(null);
  const [salesforcePulling, setSalesforcePulling] = useState(false);

  // Archive state
  const [archiveSubTab, setArchiveSubTab] = useState('notes'); // 'notes', 'email', 'sms', 'calls'
  const [propertySubTab, setPropertySubTab] = useState('property'); // 'property', 'insurance', 'legal'
  const [emailArchive] = useState([]);
  const [smsArchive] = useState([]);
  const [callArchive] = useState([]);
  const [archiveLoading] = useState(false);

  // Personal tab sub-tab state
  const [personalSubTab, setPersonalSubTab] = useState('info'); // 'info', 'employment', 'assets'

  // Income calculator mode
  const [incomeCalcMode, setIncomeCalcMode] = useState('unified'); // 'unified', 'basic'

  // Circle of Cashflow state
  const [cashflowOpportunities, setCashflowOpportunities] = useState([]);
  const [cashflowReferrals, setCashflowReferrals] = useState([]);
  const [, setCashflowPartners] = useState([]);
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

  // Loan navigation state
  const [loansList, setLoansList] = useState([]);
  const [currentLoanIndex, setCurrentLoanIndex] = useState(-1);

  // Team Members state
  const [teamMembers, setTeamMembers] = useState([]);
  const [standardMembers, setStandardMembers] = useState([]);
  const [showTeamMemberModal, setShowTeamMemberModal] = useState(false);
  const [editingTeamMember, setEditingTeamMember] = useState(null);
  const [teamMemberForm, setTeamMemberForm] = useState({
    name: '',
    role: '',
    email: '',
    phone: '',
    company: '',
    license_number: '',
    notes: '',
    is_employee: false
  });
  const [teamMemberLoading, setTeamMemberLoading] = useState(false);
  const [teamMemberSearchResults, setTeamMemberSearchResults] = useState([]);
  const [showTeamMemberSearchResults, setShowTeamMemberSearchResults] = useState(false);
  const [teamMemberSearchLoading, setTeamMemberSearchLoading] = useState(false);

  // Team member role options
  const teamMemberRoles = [
    'Realtor', 'Listing Agent', 'Buyer\'s Agent',
    'Title Agent', 'Escrow Officer', 'Insurance Agent',
    'Home Inspector', 'Appraiser', 'Attorney',
    'CPA/Accountant', 'Financial Advisor', 'Builder',
    'Contractor', 'HOA Contact', 'Other'
  ];

  useEffect(() => {
    loadLoanData();
    loadEmailHistory();
    loadLoansList();
    loadClientPortalWorkspaceId();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Load client portal workspace ID for video messaging
  const loadClientPortalWorkspaceId = async () => {
    if (!id) return;
    try {
      const apiUrl = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';
      const token = getToken();
      // Try looking up by loan ID first
      let response = await fetch(`${apiUrl}/api/v1/purl-admin/workspaces/by-loan/${id}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        if (data.workspace?.id) {
          setClientPortalWorkspaceId(data.workspace.id);
        }
      }
    } catch (error) {
      console.error('Error loading client portal workspace:', error);
    }
  };

  // Load list of loans for navigation
  const loadLoansList = async () => {
    try {
      let loans = [];
      try {
        const response = await loansAPI.getAll();
        loans = response.loans || response || [];
      } catch (apiError) {
        // Fallback to mock data
        loans = generateMockLoans();
      }
      setLoansList(loans);
      // Find current loan index
      const currentId = parseInt(id);
      const index = loans.findIndex(l => l.id === currentId);
      setCurrentLoanIndex(index);
    } catch (error) {
      console.error('Error loading loans list:', error);
    }
  };

  // Navigate to next loan
  const handleViewNextLoan = () => {
    if (loansList.length === 0) return;

    let nextIndex = currentLoanIndex + 1;
    if (nextIndex >= loansList.length) {
      nextIndex = 0; // Loop back to first loan
    }

    const nextLoan = loansList[nextIndex];
    if (nextLoan && nextLoan.id) {
      navigate(`/loans/${nextLoan.id}`);
    }
  };

  // Custom field handlers
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

  // Circle of Influence handlers
  // Professional contact types that should search partners instead of loans
  const professionalTypes = ['Real Estate Agent', 'Attorney', 'Financial Advisor', 'Insurance Agent', 'Accountant'];

  const searchContacts = async (query, contactType = circleForm.type) => {
    if (query.length < 2) {
      setSearchResults([]);
      setShowSearchResults(false);
      return;
    }
    setSearchLoading(true);
    try {
      // Search partners for professional contact types, loans for others
      if (professionalTypes.includes(contactType)) {
        const response = await partnersAPI.getAll({ search: query });
        // Map partner data to match expected format
        const partners = (response.partners || response || []).map(p => ({
          id: p.id,
          name: p.name,
          borrower_name: p.name,
          email: p.email,
          borrower_email: p.email,
          phone: p.phone,
          borrower_phone: p.phone,
          company: p.company,
          type: 'partner'
        }));
        setSearchResults(partners);
      } else {
        const response = await loansAPI.search(query);
        setSearchResults(response.loans || []);
      }
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
      name: contact.borrower_name || contact.name,
      email: contact.borrower_email || contact.email || '',
      phone: contact.borrower_phone || contact.phone || ''
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
        loanId: searchResults.find(r => (r.borrower_name || r.name) === circleForm.name)?.id || null,
        ...circleForm
      };
      setCircleContacts([...circleContacts, newContact]);
    }

    setCircleForm({ name: '', email: '', phone: '', type: 'Co-Borrower', notes: '' });
    setShowCircleModal(false);
    setShowSearchResults(false);
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
      loanId: contact.loanId
    });
    setShowCircleModal(true);
  };

  const getContactIcon = (type) => {
    const found = circleContactTypes.find(t => t.value === type);
    return found ? found.icon : '🤝';
  };

  // Load Circle of Cashflow data
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

  // Load conditions for the loan
  const loadConditions = async () => {
    if (!id) return;
    setConditionsLoading(true);
    try {
      const response = await fetch(`${process.env.REACT_APP_API_URL || ''}/api/v1/loans/${id}/conditions`);
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
      const response = await fetch(`${process.env.REACT_APP_API_URL || ''}/api/v1/loans/${id}/conditions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...newCondition,
          loan_id: id,
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
      const response = await fetch(`${process.env.REACT_APP_API_URL || ''}/api/v1/loans/${id}/conditions/${conditionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
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

  // Load conditions when Conditions tab is selected
  useEffect(() => {
    if (activeTab === 'documents') {
      loadConditions();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // Add note handler
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
      await activitiesAPI.create(noteData);
      setNoteText('');
      loadLoanData();
    } catch (error) {
      console.error('Failed to add note:', error);
      toast.error('Failed to add note');
    } finally {
      setNoteLoading(false);
    }
  };

  const loadEmailHistory = () => {
    // Load sent emails from localStorage (will be API later)
    const sentEmails = JSON.parse(localStorage.getItem('sentEmails') || '[]');
    // Filter emails for this loan/borrower
    const loanEmails = sentEmails.filter(email =>
      email.loanId === id || email.loanId === parseInt(id)
    );
    setEmailHistory(loanEmails);
  };

  const loadLoanData = async () => {
    try {
      setLoading(true);
      let loanData = null;

      try {
        // Try to fetch from API first
        loanData = await loansAPI.getById(id);
      } catch (apiError) {
        console.log('API failed, using mock data:', apiError);
        // Fallback to mock data
        const mockLoans = generateMockLoans();
        loanData = mockLoans.find(loan => loan.id === parseInt(id));

        if (!loanData) {
          toast.error('Loan not found');
          navigate('/loans');
          return;
        }
      }

      setLoan(loanData);
      setFormData(loanData);

      // Initialize borrowers array
      const borrowersList = [
        {
          id: 0,
          name: loanData.borrower_name || loanData.borrower || 'Primary Borrower',
          type: 'primary',
          data: {
            name: loanData.borrower_name || loanData.borrower,
            email: loanData.borrower_email,
            phone: loanData.borrower_phone,
          }
        }
      ];

      // Add co-borrower if exists
      if (loanData.coborrower_name) {
        borrowersList.push({
          id: 1,
          name: loanData.coborrower_name,
          type: 'co-borrower',
          data: {
            name: loanData.coborrower_name,
            email: loanData.co_borrower_email || '',
            phone: loanData.co_borrower_phone || '',
          }
        });
      }

      setBorrowers(borrowersList);
    } catch (err) {
      console.error('Failed to load loan data:', err);
      const errorMessage = err?.response?.data?.detail || err?.message || 'Failed to load loan details';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      await loansAPI.update(id, formData);
      setLoan(formData);
      setEditing(false);
      toast.success('Loan updated successfully!');
    } catch (error) {
      console.error('Failed to save loan:', error);
      toast.error('Failed to save changes');
    }
  };

  const handleCancel = () => {
    setFormData(loan);
  };

  const handleFieldChange = (field, value) => {
    const updatedData = { ...formData, [field]: value };
    setFormData(updatedData);

    // Auto-save after 1 second of no typing
    if (saveTimeout) clearTimeout(saveTimeout);
    setSaveTimeout(setTimeout(async () => {
      try {
        await loansAPI.update(id, { [field]: value });
      } catch (error) {
        console.error('Auto-save failed:', error);
      }
    }, 1000));
  };

  const handleSwitchBorrower = (borrowerIndex) => {
    setActiveBorrower(borrowerIndex);
    const borrower = borrowers[borrowerIndex];
    if (borrower && borrower.data) {
      setFormData({...formData, ...borrower.data});
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
        borrower_name: fullName,
        borrower_first_name: firstName.trim(),
        borrower_last_name: lastName.trim(),
      }
    };

    const updatedBorrowers = [...borrowers, newBorrower];
    setBorrowers(updatedBorrowers);
    setActiveBorrower(updatedBorrowers.length - 1);
    setFormData(newBorrower.data);
  };

  // ==================== TEAM MEMBER FUNCTIONS ====================
  const loadTeamMembers = async () => {
    try {
      const token = getToken();
      const response = await fetch(`${process.env.REACT_APP_API_URL || 'https://api.perenniaai.com'}/api/v1/loans/${id}/team-members`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setTeamMembers(data.team_members || []);
        setStandardMembers(data.standard_members || []);
      }
    } catch (error) {
      console.error('Error loading team members:', error);
    }
  };

  const handleAddTeamMember = () => {
    setEditingTeamMember(null);
    setTeamMemberForm({
      name: '',
      role: '',
      email: '',
      phone: '',
      company: '',
      license_number: '',
      notes: '',
      is_employee: false
    });
    setShowTeamMemberModal(true);
    setTeamMemberSearchResults([]);
    setShowTeamMemberSearchResults(false);
  };

  const searchTeamMemberPartners = async (query) => {
    if (query.length < 2) {
      setTeamMemberSearchResults([]);
      setShowTeamMemberSearchResults(false);
      return;
    }
    setTeamMemberSearchLoading(true);
    try {
      const response = await partnersAPI.getAll({ search: query });
      const partners = (response.partners || response || []).map(p => ({
        id: p.id,
        name: p.name,
        email: p.email,
        phone: p.phone,
        company: p.company,
        type: 'partner'
      }));
      setTeamMemberSearchResults(partners);
      setShowTeamMemberSearchResults(true);
    } catch (error) {
      console.error('Partner search error:', error);
      setTeamMemberSearchResults([]);
    } finally {
      setTeamMemberSearchLoading(false);
    }
  };

  const handleTeamMemberNameChange = (e) => {
    const value = e.target.value;
    setTeamMemberForm({ ...teamMemberForm, name: value });
    searchTeamMemberPartners(value);
  };

  const selectTeamMemberSearchResult = (partner) => {
    setTeamMemberForm({
      ...teamMemberForm,
      name: partner.name,
      email: partner.email || '',
      phone: partner.phone || '',
      company: partner.company || ''
    });
    setShowTeamMemberSearchResults(false);
    setTeamMemberSearchResults([]);
  };

  const handleEditTeamMember = (member) => {
    setEditingTeamMember(member);
    setTeamMemberForm({
      name: member.name || '',
      role: member.role || '',
      email: member.email || '',
      phone: member.phone || '',
      company: member.company || '',
      license_number: member.license_number || '',
      notes: member.notes || '',
      is_employee: member.is_employee || false
    });
    setShowTeamMemberModal(true);
  };

  const handleSaveTeamMember = async () => {
    if (!teamMemberForm.name || !teamMemberForm.role) {
      toast.error('Please enter a name and role');
      return;
    }

    setTeamMemberLoading(true);
    try {
      const token = getToken();
      const apiUrl = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

      if (editingTeamMember) {
        // Update existing member
        const response = await fetch(`${apiUrl}/api/v1/loans/${id}/team-members/${editingTeamMember.id}`, {
          method: 'PATCH',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(teamMemberForm)
        });

        if (response.ok) {
          await loadTeamMembers();
          setShowTeamMemberModal(false);
        } else {
          toast.error('Failed to update team member');
        }
      } else {
        // Create new member
        const response = await fetch(`${apiUrl}/api/v1/loans/${id}/team-members`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            loan_id: parseInt(id),
            ...teamMemberForm,
            create_as_partner: !teamMemberForm.is_employee
          })
        });

        if (response.ok) {
          const data = await response.json();
          await loadTeamMembers();
          setShowTeamMemberModal(false);

          // Notify if referral partner was created
          if (data.referral_partner_created) {
            toast.success(`${teamMemberForm.name} has been added and saved as a referral partner.`);
          }
        } else {
          toast.error('Failed to add team member');
        }
      }
    } catch (error) {
      console.error('Error saving team member:', error);
      toast.error('Error saving team member');
    } finally {
      setTeamMemberLoading(false);
    }
  };

  const handleDeleteTeamMember = async (memberId) => {
    try {
      const token = getToken();
      const apiUrl = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

      const response = await fetch(`${apiUrl}/api/v1/loans/${id}/team-members/${memberId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        await loadTeamMembers();
      } else {
        toast.error('Failed to remove team member');
      }
    } catch (error) {
      console.error('Error deleting team member:', error);
      toast.error('Error removing team member');
    }
  };

  // Load team members when loan loads
  useEffect(() => {
    if (id) {
      loadTeamMembers();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

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
      console.log('Voice command received:', transcript);

      // Send the transcript to the SmartAI chat
      window.dispatchEvent(new CustomEvent('voiceCommand', {
        detail: { transcript, loanId: loan.id }
      }));
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
      toast.error(`Voice recognition error: ${event.error}`);
    };

    recognition.onend = () => {
      setIsListening(false);
      console.log('Voice recognition ended.');
    };

    recognition.start();
  };

  // Salesforce pull handler - refresh data from Salesforce
  const handleSalesforcePull = async () => {
    if (salesforcePulling) return;

    try {
      setSalesforcePulling(true);

      // First check if Salesforce is connected
      const status = await salesforceAPI.getStatus();
      if (!status.connected) {
        toast.error('Salesforce is not connected. Please connect in Settings → Integrations.');
        return;
      }

      // Check if loan has Salesforce ID
      if (!salesforceStatus?.salesforce_id) {
        toast.error('This loan is not linked to Salesforce. Push it first to create the link.');
        return;
      }

      // Pull the loan from Salesforce
      const result = await salesforceAPI.pullLoan(id);

      if (result.status === 'success') {
        toast.success('Loan refreshed from Salesforce');
        // Reload the loan data to show updated fields
        loadLoanData();
        // Update sync status
        setSalesforceStatus({
          ...salesforceStatus,
          last_synced_at: new Date().toISOString(),
          sync_status: 'synced',
          needs_sync: false
        });
      }
    } catch (error) {
      console.error('Salesforce pull error:', error);
      const errorMsg = error.response?.data?.detail?.error || error.response?.data?.detail || error.message;
      toast.error(`Failed to pull from Salesforce: ${errorMsg}`);
    } finally {
      setSalesforcePulling(false);
    }
  };

  // Fetch Salesforce sync status when loan loads
  useEffect(() => {
    const fetchSalesforceStatus = async () => {
      try {
        const status = await salesforceAPI.getLoanSyncStatus(id);
        setSalesforceStatus(status);
      } catch (error) {
        // Silently fail - Salesforce may not be configured
        console.log('Salesforce status not available:', error.message);
      }
    };

    if (id) {
      fetchSalesforceStatus();
    }
  }, [id]);

  const handleSendApplication = async () => {
    if (!loan) return;
    try {
      setApplicationLoading(true);
      const response = await borrowerApplicationAPI.createForLead(loan.id, {
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

  const handleAction = async (action) => {
    const borrowerPhone = loan.borrower_phone || formData.borrower_phone;
    const _borrowerEmail = loan.borrower_email || formData.borrower_email; // eslint-disable-line no-unused-vars

    switch(action) {
      case 'call':
        if (!borrowerPhone) {
          toast.error('No phone number available for this borrower');
          return;
        }
        {
          const cleanPhone = borrowerPhone.replace(/[^\d+]/g, '');
          const dialNumber = cleanPhone.startsWith('+') ? cleanPhone : `+1${cleanPhone}`;
          window.open(`https://teams.microsoft.com/l/call/0/0?users=4:${encodeURIComponent(dialNumber)}`, '_blank');
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
        setShowVideoCall(true);
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
        // Open portal selector modal to choose between Client, Buyer's Agent, or Listing Agent portals
        setShowPortalSelector(true);
        break;
      case 'salesforce-pull':
        handleSalesforcePull();
        break;
      default:
        break;
    }
  };

  if (loading) {
    return (
      <div className="lead-detail-page">
        <div className="loading">Loading loan details...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="lead-detail-page">
        <div className="error-container" style={{ padding: '40px', textAlign: 'center' }}>
          <h2 style={{ color: '#ef4444', marginBottom: '16px' }}>Error Loading Loan</h2>
          <p style={{ color: '#6b7280', marginBottom: '24px' }}>{error}</p>
          <button
            onClick={() => navigate('/loans')}
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
            &larr; Back to Loans
          </button>
        </div>
      </div>
    );
  }

  if (!loan) {
    return (
      <div className="lead-detail-page">
        <div className="error">Loan not found</div>
      </div>
    );
  }

  const _currentBorrower = borrowers[activeBorrower] || borrowers[0] || { // eslint-disable-line no-unused-vars
    data: { name: '', email: '', phone: '' }
  };

  return (
    <div className="lead-detail-page-wrapper">
      <div className="lead-detail-page">
        {/* Header */}
        <div className="detail-header">
          <div className="nav-buttons">
            <button className="btn-back" onClick={() => navigate('/loans')}>
              ← Back to Loans
            </button>
          <button className="btn-next" onClick={handleViewNextLoan} disabled={loansList.length === 0}>
            View Next Loan →
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
        justifyContent: 'space-between'
      }}>
        <h2 style={{
          margin: 0,
          fontSize: '20px',
          fontWeight: '600',
          color: '#1a1a2e'
        }}>
          {formData.borrower_first_name || formData.borrower_last_name
            ? `${formData.borrower_first_name || ''} ${formData.borrower_last_name || ''}`.trim()
            : loan?.borrower_name || loan?.borrower || 'Unknown Borrower'}
        </h2>
        {/* Salesforce Connection Indicator */}
        <SalesforceConnectionBadge
          entityType="loan"
          entityId={id}
          salesforceId={loan?.salesforce_id}
          lastSyncedAt={loan?.salesforce_last_synced_at}
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
          className={`tab-btn ${activeTab === 'ai-activity' ? 'active' : ''}`}
          onClick={() => setActiveTab('ai-activity')}
        >
          AI Activity
        </button>
      </div>

      {/* Tab Content */}
      <div className="detail-content">
        {/* Left Column - Loan Information */}
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
                  value={formData.loan_number || loan?.loan_number || ''}
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
                  value={formData.loan_amount || formData.amount || ''}
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
                  value={formData.loan_term || formData.term || ''}
                  onChange={(e) => handleFieldChange('loan_term', e.target.value)}
                  placeholder="Months"
                />
              </div>

              <div className="info-field">
                <label>Loan Type</label>
                <select
                  value={formData.loan_type || formData.program || ''}
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
                  value={formData.lock_date ? formData.lock_date.split('T')[0] : ''}
                  onChange={(e) => handleFieldChange('lock_date', e.target.value)}
                />
              </div>

              <div className="info-field">
                <label>Lock Expiration</label>
                <input
                  type="date"
                  value={formData.lock_expiration ? formData.lock_expiration.split('T')[0] : ''}
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
                  value={formData.closing_date ? formData.closing_date.split('T')[0] : ''}
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
                  value={formData.borrower_first_name || (formData.borrower_name || '').split(' ')[0] || ''}
                  onChange={(e) => handleFieldChange('borrower_first_name', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>Last Name</label>
                <input
                  type="text"
                  value={formData.borrower_last_name || (formData.borrower_name || '').split(' ').slice(1).join(' ') || ''}
                  onChange={(e) => handleFieldChange('borrower_last_name', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>Email</label>
                <input
                  type="email"
                  value={formData.borrower_email || ''}
                  onChange={(e) => handleFieldChange('borrower_email', e.target.value)}
                />
              </div>
              <div className="info-field">
                <label>Phone</label>
                <input
                  type="tel"
                  value={formData.borrower_phone || ''}
                  onChange={(e) => handleFieldChange('borrower_phone', formatPhoneNumber(e.target.value))}
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
                entityType="loans"
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
                        <option value="other_relative">Other Relative</option>
                        <option value="employer">Employer</option>
                        <option value="friend">Friend</option>
                      </select>
                    </div>
                  </div>
                </div>
              </>
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
                      value={formData.property_address || formData.address || ''}
                      onChange={(e) => handleFieldChange('property_address', e.target.value)}
                    />
                  </div>
                  <div className="info-field">
                    <label>City</label>
                    <input
                      type="text"
                      value={formData.property_city || formData.city || ''}
                      onChange={(e) => handleFieldChange('property_city', e.target.value)}
                    />
                  </div>
                  <div className="info-field">
                    <label>State</label>
                    <input
                      type="text"
                      value={formData.property_state || formData.state || ''}
                      onChange={(e) => handleFieldChange('property_state', e.target.value)}
                    />
                  </div>
                  <div className="info-field">
                    <label>Zip Code</label>
                    <input
                      type="text"
                      value={formData.property_zip || formData.zip_code || ''}
                      onChange={(e) => handleFieldChange('property_zip', e.target.value)}
                    />
                  </div>
                  <div className="info-field">
                    <label>Property Type</label>
                    <select
                      value={formData.property_type || ''}
                      onChange={(e) => handleFieldChange('property_type', e.target.value)}
                      style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                    >
                      <option value="">Select Type</option>
                      <option value="Single Family">Single Family</option>
                      <option value="Condo">Condo</option>
                      <option value="Townhouse">Townhouse</option>
                      <option value="Multi-Family">Multi-Family</option>
                      <option value="Manufactured">Manufactured</option>
                      <option value="PUD">PUD</option>
                    </select>
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

                {/* Property Details Section - Salesforce Sync Fields */}
                <h3 style={{ margin: '2rem 0 1rem 0', fontSize: '16px', fontWeight: '600', color: '#333', borderTop: '1px solid #e0e0e0', paddingTop: '1.5rem' }}>
                  Property Details
                  <span style={{ fontSize: '12px', fontWeight: '400', color: '#666', marginLeft: '8px' }}>(Synced from Salesforce)</span>
                </h3>
                <div className="info-grid compact">
                  <div className="info-field">
                    <label>Occupancy Type</label>
                    <select
                      value={formData.occupancy_type || ''}
                      onChange={(e) => handleFieldChange('occupancy_type', e.target.value)}
                      style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                    >
                      <option value="">Select Occupancy</option>
                      <option value="Primary Residence">Primary Residence</option>
                      <option value="Second Home">Second Home</option>
                      <option value="Investment">Investment</option>
                    </select>
                  </div>
                  <div className="info-field">
                    <label>Property County</label>
                    <input
                      type="text"
                      value={formData.property_county || ''}
                      onChange={(e) => handleFieldChange('property_county', e.target.value)}
                    />
                  </div>
                  <div className="info-field">
                    <label>Ownership Type</label>
                    <select
                      value={formData.property_ownership_type || ''}
                      onChange={(e) => handleFieldChange('property_ownership_type', e.target.value)}
                      style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                    >
                      <option value="">Select Ownership</option>
                      <option value="Fee Simple">Fee Simple</option>
                      <option value="Leasehold">Leasehold</option>
                    </select>
                  </div>
                  <div className="info-field">
                    <label>Number of Units</label>
                    <input
                      type="number"
                      min="1"
                      max="4"
                      value={formData.property_units || ''}
                      onChange={(e) => handleFieldChange('property_units', parseInt(e.target.value))}
                    />
                  </div>
                  <div className="info-field">
                    <label>Appraised Value</label>
                    <CurrencyInput
                      value={formData.appraisal_value || ''}
                      onChange={(value) => handleFieldChange('appraisal_value', value)}
                      placeholder="$0"
                    />
                  </div>
                  <div className="info-field">
                    <label>Purchase Price</label>
                    <CurrencyInput
                      value={formData.purchase_price || ''}
                      onChange={(value) => handleFieldChange('purchase_price', value)}
                      placeholder="$0"
                    />
                  </div>
                </div>

                {/* LTV/CLTV Section */}
                <h3 style={{ margin: '2rem 0 1rem 0', fontSize: '16px', fontWeight: '600', color: '#333', borderTop: '1px solid #e0e0e0', paddingTop: '1.5rem' }}>
                  Loan Ratios
                </h3>
                <div className="info-grid compact">
                  <div className="info-field">
                    <label>LTV (%)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.ltv || ''}
                      onChange={(e) => handleFieldChange('ltv', parseFloat(e.target.value))}
                      placeholder="0.00"
                    />
                  </div>
                  <div className="info-field">
                    <label>CLTV (%)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.cltv || ''}
                      onChange={(e) => handleFieldChange('cltv', parseFloat(e.target.value))}
                      placeholder="0.00"
                    />
                  </div>
                  <div className="info-field">
                    <label>Loan Purpose</label>
                    <select
                      value={formData.loan_purpose || ''}
                      onChange={(e) => handleFieldChange('loan_purpose', e.target.value)}
                      style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                    >
                      <option value="">Select Purpose</option>
                      <option value="Purchase">Purchase</option>
                      <option value="Refinance">Refinance</option>
                      <option value="Cash-Out Refinance">Cash-Out Refinance</option>
                      <option value="Construction">Construction</option>
                      <option value="Home Equity">Home Equity</option>
                    </select>
                  </div>
                  <div className="info-field">
                    <label>File State</label>
                    <input
                      type="text"
                      value={formData.file_state || ''}
                      onChange={(e) => handleFieldChange('file_state', e.target.value)}
                      readOnly
                      style={{ backgroundColor: '#f5f5f5' }}
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
                      <AddressAutocomplete
                        value={formData.homeowner_insurance_company || ''}
                        onChange={(value) => handleFieldChange('homeowner_insurance_company', value)}
                        onAddressSelect={(place) => {
                          handleFieldChange('homeowner_insurance_company', place.formatted || place.name || '');
                        }}
                        placeholder="Company name"
                        types={['establishment']}
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
                        <AddressAutocomplete
                          value={formData.flood_insurance_company || ''}
                          onChange={(value) => handleFieldChange('flood_insurance_company', value)}
                          onAddressSelect={(place) => {
                            handleFieldChange('flood_insurance_company', place.formatted || place.name || '');
                          }}
                          placeholder="Company name"
                          types={['establishment']}
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
                      <AddressAutocomplete
                        value={formData.closing_address || ''}
                        onChange={(value) => handleFieldChange('closing_address', value)}
                        onAddressSelect={(addressData) => {
                          // Auto-fill address components
                          handleFieldChange('closing_address', addressData.street || addressData.formatted || '');
                          if (addressData.city) handleFieldChange('closing_city', addressData.city);
                          if (addressData.state_code) handleFieldChange('closing_state', addressData.state_code);
                          if (addressData.zip) handleFieldChange('closing_zip', addressData.zip);
                        }}
                        placeholder="Street address"
                        types={['address']}
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
            <h2>TEAM MEMBERS</h2>

            {/* Workflow Role Assignments */}
            <div style={{ marginBottom: '24px' }}>
              <WorkflowRoleAssignment
                onUpdate={() => {
                  // Optionally refresh data when assignments change
                }}
              />
            </div>

            <div className="team-members-display">
              <h4 style={{ marginBottom: '15px', color: '#333' }}>Transaction Partners</h4>

              {/* Standard/Internal Team Members */}
              {standardMembers.map((member, index) => {
                const colors = ['#2563eb', '#059669', '#7c3aed', '#dc2626', '#f59e0b'];
                const bgColor = colors[index % colors.length];
                return (
                  <div key={member.id} className="team-member-card" style={{
                    display: 'flex',
                    alignItems: 'center',
                    padding: '12px 16px',
                    backgroundColor: '#f8f9fa',
                    borderRadius: '8px',
                    marginBottom: '10px'
                  }}>
                    <div style={{
                      width: '40px',
                      height: '40px',
                      borderRadius: '50%',
                      backgroundColor: bgColor,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'white',
                      fontWeight: 'bold',
                      marginRight: '12px',
                      flexShrink: 0
                    }}>
                      {member.name?.charAt(0)?.toUpperCase() || '?'}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: '600', color: '#333' }}>{member.name}</div>
                      <div style={{ fontSize: '12px', color: '#666' }}>{member.role}</div>
                      {member.email && <div style={{ fontSize: '12px', color: '#2563eb' }}>{member.email}</div>}
                    </div>
                    <span style={{ fontSize: '10px', backgroundColor: '#e5e7eb', padding: '2px 8px', borderRadius: '4px', color: '#666' }}>
                      Employee
                    </span>
                  </div>
                );
              })}

              {/* Custom Team Members (Transaction Partners) */}
              {teamMembers.map((member) => (
                <div key={member.id} className="team-member-card" style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '12px 16px',
                  backgroundColor: '#f8f9fa',
                  borderRadius: '8px',
                  marginBottom: '10px'
                }}>
                  <div style={{
                    width: '40px',
                    height: '40px',
                    borderRadius: '50%',
                    backgroundColor: member.is_employee ? '#3b82f6' : '#f59e0b',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'white',
                    fontWeight: 'bold',
                    marginRight: '12px',
                    flexShrink: 0
                  }}>
                    {member.name?.charAt(0)?.toUpperCase() || '?'}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontWeight: '600', color: '#333' }}>{member.name}</span>
                      {member.is_new && (
                        <span style={{
                          fontSize: '10px',
                          backgroundColor: '#10b981',
                          color: 'white',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontWeight: '600'
                        }}>NEW</span>
                      )}
                    </div>
                    <div style={{ fontSize: '12px', color: '#666' }}>{member.role}</div>
                    {member.company && <div style={{ fontSize: '11px', color: '#888' }}>{member.company}</div>}
                    {member.email && <div style={{ fontSize: '12px', color: '#2563eb' }}>{member.email}</div>}
                    {member.phone && <div style={{ fontSize: '12px', color: '#666' }}>{member.phone}</div>}
                  </div>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    {!member.is_employee && member.referral_partner_id && (
                      <span style={{ fontSize: '10px', backgroundColor: '#fef3c7', padding: '2px 8px', borderRadius: '4px', color: '#92400e' }}>
                        Partner
                      </span>
                    )}
                    <button
                      onClick={() => handleEditTeamMember(member)}
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        fontSize: '16px',
                        padding: '4px',
                        color: '#6b7280'
                      }}
                      title="Edit"
                    >
                      ✎
                    </button>
                    <button
                      onClick={() => handleDeleteTeamMember(member.id)}
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        fontSize: '16px',
                        padding: '4px',
                        color: '#ef4444'
                      }}
                      title="Remove"
                    >
                      ×
                    </button>
                  </div>
                </div>
              ))}

              {/* Show message if no team members */}
              {standardMembers.length === 0 && teamMembers.length === 0 && (
                <div style={{
                  padding: '20px',
                  backgroundColor: '#f8f9fa',
                  borderRadius: '8px',
                  textAlign: 'center',
                  color: '#666'
                }}>
                  No team members assigned yet
                </div>
              )}

              {/* Add Team Member Button */}
              <button
                onClick={handleAddTeamMember}
                style={{
                  marginTop: '15px',
                  padding: '10px 20px',
                  backgroundColor: 'white',
                  border: '1px dashed #d1d5db',
                  borderRadius: '8px',
                  color: '#666',
                  cursor: 'pointer',
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px'
                }}
              >
                <span style={{ fontSize: '18px' }}>+</span>
                <span>Add Team Member</span>
              </button>
            </div>
          </div>
        )}

        {/* Marketing Tab */}
        {activeTab === 'marketing' && (
          <div className="info-section">
            <h2>Marketing</h2>
            <div className="marketing-content">
              <p className="section-description" style={{ color: '#666', marginBottom: '20px' }}>
                View and manage marketing campaigns, drip sequences, and promotional content for this borrower.
              </p>

              <div className="marketing-campaigns" style={{ marginBottom: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 style={{ margin: 0 }}>Active Campaigns</h3>
                  <button className="btn-primary" style={{ padding: '8px 16px', fontSize: '14px' }}>
                    + Add to Campaign
                  </button>
                </div>
                <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px', textAlign: 'center', color: '#666' }}>
                  No active campaigns. Add this borrower to a marketing campaign to start automated outreach.
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
                  View all email communications with this borrower.
                </p>
                <button
                  className="btn-primary"
                  style={{ padding: '8px 16px', fontSize: '14px' }}
                  onClick={() => (loan?.borrower_email || formData?.borrower_email) && window.open(`mailto:${loan?.borrower_email || formData?.borrower_email}`, '_blank')}
                  disabled={!loan?.borrower_email && !formData?.borrower_email}
                >
                  + Compose Email
                </button>
              </div>

              {/* Email History */}
              <div className="email-history-section">
                <h3>Email History</h3>
                <div className="email-list">
                  {emailHistory.length > 0 ? (
                    emailHistory.map((email) => (
                      <div key={email.id} className="email-item">
                        <div className="email-header">
                          <span className="email-subject">
                            {email.subject || 'No subject'}
                          </span>
                          <span className="email-date">
                            {new Date(email.sentAt).toLocaleDateString()}
                          </span>
                        </div>
                        <div className="email-preview">
                          {(email.body || '').substring(0, 100)}...
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
                    <p>Emails associated with this loan will appear here.</p>
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
                    <p>SMS conversations with this borrower will appear here.</p>
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
                    <p>Call recordings with this borrower will appear here.</p>
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
                        No referral opportunities detected.
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
                            {contact.loanId ? (
                              <span
                                onClick={() => navigate(`/loans/${contact.loanId}`)}
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
                          onChange={e => {
                            const newType = e.target.value;
                            setCircleForm({...circleForm, type: newType});
                            // Re-search if name is entered and type changed
                            if (circleForm.name.length >= 2) {
                              setSearchResults([]);
                              searchContacts(circleForm.name, newType);
                            }
                          }}
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
                                <div style={{ fontWeight: '500' }}>{result.borrower_name || result.name}</div>
                                {result.company && <div style={{ fontSize: '12px', color: '#888' }}>{result.company}</div>}
                                <div style={{ fontSize: '12px', color: '#666' }}>
                                  {(result.borrower_email || result.email) && <span>{result.borrower_email || result.email}</span>}
                                  {(result.borrower_email || result.email) && (result.borrower_phone || result.phone) && <span> • </span>}
                                  {(result.borrower_phone || result.phone) && <span>{result.borrower_phone || result.phone}</span>}
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
            <LoanSmartDocsTab
              loanId={parseInt(id)}
              borrowerId={loan?.borrower_id}
              borrowerName={loan?.borrower_name || ''}
              borrowerEmail={loan?.borrower_email || formData?.borrower_email || ''}
              coBorrowerName={loan?.coborrower_name || ''}
              coBorrowerEmail={loan?.coborrower_email || formData?.coborrower_email || ''}
            />
          </div>
        )}

        {/* Credit Tab */}
        {activeTab === 'credit' && (
          <div className="info-section">
            <CreditTab
              leadId={loan?.lead_id}
              loanId={parseInt(id)}
              borrowerId={loan?.borrower_id}
              formData={formData}
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
                loanId={parseInt(id)}
                borrowerId={borrowers[activeBorrower]?.id || 1}
                onIncomeCalculated={(result) => {
                  console.log('Unified income calculated:', result);
                  toast.success(`Monthly income: $${result.monthly_income?.toLocaleString() || 0}`);
                }}
              />
            ) : (
              <IncomeCalculator
                loanId={parseInt(id)}
                borrowerId={borrowers[activeBorrower]?.id || 1}
                onIncomeCalculated={(result) => {
                  console.log('Income calculated:', result);
                }}
              />
            )}
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

        {/* Important Dates Tab */}
        {activeTab === 'important-dates' && (
          <div className="tab-content sla-dates-tab">
            {/* Custom Byte Mapping SLA Dates — synced from Salesforce */}

            {/* Lead & Application Phase */}
            <div className="dates-section">
              <h3 className="dates-section-title">Lead & Application Phase</h3>
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
            <div className="dates-section">
              <h3 className="dates-section-title">Lock Phase</h3>
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
            <div className="dates-section">
              <h3 className="dates-section-title">Processing & Underwriting</h3>
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
            <div className="dates-section">
              <h3 className="dates-section-title">Appraisal</h3>
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
                  <label>Appraisal Scheduled Date</label>
                  <input type="date" value={formData.appraisal_scheduled_date || ''} onChange={(e) => handleFieldChange('appraisal_scheduled_date', e.target.value)} />
                </div>
                <div className="date-field">
                  <label>Appraisal Completed Date</label>
                  <input type="date" value={formData.appraisal_completed_date || ''} onChange={(e) => handleFieldChange('appraisal_completed_date', e.target.value)} />
                </div>
                <div className="date-field">
                  <label>Appraisal Docs Expire Date</label>
                  <input type="date" value={formData.appraisal_docs_expire_date || ''} onChange={(e) => handleFieldChange('appraisal_docs_expire_date', e.target.value)} />
                </div>
              </div>
            </div>

            {/* Title & Insurance Phase */}
            <div className="dates-section">
              <h3 className="dates-section-title">Title & Insurance</h3>
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
            <div className="dates-section">
              <h3 className="dates-section-title">Closing Disclosure</h3>
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
            <div className="dates-section">
              <h3 className="dates-section-title">Clear to Close & Docs</h3>
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

            {/* Funding & Closing Phase */}
            <div className="dates-section">
              <h3 className="dates-section-title">Funding & Closing</h3>
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
            <div className="dates-section">
              <h3 className="dates-section-title">Post-Closing & Status</h3>
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

        {/* AI Activity Tab */}
        {activeTab === 'ai-activity' && (
          <div className="info-section">
            <AIActivityTab
              loanId={loan?.id?.toString()}
              borrowerName={loan?.borrower_name || loan?.borrower}
              loanNumber={loan?.loan_number}
              loanAmount={loan?.loan_amount}
              loanStatus={loan?.stage}
              onClickToDial={() => handleAction('call')}
            />
          </div>
        )}

        </div>
      </div>

      {/* Voicemail Drop */}
      {loan && showVoicemailDrop && (
        <VoicemailDrop
          phoneNumber={loan.borrower_phone}
          recipientName={loan.borrower_name || loan.borrower}
          onClose={() => setShowVoicemailDrop(false)}
        />
      )}

      {/* SMS Modal */}
      {loan && showSMSModal && (
        <SMSModal
          phoneNumber={loan.borrower_phone || formData.borrower_phone}
          recipientName={loan.borrower_name || loan.borrower}
          onClose={() => setShowSMSModal(false)}
        />
      )}

      {/* Teams Modal */}
      {loan && showTeamsModal && (
        <TeamsModal
          recipientEmail={loan.borrower_email || formData.borrower_email}
          recipientName={loan.borrower_name || loan.borrower}
          onClose={() => setShowTeamsModal(false)}
        />
      )}

      {/* Recording Modal */}
      {loan && showRecordingModal && (
        <RecordingModal
          meetingTitle={`Loan Discussion - ${loan.borrower_name || loan.borrower}`}
          onClose={() => setShowRecordingModal(false)}
        />
      )}

      {/* Create Task Modal */}
      {loan && (
        <CreateTaskModal
          isOpen={showTaskModal}
          onClose={() => setShowTaskModal(false)}
          lead={{ id: loan.id, name: loan.borrower_name || loan.borrower, loan_number: loan.loan_number }}
        />
      )}

      {/* Appointment Modal (legacy) */}
      {loan && (
        <AppointmentModal
          isOpen={showAppointmentModal}
          onClose={() => setShowAppointmentModal(false)}
          lead={{ id: loan.id, name: loan.borrower_name || loan.borrower, phone: loan.borrower_phone, email: loan.borrower_email }}
        />
      )}

      {/* Schedule Appointment Modal (Redfin-style) */}
      {loan && (
        <ScheduleAppointmentModal
          isOpen={showScheduleModal}
          onClose={() => setShowScheduleModal(false)}
          onSuccess={() => setCalendarRefreshKey(prev => prev + 1)}
          borrower={{ id: loan.id, name: loan.borrower_name || loan.borrower, phone: loan.borrower_phone, email: loan.borrower_email }}
        />
      )}

      {/* Escalation Modal */}
      {loan && (
        <EscalationModal
          isOpen={showEscalationModal}
          onClose={() => setShowEscalationModal(false)}
          lead={{ id: loan.id, name: loan.borrower_name || loan.borrower, loan_number: loan.loan_number }}
        />
      )}

      {/* Portal Selector Modal */}
      {loan && (
        <PortalSelectorModal
          isOpen={showPortalSelector}
          onClose={() => setShowPortalSelector(false)}
          loan={loan}
        />
      )}

      {/* UVIP Video Call Schedule Modal */}
      <VideoCallScheduleModal
        isOpen={showVideoCall}
        onClose={() => setShowVideoCall(false)}
        borrower={{
          id: loan?.id,
          name: loan?.borrower_name || loan?.borrower,
          email: loan?.borrower_email || formData.borrower_email,
          phone: loan?.borrower_phone || formData.borrower_phone
        }}
        onStartVideoCall={(data) => {
          console.log('Video call started:', data);
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

      {/* Team Member Add/Edit Modal */}
      {showTeamMemberModal && (
        <div className="modal-overlay" onClick={() => setShowTeamMemberModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '500px' }}>
            <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ margin: 0 }}>{editingTeamMember ? 'Edit Team Member' : 'Add Team Member'}</h2>
              <button onClick={() => setShowTeamMemberModal(false)} style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: '#666' }}>×</button>
            </div>

            <div className="form-group" style={{ marginBottom: '16px', position: 'relative' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Name *</label>
              <input
                type="text"
                value={teamMemberForm.name}
                onChange={handleTeamMemberNameChange}
                onFocus={() => teamMemberForm.name.length >= 2 && setShowTeamMemberSearchResults(true)}
                placeholder="Start typing to search partners..."
                autoComplete="off"
                style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
              />
              {teamMemberSearchLoading && (
                <div style={{ position: 'absolute', right: '10px', top: '35px', color: '#999', fontSize: '12px' }}>
                  Searching...
                </div>
              )}
              {showTeamMemberSearchResults && teamMemberSearchResults.length > 0 && (
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
                  {teamMemberSearchResults.map(result => (
                    <div
                      key={result.id}
                      onClick={() => selectTeamMemberSearchResult(result)}
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
                      {result.company && <div style={{ fontSize: '12px', color: '#888' }}>{result.company}</div>}
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

            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Role *</label>
              <select
                value={teamMemberForm.role}
                onChange={(e) => setTeamMemberForm({ ...teamMemberForm, role: e.target.value })}
                style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
              >
                <option value="">Select a role...</option>
                {teamMemberRoles.map(role => (
                  <option key={role} value={role}>{role}</option>
                ))}
              </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
              <div className="form-group">
                <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Email</label>
                <input
                  type="email"
                  value={teamMemberForm.email}
                  onChange={(e) => setTeamMemberForm({ ...teamMemberForm, email: e.target.value })}
                  placeholder="email@example.com"
                  style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                />
              </div>
              <div className="form-group">
                <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Phone</label>
                <input
                  type="tel"
                  value={teamMemberForm.phone}
                  onChange={(e) => setTeamMemberForm({ ...teamMemberForm, phone: formatPhoneNumber(e.target.value) })}
                  placeholder="(555) 123-4567"
                  style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                />
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Company</label>
              <input
                type="text"
                value={teamMemberForm.company}
                onChange={(e) => setTeamMemberForm({ ...teamMemberForm, company: e.target.value })}
                placeholder="Company or brokerage name"
                style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
              />
            </div>

            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>License Number</label>
              <input
                type="text"
                value={teamMemberForm.license_number}
                onChange={(e) => setTeamMemberForm({ ...teamMemberForm, license_number: e.target.value })}
                placeholder="License or NMLS number"
                style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
              />
            </div>

            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Notes</label>
              <textarea
                value={teamMemberForm.notes}
                onChange={(e) => setTeamMemberForm({ ...teamMemberForm, notes: e.target.value })}
                placeholder="Additional notes..."
                rows={3}
                style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px', resize: 'vertical' }}
              />
            </div>

            <div className="form-group" style={{ marginBottom: '20px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={teamMemberForm.is_employee}
                  onChange={(e) => setTeamMemberForm({ ...teamMemberForm, is_employee: e.target.checked })}
                />
                <span>This is an internal employee</span>
              </label>
              {!teamMemberForm.is_employee && (
                <p style={{ fontSize: '12px', color: '#666', marginTop: '8px', marginLeft: '24px' }}>
                  External team members will be saved as referral partners.
                </p>
              )}
            </div>

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setShowTeamMemberModal(false)}
                style={{
                  padding: '10px 20px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  background: 'white',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveTeamMember}
                disabled={teamMemberLoading}
                style={{
                  padding: '10px 20px',
                  border: 'none',
                  borderRadius: '6px',
                  background: '#2563eb',
                  color: 'white',
                  cursor: teamMemberLoading ? 'not-allowed' : 'pointer',
                  opacity: teamMemberLoading ? 0.7 : 1
                }}
              >
                {teamMemberLoading ? 'Saving...' : (editingTeamMember ? 'Update' : 'Add Team Member')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Email Composer Modal */}
      <EmailComposerModal
        isOpen={showEmailComposer}
        onClose={() => setShowEmailComposer(false)}
        recipient={{
          name: loan?.borrower_name || loan?.borrower,
          email: loan?.borrower_email || formData.borrower_email
        }}
        entityType="loan"
        entityData={{
          id: loan?.id,
          amount: loan?.amount,
          property_address: loan?.property_address,
          stage: loan?.stage,
          closing_date: loan?.closing_date
        }}
      />

      {/* Send Video Message Modal */}
      {loan && clientPortalWorkspaceId && (
        <SendVideoModal
          isOpen={showSendVideoModal}
          onClose={() => setShowSendVideoModal(false)}
          recipientType="client"
          recipientId={clientPortalWorkspaceId}
          recipientName={loan?.borrower_name || loan?.borrower || 'Client'}
          onSuccess={() => {
            console.log('Video sent successfully');
          }}
        />
      )}
      </div>

      {/* Fixed Sidebar */}
      <CalendarSidebar loanId={id} key={calendarRefreshKey}>
      {/* Quick Actions */}
      <div className="actions-card">
        <h3>QUICK ACTIONS</h3>
        <div className="action-buttons">
          <button className="action-btn call" onClick={() => handleAction('call')} title="Click to call">
            <span>Call</span>
          </button>
          <button className="action-btn sms" onClick={() => handleAction('sms')} title="Send SMS">
            <span>SMS Text</span>
          </button>
          <button className="action-btn email" onClick={() => handleAction('email')} title="Send email">
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
          <button className="action-btn voicemail" onClick={() => handleAction('voicemail')} title="Drop voicemail">
            <span>Voicemail Drop</span>
          </button>
          <button className="action-btn record-video" onClick={() => setShowSendVideoModal(true)} disabled={!clientPortalWorkspaceId} title={clientPortalWorkspaceId ? "Record and send a video message" : "No client portal available"}>
            <span>Record Video</span>
          </button>
          <button className="action-btn application" onClick={() => handleAction('send_application')} disabled={applicationLoading} title="Send application link">
            <span>{applicationLoading ? 'Creating...' : 'Send Application'}</span>
          </button>
          <button className="action-btn portal" onClick={() => handleAction('client_portal')} title="Access portals">
            <span>Portals</span>
          </button>
          <button className="action-btn escalation" onClick={() => handleAction('escalation')} title="Escalate issue">
            <span>Escalation</span>
          </button>
          {salesforceStatus?.is_linked && (
            <button
              className={`action-btn salesforce-pull ${salesforcePulling ? 'loading' : ''}`}
              onClick={() => handleAction('salesforce-pull')}
              title={`Sync from Salesforce (${salesforceStatus.salesforce_id})`}
              disabled={salesforcePulling}
            >
              <span>{salesforcePulling ? 'Syncing...' : 'Sync from SF'}</span>
            </button>
          )}
        </div>
      </div>
    </CalendarSidebar>
      {loan && (loan.borrower_phone || formData.borrower_phone) && (
        <SMSAccordionPanel
          contactId={loan.id}
          contactName={loan.borrower_name || loan.borrower || formData.borrower_name}
          phone={loan.borrower_phone || formData.borrower_phone}
          pageType="client"
          assignedUser={loan.loan_officer_id}
          borrowers={borrowers.filter(b => b.data?.phone).map(b => ({
            id: b.id,
            name: b.name,
            phone: b.data.phone,
            type: b.type,
          }))}
        />
      )}
    </div>
  );
}

export default LoanDetail;
