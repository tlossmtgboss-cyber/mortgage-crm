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

  // Check if in read-only mode
  const isReadOnly = impersonationData?.mode === 'read_only';

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
    <div className={`impersonation-banner ${isReadOnly ? 'read-only-mode' : 'full-access-mode'}`}>
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
          {isReadOnly && (
            <>
              <span className="mode-badge read-only" title="Write operations are disabled in read-only mode">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M12 2C9.23858 2 7 4.23858 7 7V10H6C4.89543 10 4 10.8954 4 12V20C4 21.1046 4.89543 22 6 22H18C19.1046 22 20 21.1046 20 20V12C20 10.8954 19.1046 10 18 10H17V7C17 4.23858 14.7614 2 12 2ZM9 7C9 5.34315 10.3431 4 12 4C13.6569 4 15 5.34315 15 7V10H9V7Z" fill="currentColor"/>
                </svg>
                READ-ONLY
              </span>
              <span className="separator">•</span>
            </>
          )}
          {!isReadOnly && (
            <>
              <span className="mode-badge full-access" title="Full access mode - all actions are available">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M7 7V10H6C4.89543 10 4 10.8954 4 12V20C4 21.1046 4.89543 22 6 22H18C19.1046 22 20 21.1046 20 20V12C20 10.8954 19.1046 10 18 10H9V7C9 5.34315 10.3431 4 12 4C13.3062 4 14.4175 4.83481 14.8293 6H16.8999C16.4367 3.71776 14.419 2 12 2C9.23858 2 7 4.23858 7 7Z" fill="currentColor"/>
                </svg>
                FULL ACCESS
              </span>
              <span className="separator">•</span>
            </>
          )}
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
