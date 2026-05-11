import React, { useCallback, useRef, useState } from 'react';

import { usePOSApplication } from '../hooks/usePOSApplication';
import { useDocumentDetector } from '../hooks/useDocumentDetector';
import { posApi } from '../api';
import type { SectionKey } from '../types';
import { SECTION_ORDER, SECTION_LABELS, SECTION_CAPTIONS } from '../types';
import { TopNav } from './TopNav';
import { POSSidebar } from './POSSidebar';
import type { PosNavKey } from './POSSidebar';
import { StepRail } from './StepRail';
import { AriaPanel } from './AriaPanel';
import { DocumentsPage } from './DocumentsPage';
import { MessagesPage } from './MessagesPage';
import { TasksPage } from './TasksPage';
import { TeamContactPanel } from './TeamContactPanel';
import { HomePage } from './HomePage';
import { IntakePanel, EMPTY_INTAKE } from './IntakePanel';
import type { IntakeData } from './IntakePanel';

import { PersonalPanel } from './panels/PersonalPanel';
import { CoBorrowerPanel } from './panels/CoBorrowerPanel';
import { ResidencePanel } from './panels/ResidencePanel';
import { EmploymentPanel } from './panels/EmploymentPanel';
import { AssetsPanel } from './panels/AssetsPanel';
import { LiabilitiesPanel } from './panels/LiabilitiesPanel';
import { REOPanel } from './panels/REOPanel';
import { LoanPanel } from './panels/LoanPanel';
import { DocumentsUploadPanel } from './panels/DocumentsUploadPanel';
import { DeclarationsPanel } from './panels/DeclarationsPanel';
import { CreditAuthPanel } from './panels/CreditAuthPanel';
import { SchedulePanel } from './panels/SchedulePanel';
import { ReviewPanel } from './panels/ReviewPanel';

import '../../../styles/borrower-theme.css';
import '../pos.css';

export interface POSContainerProps {
  loanId?: number;
  borrowerName?: string;
  userInitials?: string;
  onAuthError?: () => void;
}

const PANEL_COMPONENTS: Record<SectionKey, React.ComponentType<any>> = {
  personal: PersonalPanel,
  coborrower: CoBorrowerPanel,
  residence: ResidencePanel,
  employment: EmploymentPanel,
  assets: AssetsPanel,
  liabilities: LiabilitiesPanel,
  reo: REOPanel,
  loan: LoanPanel,
  documents_upload: DocumentsUploadPanel,
  declarations: DeclarationsPanel,
  credit_auth: CreditAuthPanel,
  schedule: SchedulePanel,
  review: ReviewPanel,
};

