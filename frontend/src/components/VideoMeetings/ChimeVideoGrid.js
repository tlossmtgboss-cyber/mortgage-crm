/**
 * ChimeVideoGrid — Video tile grid using Amazon Chime SDK.
 *
 * Renders local + remote video tiles in a responsive grid layout.
 * Replaces manual RTCPeerConnection + remoteStreams management.
 */
import React, { useMemo } from 'react';
import {
  useRemoteVideoTileState,
  useLocalVideo,
  useRosterState,
  useActiveSpeakersState,
  LocalVideo,
  RemoteVideo,
} from 'amazon-chime-sdk-component-library-react';

export default function ChimeVideoGrid({ currentBreakoutRoom, participantBreakoutMap }) {
  const { tileId: localTileId, isVideoEnabled } = useLocalVideo();
  const { tiles: remoteTiles } = useRemoteVideoTileState();
  const { roster } = useRosterState();
  const activeSpeakers = useActiveSpeakersState();

  // Filter remote tiles based on breakout room assignment
  const visibleTiles = useMemo(() => {
    if (!currentBreakoutRoom) return remoteTiles;
    return remoteTiles.filter(tileId => {
      const attendeeId = Object.keys(roster).find(id => {
        const rosterEntry = roster[id];
        return rosterEntry?.tileId === tileId;
      });
      if (!attendeeId) return true;
      const participantRoom = participantBreakoutMap?.[attendeeId];
      return !participantRoom || participantRoom === currentBreakoutRoom;
    });
  }, [remoteTiles, currentBreakoutRoom, participantBreakoutMap, roster]);

  const totalTiles = visibleTiles.length + 1; // +1 for local
  const gridClass = totalTiles <= 2 ? 'video-grid-2' : totalTiles <= 4 ? 'video-grid-4' : 'video-grid-many';

  return (
    <div className={`video-grid ${gridClass}`}>
      {/* Local video tile */}
      <div className="video-container local">
        {isVideoEnabled ? (
          <LocalVideo className="video-element" />
        ) : (
          <div className="video-placeholder">
            <div className="avatar-circle">You</div>
          </div>
        )}
        <div className="participant-label">You</div>
      </div>

      {/* Remote video tiles */}
      {visibleTiles.map(tileId => {
        const attendeeId = Object.keys(roster).find(id => roster[id]?.tileId === tileId);
        const attendeeName = attendeeId ? (roster[attendeeId]?.name || 'Participant') : 'Participant';
        const isActiveSpeaker = attendeeId && activeSpeakers.includes(attendeeId);

        return (
          <div
            key={tileId}
            className={`video-container remote ${isActiveSpeaker ? 'active-speaker' : ''}`}
          >
            <RemoteVideo tileId={tileId} className="video-element" />
            <div className="participant-label">{attendeeName}</div>
            {isActiveSpeaker && <div className="speaking-indicator" />}
          </div>
        );
      })}
    </div>
  );
}
