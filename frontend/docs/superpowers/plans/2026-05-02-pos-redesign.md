# POS Visual Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle and restructure the existing `features/pos/` components to match the HTML prototype at `public/pos-redesign-prototype.html` — cream/green/gold palette, Fraunces serif headings, Geist sans body, sidebar nav, step rail in main content, and polished Aria chat.

**Architecture:** The TypeScript components in `src/features/pos/` (POSContainer, StepRail, 9 panels, AriaPanel, SmartCalendar, usePOSApplication hook, Zod schemas, API client) are production-ready but have no CSS file — they render BEM class names (`.pos-*`, `.urla-*`, `.aria-*`, `.smart-cal-*`) with zero corresponding styles. This plan creates the stylesheet, restructures the layout to match the prototype, adds TopNav and enhanced sidebar components, and wires the routes. No backend changes needed.

**Tech Stack:** React 18, TypeScript, CSS (BEM + custom properties), Google Fonts (Fraunces, Geist, Geist Mono), Vite

**Reference:** The working HTML prototype is at `frontend/public/pos-redesign-prototype.html` (2,279 lines). Open it at `http://localhost:3000/pos-redesign-prototype.html` to see the target design.

---

## File Map

### New files
| File | Responsibility |
|------|---------------|
| `src/features/pos/pos.css` | All POS styles — layout grid, step rail, form fields, buttons, Aria panel, Smart Calendar, animations, responsive breakpoints (~650 lines) |
| `src/features/pos/components/TopNav.tsx` | Header bar: Perennia logo, nav links (Dashboard, Application, Documents, Resources), save indicator, user avatar |
| `src/features/pos/components/POSSidebar.tsx` | Sidebar: loan file summary card, Ask Aria button, nav items (Home, Application, Documents, Tasks, Messages, Disclosures), tools section |

### Modified files
| File | Change |
|------|--------|
| `src/features/pos/types.ts` | Update SECTION_LABELS to full names, add SECTION_CAPTIONS |
| `src/features/pos/components/POSContainer.tsx` | New layout: TopNav above, sidebar left (POSSidebar), main with step rail + panel side-by-side, footer buttons |
| `src/features/pos/components/StepRail.tsx` | Add caption rendering, add step-marker state classes |
| `src/features/pos/components/AskAriaButton.tsx` | Align BEM class names with CSS (minor) |
| `src/styles/borrower-theme.css` | Replace design tokens with prototype palette and fonts |
| `public/index.html` | Add Google Fonts preconnect + link tags |
| `src/routes/index.jsx` | Wire `/apply/v2/purchase` to POS |

---

### Task 1: Design Tokens, Fonts, and POS Stylesheet Foundation

**Files:**
- Modify: `public/index.html`
- Modify: `src/styles/borrower-theme.css`
- Create: `src/features/pos/pos.css`
- Modify: `src/features/pos/types.ts`

This task establishes the visual foundation: font loading, CSS custom properties, and the structural layout CSS. After this task, the POS container will have the correct fonts, colors, and grid layout — even though no component changes have been made yet.

- [ ] **Step 1: Add Google Fonts to index.html**

Add the font preconnect and stylesheet links inside `<head>`, before the existing `<link>` tags:

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet" />
```

- [ ] **Step 2: Update borrower-theme.css design tokens**

Replace the `:root` variables in `src/styles/borrower-theme.css` with the prototype palette. The existing file has `--bt-` prefixed variables (e.g., `--bt-primary: #218D8D`). Replace the entire `:root` block with:

```css
:root {
  /* Typography */
  --bt-font-display: 'Fraunces', Georgia, serif;
  --bt-font-body: 'Geist', system-ui, -apple-system, sans-serif;
  --bt-font-mono: 'Geist Mono', ui-monospace, monospace;

  /* Backgrounds */
  --bt-bg-page: #FAF7F1;
  --bt-bg-surface: #FFFFFF;
  --bt-bg-sidebar: #F6F2EA;
  --bt-bg-elevated: #F2EDE2;
  --bt-bg-soft: #FBF8F2;

  /* Borders */
  --bt-border: #ECE6D8;
  --bt-border-strong: #D8D0BD;
  --bt-border-active: #1F3D2E;

  /* Text */
  --bt-text-primary: #1A1F1B;
  --bt-text-secondary: #4F554E;
  --bt-text-muted: #8B8A7E;
  --bt-text-faint: #B5B2A4;

  /* Brand */
  --bt-primary: #1F3D2E;
  --bt-primary-hover: #2A4F3D;
  --bt-primary-light: #E5EDE6;
  --bt-primary-tint: #EFF3EE;

  /* Accent */
  --bt-accent: #B8924A;
  --bt-accent-light: #F5EDD9;

  /* Semantic */
  --bt-success: #2D7A52;
  --bt-warning: #B25F18;
  --bt-error: #9B2C2C;
  --bt-info: #3182ce;

  /* Spacing */
  --bt-space-xs: 4px;
  --bt-space-sm: 8px;
  --bt-space-md: 16px;
  --bt-space-lg: 24px;
  --bt-space-xl: 32px;
  --bt-space-2xl: 48px;

  /* Radii */
  --bt-radius-sm: 6px;
  --bt-radius-md: 10px;
  --bt-radius-lg: 14px;

  /* Shadows */
  --bt-shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.04);
  --bt-shadow-md: 0 4px 12px rgba(0, 0, 0, 0.06);
  --bt-shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.08);

  /* Layout */
  --bt-max-width: 1200px;
  --bt-header-height: 60px;
  --bt-sidebar-width: 260px;
}

.borrower-theme {
  font-family: var(--bt-font-body);
  background: var(--bt-bg-page);
  color: var(--bt-text-primary);
  font-feature-settings: 'ss01', 'cv01', 'cv11';
  letter-spacing: -0.005em;
  -webkit-font-smoothing: antialiased;
}

.bt-font-display {
  font-family: var(--bt-font-display);
  font-feature-settings: 'ss01';
  letter-spacing: -0.018em;
}

.bt-font-mono {
  font-family: var(--bt-font-mono);
}
```

Keep the `.bt-card` and `.bt-btn-primary` utility classes below it — update their colors to use the new `--bt-primary` variable if they reference the old `#218D8D`.

- [ ] **Step 3: Update SECTION_LABELS and add SECTION_CAPTIONS in types.ts**

In `src/features/pos/types.ts`, replace `SECTION_LABELS` with full-length names matching the prototype, and add `SECTION_CAPTIONS`:

```typescript
export const SECTION_LABELS: Record<SectionKey, string> = {
  personal: 'Personal Information',
  residence: 'Address & Contact',
  employment: 'Employment & Income',
  assets: 'Assets',
  liabilities: 'Liabilities',
  reo: 'Real Estate Owned',
  loan: 'Loan & Property',
  declarations: 'Declarations',
  review: 'Review & eSign',
};

export const SECTION_CAPTIONS: Record<SectionKey, string> = {
  personal: 'Legal name, date of birth, ID',
  residence: 'Where you live and how to reach you',
  employment: 'Current job, prior history, other income',
  assets: 'Bank, retirement, gifts and credits',
  liabilities: 'Credit cards, loans, monthly obligations',
  reo: 'Properties you currently own',
  loan: 'Subject property and loan details',
  declarations: 'Disclosure questions and HMDA',
  review: 'Final review and submission',
};
```

- [ ] **Step 4: Create pos.css — Layout, global, and utility styles**

Create `src/features/pos/pos.css` with the layout foundation. This is the first part of the stylesheet — later tasks will append form, Aria, and calendar styles.

