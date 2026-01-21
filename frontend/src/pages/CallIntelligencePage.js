/**
 * Call Intelligence Page
 *
 * Main hub for AI-powered call analysis:
 * - Dashboard: Metrics and overview
 * - Active Calls: Real-time monitoring with live suggestions
 * - Review Queue: Pending calls for review
 * - Completed: Reviewed call history
 * - Settings: Configuration
 */

import React, { useState, useEffect, useCallback } from 'react';
import { toast } from '../utils/toast';
import { callMonitoringAPI } from '../services/api';
import DashboardOverview from '../components/call-intelligence/DashboardOverview';
import ActiveCallsMonitor from '../components/call-intelligence/ActiveCallsMonitor';
import ReviewQueue from '../components/call-intelligence/ReviewQueue';
import CallReviewPanel from '../components/call-intelligence/CallReviewPanel';
import CallToAppConverter from '../components/call-intelligence/CallToAppConverter';
import './CallIntelligencePage.css';

const CallIntelligencePage = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [sessions, setSessions] = useState([]);
  const [activeSessions, setActiveSessions] = useState([]);
  const [pendingSessions, setPendingSessions] = useState([]);
  const [completedSessions, setCompletedSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [reviewData, setReviewData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState({
    pending_reviews: 0,
    active_calls: 0,
    completed_today: 0,
    conversion_rate: 0,
  });
  const [showConverter, setShowConverter] = useState(false);

  // Fetch all sessions
  const fetchSessions = useCallback(async () => {
    try {
      setLoading(true);
      const data = await callMonitoringAPI.listSessions({ page_size: 100 });
      const allSessions = data.sessions || [];
      setSessions(allSessions);

      // Categorize sessions
      const active = allSessions.filter(s =>
        s.status === 'active' || s.status === 'capturing'
      );
      const pending = allSessions.filter(s =>
        s.status === 'completed' && s.approval_status === 'pending'
      );
      const completed = allSessions.filter(s =>
        s.approval_status === 'approved' || s.approval_status === 'rejected'
      );

      setActiveSessions(active);
      setPendingSessions(pending);
      setCompletedSessions(completed);

      // Calculate metrics
      const today = new Date().toISOString().split('T')[0];
      const completedToday = allSessions.filter(s =>
        s.ended_at && s.ended_at.startsWith(today)
      ).length;

      setMetrics({
        pending_reviews: pending.length,
        active_calls: active.length,
        completed_today: completedToday,
        conversion_rate: 0, // Will be calculated from actual conversions
      });

    } catch (error) {
      console.error('Error fetching sessions:', error);
      toast.error('Failed to load call sessions');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch review data for selected session
  const fetchReviewData = async (sessionId) => {
    try {
      const data = await callMonitoringAPI.getReviewData(sessionId);
      setReviewData(data);
    } catch (error) {
      console.error('Error fetching review data:', error);
      toast.error('Failed to load call details');
    }
  };

  // Handle session selection
  const handleSelectSession = (session) => {
    setSelectedSession(session);
    fetchReviewData(session.id);
  };

  // Handle artifact approval
  const handleApproveArtifacts = async (artifactIds) => {
    if (!selectedSession) return;
    try {
      await callMonitoringAPI.approveArtifacts(selectedSession.id, artifactIds);
      toast.success('Artifacts approved');
      fetchReviewData(selectedSession.id);
    } catch (error) {
      console.error('Error approving artifacts:', error);
      toast.error('Failed to approve artifacts');
    }
  };

  // Handle artifact rejection
  const handleRejectArtifacts = async (artifactIds, reason) => {
    if (!selectedSession) return;
    try {
      await callMonitoringAPI.rejectArtifacts(selectedSession.id, artifactIds, reason);
      toast.success('Artifacts rejected');
      fetchReviewData(selectedSession.id);
    } catch (error) {
      console.error('Error rejecting artifacts:', error);
      toast.error('Failed to reject artifacts');
    }
  };

  // Handle execute artifacts
  const handleExecuteArtifacts = async () => {
    if (!selectedSession) return;
    try {
      const data = await callMonitoringAPI.executeArtifacts(selectedSession.id);
      toast.success(`Executed ${data.executed_count} artifacts`);
      fetchReviewData(selectedSession.id);
      fetchSessions(); // Refresh list
    } catch (error) {
      console.error('Error executing artifacts:', error);
      toast.error('Failed to execute artifacts');
    }
  };

  // Handle complete review
  const handleCompleteReview = async () => {
    if (!selectedSession) return;
    try {
      // Mark session as reviewed
      await callMonitoringAPI.updateSession(selectedSession.id, {
        status: 'reviewed'
      });
      toast.success('Review completed');
      setSelectedSession(null);
      setReviewData(null);
      fetchSessions();
    } catch (error) {
      console.error('Error completing review:', error);
      toast.error('Failed to complete review');
    }
  };

  // Handle convert to application
  const handleConvertToApp = () => {
    setShowConverter(true);
  };

  useEffect(() => {
    fetchSessions();

    // Poll for active calls
    const interval = setInterval(() => {
      if (activeTab === 'active' || activeTab === 'dashboard') {
        fetchSessions();
      }
    }, 30000); // Every 30 seconds

    return () => clearInterval(interval);
  }, [fetchSessions, activeTab]);

  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: 'grid' },
    { id: 'active', label: 'Active Calls', icon: 'phone', badge: metrics.active_calls },
    { id: 'review', label: 'Review Queue', icon: 'clipboard', badge: metrics.pending_reviews },
    { id: 'completed', label: 'Completed', icon: 'check-circle' },
  ];

  const renderTabIcon = (icon) => {
    switch (icon) {
      case 'grid':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="7" height="7" />
            <rect x="14" y="3" width="7" height="7" />
            <rect x="14" y="14" width="7" height="7" />
            <rect x="3" y="14" width="7" height="7" />
          </svg>
        );
      case 'phone':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" />
          </svg>
        );
      case 'clipboard':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2" />
            <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
          </svg>
        );
      case 'check-circle':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        );
      default:
        return null;
    }
  };

  return (
    <div className="call-intelligence-page">
      {/* Page Header */}
      <div className="cip-header">
        <div className="cip-header-content">
          <h1>Call Intelligence</h1>
          <p>AI-powered call analysis, review, and application conversion</p>
        </div>
        <div className="cip-header-actions">
          <button
            className="cip-refresh-btn"
            onClick={fetchSessions}
            disabled={loading}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="cip-tabs">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`cip-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => {
              setActiveTab(tab.id);
              setSelectedSession(null);
              setReviewData(null);
            }}
          >
            <span className="tab-icon">{renderTabIcon(tab.icon)}</span>
            <span className="tab-label">{tab.label}</span>
            {tab.badge > 0 && (
              <span className="tab-badge">{tab.badge}</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="cip-content">
        {loading && sessions.length === 0 ? (
          <div className="cip-loading">
            <div className="spinner"></div>
            <p>Loading call data...</p>
          </div>
        ) : (
          <>
            {activeTab === 'dashboard' && (
              <DashboardOverview
                metrics={metrics}
                pendingSessions={pendingSessions}
                activeSessions={activeSessions}
                completedSessions={completedSessions}
                onSelectSession={(session) => {
                  handleSelectSession(session);
                  setActiveTab('review');
                }}
                onViewReviewQueue={() => setActiveTab('review')}
                onViewActiveCalls={() => setActiveTab('active')}
              />
            )}

            {activeTab === 'active' && (
              <ActiveCallsMonitor
                sessions={activeSessions}
                onSelectSession={handleSelectSession}
                selectedSession={selectedSession}
                onRefresh={fetchSessions}
              />
            )}

            {activeTab === 'review' && (
              <div className="cip-review-layout">
                <ReviewQueue
                  sessions={pendingSessions}
                  selectedSession={selectedSession}
                  onSelectSession={handleSelectSession}
                />
                {selectedSession && reviewData && (
                  <CallReviewPanel
                    session={selectedSession}
                    reviewData={reviewData}
                    onApprove={handleApproveArtifacts}
                    onReject={handleRejectArtifacts}
                    onExecute={handleExecuteArtifacts}
                    onComplete={handleCompleteReview}
                    onConvertToApp={handleConvertToApp}
                    onClose={() => {
                      setSelectedSession(null);
                      setReviewData(null);
                    }}
                  />
                )}
              </div>
            )}

            {activeTab === 'completed' && (
              <div className="cip-review-layout">
                <ReviewQueue
                  sessions={completedSessions}
                  selectedSession={selectedSession}
                  onSelectSession={handleSelectSession}
                  isCompletedView={true}
                />
                {selectedSession && reviewData && (
                  <CallReviewPanel
                    session={selectedSession}
                    reviewData={reviewData}
                    onApprove={handleApproveArtifacts}
                    onReject={handleRejectArtifacts}
                    onExecute={handleExecuteArtifacts}
                    onConvertToApp={handleConvertToApp}
                    onClose={() => {
                      setSelectedSession(null);
                      setReviewData(null);
                    }}
                    isReadOnly={true}
                  />
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Convert to Application Modal */}
      {showConverter && selectedSession && reviewData && (
        <CallToAppConverter
          session={selectedSession}
          reviewData={reviewData}
          onClose={() => setShowConverter(false)}
          onSuccess={() => {
            setShowConverter(false);
            toast.success('Application created from call data');
            fetchSessions();
          }}
        />
      )}
    </div>
  );
};

export default CallIntelligencePage;
