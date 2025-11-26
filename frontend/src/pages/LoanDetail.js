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
import EscalationModal from '../components/EscalationModal';
import TeamAssignment from '../components/TeamAssignment';
import EmploymentTab from '../components/EmploymentTab';
import RateLockRecommendation from '../components/RateLockRecommendation';
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
  const [activeTab, setActiveTab] = useState('personal');
  const [borrowers, setBorrowers] = useState([]);
  const [activeBorrower, setActiveBorrower] = useState(0);
  const [saveTimeout, setSaveTimeout] = useState(null);
  const [showVoicemailDrop, setShowVoicemailDrop] = useState(false);
  const [showSMSModal, setShowSMSModal] = useState(false);
  const [showTeamsModal, setShowTeamsModal] = useState(false);
  const [showRecordingModal, setShowRecordingModal] = useState(false);
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [showAppointmentModal, setShowAppointmentModal] = useState(false);
  const [showEscalationModal, setShowEscalationModal] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [emailHistory, setEmailHistory] = useState([]);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [noteText, setNoteText] = useState('');
  const [noteLoading, setNoteLoading] = useState(false);

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

  useEffect(() => {
    loadLoanData();
    loadEmailHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

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
        window.open(`mailto:${borrowerEmail}`, '_blank');
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
    <div className="lead-detail-page">
      {/* Header */}
      <div className="detail-header">
        <button className="btn-back" onClick={() => navigate('/loans')}>
          ← Back to Loans
        </button>

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
              value={formData.amount || ''}
              onChange={(e) => handleFieldChange('amount', parseFloat(e.target.value))}
              placeholder="$"
            />
          </div>

          <div className="loan-field">
            <label>Interest Rate</label>
            <input
              type="number"
              step="0.001"
              value={formData.rate || ''}
              onChange={(e) => handleFieldChange('rate', parseFloat(e.target.value))}
              placeholder="%"
            />
          </div>

          <div className="loan-field">
            <label>Loan Term</label>
            <input
              type="number"
              value={formData.term || ''}
              onChange={(e) => handleFieldChange('term', parseInt(e.target.value))}
              placeholder="months"
            />
          </div>

          <div className="loan-field">
            <label>Loan Type</label>
            <input
              type="text"
              value={formData.program || formData.loan_type || ''}
              onChange={(e) => handleFieldChange('program', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Lock Date</label>
            <input
              type="date"
              value={formData.lock_date ? formData.lock_date.split('T')[0] : ''}
              onChange={(e) => handleFieldChange('lock_date', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Lock Expiration</label>
            <input
              type="date"
              value={formData.lock_expiration ? formData.lock_expiration.split('T')[0] : ''}
              onChange={(e) => handleFieldChange('lock_expiration', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>APR</label>
            <input
              type="number"
              step="0.001"
              value={formData.apr || ''}
              onChange={(e) => handleFieldChange('apr', parseFloat(e.target.value))}
              placeholder="%"
            />
          </div>

          <div className="loan-field">
            <label>Points</label>
            <input
              type="number"
              step="0.125"
              value={formData.points || ''}
              onChange={(e) => handleFieldChange('points', parseFloat(e.target.value))}
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
              value={formData.loan_officer_name || ''}
              onChange={(e) => handleFieldChange('loan_officer_name', e.target.value)}
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
              value={formData.closing_date ? formData.closing_date.split('T')[0] : ''}
              onChange={(e) => handleFieldChange('closing_date', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Appraisal Value</label>
            <input
              type="number"
              value={formData.appraisal_value || ''}
              onChange={(e) => handleFieldChange('appraisal_value', parseFloat(e.target.value))}
              placeholder="$"
            />
          </div>

          <div className="loan-field">
            <label>LTV %</label>
            <input
              type="number"
              step="0.01"
              value={formData.ltv || ''}
              onChange={(e) => handleFieldChange('ltv', parseFloat(e.target.value))}
              placeholder="%"
            />
          </div>

          <div className="loan-field">
            <label>DTI %</label>
            <input
              type="number"
              step="0.01"
              value={formData.dti || ''}
              onChange={(e) => handleFieldChange('dti', parseFloat(e.target.value))}
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

      {/* Tab Content */}
      <div className="detail-content">
        {/* Left Column - Loan Information */}
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
                <label>Loan Number</label>
                <input
                  type="text"
                  value={formData.loan_number || ''}
                  onChange={(e) => handleFieldChange('loan_number', e.target.value)}
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
            <h2>Team Members</h2>
            <TeamAssignment leadId={id} />
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

        {/* Right Column - Actions & Email History */}
        <div className="right-column">
          {/* Quick Actions */}
          <div className="actions-card">
            <h3>Quick Actions</h3>
            <div className="action-buttons">
            <button
              className="action-btn call"
              onClick={() => handleAction('call')}
              disabled={!loan.borrower_phone && !formData.borrower_phone}
              title="Click to call using your phone"
            >
              <span className="icon">📞</span>
              <span>Call</span>
            </button>
            <button
              className="action-btn sms"
              onClick={() => handleAction('sms')}
              disabled={!loan.borrower_phone && !formData.borrower_phone}
              title="Send SMS using your phone"
            >
              <span className="icon">💬</span>
              <span>SMS Text</span>
            </button>
            <button
              className="action-btn email"
              onClick={() => handleAction('email')}
              disabled={!loan.borrower_email && !formData.borrower_email}
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
              disabled={!loan.borrower_phone && !formData.borrower_phone}
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

      {/* Appointment Modal */}
      {loan && (
        <AppointmentModal
          isOpen={showAppointmentModal}
          onClose={() => setShowAppointmentModal(false)}
          lead={{ id: loan.id, name: loan.borrower_name || loan.borrower, phone: loan.borrower_phone, email: loan.borrower_email }}
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
    </div>
  );
}

export default LoanDetail;