```css
/* ===================================================================
   PERENNIA POS — Master Stylesheet
   Covers: layout, step rail, form fields, buttons, Aria panel,
   Smart Calendar, animations, responsive breakpoints.
   =================================================================== */

/* ---------- Layout ---------- */

.pos-page {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--bt-bg-page);
  font-family: var(--bt-font-body);
  color: var(--bt-text-primary);
  -webkit-font-smoothing: antialiased;
  font-feature-settings: 'ss01', 'cv01', 'cv11';
  letter-spacing: -0.005em;
}

.pos-topnav {
  position: relative;
  z-index: 10;
  background: var(--bt-bg-sidebar);
  border-bottom: 1px solid var(--bt-border);
  height: var(--bt-header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
}

.pos-topnav__left {
  display: flex;
  align-items: center;
  gap: 32px;
}

.pos-topnav__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
}

.pos-topnav__brand-name {
  font-family: var(--bt-font-display);
  font-size: 20px;
  font-weight: 500;
  letter-spacing: -0.02em;
  color: var(--bt-text-primary);
}

.pos-topnav__links {
  display: flex;
  align-items: center;
  gap: 4px;
}

.pos-topnav__link {
  font-size: 13px;
  color: var(--bt-text-secondary);
  font-weight: 500;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  background: none;
  border: none;
  font-family: inherit;
  transition: background 0.12s, color 0.12s;
}

.pos-topnav__link:hover {
  background: var(--bt-bg-elevated);
  color: var(--bt-text-primary);
}

.pos-topnav__link--active {
  color: var(--bt-text-primary);
  background: var(--bt-bg-elevated);
}

.pos-topnav__right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pos-topnav__save-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--bt-font-mono);
  font-size: 12px;
  color: var(--bt-text-secondary);
}

.pos-topnav__save-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bt-success);
}

.pos-topnav__exit-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 8px;
  font-weight: 500;
  font-size: 13px;
  background: transparent;
  color: var(--bt-text-secondary);
  border: none;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.12s;
}

.pos-topnav__exit-btn:hover {
  background: var(--bt-bg-elevated);
  color: var(--bt-text-primary);
}

.pos-body {
  position: relative;
  z-index: 1;
  display: flex;
  flex: 1;
  min-height: calc(100vh - var(--bt-header-height));
}

/* ---------- Sidebar ---------- */

.pos-sidebar {
  width: var(--bt-sidebar-width);
  flex-shrink: 0;
  background: var(--bt-bg-sidebar);
  border-right: 1px solid var(--bt-border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.pos-sidebar__content {
  padding: 16px;
  flex: 1;
}

/* Loan file summary card */
.pos-loan-card {
  background: var(--bt-bg-surface);
  border: 1px solid var(--bt-border);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 20px;
}

.pos-loan-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.pos-loan-card__label {
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--bt-text-muted);
}

.pos-loan-card__title {
  font-family: var(--bt-font-display);
  font-size: 17px;
  font-weight: 500;
  line-height: 1.3;
  margin-bottom: 2px;
}

.pos-loan-card__id {
  font-family: var(--bt-font-mono);
  font-size: 11px;
  color: var(--bt-text-muted);
}

.pos-loan-card__progress {
  margin-top: 12px;
}

.pos-loan-card__progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.pos-loan-card__progress-label {
  font-size: 13px;
  font-weight: 500;
}

.pos-loan-card__progress-pct {
  font-family: var(--bt-font-mono);
  font-size: 11px;
  color: var(--bt-text-secondary);
}

/* Sidebar navigation */
.pos-nav {
  margin-top: 8px;
}

.pos-nav__section-title {
  font-size: 10.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--bt-text-muted);
  padding: 16px 12px 6px;
}

.pos-nav__item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border-radius: 8px;
  color: var(--bt-text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  position: relative;
  background: none;
  border: none;
  width: 100%;
  text-align: left;
  font-family: inherit;
}

.pos-nav__item:hover {
  background: rgba(31, 61, 46, 0.06);
  color: var(--bt-text-primary);
}

.pos-nav__item--active {
  background: var(--bt-primary);
  color: #F5F2E9;
}

.pos-nav__item--active .pos-nav__icon {
  color: #F5F2E9;
}

.pos-nav__icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  color: var(--bt-text-muted);
}

.pos-nav__item:hover .pos-nav__icon {
  color: var(--bt-text-primary);
}

.pos-nav__badge {
  margin-left: auto;
  min-width: 18px;
  height: 18px;
  border-radius: 9px;
  background: var(--bt-primary);
  color: #F5F2E9;
  font-size: 10.5px;
  font-weight: 600;
  display: grid;
  place-items: center;
  padding: 0 5px;
}

.pos-nav__dot {
  margin-left: auto;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bt-accent);
}

/* ---------- Main content ---------- */

.pos-main {
  flex: 1;
  min-width: 0;
  padding: 40px;
  overflow-y: auto;
}

.pos-main__welcome {
  margin-bottom: 32px;
}

.pos-main__urla-badge {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.pos-main__urla-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  background: var(--bt-primary-tint);
  color: var(--bt-primary);
  border: 1px solid var(--bt-primary-light);
}

.pos-main__time-estimate {
  font-size: 13px;
  color: var(--bt-text-muted);
}

.pos-main__heading {
  font-family: var(--bt-font-display);
  font-size: 38px;
  font-weight: 400;
  line-height: 1.15;
  letter-spacing: -0.025em;
  color: var(--bt-text-primary);
  margin-bottom: 8px;
}

.pos-main__subheading {
  font-size: 15.5px;
  color: var(--bt-text-secondary);
  line-height: 1.5;
  max-width: 600px;
}

/* Step rail + panel grid */
.pos-main__grid {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 28px;
  align-items: start;
}

/* Footer */
.pos-main__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 32px;
  border-top: 1px solid var(--bt-border);
  margin-top: 24px;
  background: var(--bt-bg-surface);
  border-radius: 0 0 16px 16px;
}

.pos-main__footer-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Trust badge */
.pos-main__trust {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px 0;
  margin-top: 16px;
  font-size: 12px;
  color: var(--bt-text-muted);
}

/* ---------- Step Rail ---------- */

.pos-step-rail {
  background: var(--bt-bg-soft);
  border: 1px solid var(--bt-border);
  border-radius: 16px;
  padding: 12px;
  list-style: none;
  margin: 0;
}

.pos-step-rail__item {
  list-style: none;
}

.pos-step-rail__btn {
  display: grid;
  grid-template-columns: 36px 1fr;
  gap: 14px;
  align-items: center;
  padding: 12px 14px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s;
  width: 100%;
  background: none;
  border: none;
  text-align: left;
  font-family: inherit;
  color: inherit;
}

.pos-step-rail__btn:hover:not(:disabled) {
  background: var(--bt-bg-elevated);
}

.pos-step-rail__btn:disabled {
  cursor: default;
}

.pos-step-rail__item--is-active .pos-step-rail__btn {
  background: var(--bt-primary-light);
}

/* Step marker circle */
.pos-step-rail__index {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-weight: 600;
  font-size: 14px;
  transition: all 0.2s;
}

.pos-step-rail__item--is-pending .pos-step-rail__index {
  background: var(--bt-bg-elevated);
  color: var(--bt-text-muted);
  border: 1px solid var(--bt-border-strong);
}

.pos-step-rail__item--is-available .pos-step-rail__index {
  background: var(--bt-bg-elevated);
  color: var(--bt-text-muted);
  border: 1px solid var(--bt-border-strong);
}

.pos-step-rail__item--is-active .pos-step-rail__index {
  background: var(--bt-accent-light);
  color: #6B4F1A;
  border: 1px solid var(--bt-accent);
  font-family: var(--bt-font-display);
}

.pos-step-rail__item--is-complete .pos-step-rail__index {
  background: var(--bt-primary);
  color: white;
  border: none;
}

/* Step labels */
.pos-step-rail__label-wrap {
  min-width: 0;
}

.pos-step-rail__label {
  display: block;
  font-size: 14.5px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--bt-text-primary);
}

.pos-step-rail__item--is-pending .pos-step-rail__label {
  color: var(--bt-text-muted);
}

.pos-step-rail__caption {
  display: block;
  font-size: 12px;
  margin-top: 2px;
  color: var(--bt-text-secondary);
}

.pos-step-rail__item--is-pending .pos-step-rail__caption {
  color: var(--bt-text-faint);
}

/* ---------- Panel (active step form area) ---------- */

.pos-main__panel {
  animation: pos-fadeUp 0.35s cubic-bezier(0.2, 0.7, 0.2, 1);
}

@keyframes pos-fadeUp {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: none; }
}

.pos-main__step-header {
  margin-bottom: 24px;
}

.pos-main__step-counter {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--bt-text-muted);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.pos-main__step-urla {
  font-size: 11px;
  color: var(--bt-text-faint);
}

.pos-main__step-title {
  font-family: var(--bt-font-display);
  font-size: 26px;
  font-weight: 500;
  margin-top: 6px;
  letter-spacing: -0.015em;
}

/* ---------- Buttons ---------- */

.pos-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 22px;
  border-radius: 8px;
  font-weight: 500;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
  font-family: inherit;
}

.pos-btn--primary {
  background: var(--bt-primary);
  color: #F5F2E9;
}

.pos-btn--primary:hover {
  background: var(--bt-primary-hover);
}

.pos-btn--secondary {
  background: transparent;
  color: var(--bt-text-primary);
  border-color: var(--bt-border-strong);
}

.pos-btn--secondary:hover {
  background: var(--bt-bg-elevated);
}

.pos-btn--ghost {
  background: transparent;
  color: var(--bt-text-secondary);
  border: none;
}

.pos-btn--ghost:hover {
  color: var(--bt-text-primary);
}

/* ---------- Progress bar ---------- */

.pos-progress-track {
  height: 4px;
  background: var(--bt-bg-elevated);
  border-radius: 999px;
  overflow: hidden;
}

.pos-progress-fill {
  height: 100%;
  background: var(--bt-primary);
  border-radius: 999px;
  transition: width 0.4s cubic-bezier(0.2, 0.7, 0.2, 1);
}

/* ---------- Decorative seal ---------- */

.pos-seal {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, #2E5740, #1F3D2E 60%, #14291F);
  display: grid;
  place-items: center;
  color: #E8DDC0;
  font-family: var(--bt-font-display);
  font-weight: 600;
  font-size: 18px;
  box-shadow: inset 0 0 0 2px rgba(232, 221, 192, 0.18), 0 1px 2px rgba(0, 0, 0, 0.18);
  flex-shrink: 0;
}

/* ---------- Chips ---------- */

.pos-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  background: var(--bt-primary-tint);
  color: var(--bt-primary);
  border: 1px solid var(--bt-primary-light);
}

.pos-chip--gold {
  background: var(--bt-accent-light);
  color: #6B4F1A;
  border-color: #E5D4A8;
}

.pos-chip--neutral {
  background: var(--bt-bg-elevated);
  color: var(--bt-text-secondary);
  border-color: var(--bt-border-strong);
}

/* ---------- Loading / Error ---------- */

.pos-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  gap: 16px;
  color: var(--bt-text-secondary);
  font-size: 15px;
}

.pos-loading__spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--bt-border);
  border-top-color: var(--bt-primary);
  border-radius: 50%;
  animation: pos-spin 0.8s linear infinite;
}

@keyframes pos-spin {
  to { transform: rotate(360deg); }
}

.pos-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  gap: 12px;
  text-align: center;
  padding: 40px;
}

.pos-error h2 {
  font-family: var(--bt-font-display);
  font-size: 22px;
  font-weight: 500;
}

.pos-error p {
  color: var(--bt-text-secondary);
  max-width: 400px;
}

.pos-error button {
  margin-top: 8px;
  padding: 10px 24px;
  background: var(--bt-primary);
  color: #F5F2E9;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
}

/* ---------- Save indicator ---------- */

.pos-save-indicator {
  font-family: var(--bt-font-mono);
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.pos-save-indicator--saving {
  color: var(--bt-text-muted);
}

.pos-save-indicator--saved {
  color: var(--bt-success);
}

.pos-save-indicator--saved::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bt-success);
}

.pos-save-indicator--error {
  color: var(--bt-error);
}

/* ---------- Scrollbar ---------- */

.pos-page ::-webkit-scrollbar { width: 10px; height: 10px; }
.pos-page ::-webkit-scrollbar-track { background: transparent; }
.pos-page ::-webkit-scrollbar-thumb {
  background: #DDD6C5;
  border-radius: 8px;
  border: 2px solid var(--bt-bg-page);
}
.pos-page ::-webkit-scrollbar-thumb:hover { background: #C7BFA9; }

/* ---------- Responsive ---------- */

@media (max-width: 1024px) {
  .pos-sidebar { display: none; }
  .pos-main__grid { grid-template-columns: 1fr; }
  .pos-topnav__links { display: none; }
  .pos-topnav__save-status { display: none; }
}

@media (max-width: 768px) {
  .pos-main { padding: 20px 16px; }
  .pos-main__heading { font-size: 28px; }
}
```

