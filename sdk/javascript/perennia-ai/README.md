# Perennia AI — JavaScript SDK

Official Node.js / browser client for the
[Perennia AI](https://perenniaai.com) mortgage-loan operating system.

## Install

```bash
npm install @perennia-ai/sdk
```

Requires Node >= 18 (built-in `fetch`) or any modern browser.

## Quick start

```js
const { Client } = require('@perennia-ai/sdk');

const client = new Client({ apiKey: 'sk_live_...' });

const leads = await client.leads.list({ limit: 25 });
const lead = await client.leads.get('lead_123');

const loans = await client.loans.list({ stage: 'UNDERWRITING' });
const loan = await client.loans.get(42);

const calls = await client.calls.list({ limit: 10 });
```

## Authentication

Every request sends `Authorization: Bearer <apiKey>`. Generate keys in
the Perennia dashboard under **Settings → API Keys**.

## Errors

Non-2xx responses throw `PerenniaError` with `status` and `body`:

```js
const { Client, PerenniaError } = require('@perennia-ai/sdk');

try {
  await client.loans.get(999999);
} catch (err) {
  if (err instanceof PerenniaError) {
    console.error(err.status, err.body);
  }
}
```

## Versioning

Semver. The current version is `0.1.0` (alpha — limited endpoint surface
that will grow with the public API).
