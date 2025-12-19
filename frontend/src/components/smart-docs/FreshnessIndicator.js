import React from 'react';
import './FreshnessIndicator.css';

// Document freshness rules (in days)
const FRESHNESS_RULES = {
  paystub: 30,
  bank_statement: 60,
  tax_return: 365, // Valid for tax year
  w2: 365,
  drivers_license: 365 * 4, // Until expiration
  appraisal: 120,
  title: 90,
  credit_report: 120,
  default: 90,
};

function FreshnessIndicator({ documentDate, documentType, expirationDate }) {
  if (!documentDate && !expirationDate) {
    return null;
  }

  const now = new Date();
  let daysOld = 0;
  let maxAge = FRESHNESS_RULES[documentType] || FRESHNESS_RULES.default;
  let referenceDate = null;

  if (expirationDate) {
    // Use explicit expiration date if provided
    referenceDate = new Date(expirationDate);
    daysOld = Math.floor((now - referenceDate) / (1000 * 60 * 60 * 24));
    if (daysOld < 0) {
      // Document has not expired yet
      const daysUntilExpiry = Math.abs(daysOld);
      if (daysUntilExpiry <= 30) {
        return (
          <div className="freshness-indicator expiring-soon">
            <span className="freshness-icon">⚠️</span>
            <span>Expires in {daysUntilExpiry} days</span>
          </div>
        );
      }
      return (
        <div className="freshness-indicator fresh">
          <span className="freshness-icon">✓</span>
          <span>Valid until {referenceDate.toLocaleDateString()}</span>
        </div>
      );
    } else {
      return (
        <div className="freshness-indicator expired">
          <span className="freshness-icon">✗</span>
          <span>Expired {daysOld} days ago</span>
        </div>
      );
    }
  }

  if (documentDate) {
    referenceDate = new Date(documentDate);
    daysOld = Math.floor((now - referenceDate) / (1000 * 60 * 60 * 24));

    const percentUsed = (daysOld / maxAge) * 100;

    if (daysOld > maxAge) {
      return (
        <div className="freshness-indicator expired">
          <span className="freshness-icon">✗</span>
          <span>Stale ({daysOld} days old)</span>
        </div>
      );
    }

    if (percentUsed >= 80) {
      return (
        <div className="freshness-indicator expiring-soon">
          <span className="freshness-icon">⚠️</span>
          <span>Expiring soon ({maxAge - daysOld} days left)</span>
        </div>
      );
    }

    return (
      <div className="freshness-indicator fresh">
        <span className="freshness-icon">✓</span>
        <span>Fresh ({daysOld} days old)</span>
      </div>
    );
  }

  return null;
}

export default FreshnessIndicator;
