import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { impersonationAPI } from '../services/api';
import { useImpersonation } from '../contexts/ImpersonationContext';
import './ImpersonationBanner.css';

function ImpersonationBanner() {
  const navigate = useNavigate();
  const { isImpersonating, impersonationData, endImpersonation, getImpersonatedUser, getTimeRemaining } = useImpersonation();
  const [timeLeft, setTimeLeft] = useState(0);
  const [ending, setEnding] = useState(false);

  useEffect(() => {
    if (!isImpersonating) return;

    // Update timer every second
    const timer = setInterval(() => {
      const remaining = getTimeRemaining();
      setTimeLeft(remaining);

      // Auto-end when time expires
      if (remaining <= 0) {
        handleEnd();
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [isImpersonating, getTimeRemaining]);

  const formatTime = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
      return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }
    return `${minutes}:${String(secs).padStart(2, '0')}`;
  };

  const handleEnd = async () => {
    setEnding(true);

    try {
      await impersonationAPI.end();
      endImpersonation();
      // Redirect back to team members page
      navigate('/team-members');
    } catch (error) {
      console.error('Failed to end impersonation:', error);
      // End locally even if API call fails
      endImpersonation();
      navigate('/team-members');
    }
  };

  if (!isImpersonating) return null;

  const impersonatedUser = getImpersonatedUser();
  if (!impersonatedUser) return null;

  // PHASE 4: Format permission role for display
  const formatRole = (role) => {
    if (!role) return 'Unknown Role';

    const roleMap = {
      'management': 'Management Role',
      'sales': 'Sales Role',
      'operations': 'Operations Role'
    };

    return roleMap[role.toLowerCase()] || role;
  };

  return (
    <div className="impersonation-banner">
      <div className="banner-content">
        <div className="banner-icon">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M10 2C5.58172 2 2 5.58172 2 10C2 14.4183 5.58172 18 10 18C14.4183 18 18 14.4183 18 10C18 5.58172 14.4183 2 10 2Z" fill="currentColor" opacity="0.2"/>
            <path d="M10 6C8.89543 6 8 6.89543 8 8C8 9.10457 8.89543 10 10 10C11.1046 10 12 9.10457 12 8C12 6.89543 11.1046 6 10 6Z" fill="currentColor"/>
            <path d="M10 11C7.79086 11 6 12.7909 6 15V16H14V15C14 12.7909 12.2091 11 10 11Z" fill="currentColor"/>
          </svg>
        </div>
        <div className="banner-text">
          <strong>IMPERSONATING:</strong>
          <span className="user-name">
            {impersonatedUser.first_name} {impersonatedUser.last_name}
          </span>
          <span className="separator">•</span>
          <span className="user-role">{formatRole(impersonatedUser.permission_role || impersonatedUser.role)}</span>
          <span className="separator">•</span>
          <span className={`timer ${timeLeft < 300 ? 'warning' : ''}`}>
            {formatTime(timeLeft)} remaining
          </span>
        </div>
      </div>
      <button
        className="exit-btn"
        onClick={handleEnd}
        disabled={ending}
      >
        {ending ? 'Ending...' : 'Exit Impersonation'}
      </button>
    </div>
  );
}

export default ImpersonationBanner;
