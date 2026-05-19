import React, { useState, useEffect, useCallback } from 'react';
import VideoRecorder from './video/VideoRecorder';
import './EmailComposerModal.css';
import api, { API_BASE_URL } from '../services/api';

const APP_BASE = process.env.REACT_APP_BASE_URL || 'https://app.perenniaai.com';

// Email templates organized by category
const EMAIL_TEMPLATES = {
  'Lead Nurturing': [
    { id: 'initial_followup', name: 'Initial Follow-Up', description: 'First contact after lead submission' },
    { id: 'rate_update', name: 'Rate Update', description: 'Notify about favorable rate changes' },
    { id: 'checking_in', name: 'Checking In', description: 'Friendly check-in on their home search' },
    { id: 'pre_approval_invitation', name: 'Pre-Approval Invitation', description: 'Invite to get pre-approved' },
  ],
  'Application Process': [
    { id: 'welcome_application', name: 'Welcome to Application', description: 'Thank them for starting application' },
    { id: 'documents_needed', name: 'Documents Needed', description: 'Request required documents' },
    { id: 'documents_received', name: 'Documents Received', description: 'Confirm document receipt' },
    { id: 'application_complete', name: 'Application Complete', description: 'Confirm application is complete' },
  ],
  'Processing Updates': [
    { id: 'processing_started', name: 'Processing Started', description: 'Loan is now in processing' },
    { id: 'appraisal_ordered', name: 'Appraisal Ordered', description: 'Appraisal has been scheduled' },
    { id: 'appraisal_complete', name: 'Appraisal Complete', description: 'Appraisal results are in' },
    { id: 'title_update', name: 'Title Update', description: 'Title work status update' },
  ],
  'Underwriting': [
    { id: 'submitted_to_uw', name: 'Submitted to Underwriting', description: 'Loan submitted for review' },
    { id: 'conditional_approval', name: 'Conditional Approval', description: 'Great news - conditionally approved!' },
    { id: 'conditions_needed', name: 'Conditions Needed', description: 'Additional items needed for approval' },
    { id: 'final_approval', name: 'Final Approval', description: 'Celebrate full approval!' },
  ],
  'Closing': [
    { id: 'clear_to_close', name: 'Clear to Close', description: 'Ready to schedule closing' },
    { id: 'closing_scheduled', name: 'Closing Scheduled', description: 'Confirm closing date/time' },
    { id: 'closing_reminder', name: 'Closing Reminder', description: 'Reminder about upcoming closing' },
    { id: 'congratulations', name: 'Congratulations!', description: 'Celebrate successful closing' },
  ],
  'Post-Closing': [
    { id: 'thank_you', name: 'Thank You', description: 'Express gratitude for their business' },
    { id: 'referral_request', name: 'Referral Request', description: 'Ask for referrals' },
    { id: 'annual_review', name: 'Annual Review', description: 'Yearly mortgage checkup' },
    { id: 'refinance_opportunity', name: 'Refinance Opportunity', description: 'Alert about refinance options' },
  ],
  'General': [
    { id: 'custom', name: 'Custom Email', description: 'Write your own message' },
    { id: 'market_update', name: 'Market Update', description: 'Share market insights' },
    { id: 'holiday_greeting', name: 'Holiday Greeting', description: 'Seasonal well wishes' },
    { id: 'birthday', name: 'Birthday Wishes', description: 'Happy birthday message' },
  ],
};

