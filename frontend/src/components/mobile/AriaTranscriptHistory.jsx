/**
 * AriaTranscriptHistory
 *
 * Mobile-optimized component that displays past Aria AI conversation history.
 * Fetches from the existing `/api/v1/conversations` endpoint via conversationsAPI.
 *
 * Features:
 *  - Scrollable list of past conversations with timestamps
 *  - Tap to expand/collapse full transcript
 *  - Date filter (today, 7 days, 30 days, all)
 *  - Text search across messages
 *  - Full-width, touch-friendly tap targets (min 44px)
 *  - Graceful loading/empty/error states
 */

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { conversationsAPI } from '../../services/api';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DATE_FILTERS = [
  { key: 'today', label: 'Today' },
  { key: '7d', label: '7 days' },
  { key: '30d', label: '30 days' },
  { key: 'all', label: 'All' },
];

const PAGE_SIZE = 50;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(dateStr) {
  if (!dateStr) return '';
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  if (isNaN(then)) return '';
  const diffMs = now - then;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: now - then > 365 * 86400000 ? 'numeric' : undefined,
  });
}

function formatFullDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function dateFilterStart(key) {
  const now = new Date();
  switch (key) {
    case 'today': {
      const start = new Date(now);
      start.setHours(0, 0, 0, 0);
      return start;
    }
    case '7d':
      return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    case '30d':
      return new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    default:
      return null;
  }
}

/**
 * Group a flat list of conversation records into logical sessions.
 * Each record has { id, message, response, role, created_at }.
 * We treat each record as a user-message + AI-response pair.
 */
function groupConversations(records) {
  return records.map((rec) => ({
    id: rec.id,
    userMessage: rec.message || '',
    aiResponse: rec.response || '',
    role: rec.role,
    timestamp: rec.created_at,
  }));
}

