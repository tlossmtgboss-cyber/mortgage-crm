/**
 * PERENNIA AI — CallIntelligenceSlidePanel (v3 — Props Fix)
 *
 * FIXED: Previously only passed onClose and initialContext (2 of 8 props).
 * Now passes all 8 required props by pulling from auth utils, initialContext,
 * and environment config.
 */

import React, { lazy, Suspense, useMemo, useState, useEffect } from 'react';
import { API_BASE_URL } from '../../services/api';
import { getUserData } from '../../utils/tokenStore';

const MobileCallIntelligencePanel = lazy(() =>
  import('../MobileCallIntelligencePanel')
);

// WS must target the API host. window.location points at app.perenniaai.com
// on web (no WS backend) and capacitor://localhost in the native app.
const WS_BASE_URL = API_BASE_URL
  .replace('https://', 'wss://')
  .replace('http://', 'ws://');

export default function CallIntelligenceSlidePanel({
  isOpen,
  onClose,
  initialContext,
}) {
  const [user, setUser] = useState(null);

  useEffect(() => {
    // getUserData reads Capacitor Preferences on native (localStorage is
    // not populated there), falling back to localStorage on web.
    let cancelled = false;
    Promise.resolve(getUserData()).then((u) => {
      if (!cancelled) setUser(u);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [isOpen]);

  const panelProps = useMemo(() => ({
    callControlId:
      initialContext?.callControlId ||
      null,

    contactId:
      initialContext?.contactId ||
      null,

    borrowerState:
      initialContext?.borrowerState ||
      null,

    borrowerContext:
      initialContext?.borrowerContext ||
      null,

    currentUser: user
      ? { id: user.id || user.user_id, name: user.full_name || user.name, email: user.email }
      : null,

    wsBaseUrl: WS_BASE_URL,

    onClose,

    onApplicationCreated: (data) => {
      console.log('Application created from CI:', data);
    },
  }), [initialContext, user, onClose]);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        bottom: 0,
        width: '100%',
        maxWidth: '420px',
        zIndex: 1000,
        background: '#060A10',
        boxShadow: '-4px 0 24px rgba(0,0,0,0.5)',
        transform: isOpen ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 0.3s ease',
      }}
    >
      <Suspense
        fallback={
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            height: '100%', color: 'rgba(255,255,255,0.4)',
            fontFamily: "'DM Sans', sans-serif", fontSize: '13px',
          }}>
            Loading Call Intelligence...
          </div>
        }
      >
        <MobileCallIntelligencePanel {...panelProps} />
      </Suspense>
    </div>
  );
}
