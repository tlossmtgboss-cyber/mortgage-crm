import React, { useState, useEffect, useCallback } from 'react';
import { Outlet, useNavigate, useParams } from 'react-router-dom';
import WorkflowSidebar from './WorkflowSidebar';
import { workflowGraphApi } from '../../services/workflowGraphApi';
import './WorkflowLayout.css';

const DEFAULT_WORKFLOWS = [
  { key: 'prospect', name: 'Prospect', color: '#22c55e', lead_count: 0 },
  { key: 'prequal', name: 'Pre-Qual', color: '#3b82f6', lead_count: 0 },
  { key: 'pre_approved', name: 'Pre-Approved', color: '#8b5cf6', lead_count: 0 },
  { key: 'under_contract', name: 'Under Contract', color: '#f59e0b', lead_count: 0 },
  { key: 'processing', name: 'Processing', color: '#06b6d4', lead_count: 0 },
  { key: 'closing', name: 'Closing', color: '#10b981', lead_count: 0 },
  { key: 'post_close', name: 'Post-Close', color: '#6366f1', lead_count: 0 },
  { key: 'nurture', name: 'Nurture', color: '#ec4899', lead_count: 0 },
];

export default function WorkflowLayout() {
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const { workflowKey } = useParams();
  const navigate = useNavigate();

  const fetchWorkflows = useCallback(async () => {
    try {
      const { data } = await workflowGraphApi.listDefinitions();
      const wfs = (data.workflows || []).filter(w => w.key);
      setWorkflows(wfs.length > 0 ? wfs : DEFAULT_WORKFLOWS);
    } catch (err) {
      console.error('Failed to load workflows:', err);
      setWorkflows(DEFAULT_WORKFLOWS);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchWorkflows(); }, [fetchWorkflows]);

  useEffect(() => {
    if (!loading && !workflowKey && workflows.length > 0) {
      navigate(`/workflow/${workflows[0].key}`, { replace: true });
    }
  }, [loading, workflowKey, workflows, navigate]);

  if (loading) {
    return <div className="wf-loading">Loading workflows...</div>;
  }

  return (
    <div className="wf-layout">
      <WorkflowSidebar workflows={workflows} onRefresh={fetchWorkflows} />
      <div className="wf-main">
        <Outlet context={{ workflows, onRefresh: fetchWorkflows }} />
      </div>
    </div>
  );
}
