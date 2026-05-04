import React, { useState, useRef, useEffect } from 'react';
import { formatDuration, AGENT_CONFIG } from '../../hooks/useCallIntelligenceSession';

const CIStatusStrip = ({
  isActive,
  isStarting,
  duration = 0,
  agentStatuses = {},
  agentEvents = [],
  sessionState,
  onTogglePanel,
  panelOpen = false,
}) => {
  const eventsEndRef = useRef(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (expanded && eventsEndRef.current) {
      eventsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [agentEvents.length, expanded]);

  if (!isActive && !isStarting && sessionState !== 'completed') return null;

  const activeAgents = Object.entries(agentStatuses).filter(
    ([, s]) => s.status === 'active'
  );
  const completedAgents = Object.entries(agentStatuses).filter(
    ([, s]) => s.status === 'complete'
  );
  const latestEvent = agentEvents[agentEvents.length - 1];

  const handleStripClick = () => {
    setExpanded(prev => !prev);
  };

  return (
    <>
      <style>{`
        .ci-strip {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          z-index: 1100;
          background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
          border-bottom: 1px solid rgba(255,255,255,0.08);
          cursor: pointer;
          user-select: none;
          transition: all 0.2s ease;
        }
        .ci-strip:hover { background: linear-gradient(135deg, #1e293b 0%, #334155 100%); }
        .ci-strip__bar {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 8px 16px;
          min-height: 40px;
        }
        .ci-strip__rec-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #ef4444;
          animation: ci-rec-blink 1s ease-in-out infinite;
          flex-shrink: 0;
        }
        @keyframes ci-rec-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        .ci-strip__timer {
          font-family: 'SF Mono', 'Fira Code', monospace;
          font-size: 13px;
          font-weight: 600;
          color: #f87171;
          min-width: 40px;
        }
        .ci-strip__divider {
          width: 1px;
          height: 16px;
          background: rgba(255,255,255,0.15);
          flex-shrink: 0;
        }
        .ci-strip__status {
          font-size: 12px;
          color: #94a3b8;
          flex: 1;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .ci-strip__status em {
          font-style: normal;
          color: #e2e8f0;
        }
        .ci-strip__agents {
          display: flex;
          gap: 4px;
          flex-shrink: 0;
        }
        .ci-strip__agent-pip {
          width: 18px;
          height: 18px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 10px;
          border: 1.5px solid transparent;
          transition: all 0.3s ease;
        }
        .ci-strip__agent-pip--active {
          border-color: currentColor;
          animation: ci-agent-spin 2s linear infinite;
        }
        .ci-strip__agent-pip--complete {
          opacity: 0.6;
        }
        @keyframes ci-agent-spin {
          0% { box-shadow: 0 0 0 0 currentColor; }
          50% { box-shadow: 0 0 4px 1px currentColor; }
          100% { box-shadow: 0 0 0 0 currentColor; }
        }
        .ci-strip__chevron {
          color: #64748b;
          font-size: 10px;
          transition: transform 0.2s ease;
          flex-shrink: 0;
        }
        .ci-strip__chevron--up { transform: rotate(180deg); }

        .ci-panel {
          position: fixed;
          top: 41px;
          right: 0;
          width: 340px;
          max-height: 400px;
          background: #0f172a;
          border: 1px solid rgba(255,255,255,0.08);
          border-top: none;
          border-radius: 0 0 0 12px;
          z-index: 1099;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          animation: ci-panel-slide 0.2s ease;
        }
        @keyframes ci-panel-slide {
          from { opacity: 0; transform: translateY(-8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .ci-panel__header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 10px 14px;
          border-bottom: 1px solid rgba(255,255,255,0.06);
        }
        .ci-panel__title {
          font-size: 11px;
          font-weight: 600;
          color: #64748b;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .ci-panel__count {
          font-size: 11px;
          color: #475569;
        }
        .ci-panel__events {
          flex: 1;
          overflow-y: auto;
          padding: 6px 0;
          scrollbar-width: thin;
          scrollbar-color: #1e293b transparent;
        }
        .ci-event {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          padding: 6px 14px;
          transition: background 0.15s;
        }
        .ci-event:hover { background: rgba(255,255,255,0.03); }
        .ci-event__icon {
          font-size: 13px;
          flex-shrink: 0;
          margin-top: 1px;
        }
        .ci-event__body {
          flex: 1;
          min-width: 0;
        }
        .ci-event__msg {
          font-size: 12px;
          color: #cbd5e1;
          line-height: 1.4;
        }
        .ci-event__value {
          font-size: 11px;
          color: #10b981;
          margin-top: 1px;
        }
        .ci-event__time {
          font-size: 10px;
          color: #475569;
          flex-shrink: 0;
          margin-top: 2px;
        }
        .ci-event--complete .ci-event__msg { color: #10b981; }
        .ci-event--error .ci-event__msg { color: #f87171; }
        .ci-panel__empty {
          padding: 24px 14px;
          text-align: center;
          color: #475569;
          font-size: 12px;
        }
        .ci-panel__empty-icon { font-size: 20px; margin-bottom: 6px; }
        .ci-strip--starting .ci-strip__rec-dot {
          background: #f59e0b;
          animation: ci-rec-blink 0.5s ease-in-out infinite;
        }
        .ci-strip--completed { border-bottom-color: rgba(16,185,129,0.3); }
        .ci-strip--completed .ci-strip__rec-dot { background: #10b981; animation: none; }
        .ci-strip--completed .ci-strip__timer { color: #10b981; }
      `}</style>

      <div
        className={`ci-strip ${isStarting ? 'ci-strip--starting' : ''} ${sessionState === 'completed' ? 'ci-strip--completed' : ''}`}
        onClick={handleStripClick}
        role="status"
        aria-label={isActive ? `Call Intelligence recording: ${formatDuration(duration)}` : 'Call Intelligence'}
      >
        <div className="ci-strip__bar">
          <div className="ci-strip__rec-dot" />
          <span className="ci-strip__timer">
            {isStarting ? '...' : formatDuration(duration)}
          </span>
          <div className="ci-strip__divider" />
          <span className="ci-strip__status">
            {isStarting ? (
              'Starting CI session...'
            ) : sessionState === 'completed' ? (
              <><em>Complete</em> — {agentEvents.length} events captured</>
            ) : latestEvent ? (
              <>{latestEvent.icon} <em>{latestEvent.label}</em>: {latestEvent.message || 'analyzing...'}{latestEvent.value ? ` → ${latestEvent.value}` : ''}</>
            ) : activeAgents.length > 0 ? (
              `${activeAgents.length} agent${activeAgents.length > 1 ? 's' : ''} analyzing...`
            ) : (
              'Listening — waiting for speech...'
            )}
          </span>
          <div className="ci-strip__agents">
            {Object.entries(AGENT_CONFIG).map(([key, cfg]) => {
              const status = agentStatuses[key];
              if (!status) return null;
              return (
                <span
                  key={key}
                  className={`ci-strip__agent-pip ci-strip__agent-pip--${status.status}`}
                  style={{ color: cfg.color }}
                  title={`${cfg.label}: ${status.status}`}
                >
                  {cfg.icon}
                </span>
              );
            })}
          </div>
          <span className={`ci-strip__chevron ${expanded ? 'ci-strip__chevron--up' : ''}`}>
            ▼
          </span>
        </div>
      </div>

      {expanded && (
        <div className="ci-panel">
          <div className="ci-panel__header">
            <span className="ci-panel__title">Agent Activity</span>
            <span className="ci-panel__count">{agentEvents.length} events</span>
          </div>
          <div className="ci-panel__events">
            {agentEvents.length === 0 ? (
              <div className="ci-panel__empty">
                <div className="ci-panel__empty-icon">🔍</div>
                Waiting for AI agents to detect data...
              </div>
            ) : (
              agentEvents.map((evt) => (
                <div
                  key={evt.id}
                  className={`ci-event ${evt.type === 'agent_complete' ? 'ci-event--complete' : ''} ${evt.type === 'agent_error' ? 'ci-event--error' : ''}`}
                >
                  <span className="ci-event__icon">{evt.icon}</span>
                  <div className="ci-event__body">
                    <div className="ci-event__msg">
                      <strong>{evt.label}</strong>: {evt.message || (evt.type === 'agent_complete' ? 'extraction complete' : 'analyzing...')}
                    </div>
                    {evt.value && (
                      <div className="ci-event__value">→ {evt.value}</div>
                    )}
                  </div>
                  <span className="ci-event__time">
                    {formatDuration(Math.floor((evt.timestamp - (activeStartRef?.current || evt.timestamp)) / 1000))}
                  </span>
                </div>
              ))
            )}
            <div ref={eventsEndRef} />
          </div>
        </div>
      )}
    </>
  );
};

// Re-export for the event time display (use session start as reference)
let activeStartRef = { current: null };

export default CIStatusStrip;
