import React, { useState, useEffect, useCallback, useMemo } from 'react';

const API_BASE = process.env.REACT_APP_API_URL || '';

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------

async function apiFetch(path, options = {}) {
  const token = localStorage.getItem('token');
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Star rating display
// ---------------------------------------------------------------------------

function StarRating({ value, maxStars = 5, size = 18 }) {
  if (value == null) return <span style={{ color: '#94a3b8', fontSize: 13 }}>No data</span>;

  const fullStars = Math.floor(value);
  const hasHalf = value - fullStars >= 0.25 && value - fullStars < 0.75;
  const emptyStars = maxStars - fullStars - (hasHalf ? 1 : 0);

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 1 }} aria-label={`${value.toFixed(1)} out of ${maxStars} stars`}>
      {Array.from({ length: fullStars }, (_, i) => (
        <svg key={`full-${i}`} width={size} height={size} viewBox="0 0 20 20" fill="#f59e0b">
          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
        </svg>
      ))}
      {hasHalf && (
        <svg width={size} height={size} viewBox="0 0 20 20">
          <defs>
            <linearGradient id="half-star-grad">
              <stop offset="50%" stopColor="#f59e0b" />
              <stop offset="50%" stopColor="#e5e7eb" />
            </linearGradient>
          </defs>
          <path fill="url(#half-star-grad)" d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
        </svg>
      )}
      {Array.from({ length: emptyStars }, (_, i) => (
        <svg key={`empty-${i}`} width={size} height={size} viewBox="0 0 20 20" fill="#e5e7eb">
          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
        </svg>
      ))}
      <span style={{ marginLeft: 6, fontSize: 14, fontWeight: 600, color: '#374151' }}>
        {value.toFixed(1)}
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// NPS Score Card
// ---------------------------------------------------------------------------

function NPSCard({ npsData }) {
  if (!npsData || npsData.nps == null) {
    return (
      <div style={cardStyle}>
        <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8 }}>Net Promoter Score</div>
        <div style={{ fontSize: 28, fontWeight: 700, color: '#94a3b8' }}>--</div>
        <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>No data yet</div>
      </div>
    );
  }

  const nps = npsData.nps;
  const npsColor = nps >= 50 ? '#10b981' : nps >= 0 ? '#f59e0b' : '#ef4444';
  const npsLabel = nps >= 50 ? 'Excellent' : nps >= 0 ? 'Good' : 'Needs Improvement';

  return (
    <div style={cardStyle}>
      <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8 }}>Net Promoter Score</div>
      <div style={{ fontSize: 36, fontWeight: 700, color: npsColor }}>{nps}</div>
      <div style={{ fontSize: 12, color: npsColor, fontWeight: 500, marginTop: 2 }}>{npsLabel}</div>
      <div style={{ display: 'flex', gap: 12, marginTop: 12, fontSize: 12, color: '#6b7280' }}>
        <span>Promoters: {npsData.promoters}</span>
        <span>Passives: {npsData.passives}</span>
        <span>Detractors: {npsData.detractors}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rating row
// ---------------------------------------------------------------------------

function RatingRow({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid #f3f4f6' }}>
      <span style={{ fontSize: 14, color: '#374151' }}>{label}</span>
      <StarRating value={value} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Feedback item
// ---------------------------------------------------------------------------

function FeedbackItem({ feedback }) {
  const ratingColor = feedback.overall_rating >= 4 ? '#10b981' : feedback.overall_rating >= 3 ? '#f59e0b' : '#ef4444';
  const completedDate = feedback.completed_at ? new Date(feedback.completed_at).toLocaleDateString() : '';

  return (
    <div style={{ padding: '14px 0', borderBottom: '1px solid #f3f4f6' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 32, height: 32, borderRadius: '50%', background: '#e0e7ff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 14, fontWeight: 600, color: '#4338ca',
          }}>
            {(feedback.borrower_name || '?')[0].toUpperCase()}
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 500, color: '#1e293b' }}>
              {feedback.borrower_name || 'Anonymous'}
            </div>
            <div style={{ fontSize: 12, color: '#94a3b8' }}>{completedDate}</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            display: 'inline-block', width: 24, height: 24, borderRadius: '50%',
            background: ratingColor, color: '#fff', fontSize: 12, fontWeight: 600,
            textAlign: 'center', lineHeight: '24px',
          }}>
            {feedback.overall_rating}
          </span>
          {feedback.would_recommend != null && (
            <span style={{
              padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 500,
              background: feedback.would_recommend ? '#dcfce7' : '#fef2f2',
              color: feedback.would_recommend ? '#166534' : '#dc2626',
            }}>
              {feedback.would_recommend ? 'Would recommend' : 'Would not recommend'}
            </span>
          )}
        </div>
      </div>
      <p style={{ margin: 0, fontSize: 14, color: '#475569', lineHeight: 1.5 }}>
        {feedback.feedback_text}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Date range selector
// ---------------------------------------------------------------------------

