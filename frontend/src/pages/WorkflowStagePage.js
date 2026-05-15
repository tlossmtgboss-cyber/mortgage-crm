import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import './WorkflowStagePage.css';
import { getToken } from '../utils/tokenStore';

// Status configurations for each stage
const LEAD_STATUSES = {
  new: { name: 'New', color: '#6b7280' },
  attempted_contact: { name: 'Attempted Contact', color: '#f59e0b' },
  prospect: { name: 'Prospect', color: '#3b82f6' },
  pre_qualified: { name: 'Pre-Qualified', color: '#06b6d4' },
  pre_approved: { name: 'Pre-Approved', color: '#2D7A52' },
  long_term_nurture: { name: 'Long-Term Nurture', color: '#B8924A' },
  credit_repair: { name: 'Credit Repair', color: '#f97316' },
  do_not_call: { name: 'Do Not Call', color: '#dc2626' }
};

const ACTIVE_LOAN_STATUSES = {
  application: { name: 'Application', color: '#B8924A' },
  disclosed: { name: 'Disclosed', color: '#B8924A' },
  in_processing: { name: 'In Processing', color: '#3b82f6' },
  underwriting_received: { name: 'Underwriting Received', color: '#B8924A' },
  approved: { name: 'Approved', color: '#2D7A52' },
  clear_to_close: { name: 'Clear to Close', color: '#f59e0b' },
  suspended: { name: 'Suspended', color: '#ef4444' },
  withdrawn: { name: 'Withdrawn', color: '#9ca3af' },
  does_not_qualify: { name: 'Does Not Qualify', color: '#dc2626' }
};

const PORTFOLIO_STATUSES = {
  closed_funded: { name: 'Closed and Funded', color: '#2D7A52' }
};

