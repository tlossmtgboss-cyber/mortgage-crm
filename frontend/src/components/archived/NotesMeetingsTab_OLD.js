import React from 'react';

/**
 * ARCHIVED: Original Notes & Meetings Tab (Tab 3) - Replaced by Workflow & Milestones
 * Date Archived: 2025-11-16
 *
 * This component was the original "Notes & Meetings" tab with simple text areas.
 * It has been replaced with a comprehensive "Workflow & Milestones" tab.
 * Kept here for reference in case we want to restore or migrate data.
 */

function NotesMeetingsTab_OLD({ formData, editing, handleFieldChange }) {
  return (
    <div className="tab-panel">
      <h2>Notes & Meetings</h2>
      <div className="notes-section">
        <div className="info-field">
          <label>Meeting Notes</label>
          <textarea
            rows="8"
            value={formData.meeting_notes || ''}
            onChange={(e) => handleFieldChange('meeting_notes', e.target.value)}
            disabled={!editing}
            placeholder="Add notes from 1-on-1 meetings, performance reviews, etc."
          />
        </div>
        <div className="info-field">
          <label>General Notes</label>
          <textarea
            rows="6"
            value={formData.general_notes || ''}
            onChange={(e) => handleFieldChange('general_notes', e.target.value)}
            disabled={!editing}
            placeholder="Any additional notes about this team member..."
          />
        </div>
      </div>
    </div>
  );
}

export default NotesMeetingsTab_OLD;
