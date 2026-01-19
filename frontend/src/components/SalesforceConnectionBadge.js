/**
 * SalesforceConnectionBadge Component
 *
 * Displays a visual indicator showing whether a CRM record is linked to
 * a Salesforce record. Data flows ONE-WAY: Salesforce → CRM.
 * When Salesforce is updated, those changes sync to the CRM.
 */

import React, { useState, useEffect } from 'react';
import { salesforceAPI } from '../services/api';
import './SalesforceConnectionBadge.css';

const SalesforceConnectionBadge = ({
  entityType = 'loan',  // 'loan', 'lead', 'contact'
  entityId,
  salesforceId,         // Salesforce record ID if linked
  lastSyncedAt,         // When CRM was last updated from Salesforce
  showDetails = true,   // Show expanded details on hover
  onRefreshClick,       // Optional: callback when refresh is clicked
  compact = false       // Compact mode for smaller displays
}) => {
  const [isConnected, setIsConnected] = useState(!!salesforceId);
  const [syncStatus, setSyncStatus] = useState(null);
  const [showTooltip, setShowTooltip] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    // If salesforceId is passed, use it directly
    if (salesforceId) {
      setIsConnected(true);
      setSyncStatus({
        salesforce_id: salesforceId,
        last_synced_at: lastSyncedAt,
        status: 'connected'
      });
    } else {
      setIsConnected(false);
      setSyncStatus(null);
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

  const handleRefreshClick = async (e) => {
    e.stopPropagation();

    if (onRefreshClick) {
      onRefreshClick();
      return;
    }

    // Refresh from Salesforce (pull latest data)
    try {
      setRefreshing(true);

      if (entityType === 'loan' && entityId) {
        await salesforceAPI.pullLoan(entityId);
      }

      // Update status after refresh
      setSyncStatus(prev => ({
        ...prev,
        last_synced_at: new Date().toISOString()
      }));

      // Reload the page to show updated data
      window.location.reload();
    } catch (error) {
      console.error('Refresh from Salesforce failed:', error);
    } finally {
      setRefreshing(false);
    }
  };

  // Compact version - just an icon
  if (compact) {
    return (
      <span
        className={`sf-badge-compact ${isConnected ? 'connected' : 'disconnected'}`}
        title={isConnected ? `Linked to Salesforce (${salesforceId})` : 'Not linked to Salesforce'}
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
          {isConnected ? 'Salesforce Linked' : 'Not in Salesforce'}
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
            <strong>Salesforce Link</strong>
          </div>
          <div className="sf-tooltip-content">
            {isConnected ? (
              <>
                <div className="sf-tooltip-row">
                  <span className="sf-tooltip-label">Status:</span>
                  <span className="sf-tooltip-value connected">Linked</span>
                </div>
                <div className="sf-tooltip-row">
                  <span className="sf-tooltip-label">SF ID:</span>
                  <span className="sf-tooltip-value">{salesforceId || 'N/A'}</span>
                </div>
                <div className="sf-tooltip-row">
                  <span className="sf-tooltip-label">Last Updated:</span>
                  <span className="sf-tooltip-value">{formatLastSync(syncStatus?.last_synced_at || lastSyncedAt)}</span>
                </div>
                <p className="sf-tooltip-info">
                  Updates from Salesforce automatically sync to CRM.
                </p>
                <button
                  className="sf-sync-button"
                  onClick={handleRefreshClick}
                  disabled={refreshing}
                >
                  {refreshing ? 'Refreshing...' : '↻ Refresh from SF'}
                </button>
              </>
            ) : (
              <>
                <p className="sf-tooltip-message">
                  This record is not linked to a Salesforce record.
                </p>
                <p className="sf-tooltip-info">
                  Create this record in Salesforce to enable sync.
                </p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default SalesforceConnectionBadge;
