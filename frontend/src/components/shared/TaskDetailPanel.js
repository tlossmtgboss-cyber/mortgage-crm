import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { aiAPI } from '../../services/api';
import { sanitizeHTML } from '../../utils/sanitize';
import './TaskDetailPanel.css';
import { toast } from '../../utils/toast';

/**
 * Shared TaskDetailPanel Component
 * Used by: Tasks page, AI Landing Page Action Center, and anywhere task details are shown
 *
 * Props:
 * - task: The selected task object
 * - onComplete: Function to handle task completion
 * - onDelete: Function to handle task deletion
 * - onSnooze: Function to handle snoozing
 * - onDelegate: Function to handle delegation (receives team member)
 * - onSend: Function to handle sending message (id, method, message)
 * - onApproveAi: Function to handle AI action approval
 * - onChangeStatus: Function to handle status change (newStatus)
 * - onClose: Function to close the panel
 * - completing: Boolean indicating if completion is in progress
 * - updatingStatus: Boolean indicating if status update is in progress
 * - compact: Boolean for compact mode (sidebar)
 * - showActionBar: Boolean to show/hide bottom action bar (default true)
 * - teamMembers: Array of team members for delegation
 * - statusOptions: Array of status options for status change modal
 */

// Lead stages (pre-application)
const LEAD_STATUS_OPTIONS = [
  { value: 'new', label: 'New', color: '#6366f1' },
  { value: 'attempted_contact', label: 'Attempted Contact', color: '#8b5cf6' },
  { value: 'contact_made', label: 'Contact Made', color: '#06b6d4' },
  { value: 'needs_analysis', label: 'Needs Analysis', color: '#0ea5e9' },
  { value: 'pre_approved', label: 'Pre-Approved', color: '#10b981' },
  { value: 'application', label: 'Application', color: '#f59e0b' },
  { value: 'not_qualified', label: 'Does Not Qualify', color: '#ef4444' },
  { value: 'withdrawn', label: 'Withdrawn', color: '#6b7280' }
];

// Loan stages (active loans - from Processing onwards)
const LOAN_STATUS_OPTIONS = [
  { value: 'disclosed', label: 'Disclosed', color: '#8b5cf6' },
  { value: 'processing', label: 'In Processing', color: '#f97316' },
  { value: 'in_underwriting', label: 'In Underwriting', color: '#0ea5e9' },
  { value: 'approved', label: 'Approved', color: '#10b981' },
  { value: 'clear_to_close', label: 'Clear to Close', color: '#22c55e' },
  { value: 'suspended', label: 'Suspended', color: '#f59e0b' },
  { value: 'funded', label: 'Funded', color: '#16a34a' },
  { value: 'nurture', label: 'Nurture', color: '#a855f7' },
  { value: 'withdrawn', label: 'Withdrawn', color: '#6b7280' },
  { value: 'not_qualified', label: 'Does Not Qualify', color: '#ef4444' }
];

// Active loan stages that indicate the entity is a loan (not a lead)
const ACTIVE_LOAN_STAGES = [
  'disclosed', 'processing', 'in_processing', 'in_underwriting', 'underwriting',
  'approved', 'clear_to_close', 'ctc', 'suspended', 'funded', 'closing', 'docs_out', 'docs_back'
];

// Default status options if none provided (legacy, use the specific ones above)
const DEFAULT_STATUS_OPTIONS = LEAD_STATUS_OPTIONS;

