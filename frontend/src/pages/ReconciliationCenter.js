import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLayoutFix } from '../hooks/useLayoutFix';
import './ReconciliationCenter.css';

import {
  NewTab,
  AutoProcessingTab,
  PendingReviewTab,
  CompletedTab,
  CallDraftsTab,
  NoMatchDialog,
  StatusCorrectionModal,
  AppliedDataModal,
  useReconciliation,
} from './reconciliation-center';

/**
 * ReconciliationCenter - Thin orchestrator component.
 * Owns layout/tab state only; all data, handlers, and business logic
 * live in the useReconciliation hook.
 */
function ReconciliationCenter() {
  const navigate = useNavigate();
  const { containerRef, triggerRecalculation } = useLayoutFix([]);
  const [activeTab, setActiveTab] = useState('new');

  const rc = useReconciliation({ triggerRecalculation, navigate });

  // Trigger resize when loading/tab/selection changes
  useEffect(() => {
    if (!rc.loading) {
      const timer = setTimeout(() => window.dispatchEvent(new Event('resize')), 100);
      return () => clearTimeout(timer);
    }
  }, [rc.loading, activeTab, rc.selectedItem]);

  // ═══════════════════════════════════════
  // Render
  // ═══════════════════════════════════════

  if (rc.loading) {
    return (
      <div className="reconciliation-page">
        <div className="reconciliation-container">
          <div className="loading-state"><div className="spinner"></div><p>Loading reconciliation items...</p></div>
        </div>
      </div>
    );
  }

  return (
    <div className="reconciliation-page" ref={containerRef}>
      <div className="reconciliation-container">
        {/* Header with tabs and sync */}
        <div className="reconciliation-header">
          <div className="header-content">
            <h1>Data Reconciliation Center</h1>
            <p>Review and approve AI-extracted loan data from emails</p>
            <div className="tab-navigation">
              <button className={`tab-button ${activeTab === 'new' ? 'active' : ''}`} onClick={() => setActiveTab('new')}>New ({rc.newItems.length})</button>
              <button className={`tab-button ${activeTab === 'autoProcessing' ? 'active' : ''}`} onClick={() => setActiveTab('autoProcessing')}>Auto-Processing ({rc.autoProcessingItems.length})</button>
              <button className={`tab-button ${activeTab === 'pendingReview' ? 'active' : ''}`} onClick={() => setActiveTab('pendingReview')}>Pending Review ({rc.pendingReviewItems.length})</button>
              <button className={`tab-button ${activeTab === 'completed' ? 'active' : ''}`} onClick={() => setActiveTab('completed')}>Completed ({rc.completedItems.length})</button>
              <button className={`tab-button ${activeTab === 'callDrafts' ? 'active' : ''}`} onClick={() => { setActiveTab('callDrafts'); rc.fetchCallDrafts(); }}>Call Drafts ({rc.callDrafts.length})</button>
            </div>
          </div>
          <div className="header-actions">
            <button className={`sync-button ${rc.syncingEmails ? 'syncing' : ''}`} onClick={() => rc.syncEmails(false)} disabled={rc.syncingEmails}>
              {rc.syncingEmails ? (<><span className="spinner-small"></span>Syncing...</>) : (<><span className="sync-icon">&#10227;</span>Sync Emails Now</>)}
            </button>
            {rc.syncStatus && <div className={`sync-status ${rc.syncStatus.includes('Synced') ? 'success' : 'error'}`}>{rc.syncStatus}</div>}
            {rc.lastSyncTime && !rc.syncStatus && <div className="last-sync">Last synced: {rc.lastSyncTime.toLocaleTimeString()}</div>}
          </div>
        </div>

        {/* Tab content */}
        {activeTab === 'new' && (
          <NewTab
            newItems={rc.newItems} selectedItem={rc.selectedItem} handleSelectItem={rc.handleSelectItem}
            handleDelete={(id) => rc.handleDelete(id, activeTab)} handleApprove={rc.handleApprove} handleReject={rc.handleReject}
            processingAction={rc.processingAction} setSelectedItem={rc.setSelectedItem}
            delegateToAI={rc.delegateToAI} setDelegateToAI={rc.setDelegateToAI}
            deleteFromInboxOverride={rc.deleteFromInboxOverride} setDeleteFromInboxOverride={rc.setDeleteFromInboxOverride}
            deleteFromInboxGlobal={rc.deleteFromInboxGlobal}
            {...rc.entityTypeProps} {...rc.fieldEditProps}
          />
        )}

        {activeTab === 'autoProcessing' && (
          <AutoProcessingTab
            autoProcessingItems={rc.autoProcessingItems} pendingItems={rc.pendingItems}
            selectedItem={rc.selectedItem} selectedItems={rc.selectedItems}
            handleSelectItem={rc.handleSelectItem} toggleItemSelection={rc.toggleItemSelection}
            selectAll={rc.selectAll} deselectAll={rc.deselectAll} bulkApprove={rc.bulkApprove}
            bulkReject={rc.bulkReject} bulkProcessing={rc.bulkProcessing}
            handleApprove={rc.handleApprove} handleReject={rc.handleReject} processingAction={rc.processingAction}
            editedFields={rc.editedFields} deletedFields={rc.deletedFields} renamedFields={rc.renamedFields}
            editingFieldKey={rc.editingFieldKey} handleFieldEdit={rc.handleFieldEdit}
            handleFieldDelete={rc.handleFieldDelete} handleFieldRestore={rc.handleFieldRestore}
            handleFieldRename={rc.handleFieldRename} handleFieldRenameUndo={rc.handleFieldRenameUndo}
            setEditingFieldKey={rc.setEditingFieldKey} getEffectiveFieldKey={rc.getEffectiveFieldKey}
            setSelectedItem={rc.setSelectedItem} setEditedFields={rc.setEditedFields}
            delegateToAI={rc.delegateToAI} setDelegateToAI={rc.setDelegateToAI}
          />
        )}

        {activeTab === 'pendingReview' && (
          <PendingReviewTab
            pendingReviewItems={rc.pendingReviewItems} selectedItem={rc.selectedItem}
            selectedReviewItems={rc.selectedReviewItems} bulkProcessing={rc.bulkProcessing}
            handleSelectItem={rc.handleSelectItem} handleDelete={(id) => rc.handleDelete(id, activeTab)}
            handleApprove={rc.handleApprove} handleReject={rc.handleReject} processingAction={rc.processingAction}
            toggleReviewItemSelection={rc.toggleReviewItemSelection} selectAllReviewItems={rc.selectAllReviewItems}
            deselectAllReviewItems={rc.deselectAllReviewItems} bulkDeleteReviewItems={rc.bulkDeleteReviewItems}
            bulkApproveReviewItems={rc.bulkApproveReviewItems} bulkBlockSenders={rc.bulkBlockSenders}
            allowAutoProcess={rc.allowAutoProcess} setAllowAutoProcess={rc.setAllowAutoProcess}
            setSelectedItem={rc.setSelectedItem}
            {...rc.entityTypeProps} {...rc.fieldEditProps}
          />
        )}

        {activeTab === 'completed' && (
          <CompletedTab
            completedItems={rc.completedItems} selectedItem={rc.selectedItem}
            handleSelectItem={rc.handleSelectItem} handleDelete={(id) => rc.handleDelete(id, activeTab)}
            setSelectedItem={rc.setSelectedItem}
          />
        )}

        {activeTab === 'callDrafts' && (
          <CallDraftsTab
            callDrafts={rc.callDrafts} callDraftsLoading={rc.callDraftsLoading}
            selectedDraft={rc.selectedDraft} setSelectedDraft={rc.setSelectedDraft}
            handleSendDraft={rc.handleSendDraft} handleDeleteDraft={rc.handleDeleteDraft}
            draftActionLoading={rc.draftActionLoading}
          />
        )}
      </div>

      {/* Modals */}
      {rc.showNoMatchDialog && (
        <NoMatchDialog
          noMatchData={rc.noMatchData} newBorrowerForm={rc.newBorrowerForm} setNewBorrowerForm={rc.setNewBorrowerForm}
          processingAction={rc.processingAction} handleCreateBorrower={rc.handleCreateBorrower} handleCancelNoMatch={rc.handleCancelNoMatch}
          referralSearchTerm={rc.referralSearchTerm} searchReferralPartners={rc.searchReferralPartners}
          showReferralDropdown={rc.showReferralDropdown} setShowReferralDropdown={rc.setShowReferralDropdown}
          referralSearchResults={rc.referralSearchResults} selectReferralPartner={rc.selectReferralPartner}
          selectedReferralPartner={rc.selectedReferralPartner} clearReferralPartner={rc.clearReferralPartner}
          showCreateReferralDialog={rc.showCreateReferralDialog} setShowCreateReferralDialog={rc.setShowCreateReferralDialog}
          newReferralPartner={rc.newReferralPartner} setNewReferralPartner={rc.setNewReferralPartner}
          handleCreateReferralPartner={rc.handleCreateReferralPartner}
        />
      )}

      {rc.showStatusCorrectionModal && rc.statusCorrectionData && (
        <StatusCorrectionModal
          statusCorrectionData={rc.statusCorrectionData} selectedNewStatus={rc.selectedNewStatus}
          setSelectedNewStatus={rc.setSelectedNewStatus} onConfirm={rc.handleStatusCorrectionConfirm}
          onSkip={rc.handleStatusCorrectionSkip} onCancel={rc.handleStatusCorrectionCancel}
        />
      )}

      {rc.showAppliedDataModal && rc.appliedDataSummary && (
        <AppliedDataModal
          appliedDataSummary={rc.appliedDataSummary} onClose={() => rc.setShowAppliedDataModal(false)}
          onViewProfile={() => {
            rc.setShowAppliedDataModal(false);
            const route = rc.appliedDataSummary.entityType === 'loan' ? `/loans/${rc.appliedDataSummary.entityId}` : `/leads/${rc.appliedDataSummary.entityId}`;
            navigate(route);
          }}
        />
      )}
    </div>
  );
}

export default ReconciliationCenter;
