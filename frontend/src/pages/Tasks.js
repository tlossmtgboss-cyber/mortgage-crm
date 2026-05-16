import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { teamAPI, tasksAPI, reconciliationAPI, leadsAPI, loansAPI, API_BASE_URL } from '../services/api';
import { useLayoutFix } from '../hooks/useLayoutFix';
import TaskDetailPanel from '../components/shared/TaskDetailPanel';
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
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
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
    title: item.subject || item.email_subject || '(No Subject)',
    borrower: item.from_name || item.from_email || item.sender_name || 'Unknown',
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

  // SMS detail state
  const [smsTaskDetail, setSmsTaskDetail] = useState(null);
  const [smsDetailLoading, setSmsDetailLoading] = useState(false);
  const [smsResponseMode, setSmsResponseMode] = useState(null);
  const [smsEditText, setSmsEditText] = useState('');
  const [smsSending, setSmsSending] = useState(false);

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

  const handleSmsRegenerate = async () => {
    if (!selectedItem?.id) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks/${selectedItem.id}/regenerate`, {
        method: 'POST', headers: getAuthHeaders(),
        body: JSON.stringify({ feedback: 'Please suggest a different response' }),
      });
      if (!res.ok) throw new Error('Failed to regenerate');
      toast.success('Regenerating AI response...');
      fetchSmsDetail(selectedItem.id);
    } catch (err) {
      toast.error('Failed to regenerate response');
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

  // =============================================
  // Render
  // =============================================
  if (loading) return <TasksSkeleton />;

  const filteredItems = getFilteredItems();

  const renderInboxItem = (item) => {
    const isSelected = selectedItem && selectedItem.id === item.id;
    const isChecked = selectedTaskIds.has(item.id);

    if (item.taskType === 'sms') {
      return (
        <div key={item.id} className={`inbox-item ${isSelected ? 'selected' : ''}`} onClick={() => setSelectedItem(item)}>
          <div className="type-dot sms" />
          <div className="inbox-item-content">
            <div className="inbox-item-top">
              <span className="inbox-item-title">{item.title}</span>
              <span className="inbox-item-time">{timeAgo(item.inbound_received_at || item.created_at)}</span>
            </div>
            <div className="inbox-item-sub">{item.borrower}{item.phone_number ? ` · ${item.phone_number}` : ''}</div>
            {item.inbound_message && (
              <div className="inbox-item-preview">"{item.inbound_message.length > 80 ? item.inbound_message.slice(0, 80) + '...' : item.inbound_message}"</div>
            )}
            <div className="inbox-item-tags">
              <span className="type-chip sms">SMS</span>
              {item.category && (
                <span className="category-badge" style={{
                  backgroundColor: (CATEGORY_COLORS[item.category] || CATEGORY_COLORS.general).bg,
                  color: (CATEGORY_COLORS[item.category] || CATEGORY_COLORS.general).text,
                }}>{(item.category || '').replace(/_/g, ' ')}</span>
              )}
              {item.ai_confidence > 0 && (
                <>
                  <div className="conf-bar"><div className={`conf-bar-fill ${item.ai_confidence >= 85 ? 'high' : item.ai_confidence >= 65 ? 'med' : 'low'}`} style={{ width: `${item.ai_confidence}%` }} /></div>
                  <span className="conf-pct">{item.ai_confidence}%</span>
                </>
              )}
            </div>
          </div>
        </div>
      );
    }

    if (item.taskType === 'reconciliation') {
      return (
        <div key={item.id} className={`inbox-item ${isSelected ? 'selected' : ''}`} onClick={() => { setSelectedItem(item); setSelectedEmail(item); }}>
          <div className="type-dot recon" />
          <div className="inbox-item-content">
            <div className="inbox-item-top">
              <span className="inbox-item-title">{item.title}</span>
              <span className="inbox-item-time">{formatEmailDate(item.sent_date || item.received_at)}</span>
            </div>
            <div className="inbox-item-sub">From: {item.borrower}</div>
            <div className="inbox-item-tags">
              <span className="type-chip recon">Reconciliation</span>
              {item.matched_loan_id && <span className="match-tag">Loan #{item.matched_loan_id}</span>}
              {item.matched_lead_id && <span className="match-tag lead">Lead #{item.matched_lead_id}</span>}
            </div>
          </div>
        </div>
      );
    }

    // Workflow / manual task
    return (
      <div key={item.id} className={`inbox-item ${isSelected ? 'selected' : ''} ${isChecked ? 'checked' : ''}`} onClick={() => setSelectedItem(item)}>
        <div className="type-dot task" />
        <div className="inbox-item-content">
          <div className="inbox-item-top">
            <input type="checkbox" className="task-checkbox" checked={isChecked} onChange={(e) => toggleTaskSelection(item.id, e)} onClick={(e) => e.stopPropagation()} />
            <span className="source-icon">{item.sourceIcon}</span>
            <span className="inbox-item-title">{item.title}</span>
            <span className="inbox-item-time">{timeAgo(item.date_created || item.due_date)}</span>
          </div>
          <div className="inbox-item-sub">{item.borrower || item.source}</div>
          <div className="inbox-item-tags">
            <span className="type-chip task">{item.source || 'Workflow'}</span>
            {item.urgency && (
              <span className="urgency-dot" style={{ backgroundColor: getUrgencyColor(item.urgency) }} title={item.urgency} />
            )}
            {item.ai_confidence && (
              <span className={`ai-confidence-meter ${item.ai_confidence >= 90 ? 'high' : item.ai_confidence >= 70 ? 'medium' : 'low'}`}>
                🤖 {item.ai_confidence}%
              </span>
            )}
          </div>
        </div>
      </div>
    );
  };

  // Detail panel for SMS tasks
  const renderSmsDetail = () => {
    if (smsDetailLoading) return <div className="detail-loading"><div className="spinner" /><p>Loading...</p></div>;
    if (!smsTaskDetail) return <div className="empty-detail"><p>Select a task to view details</p></div>;

    return (
      <div className="sms-detail-panel">
        <div className="detail-header">
          <div>
            <h2>{smsTaskDetail.contact_name || [smsTaskDetail.lead_first_name, smsTaskDetail.lead_last_name].filter(Boolean).join(' ') || 'Unknown Contact'}</h2>
            <span className="detail-phone">{smsTaskDetail.phone_number || ''}</span>
          </div>
          <button className="close-detail" onClick={() => setSelectedItem(null)}>×</button>
        </div>
        <div className="detail-section">
          <h4>Inbound Message</h4>
          <div className="inbound-message-box">
            <p>{smsTaskDetail.inbound_message}</p>
            <span className="message-time">{timeAgo(smsTaskDetail.inbound_received_at || smsTaskDetail.created_at)}</span>
          </div>
        </div>
        <div className="detail-meta">
          {smsTaskDetail.category && (
            <span className="category-badge" style={{
              backgroundColor: (CATEGORY_COLORS[smsTaskDetail.category] || CATEGORY_COLORS.general).bg,
              color: (CATEGORY_COLORS[smsTaskDetail.category] || CATEGORY_COLORS.general).text,
            }}>{(smsTaskDetail.category || 'general').replace(/_/g, ' ')}</span>
          )}
          <span className="priority-badge" style={{ color: PRIORITY_COLORS[smsTaskDetail.priority] || PRIORITY_COLORS.normal }}>
            {smsTaskDetail.priority || 'normal'} priority
          </span>
        </div>
        {smsTaskDetail.ai_recommendation && (
          <div className="detail-section">
            <h4>AI Recommended Response</h4>
            <div className="ai-response-box">
              <p>{smsTaskDetail.ai_recommendation}</p>
              <div className="ai-confidence-row">
                <span>Confidence: {smsTaskDetail.ai_confidence || 0}%</span>
                <div className="confidence-bar-bg large">
                  <div className="confidence-bar-fill" style={{ width: `${smsTaskDetail.ai_confidence || 0}%` }} />
                </div>
                <button className="regen-btn" onClick={handleSmsRegenerate} title="Regenerate">↻</button>
              </div>
            </div>
          </div>
        )}
        {smsTaskDetail.status === 'pending' && !smsResponseMode && (
          <div className="action-buttons">
            <button className="action-btn send-ai" onClick={() => handleSmsSendResponse(smsTaskDetail.ai_recommendation, 'ai')} disabled={!smsTaskDetail.ai_recommendation || smsSending}>
              {smsSending ? 'Sending...' : 'Send AI Response'}
            </button>
            <button className="action-btn edit-send" onClick={() => { setSmsResponseMode('edit'); setSmsEditText(smsTaskDetail.ai_recommendation || ''); }}>Edit & Send</button>
            <button className="action-btn write-own" onClick={() => { setSmsResponseMode('write'); setSmsEditText(''); }}>Write Own</button>
            <button className="action-btn dismiss" onClick={handleSmsDismiss}>Dismiss</button>
          </div>
        )}
        {smsResponseMode && (
          <div className="compose-area">
            <textarea value={smsEditText} onChange={(e) => setSmsEditText(e.target.value)} placeholder={smsResponseMode === 'edit' ? 'Edit the AI response...' : 'Write your response...'} rows={4} autoFocus />
            <div className="compose-actions">
              <button className="action-btn send-ai" onClick={() => handleSmsSendResponse(smsEditText, smsResponseMode === 'edit' ? 'ai_edited' : 'manual')} disabled={!smsEditText.trim() || smsSending}>
                {smsSending ? 'Sending...' : 'Send'}
              </button>
              <button className="action-btn dismiss" onClick={() => { setSmsResponseMode(null); setSmsEditText(''); }}>Cancel</button>
            </div>
          </div>
        )}
        {smsTaskDetail.status !== 'pending' && (
          <div className="detail-section">
            <h4>Response Sent</h4>
            <div className="sent-response-box">
              <p>{smsTaskDetail.response_text || 'No response recorded'}</p>
              <span className="response-source">via {(smsTaskDetail.response_source || 'unknown').replace(/_/g, ' ')}</span>
            </div>
          </div>
        )}
      </div>
    );
  };

  // Phone tab layout
  const renderPhoneLayout = () => (
    <div className="email-layout">
      <div className="task-inbox">
        <div className="inbox-header">
          <div className="inbox-header-left">
            <h3>Call Tasks</h3>
            <span className="task-count">{phoneTasksList.length}</span>
          </div>
          <div className="inbox-header-right">
            <button className="select-all-btn" onClick={selectAllPhoneTasks}>
              {selectedPhoneTaskIds.length === phoneTasksList.length ? '☑ Deselect All' : '☐ Select All'}
            </button>
            {!powerDialActive ? (
              <button className="power-dial-btn" onClick={startPowerDial} disabled={phoneTasksList.length === 0}>
                Power Dial {selectedPhoneTaskIds.length > 0 ? `(${selectedPhoneTaskIds.length})` : 'All'}
              </button>
            ) : (
              <button className="power-dial-btn stop" onClick={stopPowerDial}>Stop Dialing</button>
            )}
          </div>
        </div>
        {powerDialActive && (
          <div className="power-dial-progress">
            <div className="progress-info">
              <span>Power Dialing: {powerDialIndex + 1} of {powerDialQueue.length}</span>
              <span className="progress-contact">{powerDialQueue[powerDialIndex]?.contact_name}</span>
            </div>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${((powerDialIndex + 1) / powerDialQueue.length) * 100}%` }} />
            </div>
          </div>
        )}
        <div className="inbox-list">
          {phoneTasksList.map((task) => (
            <div key={task.id} className={`inbox-item ${selectedPhoneTask?.id === task.id ? 'selected' : ''}`} onClick={() => setSelectedPhoneTask(task)}>
              <div className="inbox-item-header">
                <input type="checkbox" className="task-checkbox" checked={selectedPhoneTaskIds.includes(task.id)} onChange={() => togglePhoneTaskSelection(task.id)} onClick={(e) => e.stopPropagation()} />
                <span className="source-icon">{task.task_type === 'workflow' ? '⚡' : '📞'}</span>
                <span className="task-title-compact">{task.title}</span>
              </div>
              <div className="inbox-item-meta">
                <span className="task-client-compact">{task.contact_name}</span>
                <span className="urgency-dot" style={{ backgroundColor: task.priority === 'high' ? '#f59e0b' : '#6b7280' }} />
              </div>
              <div className="task-preview">
                <span className="phone-tag">{task.contact_phone}</span>
                {task.entity_type && <span className={`match-tag ${task.entity_type}`}>{task.entity_type === 'lead' ? 'Lead' : 'Loan'}</span>}
              </div>
            </div>
          ))}
          {phoneTasksList.length === 0 && (
            <div className="empty-inbox"><p>No call tasks available</p><p style={{ fontSize: '12px', color: '#888' }}>Phone tasks from workflows will appear here</p></div>
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

  return (
    <div className="tasks-page" ref={containerRef}>
      <div className="tasks-container">
        <div className="tasks-header">
          <div className="header-content">
            <h1>Tasks</h1>
            <p>All workflow tasks, SMS responses, and reconciliation in one place</p>

            <div className="unified-filter-tabs">
              <button className={`filter-tab ${activeFilter === 'all' ? 'active' : ''}`} onClick={() => setActiveFilter('all')}>
                All <span className="filter-count">{allItems.length}</span>
              </button>
              <button className={`filter-tab ${activeFilter === 'workflow' ? 'active' : ''}`} onClick={() => setActiveFilter('workflow')}>
                Workflow <span className="filter-count">{workflowCount}</span>
              </button>
              <button className={`filter-tab ${activeFilter === 'sms' ? 'active' : ''}`} onClick={() => setActiveFilter('sms')}>
                SMS <span className="filter-count">{smsCount}</span>
              </button>
              <button className={`filter-tab ${activeFilter === 'reconciliation' ? 'active' : ''}`} onClick={() => setActiveFilter('reconciliation')}>
                Reconciliation <span className="filter-count">{reconCount}</span>
              </button>
              <button className={`filter-tab ${activeFilter === 'phone' ? 'active' : ''}`} onClick={() => setActiveFilter('phone')}>
                Phone <span className="filter-count">{phoneTasksList.length}</span>
              </button>
              <button className={`filter-tab ${activeFilter === 'completed' ? 'active' : ''}`} onClick={() => setActiveFilter('completed')}>
                Completed <span className="filter-count">{completedCount}</span>
              </button>
            </div>
          </div>
        </div>

        {/* Phone Tab */}
        {activeFilter === 'phone' && (
          <div className="tasks-content">{renderPhoneLayout()}</div>
        )}

        {/* All other tabs — Unified Inbox */}
        {activeFilter !== 'phone' && (
          <div className="tasks-content">
            <div className="email-layout">
              {/* Left: Item List */}
              <div className="task-inbox">
                <div className="inbox-header">
                  <div className="inbox-header-left">
                    {activeFilter !== 'completed' && filteredItems.length > 0 && (
                      <input
                        type="checkbox"
                        className="task-checkbox select-all-checkbox"
                        checked={filteredItems.length > 0 && filteredItems.every(t => selectedTaskIds.has(t.id))}
                        onChange={() => handleSelectAll(filteredItems)}
                        title="Select all"
                      />
                    )}
                    <h3>Tasks</h3>
                    <span className="task-count">{filteredItems.length}</span>
                  </div>
                  {selectedTaskIds.size > 0 && (
                    <button className="btn-bulk-delete" onClick={handleBulkDelete} disabled={bulkDeleting}>
                      {bulkDeleting ? 'Deleting...' : `Delete (${selectedTaskIds.size})`}
                    </button>
                  )}
                </div>
                <div className="inbox-search">
                  <input
                    type="text"
                    placeholder="Search tasks..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="search-input"
                  />
                </div>
                <div className="inbox-list">
                  {filteredItems.map(renderInboxItem)}
                  {filteredItems.length === 0 && (
                    <div className="empty-inbox">
                      <p>{activeFilter === 'completed' ? 'No completed tasks yet' : 'All caught up!'}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Right: Detail Panel */}
              {selectedItem?.taskType === 'sms' ? (
                <div className="task-detail-wrapper">{renderSmsDetail()}</div>
              ) : selectedItem?.taskType === 'reconciliation' ? (
                <ReconciliationDetailPanel
                  email={selectedEmail || selectedItem}
                  onProcess={(email) => handleOpenDisposition(email)}
                  onViewLoan={(loanId) => navigate(`/loans/${loanId}`)}
                  onViewLead={(leadId) => navigate(`/leads/${leadId}`)}
                  onClose={() => { setSelectedItem(null); setSelectedEmail(null); }}
                />
              ) : (
                <TaskDetailPanel
                  task={selectedItem}
                  onComplete={handleComplete}
                  onDelete={handleDelete}
                  onSnooze={handleSnooze}
                  onDelegate={handleDelegate}
                  onSend={handleSend}
                  onApproveAi={handleApproveAiTask}
                  onChangeStatus={handleChangeStatus}
                  completing={completingTask}
                  updatingStatus={updatingStatus}
                  teamMembers={teamMembers}
                  statusOptions={LEAD_STAGES}
                />
              )}
            </div>
          </div>
        )}
      </div>

      {/* Communication Detail Modal */}
      {commModal && (
        <div className="comm-modal-overlay" onClick={() => setCommModal(null)}>
          <div className="comm-modal" onClick={(e) => e.stopPropagation()}>
            <button className="btn-close-comm-modal" onClick={() => setCommModal(null)}>×</button>
            <div className="comm-modal-header">
              <span className="comm-modal-icon">
                {commModal.type === 'Email' && '📧'}
                {commModal.type === 'Phone' && '📞'}
                {commModal.type === 'Text' && '💬'}
              </span>
              <h2>{commModal.subject}</h2>
            </div>
          </div>
        </div>
      )}

      {/* Disposition Dialog Modal */}
      {showDispositionDialog && dispositionEmail && (
        <div className="modal-overlay" onClick={() => setShowDispositionDialog(false)}>
          <div className="modal-content disposition-modal" onClick={(e) => e.stopPropagation()}>
            <h2>Process Email</h2>
            <p className="disposition-email-subject"><strong>Subject:</strong> {dispositionEmail.subject || dispositionEmail.title || '(No Subject)'}</p>
            <p className="disposition-email-from"><strong>From:</strong> {dispositionEmail.from_name || dispositionEmail.from_email || dispositionEmail.borrower}</p>

            <div className="disposition-options-grid">
              {dispositionOptions.map((option) => (
                <button key={option.value} className={`disposition-option ${selectedDisposition === option.value ? 'selected' : ''}`} onClick={() => setSelectedDisposition(option.value)}>
                  <span className="disposition-icon">{option.icon}</span>
                  <span className="disposition-label">{option.label}</span>
                </button>
              ))}
            </div>

            <label className="create-task-checkbox">
              <input type="checkbox" checked={createTask} onChange={(e) => setCreateTask(e.target.checked)} />
              <span>Create a follow-up task</span>
            </label>

            {createTask && (
              <input type="text" className="task-title-input" placeholder="Task title..." value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} />
            )}

            <div className="modal-buttons">
              <button className="btn-modal-primary" onClick={handleProcessDisposition} disabled={!selectedDisposition || processingEmailId === dispositionEmail.id}>
                {processingEmailId === dispositionEmail.id ? 'Processing...' : 'Process Email'}
              </button>
              <button className="btn-modal-cancel" onClick={() => setShowDispositionDialog(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Tasks;
