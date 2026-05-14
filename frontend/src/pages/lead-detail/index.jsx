/**
 * Re-exports for clean imports from the lead-detail directory.
 *
 * Usage:
 *   import { LoanDetailsTab, PersonalTab } from './lead-detail';
 */

export { default as LoanDetailsTab } from './LoanDetailsTab';
export { default as PersonalTab } from './PersonalTab';
export { default as PropertyTab } from './PropertyTab';
export { default as TasksTab } from './TasksTab';
export { default as ConversationLogTab } from './ConversationLogTab';
export { default as CircleTab } from './CircleTab';
export { default as ConditionsTab } from './ConditionsTab';
export { default as SLADatesTab } from './SLADatesTab';

// Re-export constants
export { statusOptions, circleContactTypes, getStatusColor, getContactIcon } from './constants';