- [ ] **Step 5: Verify fonts load**

Run: `open http://localhost:3000/pos-redesign-prototype.html` and confirm Fraunces, Geist, and Geist Mono render correctly (compare to the prototype). The dev server should already be running on port 3000.

- [ ] **Step 6: Commit**

```bash
git add public/index.html src/styles/borrower-theme.css src/features/pos/pos.css src/features/pos/types.ts
git commit -m "feat(pos): design tokens, fonts, and POS stylesheet foundation"
```

---

### Task 2: TopNav and POSSidebar Components

**Files:**
- Create: `src/features/pos/components/TopNav.tsx`
- Create: `src/features/pos/components/POSSidebar.tsx`

These are the two new UI components that don't exist in the current POS. TopNav is the header bar with branding and save status. POSSidebar is the left sidebar with loan file card and navigation items. Both are presentational — they receive all data via props.

- [ ] **Step 1: Create TopNav.tsx**

```tsx
import React from 'react';

export interface TopNavProps {
  saveState: 'idle' | 'saving' | 'saved' | 'error';
  userInitials: string;
  onExit?: () => void;
}

export const TopNav: React.FC<TopNavProps> = ({ saveState, userInitials, onExit }) => {
  const saveMessage = {
    idle: '',
    saving: 'Saving…',
    saved: 'Saved · just now',
    error: 'Save failed',
  }[saveState];

  return (
    <header className="pos-topnav">
      <div className="pos-topnav__left">
        <span className="pos-topnav__brand">
          <PerenniaLogo />
          <span className="pos-topnav__brand-name">Perennia</span>
        </span>
        <nav className="pos-topnav__links">
          <button type="button" className="pos-topnav__link">Dashboard</button>
          <button type="button" className="pos-topnav__link pos-topnav__link--active">Application</button>
          <button type="button" className="pos-topnav__link">Documents</button>
          <button type="button" className="pos-topnav__link">Resources</button>
        </nav>
      </div>
      <div className="pos-topnav__right">
        {saveState !== 'idle' && (
          <div className="pos-topnav__save-status">
            {saveState === 'saved' && <span className="pos-topnav__save-dot" />}
            <span>{saveMessage}</span>
          </div>
        )}
        <button type="button" className="pos-topnav__exit-btn" onClick={onExit}>
          <ClockIcon />
          <span>Save &amp; exit</span>
        </button>
        <div className="pos-seal" style={{ width: 36, height: 36, fontSize: 14 }}>
          {userInitials}
        </div>
      </div>
    </header>
  );
};

const PerenniaLogo: React.FC = () => (
  <svg width="26" height="26" viewBox="0 0 32 32" fill="none" aria-hidden>
    <path d="M16 2 C 9 2 4 8 4 16 C 4 22 8 27 14 28 L 14 14 C 14 11 16 9 19 9 C 22 9 24 11 24 14 C 24 17 22 19 19 19 L 17 19 L 17 28 C 24 27 28 22 28 16 C 28 8 23 2 16 2 Z" fill="#1F3D2E" />
    <circle cx="19" cy="14" r="2.5" fill="#B8924A" />
  </svg>
);

const ClockIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M12 2a10 10 0 1 0 10 10" />
    <path d="M12 6v6l4 2" />
  </svg>
);
```

- [ ] **Step 2: Create POSSidebar.tsx**

