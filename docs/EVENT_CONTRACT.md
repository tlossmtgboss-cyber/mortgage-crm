# POS Event Contract

This document specifies the events the POS module publishes and any events
it expects existing handlers to consume. Subscribers should treat this as a
versioned contract — additive changes are safe; renames or removals require
a major version bump of the skill.

## Published events

### `pos.application.submitted` (POS_APPLICATION_SUBMITTED)

Emitted when a borrower clicks **Submit** on Step 9 and the transition from
`draft` → `submitted` succeeds. **This is the event the canonical-store
owner must subscribe to** — it carries everything needed to map a POS draft
into `BorrowerApplication`.

**Schema:**

```json
{
  "type": "pos.application.submitted",
  "org_id": "7",
  "data": {
    "application_id": "f24d4a8a-e1c2-4c3a-9c5e-2a4b6e8f1234",
    "loan_id": 42,
    "contact_id": 1001,
    "appointment_id": 7777,
    "submitted_at": "2026-04-25T15:32:18.123456+00:00",
    "payload": {
      "version": "pos_1003_v1",
      "sections": {
        "personal": {
          "data": { "first_name": "Alice", "last_name": "Anderson", ... },
          "is_complete": true,
          "completed_at": "2026-04-23T14:01:00+00:00"
        },
        "residence": { ... },
        "employment": { ... },
        "assets": { ... },
        "liabilities": { ... },
        "reo": { ... },
        "loan": { ... },
        "declarations": { ... },
        "review": {
          "data": {
            "acknowledged": [
              "truth_certification",
              "esign_consent",
              "credit_authorization"
            ]
          },
          "is_complete": true,
          "completed_at": "2026-04-25T15:32:18+00:00"
        }
      },
      "pii": {
        "ssn": "123-45-6789",
        "co_ssn": null,
        "dob": "1985-06-12",
        "co_dob": null
      },
      "loan_id": 42,
      "contact_id": 1001,
      "organization_id": 1,
      "workspace_id": 1,
      "source_channel": "purl_email"
    }
  }
}
```

**Subscriber responsibilities:**

1. **Map sections to BorrowerApplication.** The shape inside each section's
   `data` blob is loose. The canonical-store handler is responsible for
   mapping POS field names to the URLA columns. The skill ships a
   reference mapping sketch in `docs/SECTION_FIELD_MAPPING.md` (added by
   your dev team based on your BorrowerApplication schema).
2. **Persist PII through `EncryptedString`.** The `pii.ssn` field is in
   plaintext at this point — the in-process event bus never crosses a
   network boundary in Perennia's deployment. Write it directly to
   `BorrowerApplication.ssn_encrypted` and SQLAlchemy will encrypt at rest.
3. **Idempotency.** The handler must tolerate redelivery. Use
   `application_id` as the dedup key. A second event for the same
   application_id should be a no-op.

**Important:** the POS module does **not** delete or modify the
`pos_applications` row after publishing. The canonical store is the source
of truth post-submit, but the POS row is retained for audit and forensic
purposes. Consider archiving POS rows after some retention period (90 days
recommended).

---

### `pos.appointment.booked` (POS_APPOINTMENT_BOOKED)

Emitted when the borrower books a Smart Calendar slot from Step 9. Useful
for analytics — distinguishes POS-originated bookings from LO-originated or
public-link bookings.

**Schema:**

```json
{
  "type": "pos.appointment.booked",
  "org_id": "7",
  "data": {
    "application_id": "f24d4a8a-...",
    "appointment_id": 7777,
    "loan_id": 42,
    "loan_officer_user_id": 200,
    "meeting_type": "application_review"
  }
}
```

The existing scheduler also emits `appointment.created` at the same moment.
Consume whichever fits your dashboard.

---

## Consumed events

### `appointment.confirmed` / `appointment.cancelled`

The POS module **does not currently consume** these — the
`pos_applications.submitted_appointment_id` is set at submit time and never
updated. If you want POS to react to appointment lifecycle changes (e.g.,
clear `submitted_appointment_id` on cancellation, allow the borrower to
rebook), add subscribers in `services/pos/event_handlers.py` (not shipped
by default).

---

## Adding the new EventType members

The skill includes a runtime extension shim that adds
`POS_APPLICATION_SUBMITTED` and `POS_APPOINTMENT_BOOKED` to your `EventType`
enum at import time if they don't already exist. To make them permanent and
type-checkable, add them to the enum source:

```python
# services/event_bus.py (or wherever EventType is defined)

class EventType(str, Enum):
    # ... existing members ...

    # POS module events (added by perennia-pos-1003)
    POS_APPLICATION_SUBMITTED = "pos.application.submitted"
    POS_APPOINTMENT_BOOKED = "pos.appointment.booked"
```

Once these are part of the enum, the runtime shim becomes a no-op.
