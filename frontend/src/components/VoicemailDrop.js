import React, { useState, useRef } from 'react';
import { voiceAPI } from '../services/api';
import './VoicemailDrop.css';

function VoicemailDrop({ phoneNumber, recipientName, onClose }) {
  const [step, setStep] = useState('idle'); // idle, listening, processing, success, error
  const [message, setMessage] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const recognitionRef = useRef(null);

  const startListening = () => {
    // Check if browser supports Web Speech API
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setErrorMessage('Sorry, your browser does not support speech recognition. Please try Chrome or Edge.');
      setStep('error');
      return;
    }

    // Create new recognition instance
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      setIsListening(true);
      setStep('listening');
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      console.log('Voice message recorded:', transcript);
      setMessage(transcript);
      setStep('idle');
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
      if (event.error === 'no-speech') {
        setErrorMessage('No speech detected. Please try again.');
      } else if (event.error !== 'aborted') {
        setErrorMessage(`Error occurred: ${event.error}`);
      }
      setStep('error');
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const stopListening = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      setIsListening(false);
      setStep('idle');
    }
  };

  const handleSendVoicemail = async () => {
    if (!message.trim()) {
      setErrorMessage('Please record a message first');
      setStep('error');
      return;
    }

    if (!phoneNumber) {
      setErrorMessage('No phone number provided');
      setStep('error');
      return;
    }

    try {
      setStep('processing');
      setErrorMessage('');

      const response = await voiceAPI.dropVoicemail({
        to_number: phoneNumber,
        message: message,
        recipient_name: recipientName
      });

      if (response.success) {
        setStep('success');
        setTimeout(() => {
          onClose?.();
        }, 2000);
      } else {
        setErrorMessage(response.error || 'Failed to send voicemail');
        setStep('error');
      }
    } catch (error) {
      console.error('Error sending voicemail:', error);
      setErrorMessage(error.message || 'Failed to send voicemail');
      setStep('error');
    }
  };

  const handleReset = () => {
    setStep('idle');
    setMessage('');
    setErrorMessage('');
  };

  return (
    <div className="voicemail-drop-modal">
      <div className="voicemail-drop-content">
        <div className="voicemail-drop-header">
          <h3>📞 Voicemail Drop</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <div className="voicemail-drop-body">
          {/* Recipient Info */}
          <div className="recipient-info">
            <div className="recipient-name">
              <strong>To:</strong> {recipientName || 'Unknown'}
            </div>
            <div className="recipient-phone">
              <strong>Phone:</strong> {phoneNumber || 'No phone number'}
            </div>
          </div>

          {/* Status Messages */}
          {step === 'listening' && (
            <div className="status-message listening">
              <div className="pulse-icon">🎤</div>
              <p>Listening... Speak your voicemail message now!</p>
              <button className="btn-stop" onClick={stopListening}>
                Stop Recording
              </button>
            </div>
          )}

          {step === 'processing' && (
            <div className="status-message processing">
              <div className="spinner"></div>
              <p>Sending voicemail...</p>
            </div>
          )}

          {step === 'success' && (
            <div className="status-message success">
              <div className="success-icon">✅</div>
              <p>Voicemail delivered successfully!</p>
            </div>
          )}

          {step === 'error' && (
            <div className="status-message error">
              <div className="error-icon">❌</div>
              <p>{errorMessage}</p>
              <button className="btn-retry" onClick={handleReset}>
                Try Again
              </button>
            </div>
          )}

          {/* Message Display */}
          {message && step === 'idle' && (
            <div className="message-preview">
              <label>Your Message:</label>
              <div className="message-text">{message}</div>
              <div className="message-actions">
                <button className="btn-rerecord" onClick={handleReset}>
                  🔄 Re-record
                </button>
              </div>
            </div>
          )}

          {/* Action Buttons */}
          {step === 'idle' && (
            <div className="voicemail-actions">
              {!message ? (
                <button className="btn-record" onClick={startListening}>
                  🎤 Record Voicemail Message
                </button>
              ) : (
                <>
                  <button className="btn-send-voicemail" onClick={handleSendVoicemail}>
                    📤 Send Voicemail
                  </button>
                  <button className="btn-cancel" onClick={onClose}>
                    Cancel
                  </button>
                </>
              )}
            </div>
          )}

          {/* Instructions */}
          {!message && step === 'idle' && (
            <div className="instructions">
              <h4>How it works:</h4>
              <ol>
                <li>Click "Record Voicemail Message"</li>
                <li>Speak your message clearly</li>
                <li>AI will convert it to a professional voicemail</li>
                <li>Voicemail will be delivered to the recipient's mailbox</li>
              </ol>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default VoicemailDrop;