// ---------------------------------------------------------------------------
// Icons (inline SVG)
// ---------------------------------------------------------------------------

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function ChevronIcon({ expanded }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{
        transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
        transition: 'transform 0.2s ease',
        flexShrink: 0,
      }}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function EmptyIcon() {
  return (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.3 }}>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <line x1="9" y1="9" x2="15" y2="9" />
      <line x1="9" y1="13" x2="13" y2="13" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    background: '#0d0d1a',
    color: '#ffffff',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },

  // Header
  header: {
    padding: '16px 16px 0',
    flexShrink: 0,
  },
  headerTitle: {
    margin: 0,
    fontSize: '20px',
    fontWeight: 700,
    color: '#ffffff',
  },
  headerSubtitle: {
    margin: '2px 0 0',
    fontSize: '13px',
    color: 'rgba(255, 255, 255, 0.45)',
  },

  // Search bar
  searchWrap: {
    margin: '12px 16px 0',
    position: 'relative',
    flexShrink: 0,
  },
  searchIcon: {
    position: 'absolute',
    left: '12px',
    top: '50%',
    transform: 'translateY(-50%)',
    color: 'rgba(255, 255, 255, 0.3)',
    pointerEvents: 'none',
  },
  searchInput: {
    width: '100%',
    padding: '10px 12px 10px 36px',
    fontSize: '14px',
    color: '#ffffff',
    background: 'rgba(255, 255, 255, 0.06)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderRadius: '10px',
    outline: 'none',
    boxSizing: 'border-box',
    WebkitAppearance: 'none',
  },

  // Date filter chips
  filterRow: {
    display: 'flex',
    gap: '6px',
    padding: '10px 16px',
    overflowX: 'auto',
    flexShrink: 0,
    WebkitOverflowScrolling: 'touch',
  },
  filterChip: (active) => ({
    padding: '6px 14px',
    fontSize: '12px',
    fontWeight: active ? 600 : 400,
    color: active ? '#0d0d1a' : 'rgba(255, 255, 255, 0.55)',
    background: active ? '#7c4dff' : 'rgba(255, 255, 255, 0.06)',
    border: 'none',
    borderRadius: '20px',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    flexShrink: 0,
    WebkitTapHighlightColor: 'transparent',
    transition: 'background 0.15s, color 0.15s',
  }),

  // List
  list: {
    flex: 1,
    overflowY: 'auto',
    WebkitOverflowScrolling: 'touch',
    padding: '0 16px 24px',
  },

  // Conversation item
  item: {
    marginBottom: '8px',
    background: 'rgba(255, 255, 255, 0.04)',
    borderRadius: '12px',
    border: '1px solid rgba(255, 255, 255, 0.06)',
    overflow: 'hidden',
  },
  itemHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '14px',
    cursor: 'pointer',
    minHeight: '44px',
    WebkitTapHighlightColor: 'transparent',
  },
  itemIcon: {
    flexShrink: 0,
    width: '32px',
    height: '32px',
    borderRadius: '8px',
    background: 'rgba(124, 77, 255, 0.12)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#7c4dff',
  },
  itemMeta: {
    flex: 1,
    minWidth: 0,
  },
  itemPreview: {
    margin: 0,
    fontSize: '14px',
    fontWeight: 500,
    color: '#ffffff',
    lineHeight: '1.3',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  itemTime: {
    margin: '2px 0 0',
    fontSize: '11px',
    color: 'rgba(255, 255, 255, 0.35)',
  },
  itemChevron: {
    flexShrink: 0,
    color: 'rgba(255, 255, 255, 0.25)',
  },

  // Expanded transcript
  transcript: {
    padding: '0 14px 14px',
    borderTop: '1px solid rgba(255, 255, 255, 0.06)',
  },
  bubble: (isUser) => ({
    margin: '10px 0 0',
    padding: '10px 12px',
    fontSize: '13px',
    lineHeight: '1.5',
    color: isUser ? '#ffffff' : 'rgba(255, 255, 255, 0.8)',
    background: isUser ? 'rgba(124, 77, 255, 0.15)' : 'rgba(255, 255, 255, 0.04)',
    borderRadius: isUser ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  }),
  bubbleLabel: {
    fontSize: '10px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    color: 'rgba(255, 255, 255, 0.3)',
    marginBottom: '4px',
  },
  transcriptDate: {
    margin: '10px 0 0',
    fontSize: '11px',
    color: 'rgba(255, 255, 255, 0.25)',
    textAlign: 'right',
  },

  // States
  stateWrap: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '60px 24px',
    textAlign: 'center',
  },
  stateTitle: {
    margin: '16px 0 0',
    fontSize: '16px',
    fontWeight: 600,
    color: 'rgba(255, 255, 255, 0.5)',
  },
  stateSubtitle: {
    margin: '6px 0 0',
    fontSize: '13px',
    color: 'rgba(255, 255, 255, 0.3)',
    maxWidth: '280px',
  },
  retryBtn: {
    marginTop: '16px',
    padding: '8px 20px',
    fontSize: '13px',
    fontWeight: 600,
    color: '#7c4dff',
    background: 'rgba(124, 77, 255, 0.1)',
    border: '1px solid rgba(124, 77, 255, 0.3)',
    borderRadius: '8px',
    cursor: 'pointer',
    WebkitTapHighlightColor: 'transparent',
  },
  loadingDots: {
    display: 'flex',
    gap: '6px',
    justifyContent: 'center',
    padding: '40px 0',
  },
  dot: (i) => ({
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    background: '#7c4dff',
    opacity: 0.3,
    animation: `athPulse 1.2s ease-in-out ${i * 0.15}s infinite`,
  }),
  countBadge: {
    margin: '4px 0 0',
    fontSize: '12px',
    color: 'rgba(255, 255, 255, 0.3)',
  },
};

