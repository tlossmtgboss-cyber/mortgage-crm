import React, { useCallback, useState } from 'react';

import { usePOSApplication } from '../hooks/usePOSApplication';
import { useDocumentDetector } from '../hooks/useDocumentDetector';
import { posApi } from '../api';
import type { SectionKey } from '../types';
import { SECTION_ORDER, SECTION_LABELS, SECTION_CAPTIONS } from '../types';
import { TopNav } from './TopNav';
import { POSSidebar } from './POSSidebar';
import { StepRail } from './StepRail';
import { AriaPanel } from './AriaPanel';
import { DocumentsDrawer } from './DocumentsDrawer';
import { IntakePanel, EMPTY_INTAKE } from './IntakePanel';
import type { IntakeData } from './IntakePanel';

import { PersonalPanel } from './panels/PersonalPanel';
import { ResidencePanel } from './panels/ResidencePanel';
import { EmploymentPanel } from './panels/EmploymentPanel';
import { AssetsPanel } from './panels/AssetsPanel';
import { LiabilitiesPanel } from './panels/LiabilitiesPanel';
import { REOPanel } from './panels/REOPanel';
import { LoanPanel } from './panels/LoanPanel';
import { DeclarationsPanel } from './panels/DeclarationsPanel';
import { SchedulePanel } from './panels/SchedulePanel';
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
  schedule: SchedulePanel,
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
  const [docsOpen, setDocsOpen] = useState(false);
  const [intakeComplete, setIntakeComplete] = useState(false);
  const [intakeData, setIntakeData] = useState<IntakeData>(EMPTY_INTAKE);

  const detectedDocs = useDocumentDetector(sections, intakeData);

  React.useEffect(() => {
    if (application && !sections.personal) {
      setActiveStep(application.current_step);
      loadSection(application.current_step);
      // Load intake section to check if already completed.
      loadSection('intake' as SectionKey).then(sec => {
        if (sec?.data && sec.data.is_veteran != null) {
          setIntakeData(sec.data as unknown as IntakeData);
          setIntakeComplete(true);
        }
      });
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

  const handleIntakeComplete = async (data: IntakeData) => {
    setIntakeData(data);
    setIntakeComplete(true);
    if (application) {
      await posApi.updateSection(application.id, 'intake' as SectionKey, {
        data: data as unknown as Record<string, unknown>,
        mark_complete: true,
      });
    }
  };

  const ActivePanel = PANEL_COMPONENTS[activeStep];

  if (!intakeComplete) {
    return (
      <div className="pos-page">
        <TopNav saveState={saveState} userInitials={userInitials || borrowerName.charAt(0).toUpperCase()} />
        <div className="pos-body">
          <main className="pos-main" style={{ maxWidth: 640, margin: '0 auto' }}>
            <IntakePanel initial={intakeData} onComplete={handleIntakeComplete} />
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="pos-page">
      <TopNav saveState={saveState} userInitials={userInitials || borrowerName.charAt(0).toUpperCase()} />

      <div className="pos-body">
        <POSSidebar
          application={application}
          onAskAria={() => setAriaOpen(true)}
          documentCount={detectedDocs.length}
          onDocumentsClick={() => setDocsOpen(true)}
        />

        <main className="pos-main">
          <div className="pos-main__welcome">
            <div className="pos-main__urla-badge">
              <span className="pos-main__urla-tag">URLA · Form 1003</span>
              <span className="pos-main__time-estimate">Estimated time remaining: ~14 minutes</span>
            </div>
            <h1 className="pos-main__heading">Welcome back, {borrowerName}.</h1>
            <p className="pos-main__subheading">
              Let's finish your loan application. Your progress saves automatically — step away
              anytime and pick up right where you left off.
            </p>
          </div>

          <div className="pos-main__grid">
            <StepRail
              steps={SECTION_ORDER}
              labels={SECTION_LABELS}
              activeStep={activeStep}
              completionByStep={application.sections_complete}
              onStepClick={handleStepChange}
            />

            <div className="pos-main__panel">
              <div className="pos-main__step-header">
                <p className="pos-main__step-counter">
                  Step {SECTION_ORDER.indexOf(activeStep) + 1} of {SECTION_ORDER.length}
                </p>
                <h2 className="pos-main__step-title">{SECTION_LABELS[activeStep]}</h2>
              </div>

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
          </div>
        </main>
      </div>

      <AriaPanel
        open={ariaOpen}
        onClose={() => setAriaOpen(false)}
        applicationId={application.id}
        currentStep={activeStep}
      />

      <DocumentsDrawer
        open={docsOpen}
        onClose={() => setDocsOpen(false)}
        documents={detectedDocs}
      />
    </div>
  );
};
