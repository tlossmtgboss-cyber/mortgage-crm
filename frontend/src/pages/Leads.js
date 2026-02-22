import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { leadsAPI } from '../services/api';
import { useLeads } from '../hooks/useQueries';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import SMSModal from '../components/SMSModal';
import CalendarSidebar from '../components/CalendarSidebar';
import PermissionGate from '../components/PermissionGate';
import { usePermissions } from '../contexts/PermissionContext';
import { formatPhoneNumber } from '../utils/phoneUtils';
import AddressAutocomplete from '../components/AddressAutocomplete';
import './Leads.css';
import { toast } from '../utils/toast';

function Leads() {
  const navigate = useNavigate();
  const { canPerformAction, isReadOnlyMode, hasAnyPermission, userRole, isAdmin } = usePermissions();

  // All users can access leads
  const canAccessLeads = true;

  // Use React Query for cached data fetching - instant on revisit!
  const { data: leadsData, isLoading: loading, refetch: refetchLeads } = useLeads();
  const leads = leadsData || [];

  const [showModal, setShowModal] = useState(false);
  const [editingLead, setEditingLead] = useState(null);
  const [activeFilter, setActiveFilter] = useState('All');
  const [activeBorrower, setActiveBorrower] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [viewedLeads, setViewedLeads] = useState(() => {
    // Load viewed leads from localStorage
    const stored = localStorage.getItem('viewedLeads');
    return stored ? new Set(JSON.parse(stored)) : new Set();
  });
  const [showSMSModal, setShowSMSModal] = useState(false);
  const [selectedLeadForSMS, setSelectedLeadForSMS] = useState(null);
  const [statusDropdown, setStatusDropdown] = useState({ show: false, leadId: null, currentStage: null, position: { top: 0, left: 0 } });
  const [duplicateMap, setDuplicateMap] = useState({});  // Map of lead_id -> duplicate info
  const [duplicateTasksCreated, setDuplicateTasksCreated] = useState(false);
  const [selectedLeads, setSelectedLeads] = useState(new Set());
  const [isMasterUser, setIsMasterUser] = useState(false);
  const [bulkStatusSelection, setBulkStatusSelection] = useState('');

  // Form section tab (borrower / property / income / assets)
  const [activeFormTab, setActiveFormTab] = useState('borrower');

  // Borrowers array - each borrower has their own contact info
  const [borrowers, setBorrowers] = useState([
    {
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      credit_score: '',
      employment_status: '',
      employer_name: '',
      annual_income: '',
      monthly_debts: '',
    }
  ]);

  // Shared property and loan data
  const [propertyData, setPropertyData] = useState({
    address: '',
    city: '',
    state: '',
    zip_code: '',
    property_type: '',
    property_value: '',
    down_payment: '',
    first_time_buyer: false,
  });

  const [loanData, setLoanData] = useState({
    loan_type: '',
    loan_number: '',
    preapproval_amount: '',
    source: '',
    stage: 'New',
    notes: '',
  });

  const [assetData, setAssetData] = useState({
    checking_savings: '',
    retirement_accounts: '',
    investments: '',
    gift_funds: '',
  });

  const filters = [
    'All',
    'New',
    'Attempted Contact',
    'Prospect',
    'Application',
    'Pre-Qualified',
    'Pre-Approved',
    'Nurture',
    'Credit Repair',
    'Withdrawn',
    'Does Not Qualify',
  ];

  // Stages that belong on the Leads page — anything else belongs on Active Loans or MUM
  const LEAD_PIPELINE_STAGES = new Set([
    'New', 'Attempted Contact', 'Prospect', 'Application', 'Application Started',
    'Document Fulfillment', 'Pre-Qualified', 'Pre-Approved', 'Under Contract',
    'Long-Term Nurture', 'Nurture', 'Credit Repair', 'Withdrawn', 'Does Not Qualify',
  ]);

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

  // Valid stage transitions — only show stages a lead can move to from its current stage
  const VALID_TRANSITIONS = {
    // Lead stages
    'New': ['Attempted Contact', 'Prospect', 'Long-Term Nurture', 'Withdrawn', 'Does Not Qualify'],
    'Attempted Contact': ['Prospect', 'Application', 'Long-Term Nurture', 'Withdrawn', 'Does Not Qualify'],
    'Prospect': ['Application', 'Pre-Qualified', 'Long-Term Nurture', 'Withdrawn', 'Does Not Qualify'],
    'Application': ['Pre-Qualified', 'Pre-Approved', 'Disclosed', 'Long-Term Nurture', 'Withdrawn', 'Does Not Qualify'],
    'Pre-Qualified': ['Pre-Approved', 'Disclosed', 'Long-Term Nurture', 'Withdrawn', 'Does Not Qualify'],
    'Pre-Approved': ['Disclosed', 'Long-Term Nurture', 'Withdrawn', 'Does Not Qualify'],
    'Long-Term Nurture': ['New', 'Attempted Contact', 'Prospect', 'Withdrawn', 'Does Not Qualify'],
    // Active Loan stages
    'Disclosed': ['Processing', 'Suspended', 'Cancelled', 'Denied', 'Dead'],
    'Processing': ['Submitted', 'Suspended', 'Cancelled', 'Denied', 'Dead'],
    'Submitted': ['Underwriting', 'UW Received', 'Suspended', 'Cancelled', 'Denied', 'Dead'],
    'Underwriting': ['UW Received', 'Conditional Approval', 'Suspended', 'Cancelled', 'Denied', 'Dead'],
    'UW Received': ['Conditional Approval', 'Approved', 'Suspended', 'Cancelled', 'Denied', 'Dead'],
    'Conditional Approval': ['Approved', 'Suspended', 'Cancelled', 'Denied', 'Dead'],
    'Approved': ['CTC', 'Clear to Close', 'Suspended', 'Cancelled', 'Denied', 'Dead'],
    'Suspended': ['Processing', 'Submitted', 'Underwriting', 'Cancelled', 'Denied', 'Dead'],
    'CTC': ['Closing', 'Docs', 'Docs Out', 'Suspended', 'Cancelled', 'Denied', 'Dead'],
    'Clear to Close': ['Closing', 'Docs', 'Docs Out', 'Suspended', 'Cancelled', 'Denied', 'Dead'],
    'Closing': ['Docs', 'Docs Out', 'Funded', 'Suspended', 'Cancelled', 'Denied', 'Dead'],
    'Docs': ['Docs Out', 'Funded', 'Suspended', 'Cancelled', 'Denied', 'Dead'],
    'Docs Out': ['Funded', 'Suspended', 'Cancelled', 'Denied', 'Dead'],
    // Terminal / reactivation
    'Funded': [],
    'Cancelled': ['New'],
    'Denied': ['New'],
    'Dead': ['New'],
    'Withdrawn': ['New'],
    'Does Not Qualify': ['New'],
  };

  // Check if master user on mount
  useEffect(() => {
    const checkMasterUser = () => {
      const token = localStorage.getItem('token');
      if (token) {
        try {
          const payload = JSON.parse(atob(token.split('.')[1]));
          // Check if user ID is 1 or email is admin
          setIsMasterUser(payload.user_id === 1 || payload.sub === 'admin@perenniaai.com');
        } catch (e) {
          console.error('Error parsing token:', e);
        }
      }
    };
    checkMasterUser();
  }, []);

  // Detect duplicates when leads data changes (memoized for performance)
  useEffect(() => {
    if (leads && leads.length > 0) {
      detectDuplicates(leads);
    }
  }, [leads]);

  // Refresh leads data - React Query handles caching automatically
  const loadLeads = () => {
    refetchLeads();
  };

  // Detect duplicates based on email
  const detectDuplicates = (leadsList) => {
    const emailGroups = {};
    leadsList.forEach(lead => {
      if (lead.email) {
        const email = lead.email.toLowerCase();
        if (!emailGroups[email]) {
          emailGroups[email] = [];
        }
        emailGroups[email].push({
          id: lead.id,
          name: lead.name || `${lead.first_name || ''} ${lead.last_name || ''}`.trim(),
          stage: lead.stage,
        });
      }
    });

    // Only keep entries with duplicates
    const duplicates = {};
    Object.entries(emailGroups).forEach(([email, leads]) => {
      if (leads.length > 1) {
        leads.forEach(lead => {
          duplicates[lead.id] = {
            email,
            count: leads.length,
            otherLeads: leads.filter(l => l.id !== lead.id),
          };
        });
      }
    });
    setDuplicateMap(duplicates);
  };

  // Check if lead has duplicates
  const hasDuplicate = (leadId) => duplicateMap[leadId] !== undefined;
  const getDuplicateInfo = (leadId) => duplicateMap[leadId];
  const getTotalDuplicates = () => {
    const uniqueEmails = new Set(Object.values(duplicateMap).map(d => d.email));
    return uniqueEmails.size;
  };

  // Create tasks for duplicates
  const handleCreateDuplicateTasks = async () => {
    try {
      const token = localStorage.getItem('token');
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction
        ? 'https://api.perenniaai.com'
        : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      const response = await fetch(`${API_BASE}/api/v1/duplicates/create-tasks`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const data = await response.json();
        setDuplicateTasksCreated(true);

        // Show detailed results
        let message = `Created ${data.tasks_created} new task(s).`;
        if (data.tasks_existing > 0) {
          message += `\n${data.tasks_existing} task(s) already existed.`;
        }
        if (data.errors && data.errors.length > 0) {
          message += `\n\nErrors:\n${data.errors.join('\n')}`;
        }
        toast.info(message);
      } else {
        const error = await response.json();
        toast.error(`Error: ${error.detail || 'Failed to create tasks'}`);
      }
    } catch (err) {
      console.error('Error creating duplicate tasks:', err);
      toast.error('Failed to create duplicate tasks');
    }
  };

  // Ensure leads is always an array before filtering
  // Exclude leads that belong on Active Loans or MUM pages (Funded, Closed, Disclosed, etc.)
  const safeLeads = (Array.isArray(leads) ? leads : []).filter(lead => {
    if (!lead.stage) return true; // Show leads with no stage
    return LEAD_PIPELINE_STAGES.has(lead.stage);
  });

  // Filter by stage
  let filteredLeads;
  if (activeFilter === 'All') {
    filteredLeads = safeLeads;
  } else if (activeFilter === 'Nurture') {
    filteredLeads = safeLeads.filter(lead => lead.stage === 'Nurture' || lead.stage === 'Long-Term Nurture');
  } else {
    filteredLeads = safeLeads.filter(lead => lead.stage === activeFilter);
  }

  // Filter by search query
  if (searchQuery.trim()) {
    const query = searchQuery.toLowerCase();
    filteredLeads = filteredLeads.filter(lead =>
      lead.name?.toLowerCase().includes(query) ||
      lead.email?.toLowerCase().includes(query) ||
      lead.phone?.toLowerCase().includes(query) ||
      lead.source?.toLowerCase().includes(query)
    );
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      // Combine primary borrower data with property and loan data
      const primaryBorrower = borrowers[0];

      // Validate required fields
      const fullName = `${primaryBorrower.first_name || ''} ${primaryBorrower.last_name || ''}`.trim();
      if (!fullName) {
        toast.error('Please enter at least a first name or last name');
        return;
      }

      const rawData = {
        name: fullName,
        email: primaryBorrower.email,
        phone: primaryBorrower.phone,
        credit_score: primaryBorrower.credit_score,
        employment_status: primaryBorrower.employment_status,
        employer_name: primaryBorrower.employer_name,
        annual_income: primaryBorrower.annual_income,
        monthly_debts: primaryBorrower.monthly_debts,
        ...propertyData,
        ...loanData,
      };

      // Pack asset fields into user_metadata if any values present
      const assetFields = {};
      if (assetData.checking_savings) assetFields.checking_savings = parseFloat(assetData.checking_savings);
      if (assetData.retirement_accounts) assetFields.retirement_accounts = parseFloat(assetData.retirement_accounts);
      if (assetData.investments) assetFields.investments = parseFloat(assetData.investments);
      if (assetData.gift_funds) assetFields.gift_funds = parseFloat(assetData.gift_funds);
      if (Object.keys(assetFields).length > 0) {
        rawData.user_metadata = { ...(rawData.user_metadata || {}), assets: assetFields };
      }

      // Clean up data - convert empty strings to null for numeric fields
      const formData = Object.entries(rawData).reduce((acc, [key, value]) => {
        // Always include name, first_time_buyer, stage, and user_metadata
        if (key === 'name' || key === 'first_time_buyer' || key === 'stage' || key === 'user_metadata') {
          acc[key] = value;
          return acc;
        }
        // Skip empty values for other fields
        if (value === '' || value === undefined || value === null) {
          return acc;
        }
        // Convert numeric strings to numbers for numeric fields
        if (['credit_score', 'annual_income', 'monthly_debts', 'property_value',
             'down_payment', 'preapproval_amount'].includes(key)) {
          const num = parseFloat(value);
          if (!isNaN(num)) {
            acc[key] = num;
          }
        } else {
          acc[key] = value;
        }
        return acc;
      }, {});

      console.log('Submitting lead data:', formData);

      if (editingLead) {
        await leadsAPI.update(editingLead.id, formData);
      } else {
        await leadsAPI.create(formData);
      }
      setShowModal(false);
      setEditingLead(null);
      resetForm();
      // Clear cache to ensure new lead appears immediately
      localStorage.removeItem('leads_data');
      localStorage.removeItem('leads_data_time');
      loadLeads();
    } catch (err) {
      console.error('Failed to save lead:', err);
      console.error('Error response:', err.response?.data);
      const errorMsg = err.response?.data?.detail
        ? (typeof err.response.data.detail === 'string'
           ? err.response.data.detail
           : JSON.stringify(err.response.data.detail))
        : err.message;
      toast.error('Failed to save lead: ' + errorMsg);
    }
  };

  const handleEdit = (lead) => {
    setEditingLead(lead);

    // Parse name into first and last name
    const nameParts = (lead.name || '').split(' ');
    const firstName = nameParts[0] || '';
    const lastName = nameParts.slice(1).join(' ') || '';

    setBorrowers([{
      first_name: firstName,
      last_name: lastName,
      email: lead.email || '',
      phone: lead.phone || '',
      credit_score: lead.credit_score || '',
      employment_status: lead.employment_status || '',
      employer_name: lead.employer_name || '',
      annual_income: lead.annual_income || '',
      monthly_debts: lead.monthly_debts || '',
    }]);

    setPropertyData({
      address: lead.address || '',
      city: lead.city || '',
      state: lead.state || '',
      zip_code: lead.zip_code || '',
      property_type: lead.property_type || '',
      property_value: lead.property_value || '',
      down_payment: lead.down_payment || '',
      first_time_buyer: lead.first_time_buyer || false,
    });

    setLoanData({
      loan_type: lead.loan_type || '',
      loan_number: lead.loan_number || '',
      preapproval_amount: lead.preapproval_amount || '',
      source: lead.source || '',
      stage: lead.stage || 'New',
      notes: lead.notes || '',
    });

    // Unpack asset data from user_metadata
    const assets = lead.user_metadata?.assets || {};
    setAssetData({
      checking_savings: assets.checking_savings || '',
      retirement_accounts: assets.retirement_accounts || '',
      investments: assets.investments || '',
      gift_funds: assets.gift_funds || '',
    });

    setActiveBorrower(0);
    setActiveFormTab('borrower');
    setShowModal(true);
  };

  const handleDelete = async (id) => {
    // Find the lead name for the confirmation
    const lead = leads.find(l => l.id === id);
    const leadName = lead?.name || `Lead #${id}`;

    if (!window.confirm(`Are you sure you want to delete "${leadName}"? This action cannot be undone.`)) {
      return;
    }

    try {
      console.log('Deleting lead:', id);
      await leadsAPI.delete(id);
      console.log('Lead deleted successfully');
      // Clear cache and reload
      localStorage.removeItem('leads_data');
      localStorage.removeItem('leads_data_time');
      loadLeads();
    } catch (err) {
      console.error('Failed to delete lead:', err);
      toast.error('Failed to delete lead: ' + (err.response?.data?.detail || err.message));
    }
  };

  // Bulk selection handlers
  const handleSelectLead = (leadId, e) => {
    e.stopPropagation();
    const newSelected = new Set(selectedLeads);
    if (newSelected.has(leadId)) {
      newSelected.delete(leadId);
    } else {
      newSelected.add(leadId);
    }
    setSelectedLeads(newSelected);
  };

  const handleSelectAll = (e) => {
    e.stopPropagation();
    if (selectedLeads.size === filteredLeads.length) {
      // Deselect all
      setSelectedLeads(new Set());
    } else {
      // Select all visible leads
      setSelectedLeads(new Set(filteredLeads.map(lead => lead.id)));
    }
  };

  const handleBulkDelete = async () => {
    if (selectedLeads.size === 0) return;

    const count = selectedLeads.size;
    if (!window.confirm(`Are you sure you want to delete ${count} lead${count > 1 ? 's' : ''}? This action cannot be undone.`)) {
      return;
    }

    try {
      const leadIds = Array.from(selectedLeads);
      console.log('Bulk deleting leads:', leadIds);
      const result = await leadsAPI.bulkDelete(leadIds);
      console.log('Bulk delete result:', result);

      // Clear selection
      setSelectedLeads(new Set());

      // Clear cache and reload
      localStorage.removeItem('leads_data');
      localStorage.removeItem('leads_data_time');
      loadLeads();

      toast.success(result.message || `Successfully deleted ${result.deleted_count} leads`);
    } catch (err) {
      console.error('Failed to bulk delete leads:', err);
      const errorDetail = err.response?.data?.detail;
      const errorMessage = typeof errorDetail === 'string'
        ? errorDetail
        : (errorDetail?.message || err.message || 'Unknown error');
      toast.error('Failed to delete leads: ' + errorMessage);
    }
  };

  const handleBulkStatusUpdate = async () => {
    if (selectedLeads.size === 0 || !bulkStatusSelection) return;

    const count = selectedLeads.size;
    if (!window.confirm(`Are you sure you want to change ${count} lead${count > 1 ? 's' : ''} to "${bulkStatusSelection}"?`)) {
      return;
    }

    try {
      const leadIds = Array.from(selectedLeads);
      console.log('Bulk updating leads:', leadIds, 'to status:', bulkStatusSelection);
      const result = await leadsAPI.bulkUpdateStatus(leadIds, bulkStatusSelection);
      console.log('Bulk update result:', result);

      // Clear selection
      setSelectedLeads(new Set());
      setBulkStatusSelection('');

      // Clear cache and reload
      localStorage.removeItem('leads_data');
      localStorage.removeItem('leads_data_time');
      loadLeads();

      let msg = result.message || `Successfully updated ${result.updated_count} leads to "${bulkStatusSelection}"`;
      if (result.cascade_summary) {
        const cs = result.cascade_summary;
        const parts = [];
        if (cs.loans_updated > 0) parts.push(`${cs.loans_updated} loan${cs.loans_updated > 1 ? 's' : ''}`);
        if (cs.mum_clients_updated > 0) parts.push(`${cs.mum_clients_updated} MUM client${cs.mum_clients_updated > 1 ? 's' : ''}`);
        if (parts.length > 0) msg += `\nAlso cascaded to ${parts.join(' and ')}.`;
      }
      toast.info(msg);
    } catch (err) {
      console.error('Failed to bulk update leads:', err);
      const errorDetail = err.response?.data?.detail;
      const errorMessage = typeof errorDetail === 'string'
        ? errorDetail
        : (errorDetail?.message || err.message || 'Unknown error');
      toast.error('Failed to update leads: ' + errorMessage);
    }
  };

  const resetForm = () => {
    setBorrowers([{
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      credit_score: '',
      employment_status: '',
      employer_name: '',
      annual_income: '',
      monthly_debts: '',
    }]);

    setPropertyData({
      address: '',
      city: '',
      state: '',
      zip_code: '',
      property_type: '',
      property_value: '',
      down_payment: '',
      first_time_buyer: false,
    });

    setLoanData({
      loan_type: '',
      loan_number: '',
      preapproval_amount: '',
      source: '',
      stage: 'New',
      notes: '',
    });

    setAssetData({
      checking_savings: '',
      retirement_accounts: '',
      investments: '',
      gift_funds: '',
    });

    setActiveBorrower(0);
    setActiveFormTab('borrower');
  };

  const handleNewLead = () => {
    setEditingLead(null);
    resetForm();
    setShowModal(true);
  };

  const addBorrower = () => {
    setBorrowers([...borrowers, {
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      credit_score: '',
      employment_status: '',
      employer_name: '',
      annual_income: '',
      monthly_debts: '',
    }]);
    setActiveBorrower(borrowers.length);
  };

  const removeBorrower = (index) => {
    if (borrowers.length > 1) {
      const newBorrowers = borrowers.filter((_, i) => i !== index);
      setBorrowers(newBorrowers);
      setActiveBorrower(Math.max(0, index - 1));
    }
  };

  const updateBorrower = (index, field, value) => {
    const newBorrowers = [...borrowers];
    newBorrowers[index] = { ...newBorrowers[index], [field]: value };
    setBorrowers(newBorrowers);
  };

  const getStatusColor = (status) => {
    const colors = {
      // Lead stages
      'New': 'blue',
      'Attempted Contact': 'teal',
      'Prospect': 'yellow',
      'Application': 'orange',
      'Pre-Qualified': 'teal',
      'Pre-Approved': 'cyan',
      'Nurture': 'purple',
      'Long-Term Nurture': 'purple',
      'Withdrawn': 'red',
      'Does Not Qualify': 'gray',
      // Active Loan stages
      'Disclosed': 'orange',
      'Processing': 'orange',
      'Submitted': 'orange',
      'Underwriting': 'yellow',
      'UW Received': 'yellow',
      'Conditional Approval': 'cyan',
      'Approved': 'green',
      'Suspended': 'red',
      'CTC': 'green',
      'Clear to Close': 'green',
      'Closing': 'green',
      'Docs': 'green',
      'Docs Out': 'green',
      'Cancelled': 'red',
      'Denied': 'red',
      'Dead': 'gray',
      // MUM
      'Funded': 'green',
    };
    return colors[status] || 'gray';
  };

  const isNewLead = (createdAt) => {
    if (!createdAt) return false;
    const leadDate = new Date(createdAt);
    const now = new Date();
    const hoursDiff = (now - leadDate) / (1000 * 60 * 60);
    return hoursDiff <= 48; // Lead is "new" if created within last 48 hours
  };

  const isLeadUnviewed = (leadId) => {
    return !viewedLeads.has(String(leadId));
  };

  const handleLeadClick = (leadId) => {
    console.log('Lead clicked:', leadId);

    // Mark lead as viewed
    const newViewedLeads = new Set(viewedLeads);
    newViewedLeads.add(String(leadId));
    setViewedLeads(newViewedLeads);

    // Save to localStorage
    localStorage.setItem('viewedLeads', JSON.stringify([...newViewedLeads]));

    // Navigate to lead detail
    console.log('Navigating to:', `/leads/${leadId}`);
    navigate(`/leads/${leadId}`);
  };

  const handleStatusClick = (e, leadId, currentStage) => {
    e.stopPropagation(); // Prevent row click
    const rect = e.target.getBoundingClientRect();
    setStatusDropdown({
      show: true,
      leadId,
      currentStage: currentStage || null,
      position: {
        top: rect.bottom + window.scrollY + 5,
        left: rect.left + window.scrollX,
      },
    });
  };

  const handleStatusChange = async (newStatus) => {
    const leadId = statusDropdown.leadId;
    setStatusDropdown({ show: false, leadId: null, currentStage: null, position: { top: 0, left: 0 } });

    try {
      const result = await leadsAPI.update(leadId, { stage: newStatus });
      // Refresh data via React Query
      refetchLeads();
      // Clear cache
      localStorage.removeItem('leads_data');
      localStorage.removeItem('leads_data_time');

      // Show cascade feedback if loans/MUM clients were updated
      if (result?.data?.cascade) {
        const c = result.data.cascade;
        const parts = [];
        if (c.loans_updated > 0) parts.push(`${c.loans_updated} loan${c.loans_updated > 1 ? 's' : ''}`);
        if (c.mum_clients_updated > 0) parts.push(`${c.mum_clients_updated} MUM client${c.mum_clients_updated > 1 ? 's' : ''}`);
        if (parts.length > 0) {
          toast.info(`Status cascaded to ${parts.join(' and ')}`);
        }
      }
    } catch (err) {
      console.error('Failed to update status:', err);
      toast.error('Failed to update status');
    }
  };

  const closeStatusDropdown = () => {
    setStatusDropdown({ show: false, leadId: null, currentStage: null, position: { top: 0, left: 0 } });
  };

  // Access denied if user doesn't have leads permissions
  if (!canAccessLeads) {
    return (
      <div className="leads-page-wrapper">
        <div className="leads-page">
          <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
            <h2>Access Denied</h2>
            <p>You don't have permission to view leads.</p>
            <button className="btn-primary" onClick={() => navigate('/dashboard')}>
              Return to Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return <div className="loading">Loading leads...</div>;
  }

  const currentBorrower = borrowers[activeBorrower] || borrowers[0];

  return (
    <div className="leads-page-wrapper">
      <div className="leads-page">
        <div className="page-header">
        <div>
          <h1>Leads</h1>
          <p>{leads.length} total leads</p>
        </div>
          <button className="btn-primary" onClick={handleNewLead}>
            + Add Lead
          </button>
      </div>

      <div className="filter-tabs">
        {filters.map((filter) => (
          <button
            key={filter}
            className={`filter-tab ${activeFilter === filter ? 'active' : ''}`}
            onClick={() => setActiveFilter(filter)}
          >
            {filter}
          </button>
        ))}
      </div>

      <div className="search-bar-container">
        <input
          type="text"
          className="search-bar"
          placeholder="Search leads by name, email, phone, or source..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchQuery && (
          <button className="clear-search" onClick={() => setSearchQuery('')}>
            ×
          </button>
        )}
      </div>

      {/* Bulk Actions Bar - Only for users with appropriate permissions or master users */}
      {selectedLeads.size > 0 && (
        <div className="bulk-actions-bar">
          <span className="selected-count">{selectedLeads.size} lead{selectedLeads.size > 1 ? 's' : ''} selected</span>

          {/* Bulk Status Change */}
          <select
            value={bulkStatusSelection}
            onChange={(e) => setBulkStatusSelection(e.target.value)}
            className="bulk-status-select"
          >
            <option value="">Change Status To...</option>
            <optgroup label="Lead Stages">
              <option value="New">New</option>
              <option value="Attempted Contact">Attempted Contact</option>
              <option value="Prospect">Prospect</option>
              <option value="Application">Application</option>
              <option value="Pre-Qualified">Pre-Qualified</option>
              <option value="Pre-Approved">Pre-Approved</option>
              <option value="Long-Term Nurture">Nurture</option>
              <option value="Withdrawn">Withdrawn</option>
              <option value="Does Not Qualify">Does Not Qualify</option>
            </optgroup>
            <optgroup label="Active Loan Stages">
              <option value="Disclosed">Disclosed</option>
              <option value="Processing">Processing</option>
              <option value="Submitted">Submitted</option>
              <option value="Underwriting">Underwriting</option>
              <option value="UW Received">UW Received</option>
              <option value="Conditional Approval">Conditional Approval</option>
              <option value="Approved">Approved</option>
              <option value="Suspended">Suspended</option>
              <option value="CTC">CTC</option>
              <option value="Clear to Close">Clear to Close</option>
              <option value="Closing">Closing</option>
              <option value="Docs">Docs</option>
              <option value="Docs Out">Docs Out</option>
              <option value="Cancelled">Cancelled</option>
              <option value="Denied">Denied</option>
              <option value="Dead">Dead</option>
            </optgroup>
            <optgroup label="MUM / Closed">
              <option value="Funded">Funded</option>
            </optgroup>
          </select>
          <button
            className="btn-primary"
            onClick={handleBulkStatusUpdate}
            disabled={!bulkStatusSelection}
          >
            Apply Status
          </button>

          {/* Bulk Delete */}
            <button className="btn-danger" onClick={handleBulkDelete}>
              🗑️ Delete Selected
            </button>
          <button className="btn-secondary" onClick={() => { setSelectedLeads(new Set()); setBulkStatusSelection(''); }}>
            Cancel
          </button>
        </div>
      )}

      {/* Duplicate Warning Banner */}
      {getTotalDuplicates() > 0 && (
        <div className="duplicate-warning-banner">
          <div className="duplicate-warning-content">
            <span className="duplicate-icon">⚠️</span>
            <span className="duplicate-text">
              <strong>{getTotalDuplicates()} potential duplicate{getTotalDuplicates() > 1 ? 's' : ''} detected</strong>
              {' '}- Leads with the same email address found. Review and merge to avoid confusion.
            </span>
          </div>
          {!duplicateTasksCreated && (
            <button className="create-tasks-btn" onClick={handleCreateDuplicateTasks}>
              Create Merge Tasks
            </button>
          )}
          {duplicateTasksCreated && (
            <span className="tasks-created-badge">✓ Tasks Created</span>
          )}
        </div>
      )}

      <div className="table-container">
        <table className="leads-table">
          <thead>
            <tr>
              {isMasterUser && (
                <th className="checkbox-column">
                  <input
                    type="checkbox"
                    checked={filteredLeads.length > 0 && selectedLeads.size === filteredLeads.length}
                    onChange={handleSelectAll}
                    title="Select All"
                  />
                </th>
              )}
              <th className="col-sticky-name">Name</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Status</th>
              <th>Loan Amount</th>
              <th>Loan Purpose</th>
              <th>Loan Type</th>
              <th>Interest Rate</th>
              <th>Loan Term</th>
              <th>LTV</th>
              <th>DTI</th>
              <th>Property Address</th>
              <th>Property Type</th>
              <th>Occupancy</th>
              <th>Property Value</th>
              <th>Appraisal Value</th>
              <th>Assigned LO</th>
              <th>Processor</th>
              <th>Last Contact</th>
              <th>Source</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredLeads.map((lead) => (
              <tr
                key={lead.id}
                className={`${isNewLead(lead.created_at) && isLeadUnviewed(lead.id) ? 'new-lead-row' : ''} ${hasDuplicate(lead.id) ? 'has-duplicate' : ''} ${selectedLeads.has(lead.id) ? 'selected-row' : ''}`}
                onClick={() => handleLeadClick(lead.id)}
              >
                {isMasterUser && (
                  <td className="checkbox-column">
                    <input
                      type="checkbox"
                      checked={selectedLeads.has(lead.id)}
                      onChange={(e) => handleSelectLead(lead.id, e)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </td>
                )}
                <td className="lead-name col-sticky-name">
                  <div className="borrower-info">
                    <span>{lead.name}</span>
                    {isNewLead(lead.created_at) && isLeadUnviewed(lead.id) && <span className="new-lead-badge">NEW</span>}
                    {hasDuplicate(lead.id) && (
                      <span
                        className="duplicate-badge"
                        title={`Duplicate: Same email as ${getDuplicateInfo(lead.id).otherLeads.map(l => l.name).join(', ')}`}
                      >
                        DUPLICATE
                      </span>
                    )}
                  </div>
                </td>
                <td><ClickableEmail email={lead.email} /></td>
                <td>
                  <ClickablePhone
                    phone={lead.phone}
                    showActions={true}
                    contactName={lead.name || `${lead.first_name || ''} ${lead.last_name || ''}`.trim()}
                    leadId={lead.id}
                    onSMSClick={() => {
                      setSelectedLeadForSMS(lead);
                      setShowSMSModal(true);
                    }}
                  />
                </td>
                <td>
                  <span
                    className={`status-badge status-${getStatusColor(lead.stage)} status-clickable`}
                    onClick={(e) => handleStatusClick(e, lead.id, lead.stage)}
                    title="Click to change status"
                  >
                    {lead.stage}
                  </span>
                </td>
                <td className="col-currency">{lead.loan_amount ? `$${Number(lead.loan_amount).toLocaleString()}` : '—'}</td>
                <td>{lead.loan_purpose || '—'}</td>
                <td>{lead.loan_type || '—'}</td>
                <td>{lead.interest_rate ? `${lead.interest_rate}%` : '—'}</td>
                <td>{lead.loan_term ? `${lead.loan_term} yr` : '—'}</td>
                <td>{lead.ltv ? `${lead.ltv}%` : '—'}</td>
                <td>{lead.dti ? `${lead.dti}%` : '—'}</td>
                <td className="col-address">{lead.address ? `${lead.address}${lead.city ? `, ${lead.city}` : ''}${lead.state ? ` ${lead.state}` : ''}${lead.zip_code ? ` ${lead.zip_code}` : ''}` : '—'}</td>
                <td>{lead.property_type || '—'}</td>
                <td>{lead.occupancy_type || '—'}</td>
                <td className="col-currency">{lead.property_value ? `$${Number(lead.property_value).toLocaleString()}` : '—'}</td>
                <td className="col-currency">{lead.appraisal_value ? `$${Number(lead.appraisal_value).toLocaleString()}` : '—'}</td>
                <td>{lead.loan_officer || '—'}</td>
                <td>{lead.processor || '—'}</td>
                <td>{lead.updated_at ? new Date(lead.updated_at).toLocaleDateString() : 'N/A'}</td>
                <td>{lead.source || 'N/A'}</td>
                <td>
                  <div className="table-actions">
                    <button className="btn-icon" onClick={(e) => { e.stopPropagation(); handleDelete(lead.id); }} title="Delete">
                      🗑️
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filteredLeads.length === 0 && (
        <div className="empty-state">
          <h3>No leads found</h3>
          <p>Try adjusting your filters or add a new lead</p>
        </div>
      )}

      {leads.length === 0 && (
        <div className="empty-state">
          <h3>No leads yet</h3>
          <p>Get started by adding your first lead</p>
          <button className="btn-primary" onClick={handleNewLead}>
            + Add Your First Lead
          </button>
        </div>
      )}

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{editingLead ? 'Edit Lead' : 'New Lead'}</h2>
              <button className="close-btn" onClick={() => setShowModal(false)}>
                ×
              </button>
            </div>

            <form onSubmit={handleSubmit}>
              {/* Borrower Tabs */}
              <div className="borrower-tabs">
                <div className="tabs-row">
                  {borrowers.map((borrower, index) => (
                    <div
                      key={index}
                      className={`borrower-tab ${activeBorrower === index ? 'active' : ''}`}
                      onClick={() => setActiveBorrower(index)}
                    >
                      <span>Borrower {index + 1}</span>
                      {index > 0 && (
                        <button
                          type="button"
                          className="remove-borrower-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            removeBorrower(index);
                          }}
                          title="Remove borrower"
                        >
                          ×
                        </button>
                      )}
                    </div>
                  ))}
                  <button
                    type="button"
                    className="add-borrower-btn"
                    onClick={addBorrower}
                    title="Add another borrower"
                  >
                    +
                  </button>
                </div>
              </div>

              {/* Form Section Tabs */}
              <div className="form-section-tabs">
                <button type="button" className={`form-section-tab ${activeFormTab === 'borrower' ? 'active' : ''}`} onClick={() => setActiveFormTab('borrower')}>Borrower Info</button>
                <button type="button" className={`form-section-tab ${activeFormTab === 'property' ? 'active' : ''}`} onClick={() => setActiveFormTab('property')}>Property</button>
                <button type="button" className={`form-section-tab ${activeFormTab === 'income' ? 'active' : ''}`} onClick={() => setActiveFormTab('income')}>Income</button>
                <button type="button" className={`form-section-tab ${activeFormTab === 'assets' ? 'active' : ''}`} onClick={() => setActiveFormTab('assets')}>Assets</button>
              </div>

              {/* === BORROWER INFO TAB === */}
              {activeFormTab === 'borrower' && (
                <>
                  <div className="form-row">
                    <div className="form-group">
                      <label>First Name *</label>
                      <input
                        type="text"
                        value={currentBorrower.first_name}
                        onChange={(e) => updateBorrower(activeBorrower, 'first_name', e.target.value)}
                        required={activeBorrower === 0}
                      />
                    </div>
                    <div className="form-group">
                      <label>Last Name *</label>
                      <input
                        type="text"
                        value={currentBorrower.last_name}
                        onChange={(e) => updateBorrower(activeBorrower, 'last_name', e.target.value)}
                        required={activeBorrower === 0}
                      />
                    </div>
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label>Email</label>
                      <input
                        type="email"
                        value={currentBorrower.email}
                        onChange={(e) => updateBorrower(activeBorrower, 'email', e.target.value)}
                      />
                    </div>
                    <div className="form-group">
                      <label>Phone</label>
                      <input
                        type="tel"
                        value={currentBorrower.phone}
                        onChange={(e) => updateBorrower(activeBorrower, 'phone', formatPhoneNumber(e.target.value))}
                      />
                    </div>
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label>Credit Score</label>
                      <input
                        type="number"
                        value={currentBorrower.credit_score}
                        onChange={(e) => updateBorrower(activeBorrower, 'credit_score', e.target.value)}
                        min="300"
                        max="850"
                      />
                    </div>
                    <div className="form-group">
                      <label>Source</label>
                      <input
                        type="text"
                        value={loanData.source}
                        onChange={(e) => setLoanData({ ...loanData, source: e.target.value })}
                        placeholder="Website, Referral, etc."
                      />
                    </div>
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label>Lead Status</label>
                      <select
                        value={loanData.stage}
                        onChange={(e) => setLoanData({ ...loanData, stage: e.target.value })}
                      >
                        <option value="New">New</option>
                        <option value="Attempted Contact">Attempted Contact</option>
                        <option value="Prospect">Prospect</option>
                        <option value="Application">Application</option>
                        <option value="Pre-Qualified">Pre-Qualified</option>
                        <option value="Pre-Approved">Pre-Approved</option>
                        <option value="Long-Term Nurture">Nurture</option>
                        <option value="Withdrawn">Withdrawn</option>
                        <option value="Does Not Qualify">Does Not Qualify</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label>Notes</label>
                      <textarea
                        rows="3"
                        value={loanData.notes}
                        onChange={(e) => setLoanData({ ...loanData, notes: e.target.value })}
                        placeholder="Additional notes..."
                      />
                    </div>
                  </div>
                </>
              )}

              {/* === PROPERTY TAB === */}
              {activeFormTab === 'property' && (
                <>
                  <div className="form-group">
                    <label>Property Address</label>
                    <AddressAutocomplete
                      value={propertyData.address}
                      onChange={(text) => setPropertyData({ ...propertyData, address: text })}
                      onAddressSelect={(addressData) => {
                        setPropertyData({
                          ...propertyData,
                          address: addressData.street || addressData.formatted,
                          city: addressData.city || propertyData.city,
                          state: addressData.state_code || propertyData.state,
                          zip_code: addressData.zip || propertyData.zip_code,
                        });
                      }}
                      placeholder="Start typing an address..."
                    />
                  </div>

                  <div className="form-row three-cols">
                    <div className="form-group">
                      <label>City</label>
                      <input
                        type="text"
                        value={propertyData.city}
                        onChange={(e) => setPropertyData({ ...propertyData, city: e.target.value })}
                      />
                    </div>
                    <div className="form-group">
                      <label>State</label>
                      <input
                        type="text"
                        value={propertyData.state}
                        onChange={(e) => setPropertyData({ ...propertyData, state: e.target.value })}
                        maxLength="2"
                        placeholder="CA"
                      />
                    </div>
                    <div className="form-group">
                      <label>ZIP Code</label>
                      <input
                        type="text"
                        value={propertyData.zip_code}
                        onChange={(e) => setPropertyData({ ...propertyData, zip_code: e.target.value })}
                        maxLength="10"
                      />
                    </div>
                  </div>

                  <div className="form-row three-cols">
                    <div className="form-group">
                      <label>Property Type</label>
                      <select
                        value={propertyData.property_type}
                        onChange={(e) => setPropertyData({ ...propertyData, property_type: e.target.value })}
                      >
                        <option value="">Select...</option>
                        <option value="Single Family">Single Family</option>
                        <option value="Condo">Condo</option>
                        <option value="Townhouse">Townhouse</option>
                        <option value="Multi-Family">Multi-Family</option>
                        <option value="Manufactured">Manufactured</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label>Property Value</label>
                      <input
                        type="number"
                        value={propertyData.property_value}
                        onChange={(e) => setPropertyData({ ...propertyData, property_value: e.target.value })}
                        placeholder="$"
                      />
                    </div>
                    <div className="form-group">
                      <label>Down Payment</label>
                      <input
                        type="number"
                        value={propertyData.down_payment}
                        onChange={(e) => setPropertyData({ ...propertyData, down_payment: e.target.value })}
                        placeholder="$"
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={propertyData.first_time_buyer}
                        onChange={(e) => setPropertyData({ ...propertyData, first_time_buyer: e.target.checked })}
                      />
                      First-Time Home Buyer
                    </label>
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label>Loan Type</label>
                      <select
                        value={loanData.loan_type}
                        onChange={(e) => setLoanData({ ...loanData, loan_type: e.target.value })}
                      >
                        <option value="">Select...</option>
                        <option value="Purchase">Purchase</option>
                        <option value="Refinance">Refinance</option>
                        <option value="Cash-Out Refi">Cash-Out Refi</option>
                        <option value="HELOC">HELOC</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label>Loan Number</label>
                      <input
                        type="text"
                        value={loanData.loan_number}
                        onChange={(e) => setLoanData({ ...loanData, loan_number: e.target.value })}
                        placeholder="Optional loan number"
                      />
                    </div>
                  </div>
                </>
              )}

              {/* === INCOME TAB === */}
              {activeFormTab === 'income' && (
                <>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Employment Status</label>
                      <select
                        value={currentBorrower.employment_status}
                        onChange={(e) => updateBorrower(activeBorrower, 'employment_status', e.target.value)}
                      >
                        <option value="">Select...</option>
                        <option value="Full-Time">Full-Time</option>
                        <option value="Part-Time">Part-Time</option>
                        <option value="Self-Employed">Self-Employed</option>
                        <option value="Retired">Retired</option>
                        <option value="Unemployed">Unemployed</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label>Employer</label>
                      <input
                        type="text"
                        value={currentBorrower.employer_name}
                        onChange={(e) => updateBorrower(activeBorrower, 'employer_name', e.target.value)}
                        placeholder="Company name"
                      />
                    </div>
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label>Annual Income</label>
                      <input
                        type="number"
                        value={currentBorrower.annual_income}
                        onChange={(e) => updateBorrower(activeBorrower, 'annual_income', e.target.value)}
                        placeholder="$"
                      />
                    </div>
                    <div className="form-group">
                      <label>Monthly Debts</label>
                      <input
                        type="number"
                        value={currentBorrower.monthly_debts}
                        onChange={(e) => updateBorrower(activeBorrower, 'monthly_debts', e.target.value)}
                        placeholder="$"
                      />
                    </div>
                  </div>
                </>
              )}

              {/* === ASSETS TAB === */}
              {activeFormTab === 'assets' && (
                <>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Checking / Savings Balance</label>
                      <input
                        type="number"
                        value={assetData.checking_savings}
                        onChange={(e) => setAssetData({ ...assetData, checking_savings: e.target.value })}
                        placeholder="$"
                      />
                    </div>
                    <div className="form-group">
                      <label>Retirement Accounts</label>
                      <input
                        type="number"
                        value={assetData.retirement_accounts}
                        onChange={(e) => setAssetData({ ...assetData, retirement_accounts: e.target.value })}
                        placeholder="$"
                      />
                    </div>
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label>Investments</label>
                      <input
                        type="number"
                        value={assetData.investments}
                        onChange={(e) => setAssetData({ ...assetData, investments: e.target.value })}
                        placeholder="$"
                      />
                    </div>
                    <div className="form-group">
                      <label>Gift Funds</label>
                      <input
                        type="number"
                        value={assetData.gift_funds}
                        onChange={(e) => setAssetData({ ...assetData, gift_funds: e.target.value })}
                        placeholder="$"
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label>Preapproval Amount</label>
                    <input
                      type="number"
                      value={loanData.preapproval_amount}
                      onChange={(e) => setLoanData({ ...loanData, preapproval_amount: e.target.value })}
                      placeholder="$"
                    />
                  </div>
                </>
              )}

              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  {editingLead ? 'Update Lead' : 'Create Lead'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* SMS Modal */}
      {selectedLeadForSMS && (
        <SMSModal
          isOpen={showSMSModal}
          onClose={() => {
            setShowSMSModal(false);
            setSelectedLeadForSMS(null);
          }}
          lead={selectedLeadForSMS}
        />
      )}

      {/* Status Dropdown Popup */}
      {statusDropdown.show && (
        <>
          <div className="status-dropdown-overlay" onClick={closeStatusDropdown} />
          <div
            className="status-dropdown-popup"
            style={{
              top: statusDropdown.position.top,
              left: statusDropdown.position.left,
            }}
          >
            <div className="status-dropdown-header">
              Change Status
              {statusDropdown.currentStage && (
                <span style={{ fontSize: '11px', color: '#6b7280', fontWeight: 400, marginLeft: '6px' }}>
                  from {statusDropdown.currentStage}
                </span>
              )}
            </div>
            <div className="status-dropdown-options" style={{ maxHeight: '400px', overflowY: 'auto' }}>
              {(() => {
                const validSet = new Set(VALID_TRANSITIONS[statusDropdown.currentStage] || []);
                const hasTransitions = validSet.size > 0;
                // Filter options to only show valid transitions
                const filtered = hasTransitions
                  ? statusOptions.filter(status => {
                      if (status.isHeader) return false; // Headers handled separately
                      return validSet.has(status);
                    })
                  : []; // Terminal stage — no transitions

                if (filtered.length === 0) {
                  return (
                    <div style={{ padding: '12px', color: '#6b7280', fontSize: '13px', textAlign: 'center' }}>
                      No status changes available from {statusDropdown.currentStage || 'this stage'}
                    </div>
                  );
                }

                return filtered.map((status) => (
                  <button
                    key={status}
                    className={`status-dropdown-option status-${getStatusColor(status)}`}
                    onClick={() => handleStatusChange(status)}
                  >
                    {status}
                  </button>
                ));
              })()}
            </div>
          </div>
        </>
      )}
      </div>
      <CalendarSidebar />
    </div>
  );
}

export default Leads;
