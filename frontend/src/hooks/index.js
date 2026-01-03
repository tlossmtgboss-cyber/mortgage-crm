/**
 * Custom React hooks index
 */

export { useDialerWebSocket, useDialerEvents } from './useDialerWebSocket';
export { useDialerSession } from './useDialerSession';

// Page Permissions hook
export { usePagePermissions, withPageAccess } from './usePagePermissions';

// Realtor Portal hooks
export {
  useLoanSync,
  useRealtorAuth,
  useRealtorLoan,
  useRealtorLoans,
  useRealtorTimeline,
  useRealtorConditions,
  useLetterGeneration,
  useRealtorMessages,
  useAIAssistant,
} from './useRealtorPortal';
