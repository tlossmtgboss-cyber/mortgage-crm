import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { commandCenterAPI, tasksAPI, reconciliationAPI } from '../services/api';
import TaskDetailPanel from './shared/TaskDetailPanel';
import ReconciliationDetailPanel from './shared/ReconciliationDetailPanel';
import CallDetailPanel from './shared/CallDetailPanel';
import { TASK_EVENTS, emitTaskCompleted, subscribeToTaskEvent } from '../utils/taskEvents';
import './ActionSidebar.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const ActionSidebar = ({ onTaskSelect, onClose }) => {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [workflowTasks, setWorkflowTasks] = useState([]); // Workflow tasks from same source as Tasks page
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('tasks');
  const [selectedItem, setSelectedItem] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [completingTask, setCompletingTask] = useState(false);

  // Call-related state
  const [selectedCallIds, setSelectedCallIds] = useState(new Set());
  const [powerDialing, setPowerDialing] = useState(false);
  const [currentCallIndex, setCurrentCallIndex] = useState(0);
  const [callInProgress, setCallInProgress] = useState(false);

  // Fetch workflow tasks (same source as Tasks page) for Tasks tab
  const fetchWorkflowTasks = useCallback(async () => {
    try {
      const token = getToken();

      // Fetch workflow tasks - SAME endpoint as Tasks page
      const workflowResponse = await fetch(`${API_BASE}/api/v1/workflow-config/all-workflow-tasks?days_ahead=14`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      let wfTasks = [];
      if (workflowResponse.ok) {
        const workflowData = await workflowResponse.json();
        wfTasks = (workflowData.tasks || []).map(task => ({
          id: task.id,
          title: task.title,
          entity_name: task.client_name || 'Client',
          stage: task.stage,
          priority: task.urgency || 'medium',
          type: 'workflow',
          category: 'workflow',
          due_date: task.due_date,
          created_at: task.due_date,
          description: task.description,
          entity_type: task.client_type,
          entity_id: task.client_id,
          lead_id: task.client_type === 'lead' ? task.client_id : null,
          loan_id: task.client_type === 'loan' ? task.client_id : null,
          workflow_name: task.workflow_name,
          workflow_color: task.workflow_color,
          preferred_contact_method: task.communication_methods?.includes('phone') ? 'Phone'
            : task.communication_methods?.includes('text') ? 'Text' : 'Email',
          communication_methods: task.communication_methods || [],
          days_until_due: task.days_until_due,
          source: 'Workflow'
        }));
      }

      // Also fetch manual tasks from unified-tasks - SAME as Tasks page
      const unifiedResponse = await tasksAPI.getUnified();
      const unifiedTasks = unifiedResponse?.tasks || [];

      const manualTasks = unifiedTasks
        .filter(t => t.source === 'task' && !t.email_from && !t.email_subject)
        .map(task => ({
          id: `task-${task.id}`,
          title: task.title,
          entity_name: task.client_name || 'Client',
          stage: task.stage || 'Manual',
          priority: task.priority || 'medium',
          type: 'task',
          category: 'manual',
          due_date: task.due_date,
          created_at: task.created_at,
          description: task.description,
          entity_type: task.entity_type,
          entity_id: task.entity_id,
          source: 'Manual'
        }));

      // Filter out phone-only workflow tasks (same as Tasks page)
      const nonPhoneTasks = wfTasks.filter(task => task.preferred_contact_method !== 'Phone');

      // Combine and dedupe (same as Tasks page)
      const allTasks = [...nonPhoneTasks, ...manualTasks];
      const seen = new Set();
      const dedupedTasks = allTasks.filter(task => {
        if (seen.has(task.id)) return false;
        seen.add(task.id);
        return true;
      });

      setWorkflowTasks(dedupedTasks);
    } catch (err) {
      console.error('Error fetching workflow tasks:', err);
      setWorkflowTasks([]);
    }
  }, []);

  // Fetch command center data (for emails and calls tabs)
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);

      // Fetch both workflow tasks and command center data in parallel
      await Promise.all([
        fetchWorkflowTasks(),
        commandCenterAPI.getAll().then(result => setData(result))
      ]);

      setError(null);
    } catch (err) {
      console.error('Action sidebar error:', err);
      setError('Error loading action items');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [fetchWorkflowTasks]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 120000);

    // Subscribe to task events from other components (e.g., Tasks page)
    const unsubscribeCompleted = subscribeToTaskEvent(TASK_EVENTS.TASK_COMPLETED, (detail) => {
      // Only refresh if the event came from somewhere else
      if (detail.source !== 'action-sidebar') {
        fetchData();
      }
    });

    const unsubscribeRefresh = subscribeToTaskEvent(TASK_EVENTS.TASKS_REFRESH, (detail) => {
      if (detail.source !== 'action-sidebar') {
        fetchData();
      }
    });

    return () => {
      clearInterval(interval);
      unsubscribeCompleted();
      unsubscribeRefresh();
    };
  }, [fetchData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  // Helper to check if an item is phone/call related
  const isPhoneTask = (item) => {
    const phoneTypes = ['follow_up', 'call', 'voicemail', 'sms', 'phone'];
    const phoneKeywords = ['call', 'phone', 'voicemail', 'sms', 'text', 'contact', 'follow up', 'follow-up'];
    if (phoneTypes.includes(item.type?.toLowerCase())) return true;
    const title = (item.title || '').toLowerCase();
    const desc = (item.description || '').toLowerCase();
    return phoneKeywords.some(keyword => title.includes(keyword) || desc.includes(keyword));
  };

  // Helper to check if an item is email related
  const isEmailTask = (item) => {
    const emailTypes = ['email', 'email_pending', 'reconciliation'];
    const emailKeywords = ['email', 'reconcil'];
    if (emailTypes.includes(item.type?.toLowerCase())) return true;
    const title = (item.title || '').toLowerCase();
    const desc = (item.description || '').toLowerCase();
    return emailKeywords.some(keyword => title.includes(keyword) || desc.includes(keyword));
  };

  // Helper to check if a portfolio item is actionable (not just informational funded loan records)
  const isActionablePortfolioItem = (item) => {
    // Funded loans are not actionable tasks - they're informational records
    // Only include portfolio items that have an actual action (touchpoint due, refinance opportunity to contact, etc.)
    if (item.type === 'funded_loan') return false;
    // Include touchpoints and other actionable portfolio items
    return true;
  };

  // Get items for each tab
  const getTaskItems = () => {
    // Use workflow tasks (same source as Tasks page) for the Tasks tab
    // This ensures the count matches between Action Center and Tasks page
    return workflowTasks;
  };

  const getEmailItems = () => {
    if (!data) return [];
    const items = [];
    if (data.emails?.length) {
      items.push(...data.emails.map(item => ({ ...item, category: 'emails' })));
    }
    if (data.reconciliation?.length) {
      items.push(...data.reconciliation.map(item => ({ ...item, category: 'reconciliation' })));
    }
    if (data.urgent?.length) {
      items.push(...data.urgent.filter(isEmailTask).map(item => ({ ...item, category: 'urgent' })));
    }
    if (data.leads?.length) {
      items.push(...data.leads.filter(isEmailTask).map(item => ({ ...item, category: 'leads' })));
    }
    if (data.loans?.length) {
      items.push(...data.loans.filter(isEmailTask).map(item => ({ ...item, category: 'loans' })));
    }
    return items;
  };

  const getCallItems = () => {
    if (!data) return [];
    const items = [];
    if (data.calls?.length) {
      items.push(...data.calls.map(item => ({ ...item, category: 'calls' })));
    }
    if (data.sms?.length) {
      items.push(...data.sms.map(item => ({ ...item, category: 'sms' })));
    }
    if (data.urgent?.length) {
      items.push(...data.urgent.filter(isPhoneTask).map(item => ({ ...item, category: 'urgent' })));
    }
    if (data.leads?.length) {
      items.push(...data.leads.filter(isPhoneTask).map(item => ({ ...item, category: 'leads' })));
    }
    if (data.loans?.length) {
      items.push(...data.loans.filter(isPhoneTask).map(item => ({ ...item, category: 'loans' })));
    }
    if (data.portfolio?.length) {
      // Filter out non-actionable portfolio items (like funded_loan records) from calls too
      items.push(...data.portfolio.filter(item => isPhoneTask(item) && isActionablePortfolioItem(item)).map(item => ({ ...item, category: 'portfolio' })));
    }
    return items;
  };

  const getTabItems = () => {
    switch (activeTab) {
      case 'tasks': return getTaskItems();
      case 'emails': return getEmailItems();
      case 'calls': return getCallItems();
      default: return [];
    }
  };

  const getTabCount = (tab) => {
    switch (tab) {
      case 'tasks': return getTaskItems().length;
      case 'emails': return getEmailItems().length;
      case 'calls': return getCallItems().length;
      default: return 0;
    }
  };

  const getPriorityColor = (priority) => {
    switch (priority?.toLowerCase()) {
      case 'critical': return '#ef4444';
      case 'high': return '#f97316';
      case 'medium': return '#eab308';
      case 'low': return '#22c55e';
      default: return '#9ca3af';
    }
  };

  const getTypeIcon = (type, category) => {
    if (category === 'urgent') return '🚨';
    if (category === 'reconciliation') return '🔄';
    if (category === 'calls' || category === 'sms') return '📞';
    if (category === 'emails') return '📧';
    if (category === 'portfolio') return '👋';
    switch (type) {
      case 'sla_alert': return '⚠️';
      case 'task': return '✅';
      case 'follow_up': return '📞';
      case 'lock_expiring': return '🔒';
      case 'closing_soon': return '🏠';
      case 'touchpoint': return '👋';
      case 'email_pending': return '📧';
      case 'sms_unanswered': return '💬';
      case 'voicemail': return '📱';
      default: return '📋';
    }
  };

  const getCategoryLabel = (category) => {
    const labels = {
      urgent: 'Urgent',
      leads: 'Lead',
      loans: 'Loan',
      portfolio: 'Portfolio',
      emails: 'Email',
      sms: 'SMS',
      calls: 'Call',
      reconciliation: 'Reconcile'
    };
    return labels[category] || category;
  };

  const formatTimeAgo = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    if (minutes < 60) return `${minutes}m`;
    if (hours < 24) return `${hours}h`;
    if (days < 7) return `${days}d`;
    return date.toLocaleDateString();
  };

  const handleItemClick = (item) => {
    setSelectedItem(selectedItem?.id === item.id ? null : item);
    if (onTaskSelect) {
      onTaskSelect(item);
    }
  };

  // Complete a task or mark action item as done
  const handleCompleteTask = async (item) => {
    setCompletingTask(true);
    try {
      const itemId = item.id || '';
      const itemIdStr = String(itemId);

      // Handle workflow tasks (numeric IDs from workflow endpoint)
      if (typeof itemId === 'number' || (!itemIdStr.includes('-') && !isNaN(itemId))) {
        // Workflow task - update lead's last_contact to mark as complete
        if (item.lead_id) {
          const token = getToken();
          await fetch(`${API_BASE}/api/v1/leads/${item.lead_id}`, {
            method: 'PATCH',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ last_contact: new Date().toISOString() })
          });
        } else if (item.loan_id) {
          // For loan tasks, we could update loan's last_activity
          // Workflow task completion for loan - no additional action needed
        }
      }
      // Handle manual tasks (task-XXX format)
      else if (itemIdStr.startsWith('task-')) {
        const taskId = itemIdStr.replace('task-', '');
        await tasksAPI.update(taskId, { status: 'completed' });
      }
      // For follow-up items, update the lead's last_contact date
      else if (itemIdStr.startsWith('followup_lead_') && item.entity_id) {
        const token = getToken();
        await fetch(`${API_BASE}/api/v1/leads/${item.entity_id}`, {
          method: 'PATCH',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ last_contact: new Date().toISOString() })
        });
      }
      // For deadline items and other types, just dismiss from UI
      else if (itemIdStr.startsWith('deadline_') || itemIdStr.startsWith('sla_') || itemIdStr.startsWith('active_loan_')) {
        // Informational item dismissed - no additional action needed
      }

      // Remove from local workflow tasks immediately for instant UI feedback
      setWorkflowTasks(prev => prev.filter(t => t.id !== itemId));

      // Remove from selected and refresh
      setSelectedItem(null);

      // Emit event so other components (like Tasks page) can update
      emitTaskCompleted(itemId, 'action-sidebar');

      // Refresh data after a short delay to get updated counts
      setTimeout(() => fetchData(), 500);
    } catch (err) {
      console.error('Complete task error:', err);
      toast.error('Failed to complete task. Please try again.');
    } finally {
      setCompletingTask(false);
    }
  };

  // Make a phone call
  const handleMakeCall = async (item) => {
    const phone = item.phone || item.entity_phone || item.borrower_phone;
    if (!phone) {
      toast.error('No phone number available for this contact');
      return;
    }

    const cleanPhone = phone.replace(/[^\d+]/g, '');
    const dialNumber = cleanPhone.startsWith('+') ? cleanPhone : `+1${cleanPhone}`;
    window.open(`https://teams.microsoft.com/l/call/0/0?users=4:${encodeURIComponent(dialNumber)}`, '_blank');
    await handleCompleteTask(item);
  };

  // Toggle call selection
  const handleToggleCallSelection = (itemId) => {
    setSelectedCallIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(itemId)) {
        newSet.delete(itemId);
      } else {
        newSet.add(itemId);
      }
      return newSet;
    });
  };

  // Select all calls
  const handleSelectAllCalls = () => {
    const callItems = getCallItems();
    if (selectedCallIds.size === callItems.length) {
      setSelectedCallIds(new Set());
    } else {
      setSelectedCallIds(new Set(callItems.map(item => item.id)));
    }
  };

  // Start power dialer
  const handleStartPowerDial = async () => {
    const callItems = getCallItems().filter(item => selectedCallIds.has(item.id));
    if (callItems.length === 0) {
      toast.error('Please select contacts to call');
      return;
    }

    setPowerDialing(true);
    setCurrentCallIndex(0);

    // Start calling the first contact
    await handleMakeCall(callItems[0]);
  };

  // Navigate to entity
  const handleNavigate = (item) => {
    if (item.url) {
      navigate(item.url);
    }
  };

  const items = getTabItems();
  const callItems = getCallItems();
  const allCallsSelected = callItems.length > 0 && selectedCallIds.size === callItems.length;

  // Get total count for welcome message
  const totalItems = getTabCount('tasks') + getTabCount('emails') + getTabCount('calls');

  return (
    <div className={`action-sidebar ${selectedItem ? 'expanded' : ''}`}>
      <div className="action-sidebar-header">
        <h2>Action Center</h2>
        <div className="header-actions">
          <button
            className={`refresh-btn ${refreshing ? 'refreshing' : ''}`}
            onClick={handleRefresh}
            disabled={refreshing}
            title="Refresh"
          >
            🔄
          </button>
          {onClose && (
            <button className="close-btn" onClick={onClose}>×</button>
          )}
        </div>
      </div>

      {/* Welcome Message */}
      {totalItems > 0 && !selectedItem && (
        <div className="action-welcome-message">
          <span className="welcome-icon">👋</span>
          <div className="welcome-text">
            <strong>Here are the outstanding things you need to do first</strong>
            <span className="welcome-count">{totalItems} action items need your attention</span>
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="action-tabs">
        <button
          className={`action-tab ${activeTab === 'tasks' ? 'active' : ''}`}
          onClick={() => { setActiveTab('tasks'); setSelectedItem(null); }}
        >
          <span className="tab-icon">✅</span>
          <span className="tab-label">Tasks</span>
          {getTabCount('tasks') > 0 && (
            <span className="tab-count">{getTabCount('tasks')}</span>
          )}
        </button>
        <button
          className={`action-tab ${activeTab === 'emails' ? 'active' : ''}`}
          onClick={() => { setActiveTab('emails'); setSelectedItem(null); }}
        >
          <span className="tab-icon">📧</span>
          <span className="tab-label">Emails</span>
          {getTabCount('emails') > 0 && (
            <span className="tab-count">{getTabCount('emails')}</span>
          )}
        </button>
        <button
          className={`action-tab ${activeTab === 'calls' ? 'active' : ''}`}
          onClick={() => { setActiveTab('calls'); setSelectedItem(null); }}
        >
          <span className="tab-icon">📞</span>
          <span className="tab-label">Calls</span>
          {getTabCount('calls') > 0 && (
            <span className="tab-count">{getTabCount('calls')}</span>
          )}
        </button>
      </div>

      {/* Power Dialer Controls (Calls tab only) */}
      {activeTab === 'calls' && items.length > 0 && (
        <div className="power-dialer-controls">
          <label className="select-all-label">
            <input
              type="checkbox"
              checked={allCallsSelected}
              onChange={handleSelectAllCalls}
            />
            Select All ({callItems.length})
          </label>
          <button
            className="power-dial-btn"
            onClick={handleStartPowerDial}
            disabled={selectedCallIds.size === 0 || powerDialing}
          >
            {powerDialing ? '📞 Dialing...' : `📞 Power Dial (${selectedCallIds.size})`}
          </button>
        </div>
      )}

      {/* Content Area - Split View */}
      <div className={`action-content ${selectedItem ? 'with-detail' : ''}`}>
        {loading ? (
          <div className="action-loading">
            <div className="loading-spinner"></div>
            <p>Loading...</p>
          </div>
        ) : error ? (
          <div className="action-error">
            <p>{error}</p>
            <button onClick={handleRefresh}>Retry</button>
          </div>
        ) : items.length === 0 ? (
          <div className="action-empty">
            <span className="empty-icon">
              {activeTab === 'tasks' ? '✅' : activeTab === 'emails' ? '📧' : '📞'}
            </span>
            <p>No {activeTab} to complete</p>
            <span className="empty-subtext">You're all caught up!</span>
          </div>
        ) : (
          <>
            {/* Item List */}
            <div className="action-list">
              {items.map((item, idx) => (
                <div
                  key={item.id || idx}
                  className={`action-item ${selectedItem?.id === item.id ? 'selected' : ''} ${item.priority === 'critical' ? 'critical' : ''} ${activeTab === 'calls' ? 'with-checkbox' : ''}`}
                  onClick={() => handleItemClick(item)}
                >
                  {activeTab === 'calls' && (
                    <div className="call-checkbox">
                      <input
                        type="checkbox"
                        checked={selectedCallIds.has(item.id)}
                        onChange={(e) => {
                          e.stopPropagation();
                          handleToggleCallSelection(item.id);
                        }}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </div>
                  )}
                  <div
                    className="priority-bar"
                    style={{ backgroundColor: getPriorityColor(item.priority) }}
                  />
                  <div className="item-content">
                    <div className="item-header">
                      <span className="item-icon">{getTypeIcon(item.type, item.category)}</span>
                      <span className="item-category">{getCategoryLabel(item.category)}</span>
                      {item.created_at && (
                        <span className="item-time">{formatTimeAgo(item.created_at)}</span>
                      )}
                    </div>
                    <div className="item-title">{item.title}</div>
                    {item.entity_name && (
                      <div className="item-entity">{item.entity_name}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Detail Panel - Render appropriate shared component based on tab */}
            {selectedItem && activeTab === 'tasks' && (
              <TaskDetailPanel
                task={{
                  ...selectedItem,
                  borrower: selectedItem.entity_name || selectedItem.borrower,
                  urgency: selectedItem.priority || selectedItem.urgency,
                  source: selectedItem.source || getCategoryLabel(selectedItem.category),
                  ai_message: selectedItem.ai_message || `Hi ${(selectedItem.entity_name || selectedItem.borrower || 'there').split(' ')[0]},\n\nI hope this message finds you well! I wanted to follow up regarding your ${selectedItem.stage || 'loan application'}.\n\nIf you'd like to discuss your options or need any assistance, I'm here to help. Feel free to reply to this email or give me a call at (555) 123-4567.\n\nLooking forward to hearing from you!\n\nBest regards,\n[Your Name]\nLoan Officer`
                }}
                onComplete={(id) => handleCompleteTask(selectedItem)}
                onDelete={() => {}}
                onSnooze={() => {}}
                onDelegate={() => {}}
                onSend={() => {}}
                onApproveAi={() => {}}
                onChangeStatus={() => {}}
                onClose={() => setSelectedItem(null)}
                completing={completingTask}
                compact={true}
              />
            )}
            {selectedItem && activeTab === 'emails' && (
              <ReconciliationDetailPanel
                email={{
                  ...selectedItem,
                  subject: selectedItem.title || selectedItem.subject,
                  from_name: selectedItem.entity_name || selectedItem.from_name,
                  from_email: selectedItem.email || selectedItem.from_email,
                  sent_date: selectedItem.created_at || selectedItem.sent_date,
                  body_preview: selectedItem.description || selectedItem.body_preview,
                  matched_loan_id: selectedItem.loan_id,
                  matched_lead_id: selectedItem.lead_id
                }}
                onProcess={() => {}}
                onViewLoan={(loanId) => navigate(`/loans/${loanId}`)}
                onViewLead={(leadId) => navigate(`/leads/${leadId}`)}
                onClose={() => setSelectedItem(null)}
                compact={true}
              />
            )}
            {selectedItem && activeTab === 'calls' && (
              <CallDetailPanel
                task={{
                  ...selectedItem,
                  contact_name: selectedItem.entity_name || selectedItem.contact_name,
                  contact_phone: selectedItem.phone || selectedItem.contact_phone || '(555) 000-0000',
                  entity_type: selectedItem.lead_id ? 'lead' : 'loan',
                  lead_id: selectedItem.lead_id,
                  loan_id: selectedItem.loan_id
                }}
                callStatus={callInProgress ? 'in-progress' : 'idle'}
                powerDialActive={powerDialing}
                powerDialIndex={currentCallIndex}
                powerDialTotal={selectedCallIds.size}
                onClickToDial={(task) => {
                  // Use Telnyx dialer API instead of tel: link (which opens FaceTime on Mac)
                  handleMakeCall({
                    phone: task.contact_phone,
                    entity_name: task.contact_name,
                    entity_type: task.entity_type,
                    entity_id: task.lead_id || task.loan_id,
                    title: task.title
                  });
                }}
                onEndCall={() => setCallInProgress(false)}
                onNextContact={() => setCurrentCallIndex(prev => prev + 1)}
                onSkipContact={() => setCurrentCallIndex(prev => prev + 1)}
                onStopPowerDial={() => {
                  setPowerDialing(false);
                  setCurrentCallIndex(0);
                }}
                onViewEntity={(task) => {
                  if (task.lead_id) {
                    navigate(`/leads/${task.lead_id}`);
                  } else if (task.loan_id) {
                    navigate(`/loans/${task.loan_id}`);
                  }
                }}
                onComplete={(taskId) => handleCompleteTask(selectedItem)}
                onClose={() => setSelectedItem(null)}
                completing={completingTask}
                compact={true}
              />
            )}
          </>
        )}
      </div>

      {/* Summary Footer */}
      <div className="action-footer">
        <span className="total-count">
          {totalItems} total items
        </span>
      </div>
    </div>
  );
};

export default ActionSidebar;
