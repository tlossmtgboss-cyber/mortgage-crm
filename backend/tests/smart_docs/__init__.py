"""
Smart Docs V2 Test Suite

Regression, security, compliance, and performance tests for the
Smart Document Collection and Processing subsystem.

Test categories (via pytest markers):
    - regression:         Previously fixed bugs — must never recur
    - security:           Auth, encryption, access control
    - compliance:         TRID/RESPA/TCPA regulatory requirements
    - tenant_isolation:   Multi-org data boundary enforcement
    - income_accuracy:    Income calculation correctness
    - esign_compliance:   E-signature legal compliance
    - api_contract:       API request/response shape tests
    - performance:        Benchmark tests (skipped in CI by default)
"""
