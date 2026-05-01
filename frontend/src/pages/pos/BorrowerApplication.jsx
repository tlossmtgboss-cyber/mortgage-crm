/**
 * BorrowerApplication — Main container for the Digital 1003 borrower POS flow.
 *
 * Wraps the existing POSContainer feature component with:
 *   - Material UI theming and responsive layout
 *   - Step progress bar at the top (mobile-first)
 *   - Route parameter handling for loan_id
 *   - Auto-save status indicator
 *
 * This is the page-level entry point. The real form logic lives in:
 *   - frontend/src/features/pos/components/POSContainer.tsx
 *   - frontend/src/features/pos/hooks/usePOSApplication.ts
 *
 * Routes:
 *   /apply                         — new prequal application
 *   /apply/:loanId                 — resume application for specific loan
 *   /portal/application            — portal-embedded version
 *   /portal/loans/:loanId/application
 */
import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  Box,
  Container,
  Paper,
  Typography,
  Stepper,
  Step,
  StepLabel,
  StepButton,
  LinearProgress,
  Alert,
  useTheme,
  useMediaQuery,
  MobileStepper,
  Button,
  Chip,
  Skeleton,
} from '@mui/material';
import {
  KeyboardArrowLeft,
  KeyboardArrowRight,
  CheckCircle as CheckCircleIcon,
  RadioButtonUnchecked as PendingIcon,
} from '@mui/icons-material';

import { usePOSApplication, SECTION_ORDER, SECTION_LABELS } from '../../features/pos';

// Step components — each wraps the corresponding feature panel.
import PersonalInfo from './steps/PersonalInfo';
import Employment from './steps/Employment';
import Assets from './steps/Assets';
import Liabilities from './steps/Liabilities';
import PropertyInfo from './steps/PropertyInfo';
import Declarations from './steps/Declarations';
import ReviewSubmit from './steps/ReviewSubmit';

/**
 * Ordered steps for the progress bar. Maps the 9-step backend model
 * to the 7 user-facing steps requested in the task spec by combining
 * residence into personal and REO into property.
 */
const STEPS = [
  { key: 'personal', label: 'Personal Info', component: PersonalInfo },
  { key: 'employment', label: 'Employment & Income', component: Employment },
  { key: 'assets', label: 'Assets', component: Assets },
  { key: 'liabilities', label: 'Liabilities', component: Liabilities },
  { key: 'loan', label: 'Property & Loan', component: PropertyInfo },
  { key: 'declarations', label: 'Declarations', component: Declarations },
  { key: 'review', label: 'Review & Submit', component: ReviewSubmit },
];

