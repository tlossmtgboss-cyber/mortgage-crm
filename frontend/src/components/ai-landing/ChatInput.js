import React from 'react';

function ChatInput({
  inputValue,
  setInputValue,
  isStreaming,
  isListening,
  isExtractingDocument,
  attachedDocument,
  setAttachedDocument,
  selectedPermission,
  setSelectedPermission,
  userPermissions,
  textareaRef,
  fileInputRef,
  onSend,
  onKeyPress,
  onFileUpload,
  onToggleSpeechRecognition,
  onNavigateDashboard
}) {
  return (
    <>
      {/* Attached Document Chip */}
      {isExtractingDocument && (
        <div className="ai-extracting-indicator">
          <svg className="ai-extracting-spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
          </svg>
          Extracting document text...
        </div>
      )}
      {attachedDocument && !isExtractingDocument && (
        <div className="ai-attached-document">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          <span className="ai-attached-filename">{attachedDocument.filename}</span>
          <span className="ai-attached-size">{attachedDocument.charCount.toLocaleString()} chars{attachedDocument.truncated ? ' (truncated)' : ''}</span>
          <button className="ai-attached-remove" onClick={() => setAttachedDocument(null)} title="Remove document">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      )}

      {/* Input Area */}
      <div className="ai-input-area">
        <div className="ai-input-container-new">
          <button
            className="ai-upload-btn"
            onClick={() => fileInputRef.current?.click()}
            title="Upload documents"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
            </svg>
          </button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={onFileUpload}
            accept=".pdf,.docx,.doc,.txt,.md,.html,image/*"
            style={{ display: 'none' }}
          />

          <button
            className={`ai-mic-btn ${isListening ? 'listening' : ''}`}
            onClick={onToggleSpeechRecognition}
            title={isListening ? 'Stop listening' : 'Start voice input'}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/>
              <path d="M19 10v2a7 7 0 01-14 0v-2"/>
              <line x1="12" y1="19" x2="12" y2="23"/>
              <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
          </button>

          <textarea
            ref={textareaRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={onKeyPress}
            placeholder="Ask me to do something..."
            disabled={isStreaming}
            rows={1}
          />

          <select
            className="ai-permission-select"
            value={selectedPermission}
            onChange={(e) => setSelectedPermission(e.target.value)}
          >
            {userPermissions.map(perm => (
              <option key={perm} value={perm}>
                {perm.charAt(0).toUpperCase() + perm.slice(1)}
              </option>
            ))}
          </select>

          <button
            className="ai-send-btn-new"
            onClick={() => onSend()}
            disabled={!inputValue.trim() || isStreaming}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
            </svg>
          </button>
        </div>
      </div>

      <button className="ai-back-to-crm-new" onClick={onNavigateDashboard}>
        Back to CRM Dashboard
      </button>
    </>
  );
}

export default ChatInput;
