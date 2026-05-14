/**
 * Purchase Application - Stage Definitions
 * Defines the 9-stage flow for home purchase applications.
 */

export const STAGES = [
  { id: 'account', label: 'Get Started', icon: 'user', description: 'Create your account', hideFromProgress: true },
  { id: 'declarations', label: 'Your Story', icon: 'story', description: 'Quick questions to personalize' },
  { id: 'planning', label: 'Your Goals', icon: 'goals', description: 'Mortgage preferences' },
  { id: 'profile', label: 'About You', icon: 'profile', description: 'The basics about you' },
  { id: 'income', label: 'Your Income', icon: 'income', description: 'How you earn' },
  { id: 'assets', label: 'Your Assets', icon: 'assets', description: 'Down payment funds' },
  { id: 'property', label: 'New Home', icon: 'home', description: 'Property details' },
  { id: 'review', label: 'Review', icon: 'review', description: 'Review your info' },
  { id: 'schedule', label: 'Schedule', icon: 'calendar', description: 'Book a call' },
];

// Visible stages for progress bar (excludes account creation)
export const VISIBLE_STAGES = STAGES.filter(s => !s.hideFromProgress);

// Purchase-specific document category unlock mapping
export const CATEGORY_UNLOCK_STAGE = {
  identity: 'declarations',
  income: 'income',
  assets: 'assets',
  property: 'property',
};
