import React from 'react';

const TutorialView = ({ setView }) => (
  <div className="scheduler-tutorial-view">
    <div className="tutorial-header">
      <h3>Video Meetings Tutorial</h3>
      <p className="tutorial-intro">Learn how to maximize productivity with our AI-powered video conferencing system</p>
    </div>

    <div className="tutorial-sections">
      {/* Quick Start */}
      <div className="tutorial-section">
        <div className="section-icon">&#x1F680;</div>
        <h4>Quick Start Guide</h4>
        <div className="section-content">
          <ol>
            <li><strong>Create Meeting Types:</strong> Go to "Meeting Types" tab and click "Seed Defaults" to create standard meeting types for mortgage discussions</li>
            <li><strong>Set Your Hours:</strong> Navigate to "Settings" tab and configure your working hours for each day of the week</li>
            <li><strong>Schedule a Meeting:</strong> Click "Schedule Meeting" to create a new video meeting with all the AI features</li>
            <li><strong>Start Instant:</strong> Use "Start Instant" for immediate meetings without scheduling</li>
            <li><strong>Share Booking Links:</strong> Create public booking links in the "Booking Links" tab</li>
          </ol>
        </div>
      </div>

      {/* Meeting Types */}
      <div className="tutorial-section">
        <div className="section-icon">&#x1F4CB;</div>
        <h4>Meeting Types</h4>
        <div className="section-content">
          <p>Customize meeting types for different video call purposes:</p>
          <ul>
            <li><strong>Discovery Call:</strong> Initial video consultation with new leads (15-30 min)</li>
            <li><strong>Pre-Approval Review:</strong> Screen share to review pre-approval documents (30-45 min)</li>
            <li><strong>Document Review Session:</strong> Collect and review mortgage documents on video (30-60 min)</li>
            <li><strong>Rate Lock Discussion:</strong> Review market conditions and lock options via video (20-30 min)</li>
            <li><strong>Closing Preparation:</strong> Final walkthrough before closing day (45-60 min)</li>
            <li><strong>Post-Close Review:</strong> Follow-up after closing to ensure satisfaction (15-30 min)</li>
            <li><strong>Team Sync:</strong> Internal team meetings and coordination (30 min)</li>
          </ul>
          <p className="tip">Tip: Click on any meeting type card to edit its settings, durations, and colors.</p>
        </div>
      </div>

      {/* Booking Links */}
      <div className="tutorial-section">
        <div className="section-icon">&#x1F517;</div>
        <h4>Booking Links</h4>
        <div className="section-content">
          <p>Create shareable links for clients to book video meetings directly:</p>
          <ul>
            <li><strong>Custom URL Slugs:</strong> Create memorable URLs like /meeting/book/john-smith</li>
            <li><strong>Type Filtering:</strong> Limit which meeting types are available on each link</li>
            <li><strong>Analytics:</strong> Track views and bookings for each link</li>
            <li><strong>Easy Sharing:</strong> Copy links with one click to share via email or text</li>
          </ul>
        </div>
      </div>

      {/* AI Features */}
      <div className="tutorial-section highlight">
        <div className="section-icon">&#x1F916;</div>
        <h4>AI-Powered Features</h4>
        <div className="section-content">
          <p>Video Meetings includes advanced AI capabilities:</p>
          <ul>
            <li><strong>AI Meeting Assistant:</strong> Real-time suggestions and note-taking during calls</li>
            <li><strong>Auto-Transcription:</strong> Automatic transcription of all video meetings</li>
            <li><strong>Smart Summaries:</strong> AI-generated meeting summaries and action items</li>
            <li><strong>Smart Scheduling:</strong> AI suggests optimal meeting times based on patterns</li>
            <li><strong>Auto-Reschedule:</strong> Automatically suggests alternatives when conflicts arise</li>
            <li><strong>Smart Reminders:</strong> AI-optimized reminder timing based on engagement</li>
          </ul>
          <p className="tip">Enable AI features in Settings - AI Settings tab</p>
        </div>
      </div>

      {/* Recording Features */}
      <div className="tutorial-section">
        <div className="section-icon">&#x1F3A5;</div>
        <h4>Recording & Transcription</h4>
        <div className="section-content">
          <p>Comprehensive meeting documentation:</p>
          <ul>
            <li><strong>Auto-Recording:</strong> Meetings are automatically recorded when enabled</li>
            <li><strong>Cloud Storage:</strong> Recordings are securely stored and accessible anytime</li>
            <li><strong>Searchable Transcripts:</strong> Full-text search across all meeting transcripts</li>
            <li><strong>Timestamp Navigation:</strong> Jump to specific moments in recordings</li>
            <li><strong>Compliance Ready:</strong> Recordings meet mortgage compliance requirements</li>
          </ul>
        </div>
      </div>

      {/* Best Practices */}
      <div className="tutorial-section best-practices">
        <div className="section-icon">&#x1F4A1;</div>
        <h4>Best Practices</h4>
        <div className="section-content">
          <ul>
            <li><strong>Test Equipment:</strong> Ensure camera and microphone work before important calls</li>
            <li><strong>Buffer Time:</strong> Add 5-15 minute buffers between meetings for preparation</li>
            <li><strong>Enable Recording:</strong> Always record important client discussions for compliance</li>
            <li><strong>Use Waiting Room:</strong> Enable waiting room for better meeting control</li>
            <li><strong>Send Reminders:</strong> Configure automatic reminders to reduce no-shows</li>
            <li><strong>Review AI Summaries:</strong> Check AI-generated summaries for accuracy after meetings</li>
          </ul>
        </div>
      </div>
    </div>

    <div className="tutorial-footer">
      <p>Need more help? Contact support or visit our documentation.</p>
      <div className="tutorial-actions">
        <button className="start-btn" onClick={() => setView('types')}>
          Meeting Types
        </button>
        <button className="setup-btn" onClick={() => setView('settings')}>
          Configure Settings
        </button>
      </div>
    </div>
  </div>
);

export default TutorialView;
