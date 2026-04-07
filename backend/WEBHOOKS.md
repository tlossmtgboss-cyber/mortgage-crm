# Webhook Registry

All inbound webhook endpoints in the Perennia AI backend, their external providers, authentication methods, and configuration requirements.

Last updated: 2026-04-07

---

## Telephony & Voice

| Endpoint | Provider | Auth Method | Env Variable | Idempotency | File |
|----------|----------|-------------|--------------|-------------|------|
| `POST /api/v1/telnyx/webhook` | Telnyx | Ed25519 signature (`require_telnyx_webhook`) | `TELNYX_PUBLIC_KEY` | `WebhookIdempotencyRecord` table | `routes/telnyx_webhook_routes.py` |
| `POST /api/vapi/webhook` | Vapi | HMAC shared secret (`require_vapi_webhook`) | `VAPI_WEBHOOK_SECRET` | By `call_id` | `vapi_routes.py` |
| `POST /api/vapi/webhook/assistant-request` | Vapi | HMAC shared secret (`require_vapi_webhook`) | `VAPI_WEBHOOK_SECRET` | N/A (stateless) | `vapi_routes.py` |
| `POST /api/vapi/webhook/sms` | Vapi | HMAC shared secret (`require_vapi_webhook`) | `VAPI_WEBHOOK_SECRET` | By message ID | `vapi_routes.py` |
| `POST /api/v1/retell/webhook` | Retell AI | HMAC-SHA256 (`X-Retell-Signature`) | `RETELL_WEBHOOK_SECRET` | By `call_id` | `routes/retell_webhook_routes.py` |
| `POST /api/v1/retell/webhooks/call-events` | Retell AI | Retell SDK signature verification | `RETELL_API_KEY` | By `call_id` | `routes/retell_routes.py` |
| `POST /api/v1/telnyx-retell/webhook/inbound` | Telnyx | Ed25519 signature (`require_telnyx_webhook`) | `TELNYX_PUBLIC_KEY` | N/A (call routing) | `routes/telnyx_retell_routes.py` |
| `POST /api/v1/voicemail-drops/webhook/rvm` | Slybroadcast / Drop Cowboy | Record matching (session_id/foreign_id) | None (unauthenticated) | By `session_id` / `foreign_id` | `routes/voicemail_drop_routes.py` |
| `POST /api/v1/inbound-ai/vapi-inbound-webhook` | Vapi | HMAC shared secret | `VAPI_WEBHOOK_SECRET` | By `call_id` | `routes/inbound_ai_routes.py` |
| `POST /api/v1/nl-ivr/vapi-webhook` | Vapi | Shared secret | `VAPI_WEBHOOK_SECRET` | By `call_id` | `routes/nl_ivr_routes.py` |

## Dialer / Call Control (Telnyx TeXML Callbacks)

| Endpoint | Provider | Auth Method | Env Variable | Idempotency | File |
|----------|----------|-------------|--------------|-------------|------|
| `POST /api/v1/dialer/webhook/click-to-dial-status` | Telnyx | TeXML callback secret | `TEXML_CALLBACK_SECRET` | By `call_control_id` | `telephony/router.py` |
| `POST /api/v1/dialer/webhook/status` | Telnyx | TeXML callback secret | `TEXML_CALLBACK_SECRET` | By `call_control_id` | `telephony/router.py` |
| `POST /api/v1/dialer/webhook/dial-status` | Telnyx | TeXML callback secret | `TEXML_CALLBACK_SECRET` | By `call_control_id` | `telephony/router.py` |
| `POST /api/v1/dialer/webhook/recording-complete` | Telnyx | TeXML callback secret | `TEXML_CALLBACK_SECRET` | By recording ID | `telephony/router.py` |
| `POST /api/v1/call-queues/webhook/dequeue` | Telnyx | TeXML callback | `TEXML_CALLBACK_SECRET` | By queue entry ID | `routes/call_queue_routes.py` |
| `POST /api/v1/call-queues/webhook/connect-status` | Telnyx | TeXML callback | `TEXML_CALLBACK_SECRET` | By `call_control_id` | `routes/call_queue_routes.py` |
| `POST /api/v1/conferences/webhook/participant-status` | Telnyx | TeXML callback | `TEXML_CALLBACK_SECRET` | By participant ID | `routes/conference_routes.py` |
| `POST /api/v1/conferences/webhook/conference-status` | Telnyx | TeXML callback | `TEXML_CALLBACK_SECRET` | By conference ID | `routes/conference_routes.py` |
| `POST /api/v1/call-transfers/webhook/consult-status` | Telnyx | TeXML callback | `TEXML_CALLBACK_SECRET` | By transfer ID | `routes/call_transfer_routes.py` |
| `POST /api/v1/call-routing/webhook/route-call` | Telnyx | TeXML callback | `TEXML_CALLBACK_SECRET` | By `call_control_id` | `routes/call_routing_routes.py` |