```tsx
import React from 'react';

import type { ApplicationResponse } from '../types';
import { AskAriaButton } from './AskAriaButton';

export interface POSSidebarProps {
  application: ApplicationResponse | null;
  onAskAria: () => void;
}

export const POSSidebar: React.FC<POSSidebarProps> = ({ application, onAskAria }) => {
  const pct = application?.completion_pct ?? 0;

  return (
    <aside className="pos-sidebar">
      <div className="pos-sidebar__content">
        {/* Loan file summary card */}
        <div className="pos-loan-card">
          <div className="pos-loan-card__header">
            <span className="pos-loan-card__label">Loan File</span>
            <span className="pos-chip pos-chip--gold" style={{ fontSize: '10.5px', padding: '2px 8px' }}>
              In progress
            </span>
          </div>
          <div className="pos-loan-card__title">Purchase · Primary</div>
          <div className="pos-loan-card__id">
            {application?.id ? `PRN-${application.id.slice(0, 10).toUpperCase()}` : '—'}
          </div>
          <div className="pos-loan-card__progress">
            <div className="pos-loan-card__progress-header">
              <span className="pos-loan-card__progress-label">Application</span>
              <span className="pos-loan-card__progress-pct">{pct}%</span>
            </div>
            <div className="pos-progress-track">
              <div className="pos-progress-fill" style={{ width: `${pct}%` }} />
            </div>
          </div>
        </div>

        {/* Ask Aria CTA */}
        <div style={{ marginBottom: 20 }}>
          <AskAriaButton onClick={onAskAria} />
        </div>

        {/* Navigation */}
        <nav className="pos-nav">
          <span className="pos-nav__section-title">Your Loan</span>
          <NavItem icon={<HomeIcon />} label="Home" />
          <NavItem icon={<FormIcon />} label="Application" active />
          <NavItem icon={<UploadIcon />} label="Documents" badge={3} />
          <NavItem icon={<ChecklistIcon />} label="Tasks" count={5} />
          <NavItem icon={<ChatIcon />} label="Messages" dot />
          <NavItem icon={<BookIcon />} label="Disclosures" />

          <span className="pos-nav__section-title">Tools</span>
          <NavItem icon={<CalcIcon />} label="Calculators" />
          <NavItem icon={<TimelineIcon />} label="Loan timeline" />
          <NavItem icon={<HelpIcon />} label="Help & support" />
        </nav>
      </div>
    </aside>
  );
};

const NavItem: React.FC<{
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  badge?: number;
  count?: number;
  dot?: boolean;
}> = ({ icon, label, active, badge, count, dot }) => (
  <button
    type="button"
    className={`pos-nav__item${active ? ' pos-nav__item--active' : ''}`}
  >
    <span className="pos-nav__icon">{icon}</span>
    <span>{label}</span>
    {badge != null && <span className="pos-nav__badge">{badge}</span>}
    {count != null && <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--bt-text-muted)' }}>{count}</span>}
    {dot && <span className="pos-nav__dot" />}
  </button>
);

// ---- Icons (18×18, stroke-based) ----

const HomeIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    <polyline points="9 22 9 12 15 12 15 22" />
  </svg>
);

const FormIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="16" y1="13" x2="8" y2="13" />
    <line x1="16" y1="17" x2="8" y2="17" />
  </svg>
);

const UploadIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

const ChecklistIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M9 11l3 3L22 4" />
    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
  </svg>
);

const ChatIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);

const BookIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
  </svg>
);

const CalcIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <rect x="4" y="2" width="16" height="20" rx="2" />
    <line x1="8" y1="6" x2="16" y2="6" />
    <line x1="8" y1="10" x2="10" y2="10" /><line x1="14" y1="10" x2="16" y2="10" />
    <line x1="8" y1="14" x2="10" y2="14" /><line x1="14" y1="14" x2="16" y2="14" />
    <line x1="8" y1="18" x2="10" y2="18" /><line x1="14" y1="18" x2="16" y2="18" />
  </svg>
);

const TimelineIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

const HelpIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <circle cx="12" cy="12" r="10" />
    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);
```

- [ ] **Step 3: Commit**

```bash
git add src/features/pos/components/TopNav.tsx src/features/pos/components/POSSidebar.tsx
git commit -m "feat(pos): add TopNav and POSSidebar components"
```

---

### Task 3: StepRail Enhancement and POSContainer Restructure

**Files:**
- Modify: `src/features/pos/components/StepRail.tsx`
- Modify: `src/features/pos/components/POSContainer.tsx`
- Modify: `src/features/pos/index.ts`

The biggest structural change: POSContainer's layout changes from `[sidebar: StepRail] | [main: panel]` to `[topnav] | [sidebar: loan card + nav] | [main: welcome + [StepRail | panel] + footer]`. StepRail moves from the sidebar into a two-column grid inside the main content area.

- [ ] **Step 1: Update StepRail to render captions**

Replace the contents of `src/features/pos/components/StepRail.tsx`:

```tsx
import React from 'react';

import type { SectionKey } from '../types';

export interface StepRailProps {
  steps: SectionKey[];
  labels: Record<SectionKey, string>;
  captions: Record<SectionKey, string>;
  activeStep: SectionKey;
  completionByStep: Partial<Record<SectionKey, boolean>>;
  onStepClick: (step: SectionKey) => void;
}

export const StepRail: React.FC<StepRailProps> = ({
  steps,
  labels,
  captions,
  activeStep,
  completionByStep,
  onStepClick,
}) => {
  const activeIdx = steps.indexOf(activeStep);

  return (
    <ol className="pos-step-rail" role="list">
      {steps.map((key, idx) => {
        const isComplete = completionByStep[key] === true;
        const isActive = key === activeStep;
        const canNavigate = isComplete || isActive || idx <= activeIdx + 1;

        const stateClass = isActive
          ? 'is-active'
          : isComplete
            ? 'is-complete'
            : idx <= activeIdx
              ? 'is-available'
              : 'is-pending';

        return (
          <li
            key={key}
            className={`pos-step-rail__item pos-step-rail__item--${stateClass}`}
          >
            <button
              type="button"
              className="pos-step-rail__btn"
              onClick={() => canNavigate && onStepClick(key)}
              disabled={!canNavigate}
              aria-current={isActive ? 'step' : undefined}
            >
              <span className="pos-step-rail__index">
                {isComplete ? <CheckIcon /> : idx + 1}
              </span>
              <span className="pos-step-rail__label-wrap">
                <span className="pos-step-rail__label">{labels[key]}</span>
                <span className="pos-step-rail__caption">{captions[key]}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
};

const CheckIcon: React.FC = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
  >
    <polyline points="20 6 9 17 4 12" />
  </svg>
);
```

- [ ] **Step 2: Rewrite POSContainer with new layout**

Replace the contents of `src/features/pos/components/POSContainer.tsx`:

