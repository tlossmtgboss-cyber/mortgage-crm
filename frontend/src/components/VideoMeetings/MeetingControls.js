/**
 * MeetingControls — Control bar for video meetings (Chime SDK).
 *
 * Mute, video, screen share, record, chat, invite, leave.
 * Uses Chime SDK hooks for media device toggling.
 */
import React from 'react';
import {
  useToggleLocalMute,
  useLocalVideo,
  useContentShareControls,
  useContentShareState,
} from 'amazon-chime-sdk-component-library-react';

export default function MeetingControls({
  isHost,
  isRecording,
  recordingTime,
  isScreenRecording,
  screenRecordingTime,
  showChat,
  onToggleChat,
  onToggleRecord,
  onToggleScreenRecord,
  onToggleBreakoutPanel,
  onInvite,
  onLeave,
  onCycleVirtualBg,
  virtualBgMode,
  waitingCount,
}) {
  const { muted, toggleMute } = useToggleLocalMute();
  const { isVideoEnabled, toggleVideo } = useLocalVideo();
  const { toggleContentShare } = useContentShareControls();
  const { isLocalShareLoading, sharingAttendeeId } = useContentShareState();
  const isScreenSharing = !!sharingAttendeeId;

  const formatTime = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="meeting-controls">
      <div className="controls-left">
        <button
          className={`control-btn ${muted ? 'active' : ''}`}
          onClick={toggleMute}
          title={muted ? 'Unmute' : 'Mute'}
        >
          {muted ? '🔇' : '🎤'}
        </button>
        <button
          className={`control-btn ${!isVideoEnabled ? 'active' : ''}`}
          onClick={toggleVideo}
          title={isVideoEnabled ? 'Turn off camera' : 'Turn on camera'}
        >
          {isVideoEnabled ? '📹' : '📷'}
        </button>
      </div>

      <div className="controls-center">
        <button
          className={`control-btn ${isScreenSharing ? 'active' : ''}`}
          onClick={toggleContentShare}
          disabled={isLocalShareLoading}
          title={isScreenSharing ? 'Stop sharing' : 'Share screen'}
        >
          🖥️
        </button>

        {isHost && (
          <button
            className={`control-btn ${isRecording ? 'recording' : ''}`}
            onClick={onToggleRecord}
            title={isRecording ? `Recording ${formatTime(recordingTime)}` : 'Start recording'}
          >
            {isRecording ? `⏺ ${formatTime(recordingTime)}` : '⏺'}
          </button>
        )}

        <button
          className={`control-btn ${showChat ? 'active' : ''}`}
          onClick={onToggleChat}
          title="Chat"
        >
          💬
        </button>

        <button
          className="control-btn"
          onClick={onInvite}
          title="Invite participant"
        >
          ➕
        </button>

        <button
          className={`control-btn ${isScreenRecording ? 'recording' : ''}`}
          onClick={onToggleScreenRecord}
          title={isScreenRecording ? `Screen recording ${formatTime(screenRecordingTime)}` : 'Screen record'}
        >
          {isScreenRecording ? `📱 ${formatTime(screenRecordingTime)}` : '📱'}
        </button>

        <button
          className="control-btn"
          onClick={onCycleVirtualBg}
          title={`Virtual background: ${virtualBgMode}`}
        >
          {virtualBgMode === 'none' ? '🖼️' : virtualBgMode === 'blur' ? '🌫️' : '🔳'}
        </button>

        {isHost && (
          <button
            className="control-btn"
            onClick={onToggleBreakoutPanel}
            title="Breakout rooms"
          >
            👥
          </button>
        )}

        {isHost && waitingCount > 0 && (
          <div className="waiting-badge">{waitingCount}</div>
        )}
      </div>

      <div className="controls-right">
        <button className="control-btn leave-btn" onClick={onLeave} title="Leave meeting">
          📞 Leave
        </button>
      </div>
    </div>
  );
}
