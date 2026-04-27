/**
 * POSContainer — top-level orchestrator for the borrower POS experience.
 *
 * Renders the step rail on the left, the active section panel in the
 * middle, and the Aria panel as a slide-over from the right. Smart Calendar
 * is mounted by the Review panel only.
 *
 * Designed to drop into Perennia's existing `PortalContainer` shell — it
 * does not own its own header or chrome. Pass `loanId` if the borrower has
 * an existing loan file, otherwise the application starts as a prequal.
 */
import React, { useCallback, useState } from 'react';

import { usePOSApplication } from '../hooks/usePOSApplication';
import type { SectionKey } from '../types';
import { SECTION_ORDER, SECTION_LABELS } from '../types';
import { StepRail } from './StepRail';
import { AskAriaButton } from './AskAriaButton';
import { AriaPanel } from './AriaPanel';

import { PersonalPanel } from './panels/PersonalPanel';
import { ResidencePanel } from './panels/ResidencePanel';
import { EmploymentPanel } from './panels/EmploymentPanel';
import { AssetsPanel } from './panels/AssetsPanel';
import { LiabilitiesPanel } from './panels/LiabilitiesPanel';
import { REOPanel } from './panels/REOPanel';
import { LoanPanel } from './panels/LoanPanel';
import { DeclarationsPanel } from './panels/DeclarationsPanel';
import { ReviewPanel } from './panels/ReviewPanel';

export interface POSContainerProps {
  loanId?: number;
}

const PANEL_COMPONENTS: Record<SectionKey, React.ComponentType<any>> = {
  personal: PersonalPanel,
  residence: ResidencePanel,
  employment: EmploymentPanel,
  assets: AssetsPanel,
  liabilities: LiabilitiesPanel,
  reo: REOPanel,
  loan: LoanPanel,
  declarations: DeclarationsPanel,
  review: ReviewPanel,
};

export const POSContainer: React.FC<POSContainerProps> = ({ loanId }) => {
  const {
    application,
    sections,
    loading,
    error,
    saveState,
    loadSection,
    updateSectionData,
    markComplete,
    submit,
  } = usePOSApplication(loanId);

  const [activeStep, setActiveStep] = useState<SectionKey>('personal');
  const [ariaOpen, setAriaOpen] = useState(false);

  // Sync active step with backend's current_step on initial load.
  React.useEffect(() => {
    if (application && !sections.personal) {
      setActiveStep(application.current_step);
      // Pre-load the current step's data.
      loadSection(application.current_step);
    }
  }, [application, sections.personal, loadSection]);

  const handleStepChange = useCallback(
    (key: SectionKey) => {
      setActiveStep(key);
      if (!sections[key]) loadSection(key);
    },
    [sections, loadSection],
  );

  if (loading) {
    return (
      <div className="pos-loading">
        <div className="pos-loading__spinner" />
        <p>Loading your application…</p>
      </div>
    );
  }

  if (error || !application) {
    return (
      <div className="pos-error">
        <h2>We couldn't load your application</h2>
        <p>{error}</p>
        <button onClick={() => window.location.reload()}>Try again</button>
      </div>
    );
  }

  const ActivePanel = PANEL_COMPONENTS[activeStep];

  return (
    <div className="pos-container">
      <aside className="pos-sidebar">
        <StepRail
          steps={SECTION_ORDER}
          labels={SECTION_LABELS}
          activeStep={activeStep}
          completionByStep={application.sections_complete}
          onStepClick={handleStepChange}
        />

        <div className="pos-sidebar__progress">
          <div className="pos-sidebar__progress-label">
            <span>Application</span>
            <span>{application.completion_pct}%</span>
          </div>
          <div className="pos-sidebar__progress-track">
            <div
              className="pos-sidebar__progress-fill"
              style={{ width: `${application.completion_pct}%` }}
            />
          </div>
        </div>

        <AskAriaButton onClick={() => setAriaOpen(true)} />
      </aside>

      <main className="pos-main">
        <div className="pos-main__header">
          <div>
            <p className="pos-main__step-counter">
              Step {SECTION_ORDER.indexOf(activeStep) + 1} of {SECTION_ORDER.length}
            </p>
            <h1 className="pos-main__step-title">{SECTION_LABELS[activeStep]}</h1>
          </div>
          <SaveIndicator state={saveState} />
        </div>

        <div className="pos-main__panel">
          <ActivePanel
            section={sections[activeStep]}
            onChange={(data: Record<string, unknown>) =>
              updateSectionData(activeStep, data)
            }
            onComplete={() => {
              markComplete(activeStep).then(() => {
                const nextIdx = Math.min(
                  SECTION_ORDER.indexOf(activeStep) + 1,
                  SECTION_ORDER.length - 1,
                );
                handleStepChange(SECTION_ORDER[nextIdx]);
              });
            }}
            // Review panel needs extra props.
            application={application}
            onSubmit={submit}
            onAskAria={() => setAriaOpen(true)}
          />
        </div>
      </main>

      <AriaPanel
        open={ariaOpen}
        onClose={() => setAriaOpen(false)}
        applicationId={application.id}
        currentStep={activeStep}
      />
    </div>
  );
};

const SaveIndicator: React.FC<{ state: 'idle' | 'saving' | 'saved' | 'error' }> = ({
  state,
}) => {
  if (state === 'idle') return null;
  const message = {
    saving: 'Saving…',
    saved: 'All changes saved',
    error: 'Save failed — check your connection',
  }[state];
  return <span className={`pos-save-indicator pos-save-indicator--${state}`}>{message}</span>;
};
