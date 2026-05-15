import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import { toast } from '../utils/toast';
import './SLASettings.css';
import { getToken } from '../utils/tokenStore';

const SLASettings = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - allow SLA access to managers, admins, and loan officers
  // Use isAdmin from context which has robust admin detection (checks permission_role, is_admin flag, legacy role)
  const canAccessSLA = isAdmin || hasAnyPermission(['settings.sla', 'settings.manage', 'admin.manage', 'sla.view', 'sla.manage']) ||
    ['management', 'admin', 'loan_officer', 'sales', 'processor', 'underwriter'].includes(userRole);

  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Dashboard data
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [measures, setMeasures] = useState([]);
  const [trend, setTrend] = useState([]);
  const [bottlenecks, setBottlenecks] = useState([]);
  const [runRates, setRunRates] = useState(null);

  // Modal state
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingMeasure, setEditingMeasure] = useState(null);

  // Drill-down modal state
  const [showDrillDown, setShowDrillDown] = useState(false);
  const [drillDownType, setDrillDownType] = useState(null); // 'on_track', 'at_risk', 'overdue', 'health'
  const [drillDownMilestoneType, setDrillDownMilestoneType] = useState(null); // For direct milestone drill-down

  // Drag-and-drop state
  const [draggedItem, setDraggedItem] = useState(null);
  const [measureOrder, setMeasureOrder] = useState([]);
  const [dragOverItem, setDragOverItem] = useState(null);

  // Inline editing state
  const [editingCell, setEditingCell] = useState(null); // { measureId, field }
  const [pendingChanges, setPendingChanges] = useState({}); // { measureId: { field: value } }

  // Reports state
  const [teamMembers, setTeamMembers] = useState([]);
  const [reportHistory, setReportHistory] = useState([]);
  const [sendingReport, setSendingReport] = useState(false);

  // Workflow options for dropdown
  const [workflows, setWorkflows] = useState([]);

  const fetchDashboard = useCallback(async () => {
    try {
      setLoading(true);
      const token = getToken();
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };

      // Fetch dashboard summary
      const summaryRes = await fetch(`${API_BASE_URL}/api/v1/sla/dashboard/summary`, { headers });
      if (summaryRes.ok) {
        const summaryData = await summaryRes.json();
        setSummary(summaryData);
      }

      // Fetch alerts
      const alertsRes = await fetch(`${API_BASE_URL}/api/v1/sla/alerts?limit=10`, { headers });
      if (alertsRes.ok) {
        const alertsData = await alertsRes.json();
        setAlerts(alertsData);
      }

      // Fetch measures (including inactive ones so they can be reactivated)
      const measuresRes = await fetch(`${API_BASE_URL}/api/v1/sla/measures?active_only=false`, { headers });
      if (measuresRes.ok) {
        const measuresData = await measuresRes.json();
        setMeasures(measuresData);
      }

      // Fetch trend data
      const trendRes = await fetch(`${API_BASE_URL}/api/v1/sla/dashboard/trend`, { headers });
      if (trendRes.ok) {
        const trendData = await trendRes.json();
        setTrend(trendData.data_points || []);
      }

      // Fetch bottlenecks
      const bottlenecksRes = await fetch(`${API_BASE_URL}/api/v1/sla/dashboard/bottlenecks`, { headers });
      if (bottlenecksRes.ok) {
        const bottlenecksData = await bottlenecksRes.json();
        setBottlenecks(bottlenecksData.bottlenecks || []);
      }

      // Fetch run rates
      const runRatesRes = await fetch(`${API_BASE_URL}/api/v1/sla/dashboard/run-rates`, { headers });
      if (runRatesRes.ok) {
        const runRatesData = await runRatesRes.json();
        setRunRates(runRatesData);
      }

      // Fetch team members for reports
      try {
        const usersRes = await fetch(`${API_BASE_URL}/api/v1/users`, { headers });
        if (usersRes.ok) {
          const usersData = await usersRes.json();
          setTeamMembers(usersData.users || usersData || []);
        }
      } catch (e) {
        // Users endpoint might not exist, use empty array
        setTeamMembers([]);
      }

      // Fetch available workflows for measure assignment dropdown
      try {
        const workflowsRes = await fetch(`${API_BASE_URL}/api/v1/sla/workflows`, { headers });
        if (workflowsRes.ok) {
          const workflowsData = await workflowsRes.json();
          setWorkflows(workflowsData || []);
        }
      } catch (e) {
        // Workflows endpoint might not exist yet
        setWorkflows([]);
      }

      setError(null);
    } catch (err) {
      setError('Failed to load SLA data');
      console.error('Error fetching SLA data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  const runMigration = async () => {
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/sla/migrate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      if (response.ok) {
        toast.success('SLA tables created and default measures seeded!');
        fetchDashboard();
      } else {
        toast.error('Failed to run migration');
      }
    } catch (err) {
      console.error('Migration error:', err);
      toast.error('Migration failed: ' + err.message);
    }
  };

  const acknowledgeAlert = async (alertId) => {
    try {
      const token = getToken();
      await fetch(`${API_BASE_URL}/api/v1/sla/alerts/${alertId}/acknowledge`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
      });
      fetchDashboard();
    } catch (err) {
      console.error('Error acknowledging alert:', err);
    }
  };

  const resolveAlert = async (alertId) => {
    try {
      const token = getToken();
      await fetch(`${API_BASE_URL}/api/v1/sla/alerts/${alertId}/resolve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ resolution_notes: 'Resolved from dashboard' })
      });
      fetchDashboard();
    } catch (err) {
      console.error('Error resolving alert:', err);
    }
  };

  const saveMeasure = async (measureData) => {
    try {
      const token = getToken();
      const method = editingMeasure ? 'PUT' : 'POST';
      const url = editingMeasure
        ? `${API_BASE_URL}/api/v1/sla/measures/${editingMeasure.id}`
        : `${API_BASE_URL}/api/v1/sla/measures`;

      await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(measureData)
      });
      setShowEditModal(false);
      setEditingMeasure(null);
      fetchDashboard();
    } catch (err) {
      console.error('Error saving measure:', err);
    }
  };

  // Inline edit handlers
  const handleInlineEdit = (measureId, field, value) => {
    setPendingChanges(prev => ({
      ...prev,
      [measureId]: {
        ...(prev[measureId] || {}),
        [field]: value
      }
    }));
    // Update local state immediately for responsive UI
    // For workflow changes, also update the display name
    if (field === 'workflow_configuration_id') {
      const selectedWorkflow = workflows.find(wf => wf.id === value);
      setMeasures(prev => prev.map(m =>
        m.id === measureId ? {
          ...m,
          [field]: value,
          workflow_name: selectedWorkflow?.workflow_name || null,
          workflow_key: selectedWorkflow?.workflow_key || null
        } : m
      ));
    } else {
      setMeasures(prev => prev.map(m =>
        m.id === measureId ? { ...m, [field]: value } : m
      ));
    }
  };

  const saveInlineEdit = async (measureId, field) => {
    const measure = measures.find(m => m.id === measureId);
    if (!measure) return;

    const changes = pendingChanges[measureId] || {};
    if (Object.keys(changes).length === 0) {
      setEditingCell(null);
      return;
    }

    try {
      const token = getToken();
      await fetch(`${API_BASE_URL}/api/v1/sla/measures/${measureId}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(changes)
      });

      // Clear pending changes for this measure
      setPendingChanges(prev => {
        const newPending = { ...prev };
        delete newPending[measureId];
        return newPending;
      });
      setEditingCell(null);
    } catch (err) {
      console.error('Error saving inline edit:', err);
      // Revert on error
      fetchDashboard();
    }
  };

  const cancelInlineEdit = (measureId) => {
    // Revert local changes
    setPendingChanges(prev => {
      const newPending = { ...prev };
      delete newPending[measureId];
      return newPending;
    });
    setEditingCell(null);
    fetchDashboard(); // Refresh to get original values
  };

  // Trigger From options for inline dropdown - consolidated list
  const triggerFromOptions = [
    { value: 'lead_created', label: 'Lead Created' },
    { value: 'loan_created', label: 'Loan Created' },
    { value: 'previous_milestone', label: 'Previous Milestone' },
    { value: 'lead_response', label: 'Lead Response' },
    { value: 'application_completed', label: 'Application Completed' },
    { value: 'pre_qualified', label: 'Pre-Qualified' },
    { value: 'preapproval', label: 'Pre-Approval' },
    { value: 'contract_received', label: 'Contract Received' },
    { value: 'disclosed', label: 'Disclosed' },
    { value: 'application_submitted', label: 'Application Submitted' },
    { value: 'submitted_to_processing', label: 'Submitted to Processing' },
    { value: 'appraisal_ordered', label: 'Appraisal Ordered' },
    { value: 'appraisal_received', label: 'Appraisal Received' },
    { value: 'title_ordered', label: 'Title Ordered' },
    { value: 'title_received', label: 'Title Received' },
    { value: 'insurance_ordered', label: 'Insurance Ordered' },
    { value: 'insurance_received', label: 'Insurance Received' },
    { value: 'submitted_to_uw', label: 'Submitted to Underwriting' },
    { value: 'uw_decision', label: 'Underwriting Decision' },
    { value: 'approved', label: 'Approved' },
    { value: 'clear_to_close', label: 'Clear to Close' },
    { value: 'closing_docs_out', label: 'Closing Docs Out' },
    { value: 'closing_scheduled', label: 'Closing Scheduled' },
    { value: 'closing_date', label: 'Closing Date' },
    { value: 'funded', label: 'Loan Funded' }
  ];

  const toggleMeasureActive = async (measureId, newActiveState) => {
    try {
      const token = getToken();
      await fetch(`${API_BASE_URL}/api/v1/sla/measures/${measureId}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ is_active: newActiveState })
      });
      fetchDashboard();
    } catch (err) {
      console.error('Error toggling measure active state:', err);
    }
  };

  const deleteMeasure = async (measureId) => {
    if (!window.confirm('Are you sure you want to delete this SLA measure? This action cannot be undone.')) {
      return;
    }
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/sla/measures/${measureId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        // Immediately remove from local state for instant UI feedback
        setMeasures(prev => prev.filter(m => m.id !== measureId));
        toast.success('Measure deleted successfully');
        // Then refresh from server to ensure consistency
        fetchDashboard();
      } else {
        const error = await response.json().catch(() => ({}));
        console.error('Error deleting measure:', error);
        toast.error('Failed to delete measure: ' + (error.detail || 'Please try again.'));
      }
    } catch (err) {
      console.error('Error deleting measure:', err);
      toast.error('Failed to delete measure. Please try again.');
    }
  };

  const sendReport = async (emailAddress, options = {}) => {
    try {
      setSendingReport(true);
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/sla/reports/send-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          email_address: emailAddress,
          include_run_rates: options.includeRunRates !== false,
          include_forecasts: options.includeForecasts !== false,
          include_bottlenecks: options.includeBottlenecks !== false
        })
      });

      if (response.ok) {
        const result = await response.json();
        // Add to history
        setReportHistory(prev => [{
          id: Date.now(),
          email: emailAddress,
          sentAt: new Date().toISOString(),
          status: 'sent',
          summary: result.report_summary
        }, ...prev.slice(0, 9)]);
        return { success: true, message: `Report sent to ${emailAddress}` };
      } else {
        const error = await response.json();
        return { success: false, message: error.detail || 'Failed to send report' };
      }
    } catch (err) {
      console.error('Error sending report:', err);
      return { success: false, message: 'Failed to send report' };
    } finally {
      setSendingReport(false);
    }
  };

  const formatMilestoneType = (type) => {
    return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  // Handle drill-down click on summary cards
  const handleDrillDown = (type, milestoneType = null) => {
    setDrillDownType(type);
    setDrillDownMilestoneType(milestoneType);
    setShowDrillDown(true);
  };

  // Handle milestone row click to open drill-down directly to loans
  const handleMilestoneRowClick = (milestoneType) => {
    setDrillDownType('on_track'); // Default to showing all statuses
    setDrillDownMilestoneType(milestoneType);
    setShowDrillDown(true);
  };

  // Get drill-down data based on type
  const getDrillDownData = () => {
    if (!summary?.milestone_breakdown) return [];

    const breakdown = summary.milestone_breakdown;
    let items = [];

    Object.entries(breakdown).forEach(([milestoneType, stats]) => {
      if (drillDownType === 'on_track') {
        const onTrack = stats.total - (stats.at_risk || 0) - (stats.overdue || 0);
        if (onTrack > 0) {
          items.push({
            milestone_type: milestoneType,
            count: onTrack,
            status: 'on_track',
            details: `${onTrack} of ${stats.total} loans on track`
          });
        }
      } else if (drillDownType === 'at_risk') {
        if (stats.at_risk > 0) {
          items.push({
            milestone_type: milestoneType,
            count: stats.at_risk,
            status: 'at_risk',
            details: `${stats.at_risk} loans approaching deadline`
          });
        }
      } else if (drillDownType === 'overdue') {
        if (stats.overdue > 0) {
          items.push({
            milestone_type: milestoneType,
            count: stats.overdue,
            status: 'overdue',
            details: `${stats.overdue} loans past deadline`
          });
        }
      }
    });

    return items.sort((a, b) => b.count - a.count);
  };

  // Drag-and-drop handlers
  const handleDragStart = (e, measure) => {
    setDraggedItem(measure);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', measure.id.toString());
    // Add a slight delay to make the dragging visual more apparent
    setTimeout(() => {
      e.target.closest('tr').style.opacity = '0.4';
    }, 0);
  };

  const handleDragOver = (e, measure) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (measure && draggedItem && measure.id !== draggedItem.id) {
      setDragOverItem(measure.id);
    }
  };

  const handleDragLeave = (e) => {
    // Only clear if we're leaving the row entirely
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setDragOverItem(null);
    }
  };

  const handleDrop = async (e, targetMeasure) => {
    e.preventDefault();
    setDragOverItem(null);
    if (!draggedItem || draggedItem.id === targetMeasure.id) {
      setDraggedItem(null);
      return;
    }

    // Get all sorted measures
    const allItems = [...sortedMeasures];
    const draggedIdx = allItems.findIndex(m => m.id === draggedItem.id);
    const targetIdx = allItems.findIndex(m => m.id === targetMeasure.id);

    // Create new order
    const newItems = [...allItems];
    newItems.splice(draggedIdx, 1);
    newItems.splice(targetIdx, 0, draggedItem);

    // Update measures state to reflect new order with sequential display_order values
    const newMeasures = newItems.map((m, idx) => ({ ...m, display_order: idx }));
    setMeasures(newMeasures);

    // Update the local order display
    const newOrder = newItems.map(m => m.id);
    setMeasureOrder(newOrder);

    // Save the new order to the backend
    try {
      const token = getToken();
      // Update each measure with its new display_order
      for (let i = 0; i < newItems.length; i++) {
        const measure = newItems[i];
        await fetch(`${API_BASE_URL}/api/v1/sla/measures/${measure.id}`, {
          method: 'PUT',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ display_order: i })
        });
      }
    } catch (err) {
      console.error('Error saving measure order:', err);
    }

    setDraggedItem(null);
  };

  const handleDragEnd = (e) => {
    setDraggedItem(null);
    setDragOverItem(null);
    // Reset opacity
    if (e.target.closest('tr')) {
      e.target.closest('tr').style.opacity = '1';
    }
  };

  // Sort measures by display_order only - user controls the complete order
  const sortedMeasures = [...measures].sort((a, b) => {
    // Sort by display_order if set, otherwise by id as fallback
    const orderA = a.display_order !== undefined && a.display_order !== null ? a.display_order : 9999;
    const orderB = b.display_order !== undefined && b.display_order !== null ? b.display_order : 9999;
    if (orderA !== orderB) return orderA - orderB;
    return a.id - b.id;
  });

  // Render a single measure row with drag-and-drop support and inline editing
  const renderMeasureRow = (measure) => {
    const isEditingTarget = editingCell?.measureId === measure.id && editingCell?.field === 'target';
    const isEditingTrigger = editingCell?.measureId === measure.id && editingCell?.field === 'trigger';
    const isEditingWarning = editingCell?.measureId === measure.id && editingCell?.field === 'warning';
    const isEditingWorkflow = editingCell?.measureId === measure.id && editingCell?.field === 'workflow';
    const hasPendingChanges = pendingChanges[measure.id] && Object.keys(pendingChanges[measure.id]).length > 0;

    return (
      <tr
        key={measure.id}
        draggable="true"
        onDragStart={(e) => handleDragStart(e, measure)}
        onDragOver={(e) => handleDragOver(e, measure)}
        onDragLeave={handleDragLeave}
        onDrop={(e) => handleDrop(e, measure)}
        onDragEnd={handleDragEnd}
        className={`draggable-row ${draggedItem?.id === measure.id ? 'dragging' : ''} ${dragOverItem === measure.id ? 'drag-over' : ''}`}
        style={{
          cursor: 'grab',
          transition: 'all 0.2s ease',
          background: hasPendingChanges ? '#fffbeb' : dragOverItem === measure.id ? '#e0f2f1' : undefined,
          borderTop: dragOverItem === measure.id ? '3px solid #1F3D2E' : undefined
        }}
      >
        <td>
          <div>
            <div className="milestone-name">{measure.name}</div>
            <div className="milestone-type">{formatMilestoneType(measure.milestone_type)}</div>
          </div>
        </td>

        {/* Inline editable Target column */}
        <td
          onClick={() => !isEditingTarget && setEditingCell({ measureId: measure.id, field: 'target' })}
          style={{ cursor: 'pointer' }}
          title="Click to edit"
        >
          {isEditingTarget ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <input
                type="number"
                value={measure.target_value}
                onChange={(e) => handleInlineEdit(measure.id, 'target_value', parseFloat(e.target.value) || 0)}
                style={{
                  width: '50px',
                  padding: '4px 6px',
                  border: '1px solid #1F3D2E',
                  borderRadius: '4px',
                  fontSize: '13px'
                }}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') saveInlineEdit(measure.id, 'target');
                  if (e.key === 'Escape') cancelInlineEdit(measure.id);
                }}
              />
              <select
                value={measure.target_unit}
                onChange={(e) => handleInlineEdit(measure.id, 'target_unit', e.target.value)}
                style={{
                  padding: '4px 6px',
                  border: '1px solid #1F3D2E',
                  borderRadius: '4px',
                  fontSize: '13px'
                }}
              >
                <option value="hours">hours</option>
                <option value="days">days</option>
                <option value="business_days">biz days</option>
              </select>
              <button
                onClick={(e) => { e.stopPropagation(); saveInlineEdit(measure.id, 'target'); }}
                style={{
                  padding: '4px 8px',
                  background: '#1F3D2E',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '11px'
                }}
              >
                ✓
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); cancelInlineEdit(measure.id); }}
                style={{
                  padding: '4px 8px',
                  background: '#f3f4f6',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '11px'
                }}
              >
                ✕
              </button>
            </div>
          ) : (
            <span className="target-badge editable-cell" style={{
              borderBottom: '1px dashed #9ca3af',
              paddingBottom: '2px'
            }}>
              {formatTargetUnit(measure.target_value, measure.target_unit)}
            </span>
          )}
        </td>

        {/* Inline editable Trigger From column */}
        <td
          onClick={() => !isEditingTrigger && setEditingCell({ measureId: measure.id, field: 'trigger' })}
          style={{ cursor: 'pointer' }}
          title="Click to edit"
        >
          {isEditingTrigger ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <select
                value={measure.trigger_from || 'previous_milestone'}
                onChange={(e) => handleInlineEdit(measure.id, 'trigger_from', e.target.value)}
                style={{
                  padding: '4px 6px',
                  border: '1px solid #1F3D2E',
                  borderRadius: '4px',
                  fontSize: '13px',
                  maxWidth: '150px'
                }}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') saveInlineEdit(measure.id, 'trigger');
                  if (e.key === 'Escape') cancelInlineEdit(measure.id);
                }}
              >
                {triggerFromOptions.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <button
                onClick={(e) => { e.stopPropagation(); saveInlineEdit(measure.id, 'trigger'); }}
                style={{
                  padding: '4px 8px',
                  background: '#1F3D2E',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '11px'
                }}
              >
                ✓
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); cancelInlineEdit(measure.id); }}
                style={{
                  padding: '4px 8px',
                  background: '#f3f4f6',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '11px'
                }}
              >
                ✕
              </button>
            </div>
          ) : (
            <span style={{
              fontSize: '13px',
              color: '#4b5563',
              borderBottom: '1px dashed #9ca3af',
              paddingBottom: '2px'
            }}>
              {formatMilestoneType(measure.trigger_from || 'previous_milestone')}
              {measure.trigger_from_is_default && (
                <span style={{
                  marginLeft: '6px',
                  fontSize: '10px',
                  padding: '2px 6px',
                  background: '#dbeafe',
                  color: '#1d4ed8',
                  borderRadius: '10px'
                }}>
                  Default
                </span>
              )}
            </span>
          )}
        </td>

        {/* Inline editable Warning At column */}
        <td
          onClick={() => !isEditingWarning && setEditingCell({ measureId: measure.id, field: 'warning' })}
          style={{ cursor: 'pointer' }}
          title="Click to edit"
        >
          {isEditingWarning ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <input
                type="number"
                value={measure.warning_threshold_pct}
                onChange={(e) => handleInlineEdit(measure.id, 'warning_threshold_pct', parseFloat(e.target.value) || 0)}
                min="0"
                max="100"
                style={{
                  width: '50px',
                  padding: '4px 6px',
                  border: '1px solid #1F3D2E',
                  borderRadius: '4px',
                  fontSize: '13px'
                }}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') saveInlineEdit(measure.id, 'warning');
                  if (e.key === 'Escape') cancelInlineEdit(measure.id);
                }}
              />
              <span style={{ fontSize: '13px' }}>%</span>
              <button
                onClick={(e) => { e.stopPropagation(); saveInlineEdit(measure.id, 'warning'); }}
                style={{
                  padding: '4px 8px',
                  background: '#1F3D2E',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '11px'
                }}
              >
                ✓
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); cancelInlineEdit(measure.id); }}
                style={{
                  padding: '4px 8px',
                  background: '#f3f4f6',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '11px'
                }}
              >
                ✕
              </button>
            </div>
          ) : (
            <span style={{
              borderBottom: '1px dashed #9ca3af',
              paddingBottom: '2px'
            }}>
              {measure.warning_threshold_pct}%
            </span>
          )}
        </td>

        {/* Inline editable Workflow column */}
        <td
          onClick={() => !isEditingWorkflow && setEditingCell({ measureId: measure.id, field: 'workflow' })}
          style={{ cursor: 'pointer' }}
          title="Click to assign workflow"
        >
          {isEditingWorkflow ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <select
                value={measure.workflow_configuration_id || ''}
                onChange={(e) => handleInlineEdit(measure.id, 'workflow_configuration_id', e.target.value ? parseInt(e.target.value) : null)}
                style={{
                  padding: '4px 6px',
                  border: '1px solid #1F3D2E',
                  borderRadius: '4px',
                  fontSize: '13px',
                  minWidth: '120px'
                }}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') saveInlineEdit(measure.id, 'workflow');
                  if (e.key === 'Escape') cancelInlineEdit(measure.id);
                }}
              >
                <option value="">-- None --</option>
                {workflows.map(wf => (
                  <option key={wf.id} value={wf.id}>{wf.workflow_name}</option>
                ))}
              </select>
              <button
                onClick={(e) => { e.stopPropagation(); saveInlineEdit(measure.id, 'workflow'); }}
                style={{
                  padding: '4px 8px',
                  background: '#1F3D2E',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '11px'
                }}
              >
                ✓
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); cancelInlineEdit(measure.id); }}
                style={{
                  padding: '4px 8px',
                  background: '#f3f4f6',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '11px'
                }}
              >
                ✕
              </button>
            </div>
          ) : (
            <span style={{
              fontSize: '13px',
              color: measure.workflow_name ? '#4b5563' : '#9ca3af',
              borderBottom: '1px dashed #9ca3af',
              paddingBottom: '2px'
            }}>
              {measure.workflow_name || '-- None --'}
            </span>
          )}
        </td>

        <td>
          <div className={`status-indicator ${measure.is_active ? 'active' : 'inactive'}`}>
            <span className="dot"></span>
            {measure.is_active ? 'Active' : 'Inactive'}
          </div>
        </td>
        <td>
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            <button
              onClick={() => {
                setEditingMeasure(measure);
                setShowEditModal(true);
              }}
              style={{
                padding: '6px 12px',
                background: '#f3f4f6',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '13px'
              }}
            >
              Edit
            </button>
            <button
              onClick={() => toggleMeasureActive(measure.id, !measure.is_active)}
              style={{
                padding: '6px 12px',
                background: measure.is_active ? '#fef3c7' : '#d1fae5',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '13px',
                color: measure.is_active ? '#92400e' : '#065f46'
              }}
              title={measure.is_active ? 'Deactivate this measure' : 'Activate this measure'}
            >
              {measure.is_active ? 'Deactivate' : 'Activate'}
            </button>
            <button
              onClick={() => deleteMeasure(measure.id)}
              style={{
                padding: '6px 12px',
                background: '#fee2e2',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '13px',
                color: '#991b1b'
              }}
              title="Delete this measure"
            >
              Delete
            </button>
          </div>
        </td>
      </tr>
    );
  };

  const formatTargetUnit = (value, unit) => {
    const absValue = Math.abs(value);
    const unitLabel = unit === 'hours' ? 'hours' : unit === 'days' ? 'days' : 'business days';

    if (value < 0) {
      return `${absValue} ${unitLabel} before`;
    }
    return `${absValue} ${unitLabel}`;
  };

  // Access denied if user doesn't have SLA permissions
  if (!canAccessSLA) {
    return (
      <div className="sla-settings-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access SLA Settings.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="sla-settings-page">
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <span>Loading SLA data...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="sla-settings-page">
      <div className="page-header">
        <h1>SLA Tracking</h1>
        <p>Monitor loan lifecycle milestones and service level agreements</p>
      </div>

      {/* Dashboard Summary - Clickable Cards */}
      <div className="sla-dashboard-summary">
        <div
          className="summary-card on-track clickable"
          onClick={() => handleDrillDown('on_track')}
          title="Click to see details"
        >
          <div className="card-label">On Track</div>
          <div className="card-value">{summary?.on_track_count || 0}</div>
          <div className="card-sub">milestones within SLA</div>
          <div className="card-drill-hint">Click for details</div>
        </div>
        <div
          className="summary-card at-risk clickable"
          onClick={() => handleDrillDown('at_risk')}
          title="Click to see details"
        >
          <div className="card-label">At Risk</div>
          <div className="card-value">{summary?.at_risk_count || 0}</div>
          <div className="card-sub">approaching deadline</div>
          <div className="card-drill-hint">Click for details</div>
        </div>
        <div
          className="summary-card overdue clickable"
          onClick={() => handleDrillDown('overdue')}
          title="Click to see details"
        >
          <div className="card-label">Overdue</div>
          <div className="card-value">{summary?.overdue_count || 0}</div>
          <div className="card-sub">past deadline</div>
          <div className="card-drill-hint">Click for details</div>
        </div>
        <div
          className="summary-card alerts clickable"
          onClick={() => handleDrillDown('health')}
          title="Click to see details"
        >
          <div className="card-label">Health Score</div>
          <div className="card-value">{runRates?.summary?.health_score || 100}</div>
          <div className="card-sub">out of 100</div>
          <div className="card-drill-hint">Click for details</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="sla-tabs">
        <button
          className={activeTab === 'dashboard' ? 'active' : ''}
          onClick={() => setActiveTab('dashboard')}
        >
          Dashboard
        </button>
        <button
          className={activeTab === 'measures' ? 'active' : ''}
          onClick={() => setActiveTab('measures')}
        >
          SLA Measures
        </button>
        <button
          className={activeTab === 'alerts' ? 'active' : ''}
          onClick={() => setActiveTab('alerts')}
        >
          Alerts ({alerts.length})
        </button>
        <button
          className={activeTab === 'bottlenecks' ? 'active' : ''}
          onClick={() => setActiveTab('bottlenecks')}
        >
          Bottlenecks
        </button>
        <button
          className={activeTab === 'reports' ? 'active' : ''}
          onClick={() => setActiveTab('reports')}
        >
          Reports
        </button>
      </div>

      {/* Dashboard Tab */}
      {activeTab === 'dashboard' && (
        <>
          <div className="sla-section">
            <h2><span className="icon">📊</span> Performance Overview</h2>
            <div className="trend-stats">
              <div className="trend-stat">
                <div className={`value ${(summary?.overall_on_time_rate || 0) >= 85 ? 'positive' : 'negative'}`}>
                  {(summary?.overall_on_time_rate || 0).toFixed(1)}%
                </div>
                <div className="label">On-Time Rate (30 days)</div>
              </div>
              <div className="trend-stat">
                <div className="value">
                  {(summary?.avg_completion_time_hours || 0).toFixed(1)}h
                </div>
                <div className="label">Avg Completion Time</div>
              </div>
              <div className="trend-stat">
                <div className="value">{summary?.total_active_milestones || 0}</div>
                <div className="label">Active Milestones</div>
              </div>
              <div className="trend-stat">
                <div className="value">{measures.length}</div>
                <div className="label">SLA Measures</div>
              </div>
            </div>

            {/* Milestone Breakdown */}
            {summary?.milestone_breakdown && Object.keys(summary.milestone_breakdown).length > 0 && (
              <div style={{ marginTop: '24px' }}>
                <h3 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '12px' }}>
                  Active Milestones by Stage
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '8px' }}>
                  {Object.entries(summary.milestone_breakdown).map(([type, stats]) => (
                    <div key={type} style={{
                      padding: '12px',
                      background: '#f9fafb',
                      borderRadius: '8px',
                      fontSize: '13px'
                    }}>
                      <div style={{ fontWeight: '500', marginBottom: '4px' }}>
                        {formatMilestoneType(type)}
                      </div>
                      <div style={{ color: '#6b7280' }}>
                        {stats.total} total
                        {stats.at_risk > 0 && <span style={{ color: '#f59e0b' }}> ({stats.at_risk} at risk)</span>}
                        {stats.overdue > 0 && <span style={{ color: '#ef4444' }}> ({stats.overdue} overdue)</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Recent Alerts Preview */}
          {alerts.length > 0 && (
            <div className="sla-section">
              <h2><span className="icon">🔔</span> Recent Alerts</h2>
              <div className="alerts-list">
                {alerts.slice(0, 3).map((alert) => (
                  <div key={alert.id} className={`alert-item ${alert.alert_type}`}>
                    <span className="alert-icon">
                      {alert.alert_type === 'overdue' ? '🚨' : alert.alert_type === 'at_risk' ? '⚠️' : 'ℹ️'}
                    </span>
                    <div className="alert-content">
                      <div className="alert-title">{alert.title}</div>
                      <div className="alert-message">{alert.message}</div>
                      <div className="alert-meta">
                        <span>Loan: {alert.loan_number || alert.loan_id || 'N/A'}</span>
                        <span>Triggered: {new Date(alert.triggered_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                    <div className="alert-actions">
                      <button className="btn-acknowledge" onClick={() => acknowledgeAlert(alert.id)}>
                        Acknowledge
                      </button>
                      <button className="btn-resolve" onClick={() => resolveAlert(alert.id)}>
                        Resolve
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              {alerts.length > 3 && (
                <button
                  onClick={() => setActiveTab('alerts')}
                  style={{
                    marginTop: '12px',
                    padding: '8px 16px',
                    background: 'none',
                    border: '1px solid #d1d5db',
                    borderRadius: '6px',
                    cursor: 'pointer'
                  }}
                >
                  View All Alerts ({alerts.length})
                </button>
              )}
            </div>
          )}
        </>
      )}

      {/* SLA Measures Tab */}
      {activeTab === 'measures' && (
        <div className="sla-section">
          <h2>
            <span className="icon">⏱️</span> SLA Measures Configuration
            <button
              onClick={() => {
                setEditingMeasure(null);
                setShowEditModal(true);
              }}
              style={{
                marginLeft: 'auto',
                padding: '8px 16px',
                background: '#1F3D2E',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '13px'
              }}
            >
              + Add Measure
            </button>
          </h2>

          {measures.length === 0 ? (
            <div className="empty-state">
              <div className="icon">⏳</div>
              <h3>Loading SLA Measures...</h3>
              <p>Default measures are being initialized automatically</p>
            </div>
          ) : (
            <table className="measures-table">
              <thead>
                <tr>
                  <th>Milestone</th>
                  <th>Target</th>
                  <th>Trigger From</th>
                  <th>Warning At</th>
                  <th>Workflow</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {/* Single unified list - drag to reorder */}
                {sortedMeasures.map((measure) => renderMeasureRow(measure))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Alerts Tab */}
      {activeTab === 'alerts' && (
        <div className="sla-section">
          <h2><span className="icon">🔔</span> All Active Alerts</h2>
          {alerts.length === 0 ? (
            <div className="empty-state">
              <div className="icon">✅</div>
              <h3>No Active Alerts</h3>
              <p>All milestones are on track</p>
            </div>
          ) : (
            <div className="alerts-list">
              {alerts.map((alert) => (
                <div key={alert.id} className={`alert-item ${alert.alert_type}`}>
                  <span className="alert-icon">
                    {alert.alert_type === 'overdue' ? '🚨' : alert.alert_type === 'at_risk' ? '⚠️' : 'ℹ️'}
                  </span>
                  <div className="alert-content">
                    <div className="alert-title">{alert.title}</div>
                    <div className="alert-message">{alert.message}</div>
                    <div className="alert-meta">
                      <span>Loan: {alert.loan_number || alert.loan_id || 'N/A'}</span>
                      <span>Triggered: {new Date(alert.triggered_at).toLocaleString()}</span>
                      <span>Status: {alert.status}</span>
                    </div>
                  </div>
                  <div className="alert-actions">
                    <button className="btn-acknowledge" onClick={() => acknowledgeAlert(alert.id)}>
                      Acknowledge
                    </button>
                    <button className="btn-resolve" onClick={() => resolveAlert(alert.id)}>
                      Resolve
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Bottlenecks Tab */}
      {activeTab === 'bottlenecks' && (
        <div className="sla-section">
          <h2><span className="icon">🚧</span> Bottleneck Analysis</h2>
          <p style={{ color: '#6b7280', marginBottom: '20px' }}>
            Stages causing the most delays based on the last 30 days of data
          </p>
          {bottlenecks.length === 0 ? (
            <div className="empty-state">
              <div className="icon">📈</div>
              <h3>No Bottlenecks Detected</h3>
              <p>All stages are performing within acceptable parameters</p>
            </div>
          ) : (
            <div className="bottleneck-list">
              {bottlenecks.map((bottleneck, index) => (
                <div key={bottleneck.milestone_type} className="bottleneck-item">
                  <div className={`bottleneck-rank ${index === 1 ? 'rank-2' : index === 2 ? 'rank-3' : ''}`}>
                    {index + 1}
                  </div>
                  <div className="bottleneck-content">
                    <div className="bottleneck-name">{formatMilestoneType(bottleneck.milestone_type)}</div>
                    <div className="bottleneck-stats">
                      <span>Avg delay: {bottleneck.avg_delay_hours?.toFixed(1) || 0} hours</span>
                      <span>Frequency: {bottleneck.delay_frequency_pct?.toFixed(0) || 0}% of loans</span>
                      <span>Affected: {bottleneck.total_affected_loans || 0} loans</span>
                    </div>
                  </div>
                  <div className="bottleneck-bar">
                    <div
                      className="fill"
                      style={{ width: `${Math.min(bottleneck.delay_frequency_pct || 0, 100)}%` }}
                    ></div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Reports Tab */}
      {activeTab === 'reports' && (
        <ReportsTab
          runRates={runRates}
          teamMembers={teamMembers}
          reportHistory={reportHistory}
          sendingReport={sendingReport}
          onSendReport={sendReport}
          formatMilestoneType={formatMilestoneType}
          onMilestoneClick={handleMilestoneRowClick}
        />
      )}

      {/* Edit Modal */}
      {showEditModal && (
        <EditMeasureModal
          measure={editingMeasure}
          onSave={saveMeasure}
          onClose={() => {
            setShowEditModal(false);
            setEditingMeasure(null);
          }}
        />
      )}

      {/* Drill-Down Modal */}
      {showDrillDown && (
        <DrillDownModal
          type={drillDownType}
          data={getDrillDownData()}
          summary={summary}
          runRates={runRates}
          alerts={alerts}
          bottlenecks={bottlenecks}
          formatMilestoneType={formatMilestoneType}
          milestoneTypeFilter={drillDownMilestoneType}
          onClose={() => {
            setShowDrillDown(false);
            setDrillDownType(null);
            setDrillDownMilestoneType(null);
          }}
        />
      )}
    </div>
  );
};

// Reports Tab Component
const ReportsTab = ({ runRates, teamMembers, reportHistory, sendingReport, onSendReport, formatMilestoneType, onMilestoneClick }) => {
  const [selectedRecipients, setSelectedRecipients] = useState([]);
  const [customEmail, setCustomEmail] = useState('');
  const [reportOptions, setReportOptions] = useState({
    includeRunRates: true,
    includeForecasts: true,
    includeBottlenecks: true
  });
  const [sendStatus, setSendStatus] = useState(null);

  const handleAddCustomEmail = () => {
    if (customEmail && customEmail.includes('@')) {
      setSelectedRecipients(prev => [...prev, { email: customEmail, name: customEmail }]);
      setCustomEmail('');
    }
  };

  const handleToggleRecipient = (email) => {
    setSelectedRecipients(prev => {
      const exists = prev.find(r => r.email === email);
      if (exists) {
        return prev.filter(r => r.email !== email);
      } else {
        const member = teamMembers.find(m => m.email === email);
        return [...prev, { email, name: member?.full_name || member?.name || email }];
      }
    });
  };

  const handleSendReports = async () => {
    if (selectedRecipients.length === 0) {
      setSendStatus({ type: 'error', message: 'Please select at least one recipient' });
      return;
    }

    setSendStatus({ type: 'sending', message: 'Sending reports...' });
    const results = [];

    for (const recipient of selectedRecipients) {
      const result = await onSendReport(recipient.email, reportOptions);
      results.push({ email: recipient.email, ...result });
    }

    const successCount = results.filter(r => r.success).length;
    const failCount = results.filter(r => !r.success).length;

    if (failCount === 0) {
      setSendStatus({ type: 'success', message: `Successfully sent ${successCount} report(s)` });
    } else {
      setSendStatus({ type: 'warning', message: `Sent ${successCount}, failed ${failCount}` });
    }

    // Clear selection after sending
    setTimeout(() => {
      setSelectedRecipients([]);
      setSendStatus(null);
    }, 3000);
  };

  return (
    <>
      {/* Run Rate Summary */}
      <div className="sla-section">
        <h2><span className="icon">📈</span> Run Rate Summary</h2>
        <p style={{ color: '#6b7280', marginBottom: '20px' }}>
          Current performance metrics and inventory forecasting
        </p>

        {runRates ? (
          <>
            <div className="trend-stats" style={{ marginBottom: '24px' }}>
              <div className="trend-stat">
                <div className="value" style={{ color: runRates.summary?.health_score >= 80 ? '#2D7A52' : runRates.summary?.health_score >= 60 ? '#f59e0b' : '#ef4444' }}>
                  {runRates.summary?.health_score || 100}
                </div>
                <div className="label">Health Score</div>
              </div>
              <div className="trend-stat">
                <div className="value">{runRates.summary?.total_active_milestones || 0}</div>
                <div className="label">Active Milestones</div>
              </div>
              <div className="trend-stat">
                <div className="value" style={{ color: '#f59e0b' }}>{runRates.summary?.total_at_risk || 0}</div>
                <div className="label">At Risk</div>
              </div>
              <div className="trend-stat">
                <div className="value" style={{ color: '#ef4444' }}>{runRates.summary?.total_overdue || 0}</div>
                <div className="label">Overdue</div>
              </div>
            </div>

            {/* Run Rates Table */}
            {runRates.milestone_run_rates && runRates.milestone_run_rates.length > 0 && (
              <table className="measures-table">
                <thead>
                  <tr>
                    <th>Milestone</th>
                    <th>Daily Rate</th>
                    <th>Weekly Rate</th>
                    <th>On-Time %</th>
                    <th>Trend</th>
                    <th>Inventory</th>
                  </tr>
                </thead>
                <tbody>
                  {runRates.milestone_run_rates.map((rr) => {
                    const forecast = runRates.inventory_forecasts?.find(f => f.milestone_type === rr.milestone_type);
                    return (
                      <tr
                        key={rr.milestone_type}
                        onClick={() => onMilestoneClick && onMilestoneClick(rr.milestone_type)}
                        style={{
                          cursor: 'pointer',
                          transition: 'background 0.15s'
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.background = '#f0f9ff'}
                        onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                        title="Click to view loans for this milestone"
                      >
                        <td>
                          <div className="milestone-name" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            {formatMilestoneType(rr.milestone_type)}
                            <span style={{ color: '#9ca3af', fontSize: '12px' }}>→</span>
                          </div>
                        </td>
                        <td>{rr.daily_run_rate}</td>
                        <td>{rr.weekly_run_rate}</td>
                        <td>
                          <span style={{
                            color: rr.on_time_rate >= 85 ? '#2D7A52' : rr.on_time_rate >= 70 ? '#f59e0b' : '#ef4444'
                          }}>
                            {rr.on_time_rate}%
                          </span>
                        </td>
                        <td>
                          <span className={`trend-badge trend-${rr.trend}`}>
                            {rr.trend === 'improving' ? '↑' : rr.trend === 'declining' ? '↓' : '→'} {rr.trend}
                          </span>
                        </td>
                        <td>
                          {forecast?.current_inventory || 0}
                          {forecast?.is_potential_bottleneck && (
                            <span className="bottleneck-warning" title="Potential bottleneck">⚠️</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </>
        ) : (
          <div className="empty-state">
            <div className="icon">📊</div>
            <h3>No Run Rate Data Available</h3>
            <p>Run rate data will appear once milestones are being tracked</p>
          </div>
        )}
      </div>

      {/* Send Reports Section */}
      <div className="sla-section">
        <h2><span className="icon">📧</span> Send Reports</h2>
        <p style={{ color: '#6b7280', marginBottom: '20px' }}>
          Send SLA run rate reports to team members and stakeholders
        </p>

        <div className="report-builder">
          {/* Recipients Selection */}
          <div className="report-recipients">
            <h3 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '12px' }}>Select Recipients</h3>

            {/* Team Members */}
            {teamMembers.length > 0 && (
              <div className="team-members-list" style={{ marginBottom: '16px' }}>
                {teamMembers.map((member) => (
                  <label
                    key={member.email || member.id}
                    className="recipient-checkbox"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '8px 12px',
                      background: selectedRecipients.find(r => r.email === member.email) ? '#e0f2f1' : '#f9fafb',
                      borderRadius: '6px',
                      marginBottom: '8px',
                      cursor: 'pointer',
                      border: selectedRecipients.find(r => r.email === member.email) ? '1px solid #1F3D2E' : '1px solid transparent'
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={!!selectedRecipients.find(r => r.email === member.email)}
                      onChange={() => handleToggleRecipient(member.email)}
                      style={{ marginRight: '10px' }}
                    />
                    <div>
                      <div style={{ fontWeight: '500' }}>{member.full_name || member.name || 'User'}</div>
                      <div style={{ fontSize: '12px', color: '#6b7280' }}>{member.email}</div>
                    </div>
                    {member.role && (
                      <span style={{
                        marginLeft: 'auto',
                        fontSize: '11px',
                        padding: '2px 8px',
                        background: '#e5e7eb',
                        borderRadius: '10px',
                        color: '#6b7280'
                      }}>
                        {member.role}
                      </span>
                    )}
                  </label>
                ))}
              </div>
            )}

            {/* Custom Email Input */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
              <input
                type="email"
                value={customEmail}
                onChange={(e) => setCustomEmail(e.target.value)}
                placeholder="Add custom email address..."
                style={{
                  flex: 1,
                  padding: '10px 12px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '14px'
                }}
                onKeyPress={(e) => e.key === 'Enter' && handleAddCustomEmail()}
              />
              <button
                onClick={handleAddCustomEmail}
                style={{
                  padding: '10px 16px',
                  background: '#f3f4f6',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  cursor: 'pointer'
                }}
              >
                Add
              </button>
            </div>

            {/* Selected Recipients */}
            {selectedRecipients.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '8px' }}>
                  Selected: {selectedRecipients.length} recipient(s)
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {selectedRecipients.map((r) => (
                    <span
                      key={r.email}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '4px 10px',
                        background: '#1F3D2E',
                        color: 'white',
                        borderRadius: '16px',
                        fontSize: '12px'
                      }}
                    >
                      {r.name || r.email}
                      <button
                        onClick={() => setSelectedRecipients(prev => prev.filter(x => x.email !== r.email))}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: 'white',
                          cursor: 'pointer',
                          padding: 0,
                          fontSize: '14px',
                          lineHeight: 1
                        }}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Report Options */}
          <div className="report-options" style={{ marginBottom: '20px' }}>
            <h3 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '12px' }}>Report Contents</h3>
            <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={reportOptions.includeRunRates}
                  onChange={(e) => setReportOptions(prev => ({ ...prev, includeRunRates: e.target.checked }))}
                />
                Run Rates & Trends
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={reportOptions.includeForecasts}
                  onChange={(e) => setReportOptions(prev => ({ ...prev, includeForecasts: e.target.checked }))}
                />
                Inventory Forecasts
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={reportOptions.includeBottlenecks}
                  onChange={(e) => setReportOptions(prev => ({ ...prev, includeBottlenecks: e.target.checked }))}
                />
                Bottleneck Analysis
              </label>
            </div>
          </div>

          {/* Send Button */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button
              onClick={handleSendReports}
              disabled={sendingReport || selectedRecipients.length === 0}
              style={{
                padding: '12px 24px',
                background: selectedRecipients.length === 0 ? '#9ca3af' : '#1F3D2E',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                cursor: selectedRecipients.length === 0 ? 'not-allowed' : 'pointer',
                fontSize: '14px',
                fontWeight: '500',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}
            >
              {sendingReport ? (
                <>
                  <span className="loading-spinner" style={{ width: '16px', height: '16px', marginRight: '4px' }}></span>
                  Sending...
                </>
              ) : (
                <>
                  📧 Send Report{selectedRecipients.length > 1 ? 's' : ''}
                </>
              )}
            </button>

            {sendStatus && (
              <span style={{
                padding: '8px 16px',
                borderRadius: '6px',
                fontSize: '13px',
                background: sendStatus.type === 'success' ? '#d1fae5' : sendStatus.type === 'error' ? '#fee2e2' : sendStatus.type === 'warning' ? '#fef3c7' : '#e0f2fe',
                color: sendStatus.type === 'success' ? '#065f46' : sendStatus.type === 'error' ? '#991b1b' : sendStatus.type === 'warning' ? '#92400e' : '#0369a1'
              }}>
                {sendStatus.message}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Report History */}
      {reportHistory.length > 0 && (
        <div className="sla-section">
          <h2><span className="icon">📋</span> Recent Reports Sent</h2>
          <table className="measures-table">
            <thead>
              <tr>
                <th>Recipient</th>
                <th>Sent At</th>
                <th>Health Score</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {reportHistory.map((report) => (
                <tr key={report.id}>
                  <td>{report.email}</td>
                  <td>{new Date(report.sentAt).toLocaleString()}</td>
                  <td>{report.summary?.health_score || '-'}</td>
                  <td>
                    <span style={{
                      padding: '4px 8px',
                      borderRadius: '10px',
                      fontSize: '12px',
                      background: report.status === 'sent' ? '#d1fae5' : '#fee2e2',
                      color: report.status === 'sent' ? '#065f46' : '#991b1b'
                    }}>
                      {report.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
};

// Edit Measure Modal Component
const EditMeasureModal = ({ measure, onSave, onClose }) => {
  const [formData, setFormData] = useState({
    name: measure?.name || '',
    milestone_type: measure?.milestone_type || 'lead_response',
    description: measure?.description || '',
    target_value: measure?.target_value || 4,
    target_unit: measure?.target_unit || 'hours',
    trigger_from: measure?.trigger_from || 'previous_milestone',
    trigger_from_is_default: measure?.trigger_from_is_default ?? false,
    warning_threshold_pct: measure?.warning_threshold_pct || 75,
    critical_threshold_pct: measure?.critical_threshold_pct || 100,
    business_hours_only: measure?.business_hours_only ?? true,
    is_active: measure?.is_active ?? true
  });

  const milestoneTypes = [
    'lead_created', 'lead_response', 'application_completed', 'application_review', 'pre_qualified', 'preapproval',
    'contract_received', 'disclosed', 'application_submitted', 'documents_requested', 'documents_received',
    'document_collection', 'application_complete',
    'submitted_to_processing', 'processing_start',
    'appraisal_ordered', 'appraisal_received',
    'title_ordered', 'title_received',
    'insurance_ordered', 'insurance_received',
    'submitted_to_uw', 'uw_decision', 'approved',
    'conditions_issued', 'conditions_cleared', 'clear_to_close',
    'closing_docs_out', 'closing_scheduled', 'closing_date', 'closed', 'funded'
  ];

  // Trigger From options - what event starts the SLA timer (same as inline dropdown)
  const triggerFromOptions = [
    { value: 'lead_created', label: 'Lead Created' },
    { value: 'loan_created', label: 'Loan Created' },
    { value: 'previous_milestone', label: 'Previous Milestone' },
    { value: 'lead_response', label: 'Lead Response' },
    { value: 'application_completed', label: 'Application Completed' },
    { value: 'pre_qualified', label: 'Pre-Qualified' },
    { value: 'preapproval', label: 'Pre-Approval' },
    { value: 'contract_received', label: 'Contract Received' },
    { value: 'disclosed', label: 'Disclosed' },
    { value: 'application_submitted', label: 'Application Submitted' },
    { value: 'submitted_to_processing', label: 'Submitted to Processing' },
    { value: 'appraisal_ordered', label: 'Appraisal Ordered' },
    { value: 'appraisal_received', label: 'Appraisal Received' },
    { value: 'title_ordered', label: 'Title Ordered' },
    { value: 'title_received', label: 'Title Received' },
    { value: 'insurance_ordered', label: 'Insurance Ordered' },
    { value: 'insurance_received', label: 'Insurance Received' },
    { value: 'submitted_to_uw', label: 'Submitted to Underwriting' },
    { value: 'uw_decision', label: 'Underwriting Decision' },
    { value: 'approved', label: 'Approved' },
    { value: 'clear_to_close', label: 'Clear to Close' },
    { value: 'closing_docs_out', label: 'Closing Docs Out' },
    { value: 'closing_scheduled', label: 'Closing Scheduled' },
    { value: 'closing_date', label: 'Closing Date' },
    { value: 'funded', label: 'Loan Funded' }
  ];

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(formData);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{measure ? 'Edit SLA Measure' : 'Add SLA Measure'}</h3>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label>Name</label>
              <input
                type="text"
                value={formData.name}
                onChange={e => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Milestone Type</label>
              <select
                value={formData.milestone_type}
                onChange={e => setFormData({ ...formData, milestone_type: e.target.value })}
                disabled={false}
              >
                {milestoneTypes.map(type => (
                  <option key={type} value={type}>
                    {type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Description</label>
              <textarea
                value={formData.description}
                onChange={e => setFormData({ ...formData, description: e.target.value })}
                rows={2}
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Target Value</label>
                <input
                  type="number"
                  value={formData.target_value}
                  onChange={e => setFormData({ ...formData, target_value: parseFloat(e.target.value) })}
                  step="0.5"
                  required
                />
                <p style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                  Use negative values for "before" events (e.g., -10 = 10 days before trigger event)
                </p>
              </div>
              <div className="form-group">
                <label>Target Unit</label>
                <select
                  value={formData.target_unit}
                  onChange={e => setFormData({ ...formData, target_unit: e.target.value })}
                >
                  <option value="hours">Hours</option>
                  <option value="days">Days</option>
                  <option value="business_days">Business Days</option>
                </select>
              </div>
            </div>
            <div className="form-group">
              <label>Trigger From (SLA Timer Starts When)</label>
              <select
                value={formData.trigger_from}
                onChange={e => setFormData({ ...formData, trigger_from: e.target.value })}
                style={{ width: '100%' }}
              >
                {triggerFromOptions.map(opt => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <p style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
                The SLA timer will start counting from this event
              </p>
            </div>
            <div className="form-group">
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  type="checkbox"
                  checked={formData.trigger_from_is_default}
                  onChange={e => setFormData({ ...formData, trigger_from_is_default: e.target.checked })}
                />
                Set as Default Trigger for this Milestone
              </label>
              <p style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
                If checked, this trigger will be the default for all "{formData.milestone_type.replace(/_/g, ' ')}" milestones
              </p>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Warning Threshold (%)</label>
                <input
                  type="number"
                  value={formData.warning_threshold_pct}
                  onChange={e => setFormData({ ...formData, warning_threshold_pct: parseFloat(e.target.value) })}
                  min="0"
                  max="100"
                  required
                />
              </div>
              <div className="form-group">
                <label>Critical Threshold (%)</label>
                <input
                  type="number"
                  value={formData.critical_threshold_pct}
                  onChange={e => setFormData({ ...formData, critical_threshold_pct: parseFloat(e.target.value) })}
                  min="0"
                  max="200"
                  required
                />
              </div>
            </div>
            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={formData.business_hours_only}
                  onChange={e => setFormData({ ...formData, business_hours_only: e.target.checked })}
                  style={{ marginRight: '8px' }}
                />
                Business Hours Only
              </label>
            </div>
            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={e => setFormData({ ...formData, is_active: e.target.checked })}
                  style={{ marginRight: '8px' }}
                />
                Active
              </label>
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn-cancel" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-save">Save Measure</button>
          </div>
        </form>
      </div>
    </div>
  );
};

// Drill-Down Modal Component with Loan-Level Details
const DrillDownModal = ({ type, data, summary, runRates, alerts, bottlenecks, formatMilestoneType, onClose, milestoneTypeFilter = null }) => {
  const [loanData, setLoanData] = React.useState([]);
  const [loadingLoans, setLoadingLoans] = React.useState(false);
  const [selectedMilestoneType, setSelectedMilestoneType] = React.useState(milestoneTypeFilter);
  const [viewMode, setViewMode] = React.useState(milestoneTypeFilter ? 'loans' : 'summary'); // 'summary' or 'loans'

  // Fetch loan-level data when viewing loans
  React.useEffect(() => {
    if (viewMode === 'loans' || milestoneTypeFilter) {
      fetchLoanData();
    }
  }, [type, selectedMilestoneType, viewMode]);

  const fetchLoanData = async () => {
    setLoadingLoans(true);
    try {
      const token = getToken();
      let url = `${API_BASE_URL}/api/v1/sla/milestones/drilldown?status=${type}`;
      if (selectedMilestoneType) {
        url += `&milestone_type=${selectedMilestoneType}`;
      }
      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      if (response.ok) {
        const result = await response.json();
        setLoanData(result.loans || []);
      }
    } catch (err) {
      console.error('Error fetching loan data:', err);
    } finally {
      setLoadingLoans(false);
    }
  };

  const handleMilestoneClick = (milestoneType) => {
    setSelectedMilestoneType(milestoneType);
    setViewMode('loans');
  };

  const handleBackToSummary = () => {
    setSelectedMilestoneType(null);
    setViewMode('summary');
  };

  const getTitle = () => {
    if (selectedMilestoneType) {
      return `${formatMilestoneType(selectedMilestoneType)} - Loans`;
    }
    switch (type) {
      case 'on_track': return 'On Track Milestones';
      case 'at_risk': return 'At Risk Milestones';
      case 'overdue': return 'Overdue Milestones';
      case 'health': return 'Health Score Breakdown';
      default: return 'Details';
    }
  };

  const getIcon = () => {
    switch (type) {
      case 'on_track': return '✅';
      case 'at_risk': return '⚠️';
      case 'overdue': return '🚨';
      case 'health': return '💊';
      default: return '📊';
    }
  };

  const getStatusColor = () => {
    switch (type) {
      case 'on_track': return '#2D7A52';
      case 'at_risk': return '#f59e0b';
      case 'overdue': return '#ef4444';
      case 'health': return '#B8924A';
      default: return '#6b7280';
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0 }).format(amount || 0);
  };

  const formatTimeRemaining = (hours) => {
    if (hours <= 0) return 'Overdue';
    if (hours < 24) return `${hours.toFixed(1)}h`;
    const days = Math.floor(hours / 24);
    const remainingHours = hours % 24;
    return `${days}d ${remainingHours.toFixed(0)}h`;
  };

  // Render loan-level details
  const renderLoansList = () => {
    if (loadingLoans) {
      return (
        <div style={{ textAlign: 'center', padding: '40px' }}>
          <div className="loading-spinner" style={{ margin: '0 auto 16px' }}></div>
          <div style={{ color: '#6b7280' }}>Loading loan details...</div>
        </div>
      );
    }

    if (loanData.length === 0) {
      return (
        <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>
          <div style={{ fontSize: '48px', marginBottom: '12px' }}>📋</div>
          <div style={{ fontWeight: '500' }}>No loans found</div>
          <div style={{ fontSize: '13px', marginTop: '4px' }}>
            No loans match the current filter criteria
          </div>
        </div>
      );
    }

    return (
      <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
          <thead>
            <tr style={{ background: '#f9fafb', position: 'sticky', top: 0 }}>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '600', borderBottom: '1px solid #e5e7eb' }}>Loan</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '600', borderBottom: '1px solid #e5e7eb' }}>Borrower</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '600', borderBottom: '1px solid #e5e7eb' }}>Amount</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '600', borderBottom: '1px solid #e5e7eb' }}>Status</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '600', borderBottom: '1px solid #e5e7eb' }}>LO</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '600', borderBottom: '1px solid #e5e7eb' }}>Time</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '600', borderBottom: '1px solid #e5e7eb' }}>Progress</th>
            </tr>
          </thead>
          <tbody>
            {loanData.map((loan, idx) => (
              <tr
                key={loan.milestone_id || idx}
                style={{
                  borderBottom: '1px solid #e5e7eb',
                  background: loan.is_overdue ? '#fef2f2' : loan.is_at_risk ? '#fffbeb' : 'white',
                  cursor: 'pointer',
                  transition: 'background 0.15s'
                }}
                onClick={() => {
                  if (loan.loan_id) {
                    window.open(`/loans/${loan.loan_id}`, '_blank');
                  } else if (loan.lead_id) {
                    window.open(`/leads/${loan.lead_id}`, '_blank');
                  }
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#f0f9ff'}
                onMouseLeave={(e) => e.currentTarget.style.background = loan.is_overdue ? '#fef2f2' : loan.is_at_risk ? '#fffbeb' : 'white'}
              >
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ fontWeight: '500', color: '#1f2937' }}>{loan.loan_number}</div>
                  <div style={{ fontSize: '11px', color: '#9ca3af' }}>
                    {loan.loan_id ? `Loan #${loan.loan_id}` : `Lead #${loan.lead_id}`}
                  </div>
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ fontWeight: '500' }}>{loan.borrower_name}</div>
                </td>
                <td style={{ padding: '10px 12px', fontWeight: '500' }}>
                  {formatCurrency(loan.loan_amount)}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <span style={{
                    padding: '2px 8px',
                    borderRadius: '10px',
                    fontSize: '11px',
                    fontWeight: '500',
                    background: loan.is_overdue ? '#fee2e2' : loan.is_at_risk ? '#fef3c7' : '#d1fae5',
                    color: loan.is_overdue ? '#991b1b' : loan.is_at_risk ? '#92400e' : '#065f46'
                  }}>
                    {loan.sla_status?.replace(/_/g, ' ') || loan.loan_status}
                  </span>
                </td>
                <td style={{ padding: '10px 12px', fontSize: '12px', color: '#6b7280' }}>
                  {loan.lo_name}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <div style={{
                    fontWeight: '500',
                    color: loan.is_overdue ? '#ef4444' : loan.is_at_risk ? '#f59e0b' : '#2D7A52'
                  }}>
                    {formatTimeRemaining(loan.hours_remaining)}
                  </div>
                  <div style={{ fontSize: '10px', color: '#9ca3af' }}>
                    {loan.target_hours ? `of ${loan.target_hours}h` : ''}
                  </div>
                </td>
                <td style={{ padding: '10px 12px', width: '100px' }}>
                  <div style={{
                    height: '8px',
                    background: '#e5e7eb',
                    borderRadius: '4px',
                    overflow: 'hidden'
                  }}>
                    <div style={{
                      width: `${Math.min(loan.pct_used || 0, 100)}%`,
                      height: '100%',
                      background: loan.is_overdue ? '#ef4444' : loan.is_at_risk ? '#f59e0b' : '#2D7A52',
                      borderRadius: '4px',
                      transition: 'width 0.3s'
                    }}></div>
                  </div>
                  <div style={{ fontSize: '10px', color: '#6b7280', marginTop: '2px', textAlign: 'center' }}>
                    {(loan.pct_used || 0).toFixed(0)}%
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content drill-down-modal" style={{ maxWidth: viewMode === 'loans' ? '900px' : '600px' }} onClick={e => e.stopPropagation()}>
        <div className="modal-header" style={{ borderLeft: `4px solid ${getStatusColor()}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {viewMode === 'loans' && !milestoneTypeFilter && (
              <button
                onClick={handleBackToSummary}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: '4px 8px',
                  borderRadius: '4px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  color: '#6b7280',
                  fontSize: '13px'
                }}
                onMouseEnter={(e) => e.target.style.background = '#f3f4f6'}
                onMouseLeave={(e) => e.target.style.background = 'none'}
              >
                ← Back
              </button>
            )}
            <h3>{getIcon()} {getTitle()}</h3>
          </div>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>
        <div className="modal-body drill-down-body">
          {type === 'health' && viewMode === 'summary' ? (
            // Health Score breakdown
            <div className="health-breakdown">
              <div className="health-score-display" style={{ textAlign: 'center', marginBottom: '24px' }}>
                <div style={{
                  fontSize: '64px',
                  fontWeight: '700',
                  color: (runRates?.summary?.health_score || 100) >= 80 ? '#2D7A52' :
                         (runRates?.summary?.health_score || 100) >= 60 ? '#f59e0b' : '#ef4444'
                }}>
                  {runRates?.summary?.health_score || 100}
                </div>
                <div style={{ color: '#6b7280', fontSize: '14px' }}>Overall Health Score</div>
              </div>

              <div className="health-factors" style={{ display: 'grid', gap: '12px' }}>
                <div className="health-factor" style={{
                  padding: '16px',
                  background: '#f9fafb',
                  borderRadius: '8px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}>
                  <div>
                    <div style={{ fontWeight: '600' }}>On-Time Rate</div>
                    <div style={{ fontSize: '12px', color: '#6b7280' }}>Percentage of milestones completed on time</div>
                  </div>
                  <div style={{
                    fontSize: '24px',
                    fontWeight: '600',
                    color: (summary?.overall_on_time_rate || 0) >= 85 ? '#2D7A52' : '#f59e0b'
                  }}>
                    {(summary?.overall_on_time_rate || 0).toFixed(1)}%
                  </div>
                </div>

                <div className="health-factor" style={{
                  padding: '16px',
                  background: '#f9fafb',
                  borderRadius: '8px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}>
                  <div>
                    <div style={{ fontWeight: '600' }}>Active Milestones</div>
                    <div style={{ fontSize: '12px', color: '#6b7280' }}>Currently being tracked</div>
                  </div>
                  <div style={{ fontSize: '24px', fontWeight: '600', color: '#1f2937' }}>
                    {summary?.total_active_milestones || 0}
                  </div>
                </div>

                <div
                  className="health-factor clickable-card"
                  style={{
                    padding: '16px',
                    background: '#fef3c7',
                    borderRadius: '8px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    cursor: 'pointer',
                    transition: 'transform 0.15s, box-shadow 0.15s'
                  }}
                  onClick={() => { setViewMode('loans'); setSelectedMilestoneType(null); }}
                  onMouseEnter={(e) => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}
                >
                  <div>
                    <div style={{ fontWeight: '600', color: '#92400e' }}>At Risk</div>
                    <div style={{ fontSize: '12px', color: '#b45309' }}>Click to view loans →</div>
                  </div>
                  <div style={{ fontSize: '24px', fontWeight: '600', color: '#f59e0b' }}>
                    {summary?.at_risk_count || 0}
                  </div>
                </div>

                <div
                  className="health-factor clickable-card"
                  style={{
                    padding: '16px',
                    background: '#fee2e2',
                    borderRadius: '8px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    cursor: 'pointer',
                    transition: 'transform 0.15s, box-shadow 0.15s'
                  }}
                  onClick={() => { setViewMode('loans'); setSelectedMilestoneType(null); }}
                  onMouseEnter={(e) => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}
                >
                  <div>
                    <div style={{ fontWeight: '600', color: '#991b1b' }}>Overdue</div>
                    <div style={{ fontSize: '12px', color: '#b91c1c' }}>Click to view loans →</div>
                  </div>
                  <div style={{ fontSize: '24px', fontWeight: '600', color: '#ef4444' }}>
                    {summary?.overdue_count || 0}
                  </div>
                </div>
              </div>

              {/* Top Bottlenecks */}
              {bottlenecks && bottlenecks.length > 0 && (
                <div style={{ marginTop: '24px' }}>
                  <h4 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '12px' }}>
                    Top Bottlenecks Affecting Health
                  </h4>
                  {bottlenecks.slice(0, 3).map((bn, idx) => (
                    <div key={bn.milestone_type} style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      padding: '10px',
                      background: '#f9fafb',
                      borderRadius: '6px',
                      marginBottom: '8px',
                      cursor: 'pointer',
                      transition: 'background 0.15s'
                    }}
                    onClick={() => handleMilestoneClick(bn.milestone_type)}
                    onMouseEnter={(e) => e.currentTarget.style.background = '#e0f2f1'}
                    onMouseLeave={(e) => e.currentTarget.style.background = '#f9fafb'}
                    >
                      <span style={{
                        width: '24px',
                        height: '24px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: idx === 0 ? '#ef4444' : idx === 1 ? '#f59e0b' : '#6b7280',
                        color: 'white',
                        borderRadius: '50%',
                        fontSize: '12px',
                        fontWeight: '600'
                      }}>
                        {idx + 1}
                      </span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: '500' }}>{formatMilestoneType(bn.milestone_type)}</div>
                        <div style={{ fontSize: '12px', color: '#6b7280' }}>
                          {bn.avg_delay_hours?.toFixed(1)}h avg delay • {bn.total_affected_loans} loans
                        </div>
                      </div>
                      <span style={{ color: '#9ca3af', fontSize: '12px' }}>View →</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : viewMode === 'loans' ? (
            // Loan-level detail view
            <div>
              <div style={{
                padding: '12px 16px',
                background: type === 'on_track' ? '#d1fae5' : type === 'at_risk' ? '#fef3c7' : '#fee2e2',
                borderRadius: '8px',
                marginBottom: '16px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <div>
                  <div style={{ fontWeight: '600', color: getStatusColor() }}>
                    {loanData.length} Loans Found
                  </div>
                  <div style={{ fontSize: '12px', color: '#6b7280' }}>
                    {selectedMilestoneType ? formatMilestoneType(selectedMilestoneType) : 'All milestone types'}
                  </div>
                </div>
                <div style={{ fontSize: '12px', color: '#6b7280' }}>
                  Click a row to open loan details
                </div>
              </div>
              {renderLoansList()}
            </div>
          ) : (
            // On Track / At Risk / Overdue breakdown - Summary View
            <div className="milestone-breakdown">
              <div style={{
                padding: '16px',
                background: type === 'on_track' ? '#d1fae5' : type === 'at_risk' ? '#fef3c7' : '#fee2e2',
                borderRadius: '8px',
                marginBottom: '20px',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '48px', fontWeight: '700', color: getStatusColor() }}>
                  {type === 'on_track' ? (summary?.on_track_count || 0) :
                   type === 'at_risk' ? (summary?.at_risk_count || 0) :
                   (summary?.overdue_count || 0)}
                </div>
                <div style={{ color: '#6b7280', fontSize: '14px' }}>
                  {type === 'on_track' ? 'Total On Track' :
                   type === 'at_risk' ? 'Total At Risk' : 'Total Overdue'}
                </div>
                <button
                  onClick={() => setViewMode('loans')}
                  style={{
                    marginTop: '12px',
                    padding: '8px 16px',
                    background: getStatusColor(),
                    color: 'white',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontSize: '13px',
                    fontWeight: '500'
                  }}
                >
                  View All Loans →
                </button>
              </div>

              {data && data.length > 0 ? (
                <div className="breakdown-list" style={{ display: 'grid', gap: '10px' }}>
                  <div style={{ fontSize: '14px', fontWeight: '600', marginBottom: '8px' }}>
                    Breakdown by Milestone (click to drill down)
                  </div>
                  {data.map((item) => (
                    <div
                      key={item.milestone_type}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '12px 16px',
                        background: '#f9fafb',
                        borderRadius: '8px',
                        borderLeft: `3px solid ${getStatusColor()}`,
                        cursor: 'pointer',
                        transition: 'all 0.15s'
                      }}
                      onClick={() => handleMilestoneClick(item.milestone_type)}
                      onMouseEnter={(e) => { e.currentTarget.style.background = '#e0f2f1'; e.currentTarget.style.transform = 'translateX(4px)'; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = '#f9fafb'; e.currentTarget.style.transform = 'none'; }}
                    >
                      <div>
                        <div style={{ fontWeight: '500' }}>{formatMilestoneType(item.milestone_type)}</div>
                        <div style={{ fontSize: '12px', color: '#6b7280' }}>{item.details}</div>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{
                          fontSize: '20px',
                          fontWeight: '600',
                          color: getStatusColor()
                        }}>
                          {item.count}
                        </div>
                        <span style={{ color: '#9ca3af', fontSize: '12px' }}>→</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{
                  textAlign: 'center',
                  padding: '32px',
                  color: '#6b7280'
                }}>
                  <div style={{ fontSize: '32px', marginBottom: '8px' }}>
                    {type === 'on_track' ? '🎉' : type === 'at_risk' ? '✅' : '✅'}
                  </div>
                  <div style={{ fontWeight: '500' }}>
                    {type === 'on_track' ? 'No specific breakdown available' :
                     type === 'at_risk' ? 'No milestones at risk!' :
                     'No overdue milestones!'}
                  </div>
                  <div style={{ fontSize: '13px', marginTop: '4px' }}>
                    {type === 'on_track' ? 'All milestones are performing well' :
                     'All milestones are on track'}
                  </div>
                </div>
              )}

              {/* Related Alerts for At Risk and Overdue */}
              {(type === 'at_risk' || type === 'overdue') && alerts && alerts.length > 0 && (
                <div style={{ marginTop: '24px' }}>
                  <div style={{ fontSize: '14px', fontWeight: '600', marginBottom: '12px' }}>
                    Related Alerts
                  </div>
                  {alerts
                    .filter(a => type === 'overdue' ? a.alert_type === 'overdue' : a.alert_type === 'at_risk')
                    .slice(0, 5)
                    .map((alert) => (
                      <div key={alert.id} style={{
                        padding: '12px',
                        background: type === 'overdue' ? '#fef2f2' : '#fffbeb',
                        border: `1px solid ${type === 'overdue' ? '#fecaca' : '#fcd34d'}`,
                        borderRadius: '6px',
                        marginBottom: '8px',
                        fontSize: '13px'
                      }}>
                        <div style={{ fontWeight: '500' }}>{alert.title}</div>
                        <div style={{ color: '#6b7280', marginTop: '4px' }}>{alert.message}</div>
                        <div style={{ color: '#9ca3af', fontSize: '11px', marginTop: '4px' }}>
                          Loan: {alert.loan_number || alert.loan_id || 'N/A'} •
                          Triggered: {new Date(alert.triggered_at).toLocaleDateString()}
                        </div>
                      </div>
                    ))}
                </div>
              )}
            </div>
          )}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn-cancel" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
};

export default SLASettings;
