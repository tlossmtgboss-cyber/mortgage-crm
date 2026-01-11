/**
 * Portal Components
 *
 * Export all borrower portal components from a single entry point.
 */

export { default as DocumentStatusBadge } from './DocumentStatusBadge';
export { default as NotificationDropdown } from './NotificationDropdown';
export { default as UserMenu } from './UserMenu';
export { default as LoanSelector } from './LoanSelector';
export { default as PortalModeIndicator } from './PortalModeIndicator';

// Enhanced Portal Components
export { default as EnhancedPortalHeader } from './EnhancedPortalHeader';
export { DaysCounter, MilestoneProgressBar, LoanOfficerCard, LoanInfoBar } from './EnhancedPortalHeader';
export { default as PortalTabs, TabPanel, PORTAL_TABS, getTabsForMode } from './PortalTabs';
export { default as LoanPortalRedirect } from './LoanPortalRedirect';
export { default as MilestoneTimeline } from './MilestoneTimeline';
