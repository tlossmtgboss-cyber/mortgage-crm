import React, { useState, useRef } from 'react';

const TYPE_COLORS = {
  summary: '#3b82f6',
  scribe_recap: '#3b82f6',
  action_item: '#f59e0b',
  task: '#f59e0b',
  document_request: '#B8924A',
  risk_flag: '#ef4444',
  uw_note: '#ef4444',
  intake_field: '#2D7A52',
  scheduled_appointment: '#06b6d4',
  follow_up_call: '#06b6d4',
  calendar_action: '#06b6d4',
  follow_up_draft: '#ec4899',
  pricing_scenario: '#f59e0b',
  calculator_result: '#2D7A52',
  borrower_story_note: '#f59e0b',
  content_idea: '#ec4899',
};

const TYPE_ICONS = {
  summary: '\u{1F4CB}',
  scribe_recap: '\u{1F4CB}',
  action_item: '\u2705',
  task: '\u2705',
  document_request: '\u{1F4C4}',
  risk_flag: '\u26A0\uFE0F',
  uw_note: '\u{1F50D}',
  intake_field: '\u{1F4DD}',
  scheduled_appointment: '\u{1F4C5}',
  follow_up_call: '\u{1F4DE}',
  calendar_action: '\u{1F4C5}',
  follow_up_draft: '\u2709\uFE0F',
  pricing_scenario: '\u{1F4B0}',
  calculator_result: '\u{1F9EE}',
  borrower_story_note: '\u{1F4E3}',
  content_idea: '\u{1F4A1}',
};

