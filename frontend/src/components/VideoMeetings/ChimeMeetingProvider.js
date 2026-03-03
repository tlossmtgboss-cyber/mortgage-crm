/**
 * ChimeMeetingProvider — Amazon Chime SDK wrapper for video meetings.
 *
 * Provides Chime MeetingProvider context and a custom hook (useChimeMeeting)
 * that handles joining/leaving meetings via the backend API + Chime SDK.
 */
import React, { createContext, useContext, useCallback, useState, useRef, useEffect } from 'react';
import {
  MeetingProvider,
  useMeetingManager,
  useMeetingStatus,
  MeetingStatus,
} from 'amazon-chime-sdk-component-library-react';
import { MeetingSessionConfiguration } from 'amazon-chime-sdk-js';
import { getAuthHeaders } from '../../utils/auth';
import { toast } from '../../utils/toast';

const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

const ChimeMeetingContext = createContext(null);

export function useChimeMeeting() {
  const ctx = useContext(ChimeMeetingContext);
  if (!ctx) throw new Error('useChimeMeeting must be used inside <ChimeMeetingProvider>');
  return ctx;
}

function ChimeMeetingInner({ children }) {
  const meetingManager = useMeetingManager();
  const meetingStatus = useMeetingStatus();
  const [chimeJoinInfo, setChimeJoinInfo] = useState(null);
  const joinedRef = useRef(false);

  const joinMeeting = useCallback(async (meetingData, attendeeData) => {
    if (joinedRef.current) return;
    try {
      const configuration = new MeetingSessionConfiguration(meetingData, attendeeData);
      await meetingManager.join(configuration);
      await meetingManager.start();
      joinedRef.current = true;
      setChimeJoinInfo({ meeting: meetingData, attendee: attendeeData });
    } catch (err) {
      console.error('Chime join error:', err);
      toast.error('Failed to join video meeting');
      throw err;
    }
  }, [meetingManager]);

  const joinMeetingByRoomCode = useCallback(async (roomCode, displayName, password) => {
    try {
      const headers = { 'Content-Type': 'application/json', ...getAuthHeaders() };
      const body = { display_name: displayName };
      if (password) body.password = password;

      const response = await fetch(`${API_BASE}/api/v1/meetings/join/${roomCode}`, {
        method: 'GET',
        headers,
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to join meeting');
      }

      const data = await response.json();

      if (data.chime) {
        await joinMeeting(data.chime.meeting, data.chime.attendee);
      }

      return data;
    } catch (err) {
      console.error('Join by room code error:', err);
      throw err;
    }
  }, [joinMeeting]);

  const leaveMeeting = useCallback(async () => {
    try {
      if (joinedRef.current) {
        await meetingManager.leave();
        joinedRef.current = false;
        setChimeJoinInfo(null);
      }
    } catch (err) {
      console.error('Leave meeting error:', err);
    }
  }, [meetingManager]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (joinedRef.current) {
        meetingManager.leave().catch(() => {});
      }
    };
  }, [meetingManager]);

  const value = {
    joinMeeting,
    joinMeetingByRoomCode,
    leaveMeeting,
    meetingStatus,
    isJoined: meetingStatus === MeetingStatus.Succeeded,
    isConnecting: meetingStatus === MeetingStatus.Loading || meetingStatus === MeetingStatus.Reconnecting,
    chimeJoinInfo,
    meetingManager,
  };

  return (
    <ChimeMeetingContext.Provider value={value}>
      {children}
    </ChimeMeetingContext.Provider>
  );
}

export default function ChimeMeetingProvider({ children }) {
  return (
    <MeetingProvider>
      <ChimeMeetingInner>{children}</ChimeMeetingInner>
    </MeetingProvider>
  );
}
