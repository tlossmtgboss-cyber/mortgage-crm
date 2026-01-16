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

  // Handle application complete (submit and redirect)
  const handleComplete = useCallback(async () => {
    if (isSubmitting) return;

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
  }, [formData, applicationType, workspaceSlug, isDemo, isSubmitting, navigate]);

  // Handle going back before first stage
  const handleFirstStageBack = useCallback(() => {
    // Could show a confirmation or go to landing page
    const confirmed = window.confirm(
      'Are you sure you want to exit the application?'
    );
    if (confirmed) {
      handleExit();
    }
  }, [handleExit]);

  return (
    <ApplicationShell
      onExit={handleExit}
      showSaveIndicator={true}
    >
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
