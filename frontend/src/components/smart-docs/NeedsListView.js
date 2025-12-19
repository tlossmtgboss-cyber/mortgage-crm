import React, { useState, useEffect } from 'react';
import { smartDocsAPI } from '../../services/smartDocsApi';
import './NeedsListView.css';

function NeedsListView({ loanId, onRequestUpdated }) {
  const [needsList, setNeedsList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (loanId) {
      fetchNeedsList();
    }
  }, [loanId]);

  const fetchNeedsList = async () => {
    try {
      setLoading(true);
      const data = await smartDocsAPI.getNeedsList(loanId);
      setNeedsList(data.requests || []);
    } catch (err) {
      console.error('Error fetching needs list:', err);
      setError('Failed to load needs list');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateNeedsList = async () => {
    try {
      setGenerating(true);
      await smartDocsAPI.generateNeedsList({ loan_id: loanId, borrower_id: 1 });
      await fetchNeedsList();
      if (onRequestUpdated) onRequestUpdated();
    } catch (err) {
      console.error('Error generating needs list:', err);
      setError('Failed to generate needs list');
    } finally {
      setGenerating(false);
    }
  };

  const handleMarkFulfilled = async (requestId) => {
    try {
      // For now, just waive as fulfilled
      await smartDocsAPI.waiveRequest(requestId, 'Marked as fulfilled', 1);
      await fetchNeedsList();
      if (onRequestUpdated) onRequestUpdated();
    } catch (err) {
      console.error('Error updating request:', err);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'fulfilled': return 'green';
      case 'expired': return 'red';
      case 'waived': return 'gray';
      default: return 'orange';
    }
  };

  const getPriorityLabel = (priority) => {
    switch (priority) {
      case 1: return { label: 'Critical', class: 'critical' };
      case 2: return { label: 'High', class: 'high' };
      case 3: return { label: 'Medium', class: 'medium' };
      default: return { label: 'Low', class: 'low' };
    }
  };

  if (loading) {
    return <div className="needs-list-loading">Loading needs list...</div>;
  }

  return (
    <div className="needs-list-view">
      <div className="needs-list-header">
        <h3>Document Needs List</h3>
        <button
          className="generate-btn"
          onClick={handleGenerateNeedsList}
          disabled={generating}
        >
          {generating ? 'Generating...' : 'Generate/Refresh List'}
        </button>
      </div>

      {error && <div className="needs-list-error">{error}</div>}

      {needsList.length === 0 ? (
        <div className="needs-list-empty">
          <p>No document requests yet.</p>
          <p>Click "Generate/Refresh List" to create a needs list based on loan requirements.</p>
        </div>
      ) : (
        <div className="needs-list-items">
          {needsList.map((request) => {
            const priority = getPriorityLabel(request.priority);
            return (
              <div key={request.id} className={`needs-item status-${request.status}`}>
                <div className="needs-item-header">
                  <span className={`priority-badge ${priority.class}`}>{priority.label}</span>
                  <span className={`status-badge ${request.status}`}>{request.status}</span>
                </div>
                <h4>{request.document_category}</h4>
                <p className="description">{request.description}</p>
                <div className="needs-item-meta">
                  {request.due_date && (
                    <span className="due-date">Due: {new Date(request.due_date).toLocaleDateString()}</span>
                  )}
                  {request.requested_at && (
                    <span className="requested-date">Requested: {new Date(request.requested_at).toLocaleDateString()}</span>
                  )}
                </div>
                {request.status === 'pending' && (
                  <div className="needs-item-actions">
                    <button
                      className="btn-small btn-fulfill"
                      onClick={() => handleMarkFulfilled(request.id)}
                    >
                      Mark Fulfilled
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default NeedsListView;
