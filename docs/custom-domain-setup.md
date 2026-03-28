# Custom Domain Setup for White-Label Portals

Enterprise clients can host their borrower portal at their own domain
(e.g., `portal.acmemortgage.com`) instead of the default Perennia URL.
SSL is provisioned automatically via Vercel once DNS verification passes.

---

## Prerequisites

- An active white-label configuration (Admin → White-Label Settings).
- Access to your domain's DNS records (usually through your registrar or
  Cloudflare, Route 53, etc.).
- Platform admin, site admin, or admin role in Perennia.

---

## Setup Steps

### Step 1: Open White-Label Settings

Go to **Admin → White-Label → Custom Domain** in the Perennia dashboard.

### Step 2: Enter Your Domain

Type the subdomain you want to use — for example, `portal.acmemortgage.com`.
Do **not** include `https://`. Click **Setup Domain**.

The API call made is:

```
POST /api/v1/admin/custom-domain/setup
Body: { "domain": "portal.acmemortgage.com" }
```

You will receive a verification token such as:

```
perennia-verify=a1b2c3d4e5f6...
```

### Step 3: Add DNS Records

Log in to your DNS provider and add **two** records:

#### 3a. TXT Record (Ownership Verification)

| Field  | Value                                          |
|--------|------------------------------------------------|
| Type   | `TXT`                                          |
| Name   | `_perennia-verify.portal.acmemortgage.com`     |
| Value  | `perennia-verify=a1b2c3d4e5f6...` (your token) |
| TTL    | 300 (5 minutes) or your provider's default     |

#### 3b. CNAME Record (Traffic Routing)

| Field  | Value                    |
|--------|--------------------------|
| Type   | `CNAME`                  |
| Name   | `portal.acmemortgage.com`|
| Value  | `cname.vercel-dns.com`   |
| TTL    | 300 or default           |

> **Note:** Some DNS providers require you to enter only the subdomain
> portion (`portal`) for the Name field rather than the fully qualified
> domain name. Check your provider's documentation.

### Step 4: Click Verify

After adding the DNS records, return to Perennia and click **Verify Domain**.
The API call made is:

```
POST /api/v1/admin/custom-domain/verify
```

DNS propagation typically takes **a few minutes** but can take up to 48 hours.
If verification fails, wait a few minutes and try again.

### Step 5: Wait for SSL Provisioning

Once your domain is verified, SSL certificate provisioning begins automatically
(usually **under 5 minutes**). You can monitor progress at:

```
GET /api/v1/admin/custom-domain/status
```

The `ssl_status` field progresses through: `pending` → `provisioning` → `active`.

Once `ssl_status` is `active`, your borrower portal is live at your custom domain.

---

## Removing a Custom Domain

To remove the custom domain:

```
DELETE /api/v1/admin/custom-domain
```

Or use **Admin → White-Label → Custom Domain → Remove Domain** in the dashboard.

This clears the domain from Perennia and removes it from the SSL infrastructure.
You can then delete the DNS records from your provider.

---

## Troubleshooting

### Verification keeps failing

- **Check the TXT record name.** It must be `_perennia-verify.` prepended to
  your full domain. For `portal.acmemortgage.com` the name is
  `_perennia-verify.portal.acmemortgage.com`.
- **Check the TXT record value.** It must match exactly what was returned by
  `/setup`, including the `perennia-verify=` prefix.
- **Wait longer.** DNS propagation can take up to 48 hours in rare cases.
  Use a tool like [dnschecker.org](https://dnschecker.org) to check global
  propagation.

### SSL status is stuck on `provisioning`

- Confirm the CNAME record is pointing to `cname.vercel-dns.com` and has
  propagated globally.
- If you used an A record instead of a CNAME, SSL provisioning may fail.
  Switch to a CNAME if possible.
- Contact support if `provisioning` persists for more than 30 minutes after
  the CNAME has propagated.

### Domain shows `ssl_status: failed`

- Remove the domain (`DELETE /api/v1/admin/custom-domain`) and re-run setup.
- Ensure no conflicting DNS records exist (e.g., an A record and a CNAME for
  the same name).

### CNAME conflicts with root domain

Bare/apex domains (e.g., `acmemortgage.com` with no subdomain) cannot use
CNAME records per DNS standards. Use a subdomain instead
(e.g., `portal.acmemortgage.com`).

---

## API Reference

| Method   | Endpoint                                  | Description                          |
|----------|-------------------------------------------|--------------------------------------|
| `POST`   | `/api/v1/admin/custom-domain/setup`       | Register domain, receive TXT token   |
| `POST`   | `/api/v1/admin/custom-domain/verify`      | Run DNS lookup, trigger SSL          |
| `GET`    | `/api/v1/admin/custom-domain/status`      | Poll domain & SSL status             |
| `DELETE` | `/api/v1/admin/custom-domain`             | Remove domain and revoke SSL         |

All endpoints require an **admin**, **site_admin**, or **platform_admin** role.
