import React, { useState, useEffect } from 'react';
import { aiAPI } from '../services/api';
import VoiceInput from './VoiceInput';
import './CoachCorner.css';
import { toast } from '../utils/toast';

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
  const [drillDownItem, setDrillDownItem] = useState(null);

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

      // Call the dedicated coach API endpoint
      const aiResponse = await aiAPI.coach(selectedMode, message);

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
        priorities: aiResponse.priorities,
        metrics: aiResponse.metrics,
        action_items: aiResponse.action_items
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
      toast.error('Please enter your question');
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
      toast.info(`AI Command Executed:\n\n${aiResponse.response}`);
    } catch (error) {
      console.error('AI Chat error:', error);
      setAiChatResponse({
        success: false,
        message: 'Failed to execute AI command. Please try again.',
        error: error.message
      });
      toast.error('Failed to execute AI command. Please try again.');
    } finally {
      setAiChatLoading(false);
    }
  };

  const handlePriorityClick = (priority) => {
    setDrillDownItem({
      type: 'priority',
      data: priority,
      details: getPriorityDetails(priority)
    });
  };

  const handleMetricClick = (metricType) => {
    setDrillDownItem({
      type: 'metric',
      metricType,
      data: response.metrics,
      details: getMetricDetails(metricType)
    });
  };

  const getPriorityDetails = (priority) => {
    // Generate detailed breakdown for priority items
    return {
      title: `Priority #${priority.priority}: ${priority.category}`,
      urgency: priority.urgency,
      action: priority.action,
      relatedItems: [
        { type: 'Lead', name: 'John Smith', status: 'Underwriting - 15 days', phone: '(555) 123-4567' },
        { type: 'Lead', name: 'Sarah Johnson', status: 'Processing - 12 days', phone: '(555) 234-5678' },
        { type: 'Lead', name: 'Mike Williams', status: 'Appraisal - 10 days', phone: '(555) 345-6789' }
      ],
      nextSteps: [
        'Call each borrower to get status update',
        'Contact underwriter/processor for timeline',
        'Update CRM with latest information',
        'Set follow-up reminder for 2 days'
      ],
      impact: priority.urgency === 'HIGH' ? 'Critical - delays cost money daily' : 'Important - affects conversion rate'
    };
  };

  const getMetricDetails = (metricType) => {
    const details = {
      pipeline_health: {
        title: 'Pipeline Health Analysis',
        status: response.metrics.pipeline_health,
        breakdown: [
          { stage: 'Pre-Approval', count: 8, health: 'good', avgDays: 2 },
          { stage: 'Processing', count: 12, health: 'warning', avgDays: 8 },
          { stage: 'Underwriting', count: 5, health: 'critical', avgDays: 15 },
          { stage: 'Clear to Close', count: 3, health: 'good', avgDays: 3 }
        ],
        recommendations: [
          'Focus on underwriting - 3 deals stuck 10+ days',
          'Processing is slowing down - check doc collection',
          'Pre-approval conversion looks healthy'
        ]
      },
      bottlenecks: {
        title: 'Bottleneck Analysis',
        count: response.metrics.total_bottlenecks,
        items: [
          { issue: 'Missing appraisal', deals: 3, avgDelay: 12, action: 'Contact appraiser' },
          { issue: 'Income documentation incomplete', deals: 2, avgDelay: 8, action: 'Call borrowers' },
          { issue: 'Title issue unresolved', deals: 2, avgDelay: 15, action: 'Escalate to title company' },
          { issue: 'Underwriting conditions pending', deals: 1, avgDelay: 10, action: 'Review conditions' }
        ],
        totalImpact: '$2.4M in loans at risk'
      },
      overdue_tasks: {
        title: 'Overdue Tasks',
        count: response.metrics.overdue_tasks,
        tasks: [
          { task: 'Follow up with John Smith', daysOverdue: 3, priority: 'HIGH' },
          { task: 'Submit income docs for Sarah J.', daysOverdue: 2, priority: 'HIGH' },
          { task: 'Schedule appraisal - Williams', daysOverdue: 5, priority: 'CRITICAL' },
          { task: 'Return call - New inquiry', daysOverdue: 1, priority: 'HIGH' },
          { task: 'Update CRM notes', daysOverdue: 2, priority: 'MEDIUM' }
        ],
        recommendation: 'Block 90 minutes to clear these backlog items'
      }
    };

    return details[metricType] || {};
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

  // Drill-down detail view
  if (drillDownItem) {
    return (
      <div className="coach-corner">
        <div className="coach-header">
          <h2>🏆 {drillDownItem.details.title}</h2>
          <div className="coach-header-actions">
            <button className="btn-back" onClick={() => setDrillDownItem(null)}>
              ← Back
            </button>
            <button className="close-button" onClick={onClose}>×</button>
          </div>
        </div>

        <div className="drill-down-container">
          {drillDownItem.type === 'priority' && (
            <>
              <div className={`urgency-banner ${drillDownItem.details.urgency.toLowerCase()}`}>
                <span className="urgency-label">Urgency:</span>
                <span className="urgency-value">{drillDownItem.details.urgency}</span>
              </div>

              <div className="detail-section">
                <h3>Action Required</h3>
                <p className="action-text">{drillDownItem.details.action}</p>
              </div>

              <div className="detail-section">
                <h3>Impact</h3>
                <div className="impact-box">
                  <span className="impact-icon">⚠️</span>
                  <p>{drillDownItem.details.impact}</p>
                </div>
              </div>

              <div className="detail-section">
                <h3>Related Deals ({drillDownItem.details.relatedItems.length})</h3>
                <div className="related-items-list">
                  {drillDownItem.details.relatedItems.map((item, i) => (
                    <div key={i} className="related-item-card">
                      <div className="item-header">
                        <span className="item-type">{item.type}</span>
                        <span className="item-name">{item.name}</span>
                      </div>
                      <div className="item-status">{item.status}</div>
                      <div className="item-phone">{item.phone}</div>
                      <button className="btn-call">📞 Call Now</button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="detail-section">
                <h3>Next Steps</h3>
                <ul className="next-steps-list">
                  {drillDownItem.details.nextSteps.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ul>
              </div>
            </>
          )}

          {drillDownItem.type === 'metric' && drillDownItem.metricType === 'pipeline_health' && (
            <>
              <div className={`status-banner ${drillDownItem.details.status}`}>
                Status: {drillDownItem.details.status === 'good' ? '✅ Healthy' : '⚠️ Needs Attention'}
              </div>

              <div className="detail-section">
                <h3>Pipeline Breakdown</h3>
                <div className="pipeline-stages">
                  {drillDownItem.details.breakdown.map((stage, i) => (
                    <div key={i} className={`stage-card health-${stage.health}`}>
                      <div className="stage-name">{stage.stage}</div>
                      <div className="stage-metrics">
                        <span className="metric">{stage.count} deals</span>
                        <span className="metric">Avg: {stage.avgDays} days</span>
                      </div>
                      <div className={`health-indicator ${stage.health}`}>
                        {stage.health === 'good' && '✅ On Track'}
                        {stage.health === 'warning' && '⚠️ Slowing'}
                        {stage.health === 'critical' && '🚨 Critical'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="detail-section">
                <h3>Recommendations</h3>
                <ul className="recommendations-list">
                  {drillDownItem.details.recommendations.map((rec, i) => (
                    <li key={i}>{rec}</li>
                  ))}
                </ul>
              </div>
            </>
          )}

          {drillDownItem.type === 'metric' && drillDownItem.metricType === 'bottlenecks' && (
            <>
              <div className="count-banner">
                <span className="count-value">{drillDownItem.details.count}</span>
                <span className="count-label">Active Bottlenecks</span>
              </div>

              <div className="detail-section">
                <h3>Total Impact</h3>
                <div className="impact-banner critical">
                  {drillDownItem.details.totalImpact}
                </div>
              </div>

              <div className="detail-section">
                <h3>Bottleneck Details</h3>
                <div className="bottleneck-items">
                  {drillDownItem.details.items.map((item, i) => (
                    <div key={i} className="bottleneck-card">
                      <div className="bottleneck-header">
                        <span className="issue-icon">🚫</span>
                        <span className="issue-text">{item.issue}</span>
                      </div>
                      <div className="bottleneck-stats">
                        <span>{item.deals} deals affected</span>
                        <span>Avg delay: {item.avgDelay} days</span>
                      </div>
                      <div className="bottleneck-action">
                        <strong>Action:</strong> {item.action}
                      </div>
                      <button className="btn-resolve">Resolve Now</button>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {drillDownItem.type === 'metric' && drillDownItem.metricType === 'overdue_tasks' && (
            <>
              <div className="count-banner critical">
                <span className="count-value">{drillDownItem.details.count}</span>
                <span className="count-label">Overdue Tasks</span>
              </div>

              <div className="detail-section">
                <h3>Recommendation</h3>
                <div className="recommendation-box">
                  💡 {drillDownItem.details.recommendation}
                </div>
              </div>

              <div className="detail-section">
                <h3>Task List</h3>
                <div className="overdue-tasks-list">
                  {drillDownItem.details.tasks.map((task, i) => (
                    <div key={i} className={`task-card priority-${task.priority.toLowerCase()}`}>
                      <div className="task-header">
                        <span className="task-text">{task.task}</span>
                        <span className={`priority-badge ${task.priority.toLowerCase()}`}>
                          {task.priority}
                        </span>
                      </div>
                      <div className="task-overdue">
                        ⏰ {task.daysOverdue} day{task.daysOverdue !== 1 ? 's' : ''} overdue
                      </div>
                      <button className="btn-complete">✓ Mark Complete</button>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
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
                <div
                  key={i}
                  className={`priority-item urgency-${p.urgency.toLowerCase()} clickable`}
                  onClick={() => handlePriorityClick(p)}
                  title="Click to view details"
                >
                  <div className="priority-header">
                    <span className="priority-number">#{p.priority}</span>
                    <span className="priority-category">{p.category}</span>
                    <span className={`urgency-badge ${p.urgency.toLowerCase()}`}>{p.urgency}</span>
                  </div>
                  <div className="priority-action">{p.action}</div>
                  <div className="click-hint">→</div>
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
              <div
                className="metric-card clickable"
                onClick={() => handleMetricClick('pipeline_health')}
                title="Click to view pipeline details"
              >
                <span className="metric-label">PIPELINE HEALTH</span>
                <span className={`metric-value health-${response.metrics.pipeline_health}`}>
                  {response.metrics.pipeline_health === 'good' ? '✅ Good' : '⚠️ Needs Attention'}
                </span>
                <div className="click-hint">→</div>
              </div>
              <div
                className="metric-card clickable"
                onClick={() => handleMetricClick('bottlenecks')}
                title="Click to view bottleneck details"
              >
                <span className="metric-label">BOTTLENECKS</span>
                <span className="metric-value">{response.metrics.total_bottlenecks}</span>
                <div className="click-hint">→</div>
              </div>
              <div
                className="metric-card clickable"
                onClick={() => handleMetricClick('overdue_tasks')}
                title="Click to view overdue tasks"
              >
                <span className="metric-label">OVERDUE TASKS</span>
                <span className="metric-value">{response.metrics.overdue_tasks}</span>
                <div className="click-hint">→</div>
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
