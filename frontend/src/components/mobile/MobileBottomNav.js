import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import './MobileBottomNav.css';

const tabs = [
  { key: 'home', path: '/aria', icon: 'home', label: 'Home' },
  { key: 'calendar', path: '/aria/calendar', icon: 'calendar', label: 'Calendar' },
  { key: 'add', path: null, icon: 'add', label: '' },
  { key: 'contacts', path: '/leads', icon: 'contacts', label: 'Contacts' },
  { key: 'notifications', path: '/aria/notifications', icon: 'bell', label: 'Alerts' },
];

const TabIcon = ({ icon, active }) => {
  const color = active ? '#1a73e8' : '#9ca3af';
  switch (icon) {
    case 'home':
      return (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9z" />
          <polyline points="9 22 9 12 15 12 15 22" />
        </svg>
      );
    case 'calendar':
      return (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
          <line x1="16" y1="2" x2="16" y2="6" />
          <line x1="8" y1="2" x2="8" y2="6" />
          <line x1="3" y1="10" x2="21" y2="10" />
        </svg>
      );
    case 'add':
      return (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      );
    case 'contacts':
      return (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      );
    case 'bell':
      return (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
      );
    default:
      return null;
  }
};

export default function MobileBottomNav({ onAddPress }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);

  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);

  const isActive = (tab) => {
    if (tab.key === 'home') return location.pathname === '/aria';
    if (tab.path) return location.pathname === tab.path || location.pathname.startsWith(tab.path + '/');
    return false;
  };

  const handlePress = (tab) => {
    if (tab.key === 'add') {
      if (onAddPress) onAddPress();
      else navigate('/aria/calendar?action=new');
      return;
    }
    if (tab.path && location.pathname !== tab.path) {
      navigate(tab.path);
    }
  };

  if (!isMobile) return null;

  return (
    <nav className="mobile-bottom-nav">
      {tabs.map((tab) => {
        const active = isActive(tab);
        if (tab.key === 'add') {
          return (
            <button key={tab.key} className="mobile-bottom-nav__tab mobile-bottom-nav__fab" onClick={() => handlePress(tab)} aria-label="Create new">
              <div className="mobile-bottom-nav__fab-circle">
                <TabIcon icon={tab.icon} active={false} />
              </div>
            </button>
          );
        }
        return (
          <button key={tab.key} className={`mobile-bottom-nav__tab ${active ? 'mobile-bottom-nav__tab--active' : ''}`} onClick={() => handlePress(tab)} aria-label={tab.label}>
            <TabIcon icon={tab.icon} active={active} />
          </button>
        );
      })}
    </nav>
  );
}
