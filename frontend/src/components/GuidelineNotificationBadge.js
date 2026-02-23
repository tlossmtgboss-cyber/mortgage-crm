import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import './GuidelineNotificationBadge.css';

const GuidelineNotificationBadge = ({ userId }) => {
  const [hasNewUpdates, setHasNewUpdates] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    checkForNewUpdates();
    const interval = setInterval(checkForNewUpdates, 2 * 60 * 1000); // Check every 2 minutes
    return () => clearInterval(interval);
  }, [userId]);

  const checkForNewUpdates = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/guideline-updates/check-new?user_id=${userId}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to check for new updates');
      }

      const data = await response.json();
      setHasNewUpdates(data.has_new_updates);
      setUnreadCount(data.unread_count);
    } catch (error) {
      console.error('Error checking for new updates:', error);
    }
  };

  if (!hasNewUpdates) return null;

  return (
    <span className="notification-badge" title={`${unreadCount} new guideline update${unreadCount !== 1 ? 's' : ''}`}>
      <svg className="star-icon" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
      </svg>
      {unreadCount > 0 && (
        <span className="badge-count">{unreadCount}</span>
      )}
    </span>
  );
};

export default GuidelineNotificationBadge;
