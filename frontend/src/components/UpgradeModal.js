import React from 'react';
import { useModules } from '../contexts/ModuleContext';
import './UpgradeModal.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

/**
 * Modal that appears when user clicks on a locked feature
 * Shows module details, pricing, and upgrade options
 */
function UpgradeModal({ isOpen, onClose, module }) {
  const { refreshModules } = useModules();

  if (!isOpen || !module) return null;

  const handleStartTrial = async () => {
    try {
      const token = getToken();
      const response = await fetch(
        `${process.env.REACT_APP_API_URL || 'https://api.perenniaai.com'}/api/v1/modules/enable`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            module_key: module.module_key,
            is_trial: true,
            trial_days: 14
          })
        }
      );

      if (response.ok) {
        await refreshModules();
        onClose();
        // Show success message
        toast.success(`14-day free trial started for ${module.module_name}!`);
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to start trial');
      }
    } catch (error) {
      console.error('Error starting trial:', error);
      toast.error('Failed to start trial. Please try again.');
    }
  };

  const handleUpgrade = () => {
    // Navigate to billing/upgrade page or open Stripe checkout
    window.location.href = '/settings/billing?upgrade=' + module.module_key;
  };

  // Module icons mapping
  const moduleIcons = {
    ai_assistant: '🤖',
    partner_portals: '👥',
    video_os: '🎬',
    conversation_intelligence: '📞',
    advanced_analytics: '📊',
    integrations: '🔌',
  };

  return (
    <div className="upgrade-modal-overlay" onClick={onClose}>
      <div className="upgrade-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>×</button>

        <div className="modal-icon">
          {moduleIcons[module.module_key] || '✨'}
        </div>

        <h2 className="modal-title">Unlock {module.module_name}</h2>

        <p className="modal-description">
          {module.description || `Get access to ${module.module_name} and all its powerful features.`}
        </p>

        {module.included_features && module.included_features.length > 0 && (
          <div className="features-list">
            <h4>Included Features:</h4>
            <ul>
              {module.included_features.map((feature, idx) => (
                <li key={idx}>
                  <span className="feature-check">✓</span>
                  {feature.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="pricing-section">
          <div className="price-display">
            <span className="price-amount">${module.monthly_price || 99}</span>
            <span className="price-period">/month</span>
          </div>
          {module.annual_price && (
            <p className="annual-price">
              or ${module.annual_price}/year (save 2 months!)
            </p>
          )}
        </div>

        <div className="modal-actions">
          <button className="trial-btn" onClick={handleStartTrial}>
            Start 14-Day Free Trial
          </button>
          <button className="upgrade-btn" onClick={handleUpgrade}>
            Upgrade Now
          </button>
        </div>

        <p className="modal-footer">
          No credit card required for trial. Cancel anytime.
        </p>
      </div>
    </div>
  );
}

export default UpgradeModal;
