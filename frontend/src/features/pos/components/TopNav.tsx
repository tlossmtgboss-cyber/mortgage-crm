import React from 'react';

export interface TopNavProps {
  saveState: 'idle' | 'saving' | 'saved' | 'error';
  userInitials: string;
  onExit?: () => void;
}

export const TopNav: React.FC<TopNavProps> = ({ saveState, userInitials, onExit }) => {
  const saveMessage = {
    idle: '',
    saving: 'Saving…',
    saved: 'Saved · just now',
    error: 'Save failed',
  }[saveState];

  return (
    <header className="pos-topnav">
      <div className="pos-topnav__left">
        <span className="pos-topnav__brand">
          <PerenniaLogo />
          <span className="pos-topnav__brand-name">Perennia</span>
        </span>
      </div>
      <div className="pos-topnav__right">
        {saveState !== 'idle' && (
          <div className="pos-topnav__save-status">
            {saveState === 'saved' && <span className="pos-topnav__save-dot" />}
            <span>{saveMessage}</span>
          </div>
        )}
        <button type="button" className="pos-topnav__exit-btn" onClick={onExit}>
          <ClockIcon />
          <span>Save &amp; exit</span>
        </button>
        <div className="pos-seal" style={{ width: 36, height: 36, fontSize: 14 }}>
          {userInitials}
        </div>
      </div>
    </header>
  );
};

const PerenniaLogo: React.FC = () => (
  <svg width="26" height="26" viewBox="0 0 32 32" fill="none" aria-hidden>
    <path d="M16 2 C 9 2 4 8 4 16 C 4 22 8 27 14 28 L 14 14 C 14 11 16 9 19 9 C 22 9 24 11 24 14 C 24 17 22 19 19 19 L 17 19 L 17 28 C 24 27 28 22 28 16 C 28 8 23 2 16 2 Z" fill="#1F3D2E" />
    <circle cx="19" cy="14" r="2.5" fill="#B8924A" />
  </svg>
);

const ClockIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M12 2a10 10 0 1 0 10 10" />
    <path d="M12 6v6l4 2" />
  </svg>
);
