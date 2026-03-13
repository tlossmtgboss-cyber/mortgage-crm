/**
 * Custom React hooks index
 */

export { useDialerWebSocket, useDialerEvents } from './useDialerWebSocket';
export { useDialerSession } from './useDialerSession';

// Page Permissions hook
export { usePagePermissions, withPageAccess } from './usePagePermissions';

// Media query hooks
export {
  useMediaQuery,
  useIsTablet,
  useIsMobile,
  useIsDesktop,
  useIsPortrait,
  useIsLandscape,
  useIsTabletPortrait,
  useIsTabletLandscape,
} from './useMediaQuery';

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
