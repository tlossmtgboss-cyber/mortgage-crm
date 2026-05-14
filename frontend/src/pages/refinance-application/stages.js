/**
 * Refinance Application - Stage Definitions
 * Defines the 9-stage flow for refinance applications.
 */

export const STAGES = [
  { id: 'account', label: 'Get Started', icon: 'user', description: 'Create your account', hideFromProgress: true },
  { id: 'declarations', label: 'Your Story', icon: 'story', description: 'Quick questions' },
  { id: 'planning', label: 'Planning', icon: 'goals', description: 'Your preferences' },
  { id: 'profile', label: 'About You', icon: 'profile', description: 'The basics' },
  { id: 'income', label: 'Your Income', icon: 'income', description: 'How you earn' },
  { id: 'property', label: 'Current Home', icon: 'home', description: 'Property details' },
  { id: 'goals', label: 'Refi Goals', icon: 'target', description: 'Refinance options' },
  { id: 'review', label: 'Review', icon: 'review', description: 'Review your info' },
  { id: 'schedule', label: 'Submit', icon: 'check', description: 'Complete application' },
];

// Stages visible in progress bar (excludes account)
export const VISIBLE_STAGES = STAGES.filter(s => !s.hideFromProgress);

// Refinance-specific document category unlock mapping
// Assets unlock with income stage for refinance (no separate assets stage)
export const CATEGORY_UNLOCK_STAGE = {
  identity: 'declarations',
  income: 'income',
  assets: 'income',  // Assets unlock with income stage for refinance
  property: 'property',
};
