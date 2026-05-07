# Vite Migration Guide

This document describes the migration from Create React App (CRA) to Vite.

## Quick Start

```bash
# Install new dependencies
npm install

# Run with Vite (new)
npm run dev

# Build with Vite (new)
npm run build

# Preview production build
npm run preview
```

## CRA Commands (Still Available During Transition)

```bash
# Run with CRA
npm run start:cra

# Build with CRA
npm run build:cra

# Test with CRA/Jest
npm run test:cra
```

## Environment Variables

### Naming Convention Change

Vite uses `VITE_` prefix instead of `REACT_APP_`:

| CRA (Old)                           | Vite (New)                      |
|-------------------------------------|---------------------------------|
| `REACT_APP_API_URL`                 | `VITE_API_URL`                  |
| `REACT_APP_WS_URL`                  | `VITE_WS_URL`                   |
| `REACT_APP_MICROSOFT_CLIENT_ID`     | `VITE_MICROSOFT_CLIENT_ID`      |
| `REACT_APP_GOOGLE_PLACES_API_KEY`   | `VITE_GOOGLE_PLACES_API_KEY`    |
| `REACT_APP_GOOGLE_CLIENT_ID`        | `VITE_GOOGLE_CLIENT_ID`         |
| `REACT_APP_FACEBOOK_APP_ID`         | `VITE_FACEBOOK_APP_ID`          |
| `REACT_APP_LINKEDIN_CLIENT_ID`      | `VITE_LINKEDIN_CLIENT_ID`       |
| `REACT_APP_APPLE_CLIENT_ID`         | `VITE_APPLE_CLIENT_ID`          |
| `REACT_APP_ENABLE_AGENT_DASHBOARD`  | `VITE_ENABLE_AGENT_DASHBOARD`   |
| `REACT_APP_ENABLE_AGENT_GYM`        | `VITE_ENABLE_AGENT_GYM`         |
| `REACT_APP_ENABLE_PURL_PORTAL`      | `VITE_ENABLE_PURL_PORTAL`       |
| `REACT_APP_ENABLE_VIDEO_FEATURE`    | `VITE_ENABLE_VIDEO_FEATURE`     |
| `REACT_APP_SENTRY_DSN`              | `VITE_SENTRY_DSN`               |
| `REACT_APP_GA_TRACKING_ID`          | `VITE_GA_TRACKING_ID`           |
| `REACT_APP_MIXPANEL_TOKEN`          | `VITE_MIXPANEL_TOKEN`           |
| `REACT_APP_ENVIRONMENT`             | `VITE_ENVIRONMENT`              |
| `REACT_APP_DEBUG`                   | `VITE_DEBUG`                    |
| `REACT_APP_PURL_SESSION_TIMEOUT`    | `VITE_PURL_SESSION_TIMEOUT`     |
| `REACT_APP_PURL_DEBUG`              | `VITE_PURL_DEBUG`               |

### Accessing Environment Variables in Code

#### Old Way (CRA)
```javascript
const apiUrl = process.env.REACT_APP_API_URL;
```

#### New Way (Vite)
```javascript
// Option 1: Direct access
const apiUrl = import.meta.env.VITE_API_URL;

// Option 2: Using the env utility (recommended for migration)
import { env } from '@/utils/env';
const apiUrl = env.API_URL;
```

### Updating .env Files

Create new `.env` files with `VITE_` prefix:

```bash
# .env (development)
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
VITE_ENVIRONMENT=development

# .env.production (local only — do NOT commit; see .env.example for values)
VITE_API_URL=https://api.perenniaai.com
VITE_WS_URL=wss://api.perenniaai.com
VITE_ENVIRONMENT=production
```

## Code Changes Required

### 1. Environment Variable Access

Find and replace all `process.env.REACT_APP_*` with `import.meta.env.VITE_*`:

```javascript
// Before
const isProduction = process.env.NODE_ENV === 'production';
const apiUrl = process.env.REACT_APP_API_URL;

// After
const isProduction = import.meta.env.PROD;
const apiUrl = import.meta.env.VITE_API_URL;
```

### 2. Dynamic Imports

Vite uses native ES modules. Most dynamic imports should work, but glob imports are different:

```javascript
// CRA (webpack)
const modules = require.context('./modules', true, /\.js$/);

// Vite
const modules = import.meta.glob('./modules/*.js');
```

### 3. Static Assets

```javascript
// CRA
import logo from './logo.png';
// or
<img src={process.env.PUBLIC_URL + '/logo.png'} />

// Vite
import logo from './logo.png';
// or
<img src="/logo.png" />
```

### 4. NODE_ENV Checks

```javascript
// CRA
if (process.env.NODE_ENV === 'development') { }
if (process.env.NODE_ENV === 'production') { }

// Vite
if (import.meta.env.DEV) { }
if (import.meta.env.PROD) { }
```

## File Structure Changes

| File | Change |
|------|--------|
| `public/index.html` | Moved to `index.html` (root) |
| `src/index.js` | Entry point now in `index.html` via `<script type="module" src="/src/main.jsx">` |
| `src/main.jsx` | New entry point for Vite |

## Testing

### Vitest (New)
```bash
npm run test
```

### Jest/CRA (Legacy)
```bash
npm run test:cra
```

## Vercel Deployment

Update your Vercel project settings:

1. **Build Command**: `npm run build` (or `vite build`)
2. **Output Directory**: `build`
3. **Install Command**: `npm install`

Environment variables in Vercel should use `VITE_` prefix.

## Troubleshooting

### "process is not defined" Error

This means code is using `process.env` which doesn't exist in Vite. Update to `import.meta.env`.

### Module Not Found

Vite requires explicit file extensions for some imports. Add `.js` or `.jsx` if needed:

```javascript
// May fail
import Component from './Component';

// Works
import Component from './Component.jsx';
```

### CSS/SCSS Issues

Vite handles CSS differently. If you have issues:

```javascript
// Direct import works
import './styles.css';

// For CSS modules
import styles from './styles.module.css';
```

## Rollback to CRA

If needed, you can revert to CRA:

1. Remove `"type": "module"` from `package.json`
2. Update scripts back to use `react-scripts`
3. Delete `vite.config.js`, `vitest.config.js`, `index.html` (root), and `src/main.jsx`
4. Remove `vite`, `@vitejs/plugin-react`, and `vitest` from devDependencies
