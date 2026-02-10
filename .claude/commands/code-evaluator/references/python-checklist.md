# Python / FastAPI Checklist

## Correctness

- [ ] All `async def` endpoints actually `await` their async calls (no fire-and-forget unless intentional)
- [ ] `await` is not used on synchronous functions (causes subtle bugs, not always an error)
- [ ] All DB sessions are properly closed/committed — check for missing `finally` blocks or context manager usage
- [ ] SQLAlchemy sessions are not shared across async tasks (session-per-request pattern)
- [ ] `Optional[]` fields have proper `None` checks before access
- [ ] List/dict comprehensions don't silently swallow exceptions
- [ ] `datetime` comparisons use timezone-aware objects consistently (no naive vs aware mixing)
- [ ] String formatting doesn't break on `None` values (f-strings with `{obj.attr}` when obj may be None)
- [ ] Return types match function signatures — especially watch for `Optional` returns without handling
- [ ] Default mutable arguments (`def foo(items=[])`) — classic Python gotcha
- [ ] Integer division where float was intended (`//` vs `/`)
- [ ] Dict `.get()` returns `None` by default — check if caller handles this

## Async / Concurrency

- [ ] No blocking I/O in async functions (file reads, `requests.get`, `time.sleep`)
  - Use `aiofiles`, `httpx.AsyncClient`, `asyncio.sleep` instead
- [ ] `asyncio.gather()` has proper error handling (`return_exceptions=True` or try/except)
- [ ] No `asyncio.run()` inside already-running event loop
- [ ] Connection pools are properly sized (DB pool, HTTP client pool)
- [ ] Background tasks don't hold references to request-scoped objects
- [ ] WebSocket handlers have proper cleanup on disconnect
- [ ] Rate limiters and semaphores are used where appropriate for external API calls
- [ ] `async for` is used for async iterators, not regular `for`

## FastAPI Specific

- [ ] Dependency injection is used for DB sessions, auth, config (not global state)
- [ ] `Depends()` functions are async if they do I/O
- [ ] Request validation uses Pydantic models (not manual dict parsing)
- [ ] Response models are defined (`response_model=`) to prevent data leakage
- [ ] Path parameters are typed correctly (`{id: int}` not just `{id}`)
- [ ] Query parameters have sensible defaults and validation (`Query(ge=0, le=100)`)
- [ ] Background tasks use `BackgroundTasks` parameter, not manual thread spawning
- [ ] CORS middleware is configured with explicit origins (not `["*"]` in production)
- [ ] Exception handlers return consistent error shapes
- [ ] Startup/shutdown lifespan events properly init and cleanup resources
- [ ] File uploads validate size and content type
- [ ] Streaming responses properly handle client disconnection

## SQLAlchemy / Database

- [ ] N+1 queries: Check for loops that execute queries (use `joinedload`, `selectinload`)
- [ ] Missing indexes on columns used in WHERE, JOIN, ORDER BY
- [ ] Transactions wrap related operations atomically
- [ ] `session.commit()` is followed by error handling for IntegrityError, etc.
- [ ] Bulk operations use `bulk_insert_mappings` or `insert().values()`, not loops
- [ ] Soft deletes check `is_deleted` / `deleted_at` in all queries (not just some)
- [ ] Pagination uses `offset/limit` or keyset pagination (not loading all records)
- [ ] Raw SQL is parameterized (no f-string interpolation in queries)
- [ ] Alembic migrations are reversible (has `downgrade()`)
- [ ] Migration doesn't lock tables for extended periods on large datasets
- [ ] Enum columns match Python enum values exactly

## Error Handling

- [ ] Bare `except:` or `except Exception:` without re-raise or logging
- [ ] HTTP exceptions use appropriate status codes (not everything is 500)
- [ ] Validation errors return 422 with field-level details
- [ ] External API failures have retry logic with backoff
- [ ] Database connection failures have proper fallback/retry
- [ ] Background task failures are logged and don't crash the worker
- [ ] Errors include enough context for debugging (request ID, user ID, operation)
- [ ] No sensitive data in error messages (passwords, tokens, full SQL queries)

## Type Safety

- [ ] All function signatures have type hints
- [ ] Pydantic models use proper field types (not `Any`)
- [ ] `Union` types are narrowed before access
- [ ] `TypeVar` and `Generic` are used correctly for reusable components
- [ ] `cast()` usage is justified (not hiding type errors)
- [ ] Return type `None` is explicit when function has no meaningful return

## Environment & Configuration

- [ ] Secrets loaded from env vars, not hardcoded
- [ ] `.env` files are in `.gitignore`
- [ ] Config validation happens at startup (fail fast)
- [ ] Default values for optional config are sensible
- [ ] Different configs for dev/staging/production
- [ ] API keys and tokens are not logged
