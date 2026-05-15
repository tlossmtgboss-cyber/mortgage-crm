import React, { useRef, useEffect, useMemo } from 'react';
import { formatDuration } from '../../hooks/useCallIntelligenceSession';

const QUADRANTS = [
  {
    key: 'borrower',
    label: 'Borrower',
    icon: '\u{1F464}',
    ariaLabel: 'Borrower identity',
    color: '#60A5FA',
    agents: ['identity', 'employment'],
  },
  {
    key: 'property',
    label: 'Property & Loan',
    icon: '\u{1F3E0}',
    ariaLabel: 'Property and loan details',
    color: '#34D399',
    agents: ['property', 'intent'],
  },
  {
    key: 'financial',
    label: 'Financial',
    icon: '\u{1F4B0}',
    ariaLabel: 'Financial information',
    color: '#FBBF24',
    agents: ['financial'],
  },
  {
    key: 'compliance',
    label: 'Compliance',
    icon: '⚖️',
    ariaLabel: 'Compliance monitoring',
    color: '#F87171',
    agents: ['compliance', 'transcription'],
  },
];

const CILiveSidebar = ({
  isActive,
  isStarting,
  duration = 0,
  agentStatuses = {},
  agentEvents = [],
  sessionState,
  wsConnected = false,
  onClose,
}) => {
  const feedRef = useRef(null);
  const closeRef = useRef(null);

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [agentEvents.length]);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const quadrantData = useMemo(() => {
    return QUADRANTS.map(q => {
      const events = agentEvents.filter(e => q.agents.includes(e.agent));
      const extractions = events.filter(e => e.value);
      const hasActive = q.agents.some(a => agentStatuses[a]?.status === 'active');
      const allComplete = q.agents.length > 0 &&
        q.agents.every(a => agentStatuses[a]?.status === 'complete');
      return { ...q, events, extractions, hasActive, allComplete };
    });
  }, [agentEvents, agentStatuses]);

  const isCompleted = sessionState === 'completed';
  const firstTimestamp = agentEvents[0]?.timestamp || 0;

  return (
    <>
      <style>{`
        .ci-sidebar {
          position: fixed;
          top: 0; right: 0; bottom: 0;
          width: 100%; max-width: 420px;
          z-index: 1050;
          background: #060A10;
          box-shadow: -4px 0 24px rgba(0,0,0,0.5);
          display: flex;
          flex-direction: column;
          animation: ci-sb-slide 0.3s ease;
          font-family: 'DM Sans', -apple-system, sans-serif;
          padding-top: env(safe-area-inset-top, 0px);
        }
        @keyframes ci-sb-slide {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        @media (prefers-reduced-motion: reduce) {
          .ci-sidebar { animation: none; }
          .ci-sb-rec { animation: none !important; }
          .ci-quad__status--active { animation: none !important; }
          .ci-quad__pulse-dot { animation: none !important; }
          .ci-quad__item { animation: none !important; }
          .ci-sb-evt { animation: none !important; }
        }

        .ci-sb-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 14px 16px;
          border-bottom: 1px solid rgba(255,255,255,0.06);
          flex-shrink: 0;
        }
        .ci-sb-rec {
          width: 10px; height: 10px;
          border-radius: 50%;
          background: #ef4444;
          animation: ci-sb-blink 1s ease-in-out infinite;
          flex-shrink: 0;
        }
        .ci-sb-rec--starting {
          background: #f59e0b;
          animation-duration: 0.5s;
        }
        .ci-sb-rec--done {
          background: #2D7A52;
          animation: none;
        }
        @keyframes ci-sb-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        .ci-sb-title {
          font-size: 14px;
          font-weight: 600;
          color: #e2e8f0;
          flex: 1;
        }
        .ci-sb-ws-badge {
          font-size: 10px;
          padding: 2px 6px;
          border-radius: 4px;
          font-weight: 500;
          flex-shrink: 0;
        }
        .ci-sb-ws-badge--ok {
          background: rgba(16,185,129,0.15);
          color: #34d399;
        }
        .ci-sb-ws-badge--err {
          background: rgba(239,68,68,0.15);
          color: #fca5a5;
        }
        .ci-sb-timer {
          font-family: 'SF Mono', 'Fira Code', monospace;
          font-size: 13px;
          font-weight: 600;
          color: #f87171;
        }
        .ci-sb-timer--done { color: #2D7A52; }
        .ci-sb-close {
          background: none;
          border: 1px solid rgba(255,255,255,0.1);
          color: #cbd5e1;
          width: 44px; height: 44px;
          border-radius: 8px;
          cursor: pointer;
          font-size: 16px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.15s;
          flex-shrink: 0;
        }
        .ci-sb-close:hover {
          background: rgba(255,255,255,0.06);
          color: #f1f5f9;
        }
        .ci-sb-close:focus-visible {
          outline: 2px solid #60a5fa;
          outline-offset: 2px;
        }

        .ci-sb-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 1px;
          background: rgba(255,255,255,0.04);
          flex-shrink: 0;
        }
        .ci-quad {
          background: #0a0f1a;
          padding: 12px;
          min-height: 140px;
          display: flex;
          flex-direction: column;
          position: relative;
          overflow: hidden;
        }
        .ci-quad__head {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-bottom: 8px;
        }
        .ci-quad__icon {
          font-size: 14px;
        }
        .ci-quad__label {
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          flex: 1;
        }
        .ci-quad__status {
          width: 6px; height: 6px;
          border-radius: 50%;
          flex-shrink: 0;
        }
        .ci-quad__status--active {
          background: #22c55e;
          animation: ci-sb-blink 1s ease-in-out infinite;
        }
        .ci-quad__status--complete {
          background: #2D7A52;
        }
        .ci-quad__status--idle {
          background: #475569;
        }
        .ci-quad__items {
          flex: 1;
          overflow-y: auto;
          -webkit-overflow-scrolling: touch;
          scrollbar-width: none;
        }
        .ci-quad__items::-webkit-scrollbar { display: none; }
        .ci-quad__item {
          display: flex;
          align-items: baseline;
          gap: 6px;
          padding: 3px 0;
          animation: ci-quad-fade 0.3s ease;
        }
        @keyframes ci-quad-fade {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .ci-quad__field {
          font-size: 10px;
          color: #94a3b8;
          text-transform: uppercase;
          letter-spacing: 0.3px;
          flex-shrink: 0;
          max-width: 60px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .ci-quad__val {
          font-size: 12px;
          color: #e2e8f0;
          font-weight: 500;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .ci-quad__empty {
          font-size: 11px;
          color: #7c8ba0;
          font-style: italic;
          margin-top: 4px;
        }
        .ci-quad__pulse {
          position: absolute;
          bottom: 8px; right: 8px;
          font-size: 9px;
          color: #94a3b8;
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .ci-quad__pulse-dot {
          width: 4px; height: 4px;
          border-radius: 50%;
          background: currentColor;
          animation: ci-sb-blink 1.5s ease-in-out infinite;
        }

        .ci-sb-feed {
          flex: 1;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          border-top: 1px solid rgba(255,255,255,0.04);
        }
        .ci-sb-feed__head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 10px 16px;
          flex-shrink: 0;
        }
        .ci-sb-feed__title {
          font-size: 11px;
          font-weight: 600;
          color: #94a3b8;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .ci-sb-feed__count {
          font-size: 11px;
          color: #7c8ba0;
        }
        .ci-sb-feed__scroll {
          flex: 1;
          overflow-y: auto;
          -webkit-overflow-scrolling: touch;
          padding: 0 16px calc(16px + env(safe-area-inset-bottom, 0px));
          scrollbar-width: thin;
          scrollbar-color: #1e293b transparent;
        }
        .ci-sb-evt {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          padding: 6px 0;
          border-bottom: 1px solid rgba(255,255,255,0.02);
          animation: ci-quad-fade 0.3s ease;
        }
        .ci-sb-evt__icon {
          font-size: 12px;
          flex-shrink: 0;
          margin-top: 1px;
        }
        .ci-sb-evt__body {
          flex: 1;
          min-width: 0;
        }
        .ci-sb-evt__msg {
          font-size: 12px;
          color: #cbd5e1;
          line-height: 1.4;
        }
        .ci-sb-evt__msg strong {
          color: #e2e8f0;
        }
        .ci-sb-evt__val {
          font-size: 11px;
          color: #2D7A52;
          margin-top: 1px;
          font-weight: 500;
        }
        .ci-sb-evt__time {
          font-size: 10px;
          color: #7c8ba0;
          flex-shrink: 0;
          font-family: 'SF Mono', monospace;
        }
        .ci-sb-evt--complete .ci-sb-evt__msg { color: #2D7A52; }
        .ci-sb-evt--error .ci-sb-evt__msg { color: #f87171; }

        .ci-sb-empty {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 40px 20px;
          text-align: center;
          flex: 1;
        }
        .ci-sb-empty__icon {
          font-size: 32px;
          margin-bottom: 12px;
          opacity: 0.4;
        }
        .ci-sb-empty__text {
          font-size: 13px;
          color: #94a3b8;
          line-height: 1.5;
        }
      `}</style>

      <div className="ci-sidebar" role="complementary" aria-label="Call Intelligence dashboard">
        <div className="ci-sb-header">
          <div
            className={`ci-sb-rec ${isStarting ? 'ci-sb-rec--starting' : ''} ${isCompleted ? 'ci-sb-rec--done' : ''}`}
            role="img"
            aria-label={isStarting ? 'Starting' : isCompleted ? 'Complete' : 'Recording'}
          />
          <h2 className="ci-sb-title">
            {isStarting ? 'Starting...' : isCompleted ? 'Session Complete' : 'Call Intelligence'}
          </h2>
          {isActive && (
            <span className={`ci-sb-ws-badge ${wsConnected ? 'ci-sb-ws-badge--ok' : 'ci-sb-ws-badge--err'}`}>
              {wsConnected ? 'LIVE' : 'RECONNECTING'}
            </span>
          )}
          <span className={`ci-sb-timer ${isCompleted ? 'ci-sb-timer--done' : ''}`}>
            {isStarting ? '...' : formatDuration(duration)}
          </span>
          <button className="ci-sb-close" ref={closeRef} onClick={onClose} aria-label="Close Call Intelligence panel">
            ✕
          </button>
        </div>

        {!isActive && !isStarting && !isCompleted ? (
          <div className="ci-sb-empty">
            <div className="ci-sb-empty__icon" role="img" aria-hidden="true">{'\u{1F9E0}'}</div>
            <div className="ci-sb-empty__text">
              Press the CI button to start recording.<br />
              AI agents will analyze the call in real-time.
            </div>
          </div>
        ) : (
          <>
            <div className="ci-sb-grid" role="group" aria-label="Agent extraction quadrants">
              {quadrantData.map(q => (
                <div className="ci-quad" key={q.key} role="group" aria-label={q.ariaLabel}>
                  <div className="ci-quad__head">
                    <span className="ci-quad__icon" role="img" aria-hidden="true">{q.icon}</span>
                    <span className="ci-quad__label" style={{ color: q.color }}>{q.label}</span>
                    <span
                      className={`ci-quad__status ci-quad__status--${q.hasActive ? 'active' : q.allComplete ? 'complete' : 'idle'}`}
                      role="img"
                      aria-label={q.hasActive ? 'Active' : q.allComplete ? 'Complete' : 'Idle'}
                    />
                  </div>
                  <div className="ci-quad__items">
                    {q.extractions.length > 0 ? (
                      q.extractions.slice(-6).map(ext => (
                        <div className="ci-quad__item" key={ext.id}>
                          <span className="ci-quad__field">{ext.message?.split(' ')[0] || '—'}</span>
                          <span className="ci-quad__val">{ext.value}</span>
                        </div>
                      ))
                    ) : (
                      <div className="ci-quad__empty">
                        {q.hasActive ? 'Analyzing...' : 'Waiting for data...'}
                      </div>
                    )}
                  </div>
                  {q.hasActive && (
                    <div className="ci-quad__pulse" aria-hidden="true">
                      <span className="ci-quad__pulse-dot" />
                      listening
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="ci-sb-feed">
              <div className="ci-sb-feed__head">
                <h3 className="ci-sb-feed__title">Live Activity</h3>
                <span className="ci-sb-feed__count">{agentEvents.length} events</span>
              </div>
              <div className="ci-sb-feed__scroll" ref={feedRef} aria-live="polite" aria-atomic="false">
                {agentEvents.length === 0 ? (
                  <div style={{ padding: '16px 0', textAlign: 'center', color: '#94a3b8', fontSize: '12px' }}>
                    Waiting for AI agents to detect data...
                  </div>
                ) : (
                  agentEvents.slice(-50).map(evt => (
                    <div
                      key={evt.id}
                      className={`ci-sb-evt ${evt.type === 'agent_complete' ? 'ci-sb-evt--complete' : ''} ${evt.type === 'agent_error' ? 'ci-sb-evt--error' : ''}`}
                    >
                      <span className="ci-sb-evt__icon" role="img" aria-hidden="true">{evt.icon}</span>
                      <div className="ci-sb-evt__body">
                        <div className="ci-sb-evt__msg">
                          <strong>{evt.label}</strong>: {evt.message || 'analyzing...'}
                        </div>
                        {evt.value && (
                          <div className="ci-sb-evt__val">{'→'} {evt.value}</div>
                        )}
                      </div>
                      <span className="ci-sb-evt__time">
                        {formatDuration(Math.max(0, Math.floor((evt.timestamp - firstTimestamp) / 1000)))}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
};

export default CILiveSidebar;
