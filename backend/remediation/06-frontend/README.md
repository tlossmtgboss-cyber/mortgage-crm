# 06 — Frontend Remediation

**Findings addressed:**
- #7 (45MB bundle, 388 pages, no code splitting)
- Over-engineering observation: 4,843-line App.jsx
- Questionable decision: Context API only, no state management

## What Ships

1. **Vite config with route-based chunking** — splits the 200+ routes into 6 logical chunks. Target: <12MB initial gzipped.
2. **Zustand stores** — replaces Context providers for pipeline, session, notifications, UI.
3. **Route manifest** — moves the monolithic `App.jsx` routing into data-driven config loaded per chunk.
4. **Bundle analyzer config** — continuous monitoring, fails CI if initial chunk grows past threshold.
5. **Image/asset optimization** — auto WebP, lazy loading defaults.

## Execution

```bash
# From frontend/:
cd frontend

# 1. Install
npm install --save zustand immer
npm install --save-dev rollup-plugin-visualizer @types/node

# 2. Copy vite config
cp ../06-frontend/vite.config.ts ./vite.config.ts

# 3. Copy store scaffolding
mkdir -p src/stores
cp ../06-frontend/stores/*.ts src/stores/

# 4. Copy route manifest system
mkdir -p src/routes
cp ../06-frontend/routes/*.tsx src/routes/
cp ../06-frontend/App.tsx src/App.tsx  # minimal new App.tsx

# 5. Run bundle analysis
npm run build -- --mode analyze
open dist/stats.html  # inspect chunks

# 6. Verify size budgets
npm run size-check
```

## Chunk Strategy

| Chunk | Routes | Target size |
|-------|--------|-------------|
| `main` | login, dashboard shell, routing | <2MB |
| `pipeline` | pipeline views, loan detail, kanban | <3MB |
| `ai` | Aria, agent UI, voice, call intelligence | <3MB |
| `borrower-portal` | borrower-facing portal | <2MB |
| `admin` | settings, user mgmt, integrations, RBAC | <2MB |
| `docs` | document viewer, uploads, guidelines RAG | <2MB |

Total initial: main only, others lazy-loaded on route match.

## Migrating Contexts to Zustand

Drop-in replacement pattern:

```tsx
// Before:
const { user, setUser } = useContext(AuthContext);

// After:
const { user, setUser } = useAuthStore();
```

See `06-frontend/stores/MIGRATION.md` for every Context → Store mapping.
