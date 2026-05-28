import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import ActionSidebar from '../components/ActionSidebar';
import './AILandingPage.css';
import { getToken } from '../utils/tokenStore';
import {
  LeftSidebar,
  ChatArea,
  ChatInput,
  TaskSidebar,
  ReconciliationSidebar,
  FeedbackModal,
  ContextMenu,
  EmailCampaignPreview,
  TextCampaignPreview,
  BulkUpdatePreview,
  VoicemailCampaignPreview,
  PipelineReportPreview,
  ChatResponseComponent,
  TaskPrioritiesComponent,
  AccountabilityReviewComponent,
  LeadPreviewComponent,
  useChatSession,
  useAIMessaging,
  useReconciliation
} from '../components/ai-landing';
// Note: EmailDropZone wrapper removed - App.js already wraps with EmailDropZone globally

function AILandingPage() {
  const navigate = useNavigate();

  // Redirect to login if no token
  useEffect(() => {
    const token = getToken();
    if (!token) navigate('/login');
  }, [navigate]);

  // --- Chat session management (history, projects, reports, drag-and-drop) ---
  const session = useChatSession();

  // --- AI messaging, streaming, tasks, feedback ---
  const ai = useAIMessaging({
    messages: session.messages,
    setMessages: session.setMessages,
    sessionId: session.sessionId,
    setSessionId: session.setSessionId,
    conversationHistory: session.conversationHistory,
    updateConversationHistory: session.updateConversationHistory
  });

  // --- Reconciliation sidebar ---
  const recon = useReconciliation();

  // Reset extras when starting new chat or clearing
  const resetExtras = () => {
    ai.setTaskListData(null);
    ai.setSelectedTask(null);
    ai.setStructuredContent(null);
    ai.setShowRightSidebar(false);
  };

  const handleNewChat = () => session.handleNewChat(resetExtras);
  const handleClearContent = () => session.handleClearContent(resetExtras);

  const handleExamplePrompt = (prompt) => {
    ai.handleExamplePrompt(prompt);
  };

  const openReconciliationSidebar = () => {
    recon.openReconciliationSidebar(ai.setShowRightSidebar);
  };

  // Render special content in the right pane
  const renderSpecialContent = (message) => {
    const actionId = message.actionId;
    const preview = message.preview;

    switch (message.contentType) {
      case 'lead_preview':
        return (
          <LeadPreviewComponent
            leadData={message.leadData}
            onConfirm={ai.handleCreateLead}
            onCancel={ai.handleCancelLead}
          />
        );
      case 'email_campaign':
        return (
          <EmailCampaignPreview
            preview={preview}
            onExecute={() => actionId ? ai.executeAction(actionId) : ai.executeDemoAction('email_campaign')}
            onEdit={() => ai.addMessage('What changes would you like to make?', 'assistant')}
          />
        );
      case 'text_campaign':
        return (
          <TextCampaignPreview
            textData={message.textData}
            onExecute={() => actionId ? ai.executeAction(actionId) : ai.executeDemoAction('text_campaign')}
            onEdit={() => ai.addMessage('What would you like to change in the message?', 'assistant')}
          />
        );
      case 'bulk_update':
        return (
          <BulkUpdatePreview
            preview={preview}
            onExecute={() => actionId ? ai.executeAction(actionId) : ai.executeDemoAction('bulk_update')}
            onEdit={() => ai.addMessage('What would you like to modify?', 'assistant')}
          />
        );
      case 'voicemail_campaign':
        return (
          <VoicemailCampaignPreview
            preview={preview}
            onExecute={() => actionId ? ai.executeAction(actionId) : ai.executeDemoAction('voicemail_campaign')}
            onEdit={() => ai.addMessage('What would you like to change in the script?', 'assistant')}
          />
        );
      case 'pipeline_report':
        return (
          <PipelineReportPreview
            preview={preview}
            onExecute={() => actionId ? ai.executeAction(actionId) : ai.executeDemoAction('pipeline_report')}
            onEdit={() => ai.addMessage('How would you like to customize this report?', 'assistant')}
          />
        );
      case 'accountability_review':
        return (
          <AccountabilityReviewComponent
            content={message.content}
            reviewData={message.reviewData}
          />
        );
      case 'chat_response':
        return (
          <ChatResponseComponent
            content={message.content}
            responseData={message.responseData}
          />
        );
      case 'task_priorities':
        return (
          <TaskPrioritiesComponent
            content={message.content}
            tasks={message.tasks}
            onCompleteTask={ai.handleTaskComplete}
            onViewDetails={ai.handleTaskViewDetails}
            onSnoozeTask={ai.handleTaskSnooze}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="ai-landing-page-new">
      {/* Collapsible Left Sidebar */}
      <LeftSidebar
        sidebarCollapsed={ai.sidebarCollapsed}
        setSidebarCollapsed={ai.setSidebarCollapsed}
        sidebarView={ai.sidebarView}
        setSidebarView={ai.setSidebarView}
        searchQuery={session.searchQuery}
        setSearchQuery={session.setSearchQuery}
        filteredChats={session.filteredChats}
        sessionId={session.sessionId}
        draggedChat={session.draggedChat}
        dropTargetActive={session.dropTargetActive}
        reports={session.reports}
        projects={session.projects}
        onNewChat={handleNewChat}
        onLoadChat={session.handleLoadChat}
        onExamplePrompt={handleExamplePrompt}
        onContextMenu={session.handleContextMenu}
        onDragStart={session.handleDragStart}
        onDragEnd={session.handleDragEnd}
        onDragOver={session.handleDragOver}
        onDragLeave={session.handleDragLeave}
        onDropOnReports={session.handleDropOnReports}
        onRemoveFromReports={session.handleRemoveFromReports}
      />

      {/* Main Content Area - Split Pane */}
      <div className={`ai-main-content ${ai.showRightSidebar ? 'with-right-sidebar' : ''}`} ref={ai.containerRef}>
        {/* Top Right Buttons */}
        <div className="ai-top-right-buttons">
          {session.messages.length > 0 && (
            <>
              <button className="ai-copy-btn" onClick={ai.handleCopyContent} title="Copy content">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                  <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
                </svg>
              </button>
              <button className="ai-clear-btn" onClick={handleClearContent} title="Clear content">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                </svg>
              </button>
            </>
          )}
          {!ai.sidebarCollapsed && (
            <button className="ai-close-sidebar-btn" onClick={() => ai.setSidebarCollapsed(true)} title="Close sidebar">
              x
            </button>
          )}
        </div>

        {/* Left Pane - Input/Prompts */}
        <div className="ai-left-pane" style={{ width: session.messages.some(m => m.isSpecialContent) ? `${ai.dividerPosition}%` : '100%' }}>
          {/* Header */}
          <div className="ai-header-new">
            <div className="ai-logo-new">
              <span className="ai-logo-icon">*</span>
            </div>
            <h1>Back at it, {ai.userName}</h1>
          </div>

          {/* Conversation Area or Welcome State */}
          <ChatArea
            messages={session.messages}
            userName={ai.userName}
            chatAreaRef={ai.chatAreaRef}
            scrollAnchorRef={ai.scrollAnchorRef}
            messageFeedback={ai.messageFeedback}
            onPositiveFeedback={ai.handlePositiveFeedback}
            onNegativeFeedback={ai.handleNegativeFeedback}
            onExamplePrompt={handleExamplePrompt}
            onOpenReconciliation={openReconciliationSidebar}
            getGreeting={ai.getGreeting}
            getCurrentDateTime={ai.getCurrentDateTime}
          />

          {/* Chat Input */}
          <ChatInput
            inputValue={ai.inputValue}
            setInputValue={ai.setInputValue}
            isStreaming={ai.isStreaming}
            isListening={ai.isListening}
            isExtractingDocument={ai.isExtractingDocument}
            attachedDocument={ai.attachedDocument}
            setAttachedDocument={ai.setAttachedDocument}
            selectedPermission={ai.selectedPermission}
            setSelectedPermission={ai.setSelectedPermission}
            userPermissions={ai.userPermissions}
            textareaRef={ai.textareaRef}
            fileInputRef={ai.fileInputRef}
            onSend={ai.sendMessage}
            onKeyPress={ai.handleKeyPress}
            onFileUpload={ai.handleFileUpload}
            onToggleSpeechRecognition={ai.toggleSpeechRecognition}
            onNavigateDashboard={() => navigate('/dashboard')}
          />
        </div>

        {/* Draggable Divider */}
        {session.messages.some(m => m.isSpecialContent) && (
          <div
            className={`ai-pane-divider ${ai.isDragging ? 'dragging' : ''}`}
            onMouseDown={ai.handleDividerMouseDown}
          />
        )}

        {/* Right Pane - Results Only (Special Content) */}
        {session.messages.some(m => m.isSpecialContent) && (
          <div className="ai-right-pane" style={{ width: `${100 - ai.dividerPosition}%` }}>
            <div className="ai-messages-area">
              {session.messages.filter(message => message.isSpecialContent).map(message => (
                <div key={message.id} className={`ai-message-new ai-message-${message.type}`}>
                  {renderSpecialContent(message)}
                  <button
                    className="ai-delete-message-btn"
                    onClick={() => session.handleDeleteMessage(message.id)}
                    title="Delete message"
                  >
                    x
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Context Menu */}
      <ContextMenu
        contextMenu={session.contextMenu}
        onSaveAsProject={session.handleSaveAsProject}
        onDeleteChat={session.handleDeleteChat}
      />

      {/* AI Feedback Modal */}
      <FeedbackModal
        feedbackModal={ai.feedbackModal}
        feedbackType={ai.feedbackType}
        setFeedbackType={ai.setFeedbackType}
        feedbackText={ai.feedbackText}
        setFeedbackText={ai.setFeedbackText}
        feedbackSubmitting={ai.feedbackSubmitting}
        onSubmit={ai.handleSubmitFeedback}
        onClose={ai.closeFeedbackModal}
      />

      {/* Right Sidebar - Task Completion Panel */}
      <TaskSidebar
        structuredContent={ai.structuredContent}
        setStructuredContent={ai.setStructuredContent}
        selectedTask={ai.selectedTask}
        setSelectedTask={ai.setSelectedTask}
        selectedSendMethod={ai.selectedSendMethod}
        setSelectedSendMethod={ai.setSelectedSendMethod}
        selectedTaskIds={ai.selectedTaskIds}
        setSelectedTaskIds={ai.setSelectedTaskIds}
        bulkProcessing={ai.bulkProcessing}
        setBulkProcessing={ai.setBulkProcessing}
        showRightSidebar={ai.showRightSidebar}
        setShowRightSidebar={ai.setShowRightSidebar}
        addMessage={ai.addMessage}
      />

      {/* Reconciliation Sidebar */}
      <ReconciliationSidebar
        showReconciliationSidebar={recon.showReconciliationSidebar}
        setShowReconciliationSidebar={recon.setShowReconciliationSidebar}
        reconciliationItems={recon.reconciliationItems}
        selectedReconciliationItem={recon.selectedReconciliationItem}
        setSelectedReconciliationItem={recon.setSelectedReconciliationItem}
        reconciliationLoading={recon.reconciliationLoading}
        reconciliationTab={recon.reconciliationTab}
        setReconciliationTab={recon.setReconciliationTab}
        reconciliationCounts={recon.reconciliationCounts}
        autoProcessEnabled={recon.autoProcessEnabled}
        setAutoProcessEnabled={recon.setAutoProcessEnabled}
        onFetchItems={recon.fetchReconciliationItems}
        onApprove={recon.handleReconciliationApprove}
        onReject={recon.handleReconciliationReject}
      />

      {/* Persistent Action Sidebar */}
      {ai.showActionSidebar && !ai.showRightSidebar && !recon.showReconciliationSidebar && (
        <ActionSidebar
          onTaskSelect={(item) => {
            if (item) {
              const contextMessage = `I'm looking at a ${item.category} item: "${item.title}" for ${item.entity_name || 'a client'}. ${item.description || ''}`;
              ai.setInputValue(contextMessage);
            }
          }}
          onClose={() => ai.setShowActionSidebar(false)}
        />
      )}

      {/* Toggle button to show action sidebar when hidden */}
      {!ai.showActionSidebar && !ai.showRightSidebar && !recon.showReconciliationSidebar && (
        <button
          className="action-sidebar-toggle-btn"
          onClick={() => ai.setShowActionSidebar(true)}
          title="Show Action Center"
        >
          <span className="toggle-icon">📋</span>
        </button>
      )}
    </div>
  );
}

export default AILandingPage;
