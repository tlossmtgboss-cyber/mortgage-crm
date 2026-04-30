import React, { useState } from 'react';
import './OnboardingWizard.css';

const OnboardingWizard = ({ user, onComplete }) => {
  const [currentStep, setCurrentStep] = useState(0);

  const steps = [
    {
      title: "Welcome to Perennia AI UVIP",
      icon: "🎉",
      content: (
        <div className="welcome-step">
          <h2>Video Intelligence for Mortgage Professionals</h2>
          <p>You now have access to:</p>
          <ul className="feature-list">
            <li>
              <span className="icon">📞</span>
              <div>
                <strong>Automatic Call Recording</strong>
                <p>Every call is recorded and transcribed with AI analysis</p>
              </div>
            </li>
            <li>
              <span className="icon">🎬</span>
              <div>
                <strong>Video Clips</strong>
                <p>Record personalized videos to send to borrowers</p>
              </div>
            </li>
            <li>
              <span className="icon">🤖</span>
              <div>
                <strong>AI Coaching</strong>
                <p>Get insights on every conversation to improve performance</p>
              </div>
            </li>
            {user?.role === 'manager' && (
              <li>
                <span className="icon">📊</span>
                <div>
                  <strong>Manager Dashboard</strong>
                  <p>Track team performance and coaching priorities</p>
                </div>
              </li>
            )}
          </ul>
        </div>
      )
    },
    {
      title: "Your First Call",
      icon: "📞",
      content: (
        <div className="call-step">
          <h2>Make Your First Call</h2>
          <p>All calls through Perennia AI are automatically recorded.</p>

          <div className="demo-placeholder">
            <div className="demo-icon">📱</div>
            <p>Call recording demo</p>
          </div>

          <ol className="instructions">
            <li>Click <strong>Make Call</strong> in the top navigation</li>
            <li>Enter borrower's phone number</li>
            <li>Have your conversation normally</li>
            <li>After the call, view transcript and AI analysis in <strong>Meetings</strong></li>
          </ol>

          <div className="tip">
            <span className="tip-icon">💡</span>
            <p><strong>Tip:</strong> The AI analyzes talk-listen ratio, questions asked, and borrower concerns automatically.</p>
          </div>
        </div>
      )
    },
    {
      title: "Record a Video Clip",
      icon: "🎬",
      content: (
        <div className="clip-step">
          <h2>Send Your First Video</h2>
          <p>Record screen + camera videos to explain complex topics to borrowers.</p>

          <div className="demo-placeholder">
            <div className="demo-icon">🎥</div>
            <p>Video clip demo</p>
          </div>

          <div className="templates">
            <h3>Popular Templates</h3>
            <div className="template-grid">
              <div className="template-card">
                <span className="template-icon">🔒</span>
                <strong>Rate Lock Explanation</strong>
                <p>Explain rate locks and timing</p>
              </div>
              <div className="template-card">
                <span className="template-icon">📄</span>
                <strong>Document Checklist</strong>
                <p>Walk through required docs</p>
              </div>
              <div className="template-card">
                <span className="template-icon">✅</span>
                <strong>Pre-Approval Next Steps</strong>
                <p>Congratulate and explain next steps</p>
              </div>
            </div>
          </div>

          <p className="action-prompt">Go to <strong>Clips</strong> → <strong>New Clip</strong> to get started.</p>
        </div>
      )
    },
    {
      title: "Understanding Your Analytics",
      icon: "📊",
      content: (
        <div className="analytics-step">
          <h2>Track Your Performance</h2>
          <p>After each call, see detailed analytics and AI coaching recommendations.</p>

          <div className="metrics-preview">
            <div className="metric">
              <span className="metric-icon">🎯</span>
              <div>
                <strong>Engagement Score</strong>
                <p>Overall conversation quality (0-1.0)</p>
              </div>
            </div>
            <div className="metric">
              <span className="metric-icon">👂</span>
              <div>
                <strong>Talk-Listen Ratio</strong>
                <p>Balance between speaking and listening</p>
              </div>
            </div>
            <div className="metric">
              <span className="metric-icon">❓</span>
              <div>
                <strong>Questions Asked</strong>
                <p>Discovery and engagement signals</p>
              </div>
            </div>
            <div className="metric">
              <span className="metric-icon">😊</span>
              <div>
                <strong>Sentiment Analysis</strong>
                <p>Positive vs negative language</p>
              </div>
            </div>
          </div>

          <div className="coaching-preview">
            <h3>AI Coaching Example</h3>
            <div className="coaching-card">
              <span className="priority high">High Priority</span>
              <p><strong>Listening:</strong> Your talk ratio was 78%. Try to listen more and ask more questions to better understand the borrower's needs.</p>
            </div>
          </div>
        </div>
      )
    },
    {
      title: "You're All Set!",
      icon: "✅",
      content: (
        <div className="complete-step">
          <h2>Ready to Close More Loans</h2>
          <p>You're all set to use Perennia AI UVIP. Here's what to do next:</p>

          <div className="next-steps">
            <div className="next-step">
              <span className="step-number">1</span>
              <div>
                <strong>Make your first call</strong>
                <p>All calls are automatically recorded and analyzed</p>
              </div>
            </div>
            <div className="next-step">
              <span className="step-number">2</span>
              <div>
                <strong>Record a video clip</strong>
                <p>Send personalized videos to borrowers</p>
              </div>
            </div>
            <div className="next-step">
              <span className="step-number">3</span>
              <div>
                <strong>Review your analytics</strong>
                <p>See AI insights after each conversation</p>
              </div>
            </div>
          </div>

          <div className="help-section">
            <h3>Need Help?</h3>
            <div className="help-links">
              <a href="/help" className="help-link">
                <span>📚</span>
                <span>Browse Help Docs</span>
              </a>
              <a href="/help/videos" className="help-link">
                <span>🎥</span>
                <span>Watch Video Tutorials</span>
              </a>
              <a href="mailto:support@perenniaai.com" className="help-link">
                <span>✉️</span>
                <span>Contact Support</span>
              </a>
            </div>
          </div>
        </div>
      )
    }
  ];

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      // Mark onboarding as complete
      localStorage.setItem('onboarding_completed', 'true');
      onComplete();
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSkip = () => {
    localStorage.setItem('onboarding_completed', 'true');
    onComplete();
  };

  return (
    <div className="onboarding-modal-overlay">
      <div className="onboarding-modal">
        <button className="skip-button" onClick={handleSkip}>
          Skip Tour
        </button>

        <div className="onboarding-header">
          <div className="step-icon">{steps[currentStep].icon}</div>
          <h1>{steps[currentStep].title}</h1>

          <div className="progress-bar">
            {steps.map((_, idx) => (
              <div
                key={idx}
                className={`progress-dot ${idx <= currentStep ? 'active' : ''}`}
              />
            ))}
          </div>
        </div>

        <div className="onboarding-content">
          {steps[currentStep].content}
        </div>

        <div className="onboarding-footer">
          <div className="footer-left">
            {currentStep > 0 && (
              <button className="back-button" onClick={handleBack}>
                Back
              </button>
            )}
            <div className="step-counter">
              Step {currentStep + 1} of {steps.length}
            </div>
          </div>
          <button
            className="next-button"
            onClick={handleNext}
          >
            {currentStep === steps.length - 1 ? "Get Started" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default OnboardingWizard;
