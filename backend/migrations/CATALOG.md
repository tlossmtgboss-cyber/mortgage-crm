# Migration Catalog — Perennia AI Backend

Produced by Stage B5 audit (2026-06-18).

## Summary

| Category | Count |
|---|---|
| Python migration files | 296 |
| SQL migration files | 34 |
| **Total** | **330** |
| Referenced by startup path | 86 |
| Referenced by on-demand routes/scripts only | 61 |
| Orphaned — never called | 183 |
| Dangerous orphaned (DROP/DELETE) | 5 flagged below |

**Startup path** = `startup_migrations.py`, `database/init_db.py`, `start.py`,
`database/init/external_migrations.py`.

---

## REFERENCED — Active (startup path)

These 86 modules are imported at every server boot. They must stay in place until
`SKIP_LEGACY_MIGRATIONS` is flipped (Stage B4).

| Module | Purpose |
|---|---|
| `2026_04_25_pos_tables` | POS (point-of-sale) portal table creation |
| `add_accounting_tables` | Billing/accounting schema |
| `add_agent_memory_tables` | Agent memory store (conversations, context, embeddings) |
| `add_agent_memory_unique_indexes` | Unique indexes on agent memory tables |
| `add_ai_autonomy_tables` | Autonomous agent execution tracking |
| `add_ai_benchmark_tables` | AI classification accuracy benchmarking datasets |
| `add_all_missing_columns` | Catch-all column backfill for legacy tables |
| `add_app_completion_tables` | Application Completion Orchestrator (ACO) |
| `add_application_events_table` | Borrower application lifecycle events |
| `add_appointment_active_partial_index` | Partial index for active appointments |
| `add_aus_submission_table` | Automated Underwriting System submission tracking |
| `add_autonomous_agent_runs` | Autonomous agent run history |
| `add_briefing_preferences` | Morning briefing user preference columns |
| `add_business_rules_table` | Database-backed configurable business rules |
| `add_call_intelligence_columns` | Call intelligence enrichment columns |
| `add_call_intelligence_expansion` | Extended call intelligence schema |
| `add_call_monitoring_system` | Real-time call monitoring tables |
| `add_ci_enhancement_columns` | Call intelligence enhancement columns (phase 2) |
| `add_compliance_decision_log` | TCPA/DNC/calling-hours immutable decision log |
| `add_content_marketing_tables` | Content marketing campaign tables |
| `add_decision_audit_tables` | Append-only decision audit trail |
| `add_device_tokens_table` | Mobile push notification device tokens |
| `add_disposition_tracking` | Recruiting disposition tracking columns |
| `add_document_cache_table` | Hash-based AI document processing cache |
| `add_document_extraction_tables` | Document extraction result tables |
| `add_eclosing_table` | eClosing session tables (Snapdocs/Pavaso/NotaryCam) |
| `add_eeoc_nmls_candidate_fields` | EEOC and NMLS fields on recruiting candidates |
| `add_encompass_columns` | Encompass LOS sync columns on Loan model |
| `add_engagement_tables` | Lead engagement event tracking |
| `add_esign_tables` | E-signature envelope/recipient/field tables |
| `add_guideline_updates_tables` | Regulatory guideline update tracking |
| `add_guideline_vector_columns` | Vector embedding columns on guidelines |
| `add_hnsw_index_agent_memories` | HNSW vector index for agent memory retrieval |
| `add_lead_assignment_tables` | Lead assignment configuration and audit |
| `add_media_s3_keys_columns` | S3 key columns for media attachments |
| `add_morning_briefings` | Morning briefing content table |
| `add_multi_tenant_organization_id` | Organization ID backfill for multi-tenancy |
| `add_org_id_recruiting_tables_v2` | Org ID columns on recruiting tables (v2) |
| `add_performance_indexes` | Performance-critical composite indexes |
| `add_pii_audit_log_table` | PII access audit log (SOC 2) |
| `add_pos_consent_tables` | POS TCPA consent tables |
| `add_post_closing_workflow` | Post-closing automation workflow tables |
| `add_push_notification_preferences` | Mobile push notification preference settings |
| `add_recruit_ai_audit_log` | AI decision audit log for recruiting |
| `add_recruit_ai_audit_log_fields` | Additional fields on recruit AI audit log |
| `add_recruit_assessment_tables` | Recruiting assessment and scoring tables |
| `add_recruit_calendar_tables` | Recruiting calendar/interview scheduling |
| `add_recruit_workflow_config` | Workflow configuration for recruiting pipelines |
| `add_scheduler_audit_immutability` | Immutability constraints on scheduler audit log |
| `add_scheduler_indexes` | Performance indexes on scheduler tables |
| `add_score_gate_bypass_log` | Score gate bypass audit log |
| `add_security_training_table` | Security training records (SOC 2 CC1.4) |
| `add_smart_docs_missing_columns` | Missing column backfill for Smart Docs tables |
| `add_smart_docs_sla` | Smart Docs SLA configuration and tracking |
| `add_sms_ai_conversations` | AI-driven SMS conversation state tables |
| `add_sms_compliance_tables` | SMS compliance (TCPA/DNC) tables |
| `add_sms_consent_proof_columns` | Consent proof columns on SMS records |
| `add_sms_conv_unique_index` | Unique index on SMS conversation identifiers |
| `add_sms_delivery_tracking` | SMS delivery status tracking |
| `add_sms_persistence_tables` | DB-backed SMS campaign and scheduled job state |
| `add_sms_task_tables` | SMS task queue tables |
| `add_social_tokens_org_id` | Org ID on social OAuth token records |
| `add_stage_history_table` | Lead/loan stage change history |
| `add_subscription_modules` | Subscription module feature flags |
| `add_tcpa_consents_table` | TCPA consent records |
| `add_training_instructions_table` | AI training instruction records |
| `add_trigram_indexes` | pg_trgm trigram indexes for search |
| `add_vapi_tables` | Vapi AI voice assistant tables |
| `add_voice_workflows_table` | Voice workflow automation tables |
| `add_voicemail_sms_followup_columns` | SMS follow-up columns on voicemail drop records |
| `add_workflow_flowchart` | Visual workflow flowchart node/edge tables |
| `backfill_client_files` | Backfill client file aggregate root records |
| `consolidate_oauth_tokens` | Merge fragmented OAuth token tables |
| `create_briefing_thread_tables` | Morning briefing reply thread tables |
| `create_ops_sweep_results` | Operations sweep result tables |
| `create_social_oauth_tables` | Social media OAuth credential tables |
| `create_social_recruiting_tables` | Social recruiting (LinkedIn/etc.) tables |
| `deploy_soc2_tables` | SOC 2 compliance table deployment |
| `enable_recruiting_rls` | Row-level security on recruiting tables |
| `enable_scheduler_rls` | Row-level security on scheduler tables |
| `enterprise_challenge_tables` | Enterprise challenge/audit tables |
| `fix_smart_docs_requests_schema` | Schema fix for Smart Docs requests table |
| `hash_api_keys` | Bcrypt-hash existing plaintext API keys |
| `migration_tracker` | Migration tracking/idempotency table |
| `seed_campaign_templates` | Seed default marketing campaign templates |
| `sync_tasktype_enum` | Sync task_type enum values to match model |