## Recruiting Dialer (Telnyx)

| Endpoint | Provider | Auth Method | Env Variable | Idempotency | File |
|----------|----------|-------------|--------------|-------------|------|
| `POST /api/v1/recruiting-dialer/telnyx/recruiter-answered/{call_id}` | Telnyx | `_verify_telnyx_webhook` dependency | `TELNYX_PUBLIC_KEY` | By `call_id` | `routes/recruiting_dialer_routes.py` |
| `POST /api/v1/recruiting-dialer/telnyx/recruiter-response/{call_id}` | Telnyx | `_verify_telnyx_webhook` dependency | `TELNYX_PUBLIC_KEY` | By `call_id` | `routes/recruiting_dialer_routes.py` |
| `POST /api/v1/recruiting-dialer/telnyx/call-complete/{call_id}` | Telnyx | `_verify_telnyx_webhook` dependency | `TELNYX_PUBLIC_KEY` | By `call_id` | `routes/recruiting_dialer_routes.py` |
| `POST /api/v1/recruiting-dialer/telnyx/status/{call_id}` | Telnyx | `_verify_telnyx_webhook` dependency | `TELNYX_PUBLIC_KEY` | By `call_id` | `routes/recruiting_dialer_routes.py` |
| `POST /api/v1/recruiting-dialer/telnyx/candidate-status/{call_id}` | Telnyx | `_verify_telnyx_webhook` dependency | `TELNYX_PUBLIC_KEY` | By `call_id` | `routes/recruiting_dialer_routes.py` |
| `POST /api/v1/recruiting-dialer/telnyx/recording/{call_id}` | Telnyx | `_verify_telnyx_webhook` dependency | `TELNYX_PUBLIC_KEY` | By `call_id` | `routes/recruiting_dialer_routes.py` |

## Billing

| Endpoint | Provider | Auth Method | Env Variable | Idempotency | File |
|----------|----------|-------------|--------------|-------------|------|
| `POST /webhooks/stripe` | Stripe | `stripe.Webhook.construct_event` | `STRIPE_WEBHOOK_SECRET` | `StripeEvent` table | `routes/stripe_webhook_routes.py` |
| `POST /api/v1/webhooks/stripe` | Stripe | `stripe.Webhook.construct_event` (via service) | `STRIPE_WEBHOOK_SECRET` | By event type dedup | `public_routes.py` |

## CRM & Lead Sources

| Endpoint | Provider | Auth Method | Env Variable | Idempotency | File |
|----------|----------|-------------|--------------|-------------|------|
| `POST /webhooks/retr/import` | RETR | HMAC-SHA256 (`X-Webhook-Signature`) | `RETR_WEBHOOK_SECRET` | None (upsert logic) | `routes/webhook_routes.py` |
| `POST /api/v1/crm-webhooks/*` | Internal CRM | HMAC-SHA256 (`X-Webhook-Signature`) | `CRM_WEBHOOK_SECRET` | None | `routes/crm_webhooks.py` |
| `POST /api/v1/speed-to-lead/webhook` | External lead sources | API key (`X-API-Key`) | `SPEED_TO_LEAD_WEBHOOK_KEY` | Duplicate check (phone+org, 24h) | `routes/speed_to_lead_routes.py` |
| `POST /webhooks/followupboss/{user_id}` | Follow Up Boss | HMAC (`X-FUB-Signature`) per user | Per-user `webhook_secret` in DB | `FUBSyncEvent` table | `routes/followupboss_webhook_routes.py` |

## Third-Party Integrations

| Endpoint | Provider | Auth Method | Env Variable | Idempotency | File |
|----------|----------|-------------|--------------|-------------|------|
| `POST /api/v1/salesforce-sync/webhook` | Salesforce | HMAC (`X-Salesforce-Signature`) | `SALESFORCE_WEBHOOK_SECRET` | None (upsert logic) | `routes/salesforce_sync_routes.py` |
| `POST /api/v1/webhooks/encompass` | Encompass LOS | HMAC-SHA256 | `ENCOMPASS_WEBHOOK_SECRET` | By event ID | `routes/los_webhook_routes.py` |
| `POST /api/v1/recallai/webhook` | Recall.ai | HMAC (`Recall-Signature`) | `RECALLAI_WEBHOOK_SECRET` | By bot ID + event | `recallai_integration.py` |
| `POST /api/v1/calendly/webhook` | Calendly | HMAC-SHA256 (`Calendly-Webhook-Signature`) | `CALENDLY_WEBHOOK_SECRET` | None | `routes/calendly_routes.py` |
| `POST /api/v1/vidyard/webhooks` | Vidyard | None (unauthenticated) | None | None | `routes/vidyard_routes.py` |

