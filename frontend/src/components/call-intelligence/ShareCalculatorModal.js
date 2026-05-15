/**
 * Share Calculator Modal
 *
 * Modal for sharing calculator results with borrowers.
 * Features:
 * - Generate shareable link with configurable expiration
 * - Copy link to clipboard
 * - Send via SMS/Email (future)
 * - QR code display
 */

import React, { useState } from 'react';
import { callMonitoringAPI } from '../../services/api';
import { toast } from '../../utils/toast';
import './ShareCalculatorModal.css';

const EXPIRATION_OPTIONS = [
  { value: 1, label: '24 hours' },
  { value: 7, label: '7 days' },
  { value: 30, label: '30 days' },
];

const ShareCalculatorModal = ({ artifact, onClose }) => {
  const [shareLink, setShareLink] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expiresInDays, setExpiresInDays] = useState(7);
  const [copied, setCopied] = useState(false);

  const content = artifact?.content || artifact?.structured_data || {};
  const calculatorType = content.calculator_type || 'calculator';
  const outputs = content.outputs || content;

  // Get display title based on calculator type
  const getTitle = () => {
    switch (calculatorType) {
      case 'piti':
        return `Monthly Payment: ${formatCurrency(outputs.total_payment)}`;
      case 'dti':
        return `DTI: ${formatPercent(outputs.back_end_ratio)}`;
      case 'ltv':
        return `LTV: ${formatPercent(outputs.ltv)}`;
      case 'affordability':
        return `Max Price: ${formatCurrency(outputs.max_purchase_price)}`;
      case 'closing_costs':
        return `Closing Costs: ${formatCurrency(outputs.total_estimated)}`;
      case 'amortization':
        return 'Amortization Schedule';
      default:
        return 'Calculator Result';
    }
  };

  // Format currency
  const formatCurrency = (value) => {
    if (value === null || value === undefined) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  // Format percentage
  const formatPercent = (value) => {
    if (value === null || value === undefined) return '-';
    return `${Number(value).toFixed(1)}%`;
  };

  // Generate share link
  const handleGenerateLink = async () => {
    setLoading(true);
    try {
      const response = await callMonitoringAPI.createShareLink(artifact.id, {
        expires_in_days: expiresInDays,
      });

      // Construct full URL
      const baseUrl = window.location.origin;
      const fullUrl = `${baseUrl}/shared/calculator/${response.share_token}`;
      setShareLink({
        ...response,
        fullUrl,
      });

      toast.success('Share link created');
    } catch (error) {
      console.error('Error creating share link:', error);
      toast.error('Failed to create share link');
    } finally {
      setLoading(false);
    }
  };

  // Copy link to clipboard
  const handleCopyLink = async () => {
    if (!shareLink) return;

    try {
      await navigator.clipboard.writeText(shareLink.fullUrl);
      setCopied(true);
      toast.success('Link copied to clipboard');
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Error copying to clipboard:', error);
      toast.error('Failed to copy link');
    }
  };

  // Format expiration date
  const formatExpiration = (isoDate) => {
    const date = new Date(isoDate);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  };

  return (
    <div className="share-modal-overlay" onClick={onClose}>
      <div className="share-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="share-modal-header">
          <div className="header-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2">
              <circle cx="18" cy="5" r="3" />
              <circle cx="6" cy="12" r="3" />
              <circle cx="18" cy="19" r="3" />
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
              <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
            </svg>
          </div>
          <h3>Share Calculator Result</h3>
          <button className="close-btn" onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Content Preview */}
        <div className="share-preview">
          <div className="preview-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#B8924A" strokeWidth="2">
              <rect x="4" y="2" width="16" height="20" rx="2" ry="2" />
              <line x1="8" y1="6" x2="16" y2="6" />
              <line x1="8" y1="10" x2="16" y2="10" />
              <line x1="8" y1="14" x2="12" y2="14" />
            </svg>
          </div>
          <div className="preview-info">
            <span className="preview-type">{calculatorType.toUpperCase().replace('_', ' ')}</span>
            <span className="preview-title">{getTitle()}</span>
          </div>
        </div>

        {/* Link Generation or Display */}
        {!shareLink ? (
          <div className="share-config">
            <label className="config-label">
              Link expires after:
              <select
                value={expiresInDays}
                onChange={(e) => setExpiresInDays(Number(e.target.value))}
                className="expiration-select"
              >
                {EXPIRATION_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>

            <button
              className="generate-btn"
              onClick={handleGenerateLink}
              disabled={loading}
            >
              {loading ? (
                <>
                  <span className="spinner" />
                  Generating...
                </>
              ) : (
                <>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                  </svg>
                  Generate Share Link
                </>
              )}
            </button>
          </div>
        ) : (
          <div className="share-link-display">
            <div className="link-success">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              Share link created!
            </div>

            <div className="link-container">
              <input
                type="text"
                readOnly
                value={shareLink.fullUrl}
                className="link-input"
              />
              <button
                className={`copy-btn ${copied ? 'copied' : ''}`}
                onClick={handleCopyLink}
              >
                {copied ? (
                  <>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    Copied!
                  </>
                ) : (
                  <>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                    Copy
                  </>
                )}
              </button>
            </div>

            <div className="link-meta">
              <span className="meta-item">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
                Expires: {formatExpiration(shareLink.expires_at)}
              </span>
            </div>

            {/* Share Actions */}
            <div className="share-actions">
              <button
                className="action-btn sms-btn"
                onClick={() => {
                  window.open(`sms:?body=Check out this calculator result: ${shareLink.fullUrl}`, '_blank');
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                Send via SMS
              </button>
              <button
                className="action-btn email-btn"
                onClick={() => {
                  const subject = encodeURIComponent('Your Calculator Results');
                  const body = encodeURIComponent(`Hi,\n\nPlease review your calculator results here:\n${shareLink.fullUrl}\n\nBest regards`);
                  window.open(`mailto:?subject=${subject}&body=${body}`, '_blank');
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                  <polyline points="22,6 12,13 2,6" />
                </svg>
                Send via Email
              </button>
            </div>

            {/* Generate New Link */}
            <button
              className="new-link-btn"
              onClick={() => setShareLink(null)}
            >
              Generate New Link
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ShareCalculatorModal;