function EmailComposerModal({ isOpen, onClose, recipient, entityType, entityData }) {
  const [step, setStep] = useState(1); // 1: Select Template, 2: Review/Edit, 3: Sending
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [subject, setSubject] = useState('');
  const [emailBody, setEmailBody] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  // Salesforce connection state
  const [sfConnected, setSfConnected] = useState(false);
  const [sendMethod, setSendMethod] = useState(null);

  // Insert Video state
  const [showVideoRecorder, setShowVideoRecorder] = useState(false);
  const [isUploadingVideo, setIsUploadingVideo] = useState(false);
  const [videoUploadProgress, setVideoUploadProgress] = useState(0);
  const [hasVideoAttached, setHasVideoAttached] = useState(false);

  // Insert Calendar state
  const [showCalendarPicker, setShowCalendarPicker] = useState(false);
  const [bookingLinks, setBookingLinks] = useState([]);
  const [hasCalendarAttached, setHasCalendarAttached] = useState(false);

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setStep(1);
      setSelectedCategory(null);
      setSelectedTemplate(null);
      setSubject('');
      setEmailBody('');
      setError(null);
      setSuccess(false);
      setSendMethod(null);
      setShowVideoRecorder(false);
      setIsUploadingVideo(false);
      setVideoUploadProgress(0);
      setHasVideoAttached(false);
      setShowCalendarPicker(false);
      setHasCalendarAttached(false);
    }
  }, [isOpen]);

  // Check Salesforce connection status on modal open
  useEffect(() => {
    if (isOpen) {
      const checkSfStatus = async () => {
        try {
          const { data } = await api.get('/api/integrations/salesforce/status');
          setSfConnected(data.connected === true);
        } catch (err) {
          setSfConnected(false);
        }
      };
      checkSfStatus();
    }
  }, [isOpen]);

  // Fetch booking links when modal opens
  useEffect(() => {
    if (isOpen) {
      const fetchBookingLinks = async () => {
        try {
          const { data } = await api.get('/api/v1/scheduler/booking-links');
          setBookingLinks(data.booking_links || []);
        } catch (err) {
          console.error('Failed to fetch booking links:', err);
        }
      };
      fetchBookingLinks();
    }
  }, [isOpen]);

  const handleTemplateSelect = async (template) => {
    setSelectedTemplate(template);
    setError(null);

    if (template.id === 'custom') {
      // For custom, just show empty form
      setSubject('');
      setEmailBody('');
      setStep(2);
      return;
    }

    // Generate AI email based on template
    setIsGenerating(true);
    try {
      const { data } = await api.post('/api/v1/ai/generate-email', {
        template_id: template.id,
        template_name: template.name,
        recipient_name: recipient?.name || 'Valued Client',
        recipient_email: recipient?.email || '',
        entity_type: entityType, // 'lead', 'loan', 'mum'
        entity_data: entityData || {},
      });

      setSubject(data.subject || `${template.name}`);
      setEmailBody(data.body || '');
      setStep(2);
    } catch (err) {
      console.error('Error generating email:', err);
      setError('Failed to generate email. Please try again.');
      // Still allow them to proceed with empty form
      setSubject(template.name);
      setEmailBody('');
      setStep(2);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSendEmail = async () => {
    if (!recipient?.email) {
      setError('No recipient email address');
      return;
    }

    if (!subject.trim() || !emailBody.trim()) {
      setError('Please enter both subject and email body');
      return;
    }

    setIsSending(true);
    setError(null);

    try {
      const { data: responseData } = await api.post('/api/v1/ai/send-composed-email', {
        to_email: recipient.email,
        to_name: recipient.name || '',
        subject: subject,
        body: emailBody,
        entity_type: entityType,
        entity_id: entityData?.id,
        template_used: selectedTemplate?.id || 'custom',
      });

      setSendMethod(responseData.send_method || null);
      setSuccess(true);
      setStep(3);

      // Auto close after success
      setTimeout(() => {
        onClose();
      }, 3000);
    } catch (err) {
      console.error('Error sending email:', err);
      setError(err.message || 'Failed to send email. Please try again.');
    } finally {
      setIsSending(false);
    }
  };

  const handleRegenerateEmail = async () => {
    if (selectedTemplate && selectedTemplate.id !== 'custom') {
      await handleTemplateSelect(selectedTemplate);
    }
  };

  // Handle video recording complete → upload to S3 → insert marker
  const handleVideoRecordingComplete = useCallback(async (blob, duration) => {
    setShowVideoRecorder(false);
    setIsUploadingVideo(true);
    setVideoUploadProgress(0);
    setError(null);

    try {
      // Step 1: Get presigned upload URL
      const { data: uploadData } = await api.post('/api/v1/portal-video/upload-url', {
        portal_type: 'email',
        recipient_id: 0,
        content_type: 'video/webm',
        filename: `email_video_${Date.now()}.webm`
      });

      const { upload_url, video_key } = uploadData;
      setVideoUploadProgress(20);

      // Step 2: Upload blob to S3 (raw fetch - external presigned URL)
      const uploadResponse = await fetch(upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': 'video/webm' },
        body: blob
      });

      if (!uploadResponse.ok) throw new Error('Failed to upload video to storage');
      setVideoUploadProgress(70);

      // Step 3: Complete upload (non-blocking -- video is already on S3)
      try {
        await api.post('/api/v1/portal-video/complete', {
          portal_type: 'email',
          recipient_id: 0,
          video_key: video_key,
          message: null,
          send_notification: false,
          duration_seconds: duration
        });
      } catch (completeErr) {
        console.warn('Video metadata save failed (non-critical):', completeErr);
      }
      setVideoUploadProgress(100);

      // Insert video marker into email body
      const videoUrl = `${API_BASE_URL}/api/v1/portal-video/view/${video_key}`;
      const videoMarker = `\n[VIDEO MESSAGE - Click to watch: ${videoUrl}]\n`;
      setEmailBody(prev => prev + videoMarker);
      setHasVideoAttached(true);

    } catch (err) {
      console.error('Video upload error:', err);
      setError(err.message || 'Failed to upload video. Please try again.');
    } finally {
      setIsUploadingVideo(false);
      setVideoUploadProgress(0);
    }
  }, []);

  // Handle calendar link insertion
  const handleInsertCalendarLink = useCallback((link) => {
    const bookingUrl = `${APP_BASE}/book/${link.slug}`;
    const calendarMarker = `\nSchedule a time to talk: ${bookingUrl}\n`;
    setEmailBody(prev => prev + calendarMarker);
    setHasCalendarAttached(true);
    setShowCalendarPicker(false);
  }, []);

  // Handle Insert Calendar button click
  const handleCalendarClick = useCallback(() => {
    if (bookingLinks.length === 0) {
      setError('No booking links found. Please create one in Smart Scheduler first.');
      return;
    }
    if (bookingLinks.length === 1) {
      handleInsertCalendarLink(bookingLinks[0]);
    } else {
      setShowCalendarPicker(prev => !prev);
    }
  }, [bookingLinks, handleInsertCalendarLink]);

  if (!isOpen) return null;

  return (
    <div className="email-composer-overlay" onClick={onClose}>
      <div className="email-composer-modal" onClick={e => e.stopPropagation()}>
        <button className="email-composer-close" onClick={onClose}>×</button>

        <div className="email-composer-header">
          <h2>✉️ Compose Email</h2>
          <p className="recipient-info">
            To: <strong>{recipient?.name || 'Unknown'}</strong>
          </p>
        </div>

        {/* Step Indicator */}
        <div className="email-steps">
          <div className={`step ${step >= 1 ? 'active' : ''} ${step > 1 ? 'completed' : ''}`}>
            <span className="step-number">1</span>
            <span className="step-label">Choose Template</span>
          </div>
          <div className={`step ${step >= 2 ? 'active' : ''} ${step > 2 ? 'completed' : ''}`}>
            <span className="step-number">2</span>
            <span className="step-label">Review & Edit</span>
          </div>
          <div className={`step ${step >= 3 ? 'active' : ''}`}>
            <span className="step-number">3</span>
            <span className="step-label">Send</span>
          </div>
        </div>

        {error && (
          <div className="email-error">
            <span>⚠️ {error}</span>
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        {/* Step 1: Template Selection */}
        {step === 1 && (
          <div className="template-selection">
            {isGenerating ? (
              <div className="generating-email">
                <div className="spinner"></div>
                <p>AI is crafting your email...</p>
              </div>
            ) : (
              <>
                <div className="template-categories">
                  {Object.keys(EMAIL_TEMPLATES).map(category => (
                    <button
                      key={category}
                      className={`category-btn ${selectedCategory === category ? 'active' : ''}`}
                      onClick={() => setSelectedCategory(category)}
                    >
                      {category}
                    </button>
                  ))}
                </div>

                {selectedCategory && (
                  <div className="template-list">
                    <h3>{selectedCategory}</h3>
                    <div className="templates-grid">
                      {EMAIL_TEMPLATES[selectedCategory].map(template => (
                        <button
                          key={template.id}
                          className="template-card"
                          onClick={() => handleTemplateSelect(template)}
                        >
                          <span className="template-name">{template.name}</span>
                          <span className="template-desc">{template.description}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {!selectedCategory && (
                  <div className="template-hint">
                    <p>👆 Select a category above to see available email templates</p>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Step 2: Review & Edit */}
        {step === 2 && (
          <div className="email-editor">
            <div className="editor-toolbar">
              <button
                className="btn-back"
                onClick={() => setStep(1)}
              >
                ← Back to Templates
              </button>
              <div className="editor-toolbar-right">
                {sfConnected && (
                  <span className="sf-send-badge">
                    ☁️ Sending via Salesforce
                  </span>
                )}
                {selectedTemplate?.id !== 'custom' && (
                  <button
                    className="btn-regenerate"
                    onClick={handleRegenerateEmail}
                    disabled={isGenerating}
                  >
                    🔄 Regenerate
                  </button>
                )}
              </div>
            </div>

            <div className="editor-form">
              <div className="form-group">
                <label>Subject Line</label>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Enter email subject..."
                  className="subject-input"
                />
              </div>

              <div className="form-group">
                <label>Email Body</label>

                {/* Video Recorder (replaces textarea when active) */}
                {showVideoRecorder ? (
                  <div className="video-recorder-wrapper">
                    <VideoRecorder
                      onRecordingComplete={handleVideoRecordingComplete}
                      onCancel={() => setShowVideoRecorder(false)}
                      maxDuration={120}
                    />
                  </div>
                ) : (
                  <textarea
                    value={emailBody}
                    onChange={(e) => setEmailBody(e.target.value)}
                    placeholder="Compose your email message..."
                    className="body-textarea"
                    rows={12}
                  />
                )}

                {/* Video upload progress */}
                {isUploadingVideo && (
                  <div className="video-uploading">
                    <div className="upload-progress-bar">
                      <div className="upload-progress-fill" style={{ width: `${videoUploadProgress}%` }}></div>
                    </div>
                    <span className="upload-progress-text">Uploading video... {videoUploadProgress}%</span>
                  </div>
                )}

                {/* Insert Toolbar */}
                {!showVideoRecorder && (
                  <div className="insert-toolbar">
                    <div className="insert-toolbar-left">
                      <button
                        type="button"
                        className="insert-btn"
                        onClick={() => setShowVideoRecorder(true)}
                        disabled={isUploadingVideo}
                        title="Record and insert a video message"
                      >
                        <span className="insert-btn-icon">📹</span>
                        Insert Video
                      </button>

                      <div className="insert-btn-wrapper">
                        <button
                          type="button"
                          className="insert-btn"
                          onClick={handleCalendarClick}
                          title="Insert your scheduling link"
                        >
                          <span className="insert-btn-icon">📅</span>
                          Insert Calendar Link
                        </button>

                        {/* Booking link dropdown */}
                        {showCalendarPicker && bookingLinks.length > 1 && (
                          <div className="booking-link-dropdown">
                            {bookingLinks.map(link => (
                              <button
                                key={link.id}
                                className="booking-link-option"
                                onClick={() => handleInsertCalendarLink(link)}
                              >
                                <span className="booking-link-name">{link.link_name}</span>
                                {link.description && (
                                  <span className="booking-link-desc">{link.description}</span>
                                )}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Attached badges */}
                    <div className="insert-toolbar-badges">
                      {hasVideoAttached && (
                        <span className="inserted-badge video-badge">
                          📹 Video attached
                        </span>
                      )}
                      {hasCalendarAttached && (
                        <span className="inserted-badge calendar-badge">
                          📅 Calendar link added
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="editor-actions">
              <button
                className="btn-cancel"
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                className="btn-send"
                onClick={handleSendEmail}
                disabled={isSending || !subject.trim() || !emailBody.trim()}
              >
                {isSending ? (
                  <>
                    <span className="btn-spinner"></span>
                    Sending...
                  </>
                ) : (
                  <>
                    📤 Send Email
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Success */}
        {step === 3 && success && (
          <div className="email-success">
            <div className="success-icon">✅</div>
            <h3>Email Sent Successfully!</h3>
            <p>Your email has been delivered to <strong>{recipient?.name || 'the recipient'}</strong></p>
            {sendMethod === 'salesforce' && (
              <p className="sf-success-note">
                ☁️ Sent via Salesforce — activity logged to contact record
              </p>
            )}
            <p className="auto-close">This window will close automatically...</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default EmailComposerModal;
