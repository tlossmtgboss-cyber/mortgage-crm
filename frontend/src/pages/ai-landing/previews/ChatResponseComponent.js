import React from 'react';
import ReactMarkdown from 'react-markdown';

function ChatResponseComponent({ content, responseData }) {
  return (
    <div className="ai-message-content-new ai-special-content">
      <div className="ai-action-preview chat-response">
        <div className="ai-chat-response-content">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

export default ChatResponseComponent;
