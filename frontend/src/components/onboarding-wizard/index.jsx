import React from 'react';
import { useOnboardingState } from './useOnboardingState';
import OverviewStep from './OverviewStep';
import UserRegistrationStep from './UserRegistrationStep';
import TeamSetupStep from './TeamSetupStep';
import ProcessUploadStep from './ProcessUploadStep';
import { AssignRolesStep, ReviewTasksStep } from './ReviewSteps';
import { DataPreviewStep, DataUploadStep, ReviewDataStep } from './DataSteps';
import IntegrationsStep from './IntegrationsStep';
import AISetupStep from './AISetupStep';
import { HelpdeskModal, ConnectionModal, TaskEditModal, RoleAddModal } from './OnboardingModals';
import '../OnboardingWizard.css';

const OnboardingWizard = ({ onComplete, onSkip }) => {
  const state = useOnboardingState({ onComplete });

  const {
    currentStep, totalSteps,
    formData, setFormData,
    isProcessing, setIsProcessing,
    connectionModal, setConnectionModal,
    helpdeskModal, taskEditModal, roleAddModal,
    newRoleForm, setNewRoleForm,
    teamMembers,
    selectedMemberForTasks, setSelectedMemberForTasks,
    memberTaskModal, setMemberTaskModal,
    previewEmails,
    handleNext, handleBack,
    updateField,
    handleFileSelect, removeFile, formatFileSize,
    handleDragOver, handleDrop,
    handlePreviewEmailUpload,
    handleCloseHelpdeskModal, handleSubmitTicket,
    handleCloseModal, handleAuthComplete,
    handleCloseTaskEdit, handleSaveTaskEdit, handleUpdateTaskEditField,
    handleCloseRoleAdd, handleSaveNewRole,
    setCurrentStep,
  } = state;

  const renderStep = () => {
    switch (currentStep) {
      case 0:
        return <OverviewStep />;
      case 1:
        return <UserRegistrationStep formData={formData} setFormData={setFormData} />;
      case 2:
        return <TeamSetupStep formData={formData} setFormData={setFormData} />;
      case 3:
        return (
          <ProcessUploadStep
            formData={formData} setFormData={setFormData}
            isProcessing={isProcessing} setIsProcessing={setIsProcessing}
            setCurrentStep={setCurrentStep}
            handleFileSelect={handleFileSelect}
            removeFile={removeFile} formatFileSize={formatFileSize}
            handleDragOver={handleDragOver} handleDrop={handleDrop}
            updateField={updateField}
          />
        );
      case 4:
        return <AssignRolesStep formData={formData} />;
      case 5:
        return (
          <ReviewTasksStep
            formData={formData} setFormData={setFormData}
            selectedMemberForTasks={selectedMemberForTasks}
            setSelectedMemberForTasks={setSelectedMemberForTasks}
            memberTaskModal={memberTaskModal}
            setMemberTaskModal={setMemberTaskModal}
          />
        );
      case 6:
        return <DataPreviewStep previewEmails={previewEmails} handlePreviewEmailUpload={handlePreviewEmailUpload} />;
      case 7:
        return <DataUploadStep />;
      case 8:
        return <ReviewDataStep />;
      case 9:
        return <IntegrationsStep formData={formData} setFormData={setFormData} setConnectionModal={setConnectionModal} />;
      case 10:
        return <AISetupStep formData={formData} />;
      default:
        return null;
    }
  };

  const progress = (currentStep / totalSteps) * 100;
  const canProceed = true;

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-wizard-v2">
        {/* Close Button */}
        {onSkip && (
          <button className="btn-close-wizard" onClick={onSkip} title="Skip for now">
            ×
          </button>
        )}

        {/* Progress Bar */}
        <div className="wizard-progress">
          <div className="progress-bar-container">
            <div className="progress-bar-fill" style={{ width: `${progress}%` }}></div>
          </div>
          <div className="progress-text">
            Step {currentStep} of {totalSteps}
          </div>
        </div>

        {/* Step Indicators */}
        <div className="step-indicators">
          {[
            { num: 1, label: 'Registration', time: '5 min' },
            { num: 2, label: 'Team Setup', time: '10 min' },
            { num: 3, label: 'Process Docs', time: '15 min' },
            { num: 4, label: 'Assign Roles', time: '10 min' },
            { num: 5, label: 'Review Tasks', time: '10 min' },
            { num: 6, label: 'Data Preview', time: '5 min' },
            { num: 7, label: 'Data Upload', time: '15 min' },
            { num: 8, label: 'Review Data', time: '10 min' },
            { num: 9, label: 'Integrations', time: '10 min' },
            { num: 10, label: 'AI Setup', time: '10 min' }
          ].map((step) => (
            <div
              key={step.num}
              className={`step-indicator ${currentStep >= step.num ? 'active' : ''} ${
                currentStep > step.num ? 'completed' : ''
              }`}
            >
              <div className="indicator-dot">
                {currentStep > step.num ? '✓' : step.num}
              </div>
              <div className="indicator-label">{step.label}</div>
            </div>
          ))}
        </div>

        {/* Step Content */}
        {renderStep()}

        {/* Navigation */}
        <div className="wizard-navigation">
          {currentStep > 1 && (
            <button className="btn-nav btn-back" onClick={handleBack}>
              ← Back
            </button>
          )}

          <div className="nav-spacer"></div>

          <button
            className={`btn-nav btn-next ${!canProceed ? 'disabled' : ''}`}
            onClick={handleNext}
            disabled={!canProceed}
          >
            {currentStep === totalSteps ? (
              <>Activate Account & Go Live! 🚀</>
            ) : currentStep === 0 ? (
              <>Get Started</>
            ) : (
              <>Next →</>
            )}
          </button>
        </div>
      </div>

      {/* Modals */}
      <HelpdeskModal
        helpdeskModal={helpdeskModal}
        formData={formData}
        onClose={handleCloseHelpdeskModal}
        onSubmit={handleSubmitTicket}
      />

      <ConnectionModal
        connectionModal={connectionModal}
        onClose={handleCloseModal}
        onAuthComplete={handleAuthComplete}
      />

      <TaskEditModal
        taskEditModal={taskEditModal}
        formData={formData}
        teamMembers={teamMembers}
        onClose={handleCloseTaskEdit}
        onSave={handleSaveTaskEdit}
        onUpdateField={handleUpdateTaskEditField}
      />

      <RoleAddModal
        roleAddModal={roleAddModal}
        newRoleForm={newRoleForm}
        setNewRoleForm={setNewRoleForm}
        onClose={handleCloseRoleAdd}
        onSave={handleSaveNewRole}
      />
    </div>
  );
};

export default OnboardingWizard;
