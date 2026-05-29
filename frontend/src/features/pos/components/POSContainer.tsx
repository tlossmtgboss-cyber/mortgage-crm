import React, { useCallback, useEffect, useRef, useState } from 'react';

import { usePOSApplication } from '../hooks/usePOSApplication';
import { useDocumentDetector } from '../hooks/useDocumentDetector';
import { posApi } from '../api';
import type { SectionKey } from '../types';
import { SECTION_ORDER, SECTION_LABELS, SECTION_CAPTIONS } from '../types';
import { validateSection } from '../schemas/urla';
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
  const [view, setView] = useState<PosNavKey>('application');
  const [taskCount, setTaskCount] = useState(0);
  const [messageCount, setMessageCount] = useState(0);
  const [validationErrors, setValidationErrors] = useState<{ path: string; message: string }[]>([]);

  const appId = application?.id;
  const initialViewSet = useRef(false);
  React.useEffect(() => {
    if (application && !initialViewSet.current) {
      initialViewSet.current = true;
      if (application.status === 'submitted') {
        setView('home');
      }
    }
  }, [application]);
  React.useEffect(() => {
    if (appId) {
      posApi.getTasks(appId).then(resp => setTaskCount(resp.counts.pending + resp.counts.in_progress)).catch((err) => { console.error('Failed to load task counts:', err); });
      posApi.getMessages(appId).then(resp => setMessageCount(resp.counts.unread)).catch((err) => { console.error('Failed to load message counts:', err); });
    }
  }, [appId]);
  const [intakeComplete, setIntakeComplete] = useState(false);
  const [intakeData, setIntakeData] = useState<IntakeData>(EMPTY_INTAKE);

  const detectedDocs = useDocumentDetector(sections, intakeData);

  // M8: Focus management on step/view transitions for screen readers
  useEffect(() => {
    const timer = setTimeout(() => {
      const heading = (document.querySelector('.pos-main__step-title') || document.querySelector('.pos-main__heading')) as HTMLElement | null;
      if (heading) {
        if (!heading.hasAttribute('tabindex')) {
          heading.setAttribute('tabindex', '-1');
        }
        heading.focus();
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [activeStep, view]);

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
      setValidationErrors([]);
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

  // Derive session-error state from the error string. Must be computed before
  // any early return so the useEffect below always runs (Rules of Hooks).
  const isSessionError = !!(error && (
    error.includes('401') || error.includes('403') || error.includes('400') ||
    error.includes('404') || error.includes('Not Found') || error.includes('Unauthorized')
  ));

  // Bounce back to the auth gate when the PURL token is rejected.
  // This hook MUST live before conditional returns to satisfy Rules of Hooks.
  useEffect(() => {
    if (isSessionError && onAuthError) {
      onAuthError();
    }
  }, [isSessionError, onAuthError]);

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

  if (isSessionError && onAuthError) return null;

  if (error || !application) {
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

                  <PanelErrorBoundary sectionKey={activeStep}>
                    {validationErrors.length > 0 && (
                      <div className="pos-validation-errors" role="alert" style={{
                        background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8,
                        padding: '12px 16px', marginBottom: 16,
                      }}>
                        <p style={{ fontWeight: 600, color: '#991b1b', margin: '0 0 8px', fontSize: 14 }}>
                          Please fix the following before continuing:
                        </p>
                        <ul style={{ margin: 0, paddingLeft: 20, color: '#b91c1c', fontSize: 13, lineHeight: 1.6 }}>
                          {validationErrors.map((err, i) => (
                            <li key={i}>{err.path ? `${err.path}: ` : ''}{err.message}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <ActivePanel
                      section={sections[activeStep]}
                      onChange={(data: Record<string, unknown>) => {
                        setValidationErrors([]);
                        updateSectionData(activeStep, data);
                      }}
                      onComplete={() => {
                        // Sections with passthrough schemas skip validation.
                        const SKIP_VALIDATION: SectionKey[] = ['documents_upload', 'schedule', 'review'];
                        if (!SKIP_VALIDATION.includes(activeStep)) {
                          const sectionData = sections[activeStep]?.data || {};
                          const result = validateSection(activeStep, sectionData);
                          if (!result.ok) {
                            setValidationErrors('issues' in result ? result.issues : []);
                            return;
                          }
                        }
                        setValidationErrors([]);
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
                  </PanelErrorBoundary>
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

      {/* H7: Mobile bottom navigation (visible at <=1024px when sidebar hides) */}
      <MobileBottomNav activeNav={view} onNavigate={setView} />
    </div>
  );
};

/* H7: Mobile bottom navigation bar — appears at <=1024px when sidebar is hidden */
const MobileBottomNav: React.FC<{
  activeNav: PosNavKey;
  onNavigate: (key: PosNavKey) => void;
}> = ({ activeNav, onNavigate }) => (
  <nav className="pos-mobile-nav" aria-label="Mobile navigation">
    <button
      type="button"
      className={`pos-mobile-nav__btn${activeNav === 'home' ? ' pos-mobile-nav__btn--active' : ''}`}
      onClick={() => onNavigate('home')}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        <polyline points="9 22 9 12 15 12 15 22" />
      </svg>
      <span>Home</span>
    </button>
    <button
      type="button"
      className={`pos-mobile-nav__btn${activeNav === 'documents' ? ' pos-mobile-nav__btn--active' : ''}`}
      onClick={() => onNavigate('documents')}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </svg>
      <span>Docs</span>
    </button>
    <button
      type="button"
      className={`pos-mobile-nav__btn${activeNav === 'tasks' ? ' pos-mobile-nav__btn--active' : ''}`}
      onClick={() => onNavigate('tasks')}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M9 11l3 3L22 4" />
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </svg>
      <span>Tasks</span>
    </button>
    <button
      type="button"
      className={`pos-mobile-nav__btn${activeNav === 'messages' ? ' pos-mobile-nav__btn--active' : ''}`}
      onClick={() => onNavigate('messages')}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
      <span>Messages</span>
    </button>
    <button
      type="button"
      className={`pos-mobile-nav__btn${activeNav === 'team' ? ' pos-mobile-nav__btn--active' : ''}`}
      onClick={() => onNavigate('team')}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
      <span>Team</span>
    </button>
  </nav>
);

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

class PanelErrorBoundary extends React.Component<
  { sectionKey: string; children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { sectionKey: string; children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(`POS panel error in section "${this.props.sectionKey}":`, error, info.componentStack);
  }

  componentDidUpdate(prevProps: { sectionKey: string }) {
    if (prevProps.sectionKey !== this.props.sectionKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '48px 24px', textAlign: 'center' }}>
          <h3 style={{ fontFamily: 'var(--bt-font-display)', fontSize: 20, fontWeight: 600, color: 'var(--bt-text-primary)', marginBottom: 8 }}>
            Something went wrong.
          </h3>
          <p style={{ fontSize: 15, color: 'var(--bt-text-secondary)', marginBottom: 20 }}>
            Your data has been saved. Please try again.
          </p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false })}
            style={{
              fontFamily: 'var(--bt-font-body)', fontSize: 14, fontWeight: 600,
              color: '#fff', background: 'var(--bt-primary)',
              border: 'none', borderRadius: 8, padding: '10px 24px', cursor: 'pointer',
            }}
          >
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