---

## DANGEROUS — Review Before Archiving

Five orphaned files contain `DROP TABLE` or `DELETE FROM` operations. Do NOT
`git mv` these to `_archive/` without first confirming the target tables are
empty or intentionally absent in production.

| Module | Dangerous Operation |
|---|---|
| `add_circle_of_cashflow` | `DROP TABLE ... CASCADE` on `partner_touchpoints`, `referrals`, `referral_opportunities`, `referral_partners`, `mortgage_questionnaires` |
| `create_mum_tables` | `DROP TABLE ... CASCADE` on `mum_transactions`, `mum_clients` |
| `fix_access_certifications_schema` | `DROP TABLE ... CASCADE` on `access_certifications` |
| `create_mortgage_glossary` | `DROP TABLE` on `mortgage_glossary` |
| `add_audit_events_table` | `DELETE` cleanup for `mobile_audit_events` |

Note: `add_circle_of_cashflow`, `create_mum_tables`, and `create_mortgage_glossary`
are imported by on-demand routes in `migrations_api.py` or `mum_api_routes.py`,
not at startup. The DROP statements are in their `downgrade()` / cleanup blocks —
verify they are never called by accident before archiving.

---

## ORPHANED — Safe to Archive

Approximately **183** remaining Python migration files (and all 34 SQL files which
have no Python callers) are never imported by any application code. They are
candidates for:

```
git mv backend/migrations/<name>.py backend/migrations/_archive/
```

**Prerequisites before bulk archival (Stage B5):**

1. **Stage B4 first** — flip `SKIP_LEGACY_MIGRATIONS=true` in Railway staging
   and confirm the server boots cleanly with zero migration errors.
2. Review the 5 dangerous files above individually.
3. Run `alembic revision --autogenerate` after archival to confirm no tables
   are lost from `target_metadata`.

---

## Next Steps

| Stage | Action |
|---|---|
| **B4** | Add `SKIP_LEGACY_MIGRATIONS=true` to Railway staging env; confirm clean boot |
| **B5** | `git mv` all 183 safe orphaned files to `migrations/_archive/` |
| **B6** | Remove `Base.metadata.create_all(engine)` from `database/init_db.py`; all schema changes flow through Alembic revisions exclusively |
