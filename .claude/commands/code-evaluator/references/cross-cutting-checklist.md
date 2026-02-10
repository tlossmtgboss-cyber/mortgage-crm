# Cross-Cutting Concerns Checklist

## Security

### Authentication & Authorization
- [ ] All endpoints require authentication unless explicitly public
- [ ] Authorization checks happen at the endpoint level (not just middleware)
- [ ] Role-based access control is enforced server-side (not client-only)
- [ ] JWT tokens have reasonable expiration (access: 15-60min, refresh: 7-30 days)
- [ ] Token refresh flow handles race conditions (multiple tabs refreshing simultaneously)
- [ ] Password reset tokens are single-use and time-limited
- [ ] Session invalidation works on password change
- [ ] API keys are scoped to minimum required permissions
- [ ] Multi-tenancy: Data queries filter by tenant/organization ID at the query level
- [ ] Admin endpoints have additional auth layer (not just role check)

### Input Validation & Injection
- [ ] All user input validated server-side (client validation is UX only)
- [ ] SQL queries use parameterized queries (no string interpolation)
- [ ] NoSQL queries are parameterized (MongoDB injection is real)
- [ ] File paths are validated to prevent path traversal (`../../../etc/passwd`)
- [ ] Email addresses are validated before sending (prevent header injection)
- [ ] URL redirects validate against allowlist (open redirect prevention)
- [ ] XML parsing disables external entities (XXE prevention)
- [ ] Regular expressions are tested for ReDoS (catastrophic backtracking)
- [ ] GraphQL queries have depth/complexity limits

### Data Protection
- [ ] PII is encrypted at rest and in transit
- [ ] Sensitive fields are excluded from logs (SSN, passwords, tokens)
- [ ] API responses don't leak internal IDs, stack traces, or system info
- [ ] Database backups are encrypted
- [ ] File uploads scan for malware and validate content type
- [ ] Temporary files are cleaned up after processing
- [ ] CORS is configured with specific origins (not wildcard in production)
- [ ] HTTP security headers are set (HSTS, X-Content-Type-Options, X-Frame-Options)
- [ ] Cookies have `Secure`, `HttpOnly`, `SameSite` attributes

### Secrets Management
- [ ] No hardcoded secrets, API keys, or passwords in code
- [ ] Secrets loaded from environment variables or secrets manager
- [ ] `.env` files excluded from version control
- [ ] Different secrets for dev/staging/production
- [ ] Secrets are rotated periodically
- [ ] Leaked secrets are revoked immediately, not just rotated

## API Design

### Contracts & Consistency
- [ ] HTTP methods match semantics (GET=read, POST=create, PUT=replace, PATCH=update, DELETE=remove)
- [ ] Status codes are appropriate (201 for create, 204 for delete, 409 for conflict)
- [ ] Error responses have consistent shape (`{error: {code, message, details}}`)
- [ ] Pagination is consistent across all list endpoints
- [ ] Datetime fields use ISO 8601 format with timezone
- [ ] IDs are consistent type across the API (all UUID or all integer)
- [ ] Null vs absent fields have clear semantics
- [ ] API versioning strategy is applied consistently

### Robustness
- [ ] Rate limiting on public and authenticated endpoints
- [ ] Request size limits are configured
- [ ] Timeout configuration for upstream service calls
- [ ] Circuit breaker pattern for external dependencies
- [ ] Idempotency keys for payment and mutation endpoints
- [ ] Webhook delivery has retry with exponential backoff
- [ ] Long-running operations use async pattern (return 202, poll for status)

### Documentation
- [ ] OpenAPI/Swagger spec is generated and up to date
- [ ] Request/response examples for all endpoints
- [ ] Error codes are documented with resolution steps
- [ ] Authentication requirements are documented per endpoint

## Database

### Query Performance
- [ ] Indexes exist for all frequently queried columns
- [ ] Composite indexes match query patterns (column order matters)
- [ ] No `SELECT *` in production queries (select only needed columns)
- [ ] Queries use `EXPLAIN ANALYZE` to verify plan
- [ ] Pagination doesn't use `OFFSET` for large datasets (use keyset)
- [ ] COUNT queries on large tables are estimated, not exact
- [ ] Full-text search uses proper indexes (not `LIKE '%term%'`)
- [ ] Connection pool size matches expected concurrency

### Data Integrity
- [ ] Foreign keys are defined at the database level
- [ ] Unique constraints prevent duplicate data
- [ ] NOT NULL constraints on required fields
- [ ] Check constraints for enum-like columns
- [ ] Transactions wrap multi-table operations
- [ ] Optimistic locking for concurrent updates (version column)
- [ ] Soft deletes don't break unique constraints (partial unique index on non-deleted)
- [ ] Timestamps use UTC consistently

### Migrations
- [ ] Migrations are reversible (downgrade path exists)
- [ ] Large table migrations use batching (don't lock for minutes)
- [ ] Column renames/deletes are backward compatible (deploy app first, then migrate)
- [ ] Default values for new NOT NULL columns
- [ ] Index creation uses `CONCURRENTLY` on PostgreSQL
- [ ] Data migrations are separate from schema migrations

## Observability

### Logging
- [ ] Structured logging (JSON, not free-text)
- [ ] Request ID propagated through all logs
- [ ] Log levels used correctly (ERROR for failures, WARN for degraded, INFO for operations, DEBUG for details)
- [ ] No sensitive data in logs
- [ ] Performance-critical paths log timing
- [ ] External API calls log request/response (sanitized)

### Monitoring
- [ ] Health check endpoint exists and checks dependencies
- [ ] Error rate alerting configured
- [ ] Latency percentiles tracked (p50, p95, p99)
- [ ] Queue depth and processing rate monitored
- [ ] Disk space, memory, CPU monitored
- [ ] Database connection pool utilization tracked
- [ ] External API dependency health monitored

## Deployment & Infrastructure

- [ ] Environment variables validated at startup (fail fast on missing config)
- [ ] Graceful shutdown handles in-flight requests
- [ ] Health checks differentiate readiness vs liveness
- [ ] Rollback plan exists and is tested
- [ ] Feature flags for risky changes
- [ ] Database migrations run before app deployment
- [ ] Static assets are cache-busted (content hash in filename)
- [ ] HTTPS enforced everywhere (no mixed content)
