/**
 * useNotifications Hook
 *
 * React Query-powered hook for notification data management.
 * Fetches from /api/v1/notifications, provides mutation functions
 * for mark-as-read, mark-all-read, and dismiss operations.
 * Auto-refreshes every 30 seconds when the app is active.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';
import api from '../services/api';

// ============================================================================
// Query keys
// ============================================================================

const NOTIFICATIONS_KEY = ['notifications'];
const UNREAD_COUNT_KEY = ['notifications', 'unreadCount'];

// ============================================================================
// Fetch functions
// ============================================================================

async function fetchNotifications({ filter = 'all' } = {}) {
  const params = { limit: '100' };
  if (filter === 'unread') {
    params.unread_only = 'true';
  }
  const response = await api.get('/api/v1/notifications', { params });
  const data = response.data;

  // Normalise response: backend may return { notifications: [...], unread_count }
  // or a plain array
  const notifications = Array.isArray(data)
    ? data
    : Array.isArray(data.notifications)
      ? data.notifications
      : [];

  const unreadCount =
    typeof data.unread_count === 'number'
      ? data.unread_count
      : notifications.filter((n) => !n.is_read).length;

  return { notifications, unreadCount };
}

// ============================================================================
// Hook
// ============================================================================

const AUTO_REFRESH_MS = 30_000; // 30 seconds

export function useNotifications(filter = 'all') {
  const queryClient = useQueryClient();
  const visibleRef = useRef(true);

  // --- Main query --------------------------------------------------------
  const {
    data,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: [...NOTIFICATIONS_KEY, filter],
    queryFn: () => fetchNotifications({ filter }),
    staleTime: 1000 * 15, // 15 seconds
    gcTime: 1000 * 60 * 10, // 10 minutes cache
    refetchOnWindowFocus: true,
  });

  const notifications = data?.notifications ?? [];
  const unreadCount = data?.unreadCount ?? 0;

  // --- Auto-refresh when app is active ------------------------------------
  useEffect(() => {
    const handleVisibility = () => {
      visibleRef.current = document.visibilityState === 'visible';
      // Refetch immediately when returning to the app
      if (visibleRef.current) {
        refetch();
      }
    };

    document.addEventListener('visibilitychange', handleVisibility);

    const interval = setInterval(() => {
      if (visibleRef.current) {
        refetch();
      }
    }, AUTO_REFRESH_MS);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      clearInterval(interval);
    };
  }, [refetch]);

  // --- Mutations ----------------------------------------------------------

  const markAsReadMutation = useMutation({
    mutationFn: (notificationId) =>
      api.put(`/api/v1/notifications/${notificationId}/read`).then((r) => r.data),
    onMutate: async (notificationId) => {
      await queryClient.cancelQueries({ queryKey: NOTIFICATIONS_KEY });
      const previousData = queryClient.getQueryData([...NOTIFICATIONS_KEY, filter]);

      // Optimistic update
      queryClient.setQueryData([...NOTIFICATIONS_KEY, filter], (old) => {
        if (!old) return old;
        const updated = old.notifications.map((n) =>
          n.id === notificationId ? { ...n, is_read: true } : n,
        );
        return {
          notifications: updated,
          unreadCount: Math.max(0, old.unreadCount - 1),
        };
      });

      return { previousData };
    },
    onError: (_err, _id, context) => {
      if (context?.previousData) {
        queryClient.setQueryData([...NOTIFICATIONS_KEY, filter], context.previousData);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    },
  });

  const markAllReadMutation = useMutation({
    mutationFn: () => api.put('/api/v1/notifications/read-all').then((r) => r.data),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: NOTIFICATIONS_KEY });
      const previousData = queryClient.getQueryData([...NOTIFICATIONS_KEY, filter]);

      queryClient.setQueryData([...NOTIFICATIONS_KEY, filter], (old) => {
        if (!old) return old;
        return {
          notifications: old.notifications.map((n) => ({ ...n, is_read: true })),
          unreadCount: 0,
        };
      });

      return { previousData };
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        queryClient.setQueryData([...NOTIFICATIONS_KEY, filter], context.previousData);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    },
  });

  const dismissMutation = useMutation({
    mutationFn: (notificationId) =>
      api.delete(`/api/v1/notifications/${notificationId}`).then((r) => r.data),
    onMutate: async (notificationId) => {
      await queryClient.cancelQueries({ queryKey: NOTIFICATIONS_KEY });
      const previousData = queryClient.getQueryData([...NOTIFICATIONS_KEY, filter]);

      queryClient.setQueryData([...NOTIFICATIONS_KEY, filter], (old) => {
        if (!old) return old;
        const target = old.notifications.find((n) => n.id === notificationId);
        const wasUnread = target && !target.is_read;
        return {
          notifications: old.notifications.filter((n) => n.id !== notificationId),
          unreadCount: wasUnread ? Math.max(0, old.unreadCount - 1) : old.unreadCount,
        };
      });

      return { previousData };
    },
    onError: (_err, _id, context) => {
      if (context?.previousData) {
        queryClient.setQueryData([...NOTIFICATIONS_KEY, filter], context.previousData);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    },
  });

  // --- Public API ---------------------------------------------------------

  const markAsRead = useCallback(
    (id) => markAsReadMutation.mutate(id),
    [markAsReadMutation],
  );

  const markAllRead = useCallback(
    () => markAllReadMutation.mutate(),
    [markAllReadMutation],
  );

  const dismiss = useCallback(
    (id) => dismissMutation.mutate(id),
    [dismissMutation],
  );

  return {
    // Data
    notifications,
    unreadCount,

    // Status
    isLoading,
    isFetching,
    isError,
    error,

    // Actions
    markAsRead,
    markAllRead,
    dismiss,
    refetch,
  };
}

export default useNotifications;
