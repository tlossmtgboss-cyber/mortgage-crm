/**
 * DocumentTimeline Component
 *
 * Displays a vertical timeline of document events for a given loan,
 * fetched from the doc analytics API.
 */

import React, { useEffect, useState } from 'react';
import { toast } from '../../utils/toast';
import { getLoanTimeline } from '../../services/docAnalyticsApi';
import './DocumentTimeline.css';

// Map event types to single-letter icons shown in the circular marker
const EVENT_ICONS = {
  uploaded: 'U',
  reviewed: 'R',
  approved: 'A',
  rejected: 'X',
  requested: 'Q',
  expired: 'E',
  renewed: 'N',
  esigned: 'S',
};

// Map event types to CSS modifier classes that control marker color
const EVENT_COLOR_CLASS = {
  uploaded: 'dt-marker--primary',
  reviewed: 'dt-marker--primary',
  approved: 'dt-marker--success',
  rejected: 'dt-marker--error',
  requested: 'dt-marker--warning',
  expired: 'dt-marker--error',
  renewed: 'dt-marker--success',
  esigned: 'dt-marker--primary',
};

function formatTimestamp(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

const DocumentTimeline = ({ loanId }) => {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!loanId) return;

    let cancelled = false;

    async function fetchTimeline() {
      setLoading(true);
      try {
        const data = await getLoanTimeline(loanId);
        if (!cancelled) {
          // API may return { events: [...] } or a plain array
          const list = Array.isArray(data) ? data : (data?.events ?? []);
          setEvents(list);
        }
      } catch (err) {
        if (!cancelled) {
          toast.error('Failed to load document timeline');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchTimeline();
    return () => { cancelled = true; };
  }, [loanId]);

  if (loading) {
    return (
      <div className="dt-loading">
        <span className="dt-loading__spinner" aria-hidden="true" />
        <span>Loading timeline…</span>
      </div>
    );
  }

  if (!events.length) {
    return (
      <div className="dt-empty">
        No events
      </div>
    );
  }

  return (
    <div className="dt-timeline" role="list" aria-label="Document event timeline">
      {events.map((event, index) => {
        const type = (event.event_type || event.type || '').toLowerCase();
        const icon = EVENT_ICONS[type] ?? type.charAt(0).toUpperCase();
        const colorClass = EVENT_COLOR_CLASS[type] ?? 'dt-marker--primary';
        const isLast = index === events.length - 1;

        return (
          <div
            key={event.id ?? index}
            className="dt-event"
            role="listitem"
          >
            {/* Left column: marker + connector line */}
            <div className="dt-event__track">
              <div className={`dt-marker ${colorClass}`} aria-hidden="true">
                {icon}
              </div>
              {!isLast && <div className="dt-connector" aria-hidden="true" />}
            </div>

            {/* Right column: event content */}
            <div className="dt-event__body">
              <div className="dt-event__meta">
                <span className="dt-event__type">
                  {type.toUpperCase()}
                </span>
                {(event.timestamp || event.created_at) && (
                  <span className="dt-event__timestamp">
                    {formatTimestamp(event.timestamp || event.created_at)}
                  </span>
                )}
              </div>

              {(event.doc_type || event.document_type) && (
                <div className="dt-event__doc-type">
                  {event.doc_type || event.document_type}
                </div>
              )}

              {event.description && (
                <div className="dt-event__description">
                  {event.description}
                </div>
              )}

              {(event.user_name || event.user) && (
                <div className="dt-event__user">
                  {event.user_name || event.user}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default DocumentTimeline;
