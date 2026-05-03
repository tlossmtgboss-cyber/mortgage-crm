import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import './InboundCallLightbox.css';

const WS_BASE_URL =
  process.env.REACT_APP_WS_URL ||
  (window.location.protocol === 'https:' ? 'wss://' : 'ws://') +
  (process.env.REACT_APP_API_URL?.replace(/^https?:\/\//, '') || 'localhost:8000');

function useInboundCallSocket() {
  const [callData, setCallData] = useState(null);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);
  const attemptsRef = useRef(0);

  const connect = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) return;

    const url = `${WS_BASE_URL}/ws/calls/inbound?token=${encodeURIComponent(token)}`;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        attemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'inbound_call') {
            setCallData(data);
          }
        } catch (e) {
          // ignore parse errors
        }
      };

      ws.onclose = (event) => {
        // 4001 = auth failure — don't retry with the same invalid token
        if (event.code === 4001) return;
        if (attemptsRef.current < 10) {
          const delay = Math.min(2000 * Math.pow(1.5, attemptsRef.current), 30000);
          reconnectRef.current = setTimeout(() => {
            attemptsRef.current++;
            connect();
          }, delay);
        }
      };

      ws.onerror = () => {
        // onclose fires after onerror
      };
    } catch (e) {
      // connection failed
    }
  }, []);

  const dismiss = useCallback(() => {
    setCallData(null);
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return { callData, dismiss };
}

function formatPhone(phone) {
  if (!phone) return '';
  const digits = phone.replace(/\D/g, '');
  const last10 = digits.slice(-10);
  if (last10.length === 10) {
    return `(${last10.slice(0, 3)}) ${last10.slice(3, 6)}-${last10.slice(6)}`;
  }
  return phone;
}

export default function InboundCallLightbox() {
  const { callData, dismiss } = useInboundCallSocket();
  const navigate = useNavigate();
  const [visible, setVisible] = useState(false);
  const dismissTimerRef = useRef(null);

  const clearDismissTimer = useCallback(() => {
    if (dismissTimerRef.current) {
      clearTimeout(dismissTimerRef.current);
      dismissTimerRef.current = null;
    }
  }, []);

  const scheduleDismiss = useCallback(() => {
    setVisible(false);
    clearDismissTimer();
    dismissTimerRef.current = setTimeout(dismiss, 300);
  }, [dismiss, clearDismissTimer]);

  useEffect(() => {
    if (callData) {
      clearDismissTimer();
      setVisible(true);
      const timer = setTimeout(scheduleDismiss, 30000);
      return () => {
        clearTimeout(timer);
        clearDismissTimer();
      };
    }
    setVisible(false);
  }, [callData, scheduleDismiss, clearDismissTimer]);

  if (!callData) return null;

  const contact = callData.contact;
  const hasMatch = !!contact;

  const handleGoToProfile = () => {
    if (contact?.profile_url) {
      navigate(contact.profile_url);
    }
    scheduleDismiss();
  };

  const handleDismiss = () => {
    scheduleDismiss();
  };

  return (
    <div className={`icl-overlay${visible ? ' icl-overlay--visible' : ''}`} role="alert" aria-live="assertive">
      <div className={`icl-card${visible ? ' icl-card--visible' : ''}`}>
        <div className="icl-card__pulse" />

        <div className="icl-card__header">
          <div className="icl-card__icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/>
            </svg>
          </div>
          <div className="icl-card__title-group">
            <span className="icl-card__label">Incoming Teams Call</span>
            <span className="icl-card__phone">{formatPhone(callData.caller_phone)}</span>
          </div>
          <button
            type="button"
            className="icl-card__close"
            onClick={handleDismiss}
            aria-label="Dismiss"
          >
            &times;
          </button>
        </div>

        {hasMatch ? (
          <div className="icl-card__match">
            <div className="icl-card__avatar">
              {(contact.name || '?')[0].toUpperCase()}
            </div>
            <div className="icl-card__info">
              <div className="icl-card__name">{contact.name}</div>
              {contact.email && (
                <div className="icl-card__detail">{contact.email}</div>
              )}
              {contact.stage && (
                <div className="icl-card__detail">
                  <span className="icl-card__stage">{contact.stage}</span>
                  <span className="icl-card__match-type">
                    {contact.match_type === 'client_file' ? 'Client File' : 'Lead'}
                  </span>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="icl-card__no-match">
            <span>No matching contact found in CRM</span>
            <span className="icl-card__caller-name">
              {callData.caller_display_name || 'Unknown Caller'}
            </span>
          </div>
        )}

        <div className="icl-card__actions">
          {hasMatch && (
            <button
              type="button"
              className="icl-btn icl-btn--primary"
              onClick={handleGoToProfile}
            >
              Go to Profile
            </button>
          )}
          <button
            type="button"
            className="icl-btn icl-btn--ghost"
            onClick={handleDismiss}
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
