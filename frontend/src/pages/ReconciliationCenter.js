import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import './ReconciliationCenter.css';

function ReconciliationCenter() {
  const [activeTab, setActiveTab] = useState('pending'); // 'pending', 'pendingReview', or 'completed'
  const [pendingItems, setPendingItems] = useState([]);
  const [pendingReviewItems, setPendingReviewItems] = useState([]);
  const [completedItems, setCompletedItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedItem, setSelectedItem] = useState(null);
  const [editedFields, setEditedFields] = useState({});
  const [processingAction, setProcessingAction] = useState(false);
  const [syncingEmails, setSyncingEmails] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState(null);
  const [syncStatus, setSyncStatus] = useState('');
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [selectedReviewItems, setSelectedReviewItems] = useState(new Set());
  const [bulkProcessing, setBulkProcessing] = useState(false);
  const [approvalProgress, setApprovalProgress] = useState({ approved: 0, total: 20 });
  const [delegateToAI, setDelegateToAI] = useState(false);

  // No-match dialog state
  const [showNoMatchDialog, setShowNoMatchDialog] = useState(false);
  const [noMatchItemId, setNoMatchItemId] = useState(null);
  const [noMatchData, setNoMatchData] = useState(null);
  const [newBorrowerForm, setNewBorrowerForm] = useState({
    first_name: '',
    last_name: '',
    referral_partner_id: '',
    loan_stage: 'PROCESSING'
  });
  const [referralPartners, setReferralPartners] = useState([]);

  // Referral partner search state
  const [referralSearchTerm, setReferralSearchTerm] = useState('');
  const [referralSearchResults, setReferralSearchResults] = useState([]);
  const [showReferralDropdown, setShowReferralDropdown] = useState(false);
  const [selectedReferralPartner, setSelectedReferralPartner] = useState(null);
  const [showCreateReferralDialog, setShowCreateReferralDialog] = useState(false);
  const [newReferralPartner, setNewReferralPartner] = useState({
    name: '',
    company_name: '',
    email: '',
    phone: '',
    type: 'realtor'
  });

  // Entity type selection state
  const [selectedEntityType, setSelectedEntityType] = useState(null); // 'loan' or 'lead'
  const [selectedLoanStage, setSelectedLoanStage] = useState('UW_RECEIVED');
  const [createNewLoan, setCreateNewLoan] = useState(false);

  // Loan stages for dropdown
  const loanStages = [
    { value: 'DISCLOSED', label: 'Disclosed' },
    { value: 'PROCESSING', label: 'Processing' },
    { value: 'SUBMITTED', label: 'Submitted' },
    { value: 'UW_RECEIVED', label: 'Underwriting Received' },
    { value: 'APPROVED', label: 'Approved' },
    { value: 'CTC', label: 'Clear to Close' },
    { value: 'DOCS', label: 'Docs Out' },
    { value: 'FUNDED', label: 'Funded' }
  ];

  useEffect(() => {
    fetchPendingItems();
    fetchCompletedItems();
    fetchReferralPartners();
    // Note: loadSampleData() removed - was overwriting real API data with samples

    // Auto-sync emails every 5 minutes
    const syncInterval = setInterval(() => {
      syncEmails(true); // silent sync
    }, 5 * 60 * 1000); // 5 minutes

    // Initial sync on load
    syncEmails(true);

    return () => clearInterval(syncInterval);
  }, []);

  const fetchReferralPartners = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/referral-partners`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setReferralPartners(data.partners || data || []);
      }
    } catch (error) {
      console.error('Error fetching referral partners:', error);
    }
  };

  // Search referral partners as user types
  const searchReferralPartners = (searchTerm) => {
    setReferralSearchTerm(searchTerm);
    if (!searchTerm.trim()) {
      setReferralSearchResults([]);
      setShowReferralDropdown(false);
      return;
    }

    const searchLower = searchTerm.toLowerCase();
    const results = referralPartners.filter(partner => {
      const name = (partner.name || '').toLowerCase();
      const company = (partner.company_name || '').toLowerCase();
      return name.includes(searchLower) || company.includes(searchLower);
    });

    setReferralSearchResults(results);
    setShowReferralDropdown(true);
  };

  // Select a referral partner from search results
  const selectReferralPartner = (partner) => {
    setSelectedReferralPartner(partner);
    setNewBorrowerForm(prev => ({ ...prev, referral_partner_id: partner.id }));
    setReferralSearchTerm(partner.name || partner.company_name || '');
    setShowReferralDropdown(false);
  };

  // Clear referral partner selection
  const clearReferralPartner = () => {
    setSelectedReferralPartner(null);
    setNewBorrowerForm(prev => ({ ...prev, referral_partner_id: '' }));
    setReferralSearchTerm('');
    setReferralSearchResults([]);
  };

  // Create new referral partner
  const handleCreateReferralPartner = async () => {
    if (!newReferralPartner.name.trim()) {
      alert('Please enter a name for the referral partner');
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/referral-partners`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(newReferralPartner)
      });

      if (response.ok) {
        const created = await response.json();
        // Add to local list and select it
        setReferralPartners(prev => [...prev, created]);
        selectReferralPartner(created);
        setShowCreateReferralDialog(false);
        setNewReferralPartner({ name: '', company_name: '', email: '', phone: '', type: 'realtor' });
      } else {
        const error = await response.json();
        alert(`Failed to create referral partner: ${error.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error creating referral partner:', error);
      alert('Error creating referral partner');
    }
  };

  const fetchPendingItems = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/pending`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        const allItems = data.items || [];

        // Split items: high confidence goes to auto-processing, low confidence needs review
        const autoProcess = [];
        const needsReview = [];

        allItems.forEach(item => {
          // Items with low confidence or specific flags go to pending review
          if (item.ai_confidence < 0.75 || item.match_confidence < 0.65 || item.status === 'needs_review') {
            needsReview.push({
              ...item,
              needs_human_review: true,
              review_reason: item.ai_confidence < 0.75 ? 'Low AI confidence' :
                            item.match_confidence < 0.65 ? 'Low match confidence' :
                            'Flagged for review',
              email_subject: item.email?.subject,
              email_from: item.email?.sender,
              email_received_at: item.email?.received_at,
              email_body: item.email?.body || item.email?.text_content || item.email?.html_content
            });
          } else {
            autoProcess.push(item);
          }
        });

        setPendingItems(autoProcess);
        setPendingReviewItems(needsReview);
      }
    } catch (error) {
      console.error('Error fetching pending items:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchCompletedItems = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/completed?limit=50`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setCompletedItems(data.items || []);
      }
    } catch (error) {
      console.error('Error fetching completed items:', error);
    }
  };

  const syncEmails = async (silent = false) => {
    try {
      if (!silent) {
        setSyncingEmails(true);
        setSyncStatus('Syncing emails...');
      }

      const token = localStorage.getItem('token');

      // Check which email service is connected
      const gmailStatus = await fetch(`${API_BASE_URL}/api/v1/gmail/status`, {
        headers: { 'Authorization': `Bearer ${token}` }
      }).then(r => r.ok ? r.json() : null).catch(() => null);

      const microsoftStatus = await fetch(`${API_BASE_URL}/api/v1/microsoft/status`, {
        headers: { 'Authorization': `Bearer ${token}` }
      }).then(r => r.ok ? r.json() : null).catch(() => null);

      let response;
      let syncEndpoint;

      if (gmailStatus?.connected) {
        // Use Gmail sync
        syncEndpoint = `${API_BASE_URL}/api/v1/gmail/sync`;
        response = await fetch(syncEndpoint, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        });
      } else if (microsoftStatus?.connected) {
        // Use Microsoft sync
        syncEndpoint = `${API_BASE_URL}/api/v1/microsoft/sync-now`;
        response = await fetch(syncEndpoint, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        });
      } else {
        // No email service connected
        if (!silent) {
          setSyncStatus('⚠ No email service connected. Go to Settings to connect Gmail or Microsoft 365.');
          setTimeout(() => setSyncStatus(''), 5000);
        }
        return;
      }

      if (response.ok) {
        const data = await response.json();
        setLastSyncTime(new Date());

        if (!silent) {
          const count = data.processed_count || data.synced_count || 0;
          setSyncStatus(`✓ Synced ${count} emails successfully`);
          // Refresh both pending and completed items to show new data
          fetchPendingItems();
          fetchCompletedItems();

          // Clear status after 3 seconds
          setTimeout(() => setSyncStatus(''), 3000);
        }
      } else {
        if (!silent) {
          // Try to get specific error message
          let errorMessage = '⚠ Sync failed - please try again';
          try {
            const errorData = await response.json();
            if (response.status === 404 && errorData.detail) {
              // Not connected error
              errorMessage = `⚠ ${errorData.detail}. Go to Settings to reconnect.`;
            } else if (errorData.detail) {
              errorMessage = `⚠ ${errorData.detail}`;
            }
          } catch (e) {
            // Use default error message
          }
          setSyncStatus(errorMessage);
          setTimeout(() => setSyncStatus(''), 5000);
        }
      }
    } catch (error) {
      console.error('Error syncing emails:', error);
      if (!silent) {
        setSyncStatus('⚠ Sync failed - please try again');
        setTimeout(() => setSyncStatus(''), 3000);
      }
    } finally {
      if (!silent) {
        setSyncingEmails(false);
      }
    }
  };

  const handleApprove = async (itemId) => {
    try {
      setProcessingAction(true);

      // First check if there's a match
      const checkResponse = await fetch(`${API_BASE_URL}/api/v1/reconciliation/check-match/${itemId}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (checkResponse.ok) {
        const matchData = await checkResponse.json();

        if (!matchData.has_match) {
          // No match found - show dialog to create new borrower
          setNoMatchItemId(itemId);
          setNoMatchData(matchData);
          setNewBorrowerForm({
            first_name: matchData.extracted_name?.split(' ')[0] || '',
            last_name: matchData.extracted_name?.split(' ').slice(1).join(' ') || '',
            referral_partner_id: ''
          });
          setShowNoMatchDialog(true);
          setProcessingAction(false);
          return;
        }
      }

      // Has match or check failed - proceed with normal approval
      await proceedWithApproval(itemId);
    } catch (error) {
      console.error('Error approving item:', error);
      alert(`Error approving item: ${error.message}`);
      setProcessingAction(false);
    }
  };

  const proceedWithApproval = async (itemId, options = {}) => {
    try {
      setProcessingAction(true);
      const corrections = Object.keys(editedFields).length > 0 ? editedFields : null;

      // Build request body with entity type options
      const requestBody = {
        extracted_data_id: itemId,
        corrections: corrections,
        delegate_to_ai: delegateToAI,
        email_intent: selectedItem?.email_intent,
        recommended_action: selectedItem?.recommended_action
      };

      // Add entity type override if user selected one
      if (options.targetEntityType || selectedEntityType) {
        requestBody.target_entity_type = options.targetEntityType || selectedEntityType;
      }

      // Add create new loan option
      if (options.createNewLoan || createNewLoan) {
        requestBody.create_new_loan = true;
        requestBody.loan_stage = options.loanStage || selectedLoanStage;
      }

      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      });

      if (response.ok) {
        // Remove from list and reset
        setPendingItems(prev => prev.filter(item => item.id !== itemId));
        setPendingReviewItems(prev => prev.filter(item => item.id !== itemId));
        setSelectedItem(null);
        setEditedFields({});
        setDelegateToAI(false);
        setSelectedEntityType(null);
        setCreateNewLoan(false);
        // Refresh completed items to show the newly approved item
        fetchCompletedItems();
      } else {
        const errorData = await response.json().catch(() => ({}));
        alert(`Failed to approve item: ${errorData.detail || response.statusText}`);
      }
    } catch (error) {
      console.error('Error approving item:', error);
      alert(`Error approving item: ${error.message}`);
    } finally {
      setProcessingAction(false);
    }
  };

  const handleCreateBorrower = async () => {
    try {
      setProcessingAction(true);

      // Validate form
      if (!newBorrowerForm.first_name || !newBorrowerForm.last_name) {
        alert('Please enter first name and last name');
        setProcessingAction(false);
        return;
      }

      const itemId = noMatchItemId;

      // Close dialog first
      setShowNoMatchDialog(false);
      setNoMatchItemId(null);
      setNoMatchData(null);

      // Add the borrower name to corrections if not already in extracted fields
      const corrections = {
        borrower_name: `${newBorrowerForm.first_name} ${newBorrowerForm.last_name}`
      };

      // Now approve with create_new_loan option and loan_stage
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          extracted_data_id: itemId,
          corrections: corrections,
          create_new_loan: true,
          loan_stage: newBorrowerForm.loan_stage,
          target_entity_type: 'loan'
        })
      });

      if (response.ok) {
        // Remove from list and reset
        setPendingItems(prev => prev.filter(item => item.id !== itemId));
        setPendingReviewItems(prev => prev.filter(item => item.id !== itemId));
        setSelectedItem(null);
        setEditedFields({});
        // Reset referral partner search state
        setReferralSearchTerm('');
        setSelectedReferralPartner(null);
        // Refresh completed items
        fetchCompletedItems();
      } else {
        const errorData = await response.json().catch(() => ({}));
        alert(`Failed to create borrower: ${errorData.detail || response.statusText}`);
      }
    } catch (error) {
      console.error('Error creating borrower:', error);
      alert(`Error creating borrower: ${error.message}`);
    } finally {
      setProcessingAction(false);
    }
  };

  const handleCancelNoMatch = () => {
    setShowNoMatchDialog(false);
    setNoMatchItemId(null);
    setNoMatchData(null);
    setProcessingAction(false);
    // Reset referral partner state
    setReferralSearchTerm('');
    setSelectedReferralPartner(null);
    setShowReferralDropdown(false);
  };

  const handleReject = async (itemId, reason) => {
    try {
      setProcessingAction(true);
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          extracted_data_id: itemId,
          reason: reason
        })
      });

      if (response.ok) {
        setPendingItems(prev => prev.filter(item => item.id !== itemId));
        setPendingReviewItems(prev => prev.filter(item => item.id !== itemId));
        setSelectedItem(null);
        setEditedFields({});
        // Refresh completed items to show the rejected item
        fetchCompletedItems();
      } else {
        const errorData = await response.json().catch(() => ({}));
        alert(`Failed to reject item: ${errorData.detail || response.statusText}`);
      }
    } catch (error) {
      console.error('Error rejecting item:', error);
      alert(`Error rejecting item: ${error.message}`);
    } finally {
      setProcessingAction(false);
    }
  };

  const handleFieldEdit = (fieldName, newValue) => {
    setEditedFields(prev => ({
      ...prev,
      [fieldName]: newValue
    }));
  };

  // Handle selecting an item - resets entity type selection
  const handleSelectItem = (item) => {
    setSelectedItem(item);
    setEditedFields({});
    // Reset entity type selection to show AI's suggestion
    setSelectedEntityType(null);
    setCreateNewLoan(false);
    setSelectedLoanStage('UW_RECEIVED');
  };

  const toggleItemSelection = (itemId) => {
    setSelectedItems(prev => {
      const newSet = new Set(prev);
      if (newSet.has(itemId)) {
        newSet.delete(itemId);
      } else {
        // Limit to 20 items
        if (newSet.size < 20) {
          newSet.add(itemId);
        }
      }
      return newSet;
    });
  };

  const selectAll = () => {
    const itemsToSelect = pendingItems.slice(0, 20).map(item => item.id);
    setSelectedItems(new Set(itemsToSelect));
  };

  const deselectAll = () => {
    setSelectedItems(new Set());
  };

  const bulkApprove = async () => {
    if (selectedItems.size === 0) {
      alert('Please select items to approve');
      return;
    }

    if (!window.confirm(`Approve ${selectedItems.size} loan updates?`)) {
      return;
    }

    setBulkProcessing(true);
    let successCount = 0;

    for (const itemId of selectedItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            extracted_data_id: itemId,
            corrections: null
          })
        });

        if (response.ok) {
          successCount++;
          setApprovalProgress(prev => ({
            ...prev,
            approved: prev.approved + 1
          }));
        }
      } catch (error) {
        console.error(`Error approving item ${itemId}:`, error);
      }
    }

    // Refresh the list
    await fetchPendingItems();

    // Clear selections
    setSelectedItems(new Set());
    setBulkProcessing(false);

    alert(`Successfully approved ${successCount} out of ${selectedItems.size} items`);
  };

  const bulkReject = async () => {
    if (selectedItems.size === 0) {
      alert('Please select items to reject');
      return;
    }

    const reason = prompt('Enter reason for rejection:');
    if (!reason) return;

    if (!window.confirm(`Reject ${selectedItems.size} loan updates?`)) {
      return;
    }

    setBulkProcessing(true);
    let successCount = 0;

    for (const itemId of selectedItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            extracted_data_id: itemId,
            reason: reason
          })
        });

        if (response.ok) {
          successCount++;
        }
      } catch (error) {
        console.error(`Error rejecting item ${itemId}:`, error);
      }
    }

    // Refresh the list
    await fetchPendingItems();

    // Clear selections
    setSelectedItems(new Set());
    setBulkProcessing(false);

    alert(`Successfully rejected ${successCount} out of ${selectedItems.size} items`);
  };

  // Pending Review bulk selection functions
  const toggleReviewItemSelection = (itemId) => {
    setSelectedReviewItems(prev => {
      const newSet = new Set(prev);
      if (newSet.has(itemId)) {
        newSet.delete(itemId);
      } else {
        newSet.add(itemId);
      }
      return newSet;
    });
  };

  const selectAllReviewItems = () => {
    const itemsToSelect = pendingReviewItems.map(item => item.id);
    setSelectedReviewItems(new Set(itemsToSelect));
  };

  const deselectAllReviewItems = () => {
    setSelectedReviewItems(new Set());
  };

  const bulkDeleteReviewItems = async () => {
    if (selectedReviewItems.size === 0) {
      alert('Please select items to delete');
      return;
    }

    if (!window.confirm(`Delete ${selectedReviewItems.size} pending review item(s)? This action cannot be undone.`)) {
      return;
    }

    setBulkProcessing(true);
    let successCount = 0;

    for (const itemId of selectedReviewItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            extracted_data_id: itemId,
            reason: 'Bulk deleted by user'
          })
        });

        if (response.ok) {
          successCount++;
        }
      } catch (error) {
        console.error(`Error deleting item ${itemId}:`, error);
      }
    }

    // Refresh the list
    await fetchPendingItems();

    // Clear selections
    setSelectedReviewItems(new Set());
    setBulkProcessing(false);

    alert(`Successfully deleted ${successCount} out of ${selectedReviewItems.size} items`);
  };

  const bulkApproveReviewItems = async () => {
    if (selectedReviewItems.size === 0) {
      alert('Please select items to approve');
      return;
    }

    if (!window.confirm(`Approve ${selectedReviewItems.size} item(s) and apply to matching records?`)) {
      return;
    }

    setBulkProcessing(true);
    let successCount = 0;

    for (const itemId of selectedReviewItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            extracted_data_id: itemId,
            corrections: null
          })
        });

        if (response.ok) {
          successCount++;
        }
      } catch (error) {
        console.error(`Error approving item ${itemId}:`, error);
      }
    }

    await fetchPendingItems();
    setSelectedReviewItems(new Set());
    setBulkProcessing(false);
    alert(`Successfully approved ${successCount} out of ${selectedReviewItems.size} items`);
  };

  const bulkBlockSenders = async () => {
    if (selectedReviewItems.size === 0) {
      alert('Please select items to block senders');
      return;
    }

    // Get unique senders from selected items
    const sendersToBlock = new Set();
    selectedReviewItems.forEach(itemId => {
      const item = pendingReviewItems.find(i => i.id === itemId);
      if (item?.email_from) {
        sendersToBlock.add(item.email_from);
      }
    });

    if (!window.confirm(`Block ${sendersToBlock.size} sender(s) and delete ${selectedReviewItems.size} item(s)?\n\nBlocked senders:\n${Array.from(sendersToBlock).join('\n')}\n\nFuture emails from these senders will be automatically ignored.`)) {
      return;
    }

    setBulkProcessing(true);
    let successCount = 0;

    // Block each sender
    for (const sender of sendersToBlock) {
      try {
        await fetch(`${API_BASE_URL}/api/v1/reconciliation/block-sender`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ sender_email: sender })
        });
      } catch (error) {
        console.error(`Error blocking sender ${sender}:`, error);
      }
    }

    // Delete the selected items
    for (const itemId of selectedReviewItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            extracted_data_id: itemId,
            reason: 'Sender blocked by user'
          })
        });

        if (response.ok) {
          successCount++;
        }
      } catch (error) {
        console.error(`Error deleting item ${itemId}:`, error);
      }
    }

    await fetchPendingItems();
    setSelectedReviewItems(new Set());
    setBulkProcessing(false);
    alert(`Blocked ${sendersToBlock.size} sender(s) and deleted ${successCount} items`);
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.85) return '#10b981'; // green
    if (confidence >= 0.65) return '#f59e0b'; // orange
    return '#ef4444'; // red
  };

  const getConfidenceBadge = (confidence) => {
    if (confidence >= 0.85) return 'HIGH';
    if (confidence >= 0.65) return 'MEDIUM';
    return 'LOW';
  };

  const formatFieldName = (fieldName) => {
    return fieldName
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const extractNameFromEmail = (email) => {
    // Extract name from email address (e.g., robert.w@example.com -> Robert W)
    if (!email) return 'Unknown';
    const namePart = email.split('@')[0];
    return namePart
      .split('.')
      .map(part => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');
  };

  const formatFieldValue = (fieldName, value) => {
    if (!value) return 'N/A';

    if (fieldName.includes('date')) {
      try {
        return new Date(value).toLocaleDateString();
      } catch {
        return value;
      }
    }

    if (fieldName === 'loan_amount' || fieldName === 'appraisal_value') {
      return `$${parseFloat(value).toLocaleString()}`;
    }

    if (fieldName === 'rate') {
      return `${value}%`;
    }

    return value;
  };

  if (loading) {
    return (
      <div className="reconciliation-page">
        <div className="reconciliation-container">
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Loading reconciliation items...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="reconciliation-page">
      <div className="reconciliation-container">
        <div className="reconciliation-header">
          <div className="header-content">
            <h1>Data Reconciliation Center</h1>
            <p>Review and approve AI-extracted loan data from emails</p>

            {/* Tab Navigation */}
            <div className="tab-navigation">
              <button
                className={`tab-button ${activeTab === 'pending' ? 'active' : ''}`}
                onClick={() => setActiveTab('pending')}
              >
                Auto-Processing ({pendingItems.length})
              </button>
              <button
                className={`tab-button ${activeTab === 'pendingReview' ? 'active' : ''}`}
                onClick={() => setActiveTab('pendingReview')}
              >
                Pending Review ({pendingReviewItems.length})
              </button>
              <button
                className={`tab-button ${activeTab === 'completed' ? 'active' : ''}`}
                onClick={() => setActiveTab('completed')}
              >
                Completed ({completedItems.length})
              </button>
            </div>
          </div>
          <div className="header-actions">
            <button
              className={`sync-button ${syncingEmails ? 'syncing' : ''}`}
              onClick={() => syncEmails(false)}
              disabled={syncingEmails}
            >
              {syncingEmails ? (
                <>
                  <span className="spinner-small"></span>
                  Syncing...
                </>
              ) : (
                <>
                  <span className="sync-icon">⟳</span>
                  Sync Emails Now
                </>
              )}
            </button>
            {syncStatus && (
              <div className={`sync-status ${syncStatus.includes('✓') ? 'success' : 'error'}`}>
                {syncStatus}
              </div>
            )}
            {lastSyncTime && !syncStatus && (
              <div className="last-sync">
                Last synced: {lastSyncTime.toLocaleTimeString()}
              </div>
            )}
          </div>
        </div>

        {/* Bulk Actions Bar - only show for pending tab */}
        {activeTab === 'pending' && pendingItems.length > 0 && (
          <div className="bulk-actions-bar">
            <div className="bulk-controls">
              <button
                className="btn-select-all"
                onClick={selectAll}
                disabled={pendingItems.length === 0}
              >
                Select All (20)
              </button>
              <button
                className="btn-deselect"
                onClick={deselectAll}
                disabled={selectedItems.size === 0}
              >
                Deselect All
              </button>
              <span className="selection-count">
                {selectedItems.size} item{selectedItems.size !== 1 ? 's' : ''} selected
              </span>
            </div>
            <div className="bulk-buttons">
              <button
                className="btn-bulk-approve"
                onClick={bulkApprove}
                disabled={selectedItems.size === 0 || bulkProcessing}
              >
                {bulkProcessing ? (
                  <>
                    <span className="spinner-small"></span>
                    Processing...
                  </>
                ) : (
                  <>
                    ✓ Approve Selected ({selectedItems.size})
                  </>
                )}
              </button>
              <button
                className="btn-bulk-reject"
                onClick={bulkReject}
                disabled={selectedItems.size === 0 || bulkProcessing}
              >
                ✕ Reject Selected
              </button>
            </div>
          </div>
        )}

        {/* Pending Tab Content */}
        {activeTab === 'pending' && pendingItems.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">✓</div>
            <h2>All Caught Up!</h2>
            <p>No pending reconciliation items. The AI will notify you when new data arrives.</p>
          </div>
        ) : activeTab === 'pending' && pendingItems.length > 0 ? (
          <div className="reconciliation-content">
            {/* Items List */}
            <div className="items-list">
              {pendingItems.slice(0, 20).map((item) => (
                <div
                  key={item.id}
                  className={`reconciliation-item ${selectedItem?.id === item.id ? 'selected' : ''} ${selectedItems.has(item.id) ? 'checked' : ''}`}
                >
                  <div className="item-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedItems.has(item.id)}
                      onChange={(e) => {
                        e.stopPropagation();
                        toggleItemSelection(item.id);
                      }}
                      disabled={!selectedItems.has(item.id) && selectedItems.size >= 20}
                    />
                  </div>
                  <div className="item-content" onClick={() => handleSelectItem(item)}>
                    <div className="item-header">
                      <div className="item-category">
                        {item.category?.toUpperCase() || 'UNKNOWN'}
                      </div>
                      <div
                        className="confidence-badge"
                        style={{ backgroundColor: getConfidenceColor(item.ai_confidence) }}
                      >
                        {getConfidenceBadge(item.ai_confidence)}
                      </div>
                    </div>
                  <div className="item-subject">{item.email?.subject}</div>
                  <div className="item-meta">
                    <span className="meta-sender">From: {item.email?.sender}</span>
                    <span className="meta-date">
                      {new Date(item.email?.received_at).toLocaleDateString()}
                    </span>
                  </div>
                  {item.match_entity_type && (
                    <div className="item-match">
                      Matched to: {item.match_entity_type} #{item.match_entity_id} (
                      {Math.round(item.match_confidence * 100)}%)
                    </div>
                  )}
                  </div>
                </div>
              ))}
            </div>

            {/* Detail Panel */}
            {selectedItem && (
              <div className="detail-panel">
                <div className="panel-header">
                  <h2>Review Extracted Data</h2>
                  <button
                    className="close-panel"
                    onClick={() => {
                      setSelectedItem(null);
                      setEditedFields({});
                    }}
                  >
                    ✕
                  </button>
                </div>

                <div className="email-context">
                  <h3>Email Context</h3>
                  <div className="context-field">
                    <strong>Subject:</strong> {selectedItem.email?.subject}
                  </div>
                  <div className="context-field">
                    <strong>From:</strong> {selectedItem.email?.sender}
                  </div>
                  <div className="context-field">
                    <strong>Received:</strong>{' '}
                    {new Date(selectedItem.email?.received_at).toLocaleString()}
                  </div>
                </div>

                {/* Entity Match Info */}
                {selectedItem.match_entity_type && selectedItem.match_entity_id && (
                  <div className="entity-match-section">
                    <h3>Matched Profile</h3>
                    <div className="entity-match-card">
                      <div className="entity-icon">
                        {selectedItem.match_entity_type === 'lead' ? '👤' :
                         selectedItem.match_entity_type === 'active_loan' ? '🏠' :
                         selectedItem.match_entity_type === 'client' ? '👥' : '📋'}
                      </div>
                      <div className="entity-details">
                        <div className="entity-name">
                          {selectedItem.match_entity_name || `${selectedItem.match_entity_type} #${selectedItem.match_entity_id}`}
                        </div>
                        <div className="entity-type">
                          {selectedItem.match_entity_type === 'active_loan' ? 'Active Loan' :
                           selectedItem.match_entity_type === 'lead' ? 'Lead' :
                           selectedItem.match_entity_type === 'client' ? 'Client' :
                           selectedItem.match_entity_type}
                        </div>
                        <div className="entity-confidence">
                          Match Confidence: {Math.round(selectedItem.match_confidence * 100)}%
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Email Intent Classification */}
                {selectedItem.email_intent && (
                  <div className="email-intent-section">
                    <h3>Email Type Detected</h3>
                    <div className="intent-card">
                      <div className="intent-badge">
                        {selectedItem.email_intent}
                      </div>
                      {selectedItem.email_intent_description && (
                        <div className="intent-description">
                          {selectedItem.email_intent_description}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Recommended Action */}
                {selectedItem.recommended_action && (
                  <div className="recommended-action-section">
                    <h3>AI Recommendation</h3>
                    <div className="recommendation-card">
                      <div className="recommendation-icon">💡</div>
                      <div className="recommendation-content">
                        <div className="recommendation-title">
                          {selectedItem.recommended_action.title || 'Suggested Action'}
                        </div>
                        <div className="recommendation-description">
                          {selectedItem.recommended_action.description}
                        </div>
                        {selectedItem.recommended_action.learning_status && (
                          <div className="learning-status">
                            🧠 AI Learning: {selectedItem.recommended_action.learning_status}
                          </div>
                        )}
                        <div className="ai-delegation-option">
                          <label className="delegation-checkbox">
                            <input
                              type="checkbox"
                              checked={delegateToAI}
                              onChange={(e) => setDelegateToAI(e.target.checked)}
                            />
                            <span className="delegation-label">
                              ✓ Let AI handle this task type automatically in the future
                            </span>
                          </label>
                          {delegateToAI && (
                            <div className="delegation-notice">
                              When you approve, AI will automatically handle "{selectedItem.email_intent}" emails going forward. You can revoke this in Mission Control.
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <div className="extracted-fields">
                  <h3>Extracted Fields</h3>
                  <div className="fields-grid">
                    {Object.entries(selectedItem.fields || {}).map(([fieldName, fieldData]) => {
                      const confidence = fieldData.confidence || 0;
                      const value = fieldData.value;
                      const isEdited = fieldName in editedFields;
                      const displayValue = isEdited
                        ? editedFields[fieldName]
                        : formatFieldValue(fieldName, value);

                      return (
                        <div key={fieldName} className="field-row">
                          <div className="field-label">
                            <span>{formatFieldName(fieldName)}</span>
                            <span
                              className="field-confidence"
                              style={{ color: getConfidenceColor(confidence) }}
                            >
                              {Math.round(confidence * 100)}%
                            </span>
                          </div>
                          <input
                            type="text"
                            className={`field-input ${isEdited ? 'edited' : ''}`}
                            value={isEdited ? editedFields[fieldName] : value || ''}
                            onChange={(e) => handleFieldEdit(fieldName, e.target.value)}
                          />
                        </div>
                      );
                    })}
                  </div>
                </div>

                {Object.keys(editedFields).length > 0 && (
                  <div className="corrections-notice">
                    <strong>Note:</strong> {Object.keys(editedFields).length} field(s) edited.
                    The AI will learn from your corrections.
                  </div>
                )}

                <div className="action-buttons">
                  <button
                    className="btn-approve"
                    onClick={() => handleApprove(selectedItem.id)}
                    disabled={processingAction}
                  >
                    {processingAction ? 'Processing...' : 'Approve & Apply'}
                  </button>
                  <button
                    className="btn-reject"
                    onClick={() => {
                      const reason = prompt('Reason for rejection (optional):');
                      if (reason !== null) {
                        handleReject(selectedItem.id, reason);
                      }
                    }}
                    disabled={processingAction}
                  >
                    Reject
                  </button>
                </div>

                <div className="ai-info">
                  <div className="info-row">
                    <strong>AI Confidence:</strong>
                    <span style={{ color: getConfidenceColor(selectedItem.ai_confidence) }}>
                      {Math.round(selectedItem.ai_confidence * 100)}%
                    </span>
                  </div>
                  {selectedItem.match_entity_type && (
                    <div className="info-row">
                      <strong>Entity Match:</strong>
                      <span>
                        {selectedItem.match_entity_type} #{selectedItem.match_entity_id} (
                        {Math.round(selectedItem.match_confidence * 100)}%)
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : null}

        {/* Pending Review Tab Content */}
        {activeTab === 'pendingReview' && pendingReviewItems.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">✓</div>
            <h2>All Reviewed!</h2>
            <p>No items pending review. Items flagged by AI for manual review will appear here.</p>
          </div>
        ) : null}

        {/* Bulk Actions Bar for Pending Review - Outside reconciliation-content */}
        {activeTab === 'pendingReview' && pendingReviewItems.length > 0 && (
          <div className="bulk-actions-bar">
            <div className="selection-controls">
              <button
                className="select-btn"
                onClick={selectedReviewItems.size === pendingReviewItems.length ? deselectAllReviewItems : selectAllReviewItems}
              >
                {selectedReviewItems.size === pendingReviewItems.length ? '☐ Deselect All' : '☑ Select All'}
              </button>
              <span className="selection-count">
                {selectedReviewItems.size} of {pendingReviewItems.length} selected
              </span>
            </div>
            <div className="bulk-action-buttons">
              <button
                className="btn-success"
                onClick={bulkApproveReviewItems}
                disabled={selectedReviewItems.size === 0 || bulkProcessing}
              >
                ✓ Approve ({selectedReviewItems.size})
              </button>
              <button
                className="btn-warning"
                onClick={bulkBlockSenders}
                disabled={selectedReviewItems.size === 0 || bulkProcessing}
              >
                🚫 Block Sender ({selectedReviewItems.size})
              </button>
              <button
                className="btn-danger"
                onClick={bulkDeleteReviewItems}
                disabled={selectedReviewItems.size === 0 || bulkProcessing}
              >
                🗑️ Delete ({selectedReviewItems.size})
              </button>
            </div>
          </div>
        )}

        {activeTab === 'pendingReview' && pendingReviewItems.length > 0 ? (
          <div className="reconciliation-content">
            {/* Pending Review Items List */}
            <div className="items-list">
              {/* Select All Header */}
              <div className="select-all-header">
                <input
                  type="checkbox"
                  className="item-checkbox"
                  checked={selectedReviewItems.size === pendingReviewItems.length && pendingReviewItems.length > 0}
                  onChange={() => {
                    if (selectedReviewItems.size === pendingReviewItems.length) {
                      deselectAllReviewItems();
                    } else {
                      selectAllReviewItems();
                    }
                  }}
                />
                <span className="select-all-label">
                  {selectedReviewItems.size === pendingReviewItems.length ? 'Deselect All' : 'Select All'} ({pendingReviewItems.length} items)
                </span>
              </div>
              {pendingReviewItems.map((item) => (
                <div
                  key={item.id}
                  className={`reconciliation-item ${selectedItem?.id === item.id ? 'selected' : ''} ${selectedReviewItems.has(item.id) ? 'checked' : ''}`}
                  onClick={() => handleSelectItem(item)}
                >
                  <input
                    type="checkbox"
                    className="item-checkbox"
                    checked={selectedReviewItems.has(item.id)}
                    onChange={() => toggleReviewItemSelection(item.id)}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <div className="item-content">
                    <div className="item-header">
                      <div className="item-category">
                        {item.email_intent || 'UNKNOWN'}
                      </div>
                      <div className="status-badge warning">
                        ⚠️ NEEDS REVIEW
                      </div>
                    </div>
                    <div className="item-subject">{item.email_subject}</div>
                    <div className="item-meta">
                      <span className="item-from">From: {item.email_from}</span>
                      <span className="item-date">
                        {new Date(item.email_received_at).toLocaleDateString()}
                      </span>
                    </div>
                    {item.email_body && (
                      <div className="item-body-preview">
                        {item.email_body.substring(0, 150)}{item.email_body.length > 150 ? '...' : ''}
                      </div>
                    )}
                    {item.review_reason && (
                      <div className="review-reason">
                        <strong>Reason:</strong> {item.review_reason}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Detail Panel for Pending Review - Matches Task Detail Layout */}
            {selectedItem && (
              <div className="item-detail-panel">
                <div className="detail-header">
                  <div className="detail-title-section">
                    <div className="detail-source">
                      <span className="source-icon-large">🎯</span>
                      <span className="source-name">MANUAL PRIORITY</span>
                    </div>
                    <h2 className="detail-title">{selectedItem.email_intent || 'Review Required'}</h2>
                  </div>
                  <button className="close-detail" onClick={() => setSelectedItem(null)}>×</button>
                </div>

                <div className="detail-body">
                  <div className="detail-info-grid">
                    <div className="detail-info-item">
                      <span className="detail-label">CLIENT</span>
                      <span className="detail-value">{selectedItem.fields?.borrower_name?.value || extractNameFromEmail(selectedItem.email_from)}</span>
                    </div>
                    <div className="detail-info-item">
                      <span className="detail-label">STAGE</span>
                      <span className="detail-value">{selectedItem.match_entity_type === 'lead' ? 'Pre-Approved' : selectedItem.match_entity_type === 'loan' ? 'Processing' : 'Client Retention'}</span>
                    </div>
                    <div className="detail-info-item">
                      <span className="detail-label">PRIORITY</span>
                      <span className="detail-urgency-badge priority-high">HIGH</span>
                    </div>
                    <div className="detail-info-item">
                      <span className="detail-label">SOURCE</span>
                      <span className="detail-value">Manual Priority</span>
                    </div>
                    <div className="detail-info-item">
                      <span className="detail-label">OWNER</span>
                      <span className="detail-value">Loan Officer</span>
                    </div>
                    <div className="detail-info-item">
                      <span className="detail-label">DATE CREATED</span>
                      <span className="detail-value">
                        {new Date(selectedItem.email_received_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="detail-info-item detail-comm-method-item">
                      <span className="detail-label">SEND VIA</span>
                      <div className="comm-method-selector">
                        <button className="comm-method-btn active">
                          📧 Email
                        </button>
                        <button className="comm-method-btn">
                          💬 Text
                        </button>
                        <button className="comm-method-btn">
                          📞 Phone
                        </button>
                        <button className="comm-method-btn">
                          🎙️ Voicemail
                        </button>
                      </div>
                    </div>
                  </div>

                  {selectedItem.review_reason && (
                    <div className="review-alert-banner">
                      <div className="alert-icon">⚠️</div>
                      <div className="alert-content">
                        <strong>Flagged for Review:</strong> {selectedItem.review_reason}
                        <br />
                        <span className="match-confidence-text">
                          Match Confidence: <strong>{Math.round(selectedItem.match_confidence * 100)}%</strong>
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Entity Type Selection Section */}
                  <div className="entity-type-selection" style={{ marginBottom: '20px', padding: '15px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                    <h3 style={{ margin: '0 0 15px 0', fontSize: '14px', fontWeight: '600', color: '#374151' }}>
                      🎯 Where should this data go?
                    </h3>
                    <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
                      <button
                        onClick={() => { setSelectedEntityType('loan'); setCreateNewLoan(false); }}
                        style={{
                          flex: 1,
                          padding: '12px',
                          border: selectedEntityType === 'loan' ? '2px solid #3b82f6' : '1px solid #e5e7eb',
                          borderRadius: '8px',
                          background: selectedEntityType === 'loan' ? '#eff6ff' : 'white',
                          cursor: 'pointer',
                          fontWeight: selectedEntityType === 'loan' ? '600' : '400'
                        }}
                      >
                        📋 Active Loan
                        <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                          {selectedItem.match_entity_type === 'loan' && selectedItem.match_entity_name ?
                            `Match: ${selectedItem.match_entity_name}` : 'No match found'}
                        </div>
                      </button>
                      <button
                        onClick={() => { setSelectedEntityType('lead'); setCreateNewLoan(false); }}
                        style={{
                          flex: 1,
                          padding: '12px',
                          border: selectedEntityType === 'lead' ? '2px solid #10b981' : '1px solid #e5e7eb',
                          borderRadius: '8px',
                          background: selectedEntityType === 'lead' ? '#ecfdf5' : 'white',
                          cursor: 'pointer',
                          fontWeight: selectedEntityType === 'lead' ? '600' : '400'
                        }}
                      >
                        👤 Lead
                        <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                          {selectedItem.match_entity_type === 'lead' && selectedItem.match_entity_name ?
                            `Match: ${selectedItem.match_entity_name}` : 'No match found'}
                        </div>
                      </button>
                      <button
                        onClick={() => { setCreateNewLoan(true); setSelectedEntityType('loan'); }}
                        style={{
                          flex: 1,
                          padding: '12px',
                          border: createNewLoan ? '2px solid #8b5cf6' : '1px solid #e5e7eb',
                          borderRadius: '8px',
                          background: createNewLoan ? '#f5f3ff' : 'white',
                          cursor: 'pointer',
                          fontWeight: createNewLoan ? '600' : '400'
                        }}
                      >
                        ➕ Create New Loan
                        <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                          {selectedItem.fields?.loan_number?.value || 'Add to pipeline'}
                        </div>
                      </button>
                    </div>

                    {/* Loan Stage Selector - shows when creating new loan */}
                    {createNewLoan && (
                      <div style={{ marginTop: '15px', padding: '12px', background: 'white', borderRadius: '6px', border: '1px solid #e5e7eb' }}>
                        <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500', color: '#374151' }}>
                          Select Loan Stage:
                        </label>
                        <select
                          value={selectedLoanStage}
                          onChange={(e) => setSelectedLoanStage(e.target.value)}
                          style={{
                            width: '100%',
                            padding: '10px',
                            border: '1px solid #d1d5db',
                            borderRadius: '6px',
                            fontSize: '14px'
                          }}
                        >
                          {loanStages.map(stage => (
                            <option key={stage.value} value={stage.value}>{stage.label}</option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>

                  {/* Entity Match Section with Extracted Fields */}
                  <div className="extracted-fields-section">
                    <h3>Matched Entity</h3>
                    <div className="entity-match-info">
                      <div className="entity-type-badge" style={{
                        background: createNewLoan ? '#8b5cf6' :
                                   (selectedEntityType || selectedItem.match_entity_type) === 'loan' ? '#3b82f6' :
                                   '#10b981',
                        color: 'white',
                        padding: '4px 12px',
                        borderRadius: '9999px',
                        fontSize: '12px',
                        fontWeight: '500'
                      }}>
                        {createNewLoan ? '➕ New Loan' :
                         (selectedEntityType || selectedItem.match_entity_type) === 'lead' ? '👤 Lead' :
                         (selectedEntityType || selectedItem.match_entity_type) === 'loan' ? '📋 Loan' :
                         selectedItem.match_entity_type}
                      </div>
                      <div className="entity-confidence">
                        Match Confidence: <span style={{ color: getConfidenceColor(selectedItem.match_confidence) }}>
                          {createNewLoan ? 'N/A' : `${Math.round(selectedItem.match_confidence * 100)}%`}
                        </span>
                      </div>
                    </div>
                    <h4>EXTRACTED FIELDS</h4>
                    <div className="fields-grid-recon">
                      {Object.entries(selectedItem.fields || {}).map(([fieldName, fieldData]) => {
                        const confidence = fieldData.confidence || 0;
                        const value = fieldData.value;
                        const isEdited = fieldName in editedFields;

                        return (
                          <div key={fieldName} className="field-row-recon">
                            <div className="field-header-recon">
                              <span className="field-name">{formatFieldName(fieldName)}</span>
                              <span
                                className="field-confidence-badge"
                                style={{
                                  backgroundColor: confidence > 0.8 ? '#10b981' : confidence > 0.6 ? '#f59e0b' : '#ef4444',
                                  color: 'white'
                                }}
                              >
                                {Math.round(confidence * 100)}%
                              </span>
                            </div>
                            <div className="field-value-display">{value || 'N/A'}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Email Details Section - Full Email Display */}
                  <div className="email-details-section">
                    <h4>📧 Email Details</h4>
                    <div className="email-details-content" style={{ background: '#f9fafb', padding: '15px', borderRadius: '8px', marginTop: '10px' }}>
                      <div className="email-meta-row" style={{ marginBottom: '8px' }}>
                        <strong>From:</strong> {selectedItem.email_from}
                      </div>
                      <div className="email-meta-row" style={{ marginBottom: '8px' }}>
                        <strong>Subject:</strong> {selectedItem.email_subject}
                      </div>
                      <div className="email-meta-row" style={{ marginBottom: '8px' }}>
                        <strong>Received:</strong> {new Date(selectedItem.email_received_at).toLocaleString()}
                      </div>
                      <div className="email-body-section" style={{ marginTop: '15px', borderTop: '1px solid #e5e7eb', paddingTop: '15px' }}>
                        <strong>Email Body:</strong>
                        <div
                          className="email-body-content"
                          style={{
                            marginTop: '10px',
                            padding: '15px',
                            background: 'white',
                            border: '1px solid #e5e7eb',
                            borderRadius: '6px',
                            maxHeight: '400px',
                            overflowY: 'auto',
                            whiteSpace: 'pre-wrap',
                            fontFamily: 'monospace',
                            fontSize: '13px',
                            lineHeight: '1.5'
                          }}
                        >
                          {selectedItem.email_body || selectedItem.email?.body || selectedItem.email?.text_content || selectedItem.email?.html_content || 'No email body available'}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Action Buttons - Match Task Layout */}
                  <div className="detail-action-buttons">
                    <button
                      className="btn-approve-recon"
                      onClick={() => handleApprove(selectedItem.id)}
                      disabled={processingAction}
                    >
                      {processingAction ? 'Processing...' : '✓ APPROVE & CONTINUE'}
                    </button>
                    <button
                      className="btn-reject-recon"
                      onClick={() => {
                        const reason = prompt('Reason for rejection (optional):');
                        if (reason !== null) {
                          handleReject(selectedItem.id, reason);
                        }
                      }}
                      disabled={processingAction}
                    >
                      ✕ REJECT
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : null}

        {/* Completed Tab Content */}
        {activeTab === 'completed' && completedItems.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📋</div>
            <h2>No Completed Items</h2>
            <p>Approved and rejected reconciliation items will appear here.</p>
          </div>
        ) : activeTab === 'completed' && completedItems.length > 0 ? (
          <div className="reconciliation-content">
            {/* Completed Items List */}
            <div className="items-list">
              {completedItems.map((item) => (
                <div
                  key={item.id}
                  className={`reconciliation-item ${selectedItem?.id === item.id ? 'selected' : ''} ${item.status === 'rejected' ? 'rejected-item' : 'approved-item'}`}
                  onClick={() => handleSelectItem(item)}
                >
                  <div className="item-content">
                    <div className="item-header">
                      <div className="item-category">
                        {item.category?.toUpperCase() || 'UNKNOWN'}
                      </div>
                      <div className={`status-badge ${item.status === 'rejected' ? 'rejected' : 'approved'}`}>
                        {item.status === 'rejected' ? '✕ REJECTED' : '✓ APPROVED'}
                      </div>
                    </div>
                    <div className="item-subject">{item.email?.subject}</div>
                    <div className="item-meta">
                      <span className="meta-sender">From: {item.email?.sender}</span>
                      <span className="meta-date">
                        Reviewed: {item.reviewed_at ? new Date(item.reviewed_at).toLocaleDateString() : 'N/A'}
                      </span>
                      {item.reviewed_by && (
                        <span className="meta-reviewer">By: {item.reviewed_by}</span>
                      )}
                    </div>
                    {item.match_entity_type && (
                      <div className="item-match">
                        Applied to: {item.match_entity_type} #{item.match_entity_id}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Detail Panel for Completed Items - Read Only */}
            {selectedItem && (
              <div className="detail-panel">
                <div className="panel-header">
                  <h2>Completed Item Details</h2>
                  <button
                    className="close-panel"
                    onClick={() => setSelectedItem(null)}
                  >
                    ✕
                  </button>
                </div>

                <div className="email-context">
                  <h3>Email Context</h3>
                  <div className="context-field">
                    <strong>Subject:</strong> {selectedItem.email?.subject}
                  </div>
                  <div className="context-field">
                    <strong>From:</strong> {selectedItem.email?.sender}
                  </div>
                  <div className="context-field">
                    <strong>Received:</strong>{' '}
                    {new Date(selectedItem.email?.received_at).toLocaleString()}
                  </div>
                  <div className="context-field">
                    <strong>Status:</strong>{' '}
                    <span className={`status-text ${selectedItem.status}`}>
                      {selectedItem.status?.toUpperCase()}
                    </span>
                  </div>
                  {selectedItem.reviewed_at && (
                    <div className="context-field">
                      <strong>Reviewed:</strong>{' '}
                      {new Date(selectedItem.reviewed_at).toLocaleString()}
                      {selectedItem.reviewed_by && ` by ${selectedItem.reviewed_by}`}
                    </div>
                  )}
                </div>

                <div className="extracted-fields">
                  <h3>Extracted Fields (Read-Only)</h3>
                  <div className="fields-grid">
                    {Object.entries(selectedItem.fields || {}).map(([fieldName, fieldData]) => {
                      const confidence = fieldData.confidence || 0;
                      const value = fieldData.value;

                      return (
                        <div key={fieldName} className="field-row">
                          <div className="field-label">
                            <span>{formatFieldName(fieldName)}</span>
                            <span
                              className="field-confidence"
                              style={{ color: getConfidenceColor(confidence) }}
                            >
                              {Math.round(confidence * 100)}%
                            </span>
                          </div>
                          <input
                            type="text"
                            className="field-input"
                            value={value || ''}
                            readOnly
                            disabled
                          />
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="ai-info">
                  <div className="info-row">
                    <strong>AI Confidence:</strong>
                    <span style={{ color: getConfidenceColor(selectedItem.ai_confidence) }}>
                      {Math.round(selectedItem.ai_confidence * 100)}%
                    </span>
                  </div>
                  {selectedItem.match_entity_type && (
                    <div className="info-row">
                      <strong>Entity Match:</strong>
                      <span>
                        {selectedItem.match_entity_type} #{selectedItem.match_entity_id} (
                        {Math.round(selectedItem.match_confidence * 100)}%)
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </div>

      {/* No Match Dialog */}
      {showNoMatchDialog && (
        <div className="dialog-overlay">
          <div className="dialog-content no-match-dialog">
            <div className="dialog-header">
              <h3>No Matching Borrower Found</h3>
              <button className="dialog-close" onClick={handleCancelNoMatch}>&times;</button>
            </div>
            <div className="dialog-body">
              <p>No existing borrower profile matches this extracted data. Would you like to create a new borrower?</p>

              {noMatchData?.fields && (
                <div className="extracted-summary">
                  <h4>Extracted Information:</h4>
                  <ul>
                    {Object.entries(noMatchData.fields).map(([key, fieldData]) => {
                      // fieldData is an object like {value: "...", confidence: 0.95}
                      const displayValue = typeof fieldData === 'object' ? fieldData.value : fieldData;
                      return displayValue && <li key={key}><strong>{formatFieldName(key)}:</strong> {displayValue}</li>;
                    })}
                  </ul>
                </div>
              )}

              <div className="new-borrower-form">
                <h4>New Borrower Details:</h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
                  <div className="form-group">
                    <label>First Name *</label>
                    <input
                      type="text"
                      value={newBorrowerForm.first_name}
                      onChange={(e) => setNewBorrowerForm(prev => ({ ...prev, first_name: e.target.value }))}
                      placeholder="Enter first name"
                      required
                      style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                    />
                  </div>
                  <div className="form-group">
                    <label>Last Name *</label>
                    <input
                      type="text"
                      value={newBorrowerForm.last_name}
                      onChange={(e) => setNewBorrowerForm(prev => ({ ...prev, last_name: e.target.value }))}
                      placeholder="Enter last name"
                      required
                      style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                    />
                  </div>
                </div>

                {/* Loan Stage Selector */}
                <div className="form-group" style={{ marginTop: '15px' }}>
                  <label style={{ fontWeight: '600', marginBottom: '8px', display: 'block' }}>
                    Loan Stage *
                  </label>
                  <select
                    value={newBorrowerForm.loan_stage}
                    onChange={(e) => setNewBorrowerForm(prev => ({ ...prev, loan_stage: e.target.value }))}
                    style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '14px' }}
                  >
                    {loanStages.map(stage => (
                      <option key={stage.value} value={stage.value}>{stage.label}</option>
                    ))}
                  </select>
                </div>

                {/* Searchable Referral Partner */}
                <div className="form-group" style={{ marginTop: '15px', position: 'relative' }}>
                  <label style={{ fontWeight: '600', marginBottom: '8px', display: 'block' }}>
                    Referral Partner
                  </label>
                  <div style={{ position: 'relative' }}>
                    <input
                      type="text"
                      value={referralSearchTerm}
                      onChange={(e) => searchReferralPartners(e.target.value)}
                      onFocus={() => referralSearchTerm && setShowReferralDropdown(true)}
                      placeholder="Type to search referral partners..."
                      style={{
                        width: '100%',
                        padding: '10px',
                        paddingRight: selectedReferralPartner ? '35px' : '10px',
                        border: '1px solid #d1d5db',
                        borderRadius: '6px',
                        fontSize: '14px'
                      }}
                    />
                    {selectedReferralPartner && (
                      <button
                        onClick={clearReferralPartner}
                        style={{
                          position: 'absolute',
                          right: '10px',
                          top: '50%',
                          transform: 'translateY(-50%)',
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          fontSize: '16px',
                          color: '#6b7280'
                        }}
                      >
                        ✕
                      </button>
                    )}
                  </div>

                  {/* Search Results Dropdown */}
                  {showReferralDropdown && (
                    <div style={{
                      position: 'absolute',
                      top: '100%',
                      left: 0,
                      right: 0,
                      background: 'white',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      maxHeight: '200px',
                      overflowY: 'auto',
                      zIndex: 1000,
                      boxShadow: '0 4px 6px rgba(0,0,0,0.1)'
                    }}>
                      {referralSearchResults.length > 0 ? (
                        referralSearchResults.map(partner => (
                          <div
                            key={partner.id}
                            onClick={() => selectReferralPartner(partner)}
                            style={{
                              padding: '10px 15px',
                              cursor: 'pointer',
                              borderBottom: '1px solid #f3f4f6',
                              transition: 'background 0.2s'
                            }}
                            onMouseEnter={(e) => e.target.style.background = '#f3f4f6'}
                            onMouseLeave={(e) => e.target.style.background = 'white'}
                          >
                            <div style={{ fontWeight: '500' }}>{partner.name}</div>
                            {partner.company_name && (
                              <div style={{ fontSize: '12px', color: '#6b7280' }}>{partner.company_name}</div>
                            )}
                            {partner.type && (
                              <span style={{
                                fontSize: '11px',
                                background: '#e5e7eb',
                                padding: '2px 8px',
                                borderRadius: '9999px',
                                marginTop: '4px',
                                display: 'inline-block'
                              }}>
                                {partner.type}
                              </span>
                            )}
                          </div>
                        ))
                      ) : (
                        <div style={{ padding: '15px', textAlign: 'center' }}>
                          <p style={{ color: '#6b7280', margin: '0 0 10px 0' }}>
                            No matching partners found
                          </p>
                          <button
                            onClick={() => {
                              setNewReferralPartner(prev => ({ ...prev, name: referralSearchTerm }));
                              setShowCreateReferralDialog(true);
                              setShowReferralDropdown(false);
                            }}
                            style={{
                              background: '#3b82f6',
                              color: 'white',
                              border: 'none',
                              padding: '8px 16px',
                              borderRadius: '6px',
                              cursor: 'pointer',
                              fontSize: '13px'
                            }}
                          >
                            + Add "{referralSearchTerm}" as new partner
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {selectedReferralPartner && (
                    <div style={{
                      marginTop: '8px',
                      padding: '8px 12px',
                      background: '#ecfdf5',
                      borderRadius: '6px',
                      fontSize: '13px',
                      color: '#059669'
                    }}>
                      ✓ Selected: {selectedReferralPartner.name}
                      {selectedReferralPartner.company_name && ` (${selectedReferralPartner.company_name})`}
                    </div>
                  )}
                </div>
              </div>
            </div>
            <div className="dialog-footer">
              <button className="btn btn-secondary" onClick={handleCancelNoMatch}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleCreateBorrower}
                disabled={processingAction || !newBorrowerForm.first_name || !newBorrowerForm.last_name}
              >
                {processingAction ? 'Creating...' : 'Create Borrower & Approve'}
              </button>
            </div>
          </div>

          {/* Create New Referral Partner Dialog */}
          {showCreateReferralDialog && (
            <div style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: 'rgba(0,0,0,0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 2000
            }}>
              <div style={{
                background: 'white',
                borderRadius: '12px',
                width: '450px',
                maxWidth: '90%',
                boxShadow: '0 25px 50px rgba(0,0,0,0.25)'
              }}>
                <div style={{
                  padding: '20px',
                  borderBottom: '1px solid #e5e7eb',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}>
                  <h3 style={{ margin: 0, fontSize: '18px' }}>Add New Referral Partner</h3>
                  <button
                    onClick={() => setShowCreateReferralDialog(false)}
                    style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: '#6b7280' }}
                  >
                    &times;
                  </button>
                </div>
                <div style={{ padding: '20px' }}>
                  <div className="form-group" style={{ marginBottom: '15px' }}>
                    <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Name *</label>
                    <input
                      type="text"
                      value={newReferralPartner.name}
                      onChange={(e) => setNewReferralPartner(prev => ({ ...prev, name: e.target.value }))}
                      placeholder="Full name"
                      style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                    />
                  </div>
                  <div className="form-group" style={{ marginBottom: '15px' }}>
                    <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Company</label>
                    <input
                      type="text"
                      value={newReferralPartner.company_name}
                      onChange={(e) => setNewReferralPartner(prev => ({ ...prev, company_name: e.target.value }))}
                      placeholder="Company name (optional)"
                      style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                    />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginBottom: '15px' }}>
                    <div className="form-group">
                      <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Email</label>
                      <input
                        type="email"
                        value={newReferralPartner.email}
                        onChange={(e) => setNewReferralPartner(prev => ({ ...prev, email: e.target.value }))}
                        placeholder="Email (optional)"
                        style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                      />
                    </div>
                    <div className="form-group">
                      <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Phone</label>
                      <input
                        type="tel"
                        value={newReferralPartner.phone}
                        onChange={(e) => setNewReferralPartner(prev => ({ ...prev, phone: e.target.value }))}
                        placeholder="Phone (optional)"
                        style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                      />
                    </div>
                  </div>
                  <div className="form-group">
                    <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Type</label>
                    <select
                      value={newReferralPartner.type}
                      onChange={(e) => setNewReferralPartner(prev => ({ ...prev, type: e.target.value }))}
                      style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                    >
                      <option value="realtor">Realtor</option>
                      <option value="builder">Builder</option>
                      <option value="financial_advisor">Financial Advisor</option>
                      <option value="attorney">Attorney</option>
                      <option value="cpa">CPA</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                </div>
                <div style={{
                  padding: '15px 20px',
                  borderTop: '1px solid #e5e7eb',
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: '10px'
                }}>
                  <button
                    onClick={() => setShowCreateReferralDialog(false)}
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
                    onClick={handleCreateReferralPartner}
                    disabled={!newReferralPartner.name.trim()}
                    style={{
                      padding: '10px 20px',
                      border: 'none',
                      borderRadius: '6px',
                      background: newReferralPartner.name.trim() ? '#3b82f6' : '#9ca3af',
                      color: 'white',
                      cursor: newReferralPartner.name.trim() ? 'pointer' : 'not-allowed'
                    }}
                  >
                    Create Partner
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ReconciliationCenter;