```tsx
import React, { useCallback, useState } from 'react';

import { usePOSApplication } from '../hooks/usePOSApplication';
import type { SectionKey } from '../types';
import { SECTION_ORDER, SECTION_LABELS, SECTION_CAPTIONS } from '../types';
import { TopNav } from './TopNav';
import { POSSidebar } from './POSSidebar';
import { StepRail } from './StepRail';
import { AskAriaButton } from './AskAriaButton';
import { AriaPanel } from './AriaPanel';

import { PersonalPanel } from './panels/PersonalPanel';
import { ResidencePanel } from './panels/ResidencePanel';
import { EmploymentPanel } from './panels/EmploymentPanel';
import { AssetsPanel } from './panels/AssetsPanel';
import { LiabilitiesPanel } from './panels/LiabilitiesPanel';
import { REOPanel } from './panels/REOPanel';
import { LoanPanel } from './panels/LoanPanel';
import { DeclarationsPanel } from './panels/DeclarationsPanel';
import { ReviewPanel } from './panels/ReviewPanel';

import '../pos.css';

export interface POSContainerProps {
  loanId?: number;
  borrowerName?: string;
  userInitials?: string;
}

const PANEL_COMPONENTS: Record<SectionKey, React.ComponentType<any>> = {
  personal: PersonalPanel,
  residence: ResidencePanel,
  employment: EmploymentPanel,
  assets: AssetsPanel,
  liabilities: LiabilitiesPanel,
  reo: REOPanel,
  loan: LoanPanel,
  declarations: DeclarationsPanel,
  review: ReviewPanel,
};

export const POSContainer: React.FC<POSContainerProps> = ({
  loanId,
  borrowerName = 'there',
  userInitials = '',
}) => {
  const {
    application,
    sections,
    loading,
    error,
    saveState,
    loadSection,
    updateSectionData,
    markComplete,
    submit,
  } = usePOSApplication(loanId);

  const [activeStep, setActiveStep] = useState<SectionKey>('personal');
  const [ariaOpen, setAriaOpen] = useState(false);

  React.useEffect(() => {
    if (application && !sections.personal) {
      setActiveStep(application.current_step);
      loadSection(application.current_step);
    }
  }, [application, sections.personal, loadSection]);

  const handleStepChange = useCallback(
    (key: SectionKey) => {
      setActiveStep(key);
      if (!sections[key]) loadSection(key);
    },
    [sections, loadSection],
  );

  const handleBack = useCallback(() => {
    const idx = SECTION_ORDER.indexOf(activeStep);
    if (idx > 0) handleStepChange(SECTION_ORDER[idx - 1]);
  }, [activeStep, handleStepChange]);

  const handleContinue = useCallback(() => {
    markComplete(activeStep).then(() => {
      const nextIdx = Math.min(
        SECTION_ORDER.indexOf(activeStep) + 1,
        SECTION_ORDER.length - 1,
      );
      handleStepChange(SECTION_ORDER[nextIdx]);
    });
  }, [activeStep, markComplete, handleStepChange]);

  if (loading) {
    return (
      <div className="pos-page">
        <div className="pos-loading">
          <div className="pos-loading__spinner" />
          <p>Loading your application…</p>
        </div>
      </div>
    );
  }

  if (error || !application) {
    return (
      <div className="pos-page">
        <div className="pos-error">
          <h2>We couldn't load your application</h2>
          <p>{error}</p>
          <button onClick={() => window.location.reload()}>Try again</button>
        </div>
      </div>
    );
  }

  const ActivePanel = PANEL_COMPONENTS[activeStep];
  const stepIdx = SECTION_ORDER.indexOf(activeStep);
  const isFirstStep = stepIdx === 0;
  const isReview = activeStep === 'review';
  const completionPct = application.completion_pct;
  const timeRemaining = Math.max(2, Math.round((100 - completionPct) / 7));

  return (
    <div className="pos-page">
      <TopNav
        saveState={saveState}
        userInitials={userInitials || borrowerName.slice(0, 2).toUpperCase()}
        onExit={() => window.history.back()}
      />

      <div className="pos-body">
        <POSSidebar
          application={application}
          onAskAria={() => setAriaOpen(true)}
        />

        <main className="pos-main">
          {/* Welcome section */}
          <div className="pos-main__welcome">
            <div className="pos-main__urla-badge">
              <span className="pos-main__urla-tag">URLA · Form 1003</span>
              <span className="pos-main__time-estimate">
                · Estimated time remaining: ~{timeRemaining} minutes
              </span>
            </div>
            <h1 className="pos-main__heading">
              Welcome back, {borrowerName}.
            </h1>
            <p className="pos-main__subheading">
              Let's finish your loan application. Your progress saves
              automatically — step away anytime and pick up right where you
              left off.
            </p>
          </div>

          {/* Step rail + panel grid */}
          <div className="pos-main__grid">
            <StepRail
              steps={SECTION_ORDER}
              labels={SECTION_LABELS}
              captions={SECTION_CAPTIONS}
              activeStep={activeStep}
              completionByStep={application.sections_complete}
              onStepClick={handleStepChange}
            />

            <div>
              <div className="pos-main__step-header">
                <p className="pos-main__step-counter">
                  Step {stepIdx + 1} of {SECTION_ORDER.length}
                  <span className="pos-main__step-urla">
                    · URLA Section {stepIdx + 1}
                  </span>
                </p>
                <h2 className="pos-main__step-title">
                  {SECTION_LABELS[activeStep]}
                </h2>
              </div>

              <div className="pos-main__panel" key={activeStep}>
                <ActivePanel
                  section={sections[activeStep]}
                  onChange={(data: Record<string, unknown>) =>
                    updateSectionData(activeStep, data)
                  }
                  onComplete={handleContinue}
                  application={application}
                  onSubmit={submit}
                  onAskAria={() => setAriaOpen(true)}
                />
              </div>
            </div>
          </div>

          {/* Footer with nav buttons */}
          {!isReview && (
            <div className="pos-main__footer">
              <button
                type="button"
                className="pos-btn pos-btn--secondary"
                onClick={handleBack}
                disabled={isFirstStep}
                style={isFirstStep ? { visibility: 'hidden' } : undefined}
              >
                ← Back
              </button>
              <div className="pos-main__footer-right">
                <button type="button" className="pos-btn pos-btn--ghost">
                  Save &amp; finish later
                </button>
                <button
                  type="button"
                  className="pos-btn pos-btn--primary"
                  onClick={handleContinue}
                >
                  Continue →
                </button>
              </div>
            </div>
          )}

          {/* Trust badge */}
          <div className="pos-main__trust">
            <LockIcon />
            <span>
              Bank-grade encryption · We never sell your data · Equal Housing Lender
            </span>
          </div>
        </main>
      </div>

      {/* Aria AI chat */}
      <AriaPanel
        open={ariaOpen}
        onClose={() => setAriaOpen(false)}
        applicationId={application.id}
        currentStep={activeStep}
      />

      {/* Floating Aria FAB */}
      {!ariaOpen && (
        <AskAriaButton
          variant="floating"
          onClick={() => setAriaOpen(true)}
        />
      )}
    </div>
  );
};

const LockIcon: React.FC = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
);
```

- [ ] **Step 3: Update index.ts exports**

In `src/features/pos/index.ts`, add the new exports alongside existing ones:

```typescript
export { TopNav } from './components/TopNav';
export { POSSidebar } from './components/POSSidebar';
export { SECTION_CAPTIONS } from './types';
```

- [ ] **Step 4: Commit**

```bash
git add src/features/pos/components/StepRail.tsx src/features/pos/components/POSContainer.tsx src/features/pos/index.ts
git commit -m "feat(pos): restructure POSContainer with TopNav, sidebar, and step rail in main"
```

---

### Task 4: Form Field and AskAria Button Styling

**Files:**
- Append to: `src/features/pos/pos.css`
- Modify: `src/features/pos/components/AskAriaButton.tsx`

This task adds CSS for the URLA form fields (used by all 9 panels via `_shared.tsx`), radio cards, checkboxes, summary cells, and the Ask Aria button. After this task, the form panels will render with the correct visual treatment.

- [ ] **Step 1: Align AskAriaButton class names**

The component uses `.ask-aria-btn__icon`, `.ask-aria-btn__text`, etc. but the prototype CSS targets `.ask-aria-icon`, `.ask-aria-text`, etc. Update the class names in `AskAriaButton.tsx` to match the simpler pattern the CSS will use. Change lines 38-44:

```tsx
  return (
    <button type="button" className="ask-aria-btn" onClick={onClick}>
      <span className="ask-aria-icon">
        <SparkIcon size={14} />
      </span>
      <span className="ask-aria-text">
        <span className="ask-aria-title">Ask Aria a question</span>
        <span className="ask-aria-sub">{subtitle}</span>
      </span>
      <ChevronRightIcon />
    </button>
  );
```

Also update the floating variant's label class from `aria-fab__label` to `aria-fab-label` (line 32).

- [ ] **Step 2: Append form field styles to pos.css**

Add the following at the end of `src/features/pos/pos.css`:

