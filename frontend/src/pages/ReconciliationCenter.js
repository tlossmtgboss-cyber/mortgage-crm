import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL, emailDraftsAPI } from '../services/api';
import { useLayoutFix } from '../hooks/useLayoutFix';
import { sanitizeHTML } from '../utils/sanitize';
import './ReconciliationCenter.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

function ReconciliationCenter() {
  const navigate = useNavigate();
  const { containerRef, triggerRecalculation } = useLayoutFix([]);
  const [activeTab, setActiveTab] = useState('new'); // 'new', 'autoProcessing', 'pendingReview', 'completed', or 'callDrafts'
  const [callDrafts, setCallDrafts] = useState([]);
  const [callDraftsLoading, setCallDraftsLoading] = useState(false);
  const [selectedDraft, setSelectedDraft] = useState(null);
  const [draftActionLoading, setDraftActionLoading] = useState(null);
  const [newItems, setNewItems] = useState([]); // Fresh unprocessed messages
  const [autoProcessingItems, setAutoProcessingItems] = useState([]); // AI handles automatically
  const [pendingReviewItems, setPendingReviewItems] = useState([]); // AI completed, user verifies
  const [completedItems, setCompletedItems] = useState([]);
  // Legacy alias for backwards compatibility
  const pendingItems = autoProcessingItems;
  const setPendingItems = setAutoProcessingItems;
  const [loading, setLoading] = useState(true);
  const [selectedItem, setSelectedItem] = useState(null);
  const [editedFields, setEditedFields] = useState({});
  const [deletedFields, setDeletedFields] = useState(new Set());
  const [renamedFields, setRenamedFields] = useState({}); // { oldKey: newKey }
  const [editingFieldKey, setEditingFieldKey] = useState(null); // currently editing field key
  const [showAddFieldForm, setShowAddFieldForm] = useState(false); // show add field form
  const [newFieldKey, setNewFieldKey] = useState(''); // new field key
  const [newFieldValue, setNewFieldValue] = useState(''); // new field value
  const [addedFields, setAddedFields] = useState({}); // { fieldKey: { value, confidence } }
  const [processingAction, setProcessingAction] = useState(false);
  const [syncingEmails, setSyncingEmails] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState(null);
  const [syncStatus, setSyncStatus] = useState('');
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [selectedReviewItems, setSelectedReviewItems] = useState(new Set());
  const [bulkProcessing, setBulkProcessing] = useState(false);
  const [approvalProgress, setApprovalProgress] = useState({ approved: 0, total: 20 });
  const [delegateToAI, setDelegateToAI] = useState(false);
  const [allowAutoProcess, setAllowAutoProcess] = useState(false); // Checkbox for "Allow AI to auto-process similar messages"

  // Email inbox deletion settings
  const [deleteFromInboxGlobal, setDeleteFromInboxGlobal] = useState(false); // Global setting from user preferences
  const [deleteFromInboxOverride, setDeleteFromInboxOverride] = useState(null); // Per-email override: true/false/null (null means use global)

  // No-match dialog state
  const [showNoMatchDialog, setShowNoMatchDialog] = useState(false);
  const [noMatchItemId, setNoMatchItemId] = useState(null);
  const [noMatchData, setNoMatchData] = useState(null);
  const [newBorrowerForm, setNewBorrowerForm] = useState({
    first_name: '',
    last_name: '',
    loan_number: '',
    referral_partner_id: '',
    loan_stage: 'NEW'
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
    company: '',
    email: '',
    phone: '',
    type: 'realtor'
  });

  // Entity type selection state
  const [selectedEntityType, setSelectedEntityType] = useState(null); // 'loan' or 'lead'
  const [selectedLoanStage, setSelectedLoanStage] = useState('UW_RECEIVED');
  const [createNewLoan, setCreateNewLoan] = useState(false);

  // Status correction modal state
  const [showStatusCorrectionModal, setShowStatusCorrectionModal] = useState(false);
  const [statusCorrectionData, setStatusCorrectionData] = useState(null);
  const [pendingApprovalItemId, setPendingApprovalItemId] = useState(null);
  const [selectedNewStatus, setSelectedNewStatus] = useState(null);

  // Applied data summary modal state
  const [showAppliedDataModal, setShowAppliedDataModal] = useState(false);
  const [appliedDataSummary, setAppliedDataSummary] = useState(null);

  // All stages for dropdown - Lead stages, Active Loan stages, and MUM/Portfolio stages
  const allStages = [
    // Lead Stages
    { value: 'NEW', label: 'New Lead', category: 'Lead' },
    { value: 'ATTEMPTED_CONTACT', label: 'Attempted Contact', category: 'Lead' },
    { value: 'PROSPECT', label: 'Prospect', category: 'Lead' },
    { value: 'APPLICATION', label: 'Application', category: 'Lead' },
    { value: 'APPLICATION_STARTED', label: 'Application Started', category: 'Lead' },
    { value: 'PRE_QUALIFIED', label: 'Pre-Qualified', category: 'Lead' },
    { value: 'PRE_APPROVED', label: 'Pre-Approved', category: 'Lead' },
    { value: 'UNDER_CONTRACT', label: 'Under Contract', category: 'Lead' },
    { value: 'LONG_TERM_NURTURE', label: 'Long-Term Nurture', category: 'Lead' },
    // Active Loan Stages
    { value: 'DISCLOSED', label: 'Disclosed', category: 'Active Loan' },
    { value: 'PROCESSING', label: 'Processing', category: 'Active Loan' },
    { value: 'UW_RECEIVED', label: 'Underwriting Received', category: 'Active Loan' },
    { value: 'APPROVED', label: 'Approved', category: 'Active Loan' },
    { value: 'CTC', label: 'Clear to Close', category: 'Active Loan' },
    { value: 'SUSPENDED', label: 'Suspended', category: 'Active Loan' },
    { value: 'FUNDED', label: 'Funded', category: 'Active Loan' },
    // MUM / Portfolio Stages
    { value: 'CLOSED', label: 'Closed (Portfolio)', category: 'MUM' },
    { value: 'AMR', label: 'Annual Mortgage Review', category: 'MUM' },
    { value: 'REFERRAL_SOURCE', label: 'Referral Source', category: 'MUM' },
    // Other
    { value: 'WITHDRAWN', label: 'Withdrawn', category: 'Other' },
    { value: 'DOES_NOT_QUALIFY', label: 'Does Not Qualify', category: 'Other' }
  ];

  // Keep loanStages for backwards compatibility in some places
  const loanStages = allStages;

  // Helper function to clean email preview text
  const cleanEmailPreview = (text) => {
    if (!text) return '';

    let cleaned = text
      // Remove URLs (http, https, www)
      .replace(/https?:\/\/[^\s<>"{}|\\^`[\]]+/gi, '')
      .replace(/www\.[^\s<>"{}|\\^`[\]]+/gi, '')
      // Remove image references and file paths
      .replace(/[^\s]+\.(png|jpg|jpeg|gif|svg|webp|ico|pdf)[^\s]*/gi, '')
      // Remove HTML-like encoded characters
      .replace(/&[a-z]+;/gi, ' ')
      .replace(/&#\d+;/gi, ' ')
      // Remove email addresses
      .replace(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g, '')
      // Remove markdown image syntax
      .replace(/!\[.*?\]\(.*?\)/g, '')
      // Remove excessive whitespace, newlines, and special chars
      .replace(/[\r\n\t]+/g, ' ')
      .replace(/\s{2,}/g, ' ')
      // Remove common email cruft
      .replace(/cid:[^\s]+/gi, '')
      .replace(/\[image:.*?\]/gi, '')
      .replace(/\[cid:.*?\]/gi, '')
      // Trim
      .trim();

    // If we cleaned everything away, return a generic message
    if (!cleaned || cleaned.length < 10) {
      return 'Email content (contains images/attachments)';
    }

    return cleaned;
  };

  useEffect(() => {
    fetchPendingItems();
    fetchCompletedItems();
    fetchReferralPartners();
    fetchEmailProcessingSettings();
    // Note: loadSampleData() removed - was overwriting real API data with samples

    // Auto-sync emails every 5 minutes
    const syncInterval = setInterval(() => {
      syncEmails(true); // silent sync
    }, 5 * 60 * 1000); // 5 minutes

    // Initial sync on load
    syncEmails(true);

    return () => clearInterval(syncInterval);
  }, []);

  // Fetch email processing settings (global delete from inbox setting)
  const fetchEmailProcessingSettings = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/user-settings/email-processing`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setDeleteFromInboxGlobal(data.delete_from_inbox_after_processing || false);
      }
    } catch (error) {
      console.error('Error fetching email processing settings:', error);
    }
  };

  // Reset the override when a new item is selected
  useEffect(() => {
    setDeleteFromInboxOverride(null);
  }, [selectedItem?.id]);

  // Force layout recalculation when content loads to fix scroll issues
  useEffect(() => {
    if (!loading) {
      // Small delay to ensure DOM has updated
      const timer = setTimeout(() => {
        window.dispatchEvent(new Event('resize'));
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [loading, activeTab, selectedItem]);

  const fetchReferralPartners = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/referral-partners`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setReferralPartners(data.partners || data || []);
      }
    } catch (error) {
      // Silently handle - referral partners may not be available
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
      const company = (partner.company || partner.company_name || '').toLowerCase();
      return name.includes(searchLower) || company.includes(searchLower);
    });

    setReferralSearchResults(results);
    setShowReferralDropdown(true);
  };

  // Select a referral partner from search results
  const selectReferralPartner = (partner) => {
    setSelectedReferralPartner(partner);
    setNewBorrowerForm(prev => ({ ...prev, referral_partner_id: partner.id }));
    setReferralSearchTerm(partner.name || partner.company || '');
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
      toast.error('Please enter a name for the referral partner');
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/referral-partners`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
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
        setNewReferralPartner({ name: '', company: '', email: '', phone: '', type: 'realtor' });
      } else {
        const error = await response.json();
        toast.error(`Failed to create referral partner: ${error.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error creating referral partner:', error);
      toast.error('Error creating referral partner');
    }
  };

  const fetchPendingItems = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/pending`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        const allItems = data.items || [];

        // Split items into three categories:
        // 1. New - Fresh unprocessed messages (not yet touched by AI auto-processing rules)
        // 2. Auto-Processing - AI handles automatically (user approved similar messages before)
        // 3. Pending Review - AI completed the work, user needs to verify and deploy
        const newMessages = [];
        const autoProcess = [];
        const needsReview = [];

        allItems.forEach(item => {
          const enrichedItem = {
            ...item,
            email_subject: item.email?.subject,
            email_from: item.email?.sender,
            email_received_at: item.email?.received_at,
            email_body: item.email?.body || item.email?.text_content || item.email?.html_content
          };

          // Check if AI has auto-processing rule for this type
          if (item.auto_process_enabled || item.status === 'auto_processing') {
            // AI is handling this automatically
            autoProcess.push(enrichedItem);
          } else if (item.ai_completed || item.status === 'ai_completed') {
            // AI completed the work, waiting for user verification
            // Note: 'pending_review' and 'needs_review' are treated as new items awaiting action
            needsReview.push({
              ...enrichedItem,
              needs_human_review: true,
              review_reason: item.review_reason ||
                            (item.ai_confidence < 0.75 ? 'Low AI confidence' :
                            item.match_confidence < 0.65 ? 'Low match confidence' :
                            'AI completed - ready for review')
            });
          } else {
            // Fresh items awaiting user action (includes 'pending_review', 'needs_review', or no status)
            newMessages.push(enrichedItem);
          }
        });

        setNewItems(newMessages);
        setAutoProcessingItems(autoProcess);
        setPendingReviewItems(needsReview);
      }
    } catch (error) {
      console.error('Error fetching pending items:', error);
    } finally {
      setLoading(false);
      // Trigger layout recalculation after data loads
      setTimeout(() => triggerRecalculation(), 50);
    }
  };

  const fetchCompletedItems = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/completed?limit=50`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`
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

  const fetchCallDrafts = async () => {
    try {
      setCallDraftsLoading(true);
      const drafts = await emailDraftsAPI.getCallDrafts();
      setCallDrafts(drafts);
    } catch (error) {
      console.error('Error fetching call drafts:', error);
    } finally {
      setCallDraftsLoading(false);
    }
  };

  const handleSendDraft = async (draftId) => {
    try {
      setDraftActionLoading(draftId);
      await emailDraftsAPI.send(draftId);
      setCallDrafts(prev => prev.filter(d => d.id !== draftId));
      if (selectedDraft?.id === draftId) setSelectedDraft(null);
    } catch (error) {
      console.error('Error sending draft:', error);
      toast.error('Failed to send email: ' + (error.response?.data?.detail || error.message));
    } finally {
      setDraftActionLoading(null);
    }
  };

  const handleDeleteDraft = async (draftId) => {
    try {
      setDraftActionLoading(draftId);
      await emailDraftsAPI.delete(draftId);
      setCallDrafts(prev => prev.filter(d => d.id !== draftId));
      if (selectedDraft?.id === draftId) setSelectedDraft(null);
    } catch (error) {
      console.error('Error deleting draft:', error);
    } finally {
      setDraftActionLoading(null);
    }
  };

  const syncEmails = async (silent = false) => {
    try {
      if (!silent) {
        setSyncingEmails(true);
        setSyncStatus('Syncing emails...');
      }

      const token = getToken();

      // Check which email service is connected
      const gmailStatus = await fetch(`${API_BASE_URL}/api/v1/gmail/status`, {
        headers: { 'Authorization': `Bearer ${token}` }
      }).then(r => r.ok ? r.json() : null).catch(() => null);

      const microsoftStatus = await fetch(`${API_BASE_URL}/api/v1/microsoft/status/outlook_email`, {
        headers: { 'Authorization': `Bearer ${token}` }
      }).then(r => r.ok ? r.json() : null).catch((e) => { console.error('Microsoft status check error:', e); return null; });

      // Debug logging for troubleshooting
      console.log('Email service status check:', { gmailStatus, microsoftStatus });

      let response;
      let syncEndpoint;

      if (gmailStatus?.connected) {
        // Use Gmail sync
        syncEndpoint = `${API_BASE_URL}/api/v1/gmail/sync`;
        response = await fetch(syncEndpoint, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        });
      } else if (microsoftStatus?.data?.connected) {
        // Use Microsoft Outlook sync
        syncEndpoint = `${API_BASE_URL}/api/v1/microsoft/email/sync`;
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
          // Use message from backend which has better context
          const statusMsg = data.message || `Synced ${data.processed_count || 0} emails`;
          setSyncStatus(statusMsg);

          // Log detailed info for debugging
          console.log('Sync result:', data);

          // Refresh both pending and completed items to show new data
          fetchPendingItems();
          fetchCompletedItems();

          // Clear status after 5 seconds (longer to read the info)
          setTimeout(() => setSyncStatus(''), 5000);
        }
      } else {
        if (!silent) {
          // Try to get specific error message
          let errorMessage = 'Sync failed - please try again';
          try {
            const errorData = await response.json();
            if (response.status === 404 && errorData.detail) {
              // Not connected error
              errorMessage = `⚠ ${errorData.detail}. Go to Settings to reconnect.`;
            } else if (response.status === 401 || errorData.detail === 'needs_reauth' ||
                       (errorData.detail && (errorData.detail.includes('token') || errorData.detail.includes('expired')))) {
              // Token expired - prompt to reconnect
              const confirmReconnect = window.confirm(
                'Your Microsoft session has expired. Would you like to go to Settings to reconnect?'
              );
              if (confirmReconnect) {
                window.location.href = '/settings?tab=integrations';
              }
              errorMessage = '⚠ Microsoft session expired. Please reconnect in Settings.';
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
          'Authorization': `Bearer ${getToken()}`
        }
      });

      if (checkResponse.ok) {
        const matchData = await checkResponse.json();

        if (!matchData.has_match) {
          // No match found - show dialog to create new borrower
          setNoMatchItemId(itemId);
          setNoMatchData(matchData);

          // Extract first and last name from fields object
          const fields = matchData.fields || {};
          const getFieldValue = (fieldName) => {
            const field = fields[fieldName];
            return typeof field === 'object' ? field.value : field;
          };

          // Try to get names from specific fields first, then fall back to extracted_name
          let firstName = getFieldValue('first_name') || getFieldValue('borrower_first_name') || '';
          let lastName = getFieldValue('last_name') || getFieldValue('borrower_last_name') || '';
          let loanNumber = getFieldValue('loan_number') || getFieldValue('loan_id') || getFieldValue('file_number') || '';

          // If no specific name fields, try to parse from extracted_name or borrower_name
          if (!firstName && !lastName) {
            const fullName = matchData.extracted_name || getFieldValue('borrower_name') || '';
            if (fullName) {
              const nameParts = fullName.trim().split(' ');
              firstName = nameParts[0] || '';
              lastName = nameParts.slice(1).join(' ') || '';
            }
          }

          setNewBorrowerForm({
            first_name: firstName,
            last_name: lastName,
            loan_number: loanNumber,
            loan_stage: selectedLoanStage || 'NEW', // Use the stage selected in the first step, or default to NEW
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
      toast.error(`Error approving item: ${error.message}`);
      setProcessingAction(false);
    }
  };

  const proceedWithApproval = async (itemId, options = {}) => {
    try {
      setProcessingAction(true);

      // First, check for status mismatch (unless skipStatusCheck is true)
      if (!options.skipStatusCheck) {
        try {
          const checkResponse = await fetch(`${API_BASE_URL}/api/v1/reconciliation/pre-approval-check/${itemId}`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${getToken()}`,
              'Content-Type': 'application/json'
            }
          });

          if (checkResponse.ok) {
            const checkData = await checkResponse.json();
            if (checkData.needs_status_update) {
              // Show status correction modal
              setStatusCorrectionData(checkData);
              setPendingApprovalItemId(itemId);
              setSelectedNewStatus(checkData.suggested_status);
              setShowStatusCorrectionModal(true);
              setProcessingAction(false);
              return; // Wait for user to confirm status change
            }
          }
        } catch (checkError) {
          console.log('Pre-approval check failed, proceeding with approval:', checkError);
          // Continue with approval even if check fails
        }
      }

      const corrections = Object.keys(editedFields).length > 0 ? editedFields : null;
      const deletedFieldsList = deletedFields.size > 0 ? Array.from(deletedFields) : null;
      const renamedFieldsObj = Object.keys(renamedFields).length > 0 ? renamedFields : null;

      // Build request body with entity type options
      // Determine if we should delete from inbox
      const shouldDeleteFromInbox = deleteFromInboxOverride !== null
        ? deleteFromInboxOverride
        : deleteFromInboxGlobal;

      const requestBody = {
        extracted_data_id: itemId,
        corrections: corrections,
        deleted_fields: deletedFieldsList,
        renamed_fields: renamedFieldsObj,
        delegate_to_ai: delegateToAI,
        allow_auto_process: allowAutoProcess, // Skip review for similar messages
        email_intent: selectedItem?.email_intent,
        recommended_action: selectedItem?.recommended_action,
        delete_from_inbox: shouldDeleteFromInbox,
        email_message_id: selectedItem?.email_message_id || selectedItem?.message_id
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

      // Add status update if provided
      if (options.updateStatusTo) {
        requestBody.update_status_to = options.updateStatusTo;
      }

      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      });

      if (response.ok) {
        const responseData = await response.json();

        // Show applied data summary modal with link to profile
        setAppliedDataSummary({
          entityName: responseData.entity_name || statusCorrectionData?.entity_name || selectedItem?.match_name || 'Borrower',
          entityType: responseData.entity_type,
          entityId: responseData.entity_id,
          appliedFields: responseData.applied_fields || [],
          statusUpdated: responseData.status_updated,
          oldStatus: responseData.old_status,
          newStatus: responseData.new_status
        });
        setShowAppliedDataModal(true);

        // Remove from list and reset
        setNewItems(prev => prev.filter(item => item.id !== itemId));
        setAutoProcessingItems(prev => prev.filter(item => item.id !== itemId));
        setPendingReviewItems(prev => prev.filter(item => item.id !== itemId));
        setSelectedItem(null);
        setEditedFields({});
        setDeletedFields(new Set());
        setRenamedFields({});
        setEditingFieldKey(null);
        setDelegateToAI(false);
        setAllowAutoProcess(false);
        setSelectedEntityType(null);
        setCreateNewLoan(false);
        setStatusCorrectionData(null);
        setPendingApprovalItemId(null);
        // Refresh completed items to show the newly approved item
        fetchCompletedItems();
      } else {
        const errorData = await response.json().catch(() => ({}));
        toast.error(`Failed to approve item: ${errorData.detail || response.statusText}`);
      }
    } catch (error) {
      console.error('Error approving item:', error);
      toast.error(`Error approving item: ${error.message}`);
    } finally {
      setProcessingAction(false);
    }
  };

  // Handle status correction modal actions
  const handleStatusCorrectionConfirm = async () => {
    setShowStatusCorrectionModal(false);
    if (pendingApprovalItemId) {
      await proceedWithApproval(pendingApprovalItemId, {
        skipStatusCheck: true,
        updateStatusTo: selectedNewStatus
      });
    }
  };

  const handleStatusCorrectionSkip = async () => {
    setShowStatusCorrectionModal(false);
    if (pendingApprovalItemId) {
      await proceedWithApproval(pendingApprovalItemId, {
        skipStatusCheck: true
      });
    }
  };

  const handleStatusCorrectionCancel = () => {
    setShowStatusCorrectionModal(false);
    setStatusCorrectionData(null);
    setPendingApprovalItemId(null);
    setSelectedNewStatus(null);
    setProcessingAction(false);
  };

  const handleCreateBorrower = async () => {
    try {
      setProcessingAction(true);

      // Validate form
      if (!newBorrowerForm.first_name || !newBorrowerForm.last_name) {
        toast.error('Please enter first name and last name');
        setProcessingAction(false);
        return;
      }

      const itemId = noMatchItemId;

      // Close dialog first
      setShowNoMatchDialog(false);
      setNoMatchItemId(null);
      setNoMatchData(null);

      // Add the borrower name and loan number to corrections
      const corrections = {
        borrower_name: `${newBorrowerForm.first_name} ${newBorrowerForm.last_name}`
      };

      // Add loan number if provided
      if (newBorrowerForm.loan_number) {
        corrections.loan_number = newBorrowerForm.loan_number;
      }

      // Now approve with create_new_loan option and loan_stage
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          extracted_data_id: itemId,
          corrections: corrections,
          create_new_loan: true,
          loan_stage: newBorrowerForm.loan_stage,
          loan_number: newBorrowerForm.loan_number || null,
          target_entity_type: 'loan'
        })
      });

      if (response.ok) {
        const responseData = await response.json();

        // Show applied data summary modal with link to profile
        setAppliedDataSummary({
          entityName: responseData.entity_name || `${newBorrowerForm.first_name} ${newBorrowerForm.last_name}`,
          entityType: responseData.entity_type,
          entityId: responseData.entity_id,
          appliedFields: [],
          statusUpdated: false,
          isNewBorrower: true
        });
        setShowAppliedDataModal(true);

        // Remove from ALL lists and reset
        setNewItems(prev => prev.filter(item => item.id !== itemId));
        setAutoProcessingItems(prev => prev.filter(item => item.id !== itemId));
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
        toast.error(`Failed to create borrower: ${errorData.detail || response.statusText}`);
      }
    } catch (error) {
      console.error('Error creating borrower:', error);
      toast.error(`Error creating borrower: ${error.message}`);
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

      // Determine if we should delete from inbox
      const shouldDeleteFromInbox = deleteFromInboxOverride !== null
        ? deleteFromInboxOverride
        : deleteFromInboxGlobal;

      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          extracted_data_id: itemId,
          reason: reason,
          delete_from_inbox: shouldDeleteFromInbox,
          email_message_id: selectedItem?.email_message_id || selectedItem?.message_id
        })
      });

      if (response.ok) {
        setPendingItems(prev => prev.filter(item => item.id !== itemId));
        setPendingReviewItems(prev => prev.filter(item => item.id !== itemId));
        setSelectedItem(null);
        setEditedFields({});
        setDeleteFromInboxOverride(null);
        // Refresh completed items to show the rejected item
        fetchCompletedItems();
      } else {
        const errorData = await response.json().catch(() => ({}));
        toast.error(`Failed to reject item: ${errorData.detail || response.statusText}`);
      }
    } catch (error) {
      console.error('Error rejecting item:', error);
      toast.error(`Error rejecting item: ${error.message}`);
    } finally {
      setProcessingAction(false);
    }
  };

  const handleDelete = async (itemId) => {
    try {
      setProcessingAction(true);

      // Determine if we should delete from inbox
      const shouldDeleteFromInbox = deleteFromInboxOverride !== null
        ? deleteFromInboxOverride
        : deleteFromInboxGlobal;

      // Build URL with query params for delete_from_inbox option
      const emailMessageId = selectedItem?.email_message_id || selectedItem?.message_id;
      let url = `${API_BASE_URL}/api/v1/reconciliation/items/${itemId}`;
      if (shouldDeleteFromInbox && emailMessageId) {
        url += `?delete_from_inbox=true&email_message_id=${encodeURIComponent(emailMessageId)}`;
      }

      const response = await fetch(url, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${getToken()}`
        }
      });

      if (response.ok) {
        // Find the next item to select based on active tab
        const getCurrentList = () => {
          switch (activeTab) {
            case 'new': return newItems;
            case 'autoProcessing': return autoProcessingItems;
            case 'pendingReview': return pendingReviewItems;
            case 'completed': return completedItems;
            default: return newItems;
          }
        };

        const currentList = getCurrentList();
        const currentIndex = currentList.findIndex(item => item.id === itemId);
        const nextItem = currentList[currentIndex + 1] || currentList[currentIndex - 1] || null;

        // Remove from all lists
        setNewItems(prev => prev.filter(item => item.id !== itemId));
        setPendingItems(prev => prev.filter(item => item.id !== itemId));
        setPendingReviewItems(prev => prev.filter(item => item.id !== itemId));
        setCompletedItems(prev => prev.filter(item => item.id !== itemId));

        // Select the next item instead of clearing selection
        if (nextItem && nextItem.id !== itemId) {
          setSelectedItem(nextItem);
        } else {
          setSelectedItem(null);
        }
        setEditedFields({});
        setDeleteFromInboxOverride(null);
      } else {
        const errorData = await response.json().catch(() => ({}));
        toast.error(`Failed to delete item: ${errorData.detail || response.statusText}`);
      }
    } catch (error) {
      console.error('Error deleting item:', error);
      toast.error(`Error deleting item: ${error.message}`);
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

  // Handle deleting a field
  const handleFieldDelete = (fieldName) => {
    setDeletedFields(prev => {
      const newSet = new Set(prev);
      newSet.add(fieldName);
      return newSet;
    });
  };

  // Handle restoring a deleted field
  const handleFieldRestore = (fieldName) => {
    setDeletedFields(prev => {
      const newSet = new Set(prev);
      newSet.delete(fieldName);
      return newSet;
    });
  };

  // Handle adding a new field
  const handleAddField = () => {
    if (!newFieldKey.trim() || !newFieldValue.trim()) return;

    // Convert field key to snake_case
    const fieldKey = newFieldKey.toLowerCase().replace(/\s+/g, '_');

    setAddedFields(prev => ({
      ...prev,
      [fieldKey]: { value: newFieldValue, confidence: 1.0 }
    }));

    // Reset form
    setNewFieldKey('');
    setNewFieldValue('');
    setShowAddFieldForm(false);
  };

  // Handle removing an added field
  const handleRemoveAddedField = (fieldKey) => {
    setAddedFields(prev => {
      const newFields = { ...prev };
      delete newFields[fieldKey];
      return newFields;
    });
  };

  // Reset field editing state when selecting a new item
  const resetFieldEditState = () => {
    setEditedFields({});
    setDeletedFields(new Set());
    setRenamedFields({});
    setAddedFields({});
    setShowAddFieldForm(false);
    setNewFieldKey('');
    setNewFieldValue('');
  };

  // Handle renaming a field key
  const handleFieldRename = (oldKey, newKey) => {
    if (newKey && newKey !== oldKey) {
      setRenamedFields(prev => ({
        ...prev,
        [oldKey]: newKey
      }));
    }
    setEditingFieldKey(null);
  };

  // Handle undoing a field rename
  const handleFieldRenameUndo = (oldKey) => {
    setRenamedFields(prev => {
      const newFields = { ...prev };
      delete newFields[oldKey];
      return newFields;
    });
  };

  // Get the effective field key (after any rename)
  const getEffectiveFieldKey = (originalKey) => {
    return renamedFields[originalKey] || originalKey;
  };

  // Available field types for renaming dropdown
  const fieldTypeOptions = [
    { value: 'first_name', label: 'First Name' },
    { value: 'last_name', label: 'Last Name' },
    { value: 'borrower_name', label: 'Borrower Name' },
    { value: 'coborrower_first_name', label: 'Co-Borrower First Name' },
    { value: 'coborrower_last_name', label: 'Co-Borrower Last Name' },
    { value: 'coborrower_name', label: 'Co-Borrower Name' },
    { value: 'email', label: 'Email' },
    { value: 'phone', label: 'Phone' },
    { value: 'loan_number', label: 'Loan Number' },
    { value: 'property_address', label: 'Property Address' },
    { value: 'property_city', label: 'Property City' },
    { value: 'property_state', label: 'Property State' },
    { value: 'property_zip', label: 'Property Zip' },
    { value: 'loan_amount', label: 'Loan Amount' },
    { value: 'amount', label: 'Amount' },
    { value: 'lender', label: 'Lender' },
    { value: 'processor', label: 'Processor' },
    { value: 'processing_assistant', label: 'Processing Assistant' },
    { value: 'loan_officer', label: 'Loan Officer' },
    { value: 'loan_officer_name', label: 'Loan Officer Name' },
    { value: 'program', label: 'Program' },
    { value: 'interest_rate', label: 'Interest Rate' },
    { value: 'closing_date', label: 'Closing Date' },
    { value: 'lock_expiration', label: 'Lock Expiration' },
    { value: 'referral_partner', label: 'Referral Partner' },
    { value: 'realtor_name', label: 'Realtor Name' },
    { value: 'notes', label: 'Notes' }
  ];

  // Handle selecting an item - resets entity type selection
  const handleSelectItem = (item) => {
    setSelectedItem(item);
    setEditedFields({});
    setDeletedFields(new Set());
    setRenamedFields({});
    setEditingFieldKey(null);
    setAddedFields({});
    setShowAddFieldForm(false);
    setNewFieldKey('');
    setNewFieldValue('');
    // Reset entity type selection to show AI's suggestion
    setSelectedEntityType(null);
    setCreateNewLoan(false);
    setSelectedLoanStage('UW_RECEIVED');
    // Reset AI delegation checkboxes
    setDelegateToAI(false);
    setAllowAutoProcess(false);
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
      toast.error('Please select items to approve');
      return;
    }

    setBulkProcessing(true);
    let successCount = 0;

    for (const itemId of selectedItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${getToken()}`,
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

    toast.success(`Successfully approved ${successCount} out of ${selectedItems.size} items`);
  };

  const bulkReject = async () => {
    if (selectedItems.size === 0) {
      toast.error('Please select items to reject');
      return;
    }

    const reason = prompt('Enter reason for rejection:');
    if (!reason) return;

    setBulkProcessing(true);
    let successCount = 0;

    for (const itemId of selectedItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${getToken()}`,
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

    toast.success(`Successfully rejected ${successCount} out of ${selectedItems.size} items`);
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
    if (selectedReviewItems.size === 0) return;

    // Optimistic UI update - remove items immediately
    const itemsToDelete = new Set(selectedReviewItems);
    setPendingReviewItems(prev => prev.filter(item => !itemsToDelete.has(item.id)));
    setSelectedReviewItems(new Set());

    // Delete in background - no waiting
    for (const itemId of itemsToDelete) {
      fetch(`${API_BASE_URL}/api/v1/reconciliation/items/${itemId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${getToken()}`
        }
      }).catch(err => console.error(`Delete failed for ${itemId}:`, err));
    }
  };

  const bulkApproveReviewItems = async () => {
    if (selectedReviewItems.size === 0) return;

    // Optimistic UI update - remove items immediately
    const itemsToApprove = new Set(selectedReviewItems);
    setPendingReviewItems(prev => prev.filter(item => !itemsToApprove.has(item.id)));
    setSelectedReviewItems(new Set());

    // Approve in background - no waiting
    for (const itemId of itemsToApprove) {
      fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          extracted_data_id: itemId,
          corrections: null
        })
      }).catch(err => console.error(`Approve failed for ${itemId}:`, err));
    }
  };

  const bulkBlockSenders = async () => {
    if (selectedReviewItems.size === 0) return;

    // Get unique senders from selected items
    const sendersToBlock = new Set();
    const itemsToRemove = new Set(selectedReviewItems);
    selectedReviewItems.forEach(itemId => {
      const item = pendingReviewItems.find(i => i.id === itemId);
      if (item?.email_from) {
        sendersToBlock.add(item.email_from);
      }
    });

    // Optimistic UI update - remove items immediately
    setPendingReviewItems(prev => prev.filter(item => !itemsToRemove.has(item.id)));
    setSelectedReviewItems(new Set());

    // Block senders and reject items in background
    for (const sender of sendersToBlock) {
      fetch(`${API_BASE_URL}/api/v1/reconciliation/block-sender`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ sender_email: sender })
      }).catch(err => console.error(`Block sender failed for ${sender}:`, err));
    }

    for (const itemId of itemsToRemove) {
      fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          extracted_data_id: itemId,
          reason: 'Sender blocked by user'
        })
      }).catch(err => console.error(`Reject failed for ${itemId}:`, err));
    }
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

    if (fieldName === 'rate' || fieldName === 'interest_rate') {
      // Convert decimal to percentage if value is less than 1 (e.g., 0.05875 -> 5.875%)
      const numValue = parseFloat(value);
      if (!isNaN(numValue)) {
        if (numValue < 1) {
          return `${(numValue * 100).toFixed(3).replace(/\.?0+$/, '')}%`;
        }
        return `${numValue}%`;
      }
      return `${value}%`;
    }

    return value;
  };

  // Format field value for display - handles rate conversion and currency formatting
  const formatDisplayValue = (fieldName, value) => {
    if (!value && value !== 0) return value;

    // Handle rate/interest_rate - convert decimal to percentage
    if (fieldName === 'rate' || fieldName === 'interest_rate') {
      const numValue = parseFloat(value);
      if (!isNaN(numValue)) {
        if (numValue < 1) {
          return `${(numValue * 100).toFixed(3).replace(/\.?0+$/, '')}%`;
        }
        return `${numValue}%`;
      }
    }

    // Handle loan amounts
    if (fieldName === 'loan_amount' || fieldName === 'appraisal_value' || fieldName === 'purchase_price') {
      const numValue = parseFloat(value);
      if (!isNaN(numValue)) {
        return `$${numValue.toLocaleString()}`;
      }
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
    <div className="reconciliation-page" ref={containerRef}>
      <div className="reconciliation-container">
        <div className="reconciliation-header">
          <div className="header-content">
            <h1>Data Reconciliation Center</h1>
            <p>Review and approve AI-extracted loan data from emails</p>

            {/* Tab Navigation */}
            <div className="tab-navigation">
              <button
                className={`tab-button ${activeTab === 'new' ? 'active' : ''}`}
                onClick={() => setActiveTab('new')}
              >
                New ({newItems.length})
              </button>
              <button
                className={`tab-button ${activeTab === 'autoProcessing' ? 'active' : ''}`}
                onClick={() => setActiveTab('autoProcessing')}
              >
                Auto-Processing ({autoProcessingItems.length})
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
              <button
                className={`tab-button ${activeTab === 'callDrafts' ? 'active' : ''}`}
                onClick={() => { setActiveTab('callDrafts'); fetchCallDrafts(); }}
              >
                Call Drafts ({callDrafts.length})
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
              <div className={`sync-status ${syncStatus.includes('Synced') ? 'success' : 'error'}`}>
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

        {/* New Tab Content */}
        {activeTab === 'new' && newItems.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon"></div>
            <h2>No New Messages</h2>
            <p>New emails will appear here for processing. Click "Sync Emails Now" to check for new messages.</p>
          </div>
        ) : activeTab === 'new' && newItems.length > 0 ? (
          <div className="reconciliation-content">
            {/* New Items List */}
            <div className="items-list">
              {newItems.map((item) => (
                <div
                  key={item.id}
                  className={`reconciliation-item ${selectedItem?.id === item.id ? 'selected' : ''}`}
                  onClick={() => handleSelectItem(item)}
                >
                  <div className="item-content">
                    <div className="item-header">
                      <div className="item-category">
                        {item.category?.toUpperCase() || item.email_intent || 'NEW'}
                      </div>
                      <div className="status-badge new-badge">
                        NEW
                      </div>
                    </div>
                    <div className="item-subject">{item.email_subject || item.email?.subject}</div>
                    <div className="item-date-display">
                      {new Date(item.email_received_at || item.email?.received_at).toLocaleString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric',
                        hour: 'numeric',
                        minute: '2-digit',
                        hour12: true
                      })}
                    </div>
                    <div className="item-meta">
                      <span className="meta-sender">{item.email_from || item.email?.sender}</span>
                    </div>
                    {item.email_body && (
                      <div className="item-body-preview">
                        {(() => {
                          const cleaned = cleanEmailPreview(item.email_body);
                          return cleaned.length > 120 ? cleaned.substring(0, 120) + '...' : cleaned;
                        })()}
                      </div>
                    )}
                  </div>
                  <button
                    className="item-delete-btn"
                    onClick={(e) => { e.stopPropagation(); handleDelete(item.id); }}
                    title="Delete"
                  >
                    🗑️
                  </button>
                </div>
              ))}
            </div>

            {/* Detail Panel for New Items */}
            {selectedItem && (
              <div className="item-detail-panel">
                <div className="detail-header">
                  <div className="detail-title-section">
                    <div className="detail-source">
                      <span className="source-name">NEW MESSAGE</span>
                    </div>
                    <h2 className="detail-title">{selectedItem.email_intent || 'New Email'}</h2>
                  </div>
                  <button className="close-detail" onClick={() => setSelectedItem(null)}>×</button>
                </div>

                <div className="detail-body">
                  <div className="detail-info-grid">
                    <div className="detail-info-item">
                      <span className="detail-label">FROM</span>
                      <span className="detail-value">{selectedItem.email_from || selectedItem.email?.sender}</span>
                    </div>
                    <div className="detail-info-item">
                      <span className="detail-label">SUBJECT</span>
                      <span className="detail-value">{selectedItem.email_subject || selectedItem.email?.subject}</span>
                    </div>
                    <div className="detail-info-item">
                      <span className="detail-label">RECEIVED</span>
                      <span className="detail-value">
                        {new Date(selectedItem.email_received_at || selectedItem.email?.received_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="detail-info-item">
                      <span className="detail-label">STATUS</span>
                      <span className="detail-value">Awaiting Processing</span>
                    </div>
                  </div>

                  {/* Entity Type Selection Section */}
                  <div className="entity-type-selection" style={{ marginBottom: '20px', padding: '15px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                    <h3 style={{ margin: '0 0 15px 0', fontSize: '14px', fontWeight: '600', color: '#374151' }}>
                      Where should this data go?
                    </h3>
                    <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
                      <button
                        onClick={() => { setSelectedEntityType('lead'); setCreateNewLoan(false); }}
                        style={{
                          flex: 1,
                          padding: '12px',
                          border: selectedEntityType === 'lead' && !createNewLoan ? '2px solid #10b981' : '1px solid #e5e7eb',
                          borderRadius: '8px',
                          background: selectedEntityType === 'lead' && !createNewLoan ? '#ecfdf5' : 'white',
                          cursor: 'pointer',
                          fontWeight: selectedEntityType === 'lead' && !createNewLoan ? '600' : '400'
                        }}
                      >
                        Lead
                        <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                          {selectedItem.match_entity_type === 'lead' && selectedItem.match_entity_name ?
                            `Match: ${selectedItem.match_entity_name}` : 'No match found'}
                        </div>
                      </button>
                      <button
                        onClick={() => { setSelectedEntityType('loan'); setCreateNewLoan(false); }}
                        style={{
                          flex: 1,
                          padding: '12px',
                          border: selectedEntityType === 'loan' && !createNewLoan ? '2px solid #3b82f6' : '1px solid #e5e7eb',
                          borderRadius: '8px',
                          background: selectedEntityType === 'loan' && !createNewLoan ? '#eff6ff' : 'white',
                          cursor: 'pointer',
                          fontWeight: selectedEntityType === 'loan' && !createNewLoan ? '600' : '400'
                        }}
                      >
                        Active Loan
                        <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                          {selectedItem.match_entity_type === 'loan' && selectedItem.match_entity_name ?
                            `Match: ${selectedItem.match_entity_name}` : 'No match found'}
                        </div>
                      </button>
                      <button
                        onClick={() => { setSelectedEntityType('portfolio'); setCreateNewLoan(false); }}
                        style={{
                          flex: 1,
                          padding: '12px',
                          border: (selectedEntityType === 'portfolio' || selectedEntityType === 'active_loan') ? '2px solid #f59e0b' : '1px solid #e5e7eb',
                          borderRadius: '8px',
                          background: (selectedEntityType === 'portfolio' || selectedEntityType === 'active_loan') ? '#fef3c7' : 'white',
                          cursor: 'pointer',
                          fontWeight: (selectedEntityType === 'portfolio' || selectedEntityType === 'active_loan') ? '600' : '400'
                        }}
                      >
                        Portfolio
                        <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                          {(selectedItem.match_entity_type === 'portfolio' || selectedItem.match_entity_type === 'active_loan') && selectedItem.match_entity_name ?
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
                        + Create New Loan
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
                          <optgroup label="Lead Stages">
                            {allStages.filter(s => s.category === 'Lead').map(stage => (
                              <option key={stage.value} value={stage.value}>{stage.label}</option>
                            ))}
                          </optgroup>
                          <optgroup label="Active Loan Stages">
                            {allStages.filter(s => s.category === 'Active Loan').map(stage => (
                              <option key={stage.value} value={stage.value}>{stage.label}</option>
                            ))}
                          </optgroup>
                        </select>
                      </div>
                    )}
                  </div>

                  {/* Extracted Fields - Editable */}
                  <div className="extracted-fields-section">
                    <div className="section-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                      <h3 style={{ margin: 0 }}>Extracted Fields</h3>
                      <button
                        onClick={() => setShowAddFieldForm(true)}
                        style={{
                          padding: '6px 12px',
                          fontSize: '12px',
                          background: '#10b981',
                          color: 'white',
                          border: 'none',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}
                      >
                        + Add Field
                      </button>
                    </div>

                    {/* Add Field Form */}
                    {showAddFieldForm && (
                      <div className="add-field-form" style={{
                        background: '#f0fdf4',
                        border: '1px solid #86efac',
                        borderRadius: '8px',
                        padding: '12px',
                        marginBottom: '12px'
                      }}>
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
                          <div style={{ flex: 1 }}>
                            <label style={{ display: 'block', fontSize: '11px', color: '#374151', marginBottom: '4px' }}>Field Name</label>
                            <select
                              value={newFieldKey}
                              onChange={(e) => setNewFieldKey(e.target.value)}
                              style={{
                                width: '100%',
                                padding: '8px',
                                border: '1px solid #d1d5db',
                                borderRadius: '6px',
                                fontSize: '13px'
                              }}
                            >
                              <option value="">Select field type...</option>
                              {fieldTypeOptions.map(opt => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                              ))}
                            </select>
                          </div>
                          <div style={{ flex: 2 }}>
                            <label style={{ display: 'block', fontSize: '11px', color: '#374151', marginBottom: '4px' }}>Value</label>
                            <input
                              type="text"
                              value={newFieldValue}
                              onChange={(e) => setNewFieldValue(e.target.value)}
                              placeholder="Enter value..."
                              style={{
                                width: '100%',
                                padding: '8px',
                                border: '1px solid #d1d5db',
                                borderRadius: '6px',
                                fontSize: '13px'
                              }}
                            />
                          </div>
                          <button
                            onClick={handleAddField}
                            disabled={!newFieldKey || !newFieldValue}
                            style={{
                              padding: '8px 16px',
                              background: newFieldKey && newFieldValue ? '#10b981' : '#d1d5db',
                              color: 'white',
                              border: 'none',
                              borderRadius: '6px',
                              cursor: newFieldKey && newFieldValue ? 'pointer' : 'not-allowed',
                              fontSize: '13px'
                            }}
                          >
                            Add
                          </button>
                          <button
                            onClick={() => {
                              setShowAddFieldForm(false);
                              setNewFieldKey('');
                              setNewFieldValue('');
                            }}
                            style={{
                              padding: '8px 12px',
                              background: '#f3f4f6',
                              color: '#374151',
                              border: '1px solid #d1d5db',
                              borderRadius: '6px',
                              cursor: 'pointer',
                              fontSize: '13px'
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}

                    <div className="fields-grid-recon">
                      {/* Existing fields */}
                      {Object.entries(selectedItem.fields || {}).map(([fieldName, fieldData]) => {
                        const isDeleted = deletedFields.has(fieldName);
                        const isRenamed = fieldName in renamedFields;
                        const effectiveKey = getEffectiveFieldKey(fieldName);
                        const confidence = fieldData.confidence || 0;
                        const value = fieldData.value;
                        const isEdited = fieldName in editedFields;

                        if (isDeleted) {
                          return (
                            <div key={fieldName} className="field-row-recon deleted" style={{ opacity: 0.5, background: '#fee2e2', borderRadius: '6px' }}>
                              <div className="field-header-recon" style={{ textDecoration: 'line-through' }}>
                                <span className="field-name">{formatFieldName(fieldName)}</span>
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ color: '#991b1b', fontSize: '12px' }}>Deleted</span>
                                <button
                                  onClick={() => handleFieldRestore(fieldName)}
                                  style={{
                                    padding: '4px 8px',
                                    fontSize: '11px',
                                    background: '#f3f4f6',
                                    border: '1px solid #d1d5db',
                                    borderRadius: '4px',
                                    cursor: 'pointer'
                                  }}
                                >
                                  Restore
                                </button>
                              </div>
                            </div>
                          );
                        }

                        return (
                          <div key={fieldName} className={`field-row-recon ${isRenamed ? 'renamed' : ''}`}>
                            <div className="field-header-recon" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              {editingFieldKey === fieldName ? (
                                <select
                                  value={effectiveKey}
                                  onChange={(e) => handleFieldRename(fieldName, e.target.value)}
                                  onBlur={() => setEditingFieldKey(null)}
                                  autoFocus
                                  style={{
                                    padding: '4px 8px',
                                    fontSize: '12px',
                                    borderRadius: '4px',
                                    border: '1px solid #3b82f6',
                                    minWidth: '140px'
                                  }}
                                >
                                  <option value={fieldName}>{formatFieldName(fieldName)}</option>
                                  {fieldTypeOptions
                                    .filter(opt => opt.value !== fieldName)
                                    .map(opt => (
                                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                                    ))}
                                </select>
                              ) : (
                                <span
                                  className="field-name"
                                  onClick={() => setEditingFieldKey(fieldName)}
                                  style={{ cursor: 'pointer', borderBottom: '1px dashed #9ca3af' }}
                                  title="Click to change field type"
                                >
                                  {formatFieldName(effectiveKey)}
                                </span>
                              )}
                              {isRenamed && (
                                <span style={{
                                  fontSize: '10px',
                                  color: '#2563eb',
                                  background: '#dbeafe',
                                  padding: '2px 6px',
                                  borderRadius: '4px'
                                }}>
                                  was: {formatFieldName(fieldName)}
                                  <button
                                    onClick={() => handleFieldRenameUndo(fieldName)}
                                    style={{ background: 'transparent', border: 'none', cursor: 'pointer', fontSize: '10px', marginLeft: '4px' }}
                                  >×</button>
                                </span>
                              )}
                              <span
                                className="field-confidence-badge"
                                style={{
                                  backgroundColor: confidence > 0.8 ? '#10b981' : confidence > 0.6 ? '#f59e0b' : '#ef4444',
                                  color: 'white',
                                  marginLeft: 'auto'
                                }}
                              >
                                {Math.round(confidence * 100)}%
                              </span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <input
                                type="text"
                                className={`field-value-input ${isEdited ? 'edited' : ''}`}
                                value={isEdited ? editedFields[fieldName] : formatDisplayValue(fieldName, value) || ''}
                                onChange={(e) => handleFieldEdit(fieldName, e.target.value)}
                                style={{
                                  flex: 1,
                                  padding: '8px 10px',
                                  border: isEdited ? '2px solid #3b82f6' : '1px solid #e5e7eb',
                                  borderRadius: '6px',
                                  fontSize: '14px',
                                  background: isEdited ? '#eff6ff' : 'white'
                                }}
                              />
                              <button
                                onClick={() => handleFieldDelete(fieldName)}
                                style={{
                                  padding: '6px 10px',
                                  background: '#fef2f2',
                                  border: '1px solid #fecaca',
                                  borderRadius: '4px',
                                  cursor: 'pointer',
                                  color: '#dc2626',
                                  fontSize: '14px'
                                }}
                                title="Delete field"
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        );
                      })}

                      {/* Added fields */}
                      {Object.entries(addedFields).map(([fieldKey, fieldData]) => (
                        <div key={`added-${fieldKey}`} className="field-row-recon added" style={{ background: '#f0fdf4', borderRadius: '6px' }}>
                          <div className="field-header-recon" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span className="field-name">{formatFieldName(fieldKey)}</span>
                            <span style={{
                              fontSize: '10px',
                              color: '#166534',
                              background: '#dcfce7',
                              padding: '2px 6px',
                              borderRadius: '4px'
                            }}>
                              NEW
                            </span>
                            <span
                              className="field-confidence-badge"
                              style={{ backgroundColor: '#10b981', color: 'white', marginLeft: 'auto' }}
                            >
                              100%
                            </span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <input
                              type="text"
                              value={fieldData.value}
                              onChange={(e) => setAddedFields(prev => ({
                                ...prev,
                                [fieldKey]: { ...prev[fieldKey], value: e.target.value }
                              }))}
                              style={{
                                flex: 1,
                                padding: '8px 10px',
                                border: '2px solid #10b981',
                                borderRadius: '6px',
                                fontSize: '14px',
                                background: '#f0fdf4'
                              }}
                            />
                            <button
                              onClick={() => handleRemoveAddedField(fieldKey)}
                              style={{
                                padding: '6px 10px',
                                background: '#fef2f2',
                                border: '1px solid #fecaca',
                                borderRadius: '4px',
                                cursor: 'pointer',
                                color: '#dc2626',
                                fontSize: '14px'
                              }}
                              title="Remove field"
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Changes summary */}
                    {(Object.keys(editedFields).length > 0 || deletedFields.size > 0 || Object.keys(renamedFields).length > 0 || Object.keys(addedFields).length > 0) && (
                      <div style={{
                        marginTop: '12px',
                        padding: '10px',
                        background: '#fef3c7',
                        border: '1px solid #fcd34d',
                        borderRadius: '6px',
                        fontSize: '12px',
                        color: '#92400e'
                      }}>
                        <strong>Changes:</strong>{' '}
                        {Object.keys(addedFields).length > 0 && `${Object.keys(addedFields).length} added`}
                        {Object.keys(addedFields).length > 0 && (Object.keys(editedFields).length > 0 || deletedFields.size > 0 || Object.keys(renamedFields).length > 0) && ', '}
                        {Object.keys(editedFields).length > 0 && `${Object.keys(editedFields).length} edited`}
                        {Object.keys(editedFields).length > 0 && (deletedFields.size > 0 || Object.keys(renamedFields).length > 0) && ', '}
                        {deletedFields.size > 0 && `${deletedFields.size} deleted`}
                        {deletedFields.size > 0 && Object.keys(renamedFields).length > 0 && ', '}
                        {Object.keys(renamedFields).length > 0 && `${Object.keys(renamedFields).length} renamed`}
                      </div>
                    )}
                  </div>

                  {/* Email Body */}
                  <div className="email-details-section">
                    <h4>Email Content</h4>
                    <div className="email-details-content" style={{ background: '#f9fafb', padding: '15px', borderRadius: '8px', marginTop: '10px' }}>
                      <div
                        className="email-body-content"
                        style={{
                          padding: '15px',
                          background: 'white',
                          border: '1px solid #e5e7eb',
                          borderRadius: '6px',
                          maxHeight: '300px',
                          overflowY: 'auto',
                          whiteSpace: 'pre-wrap',
                          fontFamily: 'monospace',
                          fontSize: '13px',
                          lineHeight: '1.5'
                        }}
                      >
                        {selectedItem.email_body || selectedItem.email?.body || selectedItem.email?.text_content || 'No email body available'}
                      </div>
                    </div>
                  </div>

                  {/* AI Auto-Process Checkbox */}
                  <div className="ai-delegation-section" style={{ marginTop: '20px', padding: '15px', background: '#fef3c7', borderRadius: '8px', border: '1px solid #fcd34d' }}>
                    <label className="delegation-checkbox" style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={delegateToAI}
                        onChange={(e) => setDelegateToAI(e.target.checked)}
                        style={{ marginTop: '3px' }}
                      />
                      <div>
                        <span style={{ fontWeight: '600', color: '#92400e' }}>
                          Let AI auto-process similar messages
                        </span>
                        <p style={{ margin: '5px 0 0', fontSize: '12px', color: '#78350f' }}>
                          When approved, AI will automatically handle similar "{selectedItem.email_intent || 'email'}" messages in the future without requiring your review.
                        </p>
                      </div>
                    </label>
                  </div>

                  {/* Delete from Inbox Option */}
                  <div style={{
                    marginTop: '12px',
                    padding: '12px 16px',
                    background: deleteFromInboxOverride === true || (deleteFromInboxOverride === null && deleteFromInboxGlobal) ? '#fef2f2' : '#f8fafc',
                    borderRadius: '8px',
                    border: `1px solid ${deleteFromInboxOverride === true || (deleteFromInboxOverride === null && deleteFromInboxGlobal) ? '#fecaca' : '#e2e8f0'}`
                  }}>
                    <label style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '10px',
                      cursor: 'pointer'
                    }}>
                      <input
                        type="checkbox"
                        checked={deleteFromInboxOverride !== null ? deleteFromInboxOverride : deleteFromInboxGlobal}
                        onChange={(e) => setDeleteFromInboxOverride(e.target.checked)}
                        style={{ marginTop: '3px' }}
                      />
                      <div>
                        <span style={{ fontWeight: '600', color: '#dc2626' }}>
                          Also delete from inbox
                        </span>
                        <p style={{ margin: '5px 0 0', fontSize: '12px', color: '#6b7280' }}>
                          Move this email to trash in your email inbox after processing.
                          {deleteFromInboxGlobal && deleteFromInboxOverride === null && (
                            <span style={{ color: '#059669', fontStyle: 'italic' }}> (Enabled by default in Settings)</span>
                          )}
                        </p>
                      </div>
                    </label>
                  </div>

                  {/* Action Buttons */}
                  <div className="detail-action-buttons">
                    <button
                      className="btn-approve-recon"
                      onClick={() => handleApprove(selectedItem.id)}
                      disabled={processingAction}
                    >
                      {processingAction ? 'Processing...' : 'Process & Apply'}
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
                      Reject
                    </button>
                    <button
                      className="btn-delete-recon"
                      onClick={() => handleDelete(selectedItem.id)}
                      disabled={processingAction}
                    >
                      🗑️ Delete
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : null}

        {/* Bulk Actions Bar - only show for autoProcessing tab */}
        {activeTab === 'autoProcessing' && autoProcessingItems.length > 0 && (
          <div className="bulk-actions-bar">
            <div className="bulk-controls">
              <button
                className="btn-select-all"
                onClick={selectAll}
                disabled={autoProcessingItems.length === 0}
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
                    Approve Selected ({selectedItems.size})
                  </>
                )}
              </button>
              <button
                className="btn-bulk-reject"
                onClick={bulkReject}
                disabled={selectedItems.size === 0 || bulkProcessing}
              >
                Reject Selected
              </button>
            </div>
          </div>
        )}

        {/* Auto-Processing Tab Content */}
        {activeTab === 'autoProcessing' && autoProcessingItems.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon"></div>
            <h2>No Auto-Processing Items</h2>
            <p>Messages that AI handles automatically will appear here. Enable auto-processing by checking the box when approving similar messages.</p>
          </div>
        ) : activeTab === 'autoProcessing' && autoProcessingItems.length > 0 ? (
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
                  <div className="item-date-display">
                    {new Date(item.email?.received_at).toLocaleString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                      hour: 'numeric',
                      minute: '2-digit',
                      hour12: true
                    })}
                  </div>
                  <div className="item-meta">
                    <span className="meta-sender">{item.email?.sender}</span>
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
                        {selectedItem.match_entity_type === 'lead' ? 'Lead' :
                         selectedItem.match_entity_type === 'active_loan' ? 'Loan' :
                         selectedItem.match_entity_type === 'client' ? 'Client' : 'Item'}
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
                      <div className="recommendation-icon"></div>
                      <div className="recommendation-content">
                        <div className="recommendation-title">
                          {selectedItem.recommended_action.title || 'Suggested Action'}
                        </div>
                        <div className="recommendation-description">
                          {selectedItem.recommended_action.description}
                        </div>
                        {selectedItem.recommended_action.learning_status && (
                          <div className="learning-status">
                            AI Learning: {selectedItem.recommended_action.learning_status}
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
                              Let AI handle this task type automatically in the future
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
                      const isDeleted = deletedFields.has(fieldName);
                      const isRenamed = fieldName in renamedFields;
                      const effectiveKey = getEffectiveFieldKey(fieldName);
                      const confidence = fieldData.confidence || 0;
                      const value = fieldData.value;
                      const isEdited = fieldName in editedFields;

                      if (isDeleted) {
                        // Show deleted field with restore option
                        return (
                          <div key={fieldName} className="field-row deleted" style={{ opacity: 0.5, background: '#fee2e2' }}>
                            <div className="field-label" style={{ textDecoration: 'line-through' }}>
                              <span>{formatFieldName(fieldName)}</span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span style={{ color: '#991b1b', fontSize: '12px' }}>Deleted</span>
                              <button
                                onClick={() => handleFieldRestore(fieldName)}
                                style={{
                                  padding: '4px 8px',
                                  fontSize: '11px',
                                  background: '#f3f4f6',
                                  border: '1px solid #d1d5db',
                                  borderRadius: '4px',
                                  cursor: 'pointer'
                                }}
                                title="Restore field"
                              >
                                ↩ Restore
                              </button>
                            </div>
                          </div>
                        );
                      }

                      return (
                        <div key={fieldName} className={`field-row ${isRenamed ? 'renamed' : ''}`}>
                          <div className="field-label" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            {editingFieldKey === fieldName ? (
                              // Show dropdown for selecting new field type
                              <select
                                value={effectiveKey}
                                onChange={(e) => handleFieldRename(fieldName, e.target.value)}
                                onBlur={() => setEditingFieldKey(null)}
                                autoFocus
                                style={{
                                  padding: '4px 8px',
                                  fontSize: '12px',
                                  borderRadius: '4px',
                                  border: '1px solid #3b82f6',
                                  minWidth: '160px'
                                }}
                              >
                                <option value={fieldName}>{formatFieldName(fieldName)}</option>
                                {fieldTypeOptions
                                  .filter(opt => opt.value !== fieldName)
                                  .map(opt => (
                                    <option key={opt.value} value={opt.value}>
                                      {opt.label}
                                    </option>
                                  ))}
                              </select>
                            ) : (
                              <>
                                <span
                                  onClick={() => setEditingFieldKey(fieldName)}
                                  style={{
                                    cursor: 'pointer',
                                    borderBottom: '1px dashed #9ca3af'
                                  }}
                                  title="Click to change field type"
                                >
                                  {formatFieldName(effectiveKey)}
                                </span>
                                {isRenamed && (
                                  <span style={{
                                    fontSize: '10px',
                                    color: '#2563eb',
                                    background: '#dbeafe',
                                    padding: '2px 6px',
                                    borderRadius: '4px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '4px'
                                  }}>
                                    was: {formatFieldName(fieldName)}
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleFieldRenameUndo(fieldName);
                                      }}
                                      style={{
                                        background: 'transparent',
                                        border: 'none',
                                        cursor: 'pointer',
                                        fontSize: '10px',
                                        padding: '0 2px'
                                      }}
                                      title="Undo rename"
                                    >
                                      ✕
                                    </button>
                                  </span>
                                )}
                              </>
                            )}
                            <span
                              className="field-confidence"
                              style={{ color: getConfidenceColor(confidence), marginLeft: 'auto' }}
                            >
                              {Math.round(confidence * 100)}%
                            </span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <input
                              type="text"
                              className={`field-input ${isEdited ? 'edited' : ''}`}
                              value={isEdited ? editedFields[fieldName] : formatDisplayValue(fieldName, value) || ''}
                              onChange={(e) => handleFieldEdit(fieldName, e.target.value)}
                              style={{ flex: 1 }}
                            />
                            <button
                              onClick={() => handleFieldDelete(fieldName)}
                              style={{
                                padding: '6px 10px',
                                background: '#fef2f2',
                                border: '1px solid #fecaca',
                                borderRadius: '4px',
                                cursor: 'pointer',
                                color: '#dc2626',
                                fontSize: '14px'
                              }}
                              title="Delete field"
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {(Object.keys(editedFields).length > 0 || deletedFields.size > 0 || Object.keys(renamedFields).length > 0) && (
                  <div className="corrections-notice">
                    <strong>Changes:</strong>{' '}
                    {Object.keys(editedFields).length > 0 && `${Object.keys(editedFields).length} edited`}
                    {Object.keys(editedFields).length > 0 && (deletedFields.size > 0 || Object.keys(renamedFields).length > 0) && ', '}
                    {deletedFields.size > 0 && `${deletedFields.size} deleted`}
                    {deletedFields.size > 0 && Object.keys(renamedFields).length > 0 && ', '}
                    {Object.keys(renamedFields).length > 0 && `${Object.keys(renamedFields).length} renamed`}
                    . The AI will learn from your corrections.
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
            <div className="empty-icon"></div>
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
                Approve ({selectedReviewItems.size})
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
                Delete ({selectedReviewItems.size})
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
                        NEEDS REVIEW
                      </div>
                    </div>
                    <div className="item-subject">{item.email_subject}</div>
                    <div className="item-date-display">
                      {new Date(item.email_received_at).toLocaleString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric',
                        hour: 'numeric',
                        minute: '2-digit',
                        hour12: true
                      })}
                    </div>
                    <div className="item-meta">
                      <span className="item-from">{item.email_from}</span>
                    </div>
                    {item.email_body && (
                      <div className="item-body-preview">
                        {(() => {
                          const cleaned = cleanEmailPreview(item.email_body);
                          return cleaned.length > 120 ? cleaned.substring(0, 120) + '...' : cleaned;
                        })()}
                      </div>
                    )}
                    {item.review_reason && (
                      <div className="review-reason">
                        <strong>Reason:</strong> {item.review_reason}
                      </div>
                    )}
                  </div>
                  <button
                    className="item-delete-btn"
                    onClick={(e) => { e.stopPropagation(); handleDelete(item.id); }}
                    title="Delete"
                  >
                    🗑️
                  </button>
                </div>
              ))}
            </div>

            {/* Detail Panel for Pending Review - Matches Task Detail Layout */}
            {selectedItem && (
              <div className="item-detail-panel">
                <div className="detail-header">
                  <div className="detail-title-section">
                    <div className="detail-source">
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
                  </div>

                  {selectedItem.review_reason && (
                    <div className="review-alert-banner">
                      <div className="alert-icon"></div>
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
                      Where should this data go?
                    </h3>
                    <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
                      <button
                        onClick={() => { setSelectedEntityType('lead'); setCreateNewLoan(false); }}
                        style={{
                          flex: 1,
                          padding: '12px',
                          border: selectedEntityType === 'lead' && !createNewLoan ? '2px solid #10b981' : '1px solid #e5e7eb',
                          borderRadius: '8px',
                          background: selectedEntityType === 'lead' && !createNewLoan ? '#ecfdf5' : 'white',
                          cursor: 'pointer',
                          fontWeight: selectedEntityType === 'lead' && !createNewLoan ? '600' : '400'
                        }}
                      >
                        Lead
                        <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                          {selectedItem.match_entity_type === 'lead' && selectedItem.match_entity_name ?
                            `Match: ${selectedItem.match_entity_name}` : 'No match found'}
                        </div>
                      </button>
                      <button
                        onClick={() => { setSelectedEntityType('loan'); setCreateNewLoan(false); }}
                        style={{
                          flex: 1,
                          padding: '12px',
                          border: selectedEntityType === 'loan' && !createNewLoan ? '2px solid #3b82f6' : '1px solid #e5e7eb',
                          borderRadius: '8px',
                          background: selectedEntityType === 'loan' && !createNewLoan ? '#eff6ff' : 'white',
                          cursor: 'pointer',
                          fontWeight: selectedEntityType === 'loan' && !createNewLoan ? '600' : '400'
                        }}
                      >
                        Active Loan
                        <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                          {selectedItem.match_entity_type === 'loan' && selectedItem.match_entity_name ?
                            `Match: ${selectedItem.match_entity_name}` : 'No match found'}
                        </div>
                      </button>
                      <button
                        onClick={() => { setSelectedEntityType('portfolio'); setCreateNewLoan(false); }}
                        style={{
                          flex: 1,
                          padding: '12px',
                          border: (selectedEntityType === 'portfolio' || selectedEntityType === 'active_loan') ? '2px solid #f59e0b' : '1px solid #e5e7eb',
                          borderRadius: '8px',
                          background: (selectedEntityType === 'portfolio' || selectedEntityType === 'active_loan') ? '#fef3c7' : 'white',
                          cursor: 'pointer',
                          fontWeight: (selectedEntityType === 'portfolio' || selectedEntityType === 'active_loan') ? '600' : '400'
                        }}
                      >
                        Portfolio
                        <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                          {(selectedItem.match_entity_type === 'portfolio' || selectedItem.match_entity_type === 'active_loan') && selectedItem.match_entity_name ?
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
                        + Create New Loan
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
                          <optgroup label="Lead Stages">
                            {allStages.filter(s => s.category === 'Lead').map(stage => (
                              <option key={stage.value} value={stage.value}>{stage.label}</option>
                            ))}
                          </optgroup>
                          <optgroup label="Active Loan Stages">
                            {allStages.filter(s => s.category === 'Active Loan').map(stage => (
                              <option key={stage.value} value={stage.value}>{stage.label}</option>
                            ))}
                          </optgroup>
                          <optgroup label="MUM / Portfolio">
                            {allStages.filter(s => s.category === 'MUM').map(stage => (
                              <option key={stage.value} value={stage.value}>{stage.label}</option>
                            ))}
                          </optgroup>
                          <optgroup label="Other">
                            {allStages.filter(s => s.category === 'Other').map(stage => (
                              <option key={stage.value} value={stage.value}>{stage.label}</option>
                            ))}
                          </optgroup>
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
                        {createNewLoan ? 'New Loan' :
                         (selectedEntityType || selectedItem.match_entity_type) === 'lead' ? 'Lead' :
                         (selectedEntityType || selectedItem.match_entity_type) === 'loan' ? 'Loan' :
                         selectedItem.match_entity_type}
                      </div>
                      <div className="entity-confidence">
                        Match Confidence: <span style={{ color: getConfidenceColor(selectedItem.match_confidence) }}>
                          {createNewLoan ? 'N/A' : `${Math.round(selectedItem.match_confidence * 100)}%`}
                        </span>
                      </div>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                      <h4 style={{ margin: 0 }}>EXTRACTED FIELDS</h4>
                      <button
                        onClick={() => setShowAddFieldForm(true)}
                        style={{
                          padding: '6px 12px',
                          fontSize: '12px',
                          background: '#10b981',
                          color: 'white',
                          border: 'none',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}
                      >
                        + Add Field
                      </button>
                    </div>

                    {/* Add Field Form */}
                    {showAddFieldForm && (
                      <div style={{
                        background: '#f0fdf4',
                        border: '1px solid #86efac',
                        borderRadius: '8px',
                        padding: '12px',
                        marginBottom: '12px'
                      }}>
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
                          <div style={{ flex: 1 }}>
                            <label style={{ display: 'block', fontSize: '11px', color: '#374151', marginBottom: '4px' }}>Field Name</label>
                            <select
                              value={newFieldKey}
                              onChange={(e) => setNewFieldKey(e.target.value)}
                              style={{
                                width: '100%',
                                padding: '8px',
                                border: '1px solid #d1d5db',
                                borderRadius: '6px',
                                fontSize: '13px'
                              }}
                            >
                              <option value="">Select field type...</option>
                              {fieldTypeOptions.map(opt => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                              ))}
                            </select>
                          </div>
                          <div style={{ flex: 2 }}>
                            <label style={{ display: 'block', fontSize: '11px', color: '#374151', marginBottom: '4px' }}>Value</label>
                            <input
                              type="text"
                              value={newFieldValue}
                              onChange={(e) => setNewFieldValue(e.target.value)}
                              placeholder="Enter value..."
                              style={{
                                width: '100%',
                                padding: '8px',
                                border: '1px solid #d1d5db',
                                borderRadius: '6px',
                                fontSize: '13px'
                              }}
                            />
                          </div>
                          <button
                            onClick={handleAddField}
                            disabled={!newFieldKey || !newFieldValue}
                            style={{
                              padding: '8px 16px',
                              background: newFieldKey && newFieldValue ? '#10b981' : '#d1d5db',
                              color: 'white',
                              border: 'none',
                              borderRadius: '6px',
                              cursor: newFieldKey && newFieldValue ? 'pointer' : 'not-allowed',
                              fontSize: '13px'
                            }}
                          >
                            Add
                          </button>
                          <button
                            onClick={() => {
                              setShowAddFieldForm(false);
                              setNewFieldKey('');
                              setNewFieldValue('');
                            }}
                            style={{
                              padding: '8px 12px',
                              background: '#f3f4f6',
                              color: '#374151',
                              border: '1px solid #d1d5db',
                              borderRadius: '6px',
                              cursor: 'pointer',
                              fontSize: '13px'
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}

                    <div className="fields-grid-recon">
                      {Object.entries(selectedItem.fields || {}).map(([fieldName, fieldData]) => {
                        const isDeleted = deletedFields.has(fieldName);
                        const isRenamed = fieldName in renamedFields;
                        const effectiveKey = getEffectiveFieldKey(fieldName);
                        const confidence = fieldData.confidence || 0;
                        const value = fieldData.value;
                        const isEdited = fieldName in editedFields;

                        if (isDeleted) {
                          return (
                            <div key={fieldName} className="field-row-recon deleted" style={{ opacity: 0.5, background: '#fee2e2', borderRadius: '6px' }}>
                              <div className="field-header-recon" style={{ textDecoration: 'line-through' }}>
                                <span className="field-name">{formatFieldName(fieldName)}</span>
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ color: '#991b1b', fontSize: '12px' }}>Deleted</span>
                                <button
                                  onClick={() => handleFieldRestore(fieldName)}
                                  style={{
                                    padding: '4px 8px',
                                    fontSize: '11px',
                                    background: '#f3f4f6',
                                    border: '1px solid #d1d5db',
                                    borderRadius: '4px',
                                    cursor: 'pointer'
                                  }}
                                >
                                  Restore
                                </button>
                              </div>
                            </div>
                          );
                        }

                        return (
                          <div key={fieldName} className={`field-row-recon ${isRenamed ? 'renamed' : ''}`}>
                            <div className="field-header-recon" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              {editingFieldKey === fieldName ? (
                                <select
                                  value={effectiveKey}
                                  onChange={(e) => handleFieldRename(fieldName, e.target.value)}
                                  onBlur={() => setEditingFieldKey(null)}
                                  autoFocus
                                  style={{
                                    padding: '4px 8px',
                                    fontSize: '12px',
                                    borderRadius: '4px',
                                    border: '1px solid #3b82f6',
                                    minWidth: '140px'
                                  }}
                                >
                                  <option value={fieldName}>{formatFieldName(fieldName)}</option>
                                  {fieldTypeOptions
                                    .filter(opt => opt.value !== fieldName)
                                    .map(opt => (
                                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                                    ))}
                                </select>
                              ) : (
                                <span
                                  className="field-name"
                                  onClick={() => setEditingFieldKey(fieldName)}
                                  style={{ cursor: 'pointer', borderBottom: '1px dashed #9ca3af' }}
                                  title="Click to change field type"
                                >
                                  {formatFieldName(effectiveKey)}
                                </span>
                              )}
                              {isRenamed && (
                                <span style={{
                                  fontSize: '10px',
                                  color: '#2563eb',
                                  background: '#dbeafe',
                                  padding: '2px 6px',
                                  borderRadius: '4px'
                                }}>
                                  was: {formatFieldName(fieldName)}
                                  <button
                                    onClick={() => handleFieldRenameUndo(fieldName)}
                                    style={{ background: 'transparent', border: 'none', cursor: 'pointer', fontSize: '10px', marginLeft: '4px' }}
                                  >×</button>
                                </span>
                              )}
                              <span
                                className="field-confidence-badge"
                                style={{
                                  backgroundColor: confidence > 0.8 ? '#10b981' : confidence > 0.6 ? '#f59e0b' : '#ef4444',
                                  color: 'white',
                                  marginLeft: 'auto'
                                }}
                              >
                                {Math.round(confidence * 100)}%
                              </span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <input
                                type="text"
                                value={isEdited ? editedFields[fieldName] : formatDisplayValue(fieldName, value) || ''}
                                onChange={(e) => handleFieldEdit(fieldName, e.target.value)}
                                style={{
                                  flex: 1,
                                  padding: '8px 10px',
                                  border: isEdited ? '2px solid #3b82f6' : '1px solid #e5e7eb',
                                  borderRadius: '6px',
                                  fontSize: '14px',
                                  background: isEdited ? '#eff6ff' : 'white'
                                }}
                              />
                              <button
                                onClick={() => handleFieldDelete(fieldName)}
                                style={{
                                  padding: '6px 10px',
                                  background: '#fef2f2',
                                  border: '1px solid #fecaca',
                                  borderRadius: '4px',
                                  cursor: 'pointer',
                                  color: '#dc2626',
                                  fontSize: '14px'
                                }}
                                title="Delete field"
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        );
                      })}

                      {/* Added fields */}
                      {Object.entries(addedFields).map(([fieldKey, fieldData]) => (
                        <div key={`added-${fieldKey}`} className="field-row-recon added" style={{ background: '#f0fdf4', borderRadius: '6px' }}>
                          <div className="field-header-recon" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span className="field-name">{formatFieldName(fieldKey)}</span>
                            <span style={{
                              fontSize: '10px',
                              color: '#166534',
                              background: '#dcfce7',
                              padding: '2px 6px',
                              borderRadius: '4px'
                            }}>
                              NEW
                            </span>
                            <span
                              className="field-confidence-badge"
                              style={{ backgroundColor: '#10b981', color: 'white', marginLeft: 'auto' }}
                            >
                              100%
                            </span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <input
                              type="text"
                              value={fieldData.value}
                              onChange={(e) => setAddedFields(prev => ({
                                ...prev,
                                [fieldKey]: { ...prev[fieldKey], value: e.target.value }
                              }))}
                              style={{
                                flex: 1,
                                padding: '8px 10px',
                                border: '2px solid #10b981',
                                borderRadius: '6px',
                                fontSize: '14px',
                                background: '#f0fdf4'
                              }}
                            />
                            <button
                              onClick={() => handleRemoveAddedField(fieldKey)}
                              style={{
                                padding: '6px 10px',
                                background: '#fef2f2',
                                border: '1px solid #fecaca',
                                borderRadius: '4px',
                                cursor: 'pointer',
                                color: '#dc2626',
                                fontSize: '14px'
                              }}
                              title="Remove field"
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Changes summary */}
                    {(Object.keys(editedFields).length > 0 || deletedFields.size > 0 || Object.keys(renamedFields).length > 0 || Object.keys(addedFields).length > 0) && (
                      <div style={{
                        marginTop: '12px',
                        padding: '10px',
                        background: '#fef3c7',
                        border: '1px solid #fcd34d',
                        borderRadius: '6px',
                        fontSize: '12px',
                        color: '#92400e'
                      }}>
                        <strong>Changes:</strong>{' '}
                        {Object.keys(addedFields).length > 0 && `${Object.keys(addedFields).length} added`}
                        {Object.keys(addedFields).length > 0 && (Object.keys(editedFields).length > 0 || deletedFields.size > 0 || Object.keys(renamedFields).length > 0) && ', '}
                        {Object.keys(editedFields).length > 0 && `${Object.keys(editedFields).length} edited`}
                        {Object.keys(editedFields).length > 0 && (deletedFields.size > 0 || Object.keys(renamedFields).length > 0) && ', '}
                        {deletedFields.size > 0 && `${deletedFields.size} deleted`}
                        {deletedFields.size > 0 && Object.keys(renamedFields).length > 0 && ', '}
                        {Object.keys(renamedFields).length > 0 && `${Object.keys(renamedFields).length} renamed`}
                      </div>
                    )}
                  </div>

                  {/* Email Details Section - Full Email Display */}
                  <div className="email-details-section">
                    <h4>Email Details</h4>
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

                  {/* AI Skip Review Checkbox - for Pending Review items */}
                  <div className="ai-skip-review-section" style={{ marginTop: '20px', padding: '15px', background: '#ecfdf5', borderRadius: '8px', border: '1px solid #86efac' }}>
                    <label className="skip-review-checkbox" style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={allowAutoProcess}
                        onChange={(e) => setAllowAutoProcess(e.target.checked)}
                        style={{ marginTop: '3px' }}
                      />
                      <div>
                        <span style={{ fontWeight: '600', color: '#166534' }}>
                          Skip review for similar messages in the future
                        </span>
                        <p style={{ margin: '5px 0 0', fontSize: '12px', color: '#15803d' }}>
                          When deployed, AI will automatically complete and deploy similar "{selectedItem.email_intent || 'email'}" messages without requiring your review.
                        </p>
                      </div>
                    </label>
                  </div>

                  {/* Action Buttons - Match Task Layout */}
                  <div className="detail-action-buttons">
                    <button
                      className="btn-approve-recon"
                      onClick={() => handleApprove(selectedItem.id)}
                      disabled={processingAction}
                    >
                      {processingAction ? 'Processing...' : 'DEPLOY'}
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
                      REJECT
                    </button>
                    <button
                      className="btn-delete-recon"
                      onClick={() => handleDelete(selectedItem.id)}
                      disabled={processingAction}
                    >
                      🗑️ DELETE
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
            <div className="empty-icon"></div>
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
                        {item.status === 'rejected' ? 'REJECTED' : 'APPROVED'}
                      </div>
                    </div>
                    <div className="item-subject">{item.email?.subject}</div>
                    <div className="item-date-display">
                      {item.email?.received_at ? new Date(item.email.received_at).toLocaleString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric',
                        hour: 'numeric',
                        minute: '2-digit',
                        hour12: true
                      }) : 'N/A'}
                    </div>
                    <div className="item-meta">
                      <span className="meta-sender">{item.email?.sender}</span>
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
                  <button
                    className="item-delete-btn"
                    onClick={(e) => { e.stopPropagation(); handleDelete(item.id); }}
                    title="Delete"
                  >
                    🗑️
                  </button>
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
                            value={formatDisplayValue(fieldName, value) || ''}
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

        {/* Call Drafts Tab Content */}
        {activeTab === 'callDrafts' && callDraftsLoading ? (
          <div className="empty-state">
            <div className="spinner-small"></div>
            <p>Loading call drafts...</p>
          </div>
        ) : activeTab === 'callDrafts' && callDrafts.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon"></div>
            <h2>No Call Drafts</h2>
            <p>Email drafts generated by the AI Scribe during calls will appear here for review and sending.</p>
          </div>
        ) : activeTab === 'callDrafts' ? (
          <div className="reconciliation-content">
            <div className="items-list">
              {callDrafts.map((draft) => (
                <div
                  key={draft.id}
                  className={`reconciliation-item ${selectedDraft?.id === draft.id ? 'selected' : ''}`}
                  onClick={() => setSelectedDraft(draft)}
                >
                  <div className="item-content">
                    <div className="item-header">
                      <div className="item-category">EMAIL DRAFT</div>
                      <div className="status-badge pending">DRAFT</div>
                    </div>
                    <div className="item-subject">{draft.subject || '(No subject)'}</div>
                    <div className="item-meta">
                      <span className="meta-sender">To: {draft.recipient_email || 'Unknown'}</span>
                      <span className="meta-date">
                        {draft.created_at ? new Date(draft.created_at).toLocaleString('en-US', {
                          month: 'short', day: 'numeric', year: 'numeric',
                          hour: 'numeric', minute: '2-digit', hour12: true
                        }) : 'N/A'}
                      </span>
                    </div>
                    {draft.recipient_name && (
                      <div className="item-match">Recipient: {draft.recipient_name}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {selectedDraft && (
              <div className="detail-panel">
                <div className="panel-header">
                  <h2>Email Draft</h2>
                  <button className="close-panel" onClick={() => setSelectedDraft(null)}>&#10005;</button>
                </div>

                <div className="email-context">
                  <h3>Draft Details</h3>
                  <div className="context-field">
                    <strong>To:</strong> {selectedDraft.recipient_name} &lt;{selectedDraft.recipient_email}&gt;
                  </div>
                  <div className="context-field">
                    <strong>Subject:</strong> {selectedDraft.subject}
                  </div>
                  {selectedDraft.cc_emails?.length > 0 && (
                    <div className="context-field">
                      <strong>CC:</strong> {selectedDraft.cc_emails.join(', ')}
                    </div>
                  )}
                  <div className="context-field">
                    <strong>Source:</strong> Call Recording
                  </div>
                  <div className="context-field">
                    <strong>Created:</strong> {selectedDraft.created_at ? new Date(selectedDraft.created_at).toLocaleString() : 'N/A'}
                  </div>
                </div>

                <div className="extracted-fields">
                  <h3>Email Body</h3>
                  <div style={{
                    padding: '16px',
                    background: '#f9fafb',
                    borderRadius: '8px',
                    border: '1px solid #e5e7eb',
                    whiteSpace: 'pre-wrap',
                    lineHeight: '1.6',
                    fontSize: '14px'
                  }}>
                    {selectedDraft.body_html ? (
                      <div dangerouslySetInnerHTML={{ __html: sanitizeHTML(selectedDraft.body_html, { allowedTags: ['p', 'br', 'b', 'i', 'strong', 'em', 'a', 'div', 'span', 'table', 'tr', 'td', 'th', 'tbody', 'thead', 'hr', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'blockquote'] }) }} />
                    ) : (
                      selectedDraft.body_text || '(No content)'
                    )}
                  </div>
                </div>

                {selectedDraft.call_summary && (
                  <div className="ai-info" style={{ marginTop: '16px' }}>
                    <h3>Call Summary</h3>
                    <p>{selectedDraft.call_summary}</p>
                  </div>
                )}

                <div className="action-buttons" style={{ marginTop: '20px', display: 'flex', gap: '12px' }}>
                  <button
                    className="approve-button"
                    onClick={() => handleSendDraft(selectedDraft.id)}
                    disabled={draftActionLoading === selectedDraft.id}
                  >
                    {draftActionLoading === selectedDraft.id ? 'Sending...' : 'Send Email'}
                  </button>
                  <button
                    className="reject-button"
                    onClick={() => handleDeleteDraft(selectedDraft.id)}
                    disabled={draftActionLoading === selectedDraft.id}
                  >
                    Delete
                  </button>
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
                  <div className="form-group">
                    <label>Loan Number</label>
                    <input
                      type="text"
                      value={newBorrowerForm.loan_number}
                      onChange={(e) => setNewBorrowerForm(prev => ({ ...prev, loan_number: e.target.value }))}
                      placeholder="Enter loan number"
                      style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                    />
                  </div>
                </div>

                {/* Stage Selector - All Stages */}
                <div className="form-group" style={{ marginTop: '15px' }}>
                  <label style={{ fontWeight: '600', marginBottom: '8px', display: 'block' }}>
                    Stage *
                  </label>
                  <select
                    value={newBorrowerForm.loan_stage}
                    onChange={(e) => setNewBorrowerForm(prev => ({ ...prev, loan_stage: e.target.value }))}
                    style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '14px' }}
                  >
                    <optgroup label="Lead Stages">
                      {allStages.filter(s => s.category === 'Lead').map(stage => (
                        <option key={stage.value} value={stage.value}>{stage.label}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Active Loan Stages">
                      {allStages.filter(s => s.category === 'Active Loan').map(stage => (
                        <option key={stage.value} value={stage.value}>{stage.label}</option>
                      ))}
                    </optgroup>
                    <optgroup label="MUM / Portfolio">
                      {allStages.filter(s => s.category === 'MUM').map(stage => (
                        <option key={stage.value} value={stage.value}>{stage.label}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Other">
                      {allStages.filter(s => s.category === 'Other').map(stage => (
                        <option key={stage.value} value={stage.value}>{stage.label}</option>
                      ))}
                    </optgroup>
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
                            {(partner.company || partner.company_name) && (
                              <div style={{ fontSize: '12px', color: '#6b7280' }}>{partner.company || partner.company_name}</div>
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
                      Selected: {selectedReferralPartner.name}
                      {(selectedReferralPartner.company || selectedReferralPartner.company_name) && ` (${selectedReferralPartner.company || selectedReferralPartner.company_name})`}
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
                      value={newReferralPartner.company}
                      onChange={(e) => setNewReferralPartner(prev => ({ ...prev, company: e.target.value }))}
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

      {/* Status Correction Modal */}
      {showStatusCorrectionModal && statusCorrectionData && (
        <div className="dialog-overlay" style={{ zIndex: 2100 }}>
          <div className="dialog-content" style={{ maxWidth: '550px' }}>
            <div className="dialog-header" style={{ background: '#fef3c7', borderBottom: '2px solid #f59e0b' }}>
              <h3 style={{ display: 'flex', alignItems: 'center', gap: '10px', margin: 0 }}>
                Status Mismatch Detected
              </h3>
              <button className="dialog-close" onClick={handleStatusCorrectionCancel}>&times;</button>
            </div>
            <div className="dialog-body" style={{ padding: '24px' }}>
              <p style={{ fontSize: '15px', color: '#374151', marginBottom: '20px' }}>
                <strong>{statusCorrectionData.entity_name}</strong> is currently in{' '}
                <span style={{
                  background: '#e5e7eb',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  fontWeight: '600'
                }}>
                  {statusCorrectionData.current_status_label}
                </span>{' '}
                status, but the data suggests they should be further along in the process.
              </p>

              <div style={{
                background: '#fef9c3',
                border: '1px solid #facc15',
                borderRadius: '8px',
                padding: '16px',
                marginBottom: '20px'
              }}>
                <p style={{ margin: 0, fontWeight: '500', color: '#854d0e' }}>
                  {statusCorrectionData.reason}
                </p>
              </div>

              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontWeight: '600', marginBottom: '8px' }}>
                  Update status to:
                </label>
                <select
                  value={selectedNewStatus || ''}
                  onChange={(e) => setSelectedNewStatus(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '12px',
                    border: '2px solid #3b82f6',
                    borderRadius: '8px',
                    fontSize: '15px',
                    background: '#eff6ff'
                  }}
                >
                  <optgroup label="Lead Stages">
                    {allStages.filter(s => s.category === 'Lead').map(stage => (
                      <option key={stage.value} value={stage.value}>{stage.label}</option>
                    ))}
                  </optgroup>
                  <optgroup label="Active Loan Stages">
                    {allStages.filter(s => s.category === 'Active Loan').map(stage => (
                      <option key={stage.value} value={stage.value}>{stage.label}</option>
                    ))}
                  </optgroup>
                </select>
              </div>

              {statusCorrectionData.fields_to_apply && statusCorrectionData.fields_to_apply.length > 0 && (
                <div style={{
                  background: '#f0fdf4',
                  border: '1px solid #86efac',
                  borderRadius: '8px',
                  padding: '16px',
                  marginBottom: '20px'
                }}>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#166534' }}>
                    Data to be applied ({statusCorrectionData.fields_to_apply.length} fields):
                  </h4>
                  <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '13px', color: '#15803d' }}>
                    {statusCorrectionData.fields_to_apply.slice(0, 8).map((field, idx) => (
                      <li key={idx} style={{ marginBottom: '4px' }}>
                        <strong>{formatFieldName(field.field)}:</strong> {String(field.value).substring(0, 50)}
                      </li>
                    ))}
                    {statusCorrectionData.fields_to_apply.length > 8 && (
                      <li style={{ fontStyle: 'italic' }}>
                        ...and {statusCorrectionData.fields_to_apply.length - 8} more fields
                      </li>
                    )}
                  </ul>
                </div>
              )}
            </div>
            <div className="dialog-footer" style={{
              padding: '16px 24px',
              borderTop: '1px solid #e5e7eb',
              display: 'flex',
              justifyContent: 'space-between',
              gap: '12px',
              background: '#f9fafb'
            }}>
              <button
                onClick={handleStatusCorrectionCancel}
                style={{
                  padding: '10px 20px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  background: 'white',
                  color: '#374151',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <div style={{ display: 'flex', gap: '12px' }}>
                <button
                  onClick={handleStatusCorrectionSkip}
                  style={{
                    padding: '10px 20px',
                    border: '1px solid #d1d5db',
                    borderRadius: '6px',
                    background: 'white',
                    color: '#6b7280',
                    cursor: 'pointer'
                  }}
                >
                  Keep Current Status
                </button>
                <button
                  onClick={handleStatusCorrectionConfirm}
                  style={{
                    padding: '10px 24px',
                    border: 'none',
                    borderRadius: '6px',
                    background: '#10b981',
                    color: 'white',
                    cursor: 'pointer',
                    fontWeight: '600'
                  }}
                >
                  Update Status & Apply Data
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Applied Data Summary Modal */}
      {showAppliedDataModal && appliedDataSummary && (
        <div className="dialog-overlay" style={{ zIndex: 2100 }}>
          <div className="dialog-content" style={{ maxWidth: '500px' }}>
            <div className="dialog-header" style={{ background: '#d1fae5', borderBottom: '2px solid #10b981' }}>
              <h3 style={{ display: 'flex', alignItems: 'center', gap: '10px', margin: 0, color: '#065f46' }}>
                <span style={{ fontSize: '24px' }}>✅</span>
                {appliedDataSummary.isNewBorrower ? 'Borrower Added Successfully' : 'Data Applied Successfully'}
              </h3>
              <button
                className="dialog-close"
                onClick={() => setShowAppliedDataModal(false)}
                style={{ color: '#065f46' }}
              >
                &times;
              </button>
            </div>
            <div className="dialog-body" style={{ padding: '24px' }}>
              <p style={{ fontSize: '15px', color: '#374151', marginBottom: '20px' }}>
                {appliedDataSummary.isNewBorrower
                  ? <><strong>{appliedDataSummary.entityName}</strong> has been added to the CRM.</>
                  : <>The following data has been added to <strong>{appliedDataSummary.entityName}</strong>'s profile:</>
                }
              </p>

              {appliedDataSummary.statusUpdated && (
                <div style={{
                  background: '#fef3c7',
                  border: '1px solid #f59e0b',
                  borderRadius: '8px',
                  padding: '12px 16px',
                  marginBottom: '20px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px'
                }}>
                  <span style={{ fontSize: '20px' }}>📊</span>
                  <div>
                    <strong style={{ color: '#92400e' }}>Status Updated:</strong>
                    <span style={{ marginLeft: '8px', color: '#78350f' }}>
                      {appliedDataSummary.oldStatus} → {appliedDataSummary.newStatus}
                    </span>
                  </div>
                </div>
              )}

              {appliedDataSummary.appliedFields && appliedDataSummary.appliedFields.length > 0 ? (
                <div style={{
                  background: '#f0fdf4',
                  border: '1px solid #86efac',
                  borderRadius: '8px',
                  padding: '16px'
                }}>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#166534' }}>
                    Fields Updated ({appliedDataSummary.appliedFields.length}):
                  </h4>
                  <div style={{
                    maxHeight: '250px',
                    overflowY: 'auto',
                    fontSize: '13px'
                  }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <tbody>
                        {appliedDataSummary.appliedFields.map((field, idx) => (
                          <tr key={idx} style={{ borderBottom: '1px solid #dcfce7' }}>
                            <td style={{
                              padding: '8px 12px',
                              fontWeight: '500',
                              color: '#166534',
                              width: '40%'
                            }}>
                              {formatFieldName(field.field)}
                            </td>
                            <td style={{
                              padding: '8px 12px',
                              color: '#15803d'
                            }}>
                              {String(field.value).substring(0, 60)}
                              {String(field.value).length > 60 && '...'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <p style={{ color: '#6b7280', fontStyle: 'italic' }}>
                  No additional fields were applied.
                </p>
              )}
            </div>
            <div className="dialog-footer" style={{
              padding: '16px 24px',
              borderTop: '1px solid #e5e7eb',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              background: '#f9fafb'
            }}>
              <button
                onClick={() => setShowAppliedDataModal(false)}
                style={{
                  padding: '10px 24px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  background: 'white',
                  color: '#374151',
                  cursor: 'pointer',
                  fontWeight: '500'
                }}
              >
                Close
              </button>
              {appliedDataSummary.entityId && appliedDataSummary.entityType && (
                <button
                  onClick={() => {
                    setShowAppliedDataModal(false);
                    const route = appliedDataSummary.entityType === 'loan'
                      ? `/loans/${appliedDataSummary.entityId}`
                      : `/leads/${appliedDataSummary.entityId}`;
                    navigate(route);
                  }}
                  style={{
                    padding: '10px 24px',
                    border: 'none',
                    borderRadius: '6px',
                    background: '#10b981',
                    color: 'white',
                    cursor: 'pointer',
                    fontWeight: '600',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}
                >
                  View {appliedDataSummary.entityName}'s Profile
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ReconciliationCenter;
