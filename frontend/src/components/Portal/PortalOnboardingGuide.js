/**
 * Portal Onboarding Guide
 *
 * Shows instructional tooltips for first-time portal visitors
 * explaining what each section of the portal does.
 */

import React, { useState, useEffect, useCallback } from 'react';
import './PortalOnboardingGuide.css';

// Onboarding steps configuration for Active Loan Portal
const ONBOARDING_STEPS = [
  {
    id: 'welcome',
    title: 'Welcome to Your Loan Portal',
    description: 'This is your personal dashboard to track your loan progress, upload documents, and communicate with your loan team. Let\'s take a quick tour!',
    position: 'center',
    targetSelector: null, // No specific target - centered modal
  },
  {
    id: 'action-items',
    title: '⚡ Action Required',
    description: 'This is your task center! When you have items to complete, they\'ll appear here. Click each task to view details and mark it done. Completing these keeps your loan moving forward quickly!',
    position: 'bottom',
    targetSelector: '.applicant-tasks-section, .all-caught-up-section',
    highlightNav: false,
    isPrimary: true,
  },
  {
    id: 'overview',
    title: 'Overview Tab',
    description: 'Your home base! See your loan status, action items, documents needed, and loan progress all in one place.',
    position: 'bottom',
    targetSelector: '.purl-tab-btn.first, .portal-nav button:first-child',
    highlightNav: true,
  },
  {
    id: 'application',
    title: 'Application Tab',
    description: 'Review and update your loan application details. Make sure all your information is accurate.',
    position: 'bottom',
    targetSelector: '.purl-tab-btn:nth-child(2), .portal-nav button:nth-child(2)',
    highlightNav: true,
  },
  {
    id: 'documents',
    title: 'Documents Tab',
    description: 'Upload required documents here. You\'ll see a checklist of what\'s needed and can track what\'s been approved.',
    position: 'bottom',
    targetSelector: '.purl-tab-btn:nth-child(3), .portal-nav button:nth-child(3)',
    highlightNav: true,
  },
  {
    id: 'loan-quote',
    title: 'Loan Comparison Tab',
    description: 'Compare loan options side-by-side with detailed costs, rates, and monthly payment breakdowns.',
    position: 'bottom',
    targetSelector: '.purl-tab-btn:nth-child(4), .portal-nav button:nth-child(4)',
    highlightNav: true,
  },
  {
    id: 'pre-approval',
    title: 'Pre-Approval Tab',
    description: 'Access your pre-approval letter when available. Download or share it with your real estate agent.',
    position: 'bottom',
    targetSelector: '.purl-tab-btn:nth-child(5), .portal-nav button:nth-child(5)',
    highlightNav: true,
  },
  {
    id: 'contacts',
    title: 'Contacts Tab',
    description: 'Find contact information for your loan team. Reach out anytime you have questions.',
    position: 'bottom',
    targetSelector: '.purl-tab-btn.last, .portal-nav button:last-child',
    highlightNav: true,
  },
  {
    id: 'complete',
    title: 'You\'re All Set!',
    description: 'That\'s the basics! Explore the portal at your own pace. Your loan officer is here to help if you have questions.',
    position: 'center',
    targetSelector: null,
  },
];

