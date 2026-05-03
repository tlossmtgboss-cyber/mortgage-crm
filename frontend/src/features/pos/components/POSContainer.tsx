import React, { useCallback, useState } from 'react';

import { usePOSApplication } from '../hooks/usePOSApplication';
import type { SectionKey } from '../types';
import { SECTION_ORDER, SECTION_LABELS } from '../types';
import { TopNav } from './TopNav';
import { POSSidebar } from './POSSidebar';
import { StepRail } from './StepRail';
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

import '../../../styles/borrower-theme.css';
import '../pos.css';

export interface POSContainerProps {
  loanId?: number;
  borrowerName?: string;
  userInitials?: string;
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

export const POSContainer: React.FC<POSContainerProps> = ({
  loanId,
  borrowerName = 'there',
  userInitials = '',
}) => {
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

  React.useEffect(() => {
    if (application && !sections.personal) {
      setActiveStep(application.current_step);
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
      <div className="pos-page">
        <div className="pos-loading">
          <div className="pos-loading__spinner" />
          <p>Loading your application…</p>
        </div>
      </div>
    );
  }

  if (error || !application) {
    return (
      <div className="pos-page">
        <div className="pos-error">
          <h2>We couldn't load your application</h2>
          <p>{error}</p>
          <button onClick={() => window.location.reload()}>Try again</button>
        </div>
      </div>
    );
  }

  const ActivePanel = PANEL_COMPONENTS[activeStep];

  return (
    <div className="pos-page">
      <TopNav saveState={saveState} userInitials={userInitials || borrowerName.charAt(0).toUpperCase()} />

      <div className="pos-body">
        <POSSidebar application={application} onAskAria={() => setAriaOpen(true)} />

        <main className="pos-main">
          <div className="pos-main__header">
            <div>
              <p className="pos-main__step-counter">
                Step {SECTION_ORDER.indexOf(activeStep) + 1} of {SECTION_ORDER.length}
              </p>
              <h1 className="pos-main__step-title">{SECTION_LABELS[activeStep]}</h1>
            </div>
          </div>

          <div className="pos-main__steps">
            <StepRail
              steps={SECTION_ORDER}
              labels={SECTION_LABELS}
              activeStep={activeStep}
              completionByStep={application.sections_complete}
              onStepClick={handleStepChange}
            />
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
              application={application}
              onSubmit={submit}
              onAskAria={() => setAriaOpen(true)}
            />
          </div>
        </main>
      </div>

      <AriaPanel
        open={ariaOpen}
        onClose={() => setAriaOpen(false)}
        applicationId={application.id}
        currentStep={activeStep}
      />
    </div>
  );
};
