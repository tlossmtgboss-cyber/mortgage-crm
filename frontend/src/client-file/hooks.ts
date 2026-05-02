// ─────────────────────────────────────────────────────────────────────────
// Hooks — TanStack Query v5 wrappers
// ─────────────────────────────────────────────────────────────────────────

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import {
  actionPlanApi,
  cadenceApi,
  clientFileApi,
  documentApi,
  insightApi,
  relationshipApi,
  taskApi,
  teamChatApi,
  timelineApi,
} from "./api";
import type {
  ActivityCategory,
  ClientFile,
  TeamChatMessage,
  TeamChatReactionEmoji,
} from "./types";

// ─────────────────────────────────────────────────────────────────────────
// Query keys
// ─────────────────────────────────────────────────────────────────────────

export const qk = {
  all: ["pf-cf"] as const,
  client: (id: string) => [...qk.all, "client", id] as const,
  timeline: (id: string, cat: ActivityCategory) =>
    [...qk.all, "timeline", id, cat] as const,
  insight: (id: string) => [...qk.all, "insight", id] as const,
  tasks: (id: string, includeDone: boolean) =>
    [...qk.all, "tasks", id, includeDone] as const,
  documents: (id: string) => [...qk.all, "documents", id] as const,
  cadence: (id: string) => [...qk.all, "cadence", id] as const,
  relationships: (id: string) => [...qk.all, "relationships", id] as const,
  actionPlans: (id: string) => [...qk.all, "actionPlans", id] as const,
  // Team chat
  teamChatMessages: (id: string) => [...qk.all, "teamChat", id, "messages"] as const,
  teamChatPinned: (id: string) => [...qk.all, "teamChat", id, "pinned"] as const,
  teamChatMembers: (id: string) => [...qk.all, "teamChat", id, "members"] as const,
  teamChatUnread: (id: string) => [...qk.all, "teamChat", id, "unread"] as const,
  teamChatTyping: (id: string) => [...qk.all, "teamChat", id, "typing"] as const,
};

// ─────────────────────────────────────────────────────────────────────────
// Client file
// ─────────────────────────────────────────────────────────────────────────

export function useClientFile(
  clientFileId: string,
  opts?: Partial<UseQueryOptions<ClientFile>>,
) {
  return useQuery({
    queryKey: qk.client(clientFileId),
    queryFn: () => clientFileApi.get(clientFileId),
    ...opts,
  });
}

export function usePatchClientFile(clientFileId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<ClientFile>) =>
      clientFileApi.patch(clientFileId, patch),
    onSuccess: (data) => {
      qc.setQueryData(qk.client(clientFileId), data);
    },
  });
}

export function useSetLifecycleStage(clientFileId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (stage: ClientFile["lifecycle_stage"]) =>
      clientFileApi.setLifecycleStage(clientFileId, stage),
    onSuccess: (data) => {
      qc.setQueryData(qk.client(clientFileId), data);
      qc.invalidateQueries({ queryKey: qk.timeline(clientFileId, "all") });
    },
  });
}

export function useSetStickyNote(clientFileId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (note: string | null) =>
      clientFileApi.setStickyNote(clientFileId, note),
    onSuccess: (data) => qc.setQueryData(qk.client(clientFileId), data),
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Timeline
// ─────────────────────────────────────────────────────────────────────────

export function useTimeline(
  clientFileId: string,
  category: ActivityCategory = "all",
) {
  return useQuery({
    queryKey: qk.timeline(clientFileId, category),
    queryFn: () => timelineApi.list(clientFileId, category),
    refetchInterval: 30_000, // soft real-time without WS
  });
}

export function useStarEvent(clientFileId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ eventId, starred }: { eventId: string; starred: boolean }) =>
      starred
        ? timelineApi.unstar(clientFileId, eventId)
        : timelineApi.star(clientFileId, eventId),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: [...qk.all, "timeline", clientFileId],
      });
    },
  });
}

export function useAddNote(clientFileId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => timelineApi.addNote(clientFileId, body),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: [...qk.all, "timeline", clientFileId],
      });
    },
  });
}

export function useSendMessage(clientFileId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: Parameters<typeof timelineApi.sendMessage>[1]) =>
      timelineApi.sendMessage(clientFileId, input),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: [...qk.all, "timeline", clientFileId],
      });
      qc.invalidateQueries({ queryKey: qk.client(clientFileId) });
      qc.invalidateQueries({ queryKey: qk.cadence(clientFileId) });
    },
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Insight
// ─────────────────────────────────────────────────────────────────────────