```css
/* ===================================================================
   FORM FIELDS (urla-* classes from _shared.tsx)
   =================================================================== */

.urla-form-section {
  margin-bottom: 28px;
}

.urla-form-section__title {
  font-family: var(--bt-font-display);
  font-size: 18px;
  font-weight: 500;
  margin-bottom: 4px;
}

.urla-form-section__desc {
  font-size: 13px;
  color: var(--bt-text-secondary);
  margin-bottom: 16px;
}

.urla-form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.urla-field {
  display: flex;
  flex-direction: column;
}

.urla-field--cols-1 { grid-column: span 1; }
.urla-field--cols-2 { grid-column: span 2; }
.urla-field--cols-3 { grid-column: span 3; }

.urla-field__label {
  display: block;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--bt-text-muted);
  margin-bottom: 6px;
}

.urla-field__label .urla-field__required {
  color: var(--bt-error);
}

.urla-field__control {
  position: relative;
}

.urla-field__input,
.urla-field__select {
  width: 100%;
  padding: 11px 14px;
  background: var(--bt-bg-surface);
  border: 1px solid var(--bt-border-strong);
  border-radius: 8px;
  font-size: 14.5px;
  font-family: inherit;
  color: var(--bt-text-primary);
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
  outline: none;
}

.urla-field__input:focus,
.urla-field__select:focus {
  border-color: var(--bt-primary);
  box-shadow: 0 0 0 3px var(--bt-primary-tint);
}

.urla-field__input::placeholder {
  color: var(--bt-text-faint);
}

.urla-field__prefix {
  position: absolute;
  left: 14px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--bt-text-muted);
  font-size: 14px;
  pointer-events: none;
}

.urla-field__input--has-prefix {
  padding-left: 36px;
}

.urla-field__help {
  font-size: 12px;
  color: var(--bt-text-muted);
  margin-top: 6px;
}

.urla-field__error {
  font-size: 12px;
  color: var(--bt-error);
  margin-top: 6px;
}

/* Yes/No toggle */
.urla-yesno {
  display: flex;
  gap: 8px;
}

.urla-yesno__btn {
  flex: 1;
  padding: 10px 16px;
  border: 1px solid var(--bt-border-strong);
  border-radius: 8px;
  background: var(--bt-bg-surface);
  font-size: 14px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s;
  color: var(--bt-text-primary);
}

.urla-yesno__btn:hover {
  border-color: var(--bt-primary);
  background: var(--bt-primary-tint);
}

.urla-yesno__btn--selected {
  border-color: var(--bt-primary);
  background: var(--bt-primary-tint);
  box-shadow: 0 0 0 1px var(--bt-primary) inset;
}

/* Continue / action buttons */
.urla-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid var(--bt-border);
}

.urla-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 500;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
  font-family: inherit;
}

.urla-btn--primary {
  background: var(--bt-primary);
  color: #F5F2E9;
}

.urla-btn--primary:hover {
  background: var(--bt-primary-hover);
}

.urla-btn--ghost {
  background: transparent;
  color: var(--bt-text-secondary);
  border: none;
}

.urla-btn--large {
  padding: 14px 32px;
  font-size: 15px;
}

/* Radio cards */
.urla-radio-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid var(--bt-border-strong);
  border-radius: 10px;
  cursor: pointer;
  background: var(--bt-bg-surface);
  transition: all 0.15s;
}

.urla-radio-card:hover {
  border-color: var(--bt-primary);
  background: var(--bt-primary-tint);
}

.urla-radio-card--selected {
  border-color: var(--bt-primary);
  background: var(--bt-primary-tint);
  box-shadow: 0 0 0 1px var(--bt-primary) inset;
}

.urla-radio-dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1.5px solid var(--bt-border-strong);
  flex-shrink: 0;
  margin-top: 2px;
  display: grid;
  place-items: center;
  background: var(--bt-bg-surface);
}

.urla-radio-card--selected .urla-radio-dot {
  border-color: var(--bt-primary);
}

.urla-radio-card--selected .urla-radio-dot::after {
  content: '';
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--bt-primary);
}

/* Custom checkbox */
.urla-check {
  appearance: none;
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  border: 1.5px solid var(--bt-border-strong);
  border-radius: 4px;
  background: var(--bt-bg-surface);
  cursor: pointer;
  position: relative;
  transition: all 0.12s;
  flex-shrink: 0;
}

.urla-check:checked {
  background: var(--bt-primary);
  border-color: var(--bt-primary);
}

.urla-check:checked::after {
  content: '';
  position: absolute;
  left: 5px;
  top: 1px;
  width: 5px;
  height: 10px;
  border: solid white;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}

/* Summary cells (review step) */
.urla-summary-cell {
  padding: 18px 0;
  border-bottom: 1px solid var(--bt-border);
}

.urla-summary-cell:last-child {
  border-bottom: none;
}

.urla-summary-label {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--bt-text-muted);
  font-weight: 500;
  margin-bottom: 6px;
}

.urla-summary-value {
  font-size: 15px;
  color: var(--bt-text-primary);
  font-weight: 500;
  line-height: 1.45;
}

.urla-summary-value--muted {
  color: var(--bt-text-secondary);
  font-weight: 400;
}

/* Review confirm section */
.urla-confirm {
  padding: 32px;
  text-align: center;
}

.urla-confirm__icon {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: var(--bt-success);
  color: white;
  display: grid;
  place-items: center;
  margin: 0 auto 16px;
}

.urla-recap {
  margin-bottom: 24px;
}

/* Hairline divider */
.urla-hairline {
  display: flex;
  align-items: center;
  gap: 16px;
  color: var(--bt-text-muted);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 500;
  margin: 24px 0;
}

.urla-hairline::before,
.urla-hairline::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--bt-border);
}

/* Banner */
.urla-banner {
  background: linear-gradient(180deg, #FBF6E8, #F8F0D8);
  border: 1px solid #E5D49A;
  border-radius: 12px;
  padding: 14px 18px;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  color: #6B4F1A;
  font-size: 13.5px;
}

/* ---------- Ask Aria Button ---------- */

.ask-aria-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 12px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--bt-primary-tint) 0%, var(--bt-accent-light) 100%);
  border: 1px solid rgba(31, 61, 46, 0.12);
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
  text-align: left;
}

.ask-aria-btn:hover {
  border-color: var(--bt-primary);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px -6px rgba(31, 61, 46, 0.22);
}

.ask-aria-icon {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, #2E5740, #1F3D2E 60%, #14291F);
  display: grid;
  place-items: center;
  color: #E8DDC0;
  flex-shrink: 0;
  box-shadow: inset 0 0 0 1.5px rgba(184, 146, 74, 0.4);
}

.ask-aria-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--bt-text-primary);
  line-height: 1.2;
  display: block;
}

.ask-aria-sub {
  font-size: 10.5px;
  color: var(--bt-text-muted);
  margin-top: 2px;
  display: block;
}

/* Floating Aria FAB */
.aria-fab {
  position: fixed;
  bottom: 26px;
  right: 26px;
  z-index: 60;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--bt-primary);
  color: #F5F2E9;
  display: grid;
  place-items: center;
  cursor: pointer;
  border: none;
  box-shadow: 0 10px 28px -8px rgba(31, 61, 46, 0.45), 0 2px 6px rgba(0, 0, 0, 0.08);
  transition: transform 0.25s cubic-bezier(0.2, 0.7, 0.2, 1), opacity 0.2s, background 0.15s;
}

.aria-fab:hover {
  background: var(--bt-primary-hover);
  transform: scale(1.06);
}

.aria-fab.is-hidden {
  transform: scale(0);
  opacity: 0;
  pointer-events: none;
}

.aria-fab::after {
  content: '';
  position: absolute;
  inset: -2px;
  border-radius: 50%;
  border: 2px solid var(--bt-primary);
  opacity: 0;
  animation: aria-pulse 2.6s ease-out infinite;
}

@keyframes aria-pulse {
  0% { opacity: 0.55; transform: scale(1); }
  100% { opacity: 0; transform: scale(1.35); }
}

.aria-fab-label {
  position: absolute;
  right: 64px;
  top: 50%;
  transform: translateY(-50%);
  background: var(--bt-text-primary);
  color: var(--bt-bg-page);
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 11.5px;
  font-weight: 500;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s, transform 0.15s;
}

.aria-fab:hover .aria-fab-label {
  opacity: 1;
}

@media (max-width: 1024px) {
  .urla-form-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .urla-field--cols-3 { grid-column: span 2; }
}

@media (max-width: 768px) {
  .urla-form-grid {
    grid-template-columns: 1fr;
  }
  .urla-field--cols-2,
  .urla-field--cols-3 { grid-column: span 1; }
}
```

- [ ] **Step 3: Commit**

```bash
git add src/features/pos/pos.css src/features/pos/components/AskAriaButton.tsx
git commit -m "feat(pos): form field, radio card, checkbox, and AskAria styling"
```

---

### Task 5: Aria Panel and Smart Calendar Styling

**Files:**
- Append to: `src/features/pos/pos.css`

This task adds the Aria chat slide-over panel styles and the Smart Calendar booking widget styles. Both components already exist and render the correct class names — they just need CSS. The class names in AriaPanel.tsx use `__` BEM separators (e.g., `.aria-panel__header`) while the prototype uses `-` (e.g., `.aria-panel-header`). The CSS below targets the actual component class names.

- [ ] **Step 1: Append Aria panel styles to pos.css**

