import React from 'react';

function ContextMenu({ contextMenu, onSaveAsProject, onDeleteChat }) {
  if (!contextMenu.visible) return null;

  return (
    <div
      className="ai-context-menu"
      style={{ top: contextMenu.y, left: contextMenu.x }}
    >
      <button onClick={onSaveAsProject}>Save as Project</button>
      <button onClick={onDeleteChat}>Delete Chat</button>
    </div>
  );
}

export default ContextMenu;
