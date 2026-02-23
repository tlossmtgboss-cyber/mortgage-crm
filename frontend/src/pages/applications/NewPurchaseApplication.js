/**
 * NewPurchaseApplication - Enhanced purchase mortgage application
 * Entry point that sets up context and renders the application flow
 */

import React, { useCallback, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ApplicationProvider, useApplication } from './contexts/ApplicationContext';
import { useApplicationPersistence } from './hooks/useApplicationPersistence';
import { allPurchaseQuestions, getQuestionsByStage } from './config/purchaseQuestions';
import ApplicationShell from './components/ApplicationShell';
import StageRenderer from './components/StageRenderer';
import './NewPurchaseApplication.css';

// API base URL
const API_BASE_URL = process.env.REACT_APP_API_URL || '';

// Inner component that uses the context
const PurchaseApplicationContent = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { state } = useApplication();
  const { currentStage, applicationType, formData } = state;

  // Submission state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  // Get workspace slug from URL
  const workspaceSlug = searchParams.get('workspace');
  const isDemo = searchParams.get('demo') === 'true';

  // Set up persistence
  const {
    isSaving,
    lastSavedAt,
    forceSave,
    clearSavedData,
    showRestorePrompt,
    confirmRestore,
    declineRestore,
  } = useApplicationPersistence({
    enableApiSave: !isDemo && !!workspaceSlug,
    apiEndpoint: workspaceSlug
      ? `/api/purl/workspace/${workspaceSlug}/application`
      : null,
    onSaveError: (error) => {
      console.error('Save error:', error);
    },
  });

  // Get questions for current stage
  const currentQuestions = useMemo(
    () => getQuestionsByStage(currentStage),
    [currentStage]
  );

  // Handle exit
  const handleExit = useCallback(() => {
    // Save before exit
    forceSave();

    // Navigate back
    if (workspaceSlug) {
      navigate(`/apply/${workspaceSlug}`);
    } else {
      navigate('/');
    }
  }, [forceSave, navigate, workspaceSlug]);

  // Validate required fields before submission
  const validateSubmission = useCallback(() => {
    const errors = [];
    const borrowers = formData.borrowers || [];
    const primary = borrowers[0] || {};

    // Primary borrower must have basic info
    if (!primary.first_name?.trim()) errors.push('Primary borrower first name is required');
    if (!primary.last_name?.trim()) errors.push('Primary borrower last name is required');

    // Email validation
    const email = primary.email || formData.email || '';
    if (!email.trim()) {
      errors.push('Email address is required');
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      errors.push('Please enter a valid email address');
    }

    // SSN validation (must be exactly 9 digits)
    const ssn = (primary.ssn || '').replace(/\D/g, '');
    if (!ssn) {
      errors.push('Social Security Number is required');
    } else if (ssn.length !== 9) {
      errors.push('Social Security Number must be 9 digits');
    } else if (ssn === '000000000' || ssn.startsWith('9') || ssn.startsWith('666')) {
      errors.push('Please enter a valid Social Security Number');
    }

    // Consent must be agreed
    if (!formData.econsent_agreed) errors.push('Electronic consent is required');
    if (!formData.credit_auth_agreed) errors.push('Credit authorization is required');

    return errors;
  }, [formData]);

  // Handle application complete (submit and redirect)
  const handleComplete = useCallback(async () => {
    if (isSubmitting) return;

    // Validate before submission
    const validationErrors = validateSubmission();
    if (validationErrors.length > 0) {
      setSubmitError(validationErrors.join('. '));
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      // Prepare submission data
      const submissionData = {
        ...formData,
        applicationType,
        submittedAt: new Date().toISOString(),
        workspaceSlug,
      };

      if (!isDemo && workspaceSlug) {
        // Submit to API
        const response = await fetch(
          `${API_BASE_URL}/api/purl/workspace/${workspaceSlug}/application/submit`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(submissionData),
          }
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.message || 'Failed to submit application');
        }

        const result = await response.json();

        // Clear saved PII from localStorage after successful submission
        clearSavedData();
        localStorage.removeItem('borrower_email');

        // Redirect to client portal
        // The portal URL is typically returned from the API
        const portalUrl = result.portalUrl || `/portal/${result.applicationId}`;

        // Show success message briefly, then redirect
        setTimeout(() => {
          window.location.href = portalUrl;
        }, 500);

      } else {
        // Demo mode - just log and show success
        console.log('Demo submission:', submissionData);

        // Clear saved data even in demo mode
        clearSavedData();

        // Simulate successful submission
        setTimeout(() => {
          // Redirect to a thank-you page or portal demo
          navigate('/apply/demo?submitted=true');
        }, 1000);
      }

    } catch (error) {
      console.error('Submission error:', error);
      setSubmitError(error.message || 'An error occurred while submitting your application.');
      setIsSubmitting(false);
    }
  }, [formData, applicationType, workspaceSlug, isDemo, isSubmitting, navigate, validateSubmission]);

  // Exit confirmation state (replaces window.confirm)
  const [showExitPrompt, setShowExitPrompt] = useState(false);

  // Handle going back before first stage
  const handleFirstStageBack = useCallback(() => {
    setShowExitPrompt(true);
  }, []);

  return (
    <ApplicationShell
      onExit={handleExit}
      showSaveIndicator={true}
    >
      {showRestorePrompt && (
        <div className="exit-confirm-banner restore-prompt" role="alertdialog" aria-label="Restore saved application">
          <p>You have a saved application in progress. Would you like to continue where you left off?</p>
          <div className="exit-confirm-actions">
            <button type="button" className="btn-cancel-exit" onClick={confirmRestore}>
              Continue Application
            </button>
            <button type="button" className="btn-confirm-exit" onClick={declineRestore}>
              Start Fresh
            </button>
          </div>
        </div>
      )}
      {showExitPrompt && (
        <div className="exit-confirm-banner" role="alertdialog" aria-label="Confirm exit">
          <p>Are you sure you want to exit the application?</p>
          <div className="exit-confirm-actions">
            <button type="button" className="btn-confirm-exit" onClick={handleExit}>
              Exit
            </button>
            <button type="button" className="btn-cancel-exit" onClick={() => setShowExitPrompt(false)}>
              Continue
            </button>
          </div>
        </div>
      )}
      {submitError && (
        <div className="exit-confirm-banner submit-error" role="alert">
          <p>{submitError}</p>
          <div className="exit-confirm-actions">
            <button type="button" className="btn-cancel-exit" onClick={() => setSubmitError(null)}>
              Dismiss
            </button>
          </div>
        </div>
      )}
      {isSubmitting && (
        <div className="exit-confirm-banner submitting-banner" role="status">
          <p>Submitting your application...</p>
        </div>
      )}
      <StageRenderer
        questions={currentQuestions}
        stageId={currentStage}
        onStageComplete={handleComplete}
        onStagePrevious={handleFirstStageBack}
      />
    </ApplicationShell>
  );
};

// Main component that wraps with provider
const NewPurchaseApplication = () => {
  const [searchParams] = useSearchParams();
  const workspaceSlug = searchParams.get('workspace');

  return (
    <ApplicationProvider
      applicationType="purchase"
      workspaceSlug={workspaceSlug}
    >
      <PurchaseApplicationContent />
    </ApplicationProvider>
  );
};

export default NewPurchaseApplication;
