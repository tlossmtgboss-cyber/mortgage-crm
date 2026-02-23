/**
 * Stage Configuration
 * Defines all stages for purchase and refinance applications
 */

// Purchase Application Stages (10 stages)
export const PURCHASE_STAGES = [
  {
    id: 'about_you',
    label: 'About You',
    shortLabel: 'You',
    icon: 'user',
    description: 'Tell us about yourself',
    progress: 10,
    order: 1,
  },
  {
    id: 'new_home',
    label: 'New Home',
    shortLabel: 'Home',
    icon: 'home',
    description: 'Tell us about the property',
    progress: 25,
    order: 2,
  },
  {
    id: 'income',
    label: 'Your Income',
    shortLabel: 'Income',
    icon: 'dollar',
    description: 'Employment and income details',
    progress: 40,
    order: 3,
  },
  {
    id: 'assets',
    label: 'Your Assets',
    shortLabel: 'Assets',
    icon: 'bank',
    description: 'Bank accounts and investments',
    progress: 55,
    order: 4,
  },
  {
    id: 'real_estate_owned',
    label: 'Real Estate',
    shortLabel: 'REO',
    icon: 'building',
    description: 'Other properties you own',
    progress: 60,
    order: 5,
  },
  {
    id: 'credit',
    label: 'Credit History',
    shortLabel: 'Credit',
    icon: 'credit-card',
    description: 'Your credit history and score',
    progress: 70,
    order: 6,
  },
  {
    id: 'background',
    label: 'Declarations',
    shortLabel: 'Declarations',
    icon: 'clipboard',
    description: 'Financial declarations',
    progress: 80,
    order: 7,
  },
  {
    id: 'government_monitoring',
    label: 'Demographics',
    shortLabel: 'HMDA',
    icon: 'chart',
    description: 'Government monitoring information (optional)',
    progress: 85,
    order: 8,
    optional: true,
  },
  {
    id: 'schedule',
    label: 'Schedule',
    shortLabel: 'Schedule',
    icon: 'calendar',
    description: 'Schedule a consultation',
    progress: 90,
    order: 9,
  },
  {
    id: 'authorizations',
    label: 'Review & Sign',
    shortLabel: 'Sign',
    icon: 'check',
    description: 'Review and authorize',
    progress: 95,
    order: 10,
  },
];

// Refinance Application Stages (12 stages - includes current mortgage and credit)
export const REFINANCE_STAGES = [
  {
    id: 'about_you',
    label: 'About You',
    shortLabel: 'You',
    icon: 'user',
    description: 'Tell us about yourself',
    progress: 10,
    order: 1,
  },
  {
    id: 'current_mortgage',
    label: 'Current Mortgage',
    shortLabel: 'Mortgage',
    icon: 'document',
    description: 'Your existing mortgage details',
    progress: 20,
    order: 2,
  },
  {
    id: 'second_mortgage',
    label: 'Second Mortgage',
    shortLabel: '2nd Lien',
    icon: 'document-alt',
    description: 'Any second mortgage or HELOC',
    progress: 30,
    order: 3,
    showIf: { has_second_mortgage: true },
  },
  {
    id: 'property',
    label: 'Property',
    shortLabel: 'Property',
    icon: 'home',
    description: 'Property details',
    progress: 40,
    order: 4,
  },
  {
    id: 'income',
    label: 'Your Income',
    shortLabel: 'Income',
    icon: 'dollar',
    description: 'Employment and income details',
    progress: 50,
    order: 5,
  },
  {
    id: 'assets',
    label: 'Your Assets',
    shortLabel: 'Assets',
    icon: 'bank',
    description: 'Bank accounts and investments',
    progress: 55,
    order: 6,
  },
  {
    id: 'real_estate_owned',
    label: 'Real Estate',
    shortLabel: 'REO',
    icon: 'building',
    description: 'Other properties you own',
    progress: 60,
    order: 7,
  },
  {
    id: 'credit',
    label: 'Credit History',
    shortLabel: 'Credit',
    icon: 'credit-card',
    description: 'Your credit history and score',
    progress: 70,
    order: 8,
  },
  {
    id: 'background',
    label: 'Declarations',
    shortLabel: 'Declarations',
    icon: 'clipboard',
    description: 'Financial declarations',
    progress: 80,
    order: 9,
  },
  {
    id: 'government_monitoring',
    label: 'Demographics',
    shortLabel: 'HMDA',
    icon: 'chart',
    description: 'Government monitoring information (optional)',
    progress: 85,
    order: 10,
    optional: true,
  },
  {
    id: 'schedule',
    label: 'Schedule',
    shortLabel: 'Schedule',
    icon: 'calendar',
    description: 'Schedule a consultation',
    progress: 90,
    order: 11,
  },
  {
    id: 'authorizations',
    label: 'Review & Sign',
    shortLabel: 'Sign',
    icon: 'check',
    description: 'Review and authorize',
    progress: 95,
    order: 12,
  },
];

// Get stages by application type
export function getStages(applicationType) {
  return applicationType === 'refinance' ? REFINANCE_STAGES : PURCHASE_STAGES;
}

// Get visible stages (filtered by showIf conditions)
export function getVisibleStages(applicationType, formData) {
  const stages = getStages(applicationType);

  return stages.filter(stage => {
    if (!stage.showIf) return true;

    // Evaluate showIf condition
    return Object.entries(stage.showIf).every(([field, expectedValue]) => {
      const actualValue = formData[field];

      if (Array.isArray(expectedValue)) {
        return expectedValue.includes(actualValue);
      }

      return actualValue === expectedValue;
    });
  });
}

// Get stage by ID
export function getStageById(applicationType, stageId) {
  const stages = getStages(applicationType);
  return stages.find(s => s.id === stageId);
}

// Get next stage
export function getNextStage(applicationType, currentStageId, formData) {
  const visibleStages = getVisibleStages(applicationType, formData);
  const currentIndex = visibleStages.findIndex(s => s.id === currentStageId);

  if (currentIndex === -1 || currentIndex >= visibleStages.length - 1) {
    return null;
  }

  return visibleStages[currentIndex + 1];
}

// Get previous stage
export function getPrevStage(applicationType, currentStageId, formData) {
  const visibleStages = getVisibleStages(applicationType, formData);
  const currentIndex = visibleStages.findIndex(s => s.id === currentStageId);

  if (currentIndex <= 0) {
    return null;
  }

  return visibleStages[currentIndex - 1];
}

// Calculate overall progress based on current stage
export function calculateProgress(applicationType, currentStageId, questionProgress = 0, formData = {}) {
  const visibleStages = getVisibleStages(applicationType, formData);
  const currentStage = visibleStages.find(s => s.id === currentStageId);

  if (!currentStage) return 0;

  const currentIndex = visibleStages.findIndex(s => s.id === currentStageId);
  const stageCount = visibleStages.length;

  // Base progress from completed stages
  const stageWeight = 100 / stageCount;
  const completedProgress = currentIndex * stageWeight;

  // Add progress within current stage
  const currentStageProgress = (questionProgress / 100) * stageWeight;

  return Math.round(completedProgress + currentStageProgress);
}

// Stage navigation helpers
export const stageNavigation = {
  getStages,
  getVisibleStages,
  getStageById,
  getNextStage,
  getPrevStage,
  calculateProgress,
};

export default stageNavigation;
