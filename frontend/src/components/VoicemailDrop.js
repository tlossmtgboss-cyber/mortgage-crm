import React, { useState, useEffect, useRef } from 'react';
import { voicemailAPI } from '../services/api';
import './VoicemailDrop.css';

function VoicemailDrop({ phoneNumber, recipientName, leadId, loanId, onClose }) {
  const [inputMethod, setInputMethod] = useState('type'); // 'type', 'record', 'template'
  const [message, setMessage] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [status, setStatus] = useState('idle'); // idle, success, error
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const streamRef = useRef(null);

  // Load templates on mount + cleanup stream on unmount
  useEffect(() => {
    loadTemplates();
    return () => {
      // Stop any active recording stream on modal close
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

  const loadTemplates = async () => {
    try {
      const response = await voicemailAPI.getTemplates();
      if (response.success) {
        setTemplates(response.templates);
      }
    } catch (error) {
      console.error('Error loading templates:', error);
    }
  };

  const handleTemplateSelect = (template) => {
    setSelectedTemplate(template);
    // Replace variables in template
    let processedMessage = template.message_text;
    processedMessage = processedMessage.replace(/\{\{contact_name\}\}/g, recipientName || 'Customer');
    processedMessage = processedMessage.replace(/\{\{first_name\}\}/g, (recipientName || 'Customer').split(' ')[0]);
    processedMessage = processedMessage.replace(/\{\{last_name\}\}/g, (recipientName || '').split(' ').slice(1).join(' '));
    processedMessage = processedMessage.replace(/\{\{loan_officer\}\}/g, 'your loan officer');
    processedMessage = processedMessage.replace(/\{\{company_name\}\}/g, 'our office');
    // Strip any remaining unresolved {{variables}} so they aren't spoken literally
    processedMessage = processedMessage.replace(/\{\{[^}]+\}\}/g, '');

    setMessage(processedMessage);
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm'
      });

      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        await transcribeAudio(audioBlob);

        // Stop all tracks
        stream.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      };

      mediaRecorder.start();
      setIsRecording(true);

    } catch (error) {
      console.error('Error accessing microphone:', error);
      setErrorMessage('Could not access microphone. Please check permissions.');
      setStatus('error');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const transcribeAudio = async (audioBlob) => {
    try {
      setIsTranscribing(true);

      const formData = new FormData();
      formData.append('audio_file', audioBlob, 'recording.webm');

      const response = await voicemailAPI.transcribe(formData);

      if (response.success) {
        setMessage(response.transcription);
        setStatus('idle');
      } else {
        setErrorMessage('Failed to transcribe audio');
        setStatus('error');
      }
    } catch (error) {
      console.error('Error transcribing audio:', error);
      setErrorMessage('Transcription failed. Please try typing your message instead.');
      setStatus('error');
    } finally {
      setIsTranscribing(false);
    }
  };

  const handleSend = async () => {
    if (!message.trim()) {
      setErrorMessage('Please enter a message');
      setStatus('error');
      return;
    }

    if (!phoneNumber) {
      setErrorMessage('No phone number available');
      setStatus('error');
      return;
    }

    try {
      setIsSending(true);
      setStatus('idle');
      setErrorMessage('');

      const response = await voicemailAPI.drop({
        phone_number: phoneNumber,
        recipient_name: recipientName,
        message: message,
        lead_id: leadId,
        loan_id: loanId,
        template_id: selectedTemplate?.id
      });

      if (response.success) {
        setStatus('success');
        setSuccessMessage('Voicemail is being delivered!');

        setTimeout(() => {
          onClose?.();
        }, 2000);
      } else {
        setErrorMessage(response.error || 'Failed to send voicemail');
        setStatus('error');
      }
    } catch (error) {
      console.error('Error sending voicemail:', error);
      setErrorMessage(error.message || 'Failed to send voicemail');
      setStatus('error');
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="voicemail-drop-modal">
      <div className="voicemail-drop-content">
        {/* Header */}
        <div className="voicemail-drop-header">
          <h3>Drop Voicemail</h3>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        {/* Recipient Info */}
        <div className="recipient-info">
          <div className="recipient-row">
            <strong>To:</strong> {recipientName || 'Unknown'}
          </div>
          <div className="recipient-row">
            <strong>Phone:</strong> {phoneNumber || 'No phone number'}
          </div>
        </div>

        {/* Input Method Selector */}
        <div className="input-method-tabs">
          <button
            className={`tab-btn ${inputMethod === 'type' ? 'active' : ''}`}
            onClick={() => setInputMethod('type')}
          >
            Type Message
          </button>
          <button
            className={`tab-btn ${inputMethod === 'record' ? 'active' : ''}`}
            onClick={() => setInputMethod('record')}
          >
            Record Voice
          </button>
          <button
            className={`tab-btn ${inputMethod === 'template' ? 'active' : ''}`}
            onClick={() => setInputMethod('template')}
          >
            Use Template
          </button>
        </div>

        {/* Content Area */}
        <div className="voicemail-drop-body">
          {/* Type Method */}
          {inputMethod === 'type' && (
            <div className="input-section">
              <label>Your Message:</label>
              <textarea
                className="message-textarea"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Type your voicemail message here..."
                rows={6}
                disabled={isSending}
              />
              <div className="hint-text">
                Tip: Keep it concise and professional. The AI will deliver it naturally.
              </div>
            </div>
          )}

          {/* Record Method */}
          {inputMethod === 'record' && (
            <div className="input-section">
              {!isRecording && !isTranscribing && !message && (
                <div className="record-prompt">
                  <button className="btn-record" onClick={startRecording}>
                    🎤 Start Recording
                  </button>
                  <p className="hint-text">
                    Click to record your voicemail message. We'll transcribe it using AI.
                  </p>
                </div>
              )}

              {isRecording && (
                <div className="recording-active">
                  <div className="pulse-icon">🔴</div>
                  <p>Recording... Speak your message now</p>
                  <button className="btn-stop" onClick={stopRecording}>
                    Stop Recording
                  </button>
                </div>
              )}

              {isTranscribing && (
                <div className="transcribing">
                  <div className="spinner"></div>
                  <p>Transcribing your message...</p>
                </div>
              )}

              {message && !isRecording && !isTranscribing && (
                <div className="transcribed-message">
                  <label>Transcribed Message:</label>
                  <textarea
                    className="message-textarea"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    rows={6}
                    disabled={isSending}
                  />
                  <button
                    className="btn-rerecord"
                    onClick={() => {
                      setMessage('');
                      startRecording();
                    }}
                  >
                    🔄 Re-record
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Template Method */}
          {inputMethod === 'template' && (
            <div className="input-section">
              {!selectedTemplate ? (
                <div className="templates-list">
                  <label>Choose a Template:</label>
                  {templates.length === 0 ? (
                    <p className="hint-text">Loading templates...</p>
                  ) : (
                    <div className="template-cards">
                      {templates.map((template) => (
                        <div
                          key={template.id}
                          className="template-card"
                          onClick={() => handleTemplateSelect(template)}
                        >
                          <div className="template-name">{template.name}</div>
                          <div className="template-category">{template.category}</div>
                          <div className="template-preview">
                            {template.message_text.substring(0, 100)}...
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="selected-template">
                  <div className="template-header">
                    <strong>{selectedTemplate.name}</strong>
                    <button
                      className="btn-change-template"
                      onClick={() => {
                        setSelectedTemplate(null);
                        setMessage('');
                      }}
                    >
                      Change Template
                    </button>
                  </div>
                  <label>Message (you can edit):</label>
                  <textarea
                    className="message-textarea"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    rows={6}
                    disabled={isSending}
                  />
                </div>
              )}
            </div>
          )}

          {/* Status Messages */}
          {status === 'success' && (
            <div className="status-message success">
              <div className="success-icon">✓</div>
              <p>{successMessage}</p>
            </div>
          )}

          {status === 'error' && (
            <div className="status-message error">
              <div className="error-icon">✕</div>
              <p>{errorMessage}</p>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="voicemail-drop-footer">
          <button
            className="btn-cancel"
            onClick={onClose}
            disabled={isSending}
          >
            Cancel
          </button>
          <button
            className="btn-send"
            onClick={handleSend}
            disabled={!message.trim() || isSending || isRecording || isTranscribing}
          >
            {isSending ? 'Sending...' : 'Send Voicemail'}
          </button>
        </div>

        {/* Instructions */}
        {!message && status === 'idle' && (
          <div className="instructions">
            <h4>How it works:</h4>
            <ol>
              <li>Choose your input method (Type, Record, or Template)</li>
              <li>Create your voicemail message</li>
              <li>Click "Send Voicemail" to deliver</li>
              <li>Our AI will call and leave the message naturally</li>
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}

export default VoicemailDrop;