export function useInsight(clientFileId: string) {
  return useQuery({
    queryKey: qk.insight(clientFileId),
    queryFn: () => insightApi.get(clientFileId),
    refetchInterval: 60_000,
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Tasks
// ─────────────────────────────────────────────────────────────────────────

export function useTasks(clientFileId: string, opts: { includeDone?: boolean } = {}) {
  return useQuery({
    queryKey: qk.tasks(clientFileId, !!opts.includeDone),
    queryFn: () => taskApi.list(clientFileId, opts),
  });
}

export function useTaskMutations(clientFileId: string) {
  const qc = useQueryClient();
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: [...qk.all, "tasks", clientFileId] });
  return {
    complete: useMutation({
      mutationFn: (taskId: string) => taskApi.complete(clientFileId, taskId),
      onSuccess: invalidate,
    }),
    reopen: useMutation({
      mutationFn: (taskId: string) => taskApi.reopen(clientFileId, taskId),
      onSuccess: invalidate,
    }),
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Documents
// ─────────────────────────────────────────────────────────────────────────

export function useDocumentSets(clientFileId: string) {
  return useQuery({
    queryKey: qk.documents(clientFileId),
    queryFn: () => documentApi.listSets(clientFileId),
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Cadence
// ─────────────────────────────────────────────────────────────────────────

export function useCadenceSequences(clientFileId: string) {
  return useQuery({
    queryKey: qk.cadence(clientFileId),
    queryFn: () => cadenceApi.listForClient(clientFileId),
  });
}

export function useCadenceLifecycle(clientFileId: string) {
  const qc = useQueryClient();
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: qk.cadence(clientFileId) });
  return {
    pause: useMutation({
      mutationFn: (sequenceId: string) => cadenceApi.pause(sequenceId),
      onSuccess: invalidate,
    }),
    resume: useMutation({
      mutationFn: (sequenceId: string) => cadenceApi.resume(sequenceId),
      onSuccess: invalidate,
    }),
    cancel: useMutation({
      mutationFn: ({ sequenceId, reason }: { sequenceId: string; reason?: string }) =>
        cadenceApi.cancel(sequenceId, reason),
      onSuccess: invalidate,
    }),
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Relationships + action plans
// ─────────────────────────────────────────────────────────────────────────

export function useRelationships(clientFileId: string) {
  return useQuery({
    queryKey: qk.relationships(clientFileId),
    queryFn: () => relationshipApi.list(clientFileId),
  });
}

export function useActionPlanRuns(clientFileId: string) {
  return useQuery({
    queryKey: qk.actionPlans(clientFileId),
    queryFn: () => actionPlanApi.listRuns(clientFileId),
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Team chat
// ─────────────────────────────────────────────────────────────────────────

export function useTeamChatMessages(clientFileId: string, enabled = true) {
  return useQuery({
    queryKey: qk.teamChatMessages(clientFileId),
    queryFn: () => teamChatApi.listMessages(clientFileId),
    enabled,
    refetchInterval: enabled ? 5_000 : false, // poll while pane is open
  });
}

export function useTeamChatPinned(clientFileId: string) {
  return useQuery({
    queryKey: qk.teamChatPinned(clientFileId),
    queryFn: () => teamChatApi.getPinned(clientFileId),
  });
}

export function useTeamChatMembers(clientFileId: string) {
  return useQuery({
    queryKey: qk.teamChatMembers(clientFileId),
    queryFn: () => teamChatApi.members(clientFileId),
  });
}

export function useTeamChatUnread(clientFileId: string) {
  return useQuery({
    queryKey: qk.teamChatUnread(clientFileId),
    queryFn: () => teamChatApi.unreadCount(clientFileId),
    refetchInterval: 15_000,
  });
}

export function useTeamChatTyping(clientFileId: string, enabled = true) {
  return useQuery({
    queryKey: qk.teamChatTyping(clientFileId),
    queryFn: () => teamChatApi.getTyping(clientFileId),
    enabled,
    refetchInterval: enabled ? 3_000 : false,
  });
}

export function useTeamChatActions(clientFileId: string) {
  const qc = useQueryClient();
  const invalidateMessages = () =>
    qc.invalidateQueries({ queryKey: qk.teamChatMessages(clientFileId) });
  const invalidatePinned = () =>
    qc.invalidateQueries({ queryKey: qk.teamChatPinned(clientFileId) });
  const invalidateUnread = () =>
    qc.invalidateQueries({ queryKey: qk.teamChatUnread(clientFileId) });

  return {
    send: useMutation({
      mutationFn: (input: Parameters<typeof teamChatApi.sendMessage>[1]) =>
        teamChatApi.sendMessage(clientFileId, input),
      onSuccess: () => {
        invalidateMessages();
        invalidateUnread();
      },
    }),
    edit: useMutation({
      mutationFn: ({ messageId, body }: { messageId: string; body: string }) =>
        teamChatApi.editMessage(clientFileId, messageId, body),
      onSuccess: invalidateMessages,
    }),
    delete: useMutation({
      mutationFn: (messageId: string) =>
        teamChatApi.deleteMessage(clientFileId, messageId),
      onSuccess: invalidateMessages,
    }),
    pin: useMutation({
      mutationFn: (messageId: string) =>
        teamChatApi.pin(clientFileId, messageId),
      onSuccess: () => {
        invalidateMessages();
        invalidatePinned();
      },
    }),
    unpin: useMutation({
      mutationFn: (messageId: string) =>
        teamChatApi.unpin(clientFileId, messageId),
      onSuccess: () => {
        invalidateMessages();
        invalidatePinned();
      },
    }),
    react: useMutation({
      mutationFn: ({ messageId, emoji }: {
        messageId: string;
        emoji: TeamChatReactionEmoji;
      }) => teamChatApi.react(clientFileId, messageId, emoji),
      onSuccess: invalidateMessages,
    }),
    unreact: useMutation({
      mutationFn: ({ messageId, emoji }: {
        messageId: string;
        emoji: TeamChatReactionEmoji;
      }) => teamChatApi.unreact(clientFileId, messageId, emoji),
      onSuccess: invalidateMessages,
    }),
    markRead: useMutation({
      mutationFn: (lastReadMessageId: string) =>
        teamChatApi.markRead(clientFileId, lastReadMessageId),
      onSuccess: invalidateUnread,
    }),
    setTyping: useMutation({
      mutationFn: () => teamChatApi.setTyping(clientFileId),
    }),
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Helper: derive the unread badge count, used by the tab strip
// ─────────────────────────────────────────────────────────────────────────

export function useTeamChatBadge(clientFileId: string) {
  const { data } = useTeamChatUnread(clientFileId);
  return {
    unread: data?.unread ?? 0,
    mentions: data?.mentions ?? 0,
    show: (data?.unread ?? 0) > 0 || (data?.mentions ?? 0) > 0,
  };
}