// Task guidance templates based on workflow type and day
const getTaskGuidance = (task) => {
  const workflowName = (task.workflow_name || '').toLowerCase();
  const title = (task.title || '').toLowerCase();
  const dayMatch = title.match(/day\s*(\d+)/i) || (task.workflow_name || '').match(/day\s*(\d+)/i);
  const day = dayMatch ? parseInt(dayMatch[1]) : null;
  const stage = (task.stage || '').toLowerCase();

  // Prospect/Lead nurture workflows
  if (workflowName.includes('prospect') || workflowName.includes('lead') || workflowName.includes('nurture')) {
    if (day === 1 || day === 0) {
      return {
        action: 'Make initial contact to introduce yourself and understand their needs',
        goal: 'Build rapport and qualify the prospect',
        talkingPoints: [
          'Introduce yourself and your role',
          'Ask about their timeline for buying/refinancing',
          'Understand their motivation (first-time buyer, moving, investment, etc.)',
          'Ask if they\'re working with a realtor',
          'Offer to answer any initial questions about the mortgage process'
        ],
        tips: 'Keep it conversational. Focus on listening more than talking.'
      };
    } else if (day >= 2 && day <= 5) {
      return {
        action: 'Follow up to check if they have questions and gauge interest level',
        goal: 'Move the conversation forward and identify next steps',
        talkingPoints: [
          'Reference your previous conversation',
          'Ask if they\'ve had a chance to think about their options',
          'Offer to send rate information or pre-qualification details',
          'Ask about their preferred timeline',
          'Suggest scheduling a call to discuss their specific situation'
        ],
        tips: 'Be helpful, not pushy. Offer value in every interaction.'
      };
    } else if (day >= 6 && day <= 14) {
      return {
        action: 'Provide value and stay top-of-mind with relevant information',
        goal: 'Maintain engagement and demonstrate expertise',
        talkingPoints: [
          'Share a relevant market update or rate trend',
          'Ask if their situation or timeline has changed',
          'Offer educational content (buying tips, process overview)',
          'Remind them you\'re available when they\'re ready'
        ],
        tips: 'Focus on being a resource rather than making a sale.'
      };
    } else if (day >= 15 && day <= 30) {
      return {
        action: 'Re-engage with a personalized check-in',
        goal: 'Rekindle interest and assess if they\'re still in the market',
        talkingPoints: [
          'Ask if they\'re still considering a home purchase/refinance',
          'Share any significant rate changes since you last spoke',
          'Offer to do a quick pre-qualification if they haven\'t already',
          'Ask if there\'s anything holding them back'
        ],
        tips: 'Be understanding if they\'re not ready. Ask permission to follow up later.'
      };
    } else if (day > 30) {
      return {
        action: 'Long-term nurture touchpoint to maintain relationship',
        goal: 'Stay connected for when they\'re ready to move forward',
        talkingPoints: [
          'Check in on their current situation',
          'Share valuable market insights',
          'Ask if their homeownership goals have changed',
          'Offer to be a resource for any real estate questions'
        ],
        tips: 'Keep it brief and respectful of their time.'
      };
    }
  }

  // Pre-approval follow-up
  if (stage.includes('pre-approved') || stage.includes('pre_approved') || title.includes('pre-approval')) {
    return {
      action: 'Follow up on pre-approval status and next steps',
      goal: 'Keep them engaged in their home search',
      talkingPoints: [
        'Congratulate them on their pre-approval (if recent)',
        'Ask how their home search is going',
        'Remind them of their pre-approval amount and expiration',
        'Ask if they\'re working with a realtor',
        'Offer to connect them with trusted real estate agents'
      ],
      tips: 'Pre-approved leads are hot! They\'re actively looking.'
    };
  }

  // Document collection
  if (title.includes('document') || title.includes('upload') || workflowName.includes('document')) {
    return {
      action: 'Follow up on outstanding documents needed for the loan',
      goal: 'Collect all required documents to keep the loan moving',
      talkingPoints: [
        'Ask if they received the document request',
        'Offer to help if they have questions about any items',
        'Explain why each document is needed (briefly)',
        'Offer alternative ways to submit (email, portal, photos)',
        'Set a clear expectation for when documents are needed'
      ],
      tips: 'Make it easy for them. Offer to accept photos via text if needed.'
    };
  }

  // Application follow-up
  if (stage.includes('application') || title.includes('application')) {
    return {
      action: 'Guide them through completing their loan application',
      goal: 'Get a complete application submitted',
      talkingPoints: [
        'Check if they\'ve started the application',
        'Ask if they have questions about any section',
        'Offer to complete the application together over the phone',
        'Explain next steps after application submission',
        'Set expectations for the timeline'
      ],
      tips: 'Many people get stuck on applications. Offer to do it together.'
    };
  }

  // Processing stage
  if (stage.includes('processing') || workflowName.includes('processing')) {
    return {
      action: 'Provide a status update and address any outstanding items',
      goal: 'Keep the loan moving smoothly through processing',
      talkingPoints: [
        'Give a brief update on where their file stands',
        'Ask about any outstanding conditions or documents',
        'Set expectations for underwriting timeline',
        'Ask if they have questions about the process',
        'Remind them not to make major financial changes'
      ],
      tips: 'Proactive communication prevents anxious borrowers from calling repeatedly.'
    };
  }

  // Default guidance for unmatched tasks
  return {
    action: task.description || task.ai_action || 'Complete this task and update the client',
    goal: 'Maintain communication and move the process forward',
    talkingPoints: [
      'Review the client\'s current status before reaching out',
      'Prepare any relevant updates or information',
      'Ask if they have any questions or concerns',
      'Set clear expectations for next steps'
    ],
    tips: 'Always end the conversation with a clear next step.'
  };
};

/**
 * Generate a personalized draft message based on task context
 * @param {Object} task - The task object
 * @param {string} method - Communication method (Email, Text, Phone, Voicemail)
 * @returns {string} - The generated draft message
 */