const PortalOnboardingGuide = ({ workspaceSlug, onComplete, forceShow = false }) => {
  const [isVisible, setIsVisible] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [tooltipPosition, setTooltipPosition] = useState({ top: 0, left: 0 });

  // Check if user has seen the guide
  useEffect(() => {
    const storageKey = `portal_onboarding_${workspaceSlug}`;
    const hasSeenGuide = localStorage.getItem(storageKey);

    if (forceShow || !hasSeenGuide) {
      // Small delay to let the portal render first
      const timer = setTimeout(() => {
        setIsVisible(true);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [workspaceSlug, forceShow]);

  // Find first matching element from comma-separated selectors
  const findTarget = useCallback((selectorString) => {
    if (!selectorString) return null;
    const selectors = selectorString.split(',').map(s => s.trim());
    for (const selector of selectors) {
      try {
        const el = document.querySelector(selector);
        if (el) return el;
      } catch (e) {
        // Invalid selector, try next
      }
    }
    return null;
  }, []);

  // Position tooltip near target element
  const positionTooltip = useCallback(() => {
    const step = ONBOARDING_STEPS[currentStep];
    if (!step.targetSelector) {
      // Center in viewport for welcome/complete steps
      setTooltipPosition({
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        position: 'fixed',
      });
      return;
    }

    const target = findTarget(step.targetSelector);
    if (!target) {
      setTooltipPosition({
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        position: 'fixed',
      });
      return;
    }

    const rect = target.getBoundingClientRect();
    const tooltipWidth = 340;
    const tooltipHeight = 180;
    const padding = 16;

    let top, left, transform = '';

    switch (step.position) {
      case 'bottom':
        top = rect.bottom + padding;
        left = rect.left + rect.width / 2;
        transform = 'translateX(-50%)';
        break;
      case 'top':
        top = rect.top - tooltipHeight - padding;
        left = rect.left + rect.width / 2;
        transform = 'translateX(-50%)';
        break;
      case 'left':
        top = rect.top + rect.height / 2;
        left = rect.left - tooltipWidth - padding;
        transform = 'translateY(-50%)';
        break;
      case 'right':
        top = rect.top + rect.height / 2;
        left = rect.right + padding;
        transform = 'translateY(-50%)';
        break;
      default:
        top = '50%';
        left = '50%';
        transform = 'translate(-50%, -50%)';
    }

    // Ensure tooltip stays in viewport
    if (typeof top === 'number') {
      top = Math.max(padding, Math.min(top, window.innerHeight - tooltipHeight - padding));
    }
    if (typeof left === 'number') {
      left = Math.max(padding, Math.min(left, window.innerWidth - tooltipWidth - padding));
    }

    setTooltipPosition({
      top: typeof top === 'number' ? `${top}px` : top,
      left: typeof left === 'number' ? `${left}px` : left,
      transform,
      position: 'fixed',
    });
  }, [currentStep, findTarget]);

  // Reposition on step change or window resize
  useEffect(() => {
    if (isVisible) {
      positionTooltip();
      window.addEventListener('resize', positionTooltip);
      return () => window.removeEventListener('resize', positionTooltip);
    }
  }, [isVisible, currentStep, positionTooltip]);

  // Handle next step
  const handleNext = () => {
    if (currentStep < ONBOARDING_STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      completeGuide();
    }
  };

  // Handle previous step
  const handlePrev = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  // Complete the guide
  const completeGuide = () => {
    const storageKey = `portal_onboarding_${workspaceSlug}`;
    localStorage.setItem(storageKey, 'true');
    setIsVisible(false);
    if (onComplete) {
      onComplete();
    }
  };

  // Skip the guide
  const handleSkip = () => {
    completeGuide();
  };

  if (!isVisible) {
    return null;
  }

  const step = ONBOARDING_STEPS[currentStep];
  const isFirstStep = currentStep === 0;
  const isLastStep = currentStep === ONBOARDING_STEPS.length - 1;
  const isCenteredStep = step.position === 'center';

  return (
    <div className="portal-onboarding-overlay">
      {/* Highlight target element if applicable */}
      {step.targetSelector && (
        <TargetHighlight selector={step.targetSelector} />
      )}

      {/* Tooltip */}
      <div
        className={`portal-onboarding-tooltip ${isCenteredStep ? 'centered' : ''} ${step.isPrimary ? 'primary' : ''} position-${step.position}`}
        style={tooltipPosition}
      >
        {/* Arrow pointer for non-centered tooltips */}
        {!isCenteredStep && <div className={`tooltip-arrow arrow-${step.position}`} />}

        <div className="tooltip-header">
          <h3>{step.title}</h3>
          {!isLastStep && (
            <button className="skip-btn" onClick={handleSkip}>
              Skip Tour
            </button>
          )}
        </div>

        <div className="tooltip-body">
          <p>{step.description}</p>
        </div>

        <div className="tooltip-footer">
          {/* Progress dots */}
          <div className="progress-dots">
            {ONBOARDING_STEPS.map((_, index) => (
              <span
                key={index}
                className={`dot ${index === currentStep ? 'active' : ''} ${index < currentStep ? 'completed' : ''}`}
              />
            ))}
          </div>

          {/* Navigation buttons */}
          <div className="tooltip-actions">
            {!isFirstStep && (
              <button className="prev-btn" onClick={handlePrev}>
                Back
              </button>
            )}
            <button className="next-btn" onClick={handleNext}>
              {isLastStep ? 'Get Started' : 'Next'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// Helper to find first matching element from comma-separated selectors
const findTargetElement = (selectorString) => {
  if (!selectorString) return null;
  const selectors = selectorString.split(',').map(s => s.trim());
  for (const selector of selectors) {
    try {
      const el = document.querySelector(selector);
      if (el) return el;
    } catch (e) {
      // Invalid selector, try next
    }
  }
  return null;
};

// Component to highlight target element
const TargetHighlight = ({ selector }) => {
  const [rect, setRect] = useState(null);

  useEffect(() => {
    const element = findTargetElement(selector);
    if (element) {
      const updateRect = () => {
        const r = element.getBoundingClientRect();
        setRect({
          top: r.top - 4,
          left: r.left - 4,
          width: r.width + 8,
          height: r.height + 8,
        });
      };
      updateRect();
      window.addEventListener('resize', updateRect);
      window.addEventListener('scroll', updateRect);
      return () => {
        window.removeEventListener('resize', updateRect);
        window.removeEventListener('scroll', updateRect);
      };
    }
  }, [selector]);

  if (!rect) return null;

  return (
    <div
      className="target-highlight"
      style={{
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height,
      }}
    />
  );
};

export default PortalOnboardingGuide;
