import React from 'react';

function LeftSidebar({
  sidebarCollapsed,
  setSidebarCollapsed,
  sidebarView,
  setSidebarView,
  searchQuery,
  setSearchQuery,
  filteredChats,
  sessionId,
  draggedChat,
  dropTargetActive,
  reports,
  projects,
  onNewChat,
  onLoadChat,
  onExamplePrompt,
  onContextMenu,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDragLeave,
  onDropOnReports,
  onRemoveFromReports
}) {
  return (
    <div className={`ai-sidebar-new ${sidebarCollapsed ? 'collapsed' : ''}`}>
      <button
        className="ai-sidebar-toggle"
        onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
      >
        {sidebarCollapsed ? '>' : '<'}
      </button>

      {!sidebarCollapsed && (
        <>
          {/* New Chat Button */}
          <button className="ai-new-chat-btn" onClick={onNewChat}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            New Chat
          </button>

          {/* Navigation Buttons */}
          <div className="ai-sidebar-nav">
            <button
              className={`ai-nav-btn ${sidebarView === 'chats' ? 'active' : ''}`}
              onClick={() => setSidebarView('chats')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
              </svg>
              Chats
            </button>
            <button
              className={`ai-nav-btn ${sidebarView === 'reports' ? 'active' : ''} ${dropTargetActive ? 'drop-target' : ''}`}
              onClick={() => setSidebarView('reports')}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDropOnReports}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
              </svg>
              Reports
              {dropTargetActive && <span className="drop-hint">Drop here</span>}
            </button>
            <button
              className={`ai-nav-btn ${sidebarView === 'suggestions' ? 'active' : ''}`}
              onClick={() => setSidebarView('suggestions')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
              </svg>
              Suggestions
            </button>
          </div>

          {/* Content based on view */}
          <div className="ai-sidebar-content">
            {sidebarView === 'chats' && (
              <>
                <div className="ai-search-box">
                  <input
                    type="text"
                    placeholder="Search chats..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                </div>
                <div className="ai-chat-list">
                  {filteredChats.length === 0 ? (
                    <div className="ai-empty-list">No chats yet</div>
                  ) : (
                    filteredChats.map(chat => (
                      <div
                        key={chat.id}
                        className={`ai-chat-item ${chat.id === sessionId ? 'active' : ''} ${draggedChat?.id === chat.id ? 'dragging' : ''}`}
                        onClick={() => {
                          // Re-ask the question when clicking on a chat item
                          const firstUserMessage = chat.messages?.find(m => m.type === 'user');
                          if (firstUserMessage?.content) {
                            onExamplePrompt(firstUserMessage.content);
                          } else {
                            onLoadChat(chat);
                          }
                        }}
                        onContextMenu={(e) => onContextMenu(e, chat.id)}
                        draggable
                        onDragStart={(e) => onDragStart(e, chat)}
                        onDragEnd={onDragEnd}
                        title={chat.title}
                      >
                        <div className="ai-chat-drag-handle">⋮⋮</div>
                        <div className="ai-chat-info">
                          <div className="ai-chat-title">{chat.title}</div>
                          <div className="ai-chat-time">
                            {new Date(chat.timestamp).toLocaleDateString()}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </>
            )}

            {sidebarView === 'reports' && (
              <div
                className={`ai-reports-list ${dropTargetActive ? 'drop-target-area' : ''}`}
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDropOnReports}
              >
                {reports.length === 0 ? (
                  <div className="ai-empty-list">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{marginBottom: '8px', opacity: 0.5}}>
                      <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                    </svg>
                    <p>No reports yet</p>
                    <p className="ai-drop-instruction">Drag a chat here to save it as a report</p>
                  </div>
                ) : (
                  reports.map(report => (
                    <div
                      key={report.id}
                      className={`ai-report-item ${report.id === sessionId ? 'active' : ''}`}
                      onClick={() => onLoadChat(report)}
                    >
                      <div className="ai-report-icon">📊</div>
                      <div className="ai-report-info">
                        <div className="ai-report-title">{report.title}</div>
                        <div className="ai-report-time">
                          {new Date(report.addedToReportsAt || report.timestamp).toLocaleDateString()}
                        </div>
                      </div>
                      <button
                        className="ai-report-remove"
                        onClick={(e) => {
                          e.stopPropagation();
                          onRemoveFromReports(report.id);
                        }}
                        title="Remove from reports"
                      >
                        ×
                      </button>
                    </div>
                  ))
                )}
              </div>
            )}

            {sidebarView === 'suggestions' && (
              <div className="ai-suggestions-view">
                <h3>Share Your Ideas</h3>
                <p>Help us improve! Share your suggestions and feature requests.</p>
                <textarea
                  className="ai-suggestion-input"
                  placeholder="Type your suggestion here..."
                  rows={4}
                />
                <button className="ai-submit-suggestion">Submit Suggestion</button>
              </div>
            )}
          </div>

          {/* Projects Section */}
          {projects.length > 0 && sidebarView === 'chats' && (
            <div className="ai-projects-section">
              <h4>Saved Projects</h4>
              {projects.map(project => (
                <div
                  key={project.id}
                  className="ai-project-item"
                  onClick={() => onLoadChat(project)}
                >
                  <span className="ai-project-icon">📁</span>
                  {project.title}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default LeftSidebar;
