import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { loansAPI, activitiesAPI, circleOfCashflowAPI } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import VoicemailDrop from '../components/VoicemailDrop';
import VoicemailModal from '../components/VoicemailModal';
import SMSModal from '../components/SMSModal';
import TeamsModal from '../components/TeamsModal';
import RecordingModal from '../components/RecordingModal';
import CreateTaskModal from '../components/CreateTaskModal';
import AppointmentModal from '../components/AppointmentModal';
import ScheduleAppointmentModal from '../components/ScheduleAppointmentModal';
import EscalationModal from '../components/EscalationModal';
import TeamAssignment from '../components/TeamAssignment';
import EmploymentTab from '../components/EmploymentTab';
import RateLockRecommendation from '../components/RateLockRecommendation';
import VideoMeetings from '../components/VideoMeetings';
import EmailComposerModal from '../components/EmailComposerModal';
import CalendarSidebar from '../components/CalendarSidebar';
import './LeadDetail.css';

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
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
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
  const [showVideoMeetings, setShowVideoMeetings] = useState(false);
  const [showEmailComposer, setShowEmailComposer] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [emailHistory, setEmailHistory] = useState([]);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [noteText, setNoteText] = useState('');
  const [noteLoading, setNoteLoading] = useState(false);

  // Archive state
  const [archiveSubTab, setArchiveSubTab] = useState('notes'); // 'notes', 'email', 'sms', 'calls'
  const [emailArchive, setEmailArchive] = useState([]);
  const [smsArchive, setSmsArchive] = useState([]);
  const [callArchive, setCallArchive] = useState([]);
  const [archiveLoading, setArchiveLoading] = useState(false);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

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
  const searchContacts = async (query) => {
    if (query.length < 2) {
      setSearchResults([]);
      setShowSearchResults(false);
      return;
    }
    setSearchLoading(true);
    try {
      const response = await loansAPI.search(query);
      setSearchResults(response.loans || []);
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
      alert('Failed to add note');
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
          alert('Loan not found');
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
          }
        });
      }

      setBorrowers(borrowersList);
    } catch (error) {
      console.error('Failed to load loan data:', error);
      alert('Failed to load loan details');
      navigate('/loans');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      await loansAPI.update(id, formData);
      setLoan(formData);
      setEditing(false);
      alert('Loan updated successfully!');
    } catch (error) {
      console.error('Failed to save loan:', error);
      alert('Failed to save changes');
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

  // ==================== TEAM MEMBER FUNCTIONS ====================
  const loadTeamMembers = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${process.env.REACT_APP_API_URL || 'https://mortgage-crm-production-7a9a.up.railway.app'}/api/v1/loans/${id}/team-members`, {
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
      alert('Please enter a name and role');
      return;
    }

    setTeamMemberLoading(true);
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_API_URL || 'https://mortgage-crm-production-7a9a.up.railway.app';

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
          alert('Failed to update team member');
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
            alert(`${teamMemberForm.name} has been added and saved as a referral partner.`);
          }
        } else {
          alert('Failed to add team member');
        }
      }
    } catch (error) {
      console.error('Error saving team member:', error);
      alert('Error saving team member');
    } finally {
      setTeamMemberLoading(false);
    }
  };

  const handleDeleteTeamMember = async (memberId) => {
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_API_URL || 'https://mortgage-crm-production-7a9a.up.railway.app';

      const response = await fetch(`${apiUrl}/api/v1/loans/${id}/team-members/${memberId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        await loadTeamMembers();
      } else {
        alert('Failed to remove team member');
      }
    } catch (error) {
      console.error('Error deleting team member:', error);
      alert('Error removing team member');
    }
  };

  // Load team members when loan loads
  useEffect(() => {
    if (id) {
      loadTeamMembers();
    }
  }, [id]);

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
      console.log('Voice command received:', transcript);

      // Send the transcript to the SmartAI chat
      window.dispatchEvent(new CustomEvent('voiceCommand', {
        detail: { transcript, loanId: loan.id }
      }));
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
      alert(`Voice recognition error: ${event.error}`);
    };

    recognition.onend = () => {
      setIsListening(false);
      console.log('Voice recognition ended.');
    };

    recognition.start();
  };

  const handleAction = async (action) => {
    const borrowerPhone = loan.borrower_phone || formData.borrower_phone;
    const borrowerEmail = loan.borrower_email || formData.borrower_email;

    switch(action) {
      case 'call':
        window.open(`tel:${borrowerPhone}`, '_self');
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
        // For active loans, open the existing application or create new
        if (loan.borrower_email) {
          const appUrl = `${window.location.origin}/apply/purchase`;
          window.open(appUrl, '_blank');
        } else {
          alert('Borrower email is required to send application');
        }
        break;
      case 'client_portal':
        // Open client portal for this loan
        if (loan.workspace_slug) {
          window.open(`${window.location.origin}/portal/${loan.workspace_slug}`, '_blank');
        } else {
          alert('No client portal found for this loan. Please create one from the loan details.');
        }
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

  if (!loan) {
    return (
      <div className="lead-detail-page">
        <div className="error">Loan not found</div>
      </div>
    );
  }

  const currentBorrower = borrowers[activeBorrower] || borrowers[0] || {
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

        {/* Rate Lock Recommendation - Inline in header */}
        <div className="header-rate-lock">
          <RateLockRecommendation loan={loan} compact={true} />
        </div>

        <div className="header-actions">
          {loan?.borrower_phone && (
            <button
              className="btn-voicemail-drop"
              onClick={() => setShowVoicemailDrop(true)}
              title="Drop voicemail to borrower"
            >
              📞 Voicemail Drop
            </button>
          )}
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
        <button
          className="borrower-btn add-borrower-btn"
          onClick={() => {
            const newBorrower = {
              id: Date.now(),
              name: 'New Borrower',
              type: 'co_borrower',
              email: '',
              phone: ''
            };
            setBorrowers([...borrowers, newBorrower]);
            setActiveBorrower(borrowers.length);
          }}
        >
          + Add Borrower
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
                  value={formData.loan_amount || formData.amount || ''}
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
                  onChange={(e) => handleFieldChange('borrower_phone', e.target.value)}
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

        {/* Property Tab */}
        {activeTab === 'loan' && (
          <div className="info-section">
            <h2>Loan Information</h2>
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
            <h2>TEAM MEMBERS</h2>
            <div className="team-members-display">
              <h4 style={{ marginBottom: '15px', color: '#333' }}>Team Members on File</h4>

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
                                <div style={{ fontWeight: '500' }}>{result.borrower_name || result.name}</div>
                                <div style={{ fontSize: '12px', color: '#666' }}>
                                  {result.borrower_email && <span>{result.borrower_email}</span>}
                                  {result.borrower_email && result.borrower_phone && <span> • </span>}
                                  {result.borrower_phone && <span>{result.borrower_phone}</span>}
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
            <h2>Contract-to-Close Milestone Dates</h2>
            <p className="section-subtitle">Track key milestone dates to manage the file, chase conditions, and prevent last-minute emergencies</p>

            {/* Contract & Property Dates */}
            <div className="dates-section">
              <h3 className="dates-section-title">Contract & Property Dates</h3>
              <div className="dates-grid">
                <div className="date-field">
                  <label>Contract Received Date</label>
                  <input
                    type="date"
                    value={formData.contract_received_date || ''}
                    onChange={(e) => handleFieldChange('contract_received_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Appraisal Ordered Date</label>
                  <input
                    type="date"
                    value={formData.appraisal_ordered_date || ''}
                    onChange={(e) => handleFieldChange('appraisal_ordered_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Appraisal Scheduled Date</label>
                  <input
                    type="date"
                    value={formData.appraisal_scheduled_date || ''}
                    onChange={(e) => handleFieldChange('appraisal_scheduled_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Appraisal Completed Date</label>
                  <input
                    type="date"
                    value={formData.appraisal_completed_date || ''}
                    onChange={(e) => handleFieldChange('appraisal_completed_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Appraisal Received Date</label>
                  <input
                    type="date"
                    value={formData.appraisal_received_date || ''}
                    onChange={(e) => handleFieldChange('appraisal_received_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Title Ordered Date</label>
                  <input
                    type="date"
                    value={formData.title_ordered_date || ''}
                    onChange={(e) => handleFieldChange('title_ordered_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Title Received Date</label>
                  <input
                    type="date"
                    value={formData.title_received_date || ''}
                    onChange={(e) => handleFieldChange('title_received_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Insurance Ordered Date</label>
                  <input
                    type="date"
                    value={formData.insurance_ordered_date || ''}
                    onChange={(e) => handleFieldChange('insurance_ordered_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Insurance Received Date</label>
                  <input
                    type="date"
                    value={formData.insurance_received_date || ''}
                    onChange={(e) => handleFieldChange('insurance_received_date', e.target.value)}
                  />
                </div>
              </div>
            </div>

            {/* Loan Processing Milestones */}
            <div className="dates-section">
              <h3 className="dates-section-title">Loan Processing Milestones</h3>
              <div className="dates-grid">
                <div className="date-field">
                  <label>Initial Disclosures Sent Date</label>
                  <input
                    type="date"
                    value={formData.initial_disclosures_sent_date || ''}
                    onChange={(e) => handleFieldChange('initial_disclosures_sent_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Initial Disclosures Signed Date</label>
                  <input
                    type="date"
                    value={formData.initial_disclosures_signed_date || ''}
                    onChange={(e) => handleFieldChange('initial_disclosures_signed_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Processor Submission Date</label>
                  <input
                    type="date"
                    value={formData.processor_submission_date || ''}
                    onChange={(e) => handleFieldChange('processor_submission_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Underwriting Submission Date</label>
                  <input
                    type="date"
                    value={formData.underwriting_submission_date || ''}
                    onChange={(e) => handleFieldChange('underwriting_submission_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Conditional Approval Date</label>
                  <input
                    type="date"
                    value={formData.conditional_approval_date || ''}
                    onChange={(e) => handleFieldChange('conditional_approval_date', e.target.value)}
                  />
                  <small className="field-hint">UW Decision Date</small>
                </div>

                <div className="date-field">
                  <label>Conditions Sent to Borrower</label>
                  <input
                    type="date"
                    value={formData.conditions_sent_date || ''}
                    onChange={(e) => handleFieldChange('conditions_sent_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Conditions Received from Borrower</label>
                  <input
                    type="date"
                    value={formData.conditions_received_date || ''}
                    onChange={(e) => handleFieldChange('conditions_received_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Resubmission to Underwriting Date</label>
                  <input
                    type="date"
                    value={formData.resubmission_date || ''}
                    onChange={(e) => handleFieldChange('resubmission_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Final Approval / Clear-to-Close Date</label>
                  <input
                    type="date"
                    value={formData.clear_to_close_date || ''}
                    onChange={(e) => handleFieldChange('clear_to_close_date', e.target.value)}
                  />
                </div>
              </div>
            </div>

            {/* Rate Lock Dates */}
            <div className="dates-section">
              <h3 className="dates-section-title">Rate Lock Dates</h3>
              <div className="dates-grid">
                <div className="date-field">
                  <label>Rate Lock Date</label>
                  <input
                    type="date"
                    value={formData.rate_lock_date || ''}
                    onChange={(e) => handleFieldChange('rate_lock_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Rate Lock Expiration Date</label>
                  <input
                    type="date"
                    value={formData.rate_lock_expiration_date || ''}
                    onChange={(e) => handleFieldChange('rate_lock_expiration_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Rate Lock Extension Date</label>
                  <input
                    type="date"
                    value={formData.rate_lock_extension_date || ''}
                    onChange={(e) => handleFieldChange('rate_lock_extension_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Float-down Trigger Date</label>
                  <input
                    type="date"
                    value={formData.float_down_trigger_date || ''}
                    onChange={(e) => handleFieldChange('float_down_trigger_date', e.target.value)}
                  />
                  <small className="field-hint">If applicable</small>
                </div>
              </div>
            </div>

            {/* Closing Process Dates */}
            <div className="dates-section">
              <h3 className="dates-section-title">Closing Process Dates</h3>
              <div className="dates-grid">
                <div className="date-field">
                  <label>Closing Disclosure Sent Date</label>
                  <input
                    type="date"
                    value={formData.closing_disclosure_sent_date || ''}
                    onChange={(e) => handleFieldChange('closing_disclosure_sent_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>CD Received/Signed Date</label>
                  <input
                    type="date"
                    value={formData.cd_received_signed_date || ''}
                    onChange={(e) => handleFieldChange('cd_received_signed_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>CD Delivered Date</label>
                  <input
                    type="date"
                    value={formData.cd_delivered_date || ''}
                    onChange={(e) => handleFieldChange('cd_delivered_date', e.target.value)}
                  />
                  <small className="field-hint">3-day timing rule</small>
                </div>

                <div className="date-field">
                  <label>Final CD Issue Date</label>
                  <input
                    type="date"
                    value={formData.final_cd_issue_date || ''}
                    onChange={(e) => handleFieldChange('final_cd_issue_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Final Closing Package Sent Date</label>
                  <input
                    type="date"
                    value={formData.final_closing_package_sent_date || ''}
                    onChange={(e) => handleFieldChange('final_closing_package_sent_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Closing Scheduled Date</label>
                  <input
                    type="date"
                    value={formData.closing_scheduled_date || ''}
                    onChange={(e) => handleFieldChange('closing_scheduled_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Funding Date</label>
                  <input
                    type="date"
                    value={formData.funding_date || ''}
                    onChange={(e) => handleFieldChange('funding_date', e.target.value)}
                  />
                </div>
              </div>
            </div>
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

      {/* UVIP Video Meetings Modal */}
      {showVideoMeetings && (
        <div className="modal-overlay" onClick={() => setShowVideoMeetings(false)}>
          <div className="modal-content video-meetings-modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close-btn" onClick={() => setShowVideoMeetings(false)}>×</button>
            <VideoMeetings
              onClose={() => setShowVideoMeetings(false)}
              loanId={loan?.id}
            />
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

            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Name *</label>
              <input
                type="text"
                value={teamMemberForm.name}
                onChange={(e) => setTeamMemberForm({ ...teamMemberForm, name: e.target.value })}
                placeholder="Full name"
                style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
              />
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
                  onChange={(e) => setTeamMemberForm({ ...teamMemberForm, phone: e.target.value })}
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
      </div>

      {/* Fixed Sidebar */}
      <CalendarSidebar loanId={id} key={calendarRefreshKey}>
      {/* Quick Actions */}
      <div className="actions-card">
        <h3>QUICK ACTIONS</h3>
        <div className="action-buttons">
          <button
            className="action-btn call"
            onClick={() => handleAction('call')}
            title="Click to call using your phone"
          >
            <span className="icon">📞</span>
            <span>Call</span>
          </button>
          <button
            className="action-btn sms"
            onClick={() => handleAction('sms')}
            title="Send SMS using your phone"
          >
            <span className="icon">💬</span>
            <span>SMS Text</span>
          </button>
          <button
            className="action-btn email"
            onClick={() => handleAction('email')}
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
            className="action-btn video"
            onClick={() => handleAction('video')}
            title="Start UVIP video call"
          >
            <span className="icon">🎥</span>
            <span>UVIP Video Call</span>
          </button>
          <button
            className="action-btn voicemail"
            onClick={() => handleAction('voicemail')}
            title="Drop voicemail message"
          >
            <span className="icon">📞</span>
            <span>Voicemail Drop</span>
          </button>
          <button
            className="action-btn application"
            onClick={() => handleAction('send_application')}
            title="Send borrower application link"
          >
            <span className="icon">📝</span>
            <span>Send Application</span>
          </button>
          <button
            className="action-btn portal"
            onClick={() => handleAction('client_portal')}
            title="Open or create client portal"
          >
            <span className="icon">🌐</span>
            <span>Client Portal</span>
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
    </CalendarSidebar>
    </div>
  );
}

export default LoanDetail;
