import React from 'react';
import { sanitizeText, SafeHTML } from '../../utils/sanitize';
import { formatDateTime, getStatusBadge } from './utils';

// Create Meeting Modal
export const CreateMeetingModal = ({
  showCreateModal, setShowCreateModal,
  meetingForm, setMeetingForm,
  createScheduledMeeting
}) => {
  if (!showCreateModal) return null;

  return (
    <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Schedule Meeting</h3>
          <button className="close-btn" onClick={() => setShowCreateModal(false)}>x</button>
        </div>
        <div className="modal-body">
          <div className="form-group">
            <label>Meeting Name *</label>
            <input
              type="text"
              value={meetingForm.room_name}
              onChange={(e) => setMeetingForm({ ...meetingForm, room_name: e.target.value })}
              placeholder="e.g., Discovery Call with John"
            />
          </div>

          <div className="form-group">
            <label>Description</label>
            <textarea
              value={meetingForm.room_description}
              onChange={(e) => setMeetingForm({ ...meetingForm, room_description: e.target.value })}
              placeholder="Meeting description..."
              rows={3}
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Date & Time *</label>
              <input
                type="datetime-local"
                value={meetingForm.scheduled_start}
                onChange={(e) => setMeetingForm({ ...meetingForm, scheduled_start: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Duration</label>
              <select
                value={meetingForm.duration_minutes}
                onChange={(e) => setMeetingForm({ ...meetingForm, duration_minutes: parseInt(e.target.value) })}
              >
                <option value={15}>15 minutes</option>
                <option value={30}>30 minutes</option>
                <option value={45}>45 minutes</option>
                <option value={60}>1 hour</option>
                <option value={90}>1.5 hours</option>
                <option value={120}>2 hours</option>
              </select>
            </div>
          </div>

          <div className="form-group">
            <label>Meeting Type</label>
            <select
              value={meetingForm.meeting_type}
              onChange={(e) => setMeetingForm({ ...meetingForm, meeting_type: e.target.value })}
            >
              <option value="general">General</option>
              <option value="discovery_call">Discovery Call</option>
              <option value="pre_approval_review">Pre-Approval Review</option>
              <option value="document_review">Document Review</option>
              <option value="rate_lock_discussion">Rate Lock Discussion</option>
              <option value="closing_prep">Closing Preparation</option>
              <option value="post_close_review">Post-Close Review</option>
              <option value="team_sync">Team Sync</option>
            </select>
          </div>

          <div className="form-section">
            <h4>Meeting Settings</h4>
            <div className="checkbox-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={meetingForm.recording_enabled}
                  onChange={(e) => setMeetingForm({ ...meetingForm, recording_enabled: e.target.checked })}
                />
                <span>Enable Recording</span>
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={meetingForm.transcription_enabled}
                  onChange={(e) => setMeetingForm({ ...meetingForm, transcription_enabled: e.target.checked })}
                />
                <span>Enable Transcription</span>
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={meetingForm.ai_assistant_enabled}
                  onChange={(e) => setMeetingForm({ ...meetingForm, ai_assistant_enabled: e.target.checked })}
                />
                <span>Enable AI Assistant</span>
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={meetingForm.waiting_room_enabled}
                  onChange={(e) => setMeetingForm({ ...meetingForm, waiting_room_enabled: e.target.checked })}
                />
                <span>Enable Waiting Room</span>
              </label>
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="secondary-btn" onClick={() => setShowCreateModal(false)}>
            Cancel
          </button>
          <button
            className="primary-btn"
            onClick={createScheduledMeeting}
            disabled={!meetingForm.room_name || !meetingForm.scheduled_start}
          >
            Create Meeting
          </button>
        </div>
      </div>
    </div>
  );
};

// Meeting Type Modal
export const MeetingTypeModal = ({
  showNewTypeModal, setShowNewTypeModal,
  editingType, setEditingType,
  typeForm, setTypeForm,
  handleSaveMeetingType, handleDeleteMeetingType
}) => {
  if (!showNewTypeModal) return null;

  const iconOptions = [
    { value: 'phone', label: 'Phone' },
    { value: 'video', label: 'Video' },
    { value: 'document', label: 'Document' },
    { value: 'clipboard', label: 'Clipboard' },
    { value: 'folder', label: 'Folder' },
    { value: 'lock', label: 'Lock' },
    { value: 'home', label: 'Home' },
    { value: 'users', label: 'Users' },
    { value: 'calendar', label: 'Calendar' }
  ];

  const colorOptions = [
    '#10b981', '#3b82f6', '#8b5cf6', '#f59e0b',
    '#ef4444', '#ec4899', '#06b6d4', '#84cc16'
  ];

  const durationOptions = [15, 20, 30, 45, 60, 90, 120];

  const toggleDuration = (duration) => {
    const current = typeForm.allowed_durations || [];
    if (current.includes(duration)) {
      setTypeForm({ ...typeForm, allowed_durations: current.filter(d => d !== duration) });
    } else {
      setTypeForm({ ...typeForm, allowed_durations: [...current, duration].sort((a, b) => a - b) });
    }
  };

  return (
    <div className="scheduler-modal-overlay" onClick={() => {
      setShowNewTypeModal(false);
      setEditingType(null);
    }}>
      <div className="scheduler-modal type-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{editingType ? 'Edit Meeting Type' : 'New Meeting Type'}</h3>
          <button className="close-btn" onClick={() => {
            setShowNewTypeModal(false);
            setEditingType(null);
          }}>x</button>
        </div>

        <div className="modal-content">
          <div className="form-group">
            <label>Type Name *</label>
            <input
              type="text"
              value={typeForm.type_name}
              onChange={e => setTypeForm({ ...typeForm, type_name: e.target.value })}
              placeholder="e.g., Discovery Call"
            />
          </div>

          <div className="form-group">
            <label>Description</label>
            <textarea
              value={typeForm.description}
              onChange={e => setTypeForm({ ...typeForm, description: e.target.value })}
              placeholder="Brief description of this meeting type..."
              rows={2}
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Default Duration</label>
              <select
                value={typeForm.default_duration_minutes}
                onChange={e => setTypeForm({ ...typeForm, default_duration_minutes: parseInt(e.target.value) })}
              >
                {durationOptions.map(d => (
                  <option key={d} value={d}>{d} minutes</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Icon</label>
              <select
                value={typeForm.icon}
                onChange={e => setTypeForm({ ...typeForm, icon: e.target.value })}
              >
                {iconOptions.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-group">
            <label>Allowed Durations</label>
            <div className="duration-toggles">
              {durationOptions.map(d => (
                <button
                  key={d}
                  type="button"
                  className={`duration-toggle ${(typeForm.allowed_durations || []).includes(d) ? 'active' : ''}`}
                  onClick={() => toggleDuration(d)}
                >
                  {d}m
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label>Color</label>
            <div className="color-options">
              {colorOptions.map(color => (
                <button
                  key={color}
                  type="button"
                  className={`color-option ${typeForm.color === color ? 'selected' : ''}`}
                  style={{ backgroundColor: color }}
                  onClick={() => setTypeForm({ ...typeForm, color })}
                />
              ))}
            </div>
          </div>

          <div className="form-group checkbox-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={typeForm.recording_enabled}
                onChange={e => setTypeForm({ ...typeForm, recording_enabled: e.target.checked })}
              />
              Enable Recording by default
            </label>
          </div>

          <div className="form-group checkbox-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={typeForm.ai_assistant_enabled}
                onChange={e => setTypeForm({ ...typeForm, ai_assistant_enabled: e.target.checked })}
              />
              Enable AI Assistant by default
            </label>
          </div>
        </div>

        <div className="modal-footer">
          {editingType && (
            <button
              className="delete-btn"
              onClick={() => {
                handleDeleteMeetingType(editingType.id);
                setShowNewTypeModal(false);
                setEditingType(null);
              }}
            >
              Delete
            </button>
          )}
          <div className="footer-right">
            <button className="cancel-btn" onClick={() => {
              setShowNewTypeModal(false);
              setEditingType(null);
            }}>Cancel</button>
            <button
              className="confirm-btn"
              onClick={handleSaveMeetingType}
              disabled={!typeForm.type_name}
            >
              {editingType ? 'Save Changes' : 'Create Type'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// New Booking Link Modal
export const NewLinkModal = ({
  showNewLinkModal, setShowNewLinkModal,
  linkForm, setLinkForm,
  meetingTypes, handleCreateBookingLink
}) => {
  if (!showNewLinkModal) return null;

  return (
    <div className="scheduler-modal-overlay" onClick={() => setShowNewLinkModal(false)}>
      <div className="scheduler-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Create Booking Link</h3>
          <button className="close-btn" onClick={() => setShowNewLinkModal(false)}>x</button>
        </div>

        <div className="modal-content">
          <div className="form-group">
            <label>Link Name *</label>
            <input
              type="text"
              value={linkForm.link_name}
              onChange={e => setLinkForm({ ...linkForm, link_name: e.target.value })}
              placeholder="My Video Booking Link"
            />
          </div>

          <div className="form-group">
            <label>URL Slug *</label>
            <div className="slug-input">
              <span className="slug-prefix">/meeting/book/</span>
              <input
                type="text"
                value={linkForm.slug}
                onChange={e => setLinkForm({ ...linkForm, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '') })}
                placeholder="my-link"
              />
            </div>
          </div>

          <div className="form-group">
            <label>Description</label>
            <textarea
              value={linkForm.description}
              onChange={e => setLinkForm({ ...linkForm, description: e.target.value })}
              placeholder="Optional description..."
              rows={2}
            />
          </div>

          <div className="form-group">
            <label>Meeting Types</label>
            <div className="type-checkboxes">
              {meetingTypes.map(type => (
                <label key={type.id || type.template_key} className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={linkForm.meeting_type_ids.includes(type.id)}
                    onChange={e => {
                      if (e.target.checked) {
                        setLinkForm({ ...linkForm, meeting_type_ids: [...linkForm.meeting_type_ids, type.id] });
                      } else {
                        setLinkForm({ ...linkForm, meeting_type_ids: linkForm.meeting_type_ids.filter(id => id !== type.id) });
                      }
                    }}
                  />
                  {type.template_name || type.type_name}
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button className="cancel-btn" onClick={() => setShowNewLinkModal(false)}>Cancel</button>
          <button
            className="confirm-btn"
            onClick={() => handleCreateBookingLink(linkForm)}
            disabled={!linkForm.slug || !linkForm.link_name}
          >
            Create Link
          </button>
        </div>
      </div>
    </div>
  );
};

// Meeting Detail Modal
export const MeetingDetailModal = ({
  showMeetingDetail, setShowMeetingDetail,
  selectedMeeting,
  startMeeting, endMeeting, cancelMeeting,
  viewRecording
}) => {
  if (!showMeetingDetail || !selectedMeeting) return null;

  const meeting = selectedMeeting.meeting;
  const participants = selectedMeeting.participants || [];
  const recordings = selectedMeeting.recordings || [];

  return (
    <div className="modal-overlay" onClick={() => setShowMeetingDetail(false)}>
      <div className="modal-content large" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{sanitizeText(meeting.room_name)}</h3>
          <button className="close-btn" onClick={() => setShowMeetingDetail(false)}>x</button>
        </div>
        <div className="modal-body">
          <div className="detail-section">
            <div className="detail-row">
              <span className="detail-label">Status:</span>
              {getStatusBadge(meeting.status)}
            </div>
            <div className="detail-row">
              <span className="detail-label">Room Code:</span>
              <span className="room-code-large">{meeting.room_code}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Scheduled:</span>
              <span>{formatDateTime(meeting.scheduled_start)}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Duration:</span>
              <span>{meeting.duration_minutes} minutes</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Type:</span>
              <span>{meeting.meeting_type}</span>
            </div>
            {meeting.room_description && (
              <div className="detail-row">
                <span className="detail-label">Description:</span>
                <SafeHTML html={meeting.room_description} />
              </div>
            )}
          </div>

          <div className="detail-section">
            <h4>Participants ({participants.length})</h4>
            {participants.length === 0 ? (
              <p className="no-data">No participants yet</p>
            ) : (
              <div className="participants-list">
                {participants.map(p => (
                  <div key={p.id} className="participant-item">
                    <span className="participant-name">{sanitizeText(p.display_name || p.email)}</span>
                    <span className={`participant-role ${p.role}`}>{p.role}</span>
                    <span className={`participant-status ${p.status}`}>{p.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="detail-section">
            <h4>Recordings ({recordings.length})</h4>
            {recordings.length === 0 ? (
              <p className="no-data">No recordings yet</p>
            ) : (
              <div className="recordings-list">
                {recordings.map(r => (
                  <div
                    key={r.id}
                    className="recording-item clickable"
                    onClick={() => viewRecording(r.id, meeting.room_name)}
                  >
                    <span className="recording-icon">&#x1F534;</span>
                    <span className="recording-name">{sanitizeText(r.recording_name)}</span>
                    <span className="recording-status">{r.status}</span>
                    {r.duration_seconds && (
                      <span className="recording-duration">
                        {Math.floor(r.duration_seconds / 60)}:{(r.duration_seconds % 60).toString().padStart(2, '0')}
                      </span>
                    )}
                    <span className="recording-play-btn">&#x25B6; Play</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {meeting.ai_summary && (
            <div className="detail-section">
              <h4>AI Summary</h4>
              <SafeHTML className="ai-summary" html={meeting.ai_summary} />
            </div>
          )}

          {meeting.ai_action_items && meeting.ai_action_items.length > 0 && (
            <div className="detail-section">
              <h4>Action Items</h4>
              <ul className="action-items-list">
                {meeting.ai_action_items.map((item, idx) => (
                  <li key={idx}>{sanitizeText(item)}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="modal-footer">
          {meeting.status === 'scheduled' && (
            <>
              <button className="danger-btn" onClick={() => cancelMeeting(meeting.id)}>
                Cancel Meeting
              </button>
              <button className="primary-btn" onClick={() => startMeeting(meeting.id)}>
                Start Meeting
              </button>
            </>
          )}
          {meeting.status === 'active' && (
            <>
              <button className="danger-btn" onClick={() => endMeeting(meeting.id)}>
                End Meeting
              </button>
              <button
                className="primary-btn"
                onClick={() => window.open(`/meeting/${meeting.room_code}`, '_blank')}
              >
                Join Meeting
              </button>
            </>
          )}
          {meeting.status === 'ended' && (
            <button className="secondary-btn" onClick={() => setShowMeetingDetail(false)}>
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
