/**
 * Click-to-Dial Modal Component
 * Handles the call initiation and real-time status display
 */

import React, { useState, useEffect, useCallback } from 'react';
import { X, Phone, PhoneOff, Loader2, AlertCircle, CheckCircle, Clock } from 'lucide-react';
import axios from 'axios';
import { useDialerWebSocket } from '../../hooks/useDialerWebSocket';
import { getToken } from '../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

/**
 * @param {Object} props
 * @param {string} props.contactId - Contact ID
 * @param {string} props.contactName - Contact's name
 * @param {string} props.phone - Phone number to call
 * @param {string} [props.loanId] - Associated loan ID
 * @param {string} [props.leadId] - Associated lead ID
 * @param {string} [props.taskId] - Associated task ID
 * @param {string} [props.context] - Call context
 * @param {function} props.onClose - Close modal callback
 */
const ClickToDialModal = ({
  contactId,
  contactName,
  phone,
  loanId,
  leadId,
  taskId,
  context,
  onClose
}) => {
  const [phoneNumber, setPhoneNumber] = useState(phone);
  const [callState, setCallState] = useState('idle'); // idle, initiating, ringing, connected, completed, failed
  const [callSid, setCallSid] = useState(null);
  const [callDuration, setCallDuration] = useState(0);
  const [error, setError] = useState(null);
  const [callLogId, setCallLogId] = useState(null);

  // Get agent ID from localStorage or context
  const agentId = localStorage.getItem('userId') || 'default';

  // Handle WebSocket messages for call status updates
  const handleWebSocketMessage = useCallback((event) => {
    if (event.type === 'click_to_dial_status' && event.call_sid === callSid) {
      console.log('Call status update:', event);

      switch (event.status) {
        case 'ringing':
          setCallState('ringing');
          break;
        case 'in-progress':
        case 'answered':
          setCallState('connected');
          break;
        case 'completed':
          setCallState('completed');
          setCallDuration(event.duration_seconds || 0);
          setCallLogId(event.call_log_id);
          break;
        case 'busy':
        case 'no-answer':
        case 'failed':
        case 'canceled':
          setCallState('failed');
          setError(`Call ${event.status.replace('-', ' ')}`);
          break;
        default:
          console.log('Unknown call status:', event.status);
      }
    }
  }, [callSid]);

  // WebSocket connection
  const { isConnected } = useDialerWebSocket(agentId, {
    onMessage: handleWebSocketMessage
  });

  // Timer for connected calls
  useEffect(() => {
    let interval;
    if (callState === 'connected') {
      interval = setInterval(() => {
        setCallDuration(prev => prev + 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [callState]);

  // Format duration as MM:SS
  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Initiate the call
  const initiateCall = async () => {
    setCallState('initiating');
    setError(null);

    try {
      const response = await axios.post(
        `${API_BASE}/api/v1/dialer/click-to-dial`,
        {
          phone_number: phoneNumber,
          contact_name: contactName,
          lead_id: leadId ? parseInt(leadId) : null,
          loan_id: loanId ? parseInt(loanId) : null,
          task_id: taskId ? parseInt(taskId) : null
        },
        {
          headers: {
            Authorization: `Bearer ${getToken()}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (response.data.success) {
        setCallSid(response.data.call_sid);
        setCallState('ringing');
      } else {
        setError(response.data.error || 'Failed to initiate call');
        setCallState('failed');
      }
    } catch (err) {
      console.error('Error initiating call:', err);
      setError(err.response?.data?.detail || 'Failed to initiate call');
      setCallState('failed');
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md mx-4">
        {/* Header */}
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">Call Contact</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <div className="space-y-4">
          {/* Contact Info */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Contact
            </label>
            <div className="text-lg font-semibold">{contactName}</div>
            {context && (
              <div className="text-sm text-gray-600">{context}</div>
            )}
          </div>

          {/* Phone Number - Editable when idle */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Phone Number
            </label>
            {callState === 'idle' ? (
              <input
                type="tel"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            ) : (
              <div className="text-lg text-gray-900">{phoneNumber}</div>
            )}
          </div>

          {/* Call Status Display */}
          {callState !== 'idle' && (
            <div className={`text-center py-4 rounded-lg ${
              callState === 'initiating' || callState === 'ringing' ? 'bg-yellow-50' :
              callState === 'connected' ? 'bg-green-50' :
              callState === 'completed' ? 'bg-green-50' :
              callState === 'failed' ? 'bg-red-50' : 'bg-gray-50'
            }`}>
              {callState === 'initiating' && (
                <div className="flex items-center justify-center gap-2">
                  <Loader2 className="w-5 h-5 animate-spin text-yellow-600" />
                  <span className="text-yellow-700">Connecting...</span>
                </div>
              )}
              {callState === 'ringing' && (
                <div className="flex items-center justify-center gap-2">
                  <Phone className="w-5 h-5 animate-pulse text-yellow-600" />
                  <span className="text-yellow-700">Ringing your phone...</span>
                </div>
              )}
              {callState === 'connected' && (
                <div className="flex items-center justify-center gap-2">
                  <Clock className="w-5 h-5 text-green-600" />
                  <span className="text-green-700">Connected - {formatDuration(callDuration)}</span>
                </div>
              )}
              {callState === 'completed' && (
                <div className="flex items-center justify-center gap-2">
                  <CheckCircle className="w-5 h-5 text-green-600" />
                  <span className="text-green-700">Call completed - {formatDuration(callDuration)}</span>
                </div>
              )}
              {callState === 'failed' && (
                <div className="flex items-center justify-center gap-2">
                  <AlertCircle className="w-5 h-5 text-red-600" />
                  <span className="text-red-700">{error || 'Call failed'}</span>
                </div>
              )}
            </div>
          )}

          {/* Error Message */}
          {error && callState === 'idle' && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex space-x-3">
            {callState === 'idle' && (
              <>
                <button
                  onClick={initiateCall}
                  disabled={!phoneNumber}
                  className="flex-1 bg-green-600 text-white py-2 px-4 rounded-md hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center"
                >
                  <Phone className="w-5 h-5 mr-2" />
                  Call Now
                </button>
                <button
                  onClick={onClose}
                  className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50"
                >
                  Cancel
                </button>
              </>
            )}

            {(callState === 'initiating' || callState === 'ringing') && (
              <button
                onClick={onClose}
                className="flex-1 bg-red-600 text-white py-2 px-4 rounded-md hover:bg-red-700 flex items-center justify-center"
              >
                <PhoneOff className="w-5 h-5 mr-2" />
                Cancel
              </button>
            )}

            {callState === 'connected' && (
              <div className="flex-1 bg-gray-100 text-gray-600 py-2 px-4 rounded-md flex items-center justify-center">
                <Phone className="w-5 h-5 mr-2 text-green-600" />
                Call in progress...
              </div>
            )}

            {(callState === 'completed' || callState === 'failed') && (
              <>
                <button
                  onClick={() => {
                    setCallState('idle');
                    setError(null);
                    setCallDuration(0);
                    setCallSid(null);
                  }}
                  className="flex-1 bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 flex items-center justify-center"
                >
                  <Phone className="w-5 h-5 mr-2" />
                  Call Again
                </button>
                <button
                  onClick={onClose}
                  className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50"
                >
                  Close
                </button>
              </>
            )}
          </div>

          {/* Add Disposition button when call completed */}
          {callState === 'completed' && callLogId && (
            <button
              onClick={() => {
                window.dispatchEvent(new CustomEvent('openDisposition', {
                  detail: { callLogId, contactName, phone: phoneNumber }
                }));
                onClose();
              }}
              className="w-full px-4 py-2 text-blue-600 border border-blue-600 rounded-lg hover:bg-blue-50 transition-colors"
            >
              Add Call Disposition
            </button>
          )}

          {/* Helper text */}
          <div className="text-xs text-gray-500 text-center">
            Your cell phone will ring first. Answer to connect to the contact.
          </div>

          {/* WebSocket status indicator */}
          {!isConnected && callState !== 'idle' && (
            <div className="text-xs text-yellow-600 text-center flex items-center justify-center gap-1">
              <AlertCircle className="w-3 h-3" />
              Real-time updates unavailable
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ClickToDialModal;
