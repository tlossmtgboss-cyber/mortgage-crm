/**
 * 06-frontend/stores/uiStore.ts
 *
 * App-wide UI state: sidebar, theme, command palette, global modals.
 * Replaces UIContext and scattered useState in App.jsx.
 *
 * Drop-in: frontend/src/stores/uiStore.ts
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { immer } from "zustand/middleware/immer";

export type Theme = "system" | "light" | "dark";

type ModalId = "command-palette" | "quick-action" | "aria-panel" | null;

interface UIState {
  sidebarCollapsed: boolean;
  theme: Theme;
  density: "comfortable" | "compact";
  openModal: ModalId;

  toggleSidebar: () => void;
  setSidebarCollapsed: (v: boolean) => void;
  setTheme: (t: Theme) => void;
  setDensity: (d: "comfortable" | "compact") => void;
  openModalById: (id: ModalId) => void;
  closeModal: () => void;
}

export const useUIStore = create<UIState>()(
  persist(
    immer((set) => ({
      sidebarCollapsed: false,
      theme: "system",
      density: "comfortable",
      openModal: null,

      toggleSidebar: () =>
        set((s) => {
          s.sidebarCollapsed = !s.sidebarCollapsed;
        }),
      setSidebarCollapsed: (v) =>
        set((s) => {
          s.sidebarCollapsed = v;
        }),
      setTheme: (t) =>
        set((s) => {
          s.theme = t;
        }),
      setDensity: (d) =>
        set((s) => {
          s.density = d;
        }),
      openModalById: (id) =>
        set((s) => {
          s.openModal = id;
        }),
      closeModal: () =>
        set((s) => {
          s.openModal = null;
        }),
    })),
    {
      name: "perennia-ui",
      partialize: (s) => ({
        sidebarCollapsed: s.sidebarCollapsed,
        theme: s.theme,
        density: s.density,
      }),
    },
  ),
);
