/**
 * 06-frontend/routes/manifest.tsx
 *
 * Declarative route manifest. Every route lazy-imports its feature module.
 * Adding a route is a one-liner — no more editing a 4,843-line App.jsx.
 *
 * Drop-in: frontend/src/routes/manifest.tsx
 */

import { lazy, ComponentType } from "react";
import type { UserRole } from "@/stores/authStore";

interface RouteDef {
  path: string;
  Component: ComponentType;
  roles?: UserRole[]; // undefined = any authenticated role
}

// --- Public routes (no auth required) ---------------------------------------

const LoginPage = lazy(() => import("@/features/auth/LoginPage"));
const ForgotPasswordPage = lazy(() => import("@/features/auth/ForgotPasswordPage"));
const ResetPasswordPage = lazy(() => import("@/features/auth/ResetPasswordPage"));
const BorrowerPortalLandingPage = lazy(
  () => import("@/features/borrower-portal/LandingPage"),
);

// --- Authenticated routes ---------------------------------------------------

// Main
const DashboardPage = lazy(() => import("@/features/dashboard/DashboardPage"));
const ProfilePage = lazy(() => import("@/features/profile/ProfilePage"));

// Pipeline (chunk: app-pipeline)
const PipelinePage = lazy(() => import("@/features/pipeline/PipelinePage"));
const LoanDetailPage = lazy(() => import("@/features/pipeline/LoanDetailPage"));

// AI / Aria (chunk: app-ai)
const AriaPage = lazy(() => import("@/features/ai/AriaPage"));
const AgentsPage = lazy(() => import("@/features/ai/AgentsPage"));

// Voice / call intelligence (chunk: app-voice)
const VoicePage = lazy(() => import("@/features/voice/VoicePage"));
const CallIntelligencePage = lazy(
  () => import("@/features/call-intelligence/CallIntelligencePage"),
);

// Borrower portal (chunk: app-borrower)
const BorrowerDashboardPage = lazy(
  () => import("@/features/borrower-portal/DashboardPage"),
);
const BorrowerDocumentsPage = lazy(
  () => import("@/features/borrower-portal/DocumentsPage"),
);

// Admin (chunk: app-admin)
const SettingsPage = lazy(() => import("@/features/admin/SettingsPage"));
const UsersPage = lazy(() => import("@/features/admin/UsersPage"));
const IntegrationsPage = lazy(() => import("@/features/admin/IntegrationsPage"));
const AuditLogPage = lazy(() => import("@/features/admin/AuditLogPage"));

// Docs / guidelines (chunk: app-docs)
const DocumentsPage = lazy(() => import("@/features/documents/DocumentsPage"));
const GuidelinesPage = lazy(() => import("@/features/guidelines/GuidelinesPage"));
const GuidelineComparatorPage = lazy(
  () => import("@/features/guidelines/GuidelineComparatorPage"),
);

// ---------------------------------------------------------------------------

export const routeManifest = {
  public: [
    { path: "/login", Component: LoginPage },
    { path: "/forgot-password", Component: ForgotPasswordPage },
    { path: "/reset-password", Component: ResetPasswordPage },
    { path: "/portal", Component: BorrowerPortalLandingPage },
  ] satisfies RouteDef[],

  authenticated: [
    // Main
    { path: "/", Component: DashboardPage },
    { path: "/profile", Component: ProfilePage },

    // Pipeline
    {
      path: "/pipeline",
      Component: PipelinePage,
      roles: ["admin", "loan_officer", "processor", "underwriter", "closer"],
    },
    {
      path: "/pipeline/:loanId",
      Component: LoanDetailPage,
      roles: ["admin", "loan_officer", "processor", "underwriter", "closer"],
    },

    // AI
    {
      path: "/aria",
      Component: AriaPage,
      roles: ["admin", "loan_officer", "processor"],
    },
    {
      path: "/agents",
      Component: AgentsPage,
      roles: ["admin", "super_admin"],
    },

    // Voice
    {
      path: "/voice",
      Component: VoicePage,
      roles: ["admin", "loan_officer", "account_executive"],
    },
    {
      path: "/call-intelligence",
      Component: CallIntelligencePage,
      roles: ["admin", "loan_officer", "underwriter"],
    },

    // Borrower portal
    {
      path: "/borrower",
      Component: BorrowerDashboardPage,
      roles: ["borrower"],
    },
    {
      path: "/borrower/documents",
      Component: BorrowerDocumentsPage,
      roles: ["borrower"],
    },

    // Admin
    {
      path: "/settings/*",
      Component: SettingsPage,
      roles: ["admin", "super_admin"],
    },
    {
      path: "/users",
      Component: UsersPage,
      roles: ["admin", "super_admin"],
    },
    {
      path: "/integrations",
      Component: IntegrationsPage,
      roles: ["admin", "super_admin"],
    },
    {
      path: "/audit",
      Component: AuditLogPage,
      roles: ["admin", "super_admin"],
    },

    // Docs
    { path: "/documents", Component: DocumentsPage },
    {
      path: "/guidelines",
      Component: GuidelinesPage,
      roles: ["admin", "loan_officer", "underwriter"],
    },
    {
      path: "/guidelines/compare",
      Component: GuidelineComparatorPage,
      roles: ["admin", "loan_officer", "underwriter"],
    },
  ] satisfies RouteDef[],
};
