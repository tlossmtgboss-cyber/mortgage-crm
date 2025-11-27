/**
 * Power Dialer Panel Component
 * Floating panel that shows during an active dialer session
 */

import React from 'react';
import { Phone, Pause, Play, Square, SkipForward, Wifi, WifiOff } from 'lucide-react';
import { useDialerSession } from '../../hooks/useDialerSession';
import DispositionModal from './DispositionModal';

/**
 * @param {Object} props
 * @param {string} props.agentId - Agent ID for the session
 */
const DialerPanel = ({ agentId }) => {
  const {
    session,
    isConnected,
    showDispositionModal,
    currentCallData,
    setShowDispositionModal,
    pauseSession,
    resumeSession,
    stopSession,
    skipCurrentTask
  } = useDialerSession(agentId);

  // Don't render if no active session
  if (!session) {
    return null;
  }

  const progress = session.total_tasks > 0
    ? (session.completed_tasks / session.total_tasks) * 100
    : 0;

  return (
    <>
      <div className="fixed bottom-6 right-6 w-96 bg-white rounded-lg shadow-2xl border border-gray-200 z-40">
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-blue-700 text-white px-4 py-3 rounded-t-lg">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <Phone className="w-5 h-5 mr-2" />
              <h3 className="font-semibold">Power Dialer</h3>
            </div>
            <div className="flex items-center text-sm">
              {isConnected ? (
                <>
                  <Wifi className="w-4 h-4 mr-1" />
                  <span>Connected</span>
                </>
              ) : (
                <>
                  <WifiOff className="w-4 h-4 mr-1 text-yellow-300" />
                  <span className="text-yellow-300">Disconnected</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="px-4 pt-3">
          <div className="flex justify-between text-sm text-gray-600 mb-1">
            <span>Progress</span>
            <span>{session.completed_tasks} of {session.total_tasks}</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Stats Row */}
        <div className="px-4 py-2 flex justify-between text-xs text-gray-500 border-b">
          <span>✓ {session.completed_tasks} completed</span>
          <span>✗ {session.failed_tasks || 0} failed</span>
          <span>⟳ {session.skipped_tasks || 0} skipped</span>
        </div>

        {/* Current Call Info */}
        <div className="px-4 py-3 border-b">
          {session.current_task ? (
            <>
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm text-gray-600">
                  {session.status === 'ACTIVE' ? 'Calling' : 'Current'}
                </div>
                <div className={`px-2 py-1 rounded-full text-xs font-medium ${
                  session.status === 'ACTIVE' ? 'bg-green-100 text-green-800' :
                  session.status === 'PAUSED' ? 'bg-yellow-100 text-yellow-800' :
                  'bg-gray-100 text-gray-800'
                }`}>
                  {session.status}
                </div>
              </div>
              <div className="text-lg font-semibold text-gray-900">
                {session.current_task.name || session.current_task.contact_name}
              </div>
              <div className="text-sm text-gray-600">
                {session.current_task.phone}
              </div>
              {session.current_task.context && (
                <div className="text-xs text-gray-500 mt-1">
                  {session.current_task.context}
                </div>
              )}
              {session.current_task.call_sid && (
                <div className="mt-2 flex items-center text-xs text-green-600">
                  <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse mr-2" />
                  Call in progress
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-4 text-gray-500">
              {session.status === 'PAUSED' ? (
                <>
                  <Pause className="w-8 h-8 mx-auto mb-2 text-yellow-500" />
                  <div>Session Paused</div>
                  <div className="text-xs">Click Resume to continue</div>
                </>
              ) : session.status === 'COMPLETED' ? (
                <>
                  <div className="text-2xl mb-2">🎉</div>
                  <div>Session Complete!</div>
                  <div className="text-xs">{session.completed_tasks} calls made</div>
                </>
              ) : (
                <>
                  <div className="animate-pulse">Preparing next call...</div>
                </>
              )}
            </div>
          )}
        </div>

        {/* Controls */}
        <div className="px-4 py-3 flex space-x-2">
          {session.status === 'ACTIVE' ? (
            <>
              <button
                onClick={pauseSession}
                className="flex-1 bg-yellow-500 text-white py-2 px-3 rounded-md hover:bg-yellow-600 flex items-center justify-center transition-colors"
              >
                <Pause className="w-4 h-4 mr-1" />
                Pause
              </button>
              <button
                onClick={skipCurrentTask}
                disabled={!session.current_task}
                className="flex-1 bg-gray-500 text-white py-2 px-3 rounded-md hover:bg-gray-600 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center transition-colors"
              >
                <SkipForward className="w-4 h-4 mr-1" />
                Skip
              </button>
            </>
          ) : session.status === 'PAUSED' ? (
            <>
              <button
                onClick={resumeSession}
                className="flex-1 bg-green-600 text-white py-2 px-3 rounded-md hover:bg-green-700 flex items-center justify-center transition-colors"
              >
                <Play className="w-4 h-4 mr-1" />
                Resume
              </button>
              <button
                onClick={stopSession}
                className="flex-1 bg-red-600 text-white py-2 px-3 rounded-md hover:bg-red-700 flex items-center justify-center transition-colors"
              >
                <Square className="w-4 h-4 mr-1" />
                Stop
              </button>
            </>
          ) : (
            <button
              onClick={stopSession}
              className="flex-1 bg-red-600 text-white py-2 px-3 rounded-md hover:bg-red-700 flex items-center justify-center transition-colors"
            >
              <Square className="w-4 h-4 mr-1" />
              End Session
            </button>
          )}
        </div>

        {/* Next Up */}
        {session.next_tasks && session.next_tasks.length > 0 && (
          <div className="px-4 py-3 bg-gray-50 rounded-b-lg">
            <div className="text-xs font-semibold text-gray-600 mb-2 uppercase">
              Next Up
            </div>
            <div className="space-y-1">
              {session.next_tasks.slice(0, 3).map((task, index) => (
                <div
                  key={task.task_id || index}
                  className="text-sm text-gray-700 flex items-center"
                >
                  <div className="w-2 h-2 bg-gray-400 rounded-full mr-2" />
                  <span className="truncate">
                    {task.contact_name} • {task.phone}
                  </span>
                </div>
              ))}
              {session.next_tasks.length > 3 && (
                <div className="text-xs text-gray-500">
                  +{session.next_tasks.length - 3} more
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Disposition Modal */}
      {showDispositionModal && currentCallData && (
        <DispositionModal
          taskId={currentCallData.task_id}
          sessionId={session.session_id}
          contactName={currentCallData.contact?.name || session.current_task?.name || 'Unknown'}
          callDuration={currentCallData.duration_seconds}
          callOutcome={currentCallData.outcome}
          onClose={() => setShowDispositionModal(false)}
          onSaved={() => {
            setShowDispositionModal(false);
            // Session will auto-advance via WebSocket
          }}
        />
      )}
    </>
  );
};

export default DialerPanel;
