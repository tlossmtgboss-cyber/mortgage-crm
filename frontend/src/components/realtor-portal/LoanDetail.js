/**
 * LoanDetail Component
 *
 * Main loan detail view for the Realtor Portal.
 * Displays loan information, timeline, conditions, and actions
 * based on realtor permissions.
 */

import React, { useState, useMemo, useCallback } from 'react';
import { toast } from '../../utils/toast';
import {
  useRealtorLoan,
  useRealtorTimeline,
  useRealtorConditions,
  useLoanSync,
  useLetterGeneration,
} from '../../hooks/useRealtorPortal';

// =============================================================================
// STATUS BADGE COMPONENT
// =============================================================================

function StatusBadge({ status }) {
  const statusConfig = {
    lead: { bg: 'bg-gray-100', text: 'text-gray-800', label: 'Lead' },
    application: { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Application' },
    processing: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Processing' },
    submitted: { bg: 'bg-purple-100', text: 'text-purple-800', label: 'Submitted' },
    underwriting: { bg: 'bg-orange-100', text: 'text-orange-800', label: 'Underwriting' },
    conditional_approval: { bg: 'bg-teal-100', text: 'text-teal-800', label: 'Conditional Approval' },
    clear_to_close: { bg: 'bg-green-100', text: 'text-green-800', label: 'Clear to Close' },
    funded: { bg: 'bg-emerald-100', text: 'text-emerald-800', label: 'Funded' },
    denied: { bg: 'bg-red-100', text: 'text-red-800', label: 'Denied' },
    withdrawn: { bg: 'bg-gray-100', text: 'text-gray-500', label: 'Withdrawn' },
  };

  const config = statusConfig[status] || statusConfig.lead;

  return (
    <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${config.bg} ${config.text}`}>
      {config.label}
    </span>
  );
}

// =============================================================================
// TIMELINE COMPONENT
// =============================================================================

function Timeline({ milestones, loading }) {
  if (loading) {
    return (
      <div className="animate-pulse space-y-4">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="flex items-center space-x-4">
            <div className="w-4 h-4 bg-gray-200 rounded-full" />
            <div className="flex-1 h-4 bg-gray-200 rounded" />
          </div>
        ))}
      </div>
    );
  }

  if (!milestones?.length) {
    return <p className="text-gray-500 text-sm">No timeline data available</p>;
  }

  return (
    <div className="relative">
      {/* Vertical line */}
      <div className="absolute left-2 top-2 bottom-2 w-0.5 bg-gray-200" />

      <div className="space-y-4">
        {milestones.map((milestone, index) => (
          <div key={index} className="relative flex items-start space-x-4 pl-1">
            {/* Circle indicator */}
            <div
              className={`w-4 h-4 rounded-full flex-shrink-0 z-10 ${
                milestone.is_completed
                  ? 'bg-green-500'
                  : 'bg-gray-300 border-2 border-white'
              }`}
            />

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <h4 className={`text-sm font-medium ${
                  milestone.is_completed ? 'text-gray-900' : 'text-gray-500'
                }`}>
                  {milestone.name}
                </h4>
                {milestone.is_completed && milestone.completed_at && (
                  <span className="text-xs text-gray-400">
                    {new Date(milestone.completed_at).toLocaleDateString()}
                  </span>
                )}
              </div>
              {!milestone.is_completed && milestone.target_date && (
                <p className="text-xs text-gray-400 mt-0.5">
                  Expected: {new Date(milestone.target_date).toLocaleDateString()}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// CONDITIONS LIST COMPONENT
// =============================================================================

function ConditionsList({ conditions, summary, loading }) {
  if (loading) {
    return (
      <div className="animate-pulse space-y-3">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-16 bg-gray-100 rounded-lg" />
        ))}
      </div>
    );
  }

  if (!conditions?.length) {
    return (
      <div className="text-center py-8 text-gray-500">
        <svg className="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p>No conditions to display</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Summary */}
      {summary && (
        <div className="flex items-center space-x-4 mb-4 text-sm">
          <span className="text-gray-600">
            <span className="font-medium text-yellow-600">{summary.open}</span> Open
          </span>
          <span className="text-gray-600">
            <span className="font-medium text-green-600">{summary.cleared}</span> Cleared
          </span>
          <span className="text-gray-600">
            <span className="font-medium">{summary.total}</span> Total
          </span>
        </div>
      )}

      {/* Conditions list */}
      {conditions.map((condition) => (
        <div
          key={condition.id}
          className={`p-4 rounded-lg border ${
            condition.status === 'open'
              ? 'border-yellow-200 bg-yellow-50'
              : 'border-green-200 bg-green-50'
          }`}
        >
          <div className="flex items-start justify-between">
            <div>
              <h4 className="font-medium text-gray-900">{condition.name}</h4>
              {condition.description && (
                <p className="text-sm text-gray-600 mt-1">{condition.description}</p>
              )}
            </div>
            <span className={`text-xs font-medium px-2 py-1 rounded ${
              condition.status === 'open'
                ? 'bg-yellow-100 text-yellow-800'
                : 'bg-green-100 text-green-800'
            }`}>
              {condition.status.charAt(0).toUpperCase() + condition.status.slice(1)}
            </span>
          </div>
          {condition.due_date && condition.status === 'open' && (
            <p className="text-xs text-gray-500 mt-2">
              Due: {new Date(condition.due_date).toLocaleDateString()}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

// =============================================================================
// LETTERS PANEL COMPONENT
// =============================================================================

function LettersPanel({ loanId, permissions, onGenerateLetter }) {
  const { letters, loading, getLetterPdfUrl, getShareUrl } = useLetterGeneration(loanId);

  const canGeneratePrequal = permissions?.can_generate_prequal;
  const canGeneratePreapproval = permissions?.can_generate_preapproval;

  return (
    <div className="space-y-4">
      {/* Generate buttons */}
      <div className="flex space-x-3">
        {canGeneratePrequal && (
          <button
            onClick={() => onGenerateLetter('prequal')}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
          >
            Generate Pre-Qual Letter
          </button>
        )}
        {canGeneratePreapproval && (
          <button
            onClick={() => onGenerateLetter('preapproval')}
            className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm font-medium"
          >
            Generate Pre-Approval Letter
          </button>
        )}
      </div>

      {/* Letters list */}
      {loading ? (
        <div className="animate-pulse space-y-3">
          {[1, 2].map(i => (
            <div key={i} className="h-20 bg-gray-100 rounded-lg" />
          ))}
        </div>
      ) : letters.length === 0 ? (
        <p className="text-gray-500 text-sm text-center py-4">No letters generated yet</p>
      ) : (
        <div className="space-y-3">
          {letters.map((letter) => (
            <div
              key={letter.id}
              className={`p-4 rounded-lg border ${
                letter.is_expired || letter.is_void
                  ? 'border-gray-200 bg-gray-50 opacity-60'
                  : 'border-blue-200 bg-blue-50'
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium text-gray-900">
                    {letter.letter_type === 'prequal' ? 'Pre-Qualification' : 'Pre-Approval'} Letter
                    <span className="text-gray-400 text-sm ml-2">v{letter.version}</span>
                  </h4>
                  {letter.property_address && (
                    <p className="text-sm text-gray-600">{letter.property_address}</p>
                  )}
                  <div className="flex items-center space-x-3 mt-1 text-xs text-gray-500">
                    {letter.approved_amount && (
                      <span>${letter.approved_amount.toLocaleString()}</span>
                    )}
                    <span>Expires: {new Date(letter.expires_at).toLocaleDateString()}</span>
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  <a
                    href={getLetterPdfUrl(letter.id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded"
                    title="Download PDF"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </a>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(getShareUrl(letter.share_token));
                      toast.success('Share link copied to clipboard!');
                    }}
                    className="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded"
                    title="Copy Share Link"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// MAIN LOAN DETAIL COMPONENT
// =============================================================================

export default function LoanDetail({ loanId, onBack, onOpenLetterModal }) {
  const [activeTab, setActiveTab] = useState('overview');

  // Fetch loan data
  const { loan, permissions, loading: loanLoading, error: loanError, refetch: refetchLoan } = useRealtorLoan(loanId);
  const { milestones, loading: timelineLoading, refetch: refetchTimeline } = useRealtorTimeline(loanId);
  const { conditions, summary: conditionsSummary, loading: conditionsLoading, refetch: refetchConditions } = useRealtorConditions(loanId);

  // Real-time sync
  const { isConnected } = useLoanSync({
    onStatusChange: useCallback((id, data) => {
      if (id === loanId) {
        console.log('Status changed:', data);
        refetchLoan();
      }
    }, [loanId, refetchLoan]),
    onMilestoneUpdate: useCallback((id) => {
      if (id === loanId) refetchTimeline();
    }, [loanId, refetchTimeline]),
    onConditionUpdate: useCallback((id) => {
      if (id === loanId) refetchConditions();
    }, [loanId, refetchConditions]),
  });

  // Handle letter generation
  const handleGenerateLetter = useCallback((letterType) => {
    if (onOpenLetterModal) {
      onOpenLetterModal(letterType, loan);
    }
  }, [onOpenLetterModal, loan]);

  // Tab configuration
  const tabs = useMemo(() => {
    const available = [
      { id: 'overview', label: 'Overview', always: true },
    ];

    if (permissions?.can_view_timeline) {
      available.push({ id: 'timeline', label: 'Timeline' });
    }
    if (permissions?.can_view_conditions) {
      available.push({ id: 'conditions', label: 'Conditions' });
    }
    if (permissions?.can_generate_prequal || permissions?.can_generate_preapproval) {
      available.push({ id: 'letters', label: 'Letters' });
    }

    return available;
  }, [permissions]);

  // Loading state
  if (loanLoading) {
    return (
      <div className="min-h-screen bg-gray-50 p-6">
        <div className="max-w-4xl mx-auto">
          <div className="animate-pulse space-y-6">
            <div className="h-8 w-48 bg-gray-200 rounded" />
            <div className="h-64 bg-white rounded-xl shadow" />
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (loanError) {
    return (
      <div className="min-h-screen bg-gray-50 p-6">
        <div className="max-w-4xl mx-auto">
          <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
            <h2 className="text-red-800 font-medium">Unable to load loan</h2>
            <p className="text-red-600 mt-2">{loanError}</p>
            <button
              onClick={onBack}
              className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
            >
              Go Back
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <button
                onClick={onBack}
                className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <div>
                <h1 className="text-xl font-semibold text-gray-900">{loan?.borrower_name}</h1>
                <p className="text-sm text-gray-500">{loan?.property_address || 'Address TBD'}</p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              {/* Connection indicator */}
              <span className={`flex items-center text-xs ${isConnected ? 'text-green-600' : 'text-gray-400'}`}>
                <span className={`w-2 h-2 rounded-full mr-1.5 ${isConnected ? 'bg-green-500' : 'bg-gray-300'}`} />
                {isConnected ? 'Live' : 'Offline'}
              </span>
              <StatusBadge status={loan?.status} />
            </div>
          </div>

          {/* Tabs */}
          <div className="flex space-x-1 mt-4 -mb-px">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? 'border-blue-600 text-blue-600 bg-blue-50'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-6 py-6">
        {activeTab === 'overview' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Loan Info Card */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h3 className="font-semibold text-gray-900 mb-4">Loan Details</h3>
              <dl className="space-y-3">
                <div className="flex justify-between">
                  <dt className="text-gray-500">Loan Amount</dt>
                  <dd className="font-medium text-gray-900">
                    ${loan?.loan_amount?.toLocaleString() || 'N/A'}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-gray-500">Loan Type</dt>
                  <dd className="font-medium text-gray-900">{loan?.loan_type || 'N/A'}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-gray-500">Expected Close</dt>
                  <dd className="font-medium text-gray-900">
                    {loan?.expected_close_date
                      ? new Date(loan.expected_close_date).toLocaleDateString()
                      : 'TBD'}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-gray-500">Your Role</dt>
                  <dd className="font-medium text-gray-900 capitalize">
                    {loan?.role?.replace('_', ' ') || 'N/A'}
                  </dd>
                </div>
              </dl>
            </div>

            {/* Loan Officer Card */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h3 className="font-semibold text-gray-900 mb-4">Loan Officer</h3>
              <div className="flex items-center space-x-4">
                <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                  <span className="text-blue-600 font-semibold text-lg">
                    {loan?.loan_officer?.name?.charAt(0) || 'L'}
                  </span>
                </div>
                <div>
                  <p className="font-medium text-gray-900">{loan?.loan_officer?.name}</p>
                  <p className="text-sm text-gray-500">{loan?.loan_officer?.email}</p>
                  <p className="text-sm text-gray-500">{loan?.loan_officer?.phone}</p>
                </div>
              </div>
              {permissions?.can_send_messages && (
                <button className="mt-4 w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
                  Send Message
                </button>
              )}
            </div>

            {/* Quick Timeline Preview */}
            {permissions?.can_view_timeline && (
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 md:col-span-2">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-gray-900">Timeline</h3>
                  <button
                    onClick={() => setActiveTab('timeline')}
                    className="text-sm text-blue-600 hover:text-blue-700"
                  >
                    View All
                  </button>
                </div>
                <Timeline milestones={milestones?.slice(0, 5)} loading={timelineLoading} />
              </div>
            )}
          </div>
        )}

        {activeTab === 'timeline' && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h3 className="font-semibold text-gray-900 mb-6">Loan Timeline</h3>
            <Timeline milestones={milestones} loading={timelineLoading} />
          </div>
        )}

        {activeTab === 'conditions' && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h3 className="font-semibold text-gray-900 mb-6">Loan Conditions</h3>
            <ConditionsList
              conditions={conditions}
              summary={conditionsSummary}
              loading={conditionsLoading}
            />
          </div>
        )}

        {activeTab === 'letters' && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h3 className="font-semibold text-gray-900 mb-6">Letters</h3>
            <LettersPanel
              loanId={loanId}
              permissions={permissions}
              onGenerateLetter={handleGenerateLetter}
            />
          </div>
        )}
      </div>
    </div>
  );
}
