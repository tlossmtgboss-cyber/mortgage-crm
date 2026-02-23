import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import './GuidelineUpdatesSidebar.css';

const GuidelineUpdatesSidebar = ({ userId }) => {
  const [sidebarData, setSidebarData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedSource, setExpandedSource] = useState(null);

  useEffect(() => {
    fetchSidebarData();
    const interval = setInterval(fetchSidebarData, 5 * 60 * 1000); // Refresh every 5 minutes
    return () => clearInterval(interval);
  }, [userId]);

  const fetchSidebarData = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/guideline-updates/sidebar?user_id=${userId}&limit_per_source=5`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch sidebar data');
      }

      const data = await response.json();
      setSidebarData(data);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching sidebar data:', error);
      setLoading(false);
    }
  };

  const handleUpdateClick = async (updateId, url) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE_URL}/api/v1/guideline-updates/mark-viewed/${updateId}?user_id=${userId}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      // Refresh sidebar data to update unread status
      fetchSidebarData();

      // Open the guideline update in a new tab
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch (error) {
      console.error('Error marking update as viewed:', error);
    }
  };

  const toggleSource = (source) => {
    setExpandedSource(expandedSource === source ? null : source);
  };

  if (loading) {
    return (
      <div className="guideline-sidebar">
        <div className="sidebar-loading">Loading updates...</div>
      </div>
    );
  }

  if (!sidebarData) return null;

  return (
    <div className="guideline-sidebar">
      <div className="sidebar-header">
        <h3>Recent Guideline Updates</h3>
        {sidebarData.has_unread && (
          <span className="unread-indicator">New</span>
        )}
      </div>

      {sidebarData.sources.map((source) => (
        <SourceContainer
          key={source.source}
          source={source}
          isExpanded={expandedSource === source.source}
          onToggle={() => toggleSource(source.source)}
          onUpdateClick={handleUpdateClick}
        />
      ))}
    </div>
  );
};

const SourceContainer = ({ source, isExpanded, onToggle, onUpdateClick }) => {
  return (
    <div className={`source-container ${source.has_new_update ? 'has-new-update' : ''}`}>
      <div className="source-header" onClick={onToggle}>
        <div className="source-title">
          <h4>{source.source_name}</h4>
          {source.has_new_update && (
            <span className="new-badge">NEW</span>
          )}
        </div>
        <span className={`expand-icon ${isExpanded ? 'expanded' : ''}`}>▼</span>
      </div>

      {isExpanded && (
        <div className="source-updates">
          {source.updates.length === 0 ? (
            <div className="no-updates">No recent updates</div>
          ) : (
            <ul className="updates-list">
              {source.updates.map((update) => (
                <UpdateItem
                  key={update.id}
                  update={update}
                  onClick={() => onUpdateClick(update.id, update.url)}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

const UpdateItem = ({ update, onClick }) => {
  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  return (
    <li className="update-item" onClick={onClick}>
      <div className="update-header">
        {update.section_code && (
          <span className="section-code">{update.section_code}</span>
        )}
        <span className="update-date">{formatDate(update.published_date)}</span>
      </div>
      <div className="update-title">{update.title}</div>
      {update.is_new && (
        <span className="update-new-badge">New</span>
      )}
    </li>
  );
};

export default GuidelineUpdatesSidebar;