```css
/* ===================================================================
   ARIA AI ASSISTANT — Slide-over chat panel
   =================================================================== */

.aria-overlay {
  position: fixed;
  inset: 0;
  background: rgba(20, 41, 31, 0.22);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  z-index: 70;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.25s;
}

.aria-overlay.is-open {
  opacity: 1;
  pointer-events: auto;
}

.aria-panel {
  position: fixed;
  top: 0;
  right: 0;
  height: 100vh;
  width: 460px;
  max-width: 92vw;
  background: var(--bt-bg-page);
  z-index: 80;
  display: flex;
  flex-direction: column;
  transform: translateX(100%);
  transition: transform 0.4s cubic-bezier(0.2, 0.7, 0.2, 1);
  box-shadow: -20px 0 60px -20px rgba(0, 0, 0, 0.22);
  border-left: 1px solid var(--bt-border);
}

.aria-panel.is-open {
  transform: translateX(0);
}

.aria-panel__header {
  padding: 16px 18px;
  border-bottom: 1px solid var(--bt-border);
  background: var(--bt-bg-surface);
  flex-shrink: 0;
}

.aria-panel__identity {
  display: flex;
  align-items: center;
  gap: 12px;
}

.aria-panel__seal {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, #2E5740, #1F3D2E 60%, #14291F);
  display: grid;
  place-items: center;
  color: #E8DDC0;
  font-family: var(--bt-font-display);
  font-weight: 600;
  font-size: 16px;
  box-shadow: inset 0 0 0 1.5px rgba(184, 146, 74, 0.4);
  flex-shrink: 0;
}

.aria-panel__title-wrap {
  flex: 1;
  min-width: 0;
}

.aria-panel__title {
  font-family: var(--bt-font-display);
  font-size: 18px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.aria-panel__online-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 9.5px;
  font-weight: 500;
  font-family: var(--bt-font-body);
  background: var(--bt-primary-light);
  color: var(--bt-primary);
}

.aria-panel__online-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bt-success);
}

.aria-panel__subtitle {
  font-size: 11.5px;
  color: var(--bt-text-muted);
  margin-top: 4px;
}

.aria-panel__capabilities {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
}

.aria-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 500;
  background: var(--bt-bg-elevated);
  color: var(--bt-text-secondary);
  border: 1px solid var(--bt-border-strong);
}

.aria-panel__body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 18px 8px;
}

.aria-panel__footer {
  flex-shrink: 0;
  border-top: 1px solid var(--bt-border);
  background: var(--bt-bg-surface);
  padding: 12px 16px 14px;
}

.aria-panel__disclaimer {
  font-size: 10.5px;
  color: var(--bt-text-muted);
  margin-top: 10px;
  text-align: center;
  line-height: 1.5;
}

/* Messages */
.aria-msg-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  animation: pos-msgFade 0.35s cubic-bezier(0.2, 0.7, 0.2, 1);
}

@keyframes pos-msgFade {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: none; }
}

.aria-msg-row--aria {
  justify-content: flex-start;
}

.aria-msg-row--user {
  justify-content: flex-end;
}

.aria-msg-seal {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, #2E5740, #1F3D2E 60%, #14291F);
  display: grid;
  place-items: center;
  color: #E8DDC0;
  font-family: var(--bt-font-display);
  font-weight: 600;
  font-size: 12px;
  flex-shrink: 0;
  margin-top: 2px;
}

.aria-msg-bubble {
  max-width: 84%;
  padding: 12px 14px;
  border-radius: 14px;
  font-size: 13.5px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.aria-msg-row--aria .aria-msg-bubble {
  background: var(--bt-bg-surface);
  border: 1px solid var(--bt-border);
  color: var(--bt-text-primary);
  border-top-left-radius: 4px;
  position: relative;
  overflow: hidden;
}

.aria-msg-row--aria .aria-msg-bubble::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, var(--bt-primary), var(--bt-accent) 75%, transparent);
  opacity: 0.55;
}

.aria-msg-row--user .aria-msg-bubble {
  background: var(--bt-primary);
  color: #F5F2E9;
  border-top-right-radius: 4px;
}

.aria-msg-bubble p { margin: 0 0 8px; }
.aria-msg-bubble p:last-child { margin-bottom: 0; }
.aria-msg-bubble ul { margin: 6px 0; padding-left: 18px; }
.aria-msg-bubble li { margin: 3px 0; }
.aria-msg-bubble strong { font-weight: 600; }

/* Sources */
.aria-sources {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--bt-border);
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.aria-sources__label {
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--bt-text-muted);
  font-weight: 600;
  width: 100%;
  margin-bottom: 4px;
}

.aria-source-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background: var(--bt-bg-elevated);
  border-radius: 999px;
  color: var(--bt-text-secondary);
  font-size: 11px;
  font-weight: 500;
}

.aria-source-link {
  text-decoration: none;
  color: inherit;
}

.aria-source-link:hover .aria-source-chip {
  background: var(--bt-primary-tint);
  color: var(--bt-primary);
}

/* Typing indicator */
.aria-typing {
  display: inline-flex;
  gap: 4px;
  padding: 14px 16px;
  background: var(--bt-bg-surface);
  border: 1px solid var(--bt-border);
  border-radius: 14px;
  border-top-left-radius: 4px;
}

.aria-typing__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bt-text-muted);
  animation: aria-typing 1.4s ease-in-out infinite;
}

.aria-typing__dot:nth-child(2) { animation-delay: 0.15s; }
.aria-typing__dot:nth-child(3) { animation-delay: 0.3s; }

@keyframes aria-typing {
  0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-3px); }
}

/* Suggestions */
.aria-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.aria-suggestion {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  font-family: inherit;
  background: var(--bt-bg-page);
  border: 1px solid var(--bt-border-strong);
  color: var(--bt-text-primary);
  cursor: pointer;
  transition: all 0.15s;
}

.aria-suggestion:hover {
  border-color: var(--bt-primary);
  background: var(--bt-primary-tint);
}

/* Input */
.aria-input-row {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  background: var(--bt-bg-page);
  border: 1px solid var(--bt-border-strong);
  border-radius: 14px;
  padding: 5px 5px 5px 14px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.aria-input-row:focus-within {
  border-color: var(--bt-primary);
  box-shadow: 0 0 0 3px var(--bt-primary-tint);
}

.aria-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-family: inherit;
  font-size: 14px;
  padding: 9px 0;
  resize: none;
  max-height: 120px;
  color: var(--bt-text-primary);
  line-height: 1.4;
}

.aria-input::placeholder {
  color: var(--bt-text-faint);
}

.aria-icon-btn {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  border: none;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  background: transparent;
  color: var(--bt-text-secondary);
  flex-shrink: 0;
}

.aria-icon-btn:hover {
  background: var(--bt-bg-elevated);
  color: var(--bt-text-primary);
}

.aria-send-btn {
  background: var(--bt-primary);
  color: #F5F2E9;
}

.aria-send-btn:hover {
  background: var(--bt-primary-hover);
  color: #F5F2E9;
}

.aria-send-btn:disabled {
  background: var(--bt-bg-elevated);
  color: var(--bt-text-faint);
  cursor: not-allowed;
}

.aria-error {
  padding: 8px 12px;
  margin-bottom: 12px;
  background: rgba(155, 44, 44, 0.08);
  border: 1px solid rgba(155, 44, 44, 0.2);
  border-radius: 8px;
  color: var(--bt-error);
  font-size: 13px;
}

/* ===================================================================
   SMART CALENDAR — Booking widget in Review step
   =================================================================== */

.smart-cal {
  background: var(--bt-bg-soft);
  border: 1px solid var(--bt-border-strong);
  border-radius: 12px;
  overflow: hidden;
  margin: 24px 0;
}

.smart-cal__header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--bt-border);
}

.smart-cal__title {
  font-family: var(--bt-font-display);
  font-size: 18px;
  font-weight: 500;
}

.smart-cal__body {
  display: grid;
  grid-template-columns: 1fr 360px;
}

.smart-cal__calendar {
  padding: 20px;
  border-right: 1px solid var(--bt-border);
}

.smart-cal__slots {
  padding: 20px;
}

.smart-cal__month-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.smart-cal__month-label {
  font-weight: 600;
  font-size: 15px;
}

.smart-cal__nav-btn {
  padding: 8px;
  border-radius: 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: background 0.12s;
  color: var(--bt-text-primary);
}

.smart-cal__nav-btn:hover {
  background: var(--bt-bg-elevated);
}

.smart-cal__nav-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.smart-cal__grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
  text-align: center;
}

.smart-cal__day-header {
  font-size: 11px;
  font-weight: 600;
  color: var(--bt-text-muted);
  padding: 4px 0 8px;
  text-transform: uppercase;
}

.smart-cal__day {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-size: 13.5px;
  font-weight: 500;
  border: none;
  cursor: pointer;
  transition: all 0.12s;
  background: transparent;
  color: var(--bt-text-primary);
  margin: 0 auto;
}

.smart-cal__day:hover {
  background: var(--bt-bg-elevated);
}

.smart-cal__day--today {
  font-weight: 700;
  box-shadow: inset 0 -2px 0 var(--bt-primary);
}

.smart-cal__day--selected {
  background: var(--bt-primary);
  color: #F5F2E9;
}

.smart-cal__day--unavailable {
  color: var(--bt-text-faint);
  cursor: default;
}

.smart-cal__day--unavailable:hover {
  background: transparent;
}

.smart-cal__day--empty {
  visibility: hidden;
}

.smart-cal__slot {
  padding: 8px 14px;
  border: 1px solid var(--bt-border-strong);
  border-radius: 8px;
  font-size: 13.5px;
  font-weight: 500;
  font-family: var(--bt-font-mono);
  cursor: pointer;
  background: var(--bt-bg-surface);
  transition: all 0.12s;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  width: 100%;
  color: var(--bt-text-primary);
}

.smart-cal__slot:hover {
  border-color: var(--bt-primary);
  background: var(--bt-primary-tint);
}

.smart-cal__slot--selected {
  border-color: var(--bt-primary);
  background: var(--bt-primary-tint);
  box-shadow: 0 0 0 1px var(--bt-primary) inset;
}

.smart-cal__slot--booked {
  opacity: 0.4;
  cursor: not-allowed;
  text-decoration: line-through;
}

.smart-cal__slot--recommended::after {
  content: 'Recommended';
  font-size: 10px;
  font-family: var(--bt-font-body);
  background: var(--bt-accent-light);
  color: #6B4F1A;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 500;
}

.smart-cal__confirm-btn {
  width: 100%;
  margin-top: 16px;
}

/* Calendar confirmation */
.smart-cal__confirm-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--bt-success);
  color: white;
  display: grid;
  place-items: center;
  margin: 0 auto 16px;
}

.smart-cal__confirmed-time {
  font-family: var(--bt-font-display);
  font-size: 20px;
  font-weight: 500;
  text-align: center;
}

.smart-cal__confirmed-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-top: 16px;
}

@media (max-width: 768px) {
  .smart-cal__body {
    grid-template-columns: 1fr;
  }
  .smart-cal__calendar {
    border-right: none;
    border-bottom: 1px solid var(--bt-border);
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/features/pos/pos.css
git commit -m "feat(pos): Aria chat panel and Smart Calendar styling"
```

