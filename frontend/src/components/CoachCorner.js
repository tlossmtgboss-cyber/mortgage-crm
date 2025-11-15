import React, { useState, useEffect } from 'react';
import { aiAPI } from '../services/api';
import VoiceInput from './VoiceInput';
import './CoachCorner.css';

const CoachCorner = ({ isOpen, onClose }) => {
  const [mode, setMode] = useState(null);
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [customMessage, setCustomMessage] = useState('');
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [memoryStats, setMemoryStats] = useState(null);
  const [conversationHistory, setConversationHistory] = useState([]);
  const [aiChatMessage, setAiChatMessage] = useState('');
  const [aiChatLoading, setAiChatLoading] = useState(false);
  const [aiChatResponse, setAiChatResponse] = useState(null);

  useEffect(() => {
    if (isOpen) {
      loadMemoryStats();
    }
  }, [isOpen]);

  const loadMemoryStats = async () => {
    try {
      const stats = await aiAPI.getMemoryStats();
      setMemoryStats(stats);
    } catch (error) {
      console.error('Failed to load memory stats:', error);
    }
  };

  if (!isOpen) return null;

  const coachModes = [
    {
      id: 'daily_briefing',
      label: 'Daily Briefing',
      icon: '📋',
      description: 'Get your top 3 priorities for today'
    },
    {
      id: 'pipeline_audit',
      label: 'Pipeline Audit',
      icon: '🔍',
      description: 'Identify bottlenecks and stalled deals'
    },
    {
      id: 'focus_reset',
      label: 'Focus Reset',
      icon: '🎯',
      description: 'Get back on track when scattered'
    },
    {
      id: 'priority_guidance',
      label: 'What Should I Do Next?',
      icon: '❓',
      description: 'Priority decision guidance'
    },
    {
      id: 'accountability',
      label: 'Accountability Review',
      icon: '📊',
      description: 'Review your performance'
    },
    {
      id: 'tough_love',
      label: 'Tough Love Mode',
      icon: '💪',
      description: 'Call out inefficiencies directly'
    },
    {
      id: 'teach_process',
      label: 'Teach Me The Process',
      icon: '📚',
      description: 'Learn systems thinking and execution'
    },
    {
      id: 'tactical_advice',
      label: 'Ask a Question',
      icon: '💬',
      description: 'Get specific tactical advice'
    }
  ];

  const getMockCoachResponse = (selectedMode, customMsg = null) => {
    const responses = {
      daily_briefing: {
        mode: selectedMode,
        response: "Good morning. Here's what matters today:\n\n1. You have 3 deals stuck in underwriting for 10+ days. These need immediate attention.\n2. 5 new leads from yesterday are uncontacted. First response time is critical.\n3. Your pipeline conversion rate is down 12% this month. Focus on qualification.\n\nProcess beats chaos. Execute on these priorities before checking email.",
        priorities: [
          { priority: 1, category: "Pipeline", urgency: "HIGH", action: "Contact 3 deals stuck in underwriting - push for resolution" },
          { priority: 2, category: "Leads", urgency: "HIGH", action: "Reach out to 5 new leads from yesterday within 1 hour" },
          { priority: 3, category: "Conversion", urgency: "MEDIUM", action: "Review qualification process - identify weak points" }
        ],
        metrics: {
          pipeline_health: "needs_attention",
          total_bottlenecks: 3,
          overdue_tasks: 5
        }
      },
      pipeline_audit: {
        mode: selectedMode,
        response: "Pipeline audit complete. Here's what's broken:\n\nYou have deals dying in underwriting because you're not following up. Every day a deal sits is money evaporating.\n\nYour lead response time averages 4.2 hours. Industry standard is under 5 minutes. You're losing deals before you even know they exist.\n\nFix the process. Stop firefighting.",
        action_items: [
          "Fix John Smith deal - stuck 15 days in underwriting",
          "Fix Sarah Johnson deal - stuck 12 days in processing",
          "Fix Mike Williams deal - stuck 10 days in appraisal"
        ],
        metrics: {
          pipeline_health: "needs_attention",
          total_bottlenecks: 8,
          overdue_tasks: 12
        }
      },
      focus_reset: {
        mode: selectedMode,
        response: "Stop. Breathe. Refocus.\n\nRight now, you're scattered. Here's your reset:\n\n1. Close all tabs except your CRM\n2. Put phone on Do Not Disturb for 90 minutes\n3. Pick ONE priority from your list\n4. Work ONLY on that until complete\n\nDistraction is the enemy of excellence. You know what needs to be done. Do it.",
        priorities: [
          { priority: 1, category: "Focus", urgency: "HIGH", action: "Block 90 minutes - complete one high-priority task" }
        ]
      },
      priority_guidance: {
        mode: selectedMode,
        response: "Here's what you should do next:\n\n1. Handle the hot lead from this morning - 800K purchase, pre-approved, ready to move\n2. Follow up on the 3 deals in underwriting\n3. Return calls to yesterday's inquiries\n\nEverything else is noise. These three actions will move your business forward today.",
        priorities: [
          { priority: 1, category: "Hot Lead", urgency: "HIGH", action: "Contact $800K purchase lead - strike while hot" },
          { priority: 2, category: "Pipeline", urgency: "HIGH", action: "Push 3 underwriting deals forward" },
          { priority: 3, category: "Follow-up", urgency: "MEDIUM", action: "Return yesterday's inquiry calls" }
        ]
      },
      accountability: {
        mode: selectedMode,
        response: "Performance review:\n\nLoans closed this month: Below target\nLead response time: Needs improvement\nPipeline conversion: Declining\n\nYou're capable of better. The numbers don't lie. Either raise your standards or accept mediocrity.\n\nWhich will it be?",
        metrics: {
          pipeline_health: "needs_attention",
          total_bottlenecks: 5,
          overdue_tasks: 8
        }
      },
      tough_love: {
        mode: selectedMode,
        response: "Let's be honest:\n\nYou're busy, but are you productive? Being busy answering emails isn't the same as closing deals.\n\nYou have leads going cold because 'you'll call them later.' Later is why you're not hitting your goals.\n\nYou know exactly what needs to be done. Stop making excuses and execute.",
        action_items: [
          "Stop checking email every 5 minutes",
          "Block time for actual revenue-generating activities",
          "Follow up on cold leads from this week",
          "Update your CRM - it's 3 days behind"
        ]
      },
      teach_process: {
        mode: selectedMode,
        response: "Systems thinking 101:\n\nElite performers don't rely on motivation. They build systems that work even on bad days.\n\nYour system should be:\n1. Lead comes in → Response within 5 minutes → Qualification script\n2. Deal in pipeline → Daily check-in → Move forward or kill it\n3. Week ends → Review metrics → Adjust process\n\nProcess creates consistency. Consistency creates results.",
        action_items: [
          "Document your lead response process",
          "Create daily pipeline review habit (15 min)",
          "Set up weekly metrics review (Friday 4pm)",
          "Build templates for common scenarios"
        ]
      },
      tactical_advice: {
        mode: selectedMode,
        response: customMsg ? `Here's my take on your question:\n\n${customMsg}\n\nThe answer depends on your specific situation, but generally: Focus on the highest-leverage activity. What will move the needle most? Do that first.` : "Ask me a specific question and I'll give you tactical guidance.",
        action_items: customMsg ? ["Apply this guidance to your situation", "Take action within 24 hours"] : []
      }
    };

    return responses[selectedMode] || responses.daily_briefing;
  };

  const callCoach = async (selectedMode, message = null) => {
    setLoading(true);
    setMode(selectedMode);
    setResponse(null);

    try {
      // Build coaching prompt based on mode
      const coachingPrompts = {
        daily_briefing: 'Act as a high-performance business coach for mortgage professionals. Give me my top 3 priorities for today based on my current pipeline, leads, and performance metrics. Be direct and actionable. Focus on what will move the needle.',
        pipeline_audit: 'Act as a high-performance business coach. Audit my mortgage pipeline and identify bottlenecks, stalled deals, and areas where I\'m losing money. Be brutally honest about inefficiencies.',
        focus_reset: 'Act as a high-performance business coach. I feel scattered and need to refocus. Help me identify my single most important task right now and create a plan to execute without distraction.',
        priority_guidance: 'Act as a high-performance business coach. Look at my current situation and tell me exactly what I should do next. What is the highest-leverage activity I can do right now?',
        accountability: 'Act as a high-performance business coach. Review my performance metrics and hold me accountable. Where am I falling short? What standards am I not meeting? Be direct.',
        tough_love: 'Act as a high-performance business coach in tough love mode. Call out where I\'m being inefficient, making excuses, or avoiding what needs to be done. No sugarcoating.',
        teach_process: 'Act as a high-performance business coach. Teach me about systems thinking and building processes that work even when I don\'t feel motivated. How do elite performers structure their day?',
        tactical_advice: message || 'Act as a high-performance business coach. I have a specific question or situation I need tactical advice on.'
      };

      const coachPrompt = coachingPrompts[selectedMode] || coachingPrompts.daily_briefing;
      const fullMessage = message ? `${coachPrompt}\n\nMy question: ${message}` : coachPrompt;

      // Use Smart AI Chat with coaching context
      const aiResponse = await aiAPI.smartChat(fullMessage, {
        include_context: true,
        coaching_mode: selectedMode,
        context_type: 'coaching'
      });

      // Add to conversation history
      setConversationHistory(prev => [
        ...prev,
        { role: 'user', mode: selectedMode, message: message || selectedMode },
        { role: 'coach', response: aiResponse.response }
      ]);

      // Format response for coach display
      setResponse({
        mode: selectedMode,
        response: aiResponse.response,
        context_used: aiResponse.context_used,
        context_count: aiResponse.context_count,
        has_memory: aiResponse.has_memory
      });

      // Refresh memory stats
      loadMemoryStats();
    } catch (error) {
      console.error('Coach error:', error);
      // Use mock response as fallback when backend is unavailable
      const mockResponse = getMockCoachResponse(selectedMode, message);
      setResponse(mockResponse);
    } finally {
      setLoading(false);
    }
  };

  const handleAskQuestion = () => {
    if (!customMessage.trim()) {
      alert('Please enter your question');
      return;
    }
    callCoach('tactical_advice', customMessage);
    setShowCustomInput(false);
    setCustomMessage('');
  };

  const handleAIChatSend = async (message) => {
    if (!message.trim()) return;

    setAiChatLoading(true);
    setAiChatResponse(null);

    try {
      // Send command to Smart AI with action context
      const aiResponse = await aiAPI.smartChat(message, {
        include_context: true,
        context_type: 'action_execution',
        coaching_mode: mode,
        action_items: response.action_items || []
      });

      setAiChatResponse({
        success: true,
        message: aiResponse.response,
        actions_taken: aiResponse.actions_taken || []
      });

      // Show success message
      alert(`AI Command Executed:\n\n${aiResponse.response}`);
    } catch (error) {
      console.error('AI Chat error:', error);
      setAiChatResponse({
        success: false,
        message: 'Failed to execute AI command. Please try again.',
        error: error.message
      });
      alert('Failed to execute AI command. Please try again.');
    } finally {
      setAiChatLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="coach-corner">
        <div className="coach-header">
          <h2>🏆 The Process Coach</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>
        <div className="coach-loading">
          <div className="loading-spinner"></div>
          <p>Coach analyzing your pipeline...</p>
        </div>
      </div>
    );
  }

  if (response) {
    return (
      <div className="coach-corner">
        <div className="coach-header">
          <h2>🏆 The Process Coach</h2>
          <div className="coach-header-actions">
            <button className="btn-back" onClick={() => setResponse(null)}>
              ← Back
            </button>
            <button className="close-button" onClick={onClose}>×</button>
          </div>
        </div>

        <div className="coach-response-container">
          <div className="coach-mode-badge">{mode.replace('_', ' ').toUpperCase()}</div>

          {response.context_used && (
            <div className="context-indicator">
              💡 Using {response.context_count} previous coaching session{response.context_count !== 1 ? 's' : ''} for personalized guidance
            </div>
          )}

          <div className="coach-message">
            {response.response.split('\n').map((line, i) => (
              <p key={i}>{line}</p>
            ))}
          </div>

          {response.priorities && response.priorities.length > 0 && (
            <div className="priorities-section">
              <h3>Priority Actions</h3>
              {response.priorities.map((p, i) => (
                <div key={i} className={`priority-item urgency-${p.urgency.toLowerCase()}`}>
                  <div className="priority-header">
                    <span className="priority-number">#{p.priority}</span>
                    <span className="priority-category">{p.category}</span>
                    <span className={`urgency-badge ${p.urgency.toLowerCase()}`}>{p.urgency}</span>
                  </div>
                  <div className="priority-action">{p.action}</div>
                </div>
              ))}
            </div>
          )}

          {response.action_items && response.action_items.length > 0 && (
            <div className="action-items-section">
              <h3>Action Items</h3>
              <ul>
                {response.action_items.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {response.metrics && (
            <div className="metrics-section">
              <div className="metric-card">
                <span className="metric-label">Pipeline Health</span>
                <span className={`metric-value health-${response.metrics.pipeline_health}`}>
                  {response.metrics.pipeline_health === 'good' ? '✅ Good' : '⚠️ Needs Attention'}
                </span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Bottlenecks</span>
                <span className="metric-value">{response.metrics.total_bottlenecks}</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Overdue Tasks</span>
                <span className="metric-value">{response.metrics.overdue_tasks}</span>
              </div>
            </div>
          )}

          {/* AI Chat / Voice Command Section */}
          <div className="ai-chat-section">
            <div className="ai-chat-header">
              <h3>🤖 Smart AI Commands</h3>
              <p className="ai-chat-description">
                Give voice or text commands to take action on these items. For example:
                "Send Teams message to processor about Sarah Johnson's underwriting delay"
              </p>
            </div>

            {aiChatResponse && (
              <div className={`ai-response-alert ${aiChatResponse.success ? 'success' : 'error'}`}>
                <div className="ai-response-icon">
                  {aiChatResponse.success ? '✅' : '❌'}
                </div>
                <div className="ai-response-text">
                  <strong>{aiChatResponse.success ? 'Command Executed:' : 'Error:'}</strong>
                  <p>{aiChatResponse.message}</p>
                  {aiChatResponse.actions_taken && aiChatResponse.actions_taken.length > 0 && (
                    <ul className="actions-taken-list">
                      {aiChatResponse.actions_taken.map((action, i) => (
                        <li key={i}>{action}</li>
                      ))}
                    </ul>
                  )}
                </div>
                <button
                  className="ai-response-dismiss"
                  onClick={() => setAiChatResponse(null)}
                >
                  ×
                </button>
              </div>
            )}

            <VoiceInput
              onTranscriptChange={setAiChatMessage}
              onSend={handleAIChatSend}
              placeholder="Type or speak your command... e.g., 'Send Teams message to follow up on these deals'"
            />

            {aiChatLoading && (
              <div className="ai-chat-loading">
                <div className="loading-spinner-small"></div>
                <span>Executing AI command...</span>
              </div>
            )}

            <div className="ai-chat-examples">
              <p className="examples-label">Example Commands:</p>
              <div className="example-chips">
                <button
                  className="example-chip"
                  onClick={() => {
                    const exampleMsg = "Please send the processor a Teams message to follow up on these underwriting delays and get these files moving";
                    setAiChatMessage(exampleMsg);
                    handleAIChatSend(exampleMsg);
                  }}
                >
                  📨 Send Teams message to processor
                </button>
                <button
                  className="example-chip"
                  onClick={() => {
                    const exampleMsg = "Create tasks for each of these action items";
                    setAiChatMessage(exampleMsg);
                    handleAIChatSend(exampleMsg);
                  }}
                >
                  ✅ Create tasks from action items
                </button>
                <button
                  className="example-chip"
                  onClick={() => {
                    const exampleMsg = "Send email reminders to all borrowers with stalled deals";
                    setAiChatMessage(exampleMsg);
                    handleAIChatSend(exampleMsg);
                  }}
                >
                  📧 Email borrowers with updates
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="coach-corner">
      <div className="coach-header">
        <div className="header-content">
          <h2>🏆 The Process Coach</h2>
          {memoryStats && (
            <span className="memory-badge" title="Coaching sessions remembered">
              🧠 {memoryStats.total_memories} memories
            </span>
          )}
        </div>
        <button className="close-button" onClick={onClose}>×</button>
      </div>
      <p className="coach-subtitle">Elite Performance Guidance with AI Memory</p>

      <div className="coach-intro">
        <p><strong>Philosophy:</strong> Process over outcome. Standards over feelings. Execution over excuses.</p>
        <p>Select a coaching mode below:</p>
      </div>

      <div className="coach-modes-grid">
        {coachModes.map(m => (
          <button
            key={m.id}
            className="coach-mode-button"
            onClick={() => {
              if (m.id === 'tactical_advice') {
                setShowCustomInput(true);
              } else {
                callCoach(m.id);
              }
            }}
          >
            <div className="mode-icon">{m.icon}</div>
            <div className="mode-label">{m.label}</div>
            <div className="mode-description">{m.description}</div>
          </button>
        ))}
      </div>

      {showCustomInput && (
        <div className="custom-input-modal">
          <div className="modal-content">
            <h3>Ask The Coach</h3>
            <textarea
              value={customMessage}
              onChange={(e) => setCustomMessage(e.target.value)}
              placeholder="What's your question? Be specific."
              rows="4"
            />
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => {
                setShowCustomInput(false);
                setCustomMessage('');
              }}>
                Cancel
              </button>
              <button className="btn-primary" onClick={handleAskQuestion}>
                Get Guidance
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="coach-quick-actions">
        <button
          className="quick-action-btn"
          onClick={() => callCoach('daily_briefing')}
        >
          Give Me My Priorities
        </button>
        <button
          className="quick-action-btn"
          onClick={() => callCoach('pipeline_audit')}
        >
          Fix My Pipeline
        </button>
        <button
          className="quick-action-btn"
          onClick={() => callCoach('focus_reset')}
        >
          Reset My Focus
        </button>
      </div>
    </div>
  );
};

export default CoachCorner;
