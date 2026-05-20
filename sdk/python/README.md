# Perennia AI — Python SDK

Official Python client for the [Perennia AI](https://perenniaai.com)
mortgage-loan operating system.

## Install

```bash
pip install perennia-ai
```

The SDK is stdlib-only — no third-party runtime dependencies.

## Quick start

```python
from perennia_ai import Client

client = Client(api_key="sk_live_...")

# Leads
for lead in client.leads.list(limit=25)["data"]:
    print(lead["id"], lead["email"])

print(client.leads.get("lead_123"))

# Loans
print(client.loans.list(stage="UNDERWRITING"))
print(client.loans.get(42))

# Calls
print(client.calls.list(limit=10))
```

## Authentication

Every request sends `Authorization: Bearer <api_key>`. Issue API keys
from the Perennia dashboard under **Settings → API Keys**.

## Errors

All non-2xx responses raise `perennia_ai.PerenniaError` with the HTTP
status and response body attached:

```python
from perennia_ai import Client, PerenniaError

try:
    client.loans.get(999999)
except PerenniaError as exc:
    print(exc.status, exc.body)
```

## Versioning

The SDK follows semver. The current version is `0.1.0` (alpha — the
endpoint surface is intentionally small).
