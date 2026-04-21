/**
 * 06-frontend/stores/authStore.ts
 *
 * Auth state store. NOTE: this only stores user profile data — the actual
 * auth token lives in httpOnly cookies and is invisible to JS. That's the point.
 *
 * Drop-in: frontend/src/stores/authStore.ts
 */

import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import { immer } from "zustand/middleware/immer";

import { authFetch, login as apiLogin, logout as apiLogout, onAuthEvent } from "@/lib/auth/authClient";

export type UserRole =
  | "super_admin"
  | "admin"
  | "loan_officer"
  | "processor"
  | "underwriter"
  | "closer"
  | "borrower"
  | "account_executive";

export interface AuthUser {
  id: string;
  email: string;
  role: UserRole;
  org_id: string;
  full_name: string;
  avatar_url: string | null;
  mfa_enabled: boolean;
}

interface AuthState {
  user: AuthUser | null;
  status: "unknown" | "checking" | "authenticated" | "unauthenticated";
  error: string | null;

  // Actions
  initialize: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  subscribeWithSelector(
    immer((set, get) => ({
      user: null,
      status: "unknown",
      error: null,

      async initialize() {
        set((s) => {
          s.status = "checking";
          s.error = null;
        });
        try {
          const res = await authFetch("/me");
          if (!res.ok) {
            set((s) => {
              s.status = "unauthenticated";
              s.user = null;
            });
            return;
          }
          const user = (await res.json()) as AuthUser;
          set((s) => {
            s.user = user;
            s.status = "authenticated";
          });
        } catch {
          set((s) => {
            s.status = "unauthenticated";
            s.user = null;
          });
        }
      },

      async login(email, password) {
        set((s) => {
          s.error = null;
        });
        try {
          await apiLogin(email, password);
          // Load full profile
          await get().refreshProfile();
        } catch (err) {
          const message = err instanceof Error ? err.message : "login_failed";
          set((s) => {
            s.error = message;
            s.status = "unauthenticated";
            s.user = null;
          });
          throw err;
        }
      },

      async logout() {
        try {
          await apiLogout();
        } finally {
          set((s) => {
            s.user = null;
            s.status = "unauthenticated";
          });
        }
      },

      async refreshProfile() {
        const res = await authFetch("/me");
        if (!res.ok) {
          set((s) => {
            s.status = "unauthenticated";
            s.user = null;
          });
          return;
        }
        const user = (await res.json()) as AuthUser;
        set((s) => {
          s.user = user;
          s.status = "authenticated";
        });
      },
    })),
  ),
);

// Cross-tab sync: if another tab logs out, this tab drops its user
onAuthEvent((ev) => {
  if (ev.type === "logout") {
    useAuthStore.setState({ user: null, status: "unauthenticated" });
  } else if (ev.type === "login") {
    useAuthStore.getState().refreshProfile();
  }
});

// Selectors — subscribe narrowly to avoid unnecessary re-renders
export const useCurrentUser = () => useAuthStore((s) => s.user);
export const useAuthStatus = () => useAuthStore((s) => s.status);
export const useHasRole = (...roles: UserRole[]) =>
  useAuthStore((s) => (s.user ? roles.includes(s.user.role) : false));
