# Frontend Remediation

## Table of Contents
1. [Accessibility Baseline](#accessibility)
2. [Component Reorganization](#organization)
3. [Internationalization (i18n)](#i18n)

---

<a name="accessibility"></a>
## 1. Accessibility Baseline

### Current State
- 8 out of 295 components have ARIA attributes
- No eslint-plugin-jsx-a11y
- No keyboard navigation enforcement
- No screen reader testing
- Financial services ADA lawsuits are increasing — this is legal exposure

### Phase 1: Tooling Setup (Day 1)

```bash
# Install accessibility linting
npm install --save-dev eslint-plugin-jsx-a11y

# Add axe-core for runtime accessibility testing
npm install --save-dev @axe-core/react
```

Update `.eslintrc.js` (or `eslint.config.js`):

```javascript
// ESLint flat config
import jsxA11y from 'eslint-plugin-jsx-a11y';

export default [
  // ... existing config
  {
    plugins: { 'jsx-a11y': jsxA11y },
    rules: {
      // Start with warnings (not errors) to avoid blocking dev
      'jsx-a11y/alt-text': 'warn',
      'jsx-a11y/anchor-has-content': 'warn',
      'jsx-a11y/aria-props': 'warn',
      'jsx-a11y/aria-propstype': 'warn',
      'jsx-a11y/aria-role': 'warn',
      'jsx-a11y/aria-unsupported-elements': 'warn',
      'jsx-a11y/click-events-have-key-events': 'warn',
      'jsx-a11y/heading-has-content': 'warn',
      'jsx-a11y/html-has-lang': 'warn',
      'jsx-a11y/img-redundant-alt': 'warn',
      'jsx-a11y/interactive-supports-focus': 'warn',
      'jsx-a11y/label-has-associated-control': 'warn',
      'jsx-a11y/no-access-key': 'warn',
      'jsx-a11y/no-autofocus': 'warn',
      'jsx-a11y/no-noninteractive-element-interactions': 'warn',
      'jsx-a11y/no-static-element-interactions': 'warn',
      'jsx-a11y/role-has-required-aria-props': 'warn',
      'jsx-a11y/role-supports-aria-props': 'warn',
      'jsx-a11y/tabindex-no-positive': 'warn',
    }
  }
];
```

### Phase 2: Fix Top 10 Workflows (Week 1–2)

Fix accessibility in the components LOs use most frequently:

1. **Login/Auth forms** — Focus management, form labels, error announcements
2. **Pipeline view** — Table accessibility, sortable column headers
3. **Lead list/detail** — Data tables, action buttons
4. **Contact forms** — Input labels, validation errors, required fields
5. **Loan detail page** — Financial data tables, status indicators
6. **Navigation/Sidebar** — Keyboard nav, current page indicator
7. **Search** — Search input label, results announcement
8. **Modals/Dialogs** — Focus trapping, escape key, aria-modal
9. **Toast notifications** — aria-live regions, role="alert"
10. **Dropdown menus** — Keyboard navigation, aria-expanded

### Common Fixes

#### Forms
```jsx
// BAD — no label association
<input type="text" placeholder="Email" />

// GOOD — explicit label
<label htmlFor="email">Email address</label>
<input id="email" type="email" aria-required="true" />

// GOOD — for MUI components
<TextField
  id="email"
  label="Email address"
  required
  inputProps={{ 'aria-describedby': 'email-help' }}
/>
<FormHelperText id="email-help">We'll never share your email</FormHelperText>
```

#### Buttons
```jsx
// BAD — icon button with no accessible name
<IconButton onClick={handleDelete}><DeleteIcon /></IconButton>

// GOOD
<IconButton onClick={handleDelete} aria-label="Delete contact">
  <DeleteIcon />
</IconButton>
```

#### Data Tables
```jsx
// BAD — div-based table
<div className="table"><div className="row">...</div></div>

// GOOD — semantic table with scope
<table aria-label="Pipeline loans">
  <thead>
    <tr>
      <th scope="col">Borrower</th>
      <th scope="col">Loan Amount</th>
      <th scope="col" aria-sort="descending">Status</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>John Doe</td>
      <td>$350,000</td>
      <td><StatusBadge status="processing" /></td>
    </tr>
  </tbody>
</table>
```

#### Modals (MUI Dialog)
```jsx
// MUI Dialog already handles most a11y, but verify:
<Dialog
  open={open}
  onClose={handleClose}
  aria-labelledby="dialog-title"
  aria-describedby="dialog-description"
>
  <DialogTitle id="dialog-title">Confirm Action</DialogTitle>
  <DialogContent>
    <DialogContentText id="dialog-description">
      Are you sure you want to delete this lead?
    </DialogContentText>
  </DialogContent>
</Dialog>
```

### Phase 3: Escalate to Errors (Week 3)

After fixing the top workflows, change ESLint rules from `warn` to `error` for the most critical rules. This prevents new inaccessible code from being merged.

```javascript
// Critical rules → error
'jsx-a11y/alt-text': 'error',
'jsx-a11y/aria-props': 'error',
'jsx-a11y/aria-role': 'error',
'jsx-a11y/label-has-associated-control': 'error',
'jsx-a11y/click-events-have-key-events': 'error',
'jsx-a11y/interactive-supports-focus': 'error',
```

---

<a name="organization"></a>
## 2. Component Reorganization

### Current State
- 268 component files in a single `src/components/` directory
- No feature-based subdirectories
- No Storybook or component documentation
- Mixed JS/TS with no enforcement

### Target Structure

Reorganize by **feature domain**, not file type:

```
src/
├── features/
│   ├── auth/
│   │   ├── components/
│   │   │   ├── LoginForm.tsx
│   │   │   ├── RegisterForm.tsx
│   │   │   └── ForgotPassword.tsx
│   │   ├── hooks/
│   │   │   └── useAuth.ts
│   │   ├── api/
│   │   │   └── authApi.ts
│   │   └── index.ts           # Public exports
│   ├── pipeline/
│   │   ├── components/
│   │   │   ├── PipelineBoard.tsx
│   │   │   ├── PipelineFilters.tsx
│   │   │   ├── LoanCard.tsx
│   │   │   └── StageColumn.tsx
│   │   ├── hooks/
│   │   │   └── usePipeline.ts
│   │   └── index.ts
│   ├── leads/
│   │   ├── components/
│   │   ├── hooks/
│   │   └── index.ts
│   ├── loans/
│   │   ├── components/
│   │   ├── hooks/
│   │   └── index.ts
│   ├── contacts/
│   ├── telephony/
│   ├── ai-agents/
│   ├── settings/
│   ├── portals/
│   │   ├── borrower/
│   │   ├── realtor/
│   │   └── partner/
│   └── onboarding/
├── shared/
│   ├── components/            # Truly reusable UI components
│   │   ├── DataTable.tsx
│   │   ├── SearchInput.tsx
│   │   ├── StatusBadge.tsx
│   │   ├── ConfirmDialog.tsx
│   │   └── LoadingSpinner.tsx
│   ├── hooks/
│   │   ├── useDebounce.ts
│   │   ├── usePagination.ts
│   │   └── useLocalStorage.ts
│   ├── utils/
│   └── types/
├── app/
│   ├── App.tsx
│   ├── AppProviders.tsx
│   ├── AppRoutes.tsx
│   └── layouts/
└── assets/
```

### Migration Process

This is a large refactor. Do it incrementally:

1. **Create the new directory structure** (empty folders)
2. **Move one feature at a time** (start with the smallest)
3. **Update imports** using IDE refactoring tools or a codemod
4. **Create barrel exports** (`index.ts`) so external imports stay clean
5. **Test after each feature migration**

Do NOT attempt to migrate all 268 components at once. Plan for 2–3 features per week.

### TypeScript Migration

While reorganizing, convert JS → TS:

```bash
# Rename files (one feature at a time)
for f in src/features/auth/components/*.js; do
  mv "$f" "${f%.js}.tsx"
done
```

Add a tsconfig.json strict-mode ramp:
```json
{
  "compilerOptions": {
    "strict": false,           // Start permissive
    "noImplicitAny": false,    // Enable later
    "strictNullChecks": false, // Enable later
    // Enable these one at a time as you fix issues:
    // "noImplicitAny": true,
    // "strictNullChecks": true,
    // "strict": true,
  }
}
```

---

<a name="i18n"></a>
## 3. Internationalization (i18n)

### Why
- CA, TX, FL (top 3 mortgage markets) have significant Spanish-speaking populations
- Shape and BNTouch already offer Spanish-language borrower portals
- i18n framework also enables future language additions

### Framework: react-i18next

```bash
npm install react-i18next i18next i18next-http-backend i18next-browser-languagedetector
```

### Setup

```typescript
// src/i18n/config.ts
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import HttpApi from 'i18next-http-backend';

i18n
  .use(HttpApi)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    supportedLngs: ['en', 'es'],
    ns: ['common', 'portal', 'pipeline', 'loans'],
    defaultNS: 'common',
    backend: {
      loadPath: '/locales/{{lng}}/{{ns}}.json',
    },
    interpolation: {
      escapeValue: false, // React already escapes
    },
  });

export default i18n;
```

### Translation Files

```
public/locales/
├── en/
│   ├── common.json
│   ├── portal.json
│   ├── pipeline.json
│   └── loans.json
└── es/
    ├── common.json
    ├── portal.json
    ├── pipeline.json
    └── loans.json
```

Example `en/portal.json`:
```json
{
  "welcome": "Welcome to your mortgage portal",
  "loanStatus": "Loan Status",
  "nextSteps": "Your Next Steps",
  "documents": "Documents",
  "uploadDocument": "Upload Document",
  "closingDate": "Estimated Closing Date",
  "loanOfficer": "Your Loan Officer",
  "contactLO": "Contact Your Loan Officer"
}
```

Example `es/portal.json`:
```json
{
  "welcome": "Bienvenido a su portal hipotecario",
  "loanStatus": "Estado del préstamo",
  "nextSteps": "Sus próximos pasos",
  "documents": "Documentos",
  "uploadDocument": "Subir documento",
  "closingDate": "Fecha estimada de cierre",
  "loanOfficer": "Su oficial de préstamos",
  "contactLO": "Contactar a su oficial de préstamos"
}
```

### Usage in Components

```tsx
import { useTranslation } from 'react-i18next';

function BorrowerPortalHeader() {
  const { t } = useTranslation('portal');

  return (
    <div>
      <h1>{t('welcome')}</h1>
      <h2>{t('loanStatus')}</h2>
    </div>
  );
}
```

### Priority: Portal First

Start with the borrower-facing portal — this is what Spanish-speaking borrowers see. Internal LO-facing UI can remain English-only initially.

Pages to translate first:
1. Borrower portal dashboard
2. Document upload page
3. Loan status tracker
4. Close On Time calendar
5. Contact/messaging page

## Validation Checklist

### Accessibility
- [ ] eslint-plugin-jsx-a11y installed and configured
- [ ] Top 10 workflows have ARIA attributes
- [ ] All form inputs have associated labels
- [ ] All icon buttons have aria-label
- [ ] Data tables use semantic HTML with scope attributes
- [ ] Modals trap focus and support Escape key
- [ ] Tab navigation works through primary workflows
- [ ] Screen reader tested on login → pipeline → lead detail flow

### Component Organization
- [ ] Feature-based directory structure created
- [ ] At least 3 features migrated to new structure
- [ ] Barrel exports (index.ts) for each feature
- [ ] No new components added to flat src/components/

### i18n
- [ ] react-i18next configured with language detection
- [ ] English translation files complete for portal
- [ ] Spanish translation files complete for portal
- [ ] Language switcher available in borrower portal
- [ ] Date/number formatting respects locale
