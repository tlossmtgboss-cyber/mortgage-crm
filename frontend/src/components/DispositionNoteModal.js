import React, { useState } from 'react';
import { activitiesAPI, tasksAPI, leadsAPI } from '../services/api';
import { toast } from '../utils/toast';
import './DispositionNoteModal.css';

const DISPOSITION_LABELS = {
  'Long-Term Nurture': 'Long-Term Nurture',
  'Credit Repair': 'Credit Repair',
  'Withdrawn': 'Withdrawn',
  'Does Not Qualify': 'Does Not Qualify',
};

function DispositionNoteModal({ isOpen, onClose, onConfirm, lead, newStatus }) {
  const [note, setNote] = useState('');
  const [createFollowUp, setCreateFollowUp] = useState(false);
  const [followUpDate, setFollowUpDate] = useState('');
  const [addToMarketing, setAddToMarketing] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (!isOpen) return null;

  const label = DISPOSITION_LABELS[newStatus] || newStatus;
  const leadName = lead?.first_name
    ? `${lead.first_name} ${lead.last_name || ''}`.trim()
    : lead?.name || 'this lead';

  const handleSubmit = async () => {
    if (!note.trim()) return;

    setSubmitting(true);
    try {
      // 1. Log the note as an activity in the conversation log
      await activitiesAPI.create({
        lead_id: lead?.id,
        type: 'Note',
        content: `[Disposition to ${label}] ${note.trim()}`,
      });

      // 2. Optionally add to marketing list
      if (addToMarketing && lead?.id) {
        await leadsAPI.update(lead.id, { receive_marketing: true });
      }

      // 3. Optionally create a follow-up task
      if (createFollowUp && followUpDate) {
        await tasksAPI.create({
          title: `Follow up: ${leadName} (${label})`,
          description: note.trim(),
          lead_id: lead?.id,
          priority: 'medium',
          due_date: new Date(followUpDate).toISOString(),
        });
      }

      // 4. Proceed with the status change
      if (onConfirm) {
        await onConfirm(newStatus);
      }

      // Reset and close
      setNote('');
      setCreateFollowUp(false);
      setFollowUpDate('');
      setAddToMarketing(false);
      onClose();
    } catch (err) {
      console.error('Disposition note error:', err);
      toast.error('Failed to save note. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // Default follow-up date suggestions
  const getDefaultDate = (daysFromNow) => {
    const d = new Date();
    d.setDate(d.getDate() + daysFromNow);
    return d.toISOString().split('T')[0];
  };

  return (
    <div className="disposition-overlay" onClick={onClose}>
      <div className="disposition-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="disposition-header">
          <h2>Move to {label}</h2>
          <button className="disposition-close" onClick={onClose}>&times;</button>
        </div>

        {/* Body */}
        <div className="disposition-body">
          <p className="disposition-lead-name">
            {leadName}
          </p>

          {/* Note */}
          <div className="disposition-field">
            <label className="disposition-label">
              Disposition Note <span className="disposition-required">*</span>
            </label>
            <textarea
              className="disposition-textarea"
              placeholder={`Why is this lead being moved to ${label}?`}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={4}
              autoFocus
            />
          </div>

          {/* Marketing opt-in */}
          <div className="disposition-followup-toggle">
            <label className="disposition-checkbox-label">
              <input
                type="checkbox"
                checked={addToMarketing}
                onChange={(e) => setAddToMarketing(e.target.checked)}
              />
              <span>Add to marketing list</span>
            </label>
          </div>

          {/* Follow-up task toggle */}
          <div className="disposition-followup-toggle">
            <label className="disposition-checkbox-label">
              <input
                type="checkbox"
                checked={createFollowUp}
                onChange={(e) => setCreateFollowUp(e.target.checked)}
              />
              <span>Create follow-up task</span>
            </label>
          </div>

          {/* Follow-up date picker */}
          {createFollowUp && (
            <div className="disposition-followup-section">
              <label className="disposition-label">Follow-up Date</label>
              <input
                type="date"
                className="disposition-date-input"
                value={followUpDate}
                onChange={(e) => setFollowUpDate(e.target.value)}
                min={new Date().toISOString().split('T')[0]}
              />
              <div className="disposition-quick-dates">
                <button
                  type="button"
                  className="disposition-quick-date"
                  onClick={() => setFollowUpDate(getDefaultDate(7))}
                >
                  1 Week
                </button>
                <button
                  type="button"
                  className="disposition-quick-date"
                  onClick={() => setFollowUpDate(getDefaultDate(14))}
                >
                  2 Weeks
                </button>
                <button
                  type="button"
                  className="disposition-quick-date"
                  onClick={() => setFollowUpDate(getDefaultDate(30))}
                >
                  1 Month
                </button>
                <button
                  type="button"
                  className="disposition-quick-date"
                  onClick={() => setFollowUpDate(getDefaultDate(90))}
                >
                  3 Months
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="disposition-footer">
          <button
            className="disposition-cancel-btn"
            onClick={onClose}
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            className="disposition-confirm-btn"
            onClick={handleSubmit}
            disabled={submitting || !note.trim() || (createFollowUp && !followUpDate)}
          >
            {submitting ? 'Saving...' : `Move to ${label}`}
          </button>
        </div>
      </div>
    </div>
  );
}

// Statuses that require the disposition note modal
DispositionNoteModal.REQUIRES_NOTE = [
  'Long-Term Nurture',
  'Credit Repair',
  'Withdrawn',
  'Does Not Qualify',
  'Do Not Call',
];

export default DispositionNoteModal;
