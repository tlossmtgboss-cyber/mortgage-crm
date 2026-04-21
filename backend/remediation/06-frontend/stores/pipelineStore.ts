/**
 * 06-frontend/stores/pipelineStore.ts
 *
 * Pipeline state. Replaces PipelineContext. Uses React Query for server state
 * (loans list, loan details) and Zustand only for UI state (active view,
 * filters, selection, drag state).
 *
 * Drop-in: frontend/src/stores/pipelineStore.ts
 */

import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { persist } from "zustand/middleware";

export type PipelineView = "kanban" | "table" | "forecast" | "calendar";
export type LoanStage =
  | "lead"
  | "prequalified"
  | "application"
  | "processing"
  | "underwriting"
  | "approved"
  | "clear_to_close"
  | "closed"
  | "funded"
  | "declined"
  | "withdrawn";

export interface PipelineFilters {
  stages: LoanStage[];
  assignedTo: string[] | null;   // user ids, null = everyone
  tags: string[];
  priority: ("high" | "normal" | "low")[];
  searchQuery: string;
  dateRange: { from: string | null; to: string | null };
}

interface PipelineState {
  view: PipelineView;
  filters: PipelineFilters;
  selectedLoanIds: Set<string>;
  draggedLoanId: string | null;
  columnOrder: LoanStage[];

  setView: (view: PipelineView) => void;
  setFilter: <K extends keyof PipelineFilters>(key: K, value: PipelineFilters[K]) => void;
  resetFilters: () => void;
  toggleSelection: (loanId: string) => void;
  clearSelection: () => void;
  setDraggedLoan: (loanId: string | null) => void;
  reorderColumns: (order: LoanStage[]) => void;
}

const DEFAULT_FILTERS: PipelineFilters = {
  stages: [],
  assignedTo: null,
  tags: [],
  priority: [],
  searchQuery: "",
  dateRange: { from: null, to: null },
};

const DEFAULT_COLUMN_ORDER: LoanStage[] = [
  "lead",
  "prequalified",
  "application",
  "processing",
  "underwriting",
  "approved",
  "clear_to_close",
  "closed",
  "funded",
];

export const usePipelineStore = create<PipelineState>()(
  persist(
    immer((set) => ({
      view: "kanban",
      filters: DEFAULT_FILTERS,
      selectedLoanIds: new Set(),
      draggedLoanId: null,
      columnOrder: DEFAULT_COLUMN_ORDER,

      setView: (view) =>
        set((s) => {
          s.view = view;
        }),

      setFilter: (key, value) =>
        set((s) => {
          s.filters[key] = value as never;
        }),

      resetFilters: () =>
        set((s) => {
          s.filters = DEFAULT_FILTERS;
        }),

      toggleSelection: (loanId) =>
        set((s) => {
          if (s.selectedLoanIds.has(loanId)) {
            s.selectedLoanIds.delete(loanId);
          } else {
            s.selectedLoanIds.add(loanId);
          }
        }),

      clearSelection: () =>
        set((s) => {
          s.selectedLoanIds.clear();
        }),

      setDraggedLoan: (loanId) =>
        set((s) => {
          s.draggedLoanId = loanId;
        }),

      reorderColumns: (order) =>
        set((s) => {
          s.columnOrder = order;
        }),
    })),
    {
      name: "perennia-pipeline-ui",
      // Only persist user preferences, not transient state
      partialize: (s) => ({
        view: s.view,
        columnOrder: s.columnOrder,
      }),
    },
  ),
);
