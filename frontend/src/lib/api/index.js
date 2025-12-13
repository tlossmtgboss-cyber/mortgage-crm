/**
 * Perennia API Library
 *
 * Re-exports API client and hooks for easy importing.
 */

// API Client
export { api, PerenniaAPI, PerenniaAPIError, getApiBaseUrl } from './client';

// React Hooks
export {
  // Generic hooks
  useApiQuery,
  useApiMutation,

  // Workspace hooks
  useWorkspaceDocumentStatus,
  useWorkspaceMilestones,
  useWorkspaceActivityFeed,
  useWorkspaceNotifications,
  useWorkspaceDocuments,
  useWorkspaceData,
  useWorkspaceApplication,

  // AI Assistant hooks
  useAIAssistant,
  useQuickActions,
  useFAQ,
  useTips,
  useAssistantFeedback,

  // Document hooks
  useDocumentUpload,
  useReviewDocument,

  // Auth hooks
  usePortalSession,
  useSendMagicLink,
  useVerifyMagicLink,

  // Mutation hooks
  useMarkNotificationRead,
  useMarkAllNotificationsRead,
  useUpdateMilestone,
  useSendMessage,
} from './hooks';

// Auth Provider
export {
  PortalAuthProvider,
  usePortalAuth,
  withPortalAuth,
  RequirePortalAuth,
} from './PortalAuthProvider';