const generateDraftMessage = (task, method = 'Email') => {
  const borrowerName = task.borrower?.split(' ')[0] || 'there'; // Get first name
  const guidance = getTaskGuidance(task);
  const dayMatch = (task.title || '').match(/day\s*(\d+)/i) || (task.workflow_name || '').match(/day\s*(\d+)/i);
  const day = dayMatch ? parseInt(dayMatch[1]) : null;
  const stage = (task.stage || '').toLowerCase();

  // For Text/SMS - keep it short and conversational
  if (method === 'Text') {
    // Day 1 initial contact
    if (day === 1 || day === 0) {
      return `Hi ${borrowerName}! This is [Your Name] from [Company]. Thanks for your interest in exploring mortgage options. I'd love to help you find the best solution for your needs. Do you have a few minutes to chat this week?`;
    }
    // Day 2-5 follow-up
    if (day >= 2 && day <= 5) {
      return `Hi ${borrowerName}, just following up on my previous message. Have you had a chance to think about your mortgage options? I'm happy to answer any questions or send over some rate info. Let me know what works best for you!`;
    }
    // Day 6-14 value add
    if (day >= 6 && day <= 14) {
      return `Hi ${borrowerName}! Wanted to share a quick market update - rates have been moving recently. If you're still considering your options, I'd be happy to run some numbers for you. No pressure, just here to help when you're ready!`;
    }
    // Day 15-30 re-engage
    if (day >= 15 && day <= 30) {
      return `Hi ${borrowerName}, hope you're doing well! I wanted to check in and see if your home buying/refinance plans have changed. If you're still in the market, I'm here to help. Would you like me to send over current rates?`;
    }
    // Day 30+ long-term nurture
    if (day > 30) {
      return `Hi ${borrowerName}! Just checking in to see how things are going. If your homeownership plans have evolved, I'd love to catch up. No rush - I'm here whenever you're ready to explore your options.`;
    }
    // Pre-approval follow-up
    if (stage.includes('pre-approved') || stage.includes('pre_approved')) {
      return `Hi ${borrowerName}! How's the house hunt going? Just wanted to remind you that your pre-approval is still active. Found anything exciting? Let me know if you need any help!`;
    }
    // Document collection
    if ((task.title || '').toLowerCase().includes('document')) {
      return `Hi ${borrowerName}! Just a friendly reminder about the documents we need to keep your loan moving. Let me know if you have any questions or need help gathering anything. You can text me photos if that's easier!`;
    }
    // Default text
    return `Hi ${borrowerName}, just wanted to check in and see how things are going. Let me know if you have any questions about your mortgage - I'm here to help!`;
  }

  // For Email - more detailed and professional
  if (method === 'Email') {
    const greeting = `Hi ${borrowerName},\n\n`;
    let body = '';
    let closing = `\n\nBest regards,\n[Your Name]\n[Your Phone]\n[Your Email]`;

    // Day 1 initial contact
    if (day === 1 || day === 0) {
      body = `Thank you for your interest in exploring your mortgage options! I'm excited to help you on your journey to homeownership.

I'd love to learn more about your goals and timeline. Here are a few things I can help you with:

• Understanding your buying power and getting pre-approved
• Comparing different loan programs to find the best fit
• Answering any questions about the mortgage process

Do you have 15-20 minutes this week for a quick call? I'm happy to work around your schedule.`;
    }
    // Day 2-5 follow-up
    else if (day >= 2 && day <= 5) {
      body = `I wanted to follow up on my previous message and see if you've had a chance to think about your mortgage options.

I know this is a big decision, and I'm here to help make the process as smooth as possible. A few things I can assist with:

• Providing current rate information based on your situation
• Walking you through the pre-qualification process (it's quick and easy!)
• Answering any questions you might have

Would you like to schedule a brief call to discuss your options? I'm happy to work around your schedule.`;
    }
    // Day 6-14 value add
    else if (day >= 6 && day <= 14) {
      body = `I wanted to reach out with a quick market update. Interest rates have been fluctuating recently, and I thought you might find this information helpful as you consider your options.

If you're still thinking about buying a home or refinancing, here are some things to keep in mind:

• Current market conditions and what they mean for buyers
• How to get the best rate when you're ready to move forward
• Programs that might help with down payment or closing costs

I'm always happy to run some numbers for you with no obligation. Just let me know if you'd like me to put together a personalized analysis.`;
    }
    // Day 15-30 re-engage
    else if (day >= 15 && day <= 30) {
      body = `I hope this message finds you well! I wanted to check in and see how your plans are progressing.

I understand that timing is everything when it comes to a big decision like this. I'm here to be a resource for you, whether you're ready to move forward now or just gathering information for the future.

A few updates since we last connected:
• Current rate environment and trends
• New loan programs that might benefit your situation
• Market conditions in your area

Would you like to catch up with a quick call? I'd love to hear where you are in your journey and how I can help.`;
    }
    // Day 30+ long-term nurture
    else if (day > 30) {
      body = `It's been a while since we connected, and I wanted to reach out to see how things are going.

Life circumstances change, and I'm curious if your homeownership goals have evolved. Whether you're closer to making a move or your plans have shifted, I'm here as a resource.

I'd love to catch up when you have a few minutes. No pressure - just want to make sure you have the information you need when the time is right.`;
    }
    // Pre-approval follow-up
    else if (stage.includes('pre-approved') || stage.includes('pre_approved')) {
      body = `Congratulations again on your pre-approval! I wanted to check in and see how your home search is going.

Quick reminders about your pre-approval:
• Your approval amount: [Amount]
• Pre-approval expiration: [Date]
• You're in a strong position to make offers

Are you working with a real estate agent? If not, I'd be happy to connect you with some trusted professionals in your area.

Let me know how I can support you in finding your perfect home!`;
    }
    // Document collection
    else if ((task.title || '').toLowerCase().includes('document')) {
      body = `I wanted to follow up on the documents we need to keep your loan moving forward smoothly.

Outstanding items:
${task.missing_documents?.map(doc => `• ${doc}`).join('\n') || '• Please refer to the document checklist I sent previously'}

A few tips to make this easier:
• Photos of documents are perfectly acceptable - just make sure they're clear and complete
• You can upload directly to your secure portal
• I'm happy to answer any questions about why specific documents are needed

The sooner we receive these items, the faster we can move toward closing. Please let me know if you have any questions!`;
    }
    // Default email
    else {
      body = `I wanted to reach out and check in on your mortgage journey.

${guidance.action}

Here's what I'd like to discuss:
${guidance.talkingPoints.slice(0, 3).map(point => `• ${point}`).join('\n')}

Please let me know if you have any questions or if there's a convenient time to connect.`;
    }

    return greeting + body + closing;
  }

  // For Phone/Voicemail - talking points script
  if (method === 'Phone' || method === 'Voicemail') {
    const intro = `CALL SCRIPT for ${borrowerName}:\n\n`;
    let script = '';

    if (method === 'Voicemail') {
      script = `"Hi ${borrowerName}, this is [Your Name] calling from [Company]. I wanted to follow up with you about your mortgage inquiry. `;

      if (day === 1 || day === 0) {
        script += `I'd love to chat about your home financing goals and see how I can help. `;
      } else if (day >= 2 && day <= 5) {
        script += `I wanted to see if you had any questions about your options or if there's anything I can help with. `;
      } else {
        script += `I wanted to check in and see how things are going. `;
      }

      script += `Give me a call back at [Your Phone] when you get a chance, or feel free to text me. I look forward to speaking with you!"`;
    } else {
      script = `OPENING:\n"Hi ${borrowerName}, this is [Your Name] from [Company]. Is this a good time to chat for a few minutes?"\n\n`;
      script += `KEY TALKING POINTS:\n`;
      guidance.talkingPoints.forEach((point, idx) => {
        script += `${idx + 1}. ${point}\n`;
      });
      script += `\nGOAL: ${guidance.goal}\n`;
      script += `\nCLOSING:\n"What questions do you have for me?" Then set clear next steps.`;
    }

    return intro + script;
  }

  // Fallback
  return `Hi ${borrowerName},\n\nI wanted to reach out regarding your mortgage inquiry. Please let me know if you have any questions or if there's a convenient time to connect.\n\nBest regards`;
};