const DATE_RANGES = [
  { label: '30 days', value: 30 },
  { label: '60 days', value: 60 },
  { label: '90 days', value: 90 },
  { label: '6 months', value: 180 },
  { label: '1 year', value: 365 },
];

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function SurveyResults() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [days, setDays] = useState(90);

  const fetchResults = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await apiFetch(`/api/scheduling/surveys/results?days=${days}`);
      setData(result);
    } catch (err) {
      setError(err.message || 'Failed to load survey results');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetchResults();
  }, [fetchResults]);

  const responseRateColor = useMemo(() => {
    if (!data) return '#94a3b8';
    if (data.response_rate >= 50) return '#10b981';
    if (data.response_rate >= 25) return '#f59e0b';
    return '#ef4444';
  }, [data]);

  if (loading && !data) {
    return (
      <div style={{ padding: 24 }}>
        <div style={{ display: 'flex', gap: 16 }}>
          {[1, 2, 3].map(i => (
            <div key={i} style={{ flex: 1, height: 120, background: '#f3f4f6', borderRadius: 12, animation: 'pulse 1.5s ease-in-out infinite' }} />
          ))}
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div style={{ padding: 24, textAlign: 'center', color: '#ef4444' }}>
        <p>{error}</p>
        <button onClick={fetchResults} style={retryButtonStyle}>Retry</button>
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600, color: '#1e293b' }}>Survey Results</h2>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: '#6b7280' }}>
            Post-appointment borrower feedback
          </p>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {DATE_RANGES.map(range => (
            <button
              key={range.value}
              onClick={() => setDays(range.value)}
              style={{
                padding: '6px 12px', borderRadius: 6, border: '1px solid',
                borderColor: days === range.value ? '#3b82f6' : '#e5e7eb',
                background: days === range.value ? '#eff6ff' : '#fff',
                color: days === range.value ? '#2563eb' : '#6b7280',
                fontSize: 13, cursor: 'pointer', fontWeight: days === range.value ? 500 : 400,
              }}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
        {/* Response rate */}
        <div style={cardStyle}>
          <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8 }}>Response Rate</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: responseRateColor }}>
            {data?.response_rate != null ? `${data.response_rate}%` : '--'}
          </div>
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>
            {data?.total_completed || 0} of {data?.total_sent || 0} surveys completed
          </div>
        </div>

        {/* NPS */}
        <NPSCard npsData={data?.nps} />

        {/* Overall rating */}
        <div style={cardStyle}>
          <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8 }}>Overall Rating</div>
          <StarRating value={data?.averages?.overall} size={22} />
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 8 }}>
            Based on {data?.total_completed || 0} responses
          </div>
        </div>
      </div>

      {/* Detailed ratings */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 24, marginBottom: 24 }}>
        {/* Rating breakdown */}
        <div style={{ ...cardStyle, padding: 20 }}>
          <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 600, color: '#1e293b' }}>Rating Breakdown</h3>
          <RatingRow label="Overall Experience" value={data?.averages?.overall} />
          <RatingRow label="Communication" value={data?.averages?.communication} />
          <RatingRow label="Knowledge & Expertise" value={data?.averages?.knowledge} />
        </div>

        {/* LO Leaderboard */}
        <div style={{ ...cardStyle, padding: 20 }}>
          <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 600, color: '#1e293b' }}>Team Scores</h3>
          {(!data?.lo_breakdown || data.lo_breakdown.length === 0) ? (
            <div style={{ fontSize: 13, color: '#94a3b8', padding: 16, textAlign: 'center' }}>
              No team data yet
            </div>
          ) : (
            data.lo_breakdown.map((lo, idx) => (
              <div key={lo.lo_user_id || idx} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '10px 0', borderBottom: idx < data.lo_breakdown.length - 1 ? '1px solid #f3f4f6' : 'none',
              }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 500, color: '#1e293b' }}>{lo.lo_name}</div>
                  <div style={{ fontSize: 12, color: '#94a3b8' }}>
                    {lo.total_responses} response{lo.total_responses !== 1 ? 's' : ''}
                    {lo.nps != null && ` | NPS: ${lo.nps}`}
                  </div>
                </div>
                <StarRating value={lo.avg_overall} size={16} />
              </div>
            ))
          )}
        </div>
      </div>

      {/* Recent feedback */}
      <div style={{ ...cardStyle, padding: 20 }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 600, color: '#1e293b' }}>Recent Feedback</h3>
        {(!data?.recent_feedback || data.recent_feedback.length === 0) ? (
          <div style={{ fontSize: 13, color: '#94a3b8', padding: 24, textAlign: 'center' }}>
            No feedback received yet
          </div>
        ) : (
          data.recent_feedback.map((fb, idx) => (
            <FeedbackItem key={fb.survey_id || idx} feedback={fb} />
          ))
        )}
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: 12, color: '#6b7280', fontSize: 13 }}>
          Refreshing...
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared styles
// ---------------------------------------------------------------------------

const cardStyle = {
  background: '#fff',
  border: '1px solid #e5e7eb',
  borderRadius: 12,
  padding: 16,
};

const retryButtonStyle = {
  padding: '8px 16px',
  borderRadius: 6,
  border: '1px solid #3b82f6',
  background: '#eff6ff',
  color: '#2563eb',
  fontSize: 14,
  cursor: 'pointer',
  marginTop: 8,
};
