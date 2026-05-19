import React, { useState, useEffect } from 'react';
import api from '../../services/api';
import './PURLWidget.css';
import { toast } from '../../utils/toast';

/**
 * PURL Widget - Integrates into Lead/Loan profile pages
 * Shows PURL status, token management, and quick actions
 */
function PURLWidget({ leadId, loanId, contactData }) {
  const [workspace, setWorkspace] = useState(null);
  const [tokens, setTokens] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [copiedToken, setCopiedToken] = useState(null);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState(null);

  const PURL_DOMAIN = process.env.REACT_APP_PURL_DOMAIN || 'http://localhost:3000';

  useEffect(() => {
    loadPURLData();
  }, [leadId, loanId]);

  const loadPURLData = async () => {
    try {
      setError(null);
      const entityId = leadId || loanId;
      const entityType = leadId ? 'lead' : 'loan';

      const response = await api.get(
        `/api/v1/purl-admin/workspaces/by-${entityType}/${entityId}`
      );

      if (response.data.workspace) {
        setWorkspace(response.data.workspace);
        setTokens(response.data.tokens || []);
      }
    } catch (error) {
      if (error.response?.status !== 404) {
        console.error('Failed to load PURL data:', error);
        setError('Failed to load portal data');
      }
      // 404 is expected when no workspace exists yet
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreatePURL = async () => {
    if (!contactData?.email) {
      setError('Email is required to create a client portal');
      return;
    }

    setIsCreating(true);
    setError(null);

    try {
      const response = await api.post(
        '/api/v1/purl-admin/workspaces',
        {
          first_name: contactData.firstName || contactData.first_name || 'Client',
          last_name: contactData.lastName || contactData.last_name || '',
          email: contactData.email,
          phone: contactData.phone,
          loan_purpose: contactData.loanPurpose || contactData.loan_purpose,
          loan_amount: contactData.loanAmount || contactData.loan_amount,
          lead_id: leadId,
          loan_id: loanId
        }
      );

      setWorkspace(response.data);
      setTokens([{
        id: response.data.token_id,
        token: response.data.token,
        token_prefix: response.data.token?.substring(0, 16) || 'purl_',
        status: 'active',
        created_at: new Date().toISOString()
      }]);

    } catch (error) {
      console.error('Failed to create PURL:', error);
      setError(error.response?.data?.detail || 'Failed to create client portal');
    } finally {
      setIsCreating(false);
    }
  };

  const handleGenerateNewToken = async () => {
    if (!window.confirm('Generate a new access token? Previous tokens will remain active unless revoked.')) {
      return;
    }

    try {
      const response = await api.post(
        `/api/v1/purl-admin/workspaces/${workspace.workspace_id || workspace.id}/tokens`,
        { scope: 'write', expires_in_days: 365 }
      );

      setTokens([response.data, ...tokens]);

      // Copy to clipboard
      if (response.data.purl_url) {
        navigator.clipboard.writeText(response.data.purl_url);
      }

    } catch (error) {
      console.error('Failed to generate token:', error);
      setError('Failed to generate new token');
    }
  };

  const handleRevokeToken = async (tokenId) => {
    if (!window.confirm('Revoke this token? The borrower will lose access.')) {
      return;
    }

    try {
      await api.post(
        `/api/v1/purl-admin/tokens/${tokenId}/revoke`,
        { reason: 'Revoked by loan officer' }
      );

      setTokens(tokens.map(t =>
        t.id === tokenId ? { ...t, status: 'revoked' } : t
      ));

    } catch (error) {
      console.error('Failed to revoke token:', error);
      setError('Failed to revoke token');
    }
  };

  const handleCopyLink = (token) => {
    const slug = workspace.workspace_slug || workspace.slug;
    const purl = `${PURL_DOMAIN}/portal/${slug}?token=${token}`;
    navigator.clipboard.writeText(purl);
    setCopiedToken(token);
    setTimeout(() => setCopiedToken(null), 2000);
  };

  const handleResendEmail = async () => {
    try {
      await api.post(
        `/api/v1/purl-admin/workspaces/${workspace.workspace_id || workspace.id}/resend-invite`
      );
      setError(null);
      toast.success('Invitation email resent!');
    } catch (error) {
      console.error('Failed to resend email:', error);
      setError('Failed to resend invitation');
    }
  };

  if (isLoading) {
    return (
      <div className="purl-widget loading">
        <div className="purl-spinner"></div>
      </div>
    );
  }

  // No PURL created yet
  if (!workspace) {
    return (
      <div className="purl-widget no-portal">
        <div className="purl-widget-header">
          <h3>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
            Client Portal
          </h3>
          <span className="purl-badge badge-gray">Not Created</span>
        </div>

        <div className="purl-widget-body">
          {error && <div className="purl-error">{error}</div>}

          <p className="purl-description">
            Create a secure portal for this client to complete their application,
            upload documents, and track loan progress.
          </p>

          <button
            className="purl-btn-primary purl-btn-block"
            onClick={handleCreatePURL}
            disabled={isCreating}
          >
            {isCreating ? (
              <>
                <span className="purl-spinner-small"></span>
                Creating...
              </>
            ) : (
              <>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
                Create Client Portal
              </>
            )}
          </button>
        </div>
      </div>
    );
  }

  // PURL exists
  const activeTokens = tokens.filter(t => t.status === 'active');
  const latestToken = activeTokens[0];
  const slug = workspace.workspace_slug || workspace.slug;
  // Include token in portal URL for direct access
  const portalUrl = latestToken?.token
    ? `${PURL_DOMAIN}/portal/${slug}?token=${latestToken.token}`
    : `${PURL_DOMAIN}/portal/${slug}`;

  return (
    <div className="purl-widget has-portal">
      <div className="purl-widget-header">
        <div className="purl-header-left">
          <h3>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
            Client Portal
          </h3>
          <span className={`purl-badge badge-${workspace.status}`}>
            {(workspace.status || 'active').replace('_', ' ')}
          </span>
        </div>

        <a
          href={portalUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="purl-btn-icon"
          title="Open Portal"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
        </a>
      </div>

      <div className="purl-widget-body">
        {error && <div className="purl-error">{error}</div>}

        {/* Quick Stats */}
        <div className="purl-portal-stats">
          <div className="purl-stat">
            <span className="purl-stat-label">Application</span>
            <span className="purl-stat-value">
              {workspace.application_status || 'Not Started'}
            </span>
          </div>
          <div className="purl-stat">
            <span className="purl-stat-label">Documents</span>
            <span className="purl-stat-value">
              {workspace.document_count || 0} uploaded
            </span>
          </div>
          <div className="purl-stat">
            <span className="purl-stat-label">Last Activity</span>
            <span className="purl-stat-value">
              {workspace.last_activity
                ? new Date(workspace.last_activity).toLocaleDateString()
                : 'Never'
              }
            </span>
          </div>
        </div>

        {/* Active Token */}
        {latestToken && (
          <div className="purl-token-section">
            <div className="purl-token-header">
              <span className="purl-label">Active Access Token</span>
              <div className="purl-token-actions">
                <button
                  className="purl-btn-icon-small"
                  onClick={() => handleCopyLink(latestToken.token)}
                  title="Copy Portal Link"
                >
                  {copiedToken === latestToken.token ? (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2D7A52" strokeWidth="2">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            <div className="purl-token-display">
              <code>{latestToken.token_prefix}...</code>
              <span className="purl-token-status">Active</span>
            </div>

            {latestToken.last_used_at && (
              <div className="purl-token-meta">
                Last used: {new Date(latestToken.last_used_at).toLocaleString()}
              </div>
            )}
          </div>
        )}

        {/* Quick Actions */}
        <div className="purl-action-buttons">
          <button
            className="purl-btn-secondary purl-btn-sm"
            onClick={handleResendEmail}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
            Resend Invite
          </button>

          <button
            className="purl-btn-secondary purl-btn-sm"
            onClick={handleGenerateNewToken}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
            New Token
          </button>

          {activeTokens.length > 0 && (
            <button
              className="purl-btn-danger purl-btn-sm"
              onClick={() => handleRevokeToken(latestToken.id)}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
              Revoke Access
            </button>
          )}
        </div>

        {/* Additional Tokens Info */}
        {activeTokens.length > 1 && (
          <div className="purl-additional-tokens">
            <span className="purl-token-count">
              {activeTokens.length} active tokens
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export default PURLWidget;
