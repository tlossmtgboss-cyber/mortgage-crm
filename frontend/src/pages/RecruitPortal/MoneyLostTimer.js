import React, { useState, useEffect, useCallback } from 'react';
import './MoneyLostTimer.css';

const MoneyLostTimer = ({ slug, estimatedAnnualProduction = 5000000 }) => {
  const [elapsedTime, setElapsedTime] = useState(0);
  const [moneyLost, setMoneyLost] = useState(0);
  const [firstVisit, setFirstVisit] = useState(null);

  // Calculate potential earnings per second
  // Assuming 2.5% commission on production, this gives daily/hourly/per-second rate
  const commissionRate = 0.025;
  const annualEarnings = estimatedAnnualProduction * commissionRate;
  const earningsPerSecond = annualEarnings / (365 * 24 * 60 * 60);

  useEffect(() => {
    // Get or set first visit timestamp
    const storageKey = `recruit_first_visit_${slug}`;
    const stored = localStorage.getItem(storageKey);

    if (stored) {
      setFirstVisit(new Date(stored));
    } else {
      const now = new Date();
      localStorage.setItem(storageKey, now.toISOString());
      setFirstVisit(now);
    }
  }, [slug]);

  useEffect(() => {
    if (!firstVisit) return;

    const updateTimer = () => {
      const now = new Date();
      const elapsed = Math.floor((now - firstVisit) / 1000);
      setElapsedTime(elapsed);
      setMoneyLost(elapsed * earningsPerSecond);
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);

    return () => clearInterval(interval);
  }, [firstVisit, earningsPerSecond]);

  const formatTime = useCallback((seconds) => {
    const days = Math.floor(seconds / (24 * 60 * 60));
    const hours = Math.floor((seconds % (24 * 60 * 60)) / (60 * 60));
    const mins = Math.floor((seconds % (60 * 60)) / 60);
    const secs = seconds % 60;

    if (days > 0) {
      return `${days}d ${hours}h ${mins}m ${secs}s`;
    } else if (hours > 0) {
      return `${hours}h ${mins}m ${secs}s`;
    } else if (mins > 0) {
      return `${mins}m ${secs}s`;
    }
    return `${secs}s`;
  }, []);

  const formatMoney = useCallback((amount) => {
    if (amount < 1) {
      return `$${amount.toFixed(2)}`;
    } else if (amount < 1000) {
      return `$${amount.toFixed(2)}`;
    } else if (amount < 10000) {
      return `$${amount.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`;
    } else {
      return `$${(amount / 1000).toFixed(1)}K`;
    }
  }, []);

  if (!firstVisit) return null;

  return (
    <div className="money-lost-timer">
      <div className="timer-header">
        <span className="timer-label">Time Since First Visit</span>
        <span className="timer-value">{formatTime(elapsedTime)}</span>
      </div>
      <div className="timer-money">
        <span className="money-label">Potential Earnings Missed</span>
        <span className="money-value">{formatMoney(moneyLost)}</span>
      </div>
      <div className="timer-message">
        <p>Every second you wait is money left on the table.</p>
        <p className="timer-cta">Let's talk about your future today!</p>
      </div>
    </div>
  );
};

export default MoneyLostTimer;
