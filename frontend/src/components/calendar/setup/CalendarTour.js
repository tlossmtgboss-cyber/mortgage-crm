/**
 * CalendarTour - In-app feature walkthrough for the Calendar
 *
 * Renders a spotlight overlay that dims everything except the highlighted
 * UI element, with a tooltip containing the step title, description,
 * navigation buttons, and progress dots.
 *
 * Uses useCalendarTour() hook for state management.
 * Auto-positions the tooltip so it stays within the viewport.
 * Scrolls to elements that are not visible.
 */

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import '../../../styles/calendar-tour.css';

// Padding around the spotlighted element
const SPOTLIGHT_PADDING = 8;
// Gap between spotlight and tooltip
const TOOLTIP_GAP = 14;
// Viewport margin to keep tooltip inside the screen
const VIEWPORT_MARGIN = 16;

/**
 * Get the bounding rect of a DOM element identified by CSS selector.
 * Returns null if the element is not found.
 */
function getTargetRect(selector) {
  if (!selector) return null;
  const el = document.querySelector(selector);
  if (!el) return null;
  return { el, rect: el.getBoundingClientRect() };
}

/**
 * Scroll an element into view if it is not fully visible.
 */
function scrollToTarget(el) {
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const inView =
    rect.top >= 0 &&
    rect.left >= 0 &&
    rect.bottom <= window.innerHeight &&
    rect.right <= window.innerWidth;
  if (!inView) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
  }
}

/**
 * Calculate optimal tooltip position given spotlight rect and preferred placement.
 * Returns { top, left, arrowPosition }.
 */
function calcTooltipPosition(spotlightRect, tooltipWidth, tooltipHeight, placement) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  // Center of the spotlight
  const cx = spotlightRect.left + spotlightRect.width / 2;
  const cy = spotlightRect.top + spotlightRect.height / 2;

  let top, left, arrowPosition;

  switch (placement) {
    case 'bottom':
      top = spotlightRect.bottom + TOOLTIP_GAP;
      left = cx - tooltipWidth / 2;
      arrowPosition = 'top';
      break;
    case 'top':
      top = spotlightRect.top - tooltipHeight - TOOLTIP_GAP;
      left = cx - tooltipWidth / 2;
      arrowPosition = 'bottom';
      break;
    case 'left':
      top = cy - tooltipHeight / 2;
      left = spotlightRect.left - tooltipWidth - TOOLTIP_GAP;
      arrowPosition = 'right';
      break;
    case 'right':
      top = cy - tooltipHeight / 2;
      left = spotlightRect.right + TOOLTIP_GAP;
      arrowPosition = 'left';
      break;
    default:
      top = spotlightRect.bottom + TOOLTIP_GAP;
      left = cx - tooltipWidth / 2;
      arrowPosition = 'top';
  }

  // Clamp to viewport
  if (left < VIEWPORT_MARGIN) left = VIEWPORT_MARGIN;
  if (left + tooltipWidth > vw - VIEWPORT_MARGIN) left = vw - VIEWPORT_MARGIN - tooltipWidth;
  if (top < VIEWPORT_MARGIN) {
    // Flip to bottom if we run off the top
    top = spotlightRect.bottom + TOOLTIP_GAP;
    arrowPosition = 'top';
  }
  if (top + tooltipHeight > vh - VIEWPORT_MARGIN) {
    // Flip to top if we run off the bottom
    top = spotlightRect.top - tooltipHeight - TOOLTIP_GAP;
    arrowPosition = 'bottom';
  }

  // Final clamp
  top = Math.max(VIEWPORT_MARGIN, Math.min(top, vh - tooltipHeight - VIEWPORT_MARGIN));
  left = Math.max(VIEWPORT_MARGIN, Math.min(left, vw - tooltipWidth - VIEWPORT_MARGIN));

  return { top, left, arrowPosition };
}


