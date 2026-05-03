/**
 * StepRail — the vertical step list on the left of the POS.
 *
 * Each step shows its number, label, and a completion check. The active
 * step is highlighted; completed steps are clickable to navigate back; the
 * next pending step is clickable to proceed; further-future steps are
 * disabled.
 */
import React from 'react';

import type { SectionKey } from '../types';
import { SECTION_CAPTIONS } from '../types';

export interface StepRailProps {
  steps: SectionKey[];
  labels: Record<SectionKey, string>;
  activeStep: SectionKey;
  completionByStep: Partial<Record<SectionKey, boolean>>;
  onStepClick: (step: SectionKey) => void;
}

export const StepRail: React.FC<StepRailProps> = ({
  steps,
  labels,
  activeStep,
  completionByStep,
  onStepClick,
}) => {
  const activeIdx = steps.indexOf(activeStep);

  return (
    <ol className="pos-step-rail" role="list">
      {steps.map((key, idx) => {
        const isComplete = completionByStep[key] === true;
        const isActive = key === activeStep;
        // Clickable if completed, active, or the immediate next step.
        const canNavigate = isComplete || isActive || idx <= activeIdx + 1;

        const stateClass = isActive
          ? 'is-active'
          : isComplete
            ? 'is-complete'
            : idx <= activeIdx
              ? 'is-available'
              : 'is-pending';

        return (
          <li
            key={key}
            className={`pos-step-rail__item pos-step-rail__item--${stateClass}`}
          >
            <button
              type="button"
              className="pos-step-rail__btn"
              onClick={() => canNavigate && onStepClick(key)}
              disabled={!canNavigate}
              aria-current={isActive ? 'step' : undefined}
            >
              <span className="pos-step-rail__index">
                {isComplete ? <CheckIcon /> : idx + 1}
              </span>
              <span className="pos-step-rail__label-wrap">
                <span className="pos-step-rail__label">{labels[key]}</span>
                {SECTION_CAPTIONS[key] && (
                  <span className="pos-step-rail__caption">{SECTION_CAPTIONS[key]}</span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
};

const CheckIcon: React.FC = () => (
  <svg
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
  >
    <polyline points="20 6 9 17 4 12" />
  </svg>
);
