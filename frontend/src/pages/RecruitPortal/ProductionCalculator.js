import React, { useState, useEffect, useCallback } from 'react';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const ProductionCalculator = ({ slug, calculatorConfig }) => {
  const [currentVolume, setCurrentVolume] = useState('');
  const [currentUnits, setCurrentUnits] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [animated, setAnimated] = useState(false);

  const calculateImpact = useCallback(async () => {
    if (!currentVolume || !currentUnits) return;

    setLoading(true);
    setAnimated(false);

    try {
      const response = await fetch(`${API_URL}/api/v1/recruit-portal/purl/${slug}/calculator`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          current_volume: parseFloat(currentVolume.replace(/,/g, '')),
          current_units: parseInt(currentUnits, 10),
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setResult(data);
        // Trigger animation after results load
        setTimeout(() => setAnimated(true), 100);
      }
    } catch (err) {
      console.error('Error calculating impact:', err);
    } finally {
      setLoading(false);
    }
  }, [slug, currentVolume, currentUnits]);

  const formatCurrency = (value) => {
    if (!value && value !== 0) return '$0';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  const formatNumber = (value) => {
    if (!value && value !== 0) return '0';
    return new Intl.NumberFormat('en-US').format(Math.round(value));
  };

  const formatPercent = (value) => {
    if (!value && value !== 0) return '0%';
    return `+${value.toFixed(1)}%`;
  };

  const handleVolumeChange = (e) => {
    const value = e.target.value.replace(/[^\d]/g, '');
    const formatted = value ? parseInt(value, 10).toLocaleString() : '';
    setCurrentVolume(formatted);
  };

  return (
    <div className="production-calculator">
      <div className="calculator-header">
        <h3>Production Impact Calculator</h3>
        <p>
          See how much more business you could close with our technology, leads, and support.
          Enter your current production numbers below.
        </p>
      </div>

      <div className="calculator-inputs">
        <div className="input-group">
          <label htmlFor="currentVolume">Current Annual Volume</label>
          <div className="input-wrapper">
            <span className="input-prefix">$</span>
            <input
              type="text"
              id="currentVolume"
              value={currentVolume}
              onChange={handleVolumeChange}
              placeholder="e.g., 25,000,000"
            />
          </div>
          <span className="input-hint">Total loan volume closed in the past 12 months</span>
        </div>

        <div className="input-group">
          <label htmlFor="currentUnits">Current Annual Units</label>
          <input
            type="number"
            id="currentUnits"
            value={currentUnits}
            onChange={(e) => setCurrentUnits(e.target.value)}
            placeholder="e.g., 50"
            min="1"
          />
          <span className="input-hint">Number of loans closed in the past 12 months</span>
        </div>

        <button
          className="calculate-btn"
          onClick={calculateImpact}
          disabled={loading || !currentVolume || !currentUnits}
        >
          {loading ? 'Calculating...' : 'Calculate My Potential'}
        </button>
      </div>

      {result && (
        <div className={`calculator-results ${animated ? 'animated' : ''}`}>
          <h4>Your Projected Growth with Perennia</h4>

          <div className="results-comparison">
            <div className="comparison-column current">
              <h5>Current</h5>
              <div className="stat-item">
                <span className="stat-label">Annual Volume</span>
                <span className="stat-value">{formatCurrency(result.current_volume)}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Annual Units</span>
                <span className="stat-value">{formatNumber(result.current_units)}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Estimated Earnings</span>
                <span className="stat-value">{formatCurrency(result.current_earnings)}</span>
              </div>
            </div>

            <div className="comparison-arrow">
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M5 12H19M19 12L12 5M19 12L12 19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>

            <div className="comparison-column projected">
              <h5>With Perennia</h5>
              <div className="stat-item">
                <span className="stat-label">Projected Volume</span>
                <span className="stat-value highlight">{formatCurrency(result.projected_volume)}</span>
                <span className="stat-change positive">{formatPercent(result.volume_increase_pct)}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Projected Units</span>
                <span className="stat-value highlight">{formatNumber(result.projected_units)}</span>
                <span className="stat-change positive">{formatPercent(result.unit_increase_pct)}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Projected Earnings</span>
                <span className="stat-value highlight">{formatCurrency(result.potential_earnings)}</span>
                <span className="stat-change positive">{formatPercent(result.earnings_increase_pct)}</span>
              </div>
            </div>
          </div>

          <div className="earnings-highlight">
            <div className="highlight-box">
              <span className="highlight-label">Potential Additional Earnings</span>
              <span className="highlight-value">{formatCurrency(result.earnings_increase)}</span>
              <span className="highlight-period">per year</span>
            </div>
          </div>

          <div className="growth-factors">
            <h5>How We Help You Grow</h5>
            <div className="factors-grid">
              <div className="factor-item">
                <span className="factor-icon">📈</span>
                <span className="factor-label">Lead Conversion</span>
                <span className="factor-desc">25% higher conversion rate with our CRM</span>
              </div>
              <div className="factor-item">
                <span className="factor-icon">🎯</span>
                <span className="factor-label">Marketing Leads</span>
                <span className="factor-desc">30% more leads from our marketing</span>
              </div>
              <div className="factor-item">
                <span className="factor-icon">⚡</span>
                <span className="factor-label">Tech Efficiency</span>
                <span className="factor-desc">20% more capacity with our tools</span>
              </div>
              <div className="factor-item">
                <span className="factor-icon">💰</span>
                <span className="factor-label">Deal Size</span>
                <span className="factor-desc">15% larger average loan amount</span>
              </div>
            </div>
          </div>

          <div className="cta-section">
            <p>Ready to take your business to the next level?</p>
            <button
              className="cta-button"
              onClick={() => {
                const scheduleTab = document.querySelector('[data-tab="schedule"]');
                if (scheduleTab) scheduleTab.click();
              }}
            >
              Schedule a Call to Learn More
            </button>
          </div>
        </div>
      )}

      {!result && (
        <div className="calculator-placeholder">
          <div className="placeholder-content">
            <div className="placeholder-icon">📊</div>
            <p>Enter your current production numbers above to see your potential growth with Perennia.</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProductionCalculator;
