/**
 * SalesforceConnectionBadge Component
 *
 * Displays a visual indicator showing whether a CRM record is connected/synced
 * with Salesforce. Shows connection status, last sync time, and provides
 * quick actions for manual sync.
 */

import React, { useState, useEffect } from 'react';
import { salesforceAPI } from '../services/api';
import './SalesforceConnectionBadge.css';

const SalesforceConnectionBadge = ({
  entityType = 'loan',  // 'loan', 'lead', 'contact'
  entityId,
  salesforceId,         // If passed directly, skip API check
  lastSyncedAt,         // Optional: last sync timestamp
  showDetails = true,   // Show expanded details on hover
  onSyncClick,          // Optional: callback when sync is clicked
  compact = false       // Compact mode for smaller displays
}) => {
  const [isConnected, setIsConnected] = useState(!!salesforceId);
  const [syncStatus, setSyncStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    // If salesforceId is passed, use it directly
    if (salesforceId) {
      setIsConnected(true);
      setSyncStatus({
        salesforce_id: salesforceId,
        last_synced_at: lastSyncedAt,
        status: 'connected'
      });
    }
  }, [salesforceId, lastSyncedAt]);

  const formatLastSync = (timestamp) => {
    if (!timestamp) return 'Never';

    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString();
  };

  const handleSyncClick = async (e) => {
    e.stopPropagation();

    if (onSyncClick) {
      onSyncClick();
      return;
    }

    // Default sync behavior
    try {
      setSyncing(true);

      // Call the appropriate push endpoint based on entity type
      if (entityType === 'loan') {
        await salesforceAPI.pushLoan(entityId);
      } else if (entityType === 'lead') {
        // For leads, we can use the same endpoint or add a specific one later
        await salesforceAPI.pushLoan(entityId);
      }

      // Update status after sync
      setSyncStatus(prev => ({
        ...prev,
        last_synced_at: new Date().toISOString()
      }));
    } catch (error) {
      console.error('Sync failed:', error);
    } finally {
      setSyncing(false);
    }
  };

  // Compact version - just an icon
  if (compact) {
    return (
      <span
        className={`sf-badge-compact ${isConnected ? 'connected' : 'disconnected'}`}
        title={isConnected ? `Connected to Salesforce (${salesforceId})` : 'Not connected to Salesforce'}
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M12.5 2C9.5 2 7 4.5 7 7.5c0 .3 0 .6.1.9C4.3 9 2 11.6 2 14.8 2 18.7 5.1 22 9 22h10c3.3 0 6-2.7 6-6 0-2.6-1.7-4.9-4-5.7v-.8C21 6.5 18.5 4 15.5 4c-1.1 0-2.1.3-3 .9z"/>
        </svg>
        {isConnected && <span className="sf-badge-check">✓</span>}
      </span>
    );
  }

  return (
    <div
      className={`salesforce-connection-badge ${isConnected ? 'connected' : 'disconnected'}`}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <div className="sf-badge-main">
        <span className="sf-badge-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
            <path d="M12.5 2C9.5 2 7 4.5 7 7.5c0 .3 0 .6.1.9C4.3 9 2 11.6 2 14.8 2 18.7 5.1 22 9 22h10c3.3 0 6-2.7 6-6 0-2.6-1.7-4.9-4-5.7v-.8C21 6.5 18.5 4 15.5 4c-1.1 0-2.1.3-3 .9z"/>
          </svg>
        </span>
        <span className="sf-badge-text">
          {isConnected ? 'Salesforce Connected' : 'Not Synced'}
        </span>
        {isConnected && (
          <span className="sf-badge-status">
            <span className="sf-status-dot"></span>
          </span>
        )}
      </div>

      {/* Tooltip with details */}
      {showDetails && showTooltip && (
        <div className="sf-badge-tooltip">
          <div className="sf-tooltip-header">
            <strong>Salesforce Integration</strong>
          </div>
          <div className="sf-tooltip-content">
            {isConnected ? (
              <>
                <div className="sf-tooltip-row">
                  <span className="sf-tooltip-label">Status:</span>
                  <span className="sf-tooltip-value connected">Connected</span>
                </div>
                <div className="sf-tooltip-row">
                  <span className="sf-tooltip-label">SF ID:</span>
                  <span className="sf-tooltip-value">{salesforceId || 'N/A'}</span>
                </div>
                <div className="sf-tooltip-row">
                  <span className="sf-tooltip-label">Last Sync:</span>
                  <span className="sf-tooltip-value">{formatLastSync(syncStatus?.last_synced_at || lastSyncedAt)}</span>
                </div>
                <button
                  className="sf-sync-button"
                  onClick={handleSyncClick}
                  disabled={syncing}
                >
                  {syncing ? 'Syncing...' : '↻ Sync Now'}
                </button>
              </>
            ) : (
              <>
                <p className="sf-tooltip-message">
                  This record is not linked to Salesforce.
                </p>
                <button
                  className="sf-sync-button"
                  onClick={handleSyncClick}
                  disabled={syncing}
                >
                  {syncing ? 'Pushing...' : 'Push to Salesforce'}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default SalesforceConnectionBadge;