const STAGE_CONFIG = {
  lead: {
    name: 'Lead',
    description: 'Initial contact and qualification workflow',
    color: '#3b82f6',
    statuses: LEAD_STATUSES,
    defaultTasksByStatus: {
      new: [
        { id: 1, title: 'Initial Contact', description: 'Make first contact with lead', order: 1, auto_trigger: 'on_lead_create', days_offset: 0 },
        { id: 2, title: 'Send Introduction Email', description: 'Send welcome email', order: 2, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      attempted_contact: [
        { id: 3, title: 'Follow-up Call', description: 'Attempt to reach lead again', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 4, title: 'Send Follow-up Email', description: 'Email if no phone response', order: 2, auto_trigger: 'scheduled', days_offset: 1 },
        { id: 5, title: 'Final Attempt', description: 'Last contact attempt', order: 3, auto_trigger: 'scheduled', days_offset: 3 }
      ],
      prospect: [
        { id: 6, title: 'Schedule Discovery Call', description: 'Set up initial consultation', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 7, title: 'Send Loan Options', description: 'Email loan product info', order: 2, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      pre_qualified: [
        { id: 11, title: 'Run Credit Check', description: 'Pull credit report', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 12, title: 'Verify Income', description: 'Review income documents', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 13, title: 'Send Pre-Qual Letter', description: 'Email pre-qualification', order: 3, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      pre_approved: [
        { id: 14, title: 'Generate Pre-Approval', description: 'Create pre-approval letter', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 15, title: 'Send Pre-Approval', description: 'Email to client', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 16, title: 'Convert to Active Loan', description: 'Move to application', order: 3, auto_trigger: 'manual', days_offset: 0 }
      ],
      long_term_nurture: [
        { id: 17, title: 'Add to Drip Campaign', description: 'Enroll in long-term nurture sequence', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 18, title: 'Schedule 6-Month Check-in', description: 'Calendar follow-up', order: 2, auto_trigger: 'scheduled', days_offset: 180 }
      ],
      credit_repair: [
        { id: 19, title: 'Refer to Credit Counselor', description: 'Send credit repair resources', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 20, title: 'Schedule 90-Day Review', description: 'Check credit progress', order: 2, auto_trigger: 'scheduled', days_offset: 90 }
      ]
    }
  },
  active_loan: {
    name: 'Active Loan',
    description: 'Loan processing and underwriting workflow',
    color: '#2D7A52',
    statuses: ACTIVE_LOAN_STATUSES,
    defaultTasksByStatus: {
      application: [
        { id: 8, title: 'Send Application Link', description: 'Email application portal', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 9, title: 'Collect Documents', description: 'Request income and assets', order: 2, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 10, title: 'Credit Authorization', description: 'Get credit check consent', order: 3, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      disclosed: [
        { id: 22, title: 'Generate Loan Estimate', description: 'Create LE with loan terms, rates, closing costs, and cash to close', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 23, title: 'Generate Initial Disclosures', description: 'Prepare TRID disclosures, state disclosures, and acknowledgment forms', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 24, title: 'Send LE Package', description: 'Deliver via email with eSign link, SMS notification, and portal update', order: 3, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 25, title: 'Start TRID Clock', description: 'Track 3-business-day waiting period for compliance', order: 4, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 26, title: 'First Reminder (4 hrs)', description: 'Send reminder if LE not opened within 4 hours', order: 5, auto_trigger: 'scheduled', days_offset: 0 },
        { id: 27, title: 'Second Reminder (24 hrs)', description: 'Create LO task and send follow-up if not acknowledged', order: 6, auto_trigger: 'scheduled', days_offset: 1 },
        { id: 28, title: 'Urgent Follow-up (48 hrs)', description: 'Personal LO call required, manager notification', order: 7, auto_trigger: 'scheduled', days_offset: 2 },
        { id: 29, title: 'Verify TRID Complete', description: 'Confirm 3-day waiting period complete before proceeding', order: 8, auto_trigger: 'scheduled', days_offset: 3 }
      ],
      in_processing: [
        { id: 30, title: 'Assign Processor', description: 'Assign based on workload, expertise, and territory', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 31, title: 'Send Document Request', description: 'Generate comprehensive checklist: income, assets, property docs', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 32, title: 'Order Credit Report', description: 'Pull tri-merge credit report if not already done', order: 3, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 33, title: 'Order Appraisal', description: 'Submit appraisal order to AMC with property details', order: 4, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 34, title: 'Order Title Search', description: 'Request title work and insurance', order: 5, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 35, title: 'Request VOE', description: 'Send employment verification to employer', order: 6, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 36, title: 'Document Reminder (48 hrs)', description: 'Send reminder for critical missing documents', order: 7, auto_trigger: 'scheduled', days_offset: 2 },
        { id: 37, title: 'Processor Call (72 hrs)', description: 'Personal call if critical docs still missing', order: 8, auto_trigger: 'scheduled', days_offset: 3 },
        { id: 38, title: 'Review Appraisal', description: 'Analyze appraisal value, comparables, and conditions', order: 9, auto_trigger: 'on_appraisal_received', days_offset: 0 },
        { id: 39, title: 'Run AUS', description: 'Run Desktop Underwriter or Loan Product Advisor', order: 10, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 40, title: 'QC Review', description: 'Complete quality control checklist before UW submission', order: 11, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 41, title: 'Submit to Underwriting', description: 'Package file and submit to UW queue', order: 12, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      underwriting_received: [
        { id: 42, title: 'Assign Underwriter', description: 'Assign based on workload, expertise, and priority', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 43, title: 'AI Pre-Analysis', description: 'Run automated risk scoring and issue flagging', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 44, title: 'Review Credit', description: 'Verify scores, payment history, liabilities, and DTI', order: 3, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 45, title: 'Review Income', description: 'Calculate qualifying income from all sources', order: 4, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 46, title: 'Review Assets', description: 'Verify balances, source large deposits, confirm reserves', order: 5, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 47, title: 'Review Appraisal', description: 'Verify value supports loan, check property eligibility', order: 6, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 48, title: 'Validate AUS Findings', description: 'Confirm recommendations match file structure', order: 7, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 49, title: 'Issue Decision', description: 'Approve with conditions, suspend, or decline', order: 8, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 50, title: 'Generate Conditions', description: 'Create PTD and PTC conditions with assignments', order: 9, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      approved: [
        { id: 51, title: 'Send Approval Notice', description: 'Congratulate borrower with conditional approval details', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 52, title: 'Send Conditions List', description: 'Deliver clear conditions to borrower with deadlines', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 53, title: 'Track PTD Conditions', description: 'Monitor prior-to-docs condition clearance', order: 3, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 54, title: 'Condition Reminder (48 hrs)', description: 'Send reminder for conditions due soon', order: 4, auto_trigger: 'scheduled', days_offset: 2 },
        { id: 55, title: 'Urgent Reminder (24 hrs)', description: 'Urgent outreach for critical conditions', order: 5, auto_trigger: 'scheduled', days_offset: 1 },
        { id: 56, title: 'Clear Conditions', description: 'Review and clear each condition as received', order: 6, auto_trigger: 'on_document_received', days_offset: 0 },
        { id: 57, title: 'Prepare Closing Disclosure', description: 'Generate CD once all PTD conditions cleared', order: 7, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 58, title: 'Send CD to Borrower', description: 'Deliver CD and start 3-day TRID waiting period', order: 8, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 59, title: 'Check Rate Lock', description: 'Verify rate lock status and expiration', order: 9, auto_trigger: 'scheduled', days_offset: 0 }
      ],
      clear_to_close: [
        { id: 60, title: 'Send CTC Notice', description: 'Congratulate borrower - clear to close!', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 61, title: 'Confirm Closing Details', description: 'Verify date, time, location with all parties', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 62, title: 'Send Wire Instructions', description: 'Deliver secure wire instructions with fraud warning', order: 3, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 63, title: 'Final VOE (5 days out)', description: 'Re-verify employment is still active', order: 4, auto_trigger: 'scheduled', days_offset: -5 },
        { id: 64, title: 'Final Credit Check', description: 'Soft pull to ensure no new debt', order: 5, auto_trigger: 'scheduled', days_offset: -5 },
        { id: 65, title: 'Verify Insurance', description: 'Confirm policy in place with lender as mortgagee', order: 6, auto_trigger: 'scheduled', days_offset: -3 },
        { id: 66, title: 'Closing Week Reminder', description: 'Send 7-day countdown with final checklist', order: 7, auto_trigger: 'scheduled', days_offset: -7 },
        { id: 67, title: 'Day Before Reminder', description: 'Final confirmation with what to bring', order: 8, auto_trigger: 'scheduled', days_offset: -1 },
        { id: 68, title: 'Execute Closing', description: 'Complete signing, collect funds, deliver keys', order: 9, auto_trigger: 'on_closing_date', days_offset: 0 },
        { id: 69, title: 'QC Closing Package', description: 'Review signed docs for completeness', order: 10, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 70, title: 'Approve Funding', description: 'Wire funds to title/escrow', order: 11, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      suspended: [
        { id: 71, title: 'Document Suspension Reason', description: 'Select reason and enter detailed notes', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 72, title: 'Create Action Plan', description: 'Define what\'s needed, who\'s responsible, target date', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 73, title: 'Notify Borrower', description: 'Send transparent explanation with specific requirements', order: 3, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 74, title: 'Assign Resolution Owner', description: 'Assign processor, LO, or UW to resolve', order: 4, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 75, title: 'Daily Status Check', description: 'Monitor for received documents and progress', order: 5, auto_trigger: 'scheduled', days_offset: 1 },
        { id: 76, title: 'Day 3 Escalation', description: 'Manager notification if no progress', order: 6, auto_trigger: 'scheduled', days_offset: 3 },
        { id: 77, title: 'Day 7 Review', description: 'Manager meeting to assess viability', order: 7, auto_trigger: 'scheduled', days_offset: 7 },
        { id: 78, title: 'Day 14 Decision', description: 'Executive review - resolve, extend, or decline', order: 8, auto_trigger: 'scheduled', days_offset: 14 }
      ],
      withdrawn: [
        { id: 79, title: 'Send Exit Survey', description: 'Request feedback on why they withdrew', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 80, title: 'Add to Nurture List', description: 'Future follow-up opportunity', order: 2, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      does_not_qualify: [
        { id: 81, title: 'Send DNQ Letter', description: 'Explain reasons and next steps', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 82, title: 'Refer to Resources', description: 'Credit repair/savings tips', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 83, title: 'Schedule Follow-up', description: 'Check back in 6 months', order: 3, auto_trigger: 'scheduled', days_offset: 180 }
      ]
    }
  },
  portfolio: {
    name: 'Portfolio',
    description: 'Post-closing servicing and retention workflow',
    color: '#B8924A',
    statuses: PORTFOLIO_STATUSES,
    defaultTasksByStatus: {
      closed_funded: [
        { id: 38, title: 'Welcome Package', description: 'Send welcome materials', order: 1, auto_trigger: 'on_portfolio_add', days_offset: 0 },
        { id: 39, title: '30-Day Check-In', description: 'First payment follow-up', order: 2, auto_trigger: 'scheduled', days_offset: 30 },
        { id: 40, title: '90-Day Review', description: 'Servicing transition check', order: 3, auto_trigger: 'scheduled', days_offset: 90 },
        { id: 41, title: 'Annual Review', description: 'Yearly financial checkup', order: 4, auto_trigger: 'annual', days_offset: 365 },
        { id: 42, title: 'Birthday Outreach', description: 'Send birthday greeting', order: 5, auto_trigger: 'birthday', days_offset: 0 },
        { id: 43, title: 'Loan Anniversary', description: 'Celebrate anniversary', order: 6, auto_trigger: 'anniversary', days_offset: 0 },
        { id: 44, title: 'Refinance Check', description: 'Review for refi opportunity', order: 7, auto_trigger: 'rate_trigger', days_offset: 0 },
        { id: 45, title: 'Referral Request', description: 'Ask for referrals', order: 8, auto_trigger: 'milestone', days_offset: 0 }
      ]
    }
  }
};

const triggerOptions = [
  { value: 'on_lead_create', label: 'On Lead Create' },
  { value: 'on_status_change', label: 'On Status Change' },
  { value: 'after_previous', label: 'After Previous Task' },
  { value: 'manual', label: 'Manual' },
  { value: 'on_conversion', label: 'On Conversion' },
  { value: 'on_conditions', label: 'On Conditions' },
  { value: 'on_closing_date', label: 'On Closing Date' },
  { value: 'on_portfolio_add', label: 'On Portfolio Add' },
  { value: 'on_appraisal_received', label: 'On Appraisal Received' },
  { value: 'on_document_received', label: 'On Document Received' },
  { value: 'scheduled', label: 'Scheduled' },
  { value: 'annual', label: 'Annual' },
  { value: 'rate_trigger', label: 'Rate Trigger' },
  { value: 'birthday', label: 'Birthday' },
  { value: 'anniversary', label: 'Anniversary' },
  { value: 'milestone', label: 'Milestone' }
];

function WorkflowStagePage() {
  const { stage } = useParams();
  const navigate = useNavigate();
  const [tasksByStatus, setTasksByStatus] = useState({});
  const [selectedStatus, setSelectedStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [editingTask, setEditingTask] = useState(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newTask, setNewTask] = useState({
    title: '',
    description: '',
    auto_trigger: 'after_previous',
    days_offset: 0
  });
  const [draggedTask, setDraggedTask] = useState(null);

  const stageConfig = STAGE_CONFIG[stage];
  const statuses = stageConfig?.statuses || {};
  const statusKeys = Object.keys(statuses);
  const tasks = selectedStatus ? (tasksByStatus[selectedStatus] || []) : [];

  useEffect(() => {
    if (!stageConfig) {
      navigate('/settings');
      return;
    }
    // Set default selected status to first one
    if (statusKeys.length > 0 && !selectedStatus) {
      setSelectedStatus(statusKeys[0]);
    }
    loadTasks();
  }, [stage, stageConfig, navigate]);

  const loadTasks = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflow-stages/${stage}`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setTasksByStatus(data.tasksByStatus || stageConfig.defaultTasksByStatus);
      } else {
        setTasksByStatus(stageConfig.defaultTasksByStatus);
      }
    } catch (error) {
      console.error('Error loading tasks:', error);
      setTasksByStatus(stageConfig.defaultTasksByStatus);
    } finally {
      setLoading(false);
    }
  };

  const handleAddTask = () => {
    if (!newTask.title.trim() || !selectedStatus) return;

    const allTasks = Object.values(tasksByStatus).flat();
    const maxId = Math.max(...allTasks.map(t => t.id), 0);
    const currentTasks = tasksByStatus[selectedStatus] || [];
    const newTaskObj = {
      id: maxId + 1,
      title: newTask.title,
      description: newTask.description,
      order: currentTasks.length + 1,
      auto_trigger: newTask.auto_trigger,
      days_offset: parseInt(newTask.days_offset) || 0
    };

    setTasksByStatus({
      ...tasksByStatus,
      [selectedStatus]: [...currentTasks, newTaskObj]
    });
    setNewTask({ title: '', description: '', auto_trigger: 'after_previous', days_offset: 0 });
    setShowAddForm(false);
    setMessage({ type: 'success', text: 'Task added successfully' });
    setTimeout(() => setMessage({ type: '', text: '' }), 3000);
  };

  const handleDeleteTask = (taskId) => {
    if (!selectedStatus) return;
    const updatedTasks = tasks
      .filter(t => t.id !== taskId)
      .map((t, idx) => ({ ...t, order: idx + 1 }));

    setTasksByStatus({
      ...tasksByStatus,
      [selectedStatus]: updatedTasks
    });
    setMessage({ type: 'success', text: 'Task deleted' });
    setTimeout(() => setMessage({ type: '', text: '' }), 3000);
  };

  const handleMoveTask = (taskId, direction) => {
    if (!selectedStatus) return;
    const taskIndex = tasks.findIndex(t => t.id === taskId);
    if (
      (direction === 'up' && taskIndex === 0) ||
      (direction === 'down' && taskIndex === tasks.length - 1)
    ) return;

    const newTasks = [...tasks];
    const swapIndex = direction === 'up' ? taskIndex - 1 : taskIndex + 1;
    [newTasks[taskIndex], newTasks[swapIndex]] = [newTasks[swapIndex], newTasks[taskIndex]];

    const reorderedTasks = newTasks.map((t, idx) => ({ ...t, order: idx + 1 }));
    setTasksByStatus({
      ...tasksByStatus,
      [selectedStatus]: reorderedTasks
    });
  };

  const handleEditTask = (taskId, field, value) => {
    if (!selectedStatus) return;
    const updatedTasks = tasks.map(t =>
      t.id === taskId ? { ...t, [field]: value } : t
    );
    setTasksByStatus({
      ...tasksByStatus,
      [selectedStatus]: updatedTasks
    });
  };

  // Drag and drop handlers
  const handleDragStart = (e, task) => {
    setDraggedTask(task);
    e.dataTransfer.effectAllowed = 'move';
    e.target.style.opacity = '0.5';
  };

  const handleDragEnd = (e) => {
    e.target.style.opacity = '1';
    setDraggedTask(null);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = (e, targetTask) => {
    e.preventDefault();
    if (!draggedTask || !selectedStatus || draggedTask.id === targetTask.id) return;

    const currentTasks = [...tasks];
    const draggedIndex = currentTasks.findIndex(t => t.id === draggedTask.id);
    const targetIndex = currentTasks.findIndex(t => t.id === targetTask.id);

    // Remove dragged task and insert at target position
    currentTasks.splice(draggedIndex, 1);
    currentTasks.splice(targetIndex, 0, draggedTask);

    // Update order numbers
    const reorderedTasks = currentTasks.map((t, idx) => ({ ...t, order: idx + 1 }));

    setTasksByStatus({
      ...tasksByStatus,
      [selectedStatus]: reorderedTasks
    });
    setDraggedTask(null);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflow-stages/${stage}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ tasksByStatus })
      });

      if (response.ok) {
        setMessage({ type: 'success', text: `${stageConfig.name} workflow saved successfully!` });
      } else {
        setMessage({ type: 'error', text: 'Failed to save workflow' });
      }
    } catch (error) {
      console.error('Error saving workflow:', error);
      setMessage({ type: 'error', text: 'Error saving workflow' });
    } finally {
      setSaving(false);
      setTimeout(() => setMessage({ type: '', text: '' }), 3000);
    }
  };

  // Calculate total tasks across all statuses
  const totalTasks = Object.values(tasksByStatus).flat().length;

  if (!stageConfig) {
    return null;
  }

  if (loading) {
    return (
      <div className="workflow-stage-page">
        <div className="loading-state">Loading workflow tasks...</div>
      </div>
    );
  }

  return (
    <div className="workflow-stage-page">
      <div className="stage-page-header" style={{ '--stage-color': stageConfig.color }}>
        <button className="back-button" onClick={() => navigate(-1)}>
          ← Back to Workflow Management
        </button>
        <div className="header-content">
          <h1>{stageConfig.name} Workflow</h1>
          <p>{stageConfig.description}</p>
          <span className="task-count">{totalTasks} tasks total</span>
        </div>
      </div>

      {message.text && (
        <div className={`message-banner ${message.type}`}>
          {message.text}
          <button onClick={() => setMessage({ type: '', text: '' })} className="close-btn">×</button>
        </div>
      )}

      {/* Status Tabs */}
      <div className="status-tabs">
        {statusKeys.map(statusKey => (
          <button
            key={statusKey}
            className={`status-tab ${selectedStatus === statusKey ? 'active' : ''}`}
            onClick={() => setSelectedStatus(statusKey)}
            style={{ '--status-color': statuses[statusKey].color }}
          >
            <span className="status-name">{statuses[statusKey].name}</span>
            <span className="status-task-count">{(tasksByStatus[statusKey] || []).length}</span>
          </button>
        ))}
      </div>

      <div className="tasks-container" style={{ '--stage-color': selectedStatus ? statuses[selectedStatus]?.color : stageConfig.color }}>
        <div className="tasks-header">
          <h2>{selectedStatus ? statuses[selectedStatus]?.name : ''} Tasks</h2>
          <div className="header-actions">
            <button className="add-task-btn" onClick={() => setShowAddForm(true)}>
              + Add Task
            </button>
            <button
              className="save-workflow-btn"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save All'}
            </button>
          </div>
        </div>

        <div className="tasks-grid">
          {tasks.map((task, idx) => (
            <div
              key={task.id}
              className={`task-card ${editingTask === task.id ? 'editing' : ''} ${draggedTask?.id === task.id ? 'dragging' : ''}`}
              draggable={editingTask !== task.id}
              onDragStart={(e) => handleDragStart(e, task)}
              onDragEnd={handleDragEnd}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, task)}
              onClick={() => editingTask !== task.id && setEditingTask(task.id)}
            >
              <div className="task-card-header">
                <button
                  className="move-btn"
                  onClick={(e) => { e.stopPropagation(); handleMoveTask(task.id, 'up'); }}
                  disabled={idx === 0}
                >
                  ▲
                </button>
                <span className="order-number">{task.order}</span>
                <button
                  className="move-btn"
                  onClick={(e) => { e.stopPropagation(); handleMoveTask(task.id, 'down'); }}
                  disabled={idx === tasks.length - 1}
                >
                  ▼
                </button>
              </div>

              {editingTask === task.id ? (
                <div className="task-edit-form expanded" onClick={(e) => e.stopPropagation()}>
                  <div className="edit-form-group">
                    <label>Owner</label>
                    <select
                      value={task.owner || ''}
                      onChange={(e) => handleEditTask(task.id, 'owner', e.target.value)}
                    >
                      <option value="">Select Owner</option>
                      <option value="loan_officer">Loan Officer</option>
                      <option value="processor">Processor</option>
                      <option value="underwriter">Underwriter</option>
                      <option value="closer">Closer</option>
                      <option value="system">System (Auto)</option>
                    </select>
                  </div>
                  <div className="edit-form-group">
                    <label>Task Name</label>
                    <input
                      type="text"
                      value={task.title}
                      onChange={(e) => handleEditTask(task.id, 'title', e.target.value)}
                      placeholder="Task title"
                    />
                  </div>
                  <div className="edit-form-group">
                    <label>Description</label>
                    <textarea
                      value={task.description}
                      onChange={(e) => handleEditTask(task.id, 'description', e.target.value)}
                      placeholder="Detailed description of the task..."
                      rows={4}
                    />
                  </div>
                  <div className="edit-form-group">
                    <label>Activation Trigger</label>
                    <select
                      value={task.auto_trigger}
                      onChange={(e) => handleEditTask(task.id, 'auto_trigger', e.target.value)}
                    >
                      {triggerOptions.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="edit-form-row">
                    <div className="edit-form-group">
                      <label>Days Offset</label>
                      <input
                        type="number"
                        value={task.days_offset}
                        onChange={(e) => handleEditTask(task.id, 'days_offset', parseInt(e.target.value) || 0)}
                        min="0"
                        placeholder="0"
                      />
                    </div>
                    <div className="edit-form-group">
                      <label>Time of Day</label>
                      <select
                        value={task.activation_time || '09:00'}
                        onChange={(e) => handleEditTask(task.id, 'activation_time', e.target.value)}
                      >
                        <option value="08:00">8:00 AM</option>
                        <option value="09:00">9:00 AM</option>
                        <option value="10:00">10:00 AM</option>
                        <option value="11:00">11:00 AM</option>
                        <option value="12:00">12:00 PM</option>
                        <option value="13:00">1:00 PM</option>
                        <option value="14:00">2:00 PM</option>
                        <option value="15:00">3:00 PM</option>
                        <option value="16:00">4:00 PM</option>
                        <option value="17:00">5:00 PM</option>
                      </select>
                    </div>
                  </div>
                  <div className="edit-form-actions">
                    <button
                      className="delete-task-btn"
                      onClick={() => handleDeleteTask(task.id)}
                    >
                      Delete
                    </button>
                    <button className="done-edit-btn" onClick={() => setEditingTask(null)}>
                      Done
                    </button>
                  </div>
                </div>
              ) : (
                <div className="task-card-title">
                  {task.title}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Add Task Modal */}
        {showAddForm && (
          <div className="modal-overlay" onClick={() => setShowAddForm(false)}>
            <div className="add-task-modal" onClick={e => e.stopPropagation()}>
              <div className="modal-header">
                <h3>Add New Task</h3>
                <button className="close-modal" onClick={() => setShowAddForm(false)}>×</button>
              </div>
              <div className="modal-body">
                <div className="form-group">
                  <label>Title *</label>
                  <input
                    type="text"
                    value={newTask.title}
                    onChange={(e) => setNewTask(prev => ({ ...prev, title: e.target.value }))}
                    placeholder="Task title"
                    autoFocus
                  />
                </div>
                <div className="form-group">
                  <label>Description</label>
                  <textarea
                    value={newTask.description}
                    onChange={(e) => setNewTask(prev => ({ ...prev, description: e.target.value }))}
                    placeholder="Task description"
                    rows={3}
                  />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Trigger</label>
                    <select
                      value={newTask.auto_trigger}
                      onChange={(e) => setNewTask(prev => ({ ...prev, auto_trigger: e.target.value }))}
                    >
                      {triggerOptions.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Days Offset</label>
                    <input
                      type="number"
                      value={newTask.days_offset}
                      onChange={(e) => setNewTask(prev => ({ ...prev, days_offset: e.target.value }))}
                      min="0"
                    />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button className="cancel-btn" onClick={() => setShowAddForm(false)}>Cancel</button>
                <button
                  className="add-btn"
                  onClick={handleAddTask}
                  disabled={!newTask.title.trim()}
                >
                  Add Task
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default WorkflowStagePage;
