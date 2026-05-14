import React, { useState } from 'react';
import { ClickablePhone } from '../../components/ClickableContact';

/**
 * Conversation Log tab — sub-tabs for notes, email archive, SMS archive, recorded calls.
 */
function ConversationLogTab({
  activities,
  noteText,
  setNoteText,
  noteLoading,
  handleAddNote,
  emailArchive,
  smsArchive,
  callArchive,
  archiveLoading,
  archiveSubTab,
  setArchiveSubTab,
  onShowEmailComposer,
  onShowSMSModal,
  onShowRecordingModal,
}) {
  return (
    <div className="info-section">
      <h2>Conversation Log</h2>

      {/* Archive Sub-Tabs */}
      <div className="archive-sub-tabs">
        {[
          ['notes', 'Notes'],
          ['email', 'Email Archive'],
          ['sms', 'SMS Archive'],
          ['calls', 'Recorded Calls'],
        ].map(([key, label]) => (
          <button
            key={key}
            className={`archive-sub-tab ${archiveSubTab === key ? 'active' : ''}`}
            onClick={() => setArchiveSubTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Notes Sub-Tab */}
      {archiveSubTab === 'notes' && (
        <>
          <form onSubmit={handleAddNote} className="add-note-form">
            <textarea
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              placeholder="Add a note to the conversation log..."
              rows="3"
              disabled={noteLoading}
            />
            <button type="submit" disabled={noteLoading || !noteText.trim()}>
              {noteLoading ? 'Adding...' : 'Add Note'}
            </button>
          </form>

          <div className="conversation-log">
            {activities.length > 0 ? (
              activities.map((activity) => (
                <div key={activity.id} className="activity-item">
                  <div className="activity-header">
                    <span className={`activity-type ${activity.type}`}>
                      {activity.type}
                    </span>
                    <span className="activity-date">
                      {new Date(activity.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="activity-description">{activity.content || activity.description}</div>
                </div>
              ))
            ) : (
              <div className="empty-state">No activities yet</div>
            )}
          </div>
        </>
      )}

      {/* Email Archive Sub-Tab */}
      {archiveSubTab === 'email' && (
        <div className="archive-content">
          <div className="archive-header">
            <h3>Email History</h3>
            <p className="archive-description">All emails sent to and received from this lead</p>
          </div>
          {archiveLoading ? (
            <div className="loading-state">Loading emails...</div>
          ) : emailArchive.length > 0 ? (
            <div className="archive-list">
              {emailArchive.map((email, idx) => (
                <div key={email.id || idx} className="archive-item email-item">
                  <div className="archive-item-header">
                    <span className={`archive-direction ${email.direction || 'outbound'}`}>
                      {email.direction === 'inbound' ? '📥 Received' : '📤 Sent'}
                    </span>
                    <span className="archive-date">
                      {new Date(email.sent_at || email.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="archive-item-subject">
                    <strong>Subject:</strong> {email.subject || 'No Subject'}
                  </div>
                  <div className="archive-item-preview">
                    {email.body_text?.substring(0, 200) || email.body?.substring(0, 200) || 'No content'}
                    {(email.body_text?.length > 200 || email.body?.length > 200) && '...'}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">📧</div>
              <p>No emails found for this lead</p>
              <button className="compose-btn" onClick={onShowEmailComposer}>
                Compose Email
              </button>
            </div>
          )}
        </div>
      )}

      {/* SMS Archive Sub-Tab */}
      {archiveSubTab === 'sms' && (
        <div className="archive-content">
          <div className="archive-header">
            <h3>SMS History</h3>
            <p className="archive-description">All text messages exchanged with this lead</p>
          </div>
          {archiveLoading ? (
            <div className="loading-state">Loading messages...</div>
          ) : smsArchive.length > 0 ? (
            <div className="archive-list sms-thread">
              {smsArchive.map((sms, idx) => (
                <div
                  key={sms.id || idx}
                  className={`archive-item sms-item ${sms.direction || 'outbound'}`}
                >
                  <div className="sms-bubble">
                    {sms.senderName && <div className="sms-sender" style={{ fontSize: '11px', fontWeight: 600, marginBottom: 2, opacity: 0.7 }}>{sms.senderName}</div>}
                    <div className="sms-message">{sms.message || sms.body}</div>
                    <div className="sms-meta">
                      <span className="sms-status">{sms.status || 'sent'}</span>
                      <span className="sms-time">
                        {new Date(sms.timestamp || sms.sent_at || sms.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">💬</div>
              <p>No SMS messages found for this lead</p>
              <button className="compose-btn" onClick={onShowSMSModal}>
                Send SMS
              </button>
            </div>
          )}
        </div>
      )}

      {/* Recorded Calls Sub-Tab */}
      {archiveSubTab === 'calls' && (
        <div className="archive-content">
          <div className="archive-header">
            <h3>Recorded Calls</h3>
            <p className="archive-description">All recorded phone calls with this lead</p>
          </div>
          {archiveLoading ? (
            <div className="loading-state">Loading recordings...</div>
          ) : callArchive.length > 0 ? (
            <div className="archive-list">
              {callArchive.map((call, idx) => (
                <div key={call.id || idx} className="archive-item call-item">
                  <div className="archive-item-header">
                    <span className={`archive-direction ${call.direction || 'outbound'}`}>
                      {call.direction === 'inbound' ? '📲 Incoming' : '📞 Outgoing'}
                    </span>
                    <span className="call-duration">
                      {call.duration ? `${Math.floor(call.duration / 60)}:${(call.duration % 60).toString().padStart(2, '0')}` : 'N/A'}
                    </span>
                    <span className="archive-date">
                      {new Date(call.call_time || call.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="call-details">
                    <span className="call-status">{call.status || 'completed'}</span>
                    {call.disposition && <span className="call-disposition">{call.disposition}</span>}
                  </div>
                  {call.recording_url && (
                    <div className="call-recording">
                      <audio controls src={call.recording_url}>
                        Your browser does not support audio playback.
                      </audio>
                    </div>
                  )}
                  {call.transcription && (
                    <div className="call-transcription">
                      <strong>Transcription:</strong>
                      <p>{call.transcription.substring(0, 300)}{call.transcription.length > 300 && '...'}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">🎙️</div>
              <p>No recorded calls found for this lead</p>
              <button className="compose-btn" onClick={onShowRecordingModal}>
                Start Recording
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ConversationLogTab;
