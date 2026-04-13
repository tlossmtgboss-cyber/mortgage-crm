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

// Network status
export { useNetworkStatus } from './useNetworkStatus';

// Sensitive screen protection (screen recording prevention)
export { useSensitiveScreen, markCaptureDetected, clearCaptureDetected } from './useSensitiveScreen';

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
