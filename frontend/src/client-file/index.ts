// Public API for the @perennia/client-file package.
//
// Consumers should import from this entry point only:
//
//   import { ClientFileView, setApiBaseUrl } from "@perennia/client-file";
//
// Internal module structure may change without notice.

export { ClientFileView } from "./ClientFileView";
export { IdentityPanel } from "./IdentityPanel";
export { ActivityPane } from "./ActivityPane";
export { ActivityComposer } from "./ActivityComposer";
export { UnifiedTimeline } from "./UnifiedTimeline";
export { DocumentsPane } from "./DocumentsPane";
export { TasksPane } from "./TasksPane";
export { TeamChatPane } from "./TeamChatPane";
export { ToolsRail } from "./ToolsRail";
export { QuickActionsRail } from "./QuickActionsRail";
export {
  ActionPlansPanel,
  DocumentsPanel,
  FollowUpsPanel,
  InsightsPanel,
  LoanPanel,
  RelationshipsPanel,
  TasksPanel,
} from "./RailPanels";

export { Avatar, deriveInitials } from "./primitives/Avatar";
export { Card } from "./primitives/Card";
export { Glyph } from "./primitives/Glyph";
export { Pill } from "./primitives/Pill";

export {
  setApiBaseUrl,
  ApiError,
  cadenceApi,
  clientFileApi,
  documentApi,
  insightApi,
  relationshipApi,
  taskApi,
  teamChatApi,
  timelineApi,
  actionPlanApi,
} from "./api";

export {
  qk,
  useClientFile,
  usePatchClientFile,
  useSetLifecycleStage,
  useSetStickyNote,
  useTimeline,
  useStarEvent,
  useAddNote,
  useSendMessage,
  useInsight,
  useTasks,
  useTaskMutations,
  useDocumentSets,
  useDocumentsTab,
  useDocumentActions,
  useCadenceSequences,
  useCadenceLifecycle,
  useRelationships,
  useActionPlanRuns,
  useTeamChatMessages,
  useTeamChatPinned,
  useTeamChatMembers,
  useTeamChatUnread,
  useTeamChatTyping,
  useTeamChatActions,
  useTeamChatBadge,
} from "./hooks";

export {
  formatRelativeTime,
  formatTime,
  formatDayLabel,
  dayKey,
  LIFECYCLE_STAGE_LABEL,
  LIFECYCLE_STAGE_ORDER,
} from "./format";

export type * from "./types";