---

### Task 6: Route Wiring

**Files:**
- Create: `src/pages/pos/POSEntryPage.tsx`
- Modify: `src/routes/index.jsx`

This task wires the redesigned POS to the `/apply/v2/purchase` route, replacing the current single-question-at-a-time flow with the new multi-panel experience.

The existing `NewPurchaseApplication` at `/apply/v2/purchase` uses a completely different state management system (`ApplicationContext` + `useApplicationPersistence`). The new POS uses `usePOSApplication` which talks to the backend POS API. The entry page wraps `POSContainer` and handles initial setup (extracting parameters from the URL, passing borrower name).

- [ ] **Step 1: Create POSEntryPage.tsx**

```tsx
import React from 'react';
import { useSearchParams } from 'react-router-dom';

import { POSContainer } from '../../features/pos';

const POSEntryPage: React.FC = () => {
  const [searchParams] = useSearchParams();

  const loanIdParam = searchParams.get('loan_id');
  const loanId = loanIdParam ? parseInt(loanIdParam, 10) : undefined;
  const borrowerName = searchParams.get('name') || 'there';
  const initials = searchParams.get('initials') || '';

  return (
    <POSContainer
      loanId={loanId}
      borrowerName={borrowerName}
      userInitials={initials}
    />
  );
};

export default POSEntryPage;
```

- [ ] **Step 2: Add route in routes/index.jsx**

Find the existing `/apply/v2/purchase` route definition (around line 502). Add the new POS route ABOVE it so it takes precedence:

At the top of the file, add the lazy import:

```javascript
const POSEntryPage = lazyRetry(() => import('../pages/pos/POSEntryPage'));
```

Then add the route alongside the existing v2 routes:

```jsx
<Route key="/apply/v3/purchase" path="/apply/v3/purchase" element={<LazyPage><POSEntryPage /></LazyPage>} />
```

Use `/apply/v3/purchase` as the route path initially so the existing v2 flow remains available during testing. Once verified, the v2 route can be updated to redirect to v3, or the v3 path can replace v2.

- [ ] **Step 3: Create the pages/pos directory**

```bash
mkdir -p src/pages/pos
```

- [ ] **Step 4: Commit**

```bash
git add src/pages/pos/POSEntryPage.tsx src/routes/index.jsx
git commit -m "feat(pos): wire redesigned POS to /apply/v3/purchase route"
```

---

### Task 7: Visual Verification and Polish

**Files:**
- None created; this task is verification and minor fixes.

This task verifies the full POS experience in the browser and fixes any visual discrepancies against the prototype.

- [ ] **Step 1: Start the dev server and open both pages**

```bash
cd frontend && npm run dev
```

Open two tabs:
1. `http://localhost:3000/pos-redesign-prototype.html` — the target design
2. `http://localhost:3000/apply/v3/purchase` — the React implementation

- [ ] **Step 2: Verify the top navigation**

Check that the header shows:
- Perennia logo (green P with gold dot) + "Perennia" in Fraunces serif
- Nav links: Dashboard, Application (highlighted), Documents, Resources
- Save status indicator
- "Save & exit" button
- User avatar seal

- [ ] **Step 3: Verify the sidebar**

Check that the left sidebar shows:
- Loan file card with "In progress" gold chip, "Purchase · Primary", loan ID
- Progress bar with percentage
- "Ask Aria a question" button with green gradient icon
- Navigation items: Home, Application (active/green), Documents (badge 3), Tasks (5), Messages (dot), Disclosures
- Tools section: Calculators, Loan timeline, Help & support

- [ ] **Step 4: Verify the main content**

Check that the main area shows:
- URLA · Form 1003 tag + time estimate
- "Welcome back" heading in Fraunces serif
- Subtitle text
- Two-column grid: step rail on left, active panel on right
- Step rail with 9 steps, correct marker states (done=green check, active=gold, pending=gray)
- Step captions under each title
- Active panel with step counter and title
- Footer with Back, Save & finish later, Continue buttons
- Trust badge at bottom

- [ ] **Step 5: Test step navigation**

Click through different steps in the rail. Verify:
- Completed steps show green checkmark
- Active step highlights with gold marker and green-tinted row
- Pending steps are grayed out and disabled past next step
- Panel content transitions with fadeUp animation
- Step counter updates ("Step N of 9")

- [ ] **Step 6: Test Aria chat**

Click the "Ask Aria" button in the sidebar or the floating FAB. Verify:
- Overlay fades in with blur
- Panel slides in from right
- Header shows Aria seal, name, "Online" pill, capability chips
- Message thread renders with proper styling
- User messages appear on right in green bubbles
- Aria messages on left with brand gradient top border
- Typing indicator animates
- Suggestions render as pill buttons
- ESC closes the panel

- [ ] **Step 7: Fix any visual discrepancies**

Compare the React implementation pixel-by-pixel with the HTML prototype. Common issues to check:
- Font weights and sizes
- Spacing and padding
- Border radii
- Color values
- Responsive behavior at 1024px and 768px breakpoints

Fix any issues found and commit:

```bash
git add -A
git commit -m "fix(pos): visual polish after prototype comparison"
```

---

## Self-Review Checklist

1. **Spec coverage**: All visual elements from the prototype are addressed — top nav, sidebar with loan card + nav, step rail with captions, form field styling, buttons, Aria chat panel with messages/sources/suggestions/typing, Smart Calendar, progress bar, trust badge, responsive breakpoints.

2. **Placeholder scan**: No TBDs, TODOs, or "add appropriate" language. All CSS values are specified. All component code is complete.

3. **Type consistency**: `SECTION_CAPTIONS` is defined in types.ts (Task 1) and consumed by StepRail (Task 3) and POSContainer (Task 3). `SectionKey` type is consistent throughout. `SaveIndicator` is inlined in TopNav rather than the old POSContainer location. All BEM class names in CSS match the class names rendered by the corresponding `.tsx` components.
