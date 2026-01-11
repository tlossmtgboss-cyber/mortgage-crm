/**
 * Process Tab
 * Visual milestone timeline showing loan journey progress
 */
import React, { useState, useEffect } from 'react';

const API_BASE_URL = typeof window !== 'undefined' &&
  (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
  ? 'https://api.perenniaai.com'
  : 'http://localhost:8000';

const ProcessTab = ({ clientId, callSessionId, userRole }) => {
  const [milestones, setMilestones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedMilestone, setExpandedMilestone] = useState(null);
  const [currentStage, setCurrentStage] = useState('');
  const [estimatedClose, setEstimatedClose] = useState(null);
  const [daysInStage, setDaysInStage] = useState(0);

  useEffect(() => {
    fetchProcessData();
  }, [callSessionId]);

  const fetchProcessData = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/calls/${callSessionId}/tabs/process`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (!response.ok) {
        throw new Error('Failed to fetch process data');
      }

      const data = await response.json();
      setMilestones(data.milestones || []);
      setCurrentStage(data.current_stage || '');
      setEstimatedClose(data.estimated_close_date);
      setDaysInStage(data.days_in_current_stage || 0);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching process data:', err);
      setError(err.message);
      // Set default milestones for demo
      setMilestones([
        { id: '1', name: 'Application', status: 'complete', owner: 'Borrower' },
        { id: '2', name: 'Processing', status: 'in_progress', owner: 'Processor' },
        { id: '3', name: 'Underwriting', status: 'pending', owner: 'Underwriter' },
        { id: '4', name: 'Approval', status: 'pending', owner: 'Underwriter' },
        { id: '5', name: 'Clear to Close', status: 'pending', owner: 'Closer' },
        { id: '6', name: 'Closing', status: 'pending', owner: 'Title/Escrow' }
      ]);
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'complete':
        return { bg: '#10b981', border: '#059669' };
      case 'in_progress':
        return { bg: '#2563eb', border: '#1d4ed8' };
      case 'blocked':
        return { bg: '#ef4444', border: '#dc2626' };
      default:
        return { bg: '#d1d5db', border: '#9ca3af' };
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'complete':
        return '✓';
      case 'in_progress':
        return '→';
      case 'blocked':
        return '!';
      default:
        return '';
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '48px' }}>
        <div style={{
          width: '32px',
          height: '32px',
          margin: '0 auto 16px',
          border: '3px solid #e5e7eb',
          borderTopColor: '#2563eb',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite'
        }} />
        <p style={{ color: '#6b7280' }}>Loading process timeline...</p>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div style={{ padding: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <h2 style={{ margin: 0, fontSize: '24px', fontWeight: '700', color: '#111827' }}>
          Your Loan Process
        </h2>
        {estimatedClose && (
          <div style={{
            backgroundColor: '#f0fdf4',
            border: '1px solid #86efac',
            borderRadius: '8px',
            padding: '8px 16px'
          }}>
            <span style={{ color: '#166534', fontSize: '14px' }}>
              📅 Estimated Close: <strong>{estimatedClose}</strong>
            </span>
          </div>
        )}
      </div>

      {/* Horizontal Timeline */}
      <div style={{
        position: 'relative',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        padding: '24px 0'
      }}>
        {milestones.map((milestone, index) => {
          const colors = getStatusColor(milestone.status);
          const isActive = milestone.status === 'in_progress';

          return (
            <React.Fragment key={milestone.id}>
              {/* Milestone Node */}
              <div
                onClick={() => setExpandedMilestone(
                  expandedMilestone === milestone.id ? null : milestone.id
                )}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  cursor: 'pointer',
                  flex: 1
                }}
              >
                <div style={{
                  width: '64px',
                  height: '64px',
                  borderRadius: '50%',
                  backgroundColor: colors.bg,
                  border: `4px solid ${colors.border}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#fff',
                  fontSize: '20px',
                  fontWeight: '600',
                  transition: 'transform 0.2s ease',
                  boxShadow: isActive ? '0 0 0 4px rgba(37, 99, 235, 0.3)' : 'none',
                  animation: isActive ? 'pulse 2s infinite' : 'none'
                }}>
                  {getStatusIcon(milestone.status)}
                </div>
                <span style={{
                  marginTop: '12px',
                  fontSize: '14px',
                  fontWeight: '500',
                  color: milestone.status === 'complete' || isActive ? '#111827' : '#9ca3af',
                  textAlign: 'center'
                }}>
                  {milestone.name}
                </span>
                <span style={{
                  marginTop: '4px',
                  fontSize: '12px',
                  color: '#9ca3af'
                }}>
                  {milestone.owner}
                </span>
              </div>

              {/* Connector Line */}
              {index < milestones.length - 1 && (
                <div style={{
                  flex: 1,
                  height: '4px',
                  backgroundColor: milestones[index + 1].status === 'complete'
                    ? '#10b981'
                    : '#e5e7eb',
                  marginTop: '32px',
                  borderRadius: '2px'
                }} />
              )}
            </React.Fragment>
          );
        })}
        <style>{`
          @keyframes pulse {
            0%, 100% { box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.3); }
            50% { box-shadow: 0 0 0 8px rgba(37, 99, 235, 0.1); }
          }
        `}</style>
      </div>

      {/* Current Stage Info */}
      {currentStage && (
        <div style={{
          backgroundColor: '#eff6ff',
          border: '1px solid #bfdbfe',
          borderRadius: '8px',
          padding: '16px',
          marginTop: '32px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h3 style={{ margin: '0 0 4px', fontSize: '16px', color: '#1e40af' }}>
                Current Stage: {currentStage.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
              </h3>
              <p style={{ margin: 0, fontSize: '14px', color: '#3b82f6' }}>
                {daysInStage} days in this stage
              </p>
            </div>
            <div style={{
              backgroundColor: '#2563eb',
              color: '#fff',
              padding: '8px 16px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500'
            }}>
              In Progress
            </div>
          </div>
        </div>
      )}

      {/* Expanded Milestone Details */}
      {expandedMilestone && (
        <div style={{
          backgroundColor: '#f9fafb',
          border: '1px solid #e5e7eb',
          borderRadius: '8px',
          padding: '24px',
          marginTop: '24px'
        }}>
          {(() => {
            const milestone = milestones.find(m => m.id === expandedMilestone);
            if (!milestone) return null;

            return (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <h3 style={{ margin: '0 0 8px', fontSize: '18px', fontWeight: '600', color: '#111827' }}>
                      {milestone.name}
                    </h3>
                    <p style={{ margin: 0, fontSize: '14px', color: '#6b7280' }}>
                      Responsible: {milestone.owner}
                    </p>
                  </div>
                  <button
                    onClick={() => setExpandedMilestone(null)}
                    style={{
                      background: 'none',
                      border: 'none',
                      fontSize: '20px',
                      cursor: 'pointer',
                      color: '#9ca3af'
                    }}
                  >
                    ×
                  </button>
                </div>

                <div style={{ marginTop: '16px' }}>
                  <div style={{
                    display: 'inline-block',
                    padding: '4px 12px',
                    borderRadius: '9999px',
                    fontSize: '12px',
                    fontWeight: '500',
                    backgroundColor: getStatusColor(milestone.status).bg,
                    color: '#fff',
                    textTransform: 'capitalize'
                  }}>
                    {milestone.status.replace('_', ' ')}
                  </div>
                </div>

                {milestone.estimated_completion && (
                  <div style={{ marginTop: '16px' }}>
                    <p style={{ margin: 0, fontSize: '14px', color: '#6b7280' }}>
                      <strong>Estimated Completion:</strong> {milestone.estimated_completion}
                    </p>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
};

export default ProcessTab;
export { ProcessTab };
