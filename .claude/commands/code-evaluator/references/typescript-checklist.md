# TypeScript / React Checklist

## Correctness

- [ ] `null` and `undefined` are handled before property access (use optional chaining `?.` or guards)
- [ ] Array methods (`.map`, `.filter`, `.find`) handle empty arrays correctly
- [ ] `.find()` return value checked for `undefined` before use
- [ ] Object spread doesn't silently override important properties (`{...defaults, ...userInput}` order matters)
- [ ] `===` used instead of `==` (except intentional `== null` checks)
- [ ] `parseInt()` includes radix parameter (`parseInt(str, 10)`)
- [ ] `JSON.parse()` is wrapped in try/catch
- [ ] Array index access checks bounds (no `arr[i]` without length check)
- [ ] `Promise.all()` handles partial failures appropriately
- [ ] `Date` constructors handle timezone correctly
- [ ] `typeof` checks are correct (`typeof null === 'object'` gotcha)
- [ ] Numeric operations handle `NaN` and `Infinity`
- [ ] String `.includes()` / `.indexOf()` handles case sensitivity correctly

## React Specific

- [ ] `useEffect` dependencies are complete and correct (no stale closures)
- [ ] `useEffect` cleanup function handles component unmount
- [ ] `useMemo` / `useCallback` dependencies are correct
- [ ] State updates in loops use functional form (`setCount(prev => prev + 1)`)
- [ ] No state updates after unmount (cancel async operations in cleanup)
- [ ] `key` prop is stable and unique (not array index for dynamic lists)
- [ ] Conditional rendering handles all states (loading, error, empty, data)
- [ ] Forms handle submission correctly (prevent double submit, loading states)
- [ ] Event handlers don't create new function references on every render (unless memoized)
- [ ] Context providers are positioned correctly in the tree (not too high, not too low)
- [ ] Large lists use virtualization (`react-window`, `react-virtuoso`)
- [ ] Images have `alt` attributes, buttons have accessible labels
- [ ] Error boundaries wrap critical UI sections
- [ ] `dangerouslySetInnerHTML` is sanitized

## State Management

- [ ] Server state vs client state are separated (React Query / SWR for server state)
- [ ] Optimistic updates have rollback on failure
- [ ] Cache invalidation happens after mutations
- [ ] Global state is minimized (prefer local state + prop drilling for simple cases)
- [ ] State shape is normalized (no deeply nested objects that cause re-render cascading)
- [ ] Loading/error/success states are tracked for all async operations
- [ ] Race conditions in search/filter (debounce + cancel previous request)

## API Integration

- [ ] API calls have proper error handling (not just `.catch(console.error)`)
- [ ] Request cancellation on component unmount (`AbortController`)
- [ ] Auth tokens are refreshed before they expire
- [ ] API responses are validated/typed (not cast with `as`)
- [ ] Retry logic for transient failures (network errors, 503s)
- [ ] Loading indicators for all async operations
- [ ] Pagination/infinite scroll handles edge cases (empty pages, concurrent requests)
- [ ] File uploads validate size and type client-side before sending
- [ ] API base URL comes from environment config, not hardcoded

## Type Safety

- [ ] No `any` types (use `unknown` + type guards instead)
- [ ] No non-null assertions (`!`) without justification
- [ ] Generic types are constrained where appropriate (`T extends BaseType`)
- [ ] Discriminated unions used for variant types (not string literals + type casting)
- [ ] API response types match actual backend response shape
- [ ] Event handler types are correct (`React.ChangeEvent<HTMLInputElement>` not `any`)
- [ ] Props interfaces are exported for reusable components
- [ ] Enum vs union type chosen intentionally (prefer unions for most cases)
- [ ] `as const` used for literal types where appropriate
- [ ] Index signatures (`[key: string]: T`) are avoided in favor of explicit types

## Performance

- [ ] Bundle size: No unnecessary large imports (`import _ from 'lodash'` → `import debounce from 'lodash/debounce'`)
- [ ] Code splitting with `React.lazy()` for route-level components
- [ ] Images are optimized and lazy-loaded
- [ ] `React.memo()` on components that receive stable props but re-render due to parent
- [ ] Expensive computations use `useMemo`
- [ ] Debounced inputs for search/filter
- [ ] No layout thrashing (reading then writing DOM in loops)
- [ ] CSS animations use `transform` and `opacity` (GPU-accelerated)
- [ ] Web Workers for CPU-intensive tasks (PDF parsing, data transformation)

## Error Handling

- [ ] Global error boundary catches unhandled React errors
- [ ] Async errors are caught and displayed to user (not silent failures)
- [ ] Form validation shows field-level errors
- [ ] Network errors show retry option
- [ ] 401/403 responses redirect to login or show appropriate message
- [ ] Error messages are user-friendly (not raw API error text)
- [ ] Errors are logged to monitoring service (Sentry, etc.)

## Security (Client-Side)

- [ ] User input is sanitized before rendering (XSS prevention)
- [ ] Auth tokens stored in httpOnly cookies (not localStorage for sensitive apps)
- [ ] No sensitive data in URL parameters
- [ ] CSRF protection on state-changing requests
- [ ] Content Security Policy headers configured
- [ ] No secrets in client-side code (API keys, passwords)
- [ ] `rel="noopener noreferrer"` on external links with `target="_blank"`
- [ ] File download filenames are sanitized
