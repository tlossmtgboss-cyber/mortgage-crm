/**
 * 06-frontend/stores/notificationsStore.ts
 *
 * In-app notifications + toast queue. Replaces NotificationsContext.
 *
 * Drop-in: frontend/src/stores/notificationsStore.ts
 */

import { create } from "zustand";
import { immer } from "zustand/middleware/immer";

export type NotificationSeverity = "info" | "success" | "warning" | "error";

export interface Notification {
  id: string;
  severity: NotificationSeverity;
  title: string;
  body?: string;
  actionLabel?: string;
  actionHref?: string;
  createdAt: number;
  readAt: number | null;
}

interface NotificationsState {
  items: Notification[];
  unreadCount: number;

  add: (n: Omit<Notification, "id" | "createdAt" | "readAt">) => void;
  markRead: (id: string) => void;
  markAllRead: () => void;
  remove: (id: string) => void;
  clear: () => void;

  // Server-pushed
  hydrate: (items: Notification[]) => void;
}

export const useNotificationsStore = create<NotificationsState>()(
  immer((set) => ({
    items: [],
    unreadCount: 0,

    add: (n) =>
      set((s) => {
        s.items.unshift({
          ...n,
          id: crypto.randomUUID(),
          createdAt: Date.now(),
          readAt: null,
        });
        s.unreadCount += 1;
      }),

    markRead: (id) =>
      set((s) => {
        const item = s.items.find((x) => x.id === id);
        if (item && !item.readAt) {
          item.readAt = Date.now();
          s.unreadCount = Math.max(0, s.unreadCount - 1);
        }
      }),

    markAllRead: () =>
      set((s) => {
        const now = Date.now();
        for (const item of s.items) {
          if (!item.readAt) item.readAt = now;
        }
        s.unreadCount = 0;
      }),

    remove: (id) =>
      set((s) => {
        const idx = s.items.findIndex((x) => x.id === id);
        if (idx >= 0) {
          if (!s.items[idx].readAt) s.unreadCount = Math.max(0, s.unreadCount - 1);
          s.items.splice(idx, 1);
        }
      }),

    clear: () =>
      set((s) => {
        s.items = [];
        s.unreadCount = 0;
      }),

    hydrate: (items) =>
      set((s) => {
        s.items = items;
        s.unreadCount = items.filter((x) => !x.readAt).length;
      }),
  })),
);
