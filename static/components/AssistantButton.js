import React from 'react';

const AssistantButton = ({ onClick }) => {
  return (
    <button className="assistant-button" onClick={onClick}>
      🤖 Assistant
    </button>
  );
};

export default AssistantButton;
