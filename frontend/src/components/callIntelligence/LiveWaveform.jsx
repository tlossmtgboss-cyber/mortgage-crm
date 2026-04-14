// ─────────────────────────────────────────────────────────────
// LIVE WAVEFORM COMPONENT
// src/components/callIntelligence/LiveWaveform.jsx
// ─────────────────────────────────────────────────────────────

import React, { useMemo } from 'react';
import './LiveWaveform.css';

const NUM_BARS = 28;

function WaveBar({ index, isActive, randomValues }) {
  const { maxHeight, duration, delay, opacity } = randomValues;

  if (!isActive) {
    return (
      <div
        className="live-waveform__bar live-waveform__bar--inactive"
      />
    );
  }

  return (
    <div
      className="live-waveform__bar live-waveform__bar--active"
      style={{
        height: `${maxHeight}px`,
        animationDuration: `${duration}ms`,
        animationDelay: `${delay}ms`,
        opacity: opacity,
      }}
    />
  );
}

export default function LiveWaveform({ isActive }) {
  // Pre-compute random values once so they remain stable across renders
  const barConfigs = useMemo(() => {
    return Array.from({ length: NUM_BARS }).map((_, i) => ({
      maxHeight: 8 + Math.random() * 14,
      duration: 600 + Math.random() * 800,
      delay: i * 30 + Math.random() * 100,
      opacity: 0.65 + Math.random() * 0.25,
    }));
  }, []);

  return (
    <div className="live-waveform">
      {barConfigs.map((config, i) => (
        <WaveBar
          key={i}
          index={i}
          isActive={isActive}
          randomValues={config}
        />
      ))}
    </div>
  );
}
