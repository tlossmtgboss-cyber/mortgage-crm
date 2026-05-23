import React, { useState, useEffect, useCallback } from 'react';
import { Outlet, useNavigate, useParams } from 'react-router-dom';
import WorkflowSidebar from './WorkflowSidebar';
import { workflowGraphApi } from '../../services/workflowGraphApi';
import './WorkflowLayout.css';

export default function WorkflowLayout() {
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const { workflowKey } = useParams();
  const navigate = useNavigate();

  const fetchWorkflows = useCallback(async () => {
    try {
      const { data } = await workflowGraphApi.listDefinitions();
      setWorkflows(data.workflows || []);
      if (!workflowKey && data.workflows?.length > 0) {
        navigate(`/workflow/${data.workflows[0].key}`, { replace: true });
      }
    } catch (err) {
      console.error('Failed to load workflows:', err);
    } finally {
      setLoading(false);
    }
  }, [workflowKey, navigate]);

  useEffect(() => { fetchWorkflows(); }, [fetchWorkflows]);

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
