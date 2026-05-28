import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

function ChatArea({
  messages,
  userName,
  chatAreaRef,
  scrollAnchorRef,
  messageFeedback,
  onPositiveFeedback,
  onNegativeFeedback,
  onExamplePrompt,
  onOpenReconciliation,
  getGreeting,
  getCurrentDateTime
}) {
  // Deduplicate messages by ID to prevent duplicates
  const seenIds = new Set();
  const uniqueMessages = messages.filter(m => {
    if (!m.isSpecialContent && !seenIds.has(m.id)) {
      seenIds.add(m.id);
      return true;
    }
    return false;
  });

  if (uniqueMessages.length > 0) {
    return (
      <div className="ai-conversation-area" ref={chatAreaRef}>
        <div className="ai-conversation-messages">
          {uniqueMessages.map((msg) => (
            <div key={msg.id} className={`ai-conv-message ${msg.type}`}>
              <div className="ai-conv-avatar">
                {msg.type === 'user' ? '👤' : '🤖'}
              </div>
              <div className="ai-conv-content">
                {msg.isStreaming && !msg.content ? (
                  <div className="ai-typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                ) : (
                  <>
                    {msg.statusText && (
                      <div className="ai-status-text">{msg.statusText}</div>
                    )}
                    <div className="ai-conv-text">
                      {msg.type === 'assistant' && !msg.isStreaming ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{msg.content || ''}</ReactMarkdown>
                      ) : (
                        msg.content?.split('\n').map((line, i) => (
                          <p key={i}>{line || ' '}</p>
                        ))
                      )}
                    </div>
                    {/* Feedback buttons for assistant messages */}
                    {msg.type === 'assistant' && !msg.isStreaming && msg.content && (
                      <div className="ai-feedback-buttons">
                        {messageFeedback[msg.id] === 'submitted' ? (
                          <span className="ai-feedback-thanks">Thanks for the feedback!</span>
                        ) : messageFeedback[msg.id] === 'positive' ? (
                          <span className="ai-feedback-thanks">Thanks!</span>
                        ) : (
                          <>
                            <button
                              className={`ai-feedback-btn ${messageFeedback[msg.id] === 'positive' ? 'active' : ''}`}
                              onClick={() => onPositiveFeedback(msg.id)}
                              title="Good response"
                            >
                              👍
                            </button>
                            <button
                              className={`ai-feedback-btn ${messageFeedback[msg.id] === 'negative' ? 'active' : ''}`}
                              onClick={() => onNegativeFeedback(msg.id)}
                              title="Report issue with this response"
                            >
                              👎
                            </button>
                          </>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}
          <div ref={scrollAnchorRef} />
        </div>
      </div>
    );
  }

  // Welcome state - show when no messages
  return (
    <div className="ai-welcome-state">
      <h2>{getGreeting()}, {userName}!</h2>
      <p className="ai-datetime">{getCurrentDateTime()}</p>
      <p>Ask me anything about your CRM data, clients, or tasks. I'll handle the rest.</p>

      <div className="ai-example-prompts-new">
        <button onClick={() => onExamplePrompt('Daily Briefing - Get my top 3 priorities for today')}>
          <strong>Daily Briefing</strong>
          <span>Get your top 3 priorities for today</span>
        </button>
        <button onClick={() => onExamplePrompt('Pipeline Audit - Identify bottlenecks and stalled deals')}>
          <strong>Pipeline Audit</strong>
          <span>Identify bottlenecks and stalled deals</span>
        </button>
        <button onClick={onOpenReconciliation}>
          <strong>Reconcile Emails</strong>
          <span>Review and process incoming emails</span>
        </button>
        <button onClick={() => onExamplePrompt('Show me my tasks that need to be completed')}>
          <strong>Complete Tasks</strong>
          <span>View and manage your pending tasks</span>
        </button>
        <button onClick={() => onExamplePrompt('What trends do you see across my leads, loans, pipeline, and referral partners? Email me a full trend report.')}>
          <strong>Trend Report</strong>
          <span>Analyze KPI trends and email a report</span>
        </button>
        <button onClick={() => onExamplePrompt('Show me my top 10 leads sorted by AI score that I should call today')}>
          <strong>Top Leads</strong>
          <span>Your highest-priority leads to call</span>
        </button>
        <button onClick={() => onExamplePrompt('Check TRID compliance across my active pipeline and flag any issues')}>
          <strong>Compliance Check</strong>
          <span>TRID, RESPA and disclosure audit</span>
        </button>
        <button onClick={() => onExamplePrompt('Should I lock or float on my loans closing in the next 30 days?')}>
          <strong>Rate Advisory</strong>
          <span>Lock vs float recommendation</span>
        </button>
        <button onClick={() => onExamplePrompt('What documents are missing or expired across my active loans?')}>
          <strong>Missing Docs</strong>
          <span>Track outstanding document requests</span>
        </button>
        <button onClick={() => onExamplePrompt('Show me my referral partner performance and who I should reach out to')}>
          <strong>Referral Partners</strong>
          <span>Partner volume and engagement</span>
        </button>
        <button onClick={() => onExamplePrompt('Give me a profitability breakdown of my funded loans this month')}>
          <strong>Profitability</strong>
          <span>Revenue, margins, and cost per loan</span>
        </button>
        <button onClick={() => onExamplePrompt('Show me my SLA status - any deadlines at risk of breach?')}>
          <strong>SLA Tracker</strong>
          <span>Deadline and service level monitoring</span>
        </button>
      </div>
    </div>
  );
}

export default ChatArea;