## Calendar Sync

| Endpoint | Provider | Auth Method | Env Variable | Idempotency | File |
|----------|----------|-------------|--------------|-------------|------|
| `POST /api/v1/scheduler/calendar/sync/google/webhook` | Google Calendar | Channel token verification (`X-Goog-Channel-Token`) | `GOOGLE_CALENDAR_WEBHOOK_TOKEN` | By `X-Goog-Message-Number` | `routes/scheduler/calendar_sync_inbound.py` |
| `POST /api/v1/scheduler/calendar/sync/outlook/webhook` | Microsoft Graph | Validation token echo + `clientState` | `GRAPH_WEBHOOK_SECRET` | By notification ID | `routes/scheduler/calendar_sync_inbound.py` |

## SMS & Messaging

| Endpoint | Provider | Auth Method | Env Variable | Idempotency | File |
|----------|----------|-------------|--------------|-------------|------|
| `POST /api/v1/sms-compliance/inbound-webhook` | Telnyx | None (Telnyx signature not enforced) | None | By message content | `routes/sms_compliance_routes.py` |
| `POST /api/v1/integrations/sms/webhook` | Telnyx | Webhook signature validation | `TELNYX_PUBLIC_KEY` | By `MessageSid` | `integration_routes.py` |
| `POST /api/v1/scheduler/sms/webhook` | Telnyx | Set via `set_dependencies` | Varies | By message ID | `routes/sms_scheduler_webhook.py` |
| `POST /api/v1/app-completion/comms/webhook/inbound-sms` | Telnyx | None (provider callback) | None | By message ID | `routes/app_completion_routes.py` |
| `POST /api/v1/realtor-portal/webhooks/sms` | Telnyx | Portal-level auth | None | None | `routes/realtor_portal_routes.py` |

## Email

| Endpoint | Provider | Auth Method | Env Variable | Idempotency | File |
|----------|----------|-------------|--------------|-------------|------|
| `POST /api/v1/integrations/email/webhook` | Microsoft Graph | Graph notification verification | `GRAPH_WEBHOOK_SECRET` | By notification ID | `integration_routes.py` |
| `POST /api/v1/ai-email/webhook/inbound` | Email provider | Varies | Varies | By message ID | `routes/ai_email_conversation_routes.py` |
| `POST /api/v1/conversation-intelligence/webhook/email` | Internal | Bearer token | JWT | By message ID | `routes/conversation_intelligence_routes.py` |
| `POST /api/v1/conversation-intelligence/webhook/sms` | Internal | Bearer token | JWT | By message ID | `routes/conversation_intelligence_routes.py` |

## Documents & Financial

| Endpoint | Provider | Auth Method | Env Variable | Idempotency | File |
|----------|----------|-------------|--------------|-------------|------|
| `POST /api/v1/smart-docs/eclosing/webhooks` | eClosing provider | HMAC-SHA256 (`X-Webhook-Signature`) | `ECLOSING_WEBHOOK_SECRET` | None | `routes/smart_docs_eclosing_routes.py` |
| `POST /api/v1/smart-docs/plaid/webhooks` | Plaid | Plaid signature verification | `PLAID_WEBHOOK_SECRET` | By webhook ID | `routes/smart_docs_plaid_routes.py` |
| `POST /api/v1/accounting/banks/plaid/webhook` | Plaid | Plaid signature verification | `PLAID_WEBHOOK_SECRET` | By webhook ID | `routes/accounting/bank_routes.py` |
| `POST /api/v1/credit-monitoring/webhook/credit-alert` | Credit bureau | HMAC-SHA256 (`X-Bureau-Signature`) | `CREDIT_BUREAU_WEBHOOK_SECRET` | By `provider_reference_id` | `routes/credit_monitoring_routes.py` |

## Voice AI Receptionist

| Endpoint | Provider | Auth Method | Env Variable | Idempotency | File |
|----------|----------|-------------|--------------|-------------|------|
| `POST /api/v1/voice-ai-receptionist/webhooks/*` | Vapi | `require_vapi_webhook` | `VAPI_WEBHOOK_SECRET` | By call ID | `routes/voice_ai_receptionist_routes.py` |

