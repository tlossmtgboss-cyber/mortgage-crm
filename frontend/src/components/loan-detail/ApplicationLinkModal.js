import React from 'react';
import { toast } from '../../utils/toast';

/**
 * Application Link Modal — displays a shareable borrower application link.
 */
function ApplicationLinkModal({ applicationLink, onClose }) {
  if (!applicationLink) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '500px' }}>
        <div className="modal-header">
          <h2>Application Link Created</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>
        <div style={{ padding: '20px' }}>
          <p style={{ marginBottom: '12px' }}>Share this link with the borrower:</p>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <input type="text" readOnly value={applicationLink.url} style={{ flex: 1, padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '13px' }} />
            <button onClick={async () => { try { await navigator.clipboard.writeText(applicationLink.url); toast.success('Link copied!'); } catch { toast.error('Copy failed'); } }} style={{ padding: '8px 16px', backgroundColor: '#1F3D2E', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', whiteSpace: 'nowrap' }}>Copy</button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ApplicationLinkModal;
