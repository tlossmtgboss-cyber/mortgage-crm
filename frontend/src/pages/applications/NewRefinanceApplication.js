/**
 * NewRefinanceApplication - Enhanced refinance mortgage application
 * Entry point that sets up context and renders the application flow
 */

import React, { useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ApplicationProvider, useApplication } from './contexts/ApplicationContext';
import { useApplicationPersistence } from './hooks/useApplicationPersistence';
import { allRefinanceQuestions, getQuestionsByStage } from './config/refinanceQuestions';
import ApplicationShell from './components/ApplicationShell';
import StageRenderer from './components/StageRenderer';
import './NewRefinanceApplication.css';

// Inner component that uses the context
const RefinanceApplicationContent = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { state } = useApplication();
  const { currentStage, applicationType } = state;

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

  // Handle application complete
  const handleComplete = useCallback(() => {
    // Navigate to review/submit stage
    console.log('Application complete!');
  }, []);

  // Handle going back before first stage
  const handleFirstStageBack = useCallback(() => {
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
const NewRefinanceApplication = () => {
  const [searchParams] = useSearchParams();
  const workspaceSlug = searchParams.get('workspace');

  return (
    <ApplicationProvider
      applicationType="refinance"
      workspaceSlug={workspaceSlug}
    >
      <RefinanceApplicationContent />
    </ApplicationProvider>
  );
};

export default NewRefinanceApplication;