## Scheduler & Automation

| Endpoint | Provider | Auth Method | Env Variable | Idempotency | File |
|----------|----------|-------------|--------------|-------------|------|
| `POST /api/v1/scheduler/webhooks` | Internal | Bearer token | JWT | By event ID | `routes/scheduler/webhooks.py` |
| `POST /api/v1/rate-sheets/webhooks/call-completed` | Internal | Bearer token | JWT | None | `rate_sheet_routes.py` |
| `POST /api/v1/realtor-portal/webhooks/crm/{webhook_type}` | Internal CRM | Portal auth | Varies | None | `routes/realtor_portal_routes.py` |

---

## Authentication Methods Summary

| Method | Description | Providers Using It |
|--------|-------------|--------------------|
| **Ed25519 signature** | Telnyx signs payloads with Ed25519; verified via `TELNYX_PUBLIC_KEY` | Telnyx |
| **HMAC-SHA256** | Provider signs payload body with shared secret; header varies per provider | Retell, Stripe, Salesforce, Encompass, RETR, FUB, Calendly, eClosing, Credit Bureau |
| **Stripe SDK** | `stripe.Webhook.construct_event()` handles signature verification internally | Stripe |
| **Retell SDK** | `RetellClient.verify_webhook_signature()` with API key | Retell (inline handler) |
| **Vapi shared secret** | HMAC verification via `require_vapi_webhook` middleware dependency | Vapi |
| **Google push headers** | Channel token in `X-Goog-Channel-Token` matched against subscription records | Google Calendar |
| **MS Graph validation** | Echo `validationToken` on subscription creation; `clientState` on notifications | Microsoft Graph / Outlook |
| **API key header** | Static `X-API-Key` matched against env variable | Speed-to-Lead |
| **Record matching** | No cryptographic auth; validates by matching IDs against existing DB records | Slybroadcast, Drop Cowboy |
| **None** | Unauthenticated (should be hardened for production) | Vidyard, some SMS inbound |

## Environment Variables Checklist

All webhook-related environment variables that should be configured in production:

```
# Telephony
TELNYX_PUBLIC_KEY=             # Ed25519 public key for Telnyx webhook verification
TEXML_CALLBACK_SECRET=         # Shared secret for Telnyx TeXML callbacks
VAPI_WEBHOOK_SECRET=           # Shared secret for Vapi webhook verification
RETELL_WEBHOOK_SECRET=         # HMAC secret for Retell webhook verification
RETELL_API_KEY=                # Retell API key (also used for inline webhook signature verification)

# Billing
STRIPE_WEBHOOK_SECRET=         # Stripe webhook signing secret (whsec_...)

# CRM & Integrations
RETR_WEBHOOK_SECRET=           # HMAC secret for RETR data import webhooks
CRM_WEBHOOK_SECRET=            # HMAC secret for internal CRM webhooks
SPEED_TO_LEAD_WEBHOOK_KEY=     # API key for speed-to-lead external webhooks
SALESFORCE_WEBHOOK_SECRET=     # HMAC secret for Salesforce outbound messages
ENCOMPASS_WEBHOOK_SECRET=      # HMAC secret for Encompass LOS webhooks
RECALLAI_WEBHOOK_SECRET=       # HMAC secret for Recall.ai meeting bot webhooks
CALENDLY_WEBHOOK_SECRET=       # HMAC secret for Calendly booking webhooks

# Calendar
GOOGLE_CALENDAR_WEBHOOK_TOKEN= # Token for Google Calendar push notifications
GRAPH_WEBHOOK_SECRET=          # clientState for Microsoft Graph subscriptions

# Documents & Financial
ECLOSING_WEBHOOK_SECRET=       # HMAC secret for eClosing provider webhooks
PLAID_WEBHOOK_SECRET=          # Plaid webhook verification secret
CREDIT_BUREAU_WEBHOOK_SECRET=  # HMAC secret for credit bureau alert webhooks
```

## Adding a New Webhook Endpoint

1. Create a route handler in the appropriate route file (or a new `routes/*_webhook_routes.py` file).
2. Implement signature verification -- always fail closed (reject when secret is missing).
3. Return 200/202 immediately; process in `BackgroundTasks` or a background worker.
4. Add idempotency checks (deduplicate by event ID, call ID, or message ID).
5. Register the router in the appropriate `_register_*.py` file or `main.py`.
6. Add the endpoint to this registry.
7. Add the env variable to Railway and `.env.example`.
8. Add the webhook URL to the provider's dashboard/configuration.