export const POSContainer: React.FC<POSContainerProps> = ({
  loanId,
  borrowerName = 'there',
  userInitials = '',
  onAuthError,
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
  const [view, setView] = useState<PosNavKey>('home');
  const [taskCount, setTaskCount] = useState(0);
  const [messageCount, setMessageCount] = useState(0);

  const appId = application?.id;
  React.useEffect(() => {
    if (appId) {
      posApi.getTasks(appId).then(resp => setTaskCount(resp.counts.pending + resp.counts.in_progress)).catch(() => {});
      posApi.getMessages(appId).then(resp => setMessageCount(resp.counts.unread)).catch(() => {});
    }
  }, [appId]);
  const [intakeComplete, setIntakeComplete] = useState(false);
  const [intakeData, setIntakeData] = useState<IntakeData>(EMPTY_INTAKE);

  const detectedDocs = useDocumentDetector(sections, intakeData);

  React.useEffect(() => {
    if (application && !sections.personal) {
      setActiveStep(application.current_step);
      loadSection(application.current_step);
      loadSection('intake' as SectionKey).then(sec => {
        if (sec?.data && sec.data.is_veteran != null && sec.data.loan_purpose != null) {
          setIntakeData(sec.data as unknown as IntakeData);
          setIntakeComplete(true);
        } else if (sec?.data) {
          setIntakeData(prev => ({ ...prev, ...(sec.data as any) }));
        }
      });
    }
  }, [application, sections.personal, loadSection]);

  const reviewPreloaded = useRef(false);
  React.useEffect(() => {
    if (activeStep === 'review' && application && !reviewPreloaded.current) {
      reviewPreloaded.current = true;
      SECTION_ORDER.filter(k => k !== 'review').forEach(k => loadSection(k));
    }
    if (activeStep !== 'review') reviewPreloaded.current = false;
  }, [activeStep, application, loadSection]);

  const handleStepChange = useCallback(
    (key: SectionKey, fieldToHighlight?: string) => {
      setActiveStep(key);
      if (!sections[key]) loadSection(key);
      if (fieldToHighlight) {
        setTimeout(() => {
          const el = document.getElementById(`f-${fieldToHighlight}`);
          if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            el.classList.add('urla-field--highlight');
            el.focus();
            setTimeout(() => el.classList.remove('urla-field--highlight'), 3000);
          }
        }, 300);
      }
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
    const isSessionError = error && (
      error.includes('401') || error.includes('403') || error.includes('400') ||
      error.includes('404') || error.includes('Not Found') || error.includes('Unauthorized')
    );
    if (isSessionError && onAuthError) {
      onAuthError();
      return null;
    }
    return (
      <div className="pos-page">
        <div className="pos-error">
          <h2>We couldn't load your application</h2>
          <p>{error}</p>
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', marginTop: '16px' }}>
            <button onClick={() => window.location.reload()}>Try again</button>
            {onAuthError && (
              <button onClick={onAuthError} style={{ background: 'transparent', border: '1px solid #d4d9d6', color: '#6B7B75' }}>
                Start over
              </button>
            )}
          </div>
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
          taskCount={taskCount}
          messageCount={messageCount}
          onNavigate={setView}
          activeNav={view}
        />

        <main className="pos-main">
          {view === 'home' ? (
            <HomePage
              application={application}
              onAskAria={() => setAriaOpen(true)}
              onNavigate={(v) => setView(v as PosNavKey)}
            />
          ) : view === 'team' ? (
            <TeamContactPanel
              applicationId={application.id}
              onBack={() => setView('home')}
            />
          ) : view === 'documents' ? (
            <DocumentsPage
              loanId={application?.loan_id}
              detectedDocs={detectedDocs}
              onAskAria={() => setAriaOpen(true)}
              onBack={() => setView('home')}
            />
          ) : view === 'tasks' ? (
            <TasksPage
              applicationId={application.id}
              onAskAria={() => setAriaOpen(true)}
              onBack={() => setView('home')}
            />
          ) : view === 'messages' ? (
            <MessagesPage
              applicationId={application.id}
              onAskAria={() => setAriaOpen(true)}
              onBack={() => setView('home')}
            />
          ) : view === 'disclosures' ? (
            <PlaceholderPage title="Disclosures" description="Your disclosure documents will appear here once they're ready for review." onBack={() => setView('home')} />
          ) : view === 'calculators' ? (
            <PlaceholderPage title="Calculators" description="Mortgage calculators to help you estimate payments, compare rates, and plan your budget." onBack={() => setView('home')} />
          ) : view === 'timeline' ? (
            <PlaceholderPage title="Loan Timeline" description="Track the progress of your loan from application to closing." onBack={() => setView('home')} />
          ) : view === 'help' ? (
            <PlaceholderPage title="Help & Support" description="Have questions? Reach out to your loan team or ask Aria for instant answers." onBack={() => setView('home')} onAskAria={() => setAriaOpen(true)} />
          ) : (
            <>
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
                    intakeLoanPurpose={intakeData.loan_purpose}
                    allSections={sections}
                    onNavigate={handleStepChange}
                  />
                </div>
              </div>
            </>
          )}
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

const PlaceholderPage: React.FC<{
  title: string;
  description: string;
  onBack: () => void;
  onAskAria?: () => void;
}> = ({ title, description, onBack, onAskAria }) => (
  <div style={{ maxWidth: 640, margin: '0 auto', padding: '48px 0', textAlign: 'center' }}>
    <h2 style={{ fontFamily: 'var(--bt-font-display)', fontSize: 24, fontWeight: 600, color: 'var(--bt-text-primary)', marginBottom: 12 }}>
      {title}
    </h2>
    <p style={{ fontSize: 15, color: 'var(--bt-text-secondary)', marginBottom: 24, lineHeight: 1.6 }}>
      {description}
    </p>
    <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
      <button
        type="button"
        onClick={onBack}
        style={{
          fontFamily: 'var(--bt-font-body)', fontSize: 14, fontWeight: 600,
          color: 'var(--bt-text-secondary)', background: 'var(--bt-bg-elevated)',
          border: '1px solid var(--bt-border)', borderRadius: 8, padding: '10px 20px', cursor: 'pointer',
        }}
      >
        ← Back to Home
      </button>
      {onAskAria && (
        <button
          type="button"
          onClick={onAskAria}
          style={{
            fontFamily: 'var(--bt-font-body)', fontSize: 14, fontWeight: 600,
            color: '#fff', background: 'var(--bt-primary)',
            border: 'none', borderRadius: 8, padding: '10px 20px', cursor: 'pointer',
          }}
        >
          Ask Aria
        </button>
      )}
    </div>
  </div>
);
