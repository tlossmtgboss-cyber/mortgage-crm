import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { teamAPI, tasksAPI, reconciliationAPI, leadsAPI, loansAPI, API_BASE_URL } from '../services/api';
import { useLayoutFix } from '../hooks/useLayoutFix';
import ReconciliationDetailPanel from '../components/shared/ReconciliationDetailPanel';
import CallDetailPanel from '../components/shared/CallDetailPanel';
import TasksSkeleton from '../components/shared/TasksSkeleton';
import { TASK_EVENTS, emitTaskCompleted, subscribeToTaskEvent } from '../utils/taskEvents';
import { getAuthHeaders } from '../utils/auth';
import './Tasks.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || '';

const LEAD_STAGES = [
  { value: 'New', label: 'New', color: '#B8924A' },
  { value: 'Attempted Contact', label: 'Attempted Contact', color: '#B8924A' },
  { value: 'Prospect', label: 'Prospect', color: '#06b6d4' },
  { value: 'Pre-Qualified', label: 'Pre-Qualified', color: '#0ea5e9' },
  { value: 'Pre-Approved', label: 'Pre-Approved', color: '#2D7A52' },
  { value: 'Application', label: 'Application', color: '#f59e0b' },
  { value: 'Document Fulfillment', label: 'Document Fulfillment', color: '#f97316' },
  { value: 'Under Contract', label: 'Under Contract', color: '#22c55e' },
  { value: 'Funded', label: 'Funded', color: '#16a34a' },
  { value: 'Does Not Qualify', label: 'Does Not Qualify', color: '#ef4444' },
  { value: 'Withdrawn', label: 'Withdrawn', color: '#6b7280' },
  { value: 'Long-Term Nurture', label: 'Long-Term Nurture', color: '#6b7280' }
];

const PRIORITY_COLORS = {
  urgent: '#ef4444',
  critical: '#dc2626',
  high: '#f59e0b',
  medium: '#3b82f6',
  normal: '#22c55e',
  low: '#9ca3af',
};

const CATEGORY_COLORS = {
  scheduling: { bg: '#e0f2fe', text: '#0369a1' },
  question: { bg: '#fef3c7', text: '#92400e' },
  document_request: { bg: '#FAF3E5', text: '#8A6D30' },
  status_update: { bg: '#d1fae5', text: '#065f46' },
  rate_inquiry: { bg: '#fce7f3', text: '#9d174d' },
  general: { bg: '#f3f4f6', text: '#374151' },
};

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

const mockLoanIssues = () => [];
const mockMumAlerts = () => [];
const mockLeadMetrics = () => ({ new_today: 0, avg_contact_time: 0, conversion_rate: 0, hot_leads: 0, alerts: [] });

// Fetch workflow + manual tasks
const fetchTasksData = async () => {
  const token = getToken();
  const workflowResponse = await fetch(`${API_BASE_URL}/api/v1/workflow-config/all-workflow-tasks?days_ahead=14`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });

  let workflowTasks = [];
  if (workflowResponse.ok) {
    const workflowData = await workflowResponse.json();
    workflowTasks = (workflowData.tasks || []).map(task => ({
      id: task.id,
      title: task.title,
      borrower: task.client_name || 'Client',
      stage: task.stage,
      urgency: task.urgency || 'medium',
      ai_action: null,
      owner: 'Loan Officer',
      date_created: task.due_date,
      due_date: task.due_date,
      preferred_contact_method: task.communication_methods?.includes('phone') ? 'Phone'
        : task.communication_methods?.includes('text') ? 'Text' : 'Email',
      ai_message: `${task.description}\n\nWorkflow: ${task.workflow_name}\nDays until due: ${task.days_until_due}`,
      description: task.description,
      source: 'Workflow',
      taskType: 'workflow',
      entity_type: task.client_type,
      entity_id: task.client_id,
      lead_id: task.client_type === 'lead' ? task.client_id : null,
      loan_id: task.client_type === 'loan' ? task.client_id : null,
      workflow_name: task.workflow_name,
      workflow_color: task.workflow_color,
      communication_methods: task.communication_methods || [],
      days_until_due: task.days_until_due,
      communication_history: []
    }));
  }

  const response = await tasksAPI.getUnified();
  const unifiedTasks = response?.tasks || [];
  const transformedTasks = unifiedTasks.map(task => ({
    id: `${task.source}-${task.id}`,
    title: task.title,
    borrower: task.client_name || 'Client',
    stage: task.stage || task.source,
    urgency: task.priority === 'urgent' ? 'critical' : task.priority || 'medium',
    ai_action: task.ai_suggested_response ? 'AI has a suggested action — approve?' : null,
    owner: task.owner || 'Loan Officer',
    date_created: task.created_at,
    due_date: task.due_date,
    preferred_contact_method: 'Email',
    ai_message: task.ai_suggested_response || `Complete task: ${task.title}`,
    ai_confidence: task.ai_confidence,
    description: task.description,
    source: task.source === 'reconciliation' ? 'AI Engine'
          : task.source === 'workflow' ? 'Workflow'
          : task.source === 'task' ? 'Manual'
          : task.source,
    taskType: 'workflow',
    entity_type: task.entity_type,
    entity_id: task.entity_id,
    email_from: task.email_from,
    email_subject: task.email_subject,
    communication_history: [],
    sla_milestone_id: task.sla_milestone_id,
    sla_milestone_type: task.sla_milestone_type,
    sla_date_field: task.sla_date_field,
    related_type: task.related_type
  }));

  const manualAndUnifiedWorkflowTasks = transformedTasks.filter(t =>
    (t.source === 'Manual' || t.source === 'Workflow') &&
    !t.email_from &&
    !t.email_subject
  );

  const nonPhoneWorkflowTasks = workflowTasks.filter(task =>
    task.preferred_contact_method !== 'Phone'
  );
  const phoneWorkflowTasks = workflowTasks.filter(task =>
    task.preferred_contact_method === 'Phone'
  );

  const allTasks = [...nonPhoneWorkflowTasks, ...manualAndUnifiedWorkflowTasks];
  const seen = new Set();
  const deduplicatedTasks = allTasks.filter(task => {
    if (seen.has(task.id)) return false;
    seen.add(task.id);
    return true;
  });

  return {
    prioritizedTasks: deduplicatedTasks,
    phoneTasks: phoneWorkflowTasks,
    loanIssues: mockLoanIssues(),
    mumAlerts: mockMumAlerts(),
    leadMetrics: mockLeadMetrics(),
  };
};