const TaskDetailPanel = ({
  task,
  onComplete,
  onDelete,
  onSnooze,
  onDelegate,
  onSend,
  onApproveAi,
  onChangeStatus,
  onClose,
  completing = false,
  updatingStatus = false,
  compact = false,
  showActionBar = true,
  teamMembers = [],
  statusOptions = DEFAULT_STATUS_OPTIONS
}) => {
  const navigate = useNavigate();

  // Local state
  const [editingMessage, setEditingMessage] = useState(false);
  const [draftMessage, setDraftMessage] = useState('');
  const [aiInstructions, setAiInstructions] = useState('');
  const [aiAcknowledgment, setAiAcknowledgment] = useState(null);
  const [sendingInstruction, setSendingInstruction] = useState(false);
  const [communicationMethod, setCommunicationMethod] = useState('Email');
  const [taskOwner, setTaskOwner] = useState('Loan Officer');
  const [showHistory, setShowHistory] = useState(false);
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [showDelegateModal, setShowDelegateModal] = useState(false);
  // SLA task state
  const [slaMilestoneDate, setSlaMilestoneDate] = useState('');
  const [completingSla, setCompletingSla] = useState(false);

  // Reset state when task changes
  useEffect(() => {
    if (task) {
      const method = task.preferred_contact_method || 'Email';
      setCommunicationMethod(method);
      // Generate AI-drafted message based on task context
      const generatedMessage = generateDraftMessage(task, method);
      setDraftMessage(generatedMessage);
      setTaskOwner(task.owner || 'Loan Officer');
      setAiInstructions('');
      setAiAcknowledgment(null);
      setEditingMessage(false);
      setShowHistory(false);
      // Reset SLA date - use existing milestone_date if available
      setSlaMilestoneDate(task.milestone_date ? task.milestone_date.split('T')[0] : '');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task?.id]);

  // Regenerate message when communication method changes (but not when editing)
  useEffect(() => {
    if (task && !editingMessage) {
      const generatedMessage = generateDraftMessage(task, communicationMethod);
      setDraftMessage(generatedMessage);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [communicationMethod]);

  if (!task) {
    return (
      <div className={`task-detail-panel ${compact ? 'compact' : ''}`}>
        <div className="detail-empty">
          <span className="empty-icon">📋</span>
          <p>Select a task to view details</p>
        </div>
      </div>
    );
  }

  const getUrgencyColor = (urgency) => {
    switch (urgency?.toLowerCase()) {
      case 'critical': return '#dc2626';
      case 'high': return '#f97316';
      case 'medium': return '#eab308';
      case 'low': return '#22c55e';
      default: return '#6b7280';
    }
  };

  const getSourceIcon = (source) => {
    switch (source?.toLowerCase()) {
      case 'workflow': return '⚙️';
      case 'ai engine': return '🤖';
      case 'manual priority': return '⭐';
      case 'leads engine': return '👤';
      case 'milestone risk': return '⚠️';
      case 'client for life':
      case 'mum': return '👋';
      case 'messages': return '💬';
      default: return '📋';
    }
  };

  const handleNavigateToEntity = () => {
    const loanId = task.loan_id || task.loanId;
    const leadId = task.lead_id || task.leadId;

    // Prioritize navigating to the client profile (loan or lead page)
    if (loanId) {
      navigate(`/loans/${loanId}`);
    } else if (leadId) {
      navigate(`/leads/${leadId}`);
    } else if (task.entity_type === 'loan' && task.entity_id) {
      navigate(`/loans/${task.entity_id}`);
    } else if (task.entity_type === 'lead' && task.entity_id) {
      navigate(`/leads/${task.entity_id}`);
    }
  };

  const handleNavigateToSource = () => {
    if (task.source === 'Workflow') {
      navigate('/workflow');
    } else if (task.source === 'AI Engine') {
      navigate('/ai');
    } else if (task.source === 'Messages') {
      navigate('/dashboard'); // Messages integrated into dashboard
    } else if (task.source === 'Client for Life' || task.source === 'MUM') {
      navigate('/portfolio');
    } else if (task.source === 'Milestone Risk') {
      const loanId = task.loan_id || task.loanId || task.entity_id;
      if (loanId) navigate(`/loans/${loanId}`);
    }
  };

  const handleSendToAi = async () => {
    if (!aiInstructions.trim()) return;
    setSendingInstruction(true);
    try {
      const response = await aiAPI.submitTrainingInstruction(
        aiInstructions,
        {
          task_type: task.source || 'general',
          borrower_name: task.borrower || '',
          task_title: task.title || '',
          stage: task.stage || ''
        }
      );
      setAiAcknowledgment(response.acknowledgment);
      setAiInstructions('');
    } catch (error) {
      console.error('Failed to send instruction:', error);
      setAiAcknowledgment('Failed to send instruction. Please try again.');
    } finally {
      setSendingInstruction(false);
    }
  };

  const handleDeleteClick = () => {
    // Delete directly without confirmation
    onDelete && onDelete(task.id);
  };

  // Handle SLA task completion with date
  const handleCompleteSlaTask = async () => {
    if (!slaMilestoneDate) {
      toast.error('Please enter the milestone completion date');
      return;
    }

    setCompletingSla(true);
    try {
      // Extract numeric task ID if it's a string like "workflow-123"
      let taskId = task.id;
      if (typeof taskId === 'string' && taskId.includes('-')) {
        taskId = taskId.split('-').pop();
      }

      const response = await fetch(`/api/v1/tasks/${taskId}/complete-sla`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          milestone_date: slaMilestoneDate
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to complete SLA task');
      }

      const result = await response.json();

      // Show success message with details
      let message = 'SLA task completed!';
      if (result.loan_field_updated) {
        message += ` Updated ${result.loan_field_updated.replace(/_/g, ' ')} on the loan.`;
      }
      if (result.milestone_completed) {
        message += ' SLA milestone marked as complete.';
      }
      toast.info(message);

      // Call parent's onComplete to remove from list
      onComplete && onComplete(task.id);
    } catch (error) {
      console.error('Error completing SLA task:', error);
      toast.error(error.message || 'Failed to complete SLA task');
    } finally {
      setCompletingSla(false);
    }
  };

  const hasEntityLink = task.loan_id || task.loanId || task.lead_id || task.leadId || task.entity_id;
  const isSlaTask = task.sla_milestone_id || task.sla_milestone_type || task.related_type === 'sla_milestone';

  // Determine if this is a loan (active loan stage) or lead based on current stage and entity type
  const currentStage = (task.stage || task.status || '').toLowerCase().replace(/\s+/g, '_');
  const isLoanEntity = task.entity_type === 'loan' || task.loan_id || task.loanId ||
    ACTIVE_LOAN_STAGES.some(stage => currentStage.includes(stage));

  // Use appropriate status options based on entity type
  const effectiveStatusOptions = isLoanEntity ? LOAN_STATUS_OPTIONS :
    (statusOptions !== DEFAULT_STATUS_OPTIONS ? statusOptions : LEAD_STATUS_OPTIONS);

  return (
    <div className={`task-detail-panel ${compact ? 'compact' : ''}`}>
      {/* Header with source badge */}
      <div className="detail-header">
        <div className="detail-source">
          <span className="source-icon-large">{task.sourceIcon || getSourceIcon(task.source)}</span>
          <span className="source-name">{task.source || 'Task'}</span>
        </div>
        <div className="detail-header-right">
          {task.ai_confidence && (
            <span
              className={`ai-confidence-badge ${task.ai_confidence >= 90 ? 'high' : task.ai_confidence >= 70 ? 'medium' : 'low'}`}
              title={`AI Confidence: ${task.ai_confidence}%`}
            >
              🤖 AI Confidence: {task.ai_confidence}%
            </span>
          )}
          {onClose && (
            <button className="detail-close-btn" onClick={onClose}>×</button>
          )}
        </div>
      </div>

      {/* Title */}
      <h2 className="detail-title">{task.title}</h2>

      {/* Info Grid */}
      <div className="detail-body">
        <div className="detail-info-grid">
          {task.borrower && (
            <div className="detail-info-item">
              <span className="detail-label">Client</span>
              <span
                className={`detail-value ${hasEntityLink ? 'client-link' : ''}`}
                onClick={hasEntityLink ? handleNavigateToEntity : undefined}
                style={{
                  cursor: hasEntityLink ? 'pointer' : 'default',
                  color: hasEntityLink ? '#218D8D' : 'inherit',
                  textDecoration: hasEntityLink ? 'underline' : 'none'
                }}
              >
                {task.borrower}
              </span>
            </div>
          )}
          <div className="detail-info-item">
            <span className="detail-label">Stage</span>
            <span
              className="detail-value clickable-link"
              onClick={handleNavigateToEntity}
            >
              {task.stage || task.status || 'N/A'}
            </span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">Priority</span>
            <span
              className="detail-urgency-badge"
              style={{ backgroundColor: getUrgencyColor(task.urgency || task.priority) }}
            >
              {task.urgency || task.priority || 'Medium'}
            </span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">Source</span>
            <span
              className="detail-value clickable-link"
              onClick={handleNavigateToSource}
            >
              {task.source || 'Manual'}
            </span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">Owner</span>
            <span className="detail-value">{taskOwner}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">{task.source === 'Workflow' ? 'Due Date' : 'Date Created'}</span>
            <span className="detail-value">
              {task.due_date
                ? new Date(task.due_date).toLocaleDateString()
                : task.date_created || task.created_at
                  ? new Date(task.date_created || task.created_at).toLocaleString()
                  : 'N/A'}
              {task.days_until_due !== undefined && (
                <span className={`due-badge ${task.days_until_due === 0 ? 'due-today' : task.days_until_due === 1 ? 'due-tomorrow' : 'due-upcoming'}`}>
                  {task.days_until_due === 0 ? 'Today' : task.days_until_due === 1 ? 'Tomorrow' : `In ${task.days_until_due} days`}
                </span>
              )}
            </span>
          </div>

          {/* Send Via Options */}
          <div className="detail-info-item detail-comm-method-item">
            <span className="detail-label">Send Via</span>
            <div className="comm-method-selector">
              <button
                className={`comm-method-btn ${communicationMethod === 'Email' ? 'active' : ''}`}
                onClick={() => setCommunicationMethod('Email')}
              >
                📧 Email
              </button>
              <button
                className={`comm-method-btn ${communicationMethod === 'Text' ? 'active' : ''}`}
                onClick={() => setCommunicationMethod('Text')}
              >
                💬 Text
              </button>
              <button
                className={`comm-method-btn ${communicationMethod === 'Phone' ? 'active' : ''}`}
                onClick={() => setCommunicationMethod('Phone')}
              >
                📞 Phone
              </button>
              <button
                className={`comm-method-btn ${communicationMethod === 'Voicemail' ? 'active' : ''}`}
                onClick={() => setCommunicationMethod('Voicemail')}
              >
                🎙️ Voicemail
              </button>
            </div>
          </div>
        </div>

        {/* Action Buttons - Positioned after Send Via, before What to Accomplish */}
        {showActionBar && (
          <div className="detail-actions-inline">
            <button
              className="btn-detail-send"
              onClick={() => onSend && onSend(task.id, communicationMethod, draftMessage)}
            >
              📤 Send via {communicationMethod}
            </button>
            {task.ai_action && (
              <button
                className="btn-detail-approve"
                onClick={() => onApproveAi && onApproveAi(task.id)}
              >
                Approve AI Action
              </button>
            )}
            <button
              className="btn-detail-status"
              onClick={() => setShowStatusModal(true)}
            >
              📊 Change Status
            </button>
            <button
              className="btn-detail-secondary"
              onClick={() => onSnooze && onSnooze(task.id)}
            >
              💤 Snooze
            </button>
            <button
              className="btn-detail-secondary"
              onClick={() => setShowDelegateModal(true)}
            >
              👥 Delegate
            </button>
            <button
              className="btn-detail-complete"
              onClick={() => onComplete && onComplete(task.id)}
              disabled={completing}
            >
              {completing ? '⏳ Completing...' : '✓ Complete Task'}
            </button>
            <button
              className="btn-detail-danger"
              onClick={handleDeleteClick}
            >
              🗑️ Delete
            </button>
          </div>
        )}

        {/* Task Description - What needs to be accomplished */}
        <div className="task-description-section">
          <div className="task-description-header">
            <span className="description-icon">📋</span>
            <span className="description-title">What to Accomplish</span>
          </div>
          <div className="task-description-content">
            {/* Workflow badge if applicable */}
            {task.workflow_name && (
              <p className="task-workflow-info">
                <span className="workflow-badge" style={{ backgroundColor: task.workflow_color || '#218D8D' }}>
                  {task.workflow_name}
                </span>
                {task.days_until_due !== undefined && (
                  <span className="days-info">
                    {task.days_until_due === 0 ? 'Due today' :
                     task.days_until_due === 1 ? 'Due tomorrow' :
                     `Due in ${task.days_until_due} days`}
                  </span>
                )}
              </p>
            )}

            {/* Enhanced Task Guidance */}
            {(() => {
              const guidance = getTaskGuidance(task);
              return (
                <div className="task-guidance">
                  {/* Action */}
                  <div className="guidance-section guidance-action">
                    <div className="guidance-label">
                      <span className="guidance-icon">🎯</span>
                      <span>Action</span>
                    </div>
                    <p className="guidance-text">{guidance.action}</p>
                  </div>

                  {/* Goal */}
                  <div className="guidance-section guidance-goal">
                    <div className="guidance-label">
                      <span className="guidance-icon">🏁</span>
                      <span>Goal</span>
                    </div>
                    <p className="guidance-text">{guidance.goal}</p>
                  </div>

                  {/* Talking Points */}
                  <div className="guidance-section guidance-talking-points">
                    <div className="guidance-label">
                      <span className="guidance-icon">💬</span>
                      <span>Talking Points</span>
                    </div>
                    <ul className="talking-points-list">
                      {guidance.talkingPoints.map((point, idx) => (
                        <li key={idx}>{point}</li>
                      ))}
                    </ul>
                  </div>

                  {/* Tips */}
                  {guidance.tips && (
                    <div className="guidance-section guidance-tips">
                      <div className="guidance-label">
                        <span className="guidance-icon">💡</span>
                        <span>Pro Tip</span>
                      </div>
                      <p className="guidance-text tip-text">{guidance.tips}</p>
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        </div>

        {/* SLA Milestone Date Input Section */}
        {isSlaTask && (
          <div className="detail-sla-section">
            <div className="sla-section-header">
              <span className="sla-icon">⚠️</span>
              <span className="sla-title">SLA Milestone Completion</span>
            </div>
            <div className="sla-section-content">
              <p className="sla-instruction">
                Enter the date this milestone was completed to update the loan's Important Dates:
              </p>
              {task.sla_milestone_type && (
                <p className="sla-milestone-type">
                  <strong>Milestone:</strong> {task.sla_milestone_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </p>
              )}
              {task.sla_date_field && (
                <p className="sla-date-field">
                  <strong>Updates:</strong> {task.sla_date_field.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </p>
              )}
              <div className="sla-date-input-container">
                <label htmlFor="sla-milestone-date">Milestone Date:</label>
                <input
                  id="sla-milestone-date"
                  type="date"
                  className="sla-date-input"
                  value={slaMilestoneDate}
                  onChange={(e) => setSlaMilestoneDate(e.target.value)}
                  max={new Date().toISOString().split('T')[0]}
                />
              </div>
              <button
                className="btn-complete-sla"
                onClick={handleCompleteSlaTask}
                disabled={completingSla || !slaMilestoneDate}
              >
                {completingSla ? '⏳ Completing...' : '✓ Complete SLA Milestone'}
              </button>
            </div>
          </div>
        )}

        {/* Missing Documents Section */}
        {task.missing_documents && task.missing_documents.length > 0 && (
          <div className="detail-missing-docs-section">
            <div className="missing-docs-header">
              <span className="docs-icon">📄</span>
              <h3>Missing Documents Detected by AI</h3>
            </div>
            <div className="missing-docs-list">
              {task.missing_documents.map((doc, idx) => (
                <div key={idx} className="missing-doc-item">
                  <span className="doc-bullet">•</span>
                  <span className="doc-name">{doc}</span>
                </div>
              ))}
            </div>
            <div className="missing-docs-note">
              <span className="ai-badge">🤖 AI Analysis</span>
              <span className="analysis-text">Detected from email thread analysis</span>
            </div>
          </div>
        )}

        {/* AI Training + AI Drafted Message Sections - Always show for workflow tasks */}
        {(task.source === 'Workflow' || task.workflow_name || task.borrower) && (
          <>
            {/* AI Training Instructions Section */}
            <div className="detail-ai-training-section">
              <div className="ai-training-header">
                <span className="training-icon">🎓</span>
                <span className="training-title">Train AI (Optional)</span>
              </div>

              {/* Inline AI Response */}
              {aiAcknowledgment && (
                <div className="ai-conversation-response">
                  <div className="ai-response-header">
                    <span className="ai-response-icon">🤖</span>
                    <span className="ai-response-label">AI Response</span>
                    <button
                      className="btn-clear-response"
                      onClick={() => setAiAcknowledgment(null)}
                    >
                      ✕
                    </button>
                  </div>
                  <div
                    className="ai-response-content"
                    dangerouslySetInnerHTML={{
                      __html: sanitizeHTML(
                        aiAcknowledgment
                          .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                          .replace(/\n/g, '<br />'),
                        { allowedTags: ['strong', 'br', 'em', 'b', 'i'] }
                      )
                    }}
                  />
                </div>
              )}

              <div className="ai-training-input-container">
                <textarea
                  className="ai-training-input"
                  placeholder={aiAcknowledgment
                    ? "Continue the conversation or provide additional instructions..."
                    : "Type instructions to teach AI how to handle similar tasks in the future... (e.g., 'Always mention our competitive rates when following up on pre-approvals')"
                  }
                  value={aiInstructions}
                  onChange={(e) => setAiInstructions(e.target.value)}
                  rows={3}
                  autoComplete="off"
                />
                <button
                  className="btn-send-to-ai"
                  disabled={sendingInstruction || !aiInstructions.trim()}
                  onClick={handleSendToAi}
                >
                  {sendingInstruction ? 'Sending...' : aiAcknowledgment ? 'Continue' : 'Send to AI'}
                </button>
              </div>
            </div>

            {/* AI-Drafted Message Section */}
            <div className="detail-ai-message-section">
              <div className="ai-message-header">
                <div className="ai-message-title-row">
                  <span className="ai-icon-large">🤖</span>
                  <span className="ai-message-title">AI-Drafted Message</span>
                </div>
                <button
                  className="btn-edit-message"
                  onClick={() => setEditingMessage(!editingMessage)}
                >
                  {editingMessage ? '✓ Done Editing' : '✏️ Edit Message'}
                </button>
              </div>
              <div className="ai-message-body">
                {editingMessage ? (
                  <textarea
                    className="message-editor"
                    value={draftMessage}
                    onChange={(e) => setDraftMessage(e.target.value)}
                    rows={12}
                  />
                ) : (
                  <div
                    className="message-preview"
                    dangerouslySetInnerHTML={{
                      __html: sanitizeHTML(
                        draftMessage.replace(/\n/g, '<br />'),
                        { allowedTags: ['br'] }
                      )
                    }}
                  />
                )}
              </div>
            </div>
          </>
        )}

        {/* Recommended Action */}
        {task.action && (
          <div className="detail-action-section">
            <h3>Recommended Action</h3>
            <p>{task.action}</p>
          </div>
        )}

        {/* Communication History */}
        {task.communication_history && task.communication_history.length > 0 && (
          <div className="communication-history-section">
            <button
              className="history-accordion-button"
              onClick={() => setShowHistory(!showHistory)}
            >
              <span className="history-icon">📋</span>
              <span className="history-title">Communication History ({task.communication_history.length})</span>
              <span className="history-toggle">{showHistory ? '▼' : '▶'}</span>
            </button>
            {showHistory && (
              <div className="history-content">
                {task.communication_history.map((comm, idx) => (
                  <div key={idx} className="history-item">
                    <div className="history-item-header">
                      <div className="history-type-date">
                        <span className="history-type-icon">
                          {comm.type === 'Email' && '📧'}
                          {comm.type === 'Phone' && '📞'}
                          {comm.type === 'Text' && '💬'}
                        </span>
                        <span className="history-type">{comm.type}</span>
                        <span className="history-date">{new Date(comm.date).toLocaleDateString()}</span>
                      </div>
                      <span className={`history-status ${comm.status?.toLowerCase()}`}>
                        {comm.status}
                      </span>
                    </div>
                    <div className="history-item-body">
                      {comm.subject && <div className="history-subject">{comm.subject}</div>}
                      <div className="history-message">{comm.message}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Action buttons moved to inline position after Send Via */}

      {/* Change Status Modal */}
      {showStatusModal && (
        <div className="modal-overlay" onClick={() => setShowStatusModal(false)}>
          <div className="status-modal" onClick={(e) => e.stopPropagation()}>
            <div className="status-modal-header">
              <h3>Change {isLoanEntity ? 'Loan' : 'Lead'} Status</h3>
              <button className="modal-close" onClick={() => setShowStatusModal(false)}>×</button>
            </div>
            <div className="status-modal-content">
              <p className="status-current">
                Current: <strong>{task.stage || task.status || 'Unknown'}</strong>
              </p>
              <div className="status-options">
                {effectiveStatusOptions.map((stage) => (
                  <button
                    key={stage.value}
                    className={`status-option ${currentStage === stage.value || currentStage.includes(stage.value) ? 'current' : ''}`}
                    style={{ borderLeftColor: stage.color }}
                    onClick={() => {
                      onChangeStatus && onChangeStatus(stage.value);
                      setShowStatusModal(false);
                    }}
                    disabled={updatingStatus}
                  >
                    <span className="status-dot" style={{ backgroundColor: stage.color }}></span>
                    {stage.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delegate Modal */}
      {showDelegateModal && (
        <div className="modal-overlay" onClick={() => setShowDelegateModal(false)}>
          <div className="delegate-modal" onClick={(e) => e.stopPropagation()}>
            <div className="delegate-modal-header">
              <h3>Delegate Task</h3>
              <button className="modal-close" onClick={() => setShowDelegateModal(false)}>×</button>
            </div>
            <div className="delegate-modal-content">
              <p>Select a team member to delegate this task to:</p>
              <div className="team-member-list">
                {teamMembers.length > 0 ? (
                  teamMembers.map((member) => (
                    <button
                      key={member.id}
                      className="team-member-option"
                      onClick={() => {
                        onDelegate && onDelegate(member);
                        setShowDelegateModal(false);
                      }}
                    >
                      <span className="member-avatar">
                        {member.first_name?.[0]}{member.last_name?.[0]}
                      </span>
                      <span className="member-name">
                        {member.first_name} {member.last_name}
                      </span>
                      <span className="member-role">{member.role || 'Team Member'}</span>
                    </button>
                  ))
                ) : (
                  <p className="no-team-members">No team members available</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default TaskDetailPanel;
