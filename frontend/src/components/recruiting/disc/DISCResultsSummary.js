import React from 'react';
import DISCWheel, { DISCWheelMini } from './DISCWheel';
import { MotivatorsCompact } from './MotivatorsBarchart';
import './DISCResultsSummary.css';

/**
 * DISCResultsSummary Component
 * Card display for DISC results in RecruitDetail sidebar
 */
function DISCResultsSummary({
  discResult,
  motivatorResult,
  assessmentDate,
  onViewFullReport,
  onDownloadPDF,
  compact = false
}) {
  if (!discResult) {
    return (
      <div className="disc-summary disc-summary-empty">
        <div className="disc-summary-header">
          <h3 className="disc-summary-title">DISC + Motivators</h3>
        </div>
        <div className="disc-summary-empty-content">
          <div className="disc-summary-empty-icon">📊</div>
          <p>No assessment completed yet</p>
          <button className="disc-summary-invite-btn" onClick={onViewFullReport}>
            Send Assessment Invite
          </button>
        </div>
      </div>
    );
  }

  const {
    adapted_style,
    natural_style,
    adapted_d,
    adapted_i,
    adapted_s,
    adapted_c,
    wheel_zone,
    wheel_position,
    zone_name,
    quality_tier
  } = discResult;

  const combinedStyle = `${adapted_style}/${natural_style}`;

  return (
    <div className={`disc-summary ${compact ? 'compact' : ''}`}>
      <div className="disc-summary-header">
        <h3 className="disc-summary-title">DISC + Motivators</h3>
        {quality_tier && (
          <span className={`disc-quality-badge ${quality_tier.toLowerCase()}`}>
            {quality_tier}
          </span>
        )}
      </div>

      <div className="disc-summary-content">
        {/* Mini Wheel */}
        <div className="disc-summary-wheel">
          {compact ? (
            <DISCWheelMini zone={wheel_zone} size={60} />
          ) : (
            <DISCWheelMini zone={wheel_zone} size={80} />
          )}
        </div>

        {/* Style Info */}
        <div className="disc-summary-info">
          <div className="disc-summary-style">
            <span className="disc-style-code">{combinedStyle}</span>
            <span className="disc-style-label">Style Pattern</span>
          </div>
          <div className="disc-summary-zone">
            <span className="disc-zone-name">{zone_name}</span>
            <span className="disc-zone-label">Behavioral Zone</span>
          </div>
        </div>

        {/* DISC Bars Mini */}
        <div className="disc-summary-bars">
          <DISCMiniBar label="D" value={adapted_d} color="#DC2626" />
          <DISCMiniBar label="I" value={adapted_i} color="#F59E0B" />
          <DISCMiniBar label="S" value={adapted_s} color="#2D7A52" />
          <DISCMiniBar label="C" value={adapted_c} color="#3B82F6" />
        </div>

        {/* Motivators */}
        {motivatorResult && (
          <div className="disc-summary-motivators">
            <span className="disc-motivators-label">Top Motivators</span>
            <MotivatorsCompact
              topMotivator={motivatorResult.top_motivator}
              secondMotivator={motivatorResult.second_motivator}
            />
          </div>
        )}

        {/* Assessment Date */}
        {assessmentDate && (
          <div className="disc-summary-date">
            Completed: {new Date(assessmentDate).toLocaleDateString()}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="disc-summary-actions">
        <button
          className="disc-summary-btn disc-summary-btn-primary"
          onClick={onViewFullReport}
        >
          View Full Report
        </button>
        {onDownloadPDF && (
          <button
            className="disc-summary-btn disc-summary-btn-secondary"
            onClick={onDownloadPDF}
          >
            Download PDF
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Mini bar for summary display
 */
function DISCMiniBar({ label, value, color }) {
  return (
    <div className="disc-mini-bar">
      <span className="disc-mini-bar-label" style={{ color }}>
        {label}
      </span>
      <div className="disc-mini-bar-track">
        <div
          className="disc-mini-bar-fill"
          style={{ width: `${value}%`, backgroundColor: color }}
        />
      </div>
      <span className="disc-mini-bar-value">{value}</span>
    </div>
  );
}

/**
 * DISC Profile Card - Full width display
 */
export function DISCProfileCard({
  discResult,
  motivatorResult,
  characteristics,
  strengths,
  onViewDetails
}) {
  if (!discResult) return null;

  return (
    <div className="disc-profile-card">
      <div className="disc-profile-header">
        <div className="disc-profile-wheel">
          <DISCWheelMini zone={discResult.wheel_zone} size={100} />
        </div>
        <div className="disc-profile-info">
          <h3 className="disc-profile-style">
            {discResult.adapted_style}/{discResult.natural_style}
          </h3>
          <p className="disc-profile-zone">{discResult.zone_name}</p>
          {motivatorResult && (
            <p className="disc-profile-motivator">
              Primary Motivator: {motivatorResult.top_motivator}
            </p>
          )}
        </div>
      </div>

      {characteristics && (
        <div className="disc-profile-characteristics">
          <h4>Key Characteristics</h4>
          <p>{characteristics.substring(0, 200)}...</p>
        </div>
      )}

      {strengths && strengths.length > 0 && (
        <div className="disc-profile-strengths">
          <h4>Strengths</h4>
          <ul>
            {strengths.slice(0, 3).map((strength, i) => (
              <li key={i}>{strength}</li>
            ))}
          </ul>
        </div>
      )}

      <button className="disc-profile-btn" onClick={onViewDetails}>
        View Complete Profile
      </button>
    </div>
  );
}

/**
 * DISC Badge - Inline status indicator
 */
export function DISCBadge({ style, zone, size = 'medium' }) {
  const ZONE_COLORS = {
    1: '#DC2626', 2: '#EA580C', 3: '#F59E0B', 4: '#FBBF24',
    5: '#84CC16', 6: '#22C55E', 7: '#14B8A6', 8: '#3B82F6'
  };

  return (
    <span
      className={`disc-badge disc-badge-${size}`}
      style={{ backgroundColor: ZONE_COLORS[zone] || '#6B7280' }}
    >
      {style}
    </span>
  );
}

export default DISCResultsSummary;