// Fetch SMS tasks
const fetchSMSTasks = async () => {
  const token = getToken();
  const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks?limit=50&status=pending`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  if (!res.ok) return [];
  const data = await res.json();
  const tasks = Array.isArray(data) ? data : (data.tasks || data.items || []);
  return tasks.map(t => ({
    ...t,
    taskType: 'sms',
    title: `SMS: ${(t.category || 'general').replace(/_/g, ' ')}`,
    borrower: t.resolved_contact_name || t.contact_name || [t.lead_first_name, t.lead_last_name].filter(Boolean).join(' ') || 'Unknown',
  }));
};

// Fetch reconciliation items
const fetchReconciliationItems = async () => {
  const token = getToken();
  const res = await fetch(`${API_BASE_URL}/api/v1/reconciliation/pending`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  if (!res.ok) return [];
  const data = await res.json();
  const items = Array.isArray(data) ? data : (data.items || []);
  return items.map(item => ({
    ...item,
    taskType: 'reconciliation',
    title: item.email_subject || item.email?.subject || '(No Subject)',
    borrower: item.email_from || item.email?.sender || 'Unknown',
    subject: item.email_subject || item.email?.subject,
    from_email: item.email_from || item.email?.sender,
    from_name: item.email_from || item.email?.sender,
    sent_date: item.email_received_at || item.email?.received_at || item.created_at,
    body_preview: item.email_body || item.email?.body,
    body: item.email_body || item.email?.body,
    matched_loan_id: item.match_entity_type === 'loan' ? item.match_entity_id : null,
    matched_lead_id: item.match_entity_type === 'lead' ? item.match_entity_id : null,
  }));
};

function Tasks() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Unified data fetching
  const { data: tasksData, isLoading: tasksLoading, refetch: refetchTasks } = useQuery({
    queryKey: ['tasks'],
    queryFn: fetchTasksData,
    staleTime: 1000 * 60 * 2,
  });

  const { data: smsTasks = [], isLoading: smsLoading, refetch: refetchSMS } = useQuery({
    queryKey: ['smsTasks', 'pending'],
    queryFn: fetchSMSTasks,
    staleTime: 1000 * 60 * 2,
    refetchOnMount: 'always',
  });

  const { data: reconItems = [], isLoading: reconLoading, refetch: refetchRecon } = useQuery({
    queryKey: ['reconciliation'],
    queryFn: fetchReconciliationItems,
    staleTime: 1000 * 60 * 2,
    refetchOnMount: 'always',
  });

  const loading = tasksLoading || smsLoading || reconLoading;

  const prioritizedTasks = tasksData?.prioritizedTasks || [];
  const phoneTasks_raw = tasksData?.phoneTasks || [];
  const loanIssues = tasksData?.loanIssues || [];
  const mumAlerts = tasksData?.mumAlerts || [];
  const leadMetrics = tasksData?.leadMetrics || {};

  const [completedTasks, setCompletedTasks] = useState(() => {
    const saved = localStorage.getItem('completedTasks');
    return saved ? new Set(JSON.parse(saved)) : new Set();
  });
  const [activeFilter, setActiveFilter] = useState('all');
  const [selectedItem, setSelectedItem] = useState(null);
  const [commModal, setCommModal] = useState(null);
  const [snoozedTasks, setSnoozedTasks] = useState(new Set());
  const [teamMembers, setTeamMembers] = useState([]);
  const [selectedTaskIds, setSelectedTaskIds] = useState(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [completingTask, setCompletingTask] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);
  const [showDelegateDropdown, setShowDelegateDropdown] = useState(false);

  // SMS detail state
  const [smsTaskDetail, setSmsTaskDetail] = useState(null);
  const [smsDetailLoading, setSmsDetailLoading] = useState(false);
  const [smsResponseMode, setSmsResponseMode] = useState(null);
  const [smsEditText, setSmsEditText] = useState('');
  const [smsSending, setSmsSending] = useState(false);
  const [smsCoachOpen, setSmsCoachOpen] = useState(false);
  const [smsCoachText, setSmsCoachText] = useState('');
  const [smsCoaching, setSmsCoaching] = useState(false);

  // Reconciliation detail state
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [showDispositionDialog, setShowDispositionDialog] = useState(false);
  const [dispositionEmail, setDispositionEmail] = useState(null);
  const [selectedDisposition, setSelectedDisposition] = useState('');
  const [createTask, setCreateTask] = useState(false);
  const [taskTitle, setTaskTitle] = useState('');
  const [processingEmailId, setProcessingEmailId] = useState(null);

  // Phone tab state
  const [phoneTasksList, setPhoneTasksList] = useState([]);
  const [selectedPhoneTask, setSelectedPhoneTask] = useState(null);
  const [callStatus, setCallStatus] = useState('idle');
  const [selectedPhoneTaskIds, setSelectedPhoneTaskIds] = useState([]);
  const [powerDialActive, setPowerDialActive] = useState(false);
  const [powerDialIndex, setPowerDialIndex] = useState(0);
  const [powerDialQueue, setPowerDialQueue] = useState([]);

  const { containerRef } = useLayoutFix([loading]);

  useEffect(() => {
    localStorage.setItem('completedTasks', JSON.stringify([...completedTasks]));
  }, [completedTasks]);

  // Disposition options
  const dispositionOptions = [
    { value: 'document_received', label: 'Document Received', icon: '📄' },
    { value: 'document_request', label: 'Document Request', icon: '📋' },
    { value: 'action_required', label: 'Action Required', icon: '⚡' },
    { value: 'general_correspondence', label: 'General Correspondence', icon: '💬' },
    { value: 'status_update', label: 'Status Update', icon: '📊' },
    { value: 'rate_lock_request', label: 'Rate Lock Request', icon: '🔒' },
    { value: 'closing_related', label: 'Closing Related', icon: '🏠' },
    { value: 'skip', label: 'Skip/Archive', icon: '⏭️' }
  ];

  // Load team members and subscribe to events
  useEffect(() => {
    loadTeamMembers();
    const unsubscribeCompleted = subscribeToTaskEvent(TASK_EVENTS.TASK_COMPLETED, (detail) => {
      if (detail.source !== 'tasks-page') {
        setCompletedTasks(prev => new Set([...prev, detail.taskId]));
        refetchTasks();
      }
    });
    const unsubscribeRefresh = subscribeToTaskEvent(TASK_EVENTS.TASKS_REFRESH, (detail) => {
      if (detail.source !== 'tasks-page') {
        refetchTasks();
        refetchSMS();
        refetchRecon();
      }
    });
    return () => { unsubscribeCompleted(); unsubscribeRefresh(); };
  }, []);

  // Load phone data
  useEffect(() => {
    if (activeFilter === 'phone') {
      loadPhoneData();
    }
  }, [activeFilter]);

  // Sync phone tasks from workflow data
  useEffect(() => {
    if (phoneTasks_raw.length > 0) {
      setPhoneTasksList(phoneTasks_raw);
    }
  }, [phoneTasks_raw]);

  useEffect(() => {
    setShowStatusDropdown(false);
    setShowDelegateDropdown(false);
  }, [selectedItem?.id]);

  // Auto-select first item when filter changes
  useEffect(() => {
    if (!loading && activeFilter !== 'phone') {
      const items = getFilteredItems();
      if (items.length > 0 && (!selectedItem || !items.find(i => i.id === selectedItem.id))) {
        setSelectedItem(items[0]);
      } else if (items.length === 0) {
        setSelectedItem(null);
      }
    }
  }, [loading, activeFilter, prioritizedTasks, smsTasks, reconItems]);

  useEffect(() => {
    if (!loading) {
      const timer = setTimeout(() => window.dispatchEvent(new Event('resize')), 100);
      return () => clearTimeout(timer);
    }
  }, [loading, activeFilter, selectedItem]);

  // Fetch SMS task detail when an SMS item is selected
  useEffect(() => {
    if (selectedItem?.taskType === 'sms' && selectedItem.id) {
      fetchSmsDetail(selectedItem.id);
    } else {
      setSmsTaskDetail(null);
      setSmsResponseMode(null);
      setSmsEditText('');
    }
    setSmsCoachOpen(false);
    setSmsCoachText('');
  }, [selectedItem?.id, selectedItem?.taskType]);

  const fetchSmsDetail = async (taskId) => {
    setSmsDetailLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks/${taskId}`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        setSmsTaskDetail(data);
      }
    } catch (err) {
      console.error('Error fetching SMS task detail:', err);
    } finally {
      setSmsDetailLoading(false);
    }
  };

  // =============================================
  // Build unified item list
  // =============================================
  const getAllItems = useCallback(() => {
    const items = [];
    const addedIds = new Set();

    // Workflow tasks
    prioritizedTasks.forEach((task, idx) => {
      const taskId = task.id || `priority-${idx}`;
      if (task.source === 'AI Engine' || task.email_from || task.email_subject) return;
      if (!completedTasks.has(taskId) && !addedIds.has(taskId) && !snoozedTasks.has(taskId)) {
        addedIds.add(taskId);
        let sourceIcon = '⚡';
        if (task.source === 'Manual') sourceIcon = '🎯';
        items.push({ ...task, id: taskId, taskType: 'workflow', source: task.source || 'Workflow', sourceIcon });
      }
    });

    // Loan issues
    loanIssues.forEach((issue, idx) => {
      const taskId = `issue-${idx}`;
      if (!completedTasks.has(taskId) && !addedIds.has(taskId)) {
        addedIds.add(taskId);
        items.push({ id: taskId, ...issue, title: issue.issue, stage: 'Milestone Alert', urgency: 'critical', source: 'Milestone Risk', taskType: 'workflow', sourceIcon: '🔥' });
      }
    });

    // MUM alerts
    mumAlerts.forEach((alert, idx) => {
      const taskId = `mum-${idx}`;
      if (!completedTasks.has(taskId) && !addedIds.has(taskId)) {
        addedIds.add(taskId);
        items.push({ id: taskId, ...alert, borrower: alert.client, stage: 'Client Retention', urgency: alert.urgency || 'medium', source: 'Client for Life', taskType: 'workflow', sourceIcon: '💎' });
      }
    });

    // Lead alerts
    if (leadMetrics.alerts) {
      leadMetrics.alerts.forEach((alert, idx) => {
        const taskId = `lead-${idx}`;
        if (alert && !completedTasks.has(taskId) && !addedIds.has(taskId)) {
          addedIds.add(taskId);
          items.push({ id: taskId, title: alert, borrower: '', stage: 'Leads', urgency: 'high', source: 'Leads Engine', taskType: 'workflow', sourceIcon: '🚀' });
        }
      });
    }

    // SMS tasks
    smsTasks.forEach(task => {
      if (!completedTasks.has(task.id) && !addedIds.has(task.id)) {
        addedIds.add(task.id);
        items.push(task);
      }
    });

    // Reconciliation items
    reconItems.forEach(item => {
      if (!completedTasks.has(item.id) && !addedIds.has(item.id)) {
        addedIds.add(item.id);
        items.push(item);
      }
    });

    return items;
  }, [prioritizedTasks, loanIssues, mumAlerts, leadMetrics, smsTasks, reconItems, completedTasks, snoozedTasks]);

  const getFilteredItems = useCallback(() => {
    if (activeFilter === 'completed') return getCompletedTasks();
    if (activeFilter === 'phone') return [];

    let items = getAllItems();

    if (activeFilter === 'workflow') {
      items = items.filter(i => i.taskType === 'workflow');
    } else if (activeFilter === 'sms') {
      items = items.filter(i => i.taskType === 'sms');
    } else if (activeFilter === 'reconciliation') {
      items = items.filter(i => i.taskType === 'reconciliation');
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      items = items.filter(i =>
        (i.title || '').toLowerCase().includes(q) ||
        (i.borrower || '').toLowerCase().includes(q) ||
        (i.inbound_message || '').toLowerCase().includes(q) ||
        (i.from_email || '').toLowerCase().includes(q)
      );
    }

    return items;
  }, [activeFilter, getAllItems, searchQuery]);

  const getCompletedTasks = () => {
    const tasks = [];
    prioritizedTasks.forEach((task, idx) => {
      const taskId = task.id || `priority-${idx}`;
      if (completedTasks.has(taskId)) {
        tasks.push({ ...task, id: taskId, taskType: 'workflow', source: task.source || 'Workflow', sourceIcon: '⚡' });
      }
    });
    return tasks;
  };

  // =============================================
  // Counts for filter tabs
  // =============================================
  const allItems = getAllItems();
  const workflowCount = allItems.filter(i => i.taskType === 'workflow').length;
  const smsCount = allItems.filter(i => i.taskType === 'sms').length;
  const reconCount = allItems.filter(i => i.taskType === 'reconciliation').length;
  const completedCount = getCompletedTasks().length;

  // =============================================
  // Phone dialer
  // =============================================
  const loadPhoneData = useCallback(async () => {
    try {
      const tasksResponse = await fetch(`${API_BASE}/api/v1/dialer/call-tasks`, { headers: getAuthHeaders() });
      if (tasksResponse.ok) {
        const data = await tasksResponse.json();
        setPhoneTasksList(prev => {
          const apiTasks = data.tasks || [];
          const merged = [...prev];
          apiTasks.forEach(t => { if (!merged.find(m => m.id === t.id)) merged.push(t); });
          return merged;
        });
      }
    } catch (error) {
      console.error('Error loading phone data:', error);
    }
  }, []);

  const handleClickToDial = (task) => {
    if (!task?.contact_phone) return;
    const cleanPhone = task.contact_phone.replace(/[^\d+]/g, '');
    const dialNumber = cleanPhone.startsWith('+') ? cleanPhone : `+1${cleanPhone}`;
    window.open(`https://teams.microsoft.com/l/call/0/0?users=4:${encodeURIComponent(dialNumber)}`, '_blank');
  };

  const handleEndCall = async () => {
    setCallStatus('idle');
    loadPhoneData();
  };

  const togglePhoneTaskSelection = (taskId) => {
    setSelectedPhoneTaskIds(prev => prev.includes(taskId) ? prev.filter(id => id !== taskId) : [...prev, taskId]);
  };

  const selectAllPhoneTasks = () => {
    setSelectedPhoneTaskIds(prev => prev.length === phoneTasksList.length ? [] : phoneTasksList.map(t => t.id));
  };

  const startPowerDial = () => {
    const ids = selectedPhoneTaskIds.length > 0 ? selectedPhoneTaskIds : phoneTasksList.map(t => t.id);
    const queue = phoneTasksList.filter(t => ids.includes(t.id));
    if (queue.length === 0) { toast.error('No tasks to dial'); return; }
    setPowerDialQueue(queue);
    setPowerDialIndex(0);
    setPowerDialActive(true);
    setSelectedPhoneTask(queue[0]);
    handleClickToDial(queue[0]);
  };

  const nextPowerDialContact = () => {
    const next = powerDialIndex + 1;
    if (next < powerDialQueue.length) {
      setPowerDialIndex(next);
      setSelectedPhoneTask(powerDialQueue[next]);
      handleClickToDial(powerDialQueue[next]);
    } else {
      stopPowerDial();
    }
  };

  const skipPowerDialContact = () => nextPowerDialContact();

  const stopPowerDial = () => {
    setPowerDialActive(false);
    setPowerDialQueue([]);
    setPowerDialIndex(0);
    setCallStatus('idle');
  };

  // =============================================
  // Task handlers
  // =============================================
  const loadTeamMembers = async () => {
    try {
      const data = await teamAPI.getMembers();
      setTeamMembers(Array.isArray(data) ? data : []);
    } catch (error) {
      setTeamMembers([]);
    }
  };

  const handleSend = (taskId, method, _message) => {
    toast.success(`Task sent via ${method || 'Email'}!`);
    handleComplete(taskId);
  };

  const handleDelete = async (taskId) => {
    try {
      const mockIdPatterns = ['priority-', 'issue-', 'ai-pending-', 'ai-waiting-', 'mum-', 'lead-', 'message-'];
      const isMockTask = typeof taskId === 'string' && mockIdPatterns.some(pattern => taskId.startsWith(pattern));

      if (!isMockTask && typeof taskId === 'string') {
        if (taskId.startsWith('reconciliation-')) {
          await reconciliationAPI.delete(taskId.replace('reconciliation-', ''));
        } else if (taskId.startsWith('task-')) {
          await tasksAPI.delete(taskId.replace('task-', ''));
        } else if (!taskId.startsWith('workflow-')) {
          await tasksAPI.delete(taskId);
        }
      } else if (!isMockTask && typeof taskId === 'number') {
        await tasksAPI.delete(taskId);
      }

      setCompletedTasks(prev => new Set([...prev, taskId]));
      if (selectedItem && selectedItem.id === taskId) {
        const items = getFilteredItems();
        const idx = items.findIndex(t => t.id === taskId);
        setSelectedItem(items[idx + 1] || items[idx - 1] || null);
      }
      emitTaskCompleted(taskId, 'tasks-page');
    } catch (error) {
      console.error('Error deleting task:', error);
      toast.error('Failed to delete task. Please try again.');
    }
  };

  const handleBulkDelete = async () => {
    if (selectedTaskIds.size === 0) return;
    setBulkDeleting(true);
    let successCount = 0;
    for (const taskId of selectedTaskIds) {
      try {
        const mockIdPatterns = ['priority-', 'issue-', 'ai-pending-', 'ai-waiting-', 'mum-', 'lead-', 'message-'];
        const isMockTask = typeof taskId === 'string' && mockIdPatterns.some(p => taskId.startsWith(p));
        if (!isMockTask && typeof taskId === 'string') {
          if (taskId.startsWith('reconciliation-')) await reconciliationAPI.delete(taskId.replace('reconciliation-', ''));
          else if (taskId.startsWith('task-')) await tasksAPI.delete(taskId.replace('task-', ''));
          else if (!taskId.startsWith('workflow-')) await tasksAPI.delete(taskId);
        } else if (!isMockTask && typeof taskId === 'number') {
          await tasksAPI.delete(taskId);
        }
        setCompletedTasks(prev => new Set([...prev, taskId]));
        successCount++;
      } catch (error) {
        console.error(`Failed to delete task ${taskId}:`, error);
      }
    }
    setSelectedTaskIds(new Set());
    setSelectedItem(null);
    setBulkDeleting(false);
    if (successCount > 0) toast.success(`Deleted ${successCount} task${successCount > 1 ? 's' : ''}`);
  };

  const toggleTaskSelection = (taskId, e) => {
    e.stopPropagation();
    setSelectedTaskIds(prev => {
      const s = new Set(prev);
      s.has(taskId) ? s.delete(taskId) : s.add(taskId);
      return s;
    });
  };

  const handleSelectAll = (tasks) => {
    const allSelected = tasks.every(t => selectedTaskIds.has(t.id));
    setSelectedTaskIds(prev => {
      const s = new Set(prev);
      tasks.forEach(t => allSelected ? s.delete(t.id) : s.add(t.id));
      return s;
    });
  };

  const handleSnooze = (taskId) => {
    setSnoozedTasks(prev => new Set([...prev, taskId]));
    setTimeout(() => setSnoozedTasks(prev => { const s = new Set(prev); s.delete(taskId); return s; }), 24 * 60 * 60 * 1000);
    if (selectedItem && selectedItem.id === taskId) {
      const items = getFilteredItems();
      const idx = items.findIndex(t => t.id === taskId);
      setSelectedItem(items[idx + 1] || items[idx - 1] || null);
    }
  };

  const handleDelegate = async (member) => {
    if (!selectedItem) return;
    const taskId = selectedItem.id;
    queryClient.setQueryData(['tasks'], (prev) => {
      if (!prev) return prev;
      return { ...prev, prioritizedTasks: prev.prioritizedTasks.filter(t => t.id !== taskId) };
    });
    const items = getFilteredItems();
    const idx = items.findIndex(t => t.id === taskId);
    setSelectedItem(items[idx + 1] || items[idx - 1] || null);
    try { await tasksAPI.delegate(taskId, member.id); } catch (error) { console.error('Failed to delegate:', error); }
  };

  const handleComplete = async (taskId) => {
    setCompletingTask(true);
    try {
      const mockIdPatterns = ['priority-', 'issue-', 'ai-pending-', 'ai-waiting-', 'mum-', 'lead-', 'message-'];
      const isMockTask = typeof taskId === 'string' && mockIdPatterns.some(p => taskId.startsWith(p));
      if (!isMockTask) {
        if (typeof taskId === 'string' && taskId.startsWith('task-')) {
          await tasksAPI.update(taskId.replace('task-', ''), { status: 'completed' });
        } else if (typeof taskId === 'string' && taskId.startsWith('workflow-')) {
          try { await tasksAPI.update(taskId.replace('workflow-', ''), { status: 'completed' }); } catch (e) { /* ok */ }
        } else if (typeof taskId === 'number') {
          await tasksAPI.update(taskId, { status: 'completed' });
        }
      }
      setCompletedTasks(prev => new Set([...prev, taskId]));
      if (selectedItem && selectedItem.id === taskId) {
        const items = getFilteredItems();
        const idx = items.findIndex(t => t.id === taskId);
        setSelectedItem(items[idx + 1] || items[idx - 1] || null);
      }
      emitTaskCompleted(taskId, 'tasks-page');
    } catch (error) {
      console.error('Error completing task:', error);
      setCompletedTasks(prev => new Set([...prev, taskId]));
      emitTaskCompleted(taskId, 'tasks-page');
    } finally {
      setCompletingTask(false);
    }
  };

  const handleChangeStatus = async (newStatus) => {
    if (!selectedItem) return;
    setUpdatingStatus(true);
    try {
      const leadId = selectedItem.lead_id || selectedItem.leadId;
      const loanId = selectedItem.loan_id || selectedItem.loanId;
      if (leadId) {
        await leadsAPI.update(leadId, { stage: newStatus });
        setSelectedItem(prev => ({ ...prev, stage: newStatus }));
        toast.success(`Lead status updated to "${LEAD_STAGES.find(s => s.value === newStatus)?.label || newStatus}"`);
      } else if (loanId) {
        await loansAPI.update(loanId, { stage: newStatus });
        setSelectedItem(prev => ({ ...prev, stage: newStatus }));
        toast.success(`Loan status updated to "${newStatus}"`);
      } else {
        toast.error('No lead or loan associated with this task');
      }
    } catch (error) {
      toast.error('Failed to update status. Please try again.');
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleApproveAiTask = async (taskId, method = 'email') => {
    try {
      const task = selectedItem;
      if (task && task.ai_message) {
        const sentEmails = JSON.parse(localStorage.getItem('sentEmails') || '[]');
        sentEmails.push({
          id: `email-${Date.now()}`, taskId, to: task.borrower, subject: task.title,
          body: task.ai_message, sentAt: new Date().toISOString(), sentVia: method, status: 'sent',
          loanId: task.loan_id || task.loanId || null
        });
        localStorage.setItem('sentEmails', JSON.stringify(sentEmails));
      }
      handleComplete(taskId);
      toast.success('AI action approved and sent!');
    } catch (error) {
      toast.error('Failed to approve task');
    }
  };

  // =============================================
  // SMS handlers
  // =============================================
  const handleSmsSendResponse = async (text, source) => {
    if (!text.trim() || !selectedItem?.id) return;
    setSmsSending(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks/${selectedItem.id}/respond`, {
        method: 'POST', headers: getAuthHeaders(),
        body: JSON.stringify({ response_text: text, response_source: source }),
      });
      if (!res.ok) throw new Error('Failed to send response');
      toast.success('Response sent successfully');
      setSmsResponseMode(null);
      setSmsEditText('');
      refetchSMS();
      // Move to next SMS item
      const items = getFilteredItems();
      const idx = items.findIndex(i => i.id === selectedItem.id);
      const next = items.find((i, j) => j > idx && i.taskType === 'sms');
      if (next) setSelectedItem(next);
    } catch (err) {
      toast.error('Failed to send response');
    } finally {
      setSmsSending(false);
    }
  };

  const handleSmsDismiss = async () => {
    if (!selectedItem?.id) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks/${selectedItem.id}/dismiss`, {
        method: 'POST', headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error('Failed to dismiss task');
      toast.success('Task dismissed');
      refetchSMS();
      const items = getFilteredItems();
      const idx = items.findIndex(i => i.id === selectedItem.id);
      const next = items[idx + 1] || items[idx - 1] || null;
      setSelectedItem(next);
    } catch (err) {
      toast.error('Failed to dismiss task');
    }
  };

  const handleSmsRegenerate = async (coachingOverride) => {
    if (!selectedItem?.id) return;
    const feedback = (coachingOverride !== undefined ? coachingOverride : smsCoachText).trim();
    const isCoaching = !!feedback;
    if (isCoaching) setSmsCoaching(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks/${selectedItem.id}/regenerate`, {
        method: 'POST', headers: getAuthHeaders(),
        body: JSON.stringify({ feedback: feedback || 'Please suggest a different response' }),
      });
      if (!res.ok) throw new Error('Failed to regenerate');
      const data = await res.json();
      toast.success(isCoaching ? 'AI updated with your coaching' : 'Regenerating AI response...');
      setSmsTaskDetail((prev) => prev ? {
        ...prev,
        ai_recommendation: data.recommendation ?? prev.ai_recommendation,
        ai_confidence: data.confidence ?? prev.ai_confidence,
        ai_reasoning: data.reasoning ?? prev.ai_reasoning,
        ai_acknowledgement: data.acknowledgement ?? prev.ai_acknowledgement,
        coaching_note: data.coaching_note ?? prev.coaching_note,
      } : prev);
      if (isCoaching) {
        setSmsCoachText('');
        setSmsCoachOpen(false);
      }
    } catch (err) {
      toast.error(isCoaching ? 'Failed to send coaching to AI' : 'Failed to regenerate response');
    } finally {
      setSmsCoaching(false);
    }
  };

  // =============================================
  // Reconciliation handlers
  // =============================================
  const handleOpenDisposition = (email) => {
    setDispositionEmail(email);
    setSelectedDisposition(email.ai_analysis?.disposition || '');
    setCreateTask(false);
    setTaskTitle('');
    setShowDispositionDialog(true);
  };

  const handleProcessDisposition = async () => {
    if (!dispositionEmail || !selectedDisposition) return;
    setProcessingEmailId(dispositionEmail.id);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/email-intelligence/queue/${dispositionEmail.id}/process`, {
        method: 'POST', headers: getAuthHeaders(),
        body: JSON.stringify({ disposition: selectedDisposition, create_task: createTask, task_title: createTask ? taskTitle : undefined }),
      });
      if (response.ok) {
        setShowDispositionDialog(false);
        setDispositionEmail(null);
        refetchRecon();
      }
    } catch (error) {
      console.error('Error processing disposition:', error);
    } finally {
      setProcessingEmailId(null);
    }
  };

  const getUrgencyColor = (urgency) => PRIORITY_COLORS[urgency] || '#6b7280';

  const formatEmailDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return date.toLocaleDateString([], { weekday: 'short' });
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  const urgencyLabel = (u) => {
    if (!u) return null;
    const map = { critical: 'urgent', urgent: 'urgent', high: 'high', medium: 'medium', normal: 'low', low: 'low' };
    return map[u] || 'medium';
  };

  // =============================================
  // Render helpers
  // =============================================
  if (loading) return <TasksSkeleton />;

  const filteredItems = getFilteredItems();

  const renderInboxItem = (item) => {
    const isActive = selectedItem && selectedItem.id === item.id;
    const isChecked = selectedTaskIds.has(item.id);

    if (item.taskType === 'sms') {
      return (
        <div key={item.id} className={`tasks-inbox-item${isActive ? ' active' : ''}`} onClick={() => setSelectedItem(item)}>
          <div className="tasks-type-dot sms" />
          <div className="tasks-inbox-item-content">
            <div className="tasks-inbox-item-top">
              <span className="tasks-inbox-item-title">{item.title}</span>
              <span className="tasks-inbox-item-time">{timeAgo(item.inbound_received_at || item.created_at)}</span>
            </div>
            <div className="tasks-inbox-item-sub">{item.borrower}{item.phone_number ? ` · ${item.phone_number}` : ''}</div>
            {item.inbound_message && (
              <div className="tasks-inbox-item-preview">
                "{item.inbound_message.length > 80 ? item.inbound_message.slice(0, 80) + '...' : item.inbound_message}"
              </div>
            )}
            <div className="tasks-inbox-item-tags">
              <span className="tasks-type-chip sms">SMS</span>
              {item.category && (
                <span className="tasks-type-chip" style={{
                  backgroundColor: (CATEGORY_COLORS[item.category] || CATEGORY_COLORS.general).bg,
                  color: (CATEGORY_COLORS[item.category] || CATEGORY_COLORS.general).text,
                }}>{(item.category || '').replace(/_/g, ' ')}</span>
              )}
              {item.ai_confidence > 0 && (
                <>
                  <div className="tasks-conf-bar">
                    <div className={`tasks-conf-bar-fill ${item.ai_confidence >= 85 ? 'high' : item.ai_confidence >= 65 ? 'med' : 'low'}`} style={{ width: `${item.ai_confidence}%` }} />
                  </div>
                  <span style={{ fontSize: '11px', color: '#8A6D30' }}>{item.ai_confidence}%</span>
                </>
              )}
            </div>
          </div>
        </div>
      );
    }

    if (item.taskType === 'reconciliation') {
      return (
        <div key={item.id} className={`tasks-inbox-item${isActive ? ' active' : ''}`} onClick={() => { setSelectedItem(item); setSelectedEmail(item); }}>
          <div className="tasks-type-dot recon" />
          <div className="tasks-inbox-item-content">
            <div className="tasks-inbox-item-top">
              <span className="tasks-inbox-item-title">{item.title}</span>
              <span className="tasks-inbox-item-time">{formatEmailDate(item.sent_date || item.received_at)}</span>
            </div>
            <div className="tasks-inbox-item-sub">From: {item.borrower}</div>
            <div className="tasks-inbox-item-tags">
              <span className="tasks-type-chip recon">Reconciliation</span>
              {item.matched_loan_id && <span className="tasks-badge green">Loan #{item.matched_loan_id}</span>}
              {item.matched_lead_id && <span className="tasks-badge green">Lead #{item.matched_lead_id}</span>}
            </div>
          </div>
        </div>
      );
    }

    // Workflow / manual task
    return (
      <div key={item.id} className={`tasks-inbox-item${isActive ? ' active' : ''}${isChecked ? ' checked' : ''}`} onClick={() => setSelectedItem(item)}>
        <input
          type="checkbox"
          className="tasks-inbox-item-checkbox"
          checked={isChecked}
          onChange={(e) => toggleTaskSelection(item.id, e)}
          onClick={(e) => e.stopPropagation()}
        />
        <div className="tasks-type-dot workflow" />
        <div className="tasks-inbox-item-content">
          <div className="tasks-inbox-item-top">
            <span className="tasks-inbox-item-title">{item.title}</span>
            <span className="tasks-inbox-item-time">{timeAgo(item.date_created || item.due_date)}</span>
          </div>
          <div className="tasks-inbox-item-sub">{item.borrower || item.source}</div>
          <div className="tasks-inbox-item-tags">
            <span className="tasks-type-chip workflow">{item.source || 'Workflow'}</span>
            {item.urgency && (
              <span className={`tasks-badge ${urgencyLabel(item.urgency)}`}>{(item.urgency || '').toUpperCase()}</span>
            )}
            {item.ai_confidence > 0 && (
              <span style={{ fontSize: '11px', color: '#8A6D30' }}>AI {item.ai_confidence}%</span>
            )}
          </div>
        </div>
      </div>
    );
  };

  // SMS detail panel (cream themed)
  const renderSmsDetail = () => {
    if (smsDetailLoading) {
      return (
        <div className="tasks-detail">
          <div className="tasks-empty">
            <div className="tasks-empty-icon">...</div>
            <div className="tasks-empty-title">Loading SMS details</div>
          </div>
        </div>
      );
    }
    if (!smsTaskDetail) {
      return (
        <div className="tasks-detail">
          <div className="tasks-empty">
            <div className="tasks-empty-title">Select a task to view details</div>
          </div>
        </div>
      );
    }

    const contactName = smsTaskDetail.contact_name
      || [smsTaskDetail.lead_first_name, smsTaskDetail.lead_last_name].filter(Boolean).join(' ')
      || 'Unknown Contact';

    return (
      <div className="tasks-detail">
        <div className="tasks-detail-header">
          <div>
            <span className="tasks-type-chip sms">SMS</span>
            {smsTaskDetail.priority && (
              <span className={`tasks-badge ${urgencyLabel(smsTaskDetail.priority)}`}>{(smsTaskDetail.priority || '').toUpperCase()}</span>
            )}
            <div className="tasks-detail-title">{contactName}</div>
          </div>
          {smsTaskDetail.ai_confidence > 0 && (
            <span style={{ fontSize: '13px', color: '#8A6D30' }}>AI Confidence: {smsTaskDetail.ai_confidence}%</span>
          )}
        </div>

        <div className="tasks-detail-grid">
          <div className="tasks-detail-field">
            <label>Contact</label>
            <div className="val">{contactName}</div>
          </div>
          <div className="tasks-detail-field">
            <label>Phone</label>
            <div className="val">{smsTaskDetail.phone_number || '--'}</div>
          </div>
          <div className="tasks-detail-field">
            <label>Category</label>
            <div className="val">{(smsTaskDetail.category || 'general').replace(/_/g, ' ')}</div>
          </div>
          <div className="tasks-detail-field">
            <label>Confidence</label>
            <div className="val">
              <div className="tasks-conf-bar" style={{ width: 120, display: 'inline-flex', verticalAlign: 'middle', marginRight: 6 }}>
                <div className={`tasks-conf-bar-fill ${(smsTaskDetail.ai_confidence || 0) >= 85 ? 'high' : (smsTaskDetail.ai_confidence || 0) >= 65 ? 'med' : 'low'}`} style={{ width: `${smsTaskDetail.ai_confidence || 0}%` }} />
              </div>
              {smsTaskDetail.ai_confidence || 0}%
            </div>
          </div>
          <div className="tasks-detail-field">
            <label>Received</label>
            <div className="val">{timeAgo(smsTaskDetail.inbound_received_at || smsTaskDetail.created_at)}</div>
          </div>
          <div className="tasks-detail-field">
            <label>Status</label>
            <div className="val">{smsTaskDetail.status || 'pending'}</div>
          </div>
        </div>

        {/* Inbound message */}
        <div className="tasks-detail-section">
          <h4>Inbound Message</h4>
          <div className="tasks-sms-message inbound">
            <p>{smsTaskDetail.inbound_message}</p>
            <span style={{ fontSize: '11px', opacity: 0.7, display: 'block', marginTop: 4 }}>
              {timeAgo(smsTaskDetail.inbound_received_at || smsTaskDetail.created_at)}
            </span>
          </div>
        </div>

        {/* AI recommendation */}
        {smsTaskDetail.ai_recommendation && (
          <div className="tasks-detail-section">
            <h4>AI Recommended Response</h4>
            {smsTaskDetail.ai_acknowledgement && (
              <div className="tasks-ai-ack" role="status">
                <span className="tasks-ai-ack-label">AI acknowledgement</span>
                <p>{smsTaskDetail.ai_acknowledgement}</p>
                {smsTaskDetail.coaching_note && (
                  <div className="tasks-ai-ack-coaching">
                    <span>Your coaching:</span> &ldquo;{smsTaskDetail.coaching_note}&rdquo;
                  </div>
                )}
              </div>
            )}
            <div className="tasks-sms-message ai-response">
              <p>{smsTaskDetail.ai_recommendation}</p>
            </div>
          </div>
        )}

        {/* Coach AI container */}
        {smsTaskDetail.status === 'pending' && !smsResponseMode && smsTaskDetail.ai_recommendation && (
          <div className="tasks-detail-section tasks-coach-section">
            {!smsCoachOpen ? (
              <button
                className="tasks-btn outline tasks-coach-toggle"
                onClick={() => {
                  setSmsCoachText('');
                  setSmsCoachOpen(true);
                }}
              >Coach the AI</button>
            ) : (
              <div className="tasks-coach-box">
                <div className="tasks-coach-header">
                  <h4>Coach the AI</h4>
                  <span className="tasks-coach-hint">
                    Tell the AI what to change, or rewrite the response below. The AI will rewrite and acknowledge what changed.
                  </span>
                </div>
                <textarea
                  className="tasks-sms-textarea"
                  value={smsCoachText}
                  onChange={(e) => setSmsCoachText(e.target.value)}
                  placeholder={'e.g. "Be more concise, and don\'t promise turnaround times."\nOr paste your preferred rewrite for the AI to learn from.'}
                  rows={4}
                  autoFocus
                />
                <div className="tasks-actions" style={{ marginTop: 8 }}>
                  <button
                    className="tasks-btn primary"
                    onClick={() => handleSmsRegenerate()}
                    disabled={!smsCoachText.trim() || smsCoaching}
                  >{smsCoaching ? 'Coaching AI...' : 'Send Coaching to AI'}</button>
                  <button
                    className="tasks-btn outline"
                    onClick={() => {
                      setSmsCoachOpen(false);
                      setSmsCoachText('');
                    }}
                    disabled={smsCoaching}
                  >Cancel</button>
                  <button
                    className="tasks-btn outline"
                    style={{ marginLeft: 'auto' }}
                    onClick={() => {
                      const current = smsTaskDetail.ai_recommendation || '';
                      setSmsCoachText((prev) => prev.trim() ? prev : current);
                    }}
                    disabled={smsCoaching}
                    title="Load the current AI response into the textarea so you can rewrite it"
                  >Load current response</button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Actions for pending */}
        {smsTaskDetail.status === 'pending' && !smsResponseMode && (
          <div className="tasks-actions">
            <button
              className="tasks-btn primary"
              onClick={() => handleSmsSendResponse(smsTaskDetail.ai_recommendation, 'ai')}
              disabled={!smsTaskDetail.ai_recommendation || smsSending}
            >{smsSending ? 'Sending...' : 'Send Response'}</button>
            <button className="tasks-btn accent" onClick={() => { setSmsResponseMode('edit'); setSmsEditText(smsTaskDetail.ai_recommendation || ''); }}>Edit</button>
            <button className="tasks-btn outline" onClick={() => { setSmsResponseMode('write'); setSmsEditText(''); }}>Write Own</button>
            <button className="tasks-btn danger" onClick={handleSmsDismiss}>Dismiss</button>
            <button className="tasks-btn outline" onClick={() => handleSmsRegenerate('')}>Regenerate</button>
          </div>
        )}

        {/* Edit/Write textarea */}
        {smsResponseMode && (
          <div className="tasks-detail-section">
            <textarea
              className="tasks-sms-textarea"
              value={smsEditText}
              onChange={(e) => setSmsEditText(e.target.value)}
              placeholder={smsResponseMode === 'edit' ? 'Edit the AI response...' : 'Write your response...'}
              rows={4}
              autoFocus
            />
            <div className="tasks-actions" style={{ marginTop: 8 }}>
              <button
                className="tasks-btn primary"
                onClick={() => handleSmsSendResponse(smsEditText, smsResponseMode === 'edit' ? 'ai_edited' : 'manual')}
                disabled={!smsEditText.trim() || smsSending}
              >{smsSending ? 'Sending...' : 'Send'}</button>
              <button className="tasks-btn outline" onClick={() => { setSmsResponseMode(null); setSmsEditText(''); }}>Cancel</button>
            </div>
          </div>
        )}

        {/* Already sent */}
        {smsTaskDetail.status !== 'pending' && (
          <div className="tasks-detail-section">
            <h4>Response Sent</h4>
            <div className="tasks-sms-message ai-response">
              <p>{smsTaskDetail.response_text || 'No response recorded'}</p>
              <span style={{ fontSize: '11px', opacity: 0.7, display: 'block', marginTop: 4 }}>
                via {(smsTaskDetail.response_source || 'unknown').replace(/_/g, ' ')}
              </span>
            </div>
          </div>
        )}
      </div>
    );
  };

  // Phone tab layout (cream themed)
  const renderPhoneLayout = () => (
    <div className="tasks-inbox">
      <div className="tasks-inbox-list">
        <div className="tasks-inbox-search" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <button className="tasks-btn outline" onClick={selectAllPhoneTasks} style={{ fontSize: 12, padding: '4px 10px' }}>
            {selectedPhoneTaskIds.length === phoneTasksList.length ? 'Deselect All' : 'Select All'}
          </button>
          {!powerDialActive ? (
            <button className="tasks-btn primary" onClick={startPowerDial} disabled={phoneTasksList.length === 0} style={{ fontSize: 12, padding: '4px 10px' }}>
              Power Dial {selectedPhoneTaskIds.length > 0 ? `(${selectedPhoneTaskIds.length})` : 'All'}
            </button>
          ) : (
            <button className="tasks-btn danger" onClick={stopPowerDial} style={{ fontSize: 12, padding: '4px 10px' }}>Stop Dialing</button>
          )}
          <span style={{ fontSize: 12, color: '#8A6D30', marginLeft: 'auto' }}>{phoneTasksList.length} call tasks</span>
        </div>
        {powerDialActive && (
          <div style={{ padding: '8px 16px', background: '#FAF3E5', borderBottom: '1px solid #E8DCC8', fontSize: 13 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span>Power Dialing: {powerDialIndex + 1} of {powerDialQueue.length}</span>
              <span style={{ color: '#8A6D30' }}>{powerDialQueue[powerDialIndex]?.contact_name}</span>
            </div>
            <div style={{ height: 4, background: '#E8DCC8', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${((powerDialIndex + 1) / powerDialQueue.length) * 100}%`, background: '#B8924A', borderRadius: 2, transition: 'width 0.3s' }} />
            </div>
          </div>
        )}
        <div className="tasks-inbox-items">
          {phoneTasksList.map((task) => (
            <div key={task.id} className={`tasks-inbox-item${selectedPhoneTask?.id === task.id ? ' active' : ''}`} onClick={() => setSelectedPhoneTask(task)}>
              <input
                type="checkbox"
                className="tasks-inbox-item-checkbox"
                checked={selectedPhoneTaskIds.includes(task.id)}
                onChange={() => togglePhoneTaskSelection(task.id)}
                onClick={(e) => e.stopPropagation()}
              />
              <div className="tasks-type-dot phone" />
              <div className="tasks-inbox-item-content">
                <div className="tasks-inbox-item-top">
                  <span className="tasks-inbox-item-title">{task.title}</span>
                  <span className="tasks-inbox-item-time">{timeAgo(task.due_date)}</span>
                </div>
                <div className="tasks-inbox-item-sub">{task.contact_name}</div>
                <div className="tasks-inbox-item-tags">
                  <span className="tasks-type-chip phone">Phone</span>
                  <span style={{ fontSize: 11, color: '#6b7280' }}>{task.contact_phone}</span>
                  {task.entity_type && <span className={`tasks-badge green`}>{task.entity_type === 'lead' ? 'Lead' : 'Loan'}</span>}
                </div>
              </div>
            </div>
          ))}
          {phoneTasksList.length === 0 && (
            <div className="tasks-empty">
              <div className="tasks-empty-title">No call tasks available</div>
              <div className="tasks-empty-text">Phone tasks from workflows will appear here</div>
            </div>
          )}
        </div>
      </div>
      <CallDetailPanel
        task={selectedPhoneTask}
        callStatus={callStatus}
        powerDialActive={powerDialActive}
        powerDialIndex={powerDialIndex}
        powerDialTotal={powerDialQueue.length}
        onClickToDial={handleClickToDial}
        onEndCall={handleEndCall}
        onNextContact={nextPowerDialContact}
        onSkipContact={skipPowerDialContact}
        onStopPowerDial={stopPowerDial}
        onViewEntity={(task) => { if (task.lead_id) navigate(`/leads/${task.lead_id}`); else if (task.loan_id) navigate(`/loans/${task.loan_id}`); }}
        onComplete={(taskId) => { setPhoneTasksList(prev => prev.filter(t => t.id !== taskId)); setSelectedPhoneTask(null); }}
        onClose={() => setSelectedPhoneTask(null)}
      />
    </div>
  );

  // Reconciliation detail (cream themed wrapper)
  const renderReconDetail = () => (
    <div className="tasks-detail">
      <ReconciliationDetailPanel
        email={selectedEmail || selectedItem}
        onProcess={(email) => handleOpenDisposition(email)}
        onViewLoan={(loanId) => navigate(`/loans/${loanId}`)}
        onViewLead={(leadId) => navigate(`/leads/${leadId}`)}
        onClose={() => { setSelectedItem(null); setSelectedEmail(null); }}
      />
    </div>
  );

  // Workflow / manual task detail (cream themed — matches mockup)
  const renderWorkflowDetail = () => {
    const task = selectedItem;
    if (!task) return renderEmptyDetail();

    const methods = task.communication_methods || ['email'];
    const dueFormatted = task.due_date
      ? new Date(task.due_date).toLocaleDateString()
      : '--';

    return (
      <div className="tasks-detail">
        <div className="tasks-detail-header">
          <div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
              <span className="tasks-type-chip workflow">{task.source || 'Workflow'}</span>
              {task.urgency && (
                <span className={`tasks-badge ${urgencyLabel(task.urgency)}`}>
                  {(task.urgency || '').toUpperCase()}
                </span>
              )}
            </div>
            <div className="tasks-detail-title">{task.title}</div>
          </div>
          {task.ai_confidence > 0 && (
            <span style={{ fontSize: 11, color: 'var(--text-muted, #8B8A7E)' }}>
              AI Confidence: {task.ai_confidence}%
            </span>
          )}
        </div>

        <div className="tasks-detail-grid">
          <div className="tasks-detail-field">
            <label>Client</label>
            <div
              className="val link"
              onClick={() => {
                if (task.lead_id) navigate(`/leads/${task.lead_id}`);
                else if (task.loan_id) navigate(`/loans/${task.loan_id}`);
                else if (task.entity_id && task.entity_type === 'lead') navigate(`/leads/${task.entity_id}`);
                else if (task.entity_id && task.entity_type === 'loan') navigate(`/loans/${task.entity_id}`);
              }}
            >
              {task.borrower || '--'}
            </div>
          </div>
          <div className="tasks-detail-field">
            <label>Stage</label>
            <div className="val">{task.stage || task.source || '--'}</div>
          </div>
          <div className="tasks-detail-field">
            <label>Priority</label>
            <div className="val">
              <span className={`tasks-badge ${urgencyLabel(task.urgency)}`}>
                {(task.urgency || 'medium').toUpperCase()}
              </span>
            </div>
          </div>
          <div className="tasks-detail-field">
            <label>Due Date</label>
            <div className="val">{dueFormatted}</div>
          </div>
          <div className="tasks-detail-field">
            <label>Owner</label>
            <div className="val">{task.owner || 'Loan Officer'}</div>
          </div>
          <div className="tasks-detail-field">
            <label>Source</label>
            <div className="val">{task.workflow_name || task.source || 'Workflow Engine'}</div>
          </div>
        </div>

        <div className="tasks-channel-row">
          {['Email', 'Text', 'Phone', 'Voicemail'].map(ch => (
            <div
              key={ch}
              className={`tasks-channel-btn${methods.includes(ch.toLowerCase()) ? ' active' : ''}`}
              onClick={() => {
                if (ch === 'Email') handleSend(task.id, 'email', task.ai_message);
                else if (ch === 'Phone') {
                  const phone = task.contact_phone || task.phone;
                  if (phone) window.open(`tel:${phone}`);
                } else {
                  setCommModal({ type: ch, subject: task.title, body: task.ai_message });
                }
              }}
            >
              {ch}
            </div>
          ))}
        </div>

        <div className="tasks-actions">
          <button className="tasks-btn primary" onClick={() => handleSend(task.id, 'email', task.ai_message)}>
            Send via Email
          </button>
          <button className="tasks-btn accent" onClick={() => handleApproveAiTask(task.id)}>
            Approve AI Action
          </button>
          <button className="tasks-btn outline" onClick={() => setShowStatusDropdown(v => !v)}>
            Change Status
          </button>
          <button className="tasks-btn outline" onClick={() => handleSnooze(task.id)}>
            Snooze
          </button>
          <button className="tasks-btn outline" onClick={() => setShowDelegateDropdown(v => !v)}>
            Delegate
          </button>
          <button
            className="tasks-btn success"
            onClick={() => handleComplete(task.id)}
            disabled={completingTask}
          >
            {completingTask ? 'Completing...' : 'Complete Task'}
          </button>
        </div>

        {showStatusDropdown && (
          <div className="tasks-detail-section" style={{ padding: 12 }}>
            <h4 style={{ marginBottom: 8 }}>Select New Status</h4>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {LEAD_STAGES.map(s => (
                <button
                  key={s.value}
                  className="tasks-btn outline"
                  style={{ fontSize: 11, padding: '4px 10px' }}
                  disabled={updatingStatus}
                  onClick={() => { handleChangeStatus(s.value); setShowStatusDropdown(false); }}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {showDelegateDropdown && (
          <div className="tasks-detail-section" style={{ padding: 12 }}>
            <h4 style={{ marginBottom: 8 }}>Delegate To</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {teamMembers.length > 0 ? teamMembers.map(m => (
                <button
                  key={m.id}
                  className="tasks-btn outline"
                  style={{ fontSize: 12, justifyContent: 'flex-start' }}
                  onClick={() => { handleDelegate(m); setShowDelegateDropdown(false); }}
                >
                  {m.name || m.email || `Member ${m.id}`}
                </button>
              )) : (
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>No team members available</span>
              )}
            </div>
          </div>
        )}

        <div className="tasks-detail-section">
          <h4>What to Accomplish</h4>
          <div style={{ fontSize: 13, color: 'var(--text-secondary, #4F554E)', lineHeight: 1.6 }}>
            <strong style={{ color: 'var(--primary, #1F3D2E)' }}>Action:</strong>{' '}
            {task.description || task.ai_message || task.title}
            <br />
            <strong style={{ color: 'var(--primary, #1F3D2E)' }}>Goal:</strong>{' '}
            {task.goal || 'Maintain communication and move the process forward'}
            <br />
            <strong style={{ color: 'var(--primary, #1F3D2E)' }}>Talking Points:</strong>
            <ul style={{ marginTop: 4, paddingLeft: 18 }}>
              {(Array.isArray(task.talking_points) && task.talking_points.length > 0
                ? task.talking_points
                : [
                    'Review the client\'s current status before reaching out',
                    'Share any relevant updates or information',
                    'Ask if they have any questions or concerns',
                  ]
              ).map((point, idx) => (
                <li key={idx}>{point}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    );
  };

  // Empty detail
  const renderEmptyDetail = () => (
    <div className="tasks-detail">
      <div className="tasks-empty">
        <div className="tasks-empty-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#C4B088" strokeWidth="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M9 12h6M12 9v6" />
          </svg>
        </div>
        <div className="tasks-empty-title">
          {activeFilter === 'completed' ? 'No completed tasks yet' : 'All caught up!'}
        </div>
        <div className="tasks-empty-text">
          {activeFilter === 'completed' ? 'Completed tasks will appear here' : 'Select a task from the list or check back later'}
        </div>
      </div>
    </div>
  );

  // Filter tab data
  const filterTabs = [
    { key: 'all', label: 'All', count: allItems.length },
    { key: 'workflow', label: 'Workflow', count: workflowCount },
    { key: 'sms', label: 'SMS', count: smsCount },
    { key: 'reconciliation', label: 'Reconciliation', count: reconCount },
    { key: 'phone', label: 'Phone', count: phoneTasksList.length },
    { key: 'completed', label: 'Completed', count: completedCount },
  ];

  // =============================================
  // Main JSX return
  // =============================================
  return (
    <div className="tasks-page" ref={containerRef}>
      {/* Header */}
      <div className="tasks-header">
        <h1 className="tasks-title">Tasks</h1>
        <p className="tasks-subtitle">Manage workflow tasks, SMS responses, and reconciliation items</p>
      </div>

      {/* Filter tabs */}
      <div className="tasks-filter-bar">
        {filterTabs.map(tab => (
          <button
            key={tab.key}
            className={`tasks-filter-tab${activeFilter === tab.key ? ' active' : ''}`}
            onClick={() => setActiveFilter(tab.key)}
          >
            {tab.label}
            <span className="tasks-filter-count">{tab.count}</span>
          </button>
        ))}
        {selectedTaskIds.size > 0 && (
          <button className="tasks-btn danger" onClick={handleBulkDelete} disabled={bulkDeleting} style={{ marginLeft: 'auto', fontSize: 12, padding: '4px 12px' }}>
            {bulkDeleting ? 'Deleting...' : `Delete (${selectedTaskIds.size})`}
          </button>
        )}
      </div>

      {/* Phone tab uses its own layout */}
      {activeFilter === 'phone' && renderPhoneLayout()}

      {/* All other tabs: unified inbox */}
      {activeFilter !== 'phone' && (
        <div className="tasks-inbox">
          {/* Left column: item list */}
          <div className="tasks-inbox-list">
            <div className="tasks-inbox-search">
              <input
                type="text"
                placeholder="Search tasks..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <div className="tasks-inbox-items">
              {filteredItems.map(renderInboxItem)}
              {filteredItems.length === 0 && (
                <div className="tasks-empty">
                  <div className="tasks-empty-title">
                    {activeFilter === 'completed' ? 'No completed tasks yet' : 'All caught up!'}
                  </div>
                  <div className="tasks-empty-text">
                    {activeFilter === 'completed' ? 'Tasks you complete will show here' : 'No tasks match your current filters'}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right column: detail panel */}
          {selectedItem?.taskType === 'sms'
            ? renderSmsDetail()
            : selectedItem?.taskType === 'reconciliation'
              ? renderReconDetail()
              : selectedItem
                ? renderWorkflowDetail()
                : renderEmptyDetail()
          }
        </div>
      )}

      {/* Communication Detail Modal */}
      {commModal && (
        <div className="tasks-disposition-overlay" onClick={() => setCommModal(null)}>
          <div className="tasks-disposition-modal" onClick={(e) => e.stopPropagation()}>
            <button className="tasks-btn outline" onClick={() => setCommModal(null)} style={{ position: 'absolute', top: 12, right: 12 }}>X</button>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <span className={`tasks-type-chip ${commModal.type === 'Email' ? 'workflow' : commModal.type === 'Phone' ? 'phone' : 'sms'}`}>
                {commModal.type}
              </span>
              <h2 style={{ margin: 0, fontSize: 18, color: 'var(--primary, #1F3D2E)' }}>{commModal.subject}</h2>
            </div>
          </div>
        </div>
      )}

      {/* Disposition Dialog Modal */}
      {showDispositionDialog && dispositionEmail && (
        <div className="tasks-disposition-overlay" onClick={() => setShowDispositionDialog(false)}>
          <div className="tasks-disposition-modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ margin: '0 0 12px', fontSize: 18, color: '#3D2E1C' }}>Process Email</h2>
            <p style={{ margin: '0 0 4px', fontSize: 13, color: '#5A4A32' }}>
              <strong>Subject:</strong> {dispositionEmail.subject || dispositionEmail.title || '(No Subject)'}
            </p>
            <p style={{ margin: '0 0 16px', fontSize: 13, color: '#5A4A32' }}>
              <strong>From:</strong> {dispositionEmail.from_name || dispositionEmail.from_email || dispositionEmail.borrower}
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 8, marginBottom: 16 }}>
              {dispositionOptions.map((option) => (
                <button
                  key={option.value}
                  className={`tasks-disposition-option${selectedDisposition === option.value ? ' selected' : ''}`}
                  onClick={() => setSelectedDisposition(option.value)}
                >
                  <span>{option.icon}</span>
                  <span>{option.label}</span>
                </button>
              ))}
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 8, color: '#5A4A32' }}>
              <input type="checkbox" checked={createTask} onChange={(e) => setCreateTask(e.target.checked)} />
              Create a follow-up task
            </label>

            {createTask && (
              <input
                type="text"
                placeholder="Task title..."
                value={taskTitle}
                onChange={(e) => setTaskTitle(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', border: '1px solid #E8DCC8', borderRadius: 6, fontSize: 13, marginBottom: 12, background: '#FFF' }}
              />
            )}

            <div className="tasks-actions">
              <button
                className="tasks-btn primary"
                onClick={handleProcessDisposition}
                disabled={!selectedDisposition || processingEmailId === dispositionEmail.id}
              >{processingEmailId === dispositionEmail.id ? 'Processing...' : 'Process Email'}</button>
              <button className="tasks-btn outline" onClick={() => setShowDispositionDialog(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Tasks;