// Inject keyframes for loading animation
const KEYFRAMES_ID = 'ath-keyframes';
function ensureKeyframes() {
  if (typeof document === 'undefined') return;
  if (document.getElementById(KEYFRAMES_ID)) return;
  const style = document.createElement('style');
  style.id = KEYFRAMES_ID;
  style.textContent = `
    @keyframes athPulse {
      0%, 80%, 100% { opacity: 0.3; transform: scale(1); }
      40% { opacity: 1; transform: scale(1.2); }
    }
  `;
  document.head.appendChild(style);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ConversationItem({ conv, expanded, onToggle }) {
  const preview = conv.userMessage || conv.aiResponse || '(empty)';

  return (
    <div style={styles.item}>
      <div
        style={styles.itemHeader}
        onClick={onToggle}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle(); } }}
      >
        <div style={styles.itemIcon}>
          <ChatIcon />
        </div>
        <div style={styles.itemMeta}>
          <p style={styles.itemPreview}>{preview}</p>
          <p style={styles.itemTime}>{relativeTime(conv.timestamp)}</p>
        </div>
        <div style={styles.itemChevron}>
          <ChevronIcon expanded={expanded} />
        </div>
      </div>

      {expanded && (
        <div style={styles.transcript}>
          {conv.userMessage && (
            <div style={styles.bubble(true)}>
              <div style={styles.bubbleLabel}>You</div>
              {conv.userMessage}
            </div>
          )}
          {conv.aiResponse && (
            <div style={styles.bubble(false)}>
              <div style={styles.bubbleLabel}>Aria</div>
              {conv.aiResponse}
            </div>
          )}
          <p style={styles.transcriptDate}>{formatFullDate(conv.timestamp)}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function AriaTranscriptHistory() {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dateFilter, setDateFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedIds, setExpandedIds] = useState(new Set());
  const listRef = useRef(null);

  // Inject keyframes on mount
  useEffect(() => { ensureKeyframes(); }, []);

  // ── Fetch conversations ────────────────────────────────────────────────

  const fetchConversations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await conversationsAPI.getAll({ limit: PAGE_SIZE });
      const grouped = groupConversations(data);
      setConversations(grouped);
    } catch (e) {
      console.error('[AriaTranscriptHistory] fetch error:', e);
      setError(e?.response?.data?.detail || e.message || 'Failed to load conversations');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // ── Filtered & searched list ───────────────────────────────────────────

  const filteredConversations = useMemo(() => {
    let list = conversations;

    // Date filter
    const start = dateFilterStart(dateFilter);
    if (start) {
      const startTs = start.getTime();
      list = list.filter((c) => {
        const ts = new Date(c.timestamp).getTime();
        return !isNaN(ts) && ts >= startTs;
      });
    }

    // Text search
    const q = searchQuery.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (c) =>
          (c.userMessage && c.userMessage.toLowerCase().includes(q)) ||
          (c.aiResponse && c.aiResponse.toLowerCase().includes(q))
      );
    }

    return list;
  }, [conversations, dateFilter, searchQuery]);

  // ── Toggle expand ──────────────────────────────────────────────────────

  const toggleExpanded = useCallback((id) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // ── Render states ──────────────────────────────────────────────────────

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h2 style={styles.headerTitle}>Conversation History</h2>
          <p style={styles.headerSubtitle}>Past conversations with Aria</p>
        </div>
        <div style={styles.loadingDots}>
          <span style={styles.dot(0)} />
          <span style={styles.dot(1)} />
          <span style={styles.dot(2)} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h2 style={styles.headerTitle}>Conversation History</h2>
        </div>
        <div style={styles.stateWrap}>
          <p style={styles.stateTitle}>Could not load conversations</p>
          <p style={styles.stateSubtitle}>{error}</p>
          <button style={styles.retryBtn} onClick={fetchConversations} type="button">
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <h2 style={styles.headerTitle}>Conversation History</h2>
        <p style={styles.headerSubtitle}>
          {conversations.length} conversation{conversations.length !== 1 ? 's' : ''} with Aria
        </p>
      </div>

      {/* Search */}
      <div style={styles.searchWrap}>
        <span style={styles.searchIcon}><SearchIcon /></span>
        <input
          type="text"
          style={styles.searchInput}
          placeholder="Search conversations..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck="false"
        />
      </div>

      {/* Date filter chips */}
      <div style={styles.filterRow}>
        {DATE_FILTERS.map((f) => (
          <button
            key={f.key}
            style={styles.filterChip(dateFilter === f.key)}
            onClick={() => setDateFilter(f.key)}
            type="button"
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Count badge */}
      {filteredConversations.length !== conversations.length && (
        <p style={{ ...styles.countBadge, padding: '0 16px' }}>
          Showing {filteredConversations.length} of {conversations.length}
        </p>
      )}

      {/* List */}
      <div style={styles.list} ref={listRef}>
        {filteredConversations.length === 0 ? (
          <div style={styles.stateWrap}>
            <EmptyIcon />
            <p style={styles.stateTitle}>
              {searchQuery || dateFilter !== 'all' ? 'No matches' : 'No conversations yet'}
            </p>
            <p style={styles.stateSubtitle}>
              {searchQuery || dateFilter !== 'all'
                ? 'Try adjusting your search or date filter.'
                : 'Start a conversation with Aria to see your history here.'}
            </p>
          </div>
        ) : (
          filteredConversations.map((conv) => (
            <ConversationItem
              key={conv.id}
              conv={conv}
              expanded={expandedIds.has(conv.id)}
              onToggle={() => toggleExpanded(conv.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