function CalendarTour({
  isActive,
  currentStep,
  steps,
  totalSteps,
  dontShowAgain,
  onNext,
  onBack,
  onSkip,
  onComplete,
  onToggleDontShowAgain,
}) {
  const [spotlightStyle, setSpotlightStyle] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({ top: 0, left: 0 });
  const [arrowPosition, setArrowPosition] = useState('top');
  const [phase, setPhase] = useState('entering'); // entering | active | exiting
  const tooltipRef = useRef(null);
  const stepData = steps[currentStep];

  // Transition phase on mount / unmount
  useEffect(() => {
    if (isActive) {
      setPhase('entering');
      const timer = setTimeout(() => setPhase('active'), 50);
      return () => clearTimeout(timer);
    } else {
      setPhase('exiting');
    }
  }, [isActive]);

  // Reposition spotlight + tooltip whenever currentStep changes
  const reposition = useCallback(() => {
    if (!stepData) return;

    const result = getTargetRect(stepData.target);
    if (!result) {
      // Element not found: use a centered fallback
      const fallbackRect = {
        top: window.innerHeight / 2 - 40,
        left: window.innerWidth / 2 - 100,
        width: 200,
        height: 80,
        bottom: window.innerHeight / 2 + 40,
        right: window.innerWidth / 2 + 100,
      };
      setSpotlightStyle({
        top: fallbackRect.top - SPOTLIGHT_PADDING,
        left: fallbackRect.left - SPOTLIGHT_PADDING,
        width: fallbackRect.width + SPOTLIGHT_PADDING * 2,
        height: fallbackRect.height + SPOTLIGHT_PADDING * 2,
      });

      const tooltipWidth = 340;
      const tooltipHeight = 240;
      const pos = calcTooltipPosition(fallbackRect, tooltipWidth, tooltipHeight, stepData.placement);
      setTooltipPos({ top: pos.top, left: pos.left });
      setArrowPosition(pos.arrowPosition);
      return;
    }

    const { el, rect } = result;

    // Scroll into view first
    scrollToTarget(el);

    // Use a short delay after scroll so getBoundingClientRect is updated
    requestAnimationFrame(() => {
      const freshRect = el.getBoundingClientRect();

      setSpotlightStyle({
        top: freshRect.top - SPOTLIGHT_PADDING,
        left: freshRect.left - SPOTLIGHT_PADDING,
        width: freshRect.width + SPOTLIGHT_PADDING * 2,
        height: freshRect.height + SPOTLIGHT_PADDING * 2,
      });

      // Measure tooltip if possible
      const tooltipEl = tooltipRef.current;
      const tooltipWidth = tooltipEl ? tooltipEl.offsetWidth : 340;
      const tooltipHeight = tooltipEl ? tooltipEl.offsetHeight : 240;

      const pos = calcTooltipPosition(freshRect, tooltipWidth, tooltipHeight, stepData.placement);
      setTooltipPos({ top: pos.top, left: pos.left });
      setArrowPosition(pos.arrowPosition);
    });
  }, [stepData]);

  // Reposition on step change and window resize
  useEffect(() => {
    if (!isActive) return;
    reposition();

    const handleResize = () => reposition();
    window.addEventListener('resize', handleResize);
    window.addEventListener('scroll', handleResize, true);
    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('scroll', handleResize, true);
    };
  }, [isActive, currentStep, reposition]);

  // Keyboard handling: Escape to skip, Left/Right to navigate, Tab trap
  useEffect(() => {
    if (!isActive) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onSkip();
      } else if (e.key === 'ArrowRight') {
        if (stepData?.isFinal) {
          onComplete();
        } else {
          onNext();
        }
      } else if (e.key === 'ArrowLeft') {
        if (currentStep > 0) onBack();
      } else if (e.key === 'Tab' && tooltipRef.current) {
        // Focus trap within the tooltip
        const focusable = tooltipRef.current.querySelectorAll(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isActive, currentStep, stepData, onNext, onBack, onSkip, onComplete]);

  if (!isActive || !stepData) return null;

  const isFirstStep = currentStep === 0;
  const isLastStep = stepData.isFinal;

  const overlay = (
    <div className={`calendar-tour-overlay calendar-tour-overlay--${phase}`} onClick={onSkip}>
      {/* Spotlight cutout */}
      {spotlightStyle && (
        <>
          <div
            className="calendar-tour-spotlight"
            style={{
              top: spotlightStyle.top,
              left: spotlightStyle.left,
              width: spotlightStyle.width,
              height: spotlightStyle.height,
            }}
          />
          {/* Transparent clickthrough layer over the spotlighted element */}
          <div
            className="calendar-tour-spotlight-clickthrough"
            style={{
              top: spotlightStyle.top,
              left: spotlightStyle.left,
              width: spotlightStyle.width,
              height: spotlightStyle.height,
            }}
            onClick={(e) => e.stopPropagation()}
          />
        </>
      )}

      {/* Tooltip */}
      <div
        ref={tooltipRef}
        className={`calendar-tour-tooltip${spotlightStyle ? '' : ' calendar-tour-tooltip--hidden'}`}
        style={{ top: tooltipPos.top, left: tooltipPos.left }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Tour step ${currentStep + 1} of ${totalSteps}: ${stepData.title}`}
      >
        {/* Accent bar */}
        <div className="calendar-tour-tooltip__accent" />

        {/* Arrow */}
        <div className={`calendar-tour-arrow calendar-tour-arrow--${arrowPosition}`} />

        {/* Body */}
        <div className="calendar-tour-tooltip__body">
          <span className="calendar-tour-tooltip__step">
            Step {currentStep + 1} of {totalSteps}
          </span>
          <h3 className="calendar-tour-tooltip__title">{stepData.title}</h3>

          {isLastStep ? (
            <div className="calendar-tour-celebration">
              <div className="calendar-tour-celebration__icon" aria-hidden="true">
                &#10024;
              </div>
              <p className="calendar-tour-tooltip__description">
                You now know the essentials. Here are a few more tips:
              </p>
              <ul className="calendar-tour-tips">
                <li>Right-click any time slot for quick actions</li>
                <li>Press "?" for keyboard shortcuts</li>
                <li>Drag appointments to reschedule them</li>
                <li>Use labels to color-code your events</li>
                <li>Visit Settings to customize your booking page</li>
              </ul>
            </div>
          ) : (
            <p className="calendar-tour-tooltip__description">{stepData.description}</p>
          )}
        </div>

        {/* "Don't show again" checkbox — only on final step */}
        {isLastStep && (
          <label className="calendar-tour-dontshow">
            <input
              type="checkbox"
              checked={dontShowAgain}
              onChange={(e) => onToggleDontShowAgain(e.target.checked)}
            />
            <span className="calendar-tour-dontshow__label">Don't show this tour again</span>
          </label>
        )}

        {/* Footer */}
        <div className="calendar-tour-tooltip__footer">
          {/* Progress dots */}
          <div className="calendar-tour-progress" role="presentation" aria-hidden="true">
            {steps.map((_, idx) => (
              <div
                key={idx}
                className={`calendar-tour-progress__dot${
                  idx === currentStep
                    ? ' calendar-tour-progress__dot--active'
                    : idx < currentStep
                    ? ' calendar-tour-progress__dot--completed'
                    : ''
                }`}
              />
            ))}
          </div>

          {/* Navigation */}
          <div className="calendar-tour-tooltip__nav">
            {!isLastStep && (
              <button
                className="calendar-tour-btn calendar-tour-btn--skip"
                onClick={onSkip}
                type="button"
              >
                Skip
              </button>
            )}

            {!isFirstStep && (
              <button
                className="calendar-tour-btn calendar-tour-btn--back"
                onClick={onBack}
                type="button"
              >
                Back
              </button>
            )}

            {isLastStep ? (
              <button
                className="calendar-tour-btn calendar-tour-btn--finish"
                onClick={onComplete}
                type="button"
                autoFocus
              >
                Got It
              </button>
            ) : (
              <button
                className="calendar-tour-btn calendar-tour-btn--next"
                onClick={onNext}
                type="button"
                autoFocus
              >
                Next
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  return createPortal(overlay, document.body);
}

/**
 * TourTriggerButton - Small "?" button to launch/relaunch the tour
 */
export function TourTriggerButton({ onClick }) {
  return (
    <button
      className="calendar-tour-trigger"
      onClick={onClick}
      type="button"
      title="Take a tour of the calendar"
      aria-label="Take a tour of the calendar"
    >
      ?
    </button>
  );
}

export default CalendarTour;
