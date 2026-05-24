import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL, emailDraftsAPI } from '../../services/api';
import { toast } from '../../utils/toast';
import { getToken } from '../../utils/tokenStore';

/**
 * useReconciliation - Custom hook encapsulating all data fetching,
 * email sync, and action handlers for the Reconciliation Center.
 *
 * Returns state values and handler functions consumed by the orchestrator.
 */
export default function useReconciliation({ triggerRecalculation, navigate }) {
  // ─── Tab & list state ───
  const [newItems, setNewItems] = useState([]);
  const [autoProcessingItems, setAutoProcessingItems] = useState([]);
  const [pendingReviewItems, setPendingReviewItems] = useState([]);
  const [completedItems, setCompletedItems] = useState([]);
  const [loading, setLoading] = useState(true);

  // ─── Call drafts state ───
  const [callDrafts, setCallDrafts] = useState([]);
  const [callDraftsLoading, setCallDraftsLoading] = useState(false);
  const [selectedDraft, setSelectedDraft] = useState(null);
  const [draftActionLoading, setDraftActionLoading] = useState(null);

  // ─── Selection & detail state ───
  const [selectedItem, setSelectedItem] = useState(null);
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [selectedReviewItems, setSelectedReviewItems] = useState(new Set());

  // ─── Field editing state ───
  const [editedFields, setEditedFields] = useState({});
  const [deletedFields, setDeletedFields] = useState(new Set());
  const [renamedFields, setRenamedFields] = useState({});
  const [editingFieldKey, setEditingFieldKey] = useState(null);
  const [showAddFieldForm, setShowAddFieldForm] = useState(false);
  const [newFieldKey, setNewFieldKey] = useState('');
  const [newFieldValue, setNewFieldValue] = useState('');
  const [addedFields, setAddedFields] = useState({});

  // ─── Processing state ───
  const [processingAction, setProcessingAction] = useState(false);
  const [syncingEmails, setSyncingEmails] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState(null);
  const [syncStatus, setSyncStatus] = useState('');
  const [bulkProcessing, setBulkProcessing] = useState(false);
  const [approvalProgress, setApprovalProgress] = useState({ approved: 0, total: 20 });

  // ─── AI delegation state ───
  const [delegateToAI, setDelegateToAI] = useState(false);
  const [allowAutoProcess, setAllowAutoProcess] = useState(false);

  // ─── Email inbox deletion state ───
  const [deleteFromInboxGlobal, setDeleteFromInboxGlobal] = useState(false);
  const [deleteFromInboxOverride, setDeleteFromInboxOverride] = useState(null);

  // ─── Entity type selection state ───
  const [selectedEntityType, setSelectedEntityType] = useState(null);
  const [selectedLoanStage, setSelectedLoanStage] = useState('UW_RECEIVED');
  const [createNewLoan, setCreateNewLoan] = useState(false);

  // ─── No-match dialog state ───
  const [showNoMatchDialog, setShowNoMatchDialog] = useState(false);
  const [noMatchItemId, setNoMatchItemId] = useState(null);
  const [noMatchData, setNoMatchData] = useState(null);
  const [newBorrowerForm, setNewBorrowerForm] = useState({
    first_name: '', last_name: '', loan_number: '', referral_partner_id: '', loan_stage: 'NEW'
  });
  const [referralPartners, setReferralPartners] = useState([]);
  const [referralSearchTerm, setReferralSearchTerm] = useState('');
  const [referralSearchResults, setReferralSearchResults] = useState([]);
  const [showReferralDropdown, setShowReferralDropdown] = useState(false);
  const [selectedReferralPartner, setSelectedReferralPartner] = useState(null);
  const [showCreateReferralDialog, setShowCreateReferralDialog] = useState(false);
  const [newReferralPartner, setNewReferralPartner] = useState({
    name: '', company: '', email: '', phone: '', type: 'realtor'
  });

  // ─── Status correction modal state ───
  const [showStatusCorrectionModal, setShowStatusCorrectionModal] = useState(false);
  const [statusCorrectionData, setStatusCorrectionData] = useState(null);
  const [pendingApprovalItemId, setPendingApprovalItemId] = useState(null);
  const [selectedNewStatus, setSelectedNewStatus] = useState(null);

  // ─── Applied data summary modal state ───
  const [showAppliedDataModal, setShowAppliedDataModal] = useState(false);
  const [appliedDataSummary, setAppliedDataSummary] = useState(null);

  // Aliases for backward compat
  const pendingItems = autoProcessingItems;

  // ═══════════════════════════════════════
  // Data fetching
  // ═══════════════════════════════════════

  const fetchEmailProcessingSettings = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/user-settings/email-processing`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      if (response.ok) {
        const data = await response.json();
        setDeleteFromInboxGlobal(data.delete_from_inbox_after_processing || false);
      }
    } catch (error) { console.error('Error fetching email processing settings:', error); }
  };

  const fetchReferralPartners = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/referral-partners`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      if (response.ok) {
        const data = await response.json();
        setReferralPartners(data.partners || data || []);
      }
    } catch (error) { /* Silently handle */ }
  };

  const fetchPendingItems = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/pending`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      if (response.ok) {
        const data = await response.json();
        const allItems = data.items || [];
        const newMessages = [], autoProcess = [], needsReview = [];
        allItems.forEach(item => {
          const enrichedItem = {
            ...item,
            email_subject: item.email?.subject,
            email_from: item.email?.sender,
            email_received_at: item.email?.received_at,
            email_body: item.email?.body || item.email?.text_content || item.email?.html_content
          };
          if (item.auto_process_enabled || item.status === 'auto_processing') {
            autoProcess.push(enrichedItem);
          } else if (item.ai_completed || item.status === 'ai_completed') {
            needsReview.push({
              ...enrichedItem,
              needs_human_review: true,
              review_reason: item.review_reason ||
                (item.ai_confidence < 0.75 ? 'Low AI confidence' :
                item.match_confidence < 0.65 ? 'Low match confidence' :
                'AI completed - ready for review')
            });
          } else {
            newMessages.push(enrichedItem);
          }
        });
        setNewItems(newMessages);
        setAutoProcessingItems(autoProcess);
        setPendingReviewItems(needsReview);
      }
    } catch (error) { console.error('Error fetching pending items:', error); }
    finally {
      setLoading(false);
      setTimeout(() => triggerRecalculation(), 50);
    }
  };

  const fetchCompletedItems = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/completed?limit=50`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      if (response.ok) {
        const data = await response.json();
        setCompletedItems(data.items || []);
      }
    } catch (error) { console.error('Error fetching completed items:', error); }
  };

  const fetchCallDrafts = async () => {
    try {
      setCallDraftsLoading(true);
      const drafts = await emailDraftsAPI.getCallDrafts();
      setCallDrafts(drafts);
    } catch (error) { console.error('Error fetching call drafts:', error); }
    finally { setCallDraftsLoading(false); }
  };

  // ═══════════════════════════════════════
  // Email sync
  // ═══════════════════════════════════════

  const syncEmails = async (silent = false) => {
    try {
      if (!silent) { setSyncingEmails(true); setSyncStatus('Syncing emails...'); }
      const token = getToken();
      const gmailStatus = await fetch(`${API_BASE_URL}/api/v1/gmail/status`, {
        headers: { 'Authorization': `Bearer ${token}` }
      }).then(r => r.ok ? r.json() : null).catch(() => null);
      const microsoftStatus = await fetch(`${API_BASE_URL}/api/v1/microsoft/status/outlook_email`, {
        headers: { 'Authorization': `Bearer ${token}` }
      }).then(r => r.ok ? r.json() : null).catch((e) => { console.error('Microsoft status check error:', e); return null; });
      console.log('Email service status check:', { gmailStatus, microsoftStatus });

      let response, syncEndpoint;
      if (gmailStatus?.connected) {
        syncEndpoint = `${API_BASE_URL}/api/v1/gmail/sync`;
        response = await fetch(syncEndpoint, { method: 'POST', headers: { 'Authorization': `Bearer ${token}` } });
      } else if (microsoftStatus?.data?.connected) {
        syncEndpoint = `${API_BASE_URL}/api/v1/microsoft/email/sync`;
        response = await fetch(syncEndpoint, { method: 'POST', headers: { 'Authorization': `Bearer ${token}` } });
      } else {
        if (!silent) setSyncStatus('Emails are synced via Claude Code. Refreshing view...');
        await fetchPendingItems(); await fetchCompletedItems();
        if (!silent) { setSyncingEmails(false); setSyncStatus('View refreshed. Use Claude Code to sync new emails.'); }
        return;
      }

      if (response.ok) {
        const data = await response.json();
        setLastSyncTime(new Date());
        if (!silent) {
          setSyncStatus(data.message || `Synced ${data.processed_count || 0} emails`);
          console.log('Sync result:', data);
          fetchPendingItems(); fetchCompletedItems();
          setTimeout(() => setSyncStatus(''), 5000);
        }
      } else if (!silent) {
        let errorMessage = 'Sync failed - please try again';
        try {
          const errorData = await response.json();
          if (response.status === 404 && errorData.detail) {
            errorMessage = `Warning: ${errorData.detail}. Go to Settings to reconnect.`;
          } else if (response.status === 401 || errorData.detail === 'needs_reauth' ||
                     (errorData.detail && (errorData.detail.includes('token') || errorData.detail.includes('expired')))) {
            const confirmReconnect = window.confirm('Your Microsoft session has expired. Would you like to go to Settings to reconnect?');
            if (confirmReconnect) window.location.href = '/settings?tab=integrations';
            errorMessage = 'Warning: Microsoft session expired. Please reconnect in Settings.';
          } else if (errorData.detail) { errorMessage = `Warning: ${errorData.detail}`; }
        } catch (e) { /* Use default */ }
        setSyncStatus(errorMessage);
        setTimeout(() => setSyncStatus(''), 5000);
      }
    } catch (error) {
      console.error('Error syncing emails:', error);
      if (!silent) { setSyncStatus('Warning: Sync failed - please try again'); setTimeout(() => setSyncStatus(''), 3000); }
    } finally {
      if (!silent) setSyncingEmails(false);
    }
  };

  // ═══════════════════════════════════════
  // Effects
  // ═══════════════════════════════════════

  useEffect(() => {
    fetchPendingItems();
    fetchCompletedItems();
    fetchReferralPartners();
    fetchEmailProcessingSettings();
    const syncInterval = setInterval(() => syncEmails(true), 5 * 60 * 1000);
    syncEmails(true);
    return () => clearInterval(syncInterval);
  }, []);

  useEffect(() => { setDeleteFromInboxOverride(null); }, [selectedItem?.id]);

  // ═══════════════════════════════════════
  // Call draft handlers
  // ═══════════════════════════════════════

  const handleSendDraft = async (draftId) => {
    try {
      setDraftActionLoading(draftId);
      await emailDraftsAPI.send(draftId);
      setCallDrafts(prev => prev.filter(d => d.id !== draftId));
      if (selectedDraft?.id === draftId) setSelectedDraft(null);
    } catch (error) {
      console.error('Error sending draft:', error);
      toast.error('Failed to send email: ' + (error.response?.data?.detail || error.message));
    } finally { setDraftActionLoading(null); }
  };

  const handleDeleteDraft = async (draftId) => {
    try {
      setDraftActionLoading(draftId);
      await emailDraftsAPI.delete(draftId);
      setCallDrafts(prev => prev.filter(d => d.id !== draftId));
      if (selectedDraft?.id === draftId) setSelectedDraft(null);
    } catch (error) { console.error('Error deleting draft:', error); }
    finally { setDraftActionLoading(null); }
  };

  // ═══════════════════════════════════════
  // Referral partner handlers
  // ═══════════════════════════════════════

  const searchReferralPartners = (searchTerm) => {
    setReferralSearchTerm(searchTerm);
    if (!searchTerm.trim()) { setReferralSearchResults([]); setShowReferralDropdown(false); return; }
    const searchLower = searchTerm.toLowerCase();
    const results = referralPartners.filter(partner => {
      const name = (partner.name || '').toLowerCase();
      const company = (partner.company || partner.company_name || '').toLowerCase();
      return name.includes(searchLower) || company.includes(searchLower);
    });
    setReferralSearchResults(results);
    setShowReferralDropdown(true);
  };

  const selectReferralPartner = (partner) => {
    setSelectedReferralPartner(partner);
    setNewBorrowerForm(prev => ({ ...prev, referral_partner_id: partner.id }));
    setReferralSearchTerm(partner.name || partner.company || '');
    setShowReferralDropdown(false);
  };

  const clearReferralPartner = () => {
    setSelectedReferralPartner(null);
    setNewBorrowerForm(prev => ({ ...prev, referral_partner_id: '' }));
    setReferralSearchTerm('');
    setReferralSearchResults([]);
  };

  const handleCreateReferralPartner = async () => {
    if (!newReferralPartner.name.trim()) { toast.error('Please enter a name for the referral partner'); return; }
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/referral-partners`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(newReferralPartner)
      });
      if (response.ok) {
        const created = await response.json();
        setReferralPartners(prev => [...prev, created]);
        selectReferralPartner(created);
        setShowCreateReferralDialog(false);
        setNewReferralPartner({ name: '', company: '', email: '', phone: '', type: 'realtor' });
      } else {
        const error = await response.json();
        toast.error(`Failed to create referral partner: ${error.detail || 'Unknown error'}`);
      }
    } catch (error) { console.error('Error creating referral partner:', error); toast.error('Error creating referral partner'); }
  };

  // ═══════════════════════════════════════
  // Approve / reject / delete handlers
  // ═══════════════════════════════════════

  const proceedWithApproval = async (itemId, options = {}) => {
    try {
      setProcessingAction(true);
      if (!options.skipStatusCheck) {
        try {
          const checkResponse = await fetch(`${API_BASE_URL}/api/v1/reconciliation/pre-approval-check/${itemId}`, {
            method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' }
          });
          if (checkResponse.ok) {
            const checkData = await checkResponse.json();
            if (checkData.needs_status_update) {
              setStatusCorrectionData(checkData); setPendingApprovalItemId(itemId);
              setSelectedNewStatus(checkData.suggested_status); setShowStatusCorrectionModal(true);
              setProcessingAction(false); return;
            }
          }
        } catch (checkError) { console.log('Pre-approval check failed, proceeding:', checkError); }
      }
      const corrections = Object.keys(editedFields).length > 0 ? editedFields : null;
      const deletedFieldsList = deletedFields.size > 0 ? Array.from(deletedFields) : null;
      const renamedFieldsObj = Object.keys(renamedFields).length > 0 ? renamedFields : null;
      const shouldDeleteFromInbox = deleteFromInboxOverride !== null ? deleteFromInboxOverride : deleteFromInboxGlobal;
      const requestBody = {
        extracted_data_id: itemId, corrections, deleted_fields: deletedFieldsList,
        renamed_fields: renamedFieldsObj, delegate_to_ai: delegateToAI, allow_auto_process: allowAutoProcess,
        email_intent: selectedItem?.email_intent, recommended_action: selectedItem?.recommended_action,
        delete_from_inbox: shouldDeleteFromInbox, email_message_id: selectedItem?.email_message_id || selectedItem?.message_id
      };
      if (options.targetEntityType || selectedEntityType) requestBody.target_entity_type = options.targetEntityType || selectedEntityType;
      if (options.createNewLoan || createNewLoan) { requestBody.create_new_loan = true; requestBody.loan_stage = options.loanStage || selectedLoanStage; }
      if (options.updateStatusTo) requestBody.update_status_to = options.updateStatusTo;

      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
        method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      });
      if (response.ok) {
        const responseData = await response.json();
        setAppliedDataSummary({
          entityName: responseData.entity_name || statusCorrectionData?.entity_name || selectedItem?.match_name || 'Borrower',
          entityType: responseData.entity_type, entityId: responseData.entity_id,
          appliedFields: responseData.applied_fields || [], statusUpdated: responseData.status_updated,
          oldStatus: responseData.old_status, newStatus: responseData.new_status
        });
        setShowAppliedDataModal(true);
        setNewItems(prev => prev.filter(item => item.id !== itemId));
        setAutoProcessingItems(prev => prev.filter(item => item.id !== itemId));
        setPendingReviewItems(prev => prev.filter(item => item.id !== itemId));
        setSelectedItem(null); setEditedFields({}); setDeletedFields(new Set()); setRenamedFields({});
        setEditingFieldKey(null); setDelegateToAI(false); setAllowAutoProcess(false);
        setSelectedEntityType(null); setCreateNewLoan(false); setStatusCorrectionData(null); setPendingApprovalItemId(null);
        fetchCompletedItems();
      } else {
        const errorData = await response.json().catch(() => ({}));
        toast.error(`Failed to approve item: ${errorData.detail || response.statusText}`);
      }
    } catch (error) { console.error('Error approving item:', error); toast.error(`Error approving item: ${error.message}`); }
    finally { setProcessingAction(false); }
  };

  const handleApprove = async (itemId) => {
    try {
      setProcessingAction(true);
      const checkResponse = await fetch(`${API_BASE_URL}/api/v1/reconciliation/check-match/${itemId}`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      if (checkResponse.ok) {
        const matchData = await checkResponse.json();
        if (!matchData.has_match) {
          setNoMatchItemId(itemId);
          setNoMatchData(matchData);
          const fields = matchData.fields || {};
          const getFieldValue = (fn) => { const f = fields[fn]; return typeof f === 'object' ? f.value : f; };
          let firstName = getFieldValue('first_name') || getFieldValue('borrower_first_name') || '';
          let lastName = getFieldValue('last_name') || getFieldValue('borrower_last_name') || '';
          let loanNumber = getFieldValue('loan_number') || getFieldValue('loan_id') || getFieldValue('file_number') || '';
          if (!firstName && !lastName) {
            const fullName = matchData.extracted_name || getFieldValue('borrower_name') || '';
            if (fullName) { const parts = fullName.trim().split(' '); firstName = parts[0] || ''; lastName = parts.slice(1).join(' ') || ''; }
          }
          setNewBorrowerForm({ first_name: firstName, last_name: lastName, loan_number: loanNumber, loan_stage: selectedLoanStage || 'NEW', referral_partner_id: '' });
          setShowNoMatchDialog(true);
          setProcessingAction(false);
          return;
        }
      }
      await proceedWithApproval(itemId);
    } catch (error) { console.error('Error approving item:', error); toast.error(`Error approving item: ${error.message}`); setProcessingAction(false); }
  };

  const handleStatusCorrectionConfirm = async () => {
    setShowStatusCorrectionModal(false);
    if (pendingApprovalItemId) await proceedWithApproval(pendingApprovalItemId, { skipStatusCheck: true, updateStatusTo: selectedNewStatus });
  };
  const handleStatusCorrectionSkip = async () => {
    setShowStatusCorrectionModal(false);
    if (pendingApprovalItemId) await proceedWithApproval(pendingApprovalItemId, { skipStatusCheck: true });
  };
  const handleStatusCorrectionCancel = () => {
    setShowStatusCorrectionModal(false); setStatusCorrectionData(null); setPendingApprovalItemId(null); setSelectedNewStatus(null); setProcessingAction(false);
  };

  const handleCreateBorrower = async () => {
    try {
      setProcessingAction(true);
      if (!newBorrowerForm.first_name || !newBorrowerForm.last_name) { toast.error('Please enter first name and last name'); setProcessingAction(false); return; }
      const itemId = noMatchItemId;
      setShowNoMatchDialog(false); setNoMatchItemId(null); setNoMatchData(null);
      const corrections = { borrower_name: `${newBorrowerForm.first_name} ${newBorrowerForm.last_name}` };
      if (newBorrowerForm.loan_number) corrections.loan_number = newBorrowerForm.loan_number;
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
        method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ extracted_data_id: itemId, corrections, create_new_loan: true, loan_stage: newBorrowerForm.loan_stage, loan_number: newBorrowerForm.loan_number || null, target_entity_type: 'loan' })
      });
      if (response.ok) {
        const responseData = await response.json();
        setAppliedDataSummary({ entityName: responseData.entity_name || `${newBorrowerForm.first_name} ${newBorrowerForm.last_name}`, entityType: responseData.entity_type, entityId: responseData.entity_id, appliedFields: [], statusUpdated: false, isNewBorrower: true });
        setShowAppliedDataModal(true);
        setNewItems(prev => prev.filter(item => item.id !== itemId));
        setAutoProcessingItems(prev => prev.filter(item => item.id !== itemId));
        setPendingReviewItems(prev => prev.filter(item => item.id !== itemId));
        setSelectedItem(null); setEditedFields({}); setReferralSearchTerm(''); setSelectedReferralPartner(null);
        fetchCompletedItems();
      } else { const errorData = await response.json().catch(() => ({})); toast.error(`Failed to create borrower: ${errorData.detail || response.statusText}`); }
    } catch (error) { console.error('Error creating borrower:', error); toast.error(`Error creating borrower: ${error.message}`); }
    finally { setProcessingAction(false); }
  };

  const handleCancelNoMatch = () => {
    setShowNoMatchDialog(false); setNoMatchItemId(null); setNoMatchData(null); setProcessingAction(false);
    setReferralSearchTerm(''); setSelectedReferralPartner(null); setShowReferralDropdown(false);
  };

  const handleReject = async (itemId, reason) => {
    try {
      setProcessingAction(true);
      const shouldDeleteFromInbox = deleteFromInboxOverride !== null ? deleteFromInboxOverride : deleteFromInboxGlobal;
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, {
        method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ extracted_data_id: itemId, reason, delete_from_inbox: shouldDeleteFromInbox, email_message_id: selectedItem?.email_message_id || selectedItem?.message_id })
      });
      if (response.ok) {
        setAutoProcessingItems(prev => prev.filter(item => item.id !== itemId));
        setPendingReviewItems(prev => prev.filter(item => item.id !== itemId));
        setSelectedItem(null); setEditedFields({}); setDeleteFromInboxOverride(null);
        fetchCompletedItems();
      } else { const errorData = await response.json().catch(() => ({})); toast.error(`Failed to reject item: ${errorData.detail || response.statusText}`); }
    } catch (error) { console.error('Error rejecting item:', error); toast.error(`Error rejecting item: ${error.message}`); }
    finally { setProcessingAction(false); }
  };

  const handleDelete = async (itemId, activeTab) => {
    try {
      setProcessingAction(true);
      const shouldDeleteFromInbox = deleteFromInboxOverride !== null ? deleteFromInboxOverride : deleteFromInboxGlobal;
      const emailMessageId = selectedItem?.email_message_id || selectedItem?.message_id;
      let url = `${API_BASE_URL}/api/v1/reconciliation/items/${itemId}`;
      if (shouldDeleteFromInbox && emailMessageId) url += `?delete_from_inbox=true&email_message_id=${encodeURIComponent(emailMessageId)}`;
      const response = await fetch(url, { method: 'DELETE', headers: { 'Authorization': `Bearer ${getToken()}` } });
      if (response.ok) {
        const getCurrentList = () => {
          switch (activeTab) {
            case 'new': return newItems; case 'autoProcessing': return autoProcessingItems;
            case 'pendingReview': return pendingReviewItems; case 'completed': return completedItems;
            default: return newItems;
          }
        };
        const currentList = getCurrentList();
        const currentIndex = currentList.findIndex(item => item.id === itemId);
        const nextItem = currentList[currentIndex + 1] || currentList[currentIndex - 1] || null;
        setNewItems(prev => prev.filter(item => item.id !== itemId));
        setAutoProcessingItems(prev => prev.filter(item => item.id !== itemId));
        setPendingReviewItems(prev => prev.filter(item => item.id !== itemId));
        setCompletedItems(prev => prev.filter(item => item.id !== itemId));
        if (nextItem && nextItem.id !== itemId) setSelectedItem(nextItem); else setSelectedItem(null);
        setEditedFields({}); setDeleteFromInboxOverride(null);
      } else { const errorData = await response.json().catch(() => ({})); toast.error(`Failed to delete item: ${errorData.detail || response.statusText}`); }
    } catch (error) { console.error('Error deleting item:', error); toast.error(`Error deleting item: ${error.message}`); }
    finally { setProcessingAction(false); }
  };

  // ═══════════════════════════════════════
  // Field manipulation handlers
  // ═══════════════════════════════════════

  const handleFieldEdit = (fieldName, newValue) => setEditedFields(prev => ({ ...prev, [fieldName]: newValue }));
  const handleFieldDelete = (fieldName) => setDeletedFields(prev => { const s = new Set(prev); s.add(fieldName); return s; });
  const handleFieldRestore = (fieldName) => setDeletedFields(prev => { const s = new Set(prev); s.delete(fieldName); return s; });
  const handleAddField = () => {
    if (!newFieldKey.trim() || !newFieldValue.trim()) return;
    const fieldKey = newFieldKey.toLowerCase().replace(/\s+/g, '_');
    setAddedFields(prev => ({ ...prev, [fieldKey]: { value: newFieldValue, confidence: 1.0 } }));
    setNewFieldKey(''); setNewFieldValue(''); setShowAddFieldForm(false);
  };
  const handleRemoveAddedField = (fieldKey) => setAddedFields(prev => { const nf = { ...prev }; delete nf[fieldKey]; return nf; });
  const handleFieldRename = (oldKey, newKey) => { if (newKey && newKey !== oldKey) setRenamedFields(prev => ({ ...prev, [oldKey]: newKey })); setEditingFieldKey(null); };
  const handleFieldRenameUndo = (oldKey) => setRenamedFields(prev => { const nf = { ...prev }; delete nf[oldKey]; return nf; });
  const getEffectiveFieldKey = (originalKey) => renamedFields[originalKey] || originalKey;

  // ═══════════════════════════════════════
  // Selection handlers
  // ═══════════════════════════════════════

  const handleSelectItem = (item) => {
    setSelectedItem(item); setEditedFields({}); setDeletedFields(new Set()); setRenamedFields({});
    setEditingFieldKey(null); setAddedFields({}); setShowAddFieldForm(false); setNewFieldKey(''); setNewFieldValue('');
    setSelectedEntityType(null); setCreateNewLoan(false); setSelectedLoanStage('UW_RECEIVED');
    setDelegateToAI(false); setAllowAutoProcess(false);
  };

  const toggleItemSelection = (itemId) => {
    setSelectedItems(prev => { const s = new Set(prev); if (s.has(itemId)) s.delete(itemId); else if (s.size < 20) s.add(itemId); return s; });
  };
  const selectAll = () => setSelectedItems(new Set(pendingItems.slice(0, 20).map(i => i.id)));
  const deselectAll = () => setSelectedItems(new Set());

  const bulkApprove = async () => {
    if (selectedItems.size === 0) { toast.error('Please select items to approve'); return; }
    setBulkProcessing(true); let successCount = 0;
    for (const itemId of selectedItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
          method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ extracted_data_id: itemId, corrections: null })
        });
        if (response.ok) { successCount++; setApprovalProgress(prev => ({ ...prev, approved: prev.approved + 1 })); }
      } catch (error) { console.error(`Error approving item ${itemId}:`, error); }
    }
    await fetchPendingItems(); setSelectedItems(new Set()); setBulkProcessing(false);
    toast.success(`Successfully approved ${successCount} out of ${selectedItems.size} items`);
  };

  const bulkReject = async () => {
    if (selectedItems.size === 0) { toast.error('Please select items to reject'); return; }
    const reason = prompt('Enter reason for rejection:'); if (!reason) return;
    setBulkProcessing(true); let successCount = 0;
    for (const itemId of selectedItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, {
          method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ extracted_data_id: itemId, reason })
        });
        if (response.ok) successCount++;
      } catch (error) { console.error(`Error rejecting item ${itemId}:`, error); }
    }
    await fetchPendingItems(); setSelectedItems(new Set()); setBulkProcessing(false);
    toast.success(`Successfully rejected ${successCount} out of ${selectedItems.size} items`);
  };

  // Pending Review bulk actions
  const toggleReviewItemSelection = (itemId) => {
    setSelectedReviewItems(prev => { const s = new Set(prev); if (s.has(itemId)) s.delete(itemId); else s.add(itemId); return s; });
  };
  const selectAllReviewItems = () => setSelectedReviewItems(new Set(pendingReviewItems.map(i => i.id)));
  const deselectAllReviewItems = () => setSelectedReviewItems(new Set());

  const bulkDeleteReviewItems = async () => {
    if (selectedReviewItems.size === 0) return;
    const itemsToDelete = new Set(selectedReviewItems);
    setPendingReviewItems(prev => prev.filter(item => !itemsToDelete.has(item.id)));
    setSelectedReviewItems(new Set());
    for (const itemId of itemsToDelete) {
      fetch(`${API_BASE_URL}/api/v1/reconciliation/items/${itemId}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${getToken()}` } }).catch(err => console.error(`Delete failed for ${itemId}:`, err));
    }
  };

  const bulkApproveReviewItems = async () => {
    if (selectedReviewItems.size === 0) return;
    const itemsToApprove = new Set(selectedReviewItems);
    setPendingReviewItems(prev => prev.filter(item => !itemsToApprove.has(item.id)));
    setSelectedReviewItems(new Set());
    for (const itemId of itemsToApprove) {
      fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, { method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ extracted_data_id: itemId, corrections: null }) }).catch(err => console.error(`Approve failed for ${itemId}:`, err));
    }
  };

  const bulkBlockSenders = async () => {
    if (selectedReviewItems.size === 0) return;
    const sendersToBlock = new Set();
    const itemsToRemove = new Set(selectedReviewItems);
    selectedReviewItems.forEach(itemId => { const item = pendingReviewItems.find(i => i.id === itemId); if (item?.email_from) sendersToBlock.add(item.email_from); });
    setPendingReviewItems(prev => prev.filter(item => !itemsToRemove.has(item.id)));
    setSelectedReviewItems(new Set());
    for (const sender of sendersToBlock) {
      fetch(`${API_BASE_URL}/api/v1/reconciliation/block-sender`, { method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ sender_email: sender }) }).catch(err => console.error(`Block sender failed for ${sender}:`, err));
    }
    for (const itemId of itemsToRemove) {
      fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, { method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ extracted_data_id: itemId, reason: 'Sender blocked by user' }) }).catch(err => console.error(`Reject failed for ${itemId}:`, err));
    }
  };

  // ═══════════════════════════════════════
  // Shared prop bundles
  // ═══════════════════════════════════════

  const fieldEditProps = {
    editedFields, deletedFields, renamedFields, addedFields, editingFieldKey,
    showAddFieldForm, newFieldKey, newFieldValue,
    handleFieldEdit, handleFieldDelete, handleFieldRestore, handleFieldRename, handleFieldRenameUndo,
    handleAddField, handleRemoveAddedField, setEditingFieldKey, setShowAddFieldForm,
    setNewFieldKey, setNewFieldValue, setAddedFields, getEffectiveFieldKey,
  };

  const entityTypeProps = {
    selectedEntityType, setSelectedEntityType, createNewLoan, setCreateNewLoan,
    selectedLoanStage, setSelectedLoanStage,
  };

  return {
    // List data
    newItems, autoProcessingItems, pendingReviewItems, completedItems, pendingItems, loading,
    // Call drafts
    callDrafts, callDraftsLoading, selectedDraft, setSelectedDraft, draftActionLoading,
    fetchCallDrafts, handleSendDraft, handleDeleteDraft,
    // Selection
    selectedItem, setSelectedItem, selectedItems, selectedReviewItems,
    handleSelectItem,
    // Sync
    syncingEmails, lastSyncTime, syncStatus, syncEmails,
    // Actions
    processingAction, bulkProcessing, approvalProgress,
    handleApprove, handleReject, handleDelete, handleCreateBorrower, handleCancelNoMatch,
    // Bulk actions
    toggleItemSelection, selectAll, deselectAll, bulkApprove, bulkReject,
    toggleReviewItemSelection, selectAllReviewItems, deselectAllReviewItems,
    bulkDeleteReviewItems, bulkApproveReviewItems, bulkBlockSenders,
    // AI delegation
    delegateToAI, setDelegateToAI, allowAutoProcess, setAllowAutoProcess,
    // Delete from inbox
    deleteFromInboxOverride, setDeleteFromInboxOverride, deleteFromInboxGlobal,
    // Entity type
    entityTypeProps,
    // Field editing
    fieldEditProps,
    editedFields, setEditedFields, deletedFields, renamedFields, editingFieldKey,
    handleFieldEdit, handleFieldDelete, handleFieldRestore, handleFieldRename, handleFieldRenameUndo,
    setEditingFieldKey, getEffectiveFieldKey,
    // No-match dialog
    showNoMatchDialog, noMatchData, newBorrowerForm, setNewBorrowerForm,
    referralSearchTerm, searchReferralPartners,
    showReferralDropdown, setShowReferralDropdown,
    referralSearchResults, selectReferralPartner,
    selectedReferralPartner, clearReferralPartner,
    showCreateReferralDialog, setShowCreateReferralDialog,
    newReferralPartner, setNewReferralPartner, handleCreateReferralPartner,
    // Status correction modal
    showStatusCorrectionModal, statusCorrectionData,
    selectedNewStatus, setSelectedNewStatus,
    handleStatusCorrectionConfirm, handleStatusCorrectionSkip, handleStatusCorrectionCancel,
    // Applied data modal
    showAppliedDataModal, setShowAppliedDataModal, appliedDataSummary,
  };
}