export default function BorrowerApplication() {
  const { loanId } = useParams();
  const [searchParams] = useSearchParams();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  const parsedLoanId = loanId ? Number(loanId) : undefined;
  const effectiveLoanId = Number.isFinite(parsedLoanId) ? parsedLoanId : undefined;

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
  } = usePOSApplication(effectiveLoanId);

  const [activeStep, setActiveStep] = useState(0);

  // Sync active step from backend on initial load.
  useEffect(() => {
    if (application?.current_step) {
      const idx = STEPS.findIndex(s => s.key === application.current_step);
      if (idx >= 0 && !sections[STEPS[0].key]) {
        setActiveStep(idx);
      }
    }
  }, [application, sections]);

  // Pre-load the current step's section data.
  useEffect(() => {
    if (application) {
      const currentKey = STEPS[activeStep]?.key;
      if (currentKey && !sections[currentKey]) {
        loadSection(currentKey);
      }
    }
  }, [application, activeStep, sections, loadSection]);

  const handleStepClick = useCallback((stepIndex) => {
    const step = STEPS[stepIndex];
    if (!step) return;
    setActiveStep(stepIndex);
    if (!sections[step.key]) {
      loadSection(step.key);
    }
  }, [sections, loadSection]);

  const handleNext = useCallback(() => {
    const currentStep = STEPS[activeStep];
    if (!currentStep) return;

    markComplete(currentStep.key).then(() => {
      const nextIdx = Math.min(activeStep + 1, STEPS.length - 1);
      handleStepClick(nextIdx);
    });
  }, [activeStep, markComplete, handleStepClick]);

  const handleBack = useCallback(() => {
    setActiveStep(prev => Math.max(prev - 1, 0));
  }, []);

  const handleSectionChange = useCallback((data) => {
    const currentKey = STEPS[activeStep]?.key;
    if (currentKey) {
      updateSectionData(currentKey, data);
    }
  }, [activeStep, updateSectionData]);

  // Completion percentage for the progress bar.
  const completionPct = application?.completion_pct ?? 0;

  // Check which steps are complete.
  const stepCompletion = useMemo(() => {
    if (!application?.sections_complete) return {};
    return application.sections_complete;
  }, [application]);

  // Loading skeleton.
  if (loading) {
    return (
      <Container maxWidth="md" sx={{ py: 4 }}>
        <Skeleton variant="text" width={300} height={40} />
        <Skeleton variant="rectangular" height={60} sx={{ mt: 2, borderRadius: 1 }} />
        <Skeleton variant="rectangular" height={400} sx={{ mt: 3, borderRadius: 1 }} />
      </Container>
    );
  }

  // Error state.
  if (error || !application) {
    return (
      <Container maxWidth="md" sx={{ py: 4 }}>
        <Alert severity="error" sx={{ mb: 2 }}>
          {error || 'Unable to load your application. Please try again.'}
        </Alert>
        <Button variant="outlined" onClick={() => window.location.reload()}>
          Reload
        </Button>
      </Container>
    );
  }

  const ActiveComponent = STEPS[activeStep]?.component;
  const currentStepKey = STEPS[activeStep]?.key;

  return (
    <Container maxWidth="md" sx={{ py: { xs: 2, md: 4 } }}>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5" component="h1" fontWeight={600}>
          Loan Application
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
          <LinearProgress
            variant="determinate"
            value={completionPct}
            sx={{
              flex: 1,
              height: 8,
              borderRadius: 4,
              bgcolor: 'grey.200',
              '& .MuiLinearProgress-bar': {
                borderRadius: 4,
                bgcolor: completionPct === 100 ? 'success.main' : 'primary.main',
              },
            }}
          />
          <Typography variant="body2" color="text.secondary" sx={{ minWidth: 40 }}>
            {completionPct}%
          </Typography>
          <SaveStateChip state={saveState} />
        </Box>
      </Box>

      {/* Stepper — horizontal on desktop, mobile stepper on small screens */}
      {isMobile ? (
        <MobileStepper
          variant="dots"
          steps={STEPS.length}
          position="static"
          activeStep={activeStep}
          sx={{ mb: 2, bgcolor: 'transparent', p: 0 }}
          nextButton={
            <Button
              size="small"
              onClick={handleNext}
              disabled={activeStep === STEPS.length - 1}
            >
              Next <KeyboardArrowRight />
            </Button>
          }
          backButton={
            <Button
              size="small"
              onClick={handleBack}
              disabled={activeStep === 0}
            >
              <KeyboardArrowLeft /> Back
            </Button>
          }
        />
      ) : (
        <Stepper
          activeStep={activeStep}
          alternativeLabel
          sx={{ mb: 4 }}
        >
          {STEPS.map((step, index) => {
            const isComplete = stepCompletion[step.key] === true;
            return (
              <Step key={step.key} completed={isComplete}>
                <StepButton onClick={() => handleStepClick(index)}>
                  <StepLabel
                    StepIconComponent={isComplete ? CompleteStepIcon : undefined}
                  >
                    {step.label}
                  </StepLabel>
                </StepButton>
              </Step>
            );
          })}
        </Stepper>
      )}

      {/* Active step content */}
      <Paper
        elevation={0}
        sx={{
          p: { xs: 2, md: 4 },
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 2,
          minHeight: 400,
        }}
      >
        <Typography variant="h6" gutterBottom>
          {STEPS[activeStep]?.label}
        </Typography>

        {ActiveComponent && (
          <ActiveComponent
            section={sections[currentStepKey]}
            application={application}
            onChange={handleSectionChange}
            onComplete={handleNext}
            onBack={handleBack}
            onSubmit={submit}
            isFirstStep={activeStep === 0}
            isLastStep={activeStep === STEPS.length - 1}
          />
        )}
      </Paper>

      {/* Mobile navigation buttons */}
      {isMobile && (
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 2 }}>
          <Button
            variant="outlined"
            onClick={handleBack}
            disabled={activeStep === 0}
            startIcon={<KeyboardArrowLeft />}
          >
            Back
          </Button>
          {activeStep < STEPS.length - 1 && (
            <Button
              variant="contained"
              onClick={handleNext}
              endIcon={<KeyboardArrowRight />}
            >
              Save & Continue
            </Button>
          )}
        </Box>
      )}
    </Container>
  );
}


// ---------------------------------------------------------------------------
// Helper components
// ---------------------------------------------------------------------------

function CompleteStepIcon() {
  return <CheckCircleIcon color="success" />;
}

function SaveStateChip({ state }) {
  if (state === 'idle') return null;

  const config = {
    saving: { label: 'Saving...', color: 'default' },
    saved: { label: 'Saved', color: 'success' },
    error: { label: 'Save failed', color: 'error' },
  };

  const { label, color } = config[state] || config.saved;

  return (
    <Chip
      label={label}
      color={color}
      size="small"
      variant="outlined"
      sx={{ ml: 1 }}
    />
  );
}