const STATUS_STYLES = {
  pending: { bg: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b', text: 'Pending' },
  approved: { bg: 'rgba(16, 185, 129, 0.15)', color: '#2D7A52', text: 'Approved' },
  auto_approved: { bg: 'rgba(16, 185, 129, 0.15)', color: '#2D7A52', text: 'Auto' },
  rejected: { bg: 'rgba(239, 68, 68, 0.15)', color: '#ef4444', text: 'Rejected' },
  executed: { bg: 'rgba(59, 130, 246, 0.15)', color: '#3b82f6', text: 'Done' },
};

const PRIORITY_DOTS = {
  high: '#ef4444',
  medium: '#f59e0b',
  low: '#6b7280',
};

const ArtifactActionCard = ({
  artifact,
  onApprove,
  onReject,
  onExpand,
  compact = false,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [swipeOffset, setSwipeOffset] = useState(0);
  const [swipeAction, setSwipeAction] = useState(null); // 'approve' | 'reject' | null
  const touchStartX = useRef(0);
  const isDragging = useRef(false);

  const {
    id,
    artifact_type: type = 'action_item',
    title = 'Untitled',
    content,
    confidence,
    approval_status: status = 'pending',
    execution_status: execStatus,
    priority = 'medium',
  } = artifact || {};

  const color = TYPE_COLORS[type] || '#6b7280';
  const icon = TYPE_ICONS[type] || '\u{1F4CC}';
  const statusStyle = STATUS_STYLES[execStatus === 'executed' ? 'executed' : status] || STATUS_STYLES.pending;
  const priorityColor = PRIORITY_DOTS[priority] || PRIORITY_DOTS.medium;

  // Parse content for display
  const contentText = typeof content === 'object'
    ? (content?.text || content?.details || content?.summary || content?.description || JSON.stringify(content))
    : (content || '');

  // Touch handlers for swipe gestures
  const handleTouchStart = (e) => {
    touchStartX.current = e.touches[0].clientX;
    isDragging.current = true;
    setSwipeAction(null);
  };

  const handleTouchMove = (e) => {
    if (!isDragging.current || status !== 'pending') return;
    const diff = e.touches[0].clientX - touchStartX.current;
    setSwipeOffset(Math.max(-100, Math.min(100, diff)));

    if (diff > 60) setSwipeAction('approve');
    else if (diff < -60) setSwipeAction('reject');
    else setSwipeAction(null);
  };

  const handleTouchEnd = () => {
    isDragging.current = false;
    if (swipeAction === 'approve' && onApprove) {
      onApprove(id);
    } else if (swipeAction === 'reject' && onReject) {
      onReject(id);
    }
    setSwipeOffset(0);
    setSwipeAction(null);
  };

  const handleTap = () => {
    if (Math.abs(swipeOffset) < 5) {
      setIsExpanded(!isExpanded);
      onExpand?.(id);
    }
  };

  // Swipe background indicators
  const swipeBgColor = swipeAction === 'approve'
    ? 'rgba(16, 185, 129, 0.2)'
    : swipeAction === 'reject'
    ? 'rgba(239, 68, 68, 0.2)'
    : 'transparent';

  return (
    <div
      style={{
        position: 'relative',
        background: swipeBgColor,
        borderRadius: '12px',
        overflow: 'hidden',
        marginBottom: '8px',
        transition: isDragging.current ? 'none' : 'background 0.2s ease',
      }}
    >
      {/* Swipe action labels */}
      {status === 'pending' && swipeOffset !== 0 && (
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: swipeOffset > 0 ? 'flex-start' : 'flex-end',
          padding: '0 20px',
          color: swipeAction === 'approve' ? '#2D7A52' : swipeAction === 'reject' ? '#ef4444' : 'transparent',
          fontWeight: '600',
          fontSize: '14px',
        }}>
          {swipeOffset > 0 ? '\u2713 Approve' : '\u2715 Reject'}
        </div>
      )}

      {/* Card content */}
      <div
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onClick={handleTap}
        style={{
          position: 'relative',
          background: '#1a2332',
          borderLeft: `3px solid ${color}`,
          borderRadius: '12px',
          padding: compact ? '10px 12px' : '12px 14px',
          transform: `translateX(${swipeOffset}px)`,
          transition: isDragging.current ? 'none' : 'transform 0.3s ease',
          cursor: 'pointer',
        }}
        role="article"
        aria-label={`${type.replace(/_/g, ' ')} artifact: ${title}`}
        aria-expanded={isExpanded}
      >
        {/* Top row: icon, title, status badge */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
        }}>
          <span
            style={{ fontSize: compact ? '14px' : '16px', flexShrink: 0 }}
            role="img"
            aria-hidden="true"
          >
            {icon}
          </span>
          <span style={{
            flex: 1,
            fontSize: compact ? '13px' : '14px',
            fontWeight: '500',
            color: '#fff',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: isExpanded ? 'normal' : 'nowrap',
          }}>
            {title}
          </span>

          {/* Priority dot */}
          <span
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: priorityColor,
              flexShrink: 0,
            }}
            aria-label={`${priority} priority`}
            role="img"
          />

          {/* Status badge */}
          <span style={{
            padding: '2px 6px',
            borderRadius: '8px',
            fontSize: '10px',
            fontWeight: '600',
            background: statusStyle.bg,
            color: statusStyle.color,
            flexShrink: 0,
          }}>
            {statusStyle.text}
          </span>
        </div>

        {/* Confidence bar (if available) */}
        {confidence != null && !compact && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            marginTop: '6px',
          }}>
            <div
              style={{
                flex: 1,
                height: '3px',
                borderRadius: '2px',
                background: 'rgba(255, 255, 255, 0.1)',
                overflow: 'hidden',
              }}
              role="progressbar"
              aria-valuenow={Math.round(confidence * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`Confidence: ${Math.round(confidence * 100)}%`}
            >
              <div style={{
                width: `${Math.round(confidence * 100)}%`,
                height: '100%',
                borderRadius: '2px',
                background: color,
                transition: 'width 0.3s ease',
              }} />
            </div>
            <span style={{
              fontSize: '10px',
              color: 'rgba(255, 255, 255, 0.4)',
            }}>
              {Math.round(confidence * 100)}%
            </span>
          </div>
        )}

        {/* Expanded content */}
        {isExpanded && contentText && (
          <div style={{
            marginTop: '10px',
            padding: '10px',
            background: 'rgba(255, 255, 255, 0.05)',
            borderRadius: '8px',
            fontSize: '13px',
            lineHeight: '1.5',
            color: 'rgba(255, 255, 255, 0.7)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}>
            {contentText}
          </div>
        )}

        {/* Action buttons (when expanded and pending) */}
        {isExpanded && status === 'pending' && (
          <div style={{
            display: 'flex',
            gap: '8px',
            marginTop: '10px',
          }}>
            <button
              onClick={(e) => { e.stopPropagation(); onApprove?.(id); }}
              aria-label={`Approve ${title}`}
              style={{
                flex: 1,
                padding: '8px',
                borderRadius: '8px',
                border: 'none',
                background: 'rgba(16, 185, 129, 0.2)',
                color: '#2D7A52',
                fontWeight: '600',
                fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              {'\u2713'} Approve
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onReject?.(id); }}
              aria-label={`Reject ${title}`}
              style={{
                flex: 1,
                padding: '8px',
                borderRadius: '8px',
                border: 'none',
                background: 'rgba(239, 68, 68, 0.2)',
                color: '#ef4444',
                fontWeight: '600',
                fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              {'\u2715'} Reject
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ArtifactActionCard;
