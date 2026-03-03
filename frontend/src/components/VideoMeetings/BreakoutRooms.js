/**
 * BreakoutRooms — Breakout room panel for video meetings.
 *
 * Extracted from MeetingRoom.js breakout room logic.
 * Handles create, join, leave, close breakout rooms via backend API.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { getAuthHeaders } from '../../utils/auth';
import { toast } from '../../utils/toast';

const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

const POLL_INTERVAL = 5000;

export default function BreakoutRooms({
  meetingId,
  isHost,
  currentBreakoutRoom,
  onBreakoutRoomChange,
  onClose,
}) {
  const [rooms, setRooms] = useState([]);
  const [newRoomName, setNewRoomName] = useState('');
  const [creating, setCreating] = useState(false);
  const pollRef = useRef(null);

  const fetchRooms = useCallback(async () => {
    if (!meetingId) return;
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/meetings/rooms/${meetingId}/breakout-rooms`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setRooms(data.breakout_rooms || []);
      }
    } catch {
      // silent fail for polling
    }
  }, [meetingId]);

  // Poll for breakout room updates
  useEffect(() => {
    fetchRooms();
    pollRef.current = setInterval(fetchRooms, POLL_INTERVAL);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchRooms]);

  const createRoom = useCallback(async () => {
    if (!newRoomName.trim()) return;
    setCreating(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/meetings/rooms/${meetingId}/breakout-rooms`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
          body: JSON.stringify({ room_name: newRoomName.trim() }),
        }
      );
      if (response.ok) {
        setNewRoomName('');
        await fetchRooms();
        toast.success('Breakout room created');
      } else {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to create breakout room');
      }
    } catch (err) {
      toast.error(err.message);
    } finally {
      setCreating(false);
    }
  }, [meetingId, newRoomName, fetchRooms]);

  const joinRoom = useCallback(async (breakoutId) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/meetings/rooms/${meetingId}/breakout-rooms/${breakoutId}/join`,
        { method: 'POST', headers: getAuthHeaders() }
      );
      if (response.ok) {
        onBreakoutRoomChange(breakoutId);
        toast.success('Joined breakout room');
      } else {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to join breakout room');
      }
    } catch (err) {
      toast.error(err.message);
    }
  }, [meetingId, onBreakoutRoomChange]);

  const leaveRoom = useCallback(async () => {
    if (!currentBreakoutRoom) return;
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/meetings/rooms/${meetingId}/breakout-rooms/${currentBreakoutRoom}/leave`,
        { method: 'POST', headers: getAuthHeaders() }
      );
      if (response.ok) {
        onBreakoutRoomChange(null);
        toast.info('Returned to main room');
      }
    } catch (err) {
      toast.error('Failed to leave breakout room');
    }
  }, [meetingId, currentBreakoutRoom, onBreakoutRoomChange]);

  const closeRoom = useCallback(async (breakoutId) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/meetings/rooms/${meetingId}/breakout-rooms/${breakoutId}/close`,
        { method: 'POST', headers: getAuthHeaders() }
      );
      if (response.ok) {
        if (currentBreakoutRoom === breakoutId) {
          onBreakoutRoomChange(null);
        }
        await fetchRooms();
        toast.success('Breakout room closed');
      } else {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to close breakout room');
      }
    } catch (err) {
      toast.error(err.message);
    }
  }, [meetingId, currentBreakoutRoom, onBreakoutRoomChange, fetchRooms]);

  return (
    <div className="breakout-panel">
      <div className="breakout-header">
        <h3>Breakout Rooms</h3>
        <button className="panel-close-btn" onClick={onClose}>&times;</button>
      </div>

      {currentBreakoutRoom && (
        <div className="breakout-current">
          <span>In breakout room</span>
          <button className="btn-secondary btn-sm" onClick={leaveRoom}>
            Return to Main
          </button>
        </div>
      )}

      <div className="breakout-list">
        {rooms.length === 0 && (
          <p className="breakout-empty">No breakout rooms yet</p>
        )}
        {rooms.map((room) => (
          <div key={room.id} className="breakout-room-item">
            <div className="breakout-room-info">
              <span className="breakout-room-name">{room.room_name}</span>
              <span className="breakout-room-count">
                {room.participant_count}/{room.max_participants || 10}
              </span>
            </div>
            <div className="breakout-room-actions">
              {currentBreakoutRoom !== room.id && (
                <button
                  className="btn-primary btn-sm"
                  onClick={() => joinRoom(room.id)}
                >
                  Join
                </button>
              )}
              {isHost && (
                <button
                  className="btn-danger btn-sm"
                  onClick={() => closeRoom(room.id)}
                >
                  Close
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {isHost && (
        <div className="breakout-create">
          <input
            type="text"
            value={newRoomName}
            onChange={(e) => setNewRoomName(e.target.value)}
            placeholder="Room name"
            maxLength={50}
            className="breakout-name-input"
          />
          <button
            className="btn-primary btn-sm"
            onClick={createRoom}
            disabled={creating || !newRoomName.trim()}
          >
            {creating ? 'Creating...' : 'Create'}
          </button>
        </div>
      )}
    </div>
  );
}
