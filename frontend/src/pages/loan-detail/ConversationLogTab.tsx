/**
 * Conversation Log tab -- Notes, Email Archive, SMS Archive, Recorded Calls.
 */
import React from 'react';
import type { ArchiveSubTab } from './types';

interface ConversationLogTabProps {
  archiveSubTab: ArchiveSubTab;
  setArchiveSubTab: (tab: ArchiveSubTab) => void;
  noteText: string;
  setNoteText: (text: string) => void;
  noteLoading: boolean;
  handleAddNote: (e: React.FormEvent) => void;
  activities: any[];
  emailArchive: any[];
  smsArchive: any[];
  callArchive: any[];
  archiveLoading: boolean;
  setShowEmailComposer: (show: boolean) => void;
  setShowSMSModal: (show: boolean) => void;
  setShowRecordingModal: (show: boolean) => void;
}

export default function ConversationLogTab({
  archiveSubTab,
  setArchiveSubTab,
  noteText,
  setNoteText,
  noteLoading,
  handleAddNote,
  activities,
  emailArchive,
  smsArchive,
  callArchive,
  archiveLoading,
  setShowEmailComposer,
  setShowSMSModal,
  setShowRecordingModal,
}: ConversationLogTabProps) {
  return (
    <div className="info-section">
      <h2>Conversation Log</h2>

      {/* Archive Sub-tabs */}
      <div className="archive-sub-tabs">
        <button
          className={`archive-sub-tab ${archiveSubTab === 'notes' ? 'active' : ''}`}
          onClick={() => setArchiveSubTab('notes')}
        >
          Notes
        </button>
        <button
          className={`archive-sub-tab ${archiveSubTab === 'email' ? 'active' : ''}`}
          onClick={() => setArchiveSubTab('email')}
        >
          Email Archive
        </button>
        <button
          className={`archive-sub-tab ${archiveSubTab === 'sms' ? 'active' : ''}`}
          onClick={() => setArchiveSubTab('sms')}
        >
          SMS Archive
        </button>
        <button
          className={`archive-sub-tab ${archiveSubTab === 'calls' ? 'active' : ''}`}
          onClick={() => setArchiveSubTab('calls')}
        >
          Recorded Calls
        </button>
      </div>

      {/* Notes Sub-tab */}
      {archiveSubTab === 'notes' && (
        <>
          {/* Add Note Form */}
          <form onSubmit={handleAddNote} className="add-note-form">
            <textarea
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              placeholder="Add a note to the conversation log..."
              rows={3}
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

      {/* Email Archive Sub-tab */}
      {archiveSubTab === 'email' && (
        <div className="archive-section">
          {archiveLoading ? (
            <div className="loading-state">Loading email archive...</div>
          ) : emailArchive.length > 0 ? (
            <div className="email-archive-list">
              {emailArchive.map((email) => (
                <div key={email.id} className="email-archive-item">
                  <div className="email-archive-header">
                    <span className={`email-direction ${email.direction || 'inbound'}`}>
                      {email.direction === 'outbound' ? 'Sent' : 'Received'}
                    </span>
                    <span className="email-date">
                      {new Date(email.date || email.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="email-subject">{email.subject || '(No Subject)'}</div>
                  <div className="email-preview">{email.preview || email.body?.substring(0, 150) || ''}</div>
                  <div className="email-participants">
                    <span>From: {email.from || email.sender}</span>
                    <span>To: {email.to || email.recipient}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-archive-state">
              <div className="empty-icon">📧</div>
              <h3>No Emails Archived</h3>
              <p>Emails associated with this loan will appear here.</p>
              <button className="sync-archive-btn" onClick={() => setShowEmailComposer(true)}>
                Compose Email
              </button>
            </div>
          )}
        </div>
      )}

      {/* SMS Archive Sub-tab */}
      {archiveSubTab === 'sms' && (
        <div className="archive-section">
          {archiveLoading ? (
            <div className="loading-state">Loading SMS archive...</div>
          ) : smsArchive.length > 0 ? (
            <div className="sms-thread">
              {smsArchive.map((sms) => (
                <div key={sms.id} className={`sms-item ${sms.direction || 'inbound'}`}>
                  <div className="sms-bubble">
                    <div className="sms-content">{sms.content || sms.message}</div>
                    <div className="sms-time">
                      {new Date(sms.sent_at || sms.created_at).toLocaleString()}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-archive-state">
              <div className="empty-icon">💬</div>
              <h3>No SMS Messages</h3>
              <p>SMS conversations with this borrower will appear here.</p>
              <button className="sync-archive-btn" onClick={() => setShowSMSModal(true)}>
                Send SMS
              </button>
            </div>
          )}
        </div>
      )}

      {/* Recorded Calls Sub-tab */}
      {archiveSubTab === 'calls' && (
        <div className="archive-section">
          {archiveLoading ? (
            <div className="loading-state">Loading call recordings...</div>
          ) : callArchive.length > 0 ? (
            <div className="calls-archive-list">
              {callArchive.map((call) => (
                <div key={call.id} className="call-archive-item">
                  <div className="call-archive-header">
                    <span className={`call-direction ${call.direction || 'inbound'}`}>
                      {call.direction === 'outbound' ? 'Outgoing' : 'Incoming'}
                    </span>
                    <span className="call-duration">{call.duration || '0:00'}</span>
                    <span className="call-date">
                      {new Date(call.call_time || call.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="call-participants">
                    <span>{call.caller_name || 'Unknown'} - {call.phone_number}</span>
                  </div>
                  {call.recording_url && (
                    <div className="call-recording">
                      <audio controls src={call.recording_url}>
                        Your browser does not support the audio element.
                      </audio>
                    </div>
                  )}
                  {call.transcription && (
                    <div className="call-transcription">
                      <strong>Transcription:</strong>
                      <p>{call.transcription}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-archive-state">
              <div className="empty-icon">📞</div>
              <h3>No Recorded Calls</h3>
              <p>Call recordings with this borrower will appear here.</p>
              <button className="sync-archive-btn" onClick={() => setShowRecordingModal(true)}>
                Start Recording
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
