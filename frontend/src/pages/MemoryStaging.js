import React, { useState, useEffect, useCallback } from 'react';
import { toast } from 'react-toastify';
import api from '../services/api';
import './MemoryStaging.css';

const TABS = [
  { key: 'staging', label: 'Staging Queue' },
  { key: 'shadow', label: 'Shadow Mode' },
  { key: 'audit_sample', label: 'Audit Samples' },
];

const STATUS_OPTIONS = [
  { value: 'pending_review', label: 'Pending Review' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
];

export default function MemoryStaging() {
  const [activeTab, setActiveTab] = useState('staging');
  const [status, setStatus] = useState('pending_review');
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [processingId, setProcessingId] = useState(null);

  const perPage = 50;

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, per_page: perPage, tab: activeTab };
      if (activeTab === 'staging') {
        params.status = status;
      }
      const response = await api.get('/admin/memory-staging', { params });
      setItems(response.data.items || []);
      setTotal(response.data.total || 0);
    } catch (err) {
      toast.error('Failed to load staging items');
    } finally {
      setLoading(false);
    }
  }, [page, status, activeTab]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleApprove = async (id) => {
    setProcessingId(id);
    try {
      const res = await api.post(`/admin/memory-staging/${id}/approve`);
      toast.success(`Approved — memory #${res.data.memory_id} committed`);
      fetchItems();
    } catch (err) {
      toast.error('Approve failed');
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (id) => {
    const reason = window.prompt('Rejection reason (optional):');
    setProcessingId(id);
    try {
      await api.post(`/admin/memory-staging/${id}/reject`, { reason });
      toast.success('Item rejected');
      fetchItems();
    } catch (err) {
      toast.error('Reject failed');
    } finally {
      setProcessingId(null);
    }
  };

  const handleEdit = (item) => {
    setEditingId(item.id);
    setEditForm({
      fact_text: item.fact_text,
      topic: item.topic || '',
      fact_type: item.fact_type,
    });
  };

  const handleEditSave = async (id) => {
    setProcessingId(id);
    try {
      await api.patch(`/admin/memory-staging/${id}`, editForm);
      toast.success('Item updated');
      setEditingId(null);
      fetchItems();
    } catch (err) {
      toast.error('Edit failed');
    } finally {
      setProcessingId(null);
    }
  };

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="memory-staging-page">
      <div className="memory-staging-header">
        <h1>Memory Staging</h1>
        <p className="memory-staging-subtitle">Review and approve AI-extracted borrower memories</p>
      </div>

      <div className="memory-staging-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`memory-staging-tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => { setActiveTab(tab.key); setPage(1); }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'staging' && (
        <div className="memory-staging-filters">
          <label>Status:</label>
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      )}

      {loading ? (
        <div className="memory-staging-loading">Loading...</div>
      ) : items.length === 0 ? (
        <div className="memory-staging-empty">No items to display</div>
      ) : (
        <div className="memory-staging-table-wrapper">
          <table className="memory-staging-table">
            <thead>
              <tr>
                <th>Fact</th>
                <th>Type</th>
                <th>Topic</th>
                <th>Confidence</th>
                <th>Transcript</th>
                <th>Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td className="memory-staging-fact-cell">
                    {editingId === item.id ? (
                      <input
                        type="text"
                        value={editForm.fact_text}
                        onChange={(e) => setEditForm({ ...editForm, fact_text: e.target.value })}
                        className="memory-staging-edit-input"
                      />
                    ) : (
                      item.fact_text
                    )}
                  </td>
                  <td>
                    {editingId === item.id ? (
                      <select
                        value={editForm.fact_type}
                        onChange={(e) => setEditForm({ ...editForm, fact_type: e.target.value })}
                      >
                        <option value="fact">fact</option>
                        <option value="preference">preference</option>
                        <option value="context">context</option>
                        <option value="insight">insight</option>
                        <option value="directive">directive</option>
                      </select>
                    ) : (
                      <span className={`memory-staging-badge type-${item.fact_type}`}>
                        {item.fact_type}
                      </span>
                    )}
                  </td>
                  <td>
                    {editingId === item.id ? (
                      <input
                        type="text"
                        value={editForm.topic}
                        onChange={(e) => setEditForm({ ...editForm, topic: e.target.value })}
                        className="memory-staging-edit-input memory-staging-edit-input--small"
                      />
                    ) : (
                      item.topic || '—'
                    )}
                  </td>
                  <td>
                    <span className={`memory-staging-confidence ${item.confidence >= 0.85 ? 'high' : item.confidence >= 0.6 ? 'medium' : 'low'}`}>
                      {(item.confidence * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="memory-staging-transcript-cell">
                    {item.transcript_span ? (
                      <span className="memory-staging-transcript" title={item.transcript_span}>
                        "{item.transcript_span.substring(0, 80)}{item.transcript_span.length > 80 ? '...' : ''}"
                      </span>
                    ) : '—'}
                  </td>
                  <td>{item.created_at ? new Date(item.created_at).toLocaleDateString() : '—'}</td>
                  <td className="memory-staging-actions">
                    {editingId === item.id ? (
                      <>
                        <button
                          className="memory-staging-btn memory-staging-btn--save"
                          onClick={() => handleEditSave(item.id)}
                          disabled={processingId === item.id}
                        >
                          Save
                        </button>
                        <button
                          className="memory-staging-btn memory-staging-btn--cancel"
                          onClick={() => setEditingId(null)}
                        >
                          Cancel
                        </button>
                      </>
                    ) : item.status === 'pending_review' || item.status === 'shadow_pending' ? (
                      <>
                        <button
                          className="memory-staging-btn memory-staging-btn--approve"
                          onClick={() => handleApprove(item.id)}
                          disabled={processingId === item.id}
                        >
                          Approve
                        </button>
                        <button
                          className="memory-staging-btn memory-staging-btn--reject"
                          onClick={() => handleReject(item.id)}
                          disabled={processingId === item.id}
                        >
                          Reject
                        </button>
                        <button
                          className="memory-staging-btn memory-staging-btn--edit"
                          onClick={() => handleEdit(item)}
                          disabled={processingId === item.id}
                        >
                          Edit
                        </button>
                      </>
                    ) : (
                      <span className={`memory-staging-badge status-${item.review_action || item.status}`}>
                        {item.review_action || item.status}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="memory-staging-pagination">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page} of {totalPages} ({total} total)</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
    </div>
  );
}
