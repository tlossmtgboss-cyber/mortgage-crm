"""Registry of all models classified by tenant scope.

Every SQLAlchemy model must be in exactly one registry. The startup health
check and CI tests validate completeness.

Classification rules:
- TENANT_SCOPED_MODELS: Has an ``organization_id`` column. RLS policies
  can filter these rows directly.
- SYSTEM_SCOPED_MODELS: No ``organization_id`` column. Either genuinely
  global (Organization, SubscriptionPlan, StateDisclosure) or scoped
  indirectly via FK to a tenant-scoped parent (e.g. BorrowerAuthEvent ->
  BorrowerProfile which has organization_id).

If a model is missing from both registries the test suite will fail,
forcing an explicit classification decision for every new model.
"""

# ---------------------------------------------------------------------------
# Models that MUST have organization_id and are subject to RLS policies
# ---------------------------------------------------------------------------
TENANT_SCOPED_MODELS: set[str] = {
    # --- core.py ---
    "Branch",
    "User",
    "ApiKey",
    "CalendarAssignment",

    # --- lead_loan.py ---
    "Lead",
    "Loan",

    # --- task.py ---
    "AITask",
    "Task",
    "EscalationRecord",
    "HandoffLog",

    # --- document.py ---
    "EmailIntake",
    "AttachmentIntake",
    "Document",

    # --- communication.py ---
    "Activity",
    "StageHistory",
    "Conversation",
    "ConversationMemory",
    "SMSMessage",
    "SMSConversation",
    "EmailMessage",
    "Email",
    "EmailDraft",
    "TeamsMessage",
    "VoicemailDrop",
    "VoicemailTemplate",
    "VoicemailCampaign",
    "CalendarEvent",
    "IntegrationLog",
    "IntegrationCredential",
    "ConversationSession",
    "EntityExtraction",
    "ChannelPreference",
    "MessageTemplate",

    # --- ai.py ---
    "AIDelegatedTask",
    "AIFeedbackLog",
    "AIAction",
    "AILearningMetric",
    "AIKnowledgeBase",
    "AIAuditLog",
    "AIColleagueAction",

    # --- referral.py ---
    "ReferralPartner",
    "MUMClient",

    # --- workflow.py ---
    "ScheduledWorkflow",
    "WorkflowExecution",
    "Workflow",

    # --- permission.py ---
    "EmployeeInvite",

    # --- security.py ---
    "AuditLog",
    "Notification",
    "DataSubjectRequest",

    # --- subscription.py (none have org_id) ---

    # --- microsoft.py ---
    "MicrosoftAppConfig",

    # --- microsoft_email.py ---
    "MicrosoftEmailToken",

    # --- estimate.py ---
    "EstimateParseCache",
    "EstimateParseFailure",
    "EstimateComparison",

    # --- platform_contract.py ---
    "PlatformContract",

    # --- refinance_intelligence.py ---
    "RefiOpportunity",
    "PortfolioMonitoringRun",

    # --- credit_monitoring.py ---
    "CreditMonitoringSubscription",
    "CreditAlert",

    # --- rate_lock.py ---
    "RateLock",
    "RateMarketData",

    # --- marketing.py ---
    "AudienceSegment",
    "CampaignDefinition",
    "DripSequence",

    # --- los_sync.py ---
    "LosFieldMapping",
    "LosSyncLog",

    # --- encompass_config.py ---
    "EncompassConfig",

    # --- compliance.py ---
    "LoanFee",
    "DisclosureEvent",
    "AdverseActionNotice",
    "ComplianceAlert",

    # --- ai_prospect_conversation.py ---
    "AIProspectConversation",
    "AIReengagementConfig",

    # --- device_token.py ---
    "DeviceToken",
    "PushNotificationPreference",

    # --- sso.py ---
    "SSOConfig",

    # --- sso_config.py ---
    "SSOConfiguration",

    # --- webhook.py ---
    "WebhookSubscription",

    # --- content_library.py ---
    "ContentLibraryItem",
    "ContentLibraryUsageLog",

    # --- document_intelligence.py ---
    "AIDocumentClassification",
    "DocumentRequirementRule",
    "POSDocumentMapping",
    "CallIntelDocumentNeed",

    # --- document_followup.py ---
    "FollowupCampaign",
    "FollowupEvent",
    "DocumentAppointment",
    "FollowupTemplate",

    # --- esignature.py ---
    "ESignatureEnvelope",
    "ESignatureTemplate",
    "ESignConsentSession",

    # --- document_security.py ---
    "DocumentAccessLog",
    "DocumentEncryptionRecord",
    "DocumentIntegrityCheck",
    "DocumentRetentionPolicy",
    "DocumentWatermarkLog",

    # --- scheduling_analytics.py ---
    "SchedulingInsight",
    "AppointmentOutcome",

    # --- decision_audit.py ---
    "DecisionAuditLog",
    "AuditRetentionConfig",
    "ArchivedDecisionAuditLog",

    # --- calendar_event_map.py ---
    "CalendarEventMap",

    # --- document_cache.py ---
    "DocumentProcessingCache",

    # --- tcpa_smart_docs.py ---
    "SmartDocsConsentRecord",
    "InternalDNCEntry",
    "OutreachLog",

    # --- business_rules.py ---
    "BusinessRuleConfig",

    # --- eclosing.py ---
    "EClosingSession",

    # --- plaid_connection.py ---
    "PlaidConnection",

    # --- aus_submission.py ---
    "AUSSubmission",

    # --- irs_transcript.py ---
    "IRSTranscriptRequest",

    # --- ai_benchmark.py ---
    "AIBenchmarkDataset",
    "AIBenchmarkSample",

    # --- document_version.py ---
    "DocumentVersion",

    # --- document_annotation.py ---
    "DocumentAnnotation",

    # --- document_search_index.py ---
    "DocumentSearchIndex",
    "SavedSearch",
    "SearchAnalyticsEvent",

    # --- batch_job.py ---
    "BatchJob",

    # --- document_template.py ---
    "DocumentTemplate",
    "DocumentGenerationLog",

    # --- document_archive.py ---
    "DocumentArchive",

    # --- escalation_rule.py ---
    "SmartDocsEscalationRule",
    "SmartDocsEscalationEvent",

    # --- followup_cadence.py ---
    "FollowupCadence",
    "FollowupExecution",

    # --- white_label_config.py ---
    "WhiteLabelConfig",
    "SmartDocsEmailTemplate",

    # --- doc_sla_config.py ---
    "DocSLAConfig",
    "DocSLATracking",

    # --- lead_assignment.py ---
    "LeadAssignmentConfig",
    "LeadAssignmentRule",
    "LeadAssignmentPool",
    "LeadAssignmentException",
    "LeadAssignmentAuditLog",

    # --- routing_rule.py ---
    "RoutingRule",
    "ProcessingQueue",
    "RoutingAuditLog",

    # --- approval_chain.py ---
    "ApprovalChainConfig",
    "ApprovalRequest",
    "ApprovalDelegation",

    # --- doc_field_mapping.py ---
    "FieldMappingConfig",
    "CustomField",

    # --- recurring_availability.py ---
    "RecurringAvailability",
    "AvailabilityException",
    "AvailabilityTemplate",

    # --- reminder_config.py ---
    "ReminderTemplate",

    # --- waiting_room.py ---
    "WaitlistEntry",

    # --- reschedule_history.py ---
    "RescheduleHistory",

    # --- appointment_template.py ---
    "AppointmentTemplate",

    # --- calendar_label.py ---
    "CalendarLabel",

    # --- calendar_feed.py ---
    "CalendarFeedToken",

    # --- appointment_survey.py ---
    "AppointmentSurvey",

    # --- appointment_location.py ---
    "AppointmentLocation",

    # --- cancellation_policy.py ---
    "CancellationPolicy",

    # --- app_completion.py ---
    "ApplicationCompletenessReview",
    "MissingItem",
    "DocumentStagingRequest",
    "BorrowerCommunicationLog",
    "AppointmentCoordination",
    "ApplicationScoreHistory",

    # --- scheduler.py ---
    "SchedulerConfig",
    "AvailabilitySlot",
    "SchedulerAppointmentType",
    "SchedulerAppointment",
    "SchedulerRoutingRule",
    "BlockedTime",
    "BookingLink",
    "SchedulerAppointmentReminder",
    "AppointmentStatusHistory",
    "SchedulerAuditLog",
    "SlotHold",

    # --- agent_metrics.py ---
    "AgentInvocation",

    # --- compliance_log.py ---
    "ComplianceDecisionLog",

    # --- consent_audit.py ---
    "ConsentAuditLog",

    # --- sms_persistence.py ---
    "SMSCampaignRecord",
    "ScheduledSMSJobRecord",

    # --- morning_briefing.py ---
    "MorningBriefing",

    # --- security_training.py ---
    "SecurityTrainingRecord",

    # --- sms_delivery.py ---
    "SMSDeliveryLog",

    # --- sms_panel_message.py ---
    "SMSPanelMessage",

    # --- voice_consent.py ---
    "VoiceConsent",

    # --- borrower.py ---
    "BorrowerProfile",
    "BorrowerApplication",

    # --- dialer.py ---
    "AgentTelephonySettings",
    "VerifiedCallerId",
    "DialerSession",
    "DialerSessionTask",
    "CallLog",
    "ActiveCall",
    "ContactDNCStatus",

    # --- iMessage / BlueBubbles ---
    "IMessageLine",
    "IMessageThread",
    "IMessageMessage",
    "IMessageWebhookLog",

    # --- team_chat.py ---
    "TeamChatChannel",
    "TeamChatMessage",
    "TeamChatReaction",
    "TeamChatRead",

    # --- client_file.py ---
    "ClientFile",
    "ClientFileCollaborator",

    # --- aria_campaign.py ---
    "AriaCampaign",

    # --- gdpr.py ---
    "ErasureRequest",

    # --- lo_license.py ---
    "LoanOfficerLicense",

    # --- briefing_thread.py ---
    "BriefingThread",
    "BriefingTask",
    "BriefingAuditLog",

    # --- contact_card.py ---
    "ContactCardMember",

    # --- ai_cost_record.py ---
    "AICostRecord",

    # --- partner.py ---
    "PreApprovalLetterRequest",

    # --- audit_event.py (non-exported, but has org_id) ---
    "AuditEvent",

    # --- audit.py (non-exported) ---
    "MobileAuditEvent",

    # --- autonomous_task.py (non-exported) ---
    "AutonomousTask",

    # --- agent_escalation.py (non-exported) ---
    "AgentEscalation",

    # --- agent_registry.py (non-exported) ---
    "AgentRunLog",

    # --- action_type_confidence.py (non-exported) ---
    "ActionTypeConfidence",

    # --- borrower_prep.py (non-exported) ---
    "BorrowerPrepSequence",

    # --- call_disposition.py (non-exported) ---
    "CallDisposition",

    # --- content_governance.py (non-exported) ---
    "ContentTemplate",

    # --- demo_data.py (non-exported) ---
    "DemoDataRecord",

    # --- doc_notification.py (non-exported) ---
    "DocNotification",

    # --- drip_enrollment.py (non-exported) ---
    "DripEnrollment",

    # --- email_tracking.py (non-exported) ---
    "EmailTrackingEvent",

    # --- engagement_event.py (non-exported) ---
    "EngagementEvent",

    # --- file_collaborator.py (non-exported) ---
    "LoanFileCollaborator",
    "UserOnboardingState",

    # --- file_communication.py (non-exported) ---
    "FileCommunication",
    "CommunicationParticipant",

    # --- income_calculation.py (non-exported) ---
    "IncomeCalculation",
    "IncomeVerificationTask",

    # --- learning_example.py (non-exported) ---
    "LearningExample",
    "LearningPattern",

    # --- live_transfer.py (non-exported) ---
    "LiveTransfer",

    # --- lo_availability.py (non-exported) ---
    "LOAvailability",
    "LOAvailabilitySchedule",

    # --- memory_audit.py (non-exported) ---
    "MemoryAuditEvent",

    # --- memory_staging.py (non-exported) ---
    "MemoryStaging",

    # --- memory_topic_config.py (non-exported) ---
    "MemoryTopicConfig",

    # --- oauth_token.py (non-exported) ---
    "OAuthToken",

    # --- pos_consent.py (non-exported) ---
    "CreditAuthorization",
    "EConsentAgreement",

    # --- pos.py (non-exported) ---
    "POSApplication",
    "POSBorrowerMessage",
    "POSVerification",
    "POSTrustedDevice",

    # --- recovery_opt_out.py (non-exported) ---
    "RecoveryOptOut",

    # --- sms_compliance.py (non-exported) ---
    "SMSOptOut",
    "SMSConsent",
    "SMSComplianceLog",

    # --- sms_conversation.py (non-exported) ---
    "SMSAIConversation",

    # --- sms_dead_letter.py (non-exported) ---
    "SMSDeadLetter",

    # --- sms_task.py (non-exported) ---
    "SMSTask",
    "SMSResponsePattern",
    "SMSAIConfidence",
    "SMSAIAuditLog",

    # --- tcpa_consent.py (non-exported) ---
    "TCPAConsent",

    # --- vendor.py (non-exported) ---
    "Vendor",
    "VendorOrder",

    # --- voice_call_session.py (non-exported) ---
    "VoiceCallSession",

    # --- voice_workflow.py (non-exported) ---
    "VoiceWorkflow",

    # --- agent_memory.py (non-exported, has org_id) ---
    "AgentConversation",
    "AgentMemory",
    "AgentContext",

    # --- agent_feedback.py (non-exported, has org_id) ---
    "AgentFeedback",
    "AgentFeedbackSummary",

    # --- autonomous_task.py (non-exported, has org_id) ---
    "TaskExecution",
    "AgentAction",

    # --- subscription.py: user-level subscriptions (tablename='subscriptions') ---
    # OrgSubscription (models/billing.py) now uses separate 'org_subscriptions' table
    "Subscription",

    # =========================================================================
    # Legacy models (backend/models/ directory and scattered backend files)
    # =========================================================================

    # --- models/accounting/accounts_payable.py ---
    "APVendor",
    "APBill",
    "APPayment",

    # --- models/accounting/accounts_receivable.py ---
    "ARCustomer",
    "ARInvoice",
    "ARPayment",

    # --- models/accounting/banking.py ---
    "BankAccount",
    "PlaidItem",
    "BankTransaction",
    "BankCategorizationRule",
    "BankReconciliation",

    # --- models/accounting/budgeting.py ---
    "BudgetTemplate",

    # --- models/accounting/core.py ---
    "ChartOfAccounts",
    "AccountingPeriod",
    "JournalEntry",
    "JournalEntryTemplate",
    "AccountingSettings",
    "TaxRate",
    "RecurringTransaction",
    "AccountingAuditLog",

    # --- models/acquisition_engine/campaign_models.py ---
    "CampaignInstance",

    # --- models/acquisition_engine/event_models.py ---
    "AcquisitionEvent",

    # --- models/agent_governance.py ---
    "AgentProfile",

    # --- models/billing.py ---
    "OrgSubscription",
    "Invoice",
    "UsageRecord",
    "PaymentMethod",
    "OrganizationFeature",

    # --- models/business_operations.py ---
    "ServiceProvider",
    "ServiceUsageRecord",
    "ServiceInvoice",
    "SubscriptionRevenue",
    "UsageRevenue",
    "MarketingCampaign",
    "MarketingMetrics",
    "BusinessForecast",
    "BusinessKPI",
    "BudgetAlert",

    # --- models/calendar_sync_models.py ---
    "CRMCalendarEvent",
    "CalendarEventSyncMap",
    "CalendarSyncLog",
    "CalendarSyncSettings",

    # --- models/call_monitoring_models.py ---
    "CallSession",
    "CallParticipant",
    "AgentRun",
    "AgentEvent",
    "CallArtifact",
    "IntakeFieldUpdate",
    "CallRiskFlag",
    "UnderwritingGuideline",

    # --- models/carousel_builder.py ---
    "CarouselProject",
    "CarouselTheme",

    # --- models/content_marketing.py ---
    "ContentBrandVoice",
    "ContentCalendar",
    "ContentBrief",
    "SEOKeyword",
    "ContentMarketingTemplate",

    # --- models/custom_domains.py ---
    "CustomDomain",

    # --- models/financial_intelligence.py ---
    "LoanSale",
    "HedgePosition",
    "SecondaryMetrics",
    "MSRPortfolio",
    "WarehouseLine",
    "WarehouseUsage",
    "ProductProfitability",
    "CashPosition",
    "CashForecast",
    "BurnRate",
    "CompetitorRate",
    "LostDeal",
    "CapitalRequirement",
    "ComplianceRisk",

    # --- models/master_manager_models.py ---
    "RoleDefinition",
    "TalentCapacity",
    "TalentState",
    "TalentStateHistory",
    "TalentPerformance",
    "CapacityAlert",
    "CoverageMap",
    "Candidate",
    "JobPosting",
    "Interview",
    "Offer",
    "CandidateActivity",
    "CandidateNote",

    # --- models/microsite.py ---
    "MicrositeTemplatePack",
    "MicrositePage",
    "MicrositeLead",
    "OrganizationMicrositeSettings",

    # --- models/pii_audit_log.py ---
    "PIIAuditLog",

    # --- models/profitability.py ---
    # NOTE: ExpenseCategory has no org_id (global reference data) -> SYSTEM
    # NOTE: LoanAttribution has no org_id (FK-scoped to loan) -> SYSTEM
    "Expense",
    "ProfitabilityRole",
    "EmployeeCost",
    "ProfitabilityLoan",
    "RevenueRecord",
    "ProfitabilitySnapshot",
    "ProfitabilityScenario",
    "ProfitabilityInsight",
    "ProfitabilityAudit",

    # --- models/purl.py ---
    "PURLWorkspace",
    "PURLContact",
    "PURLWorkspaceMember",
    "PURLAccessToken",
    "PURLApplication",
    "PURLLoan",
    "PURLDocument",
    "PURLPortalModule",
    "PURLMilestoneDefinition",
    "PURLLoanMilestone",
    "PURLTask",
    "PURLMessage",
    "PURLEventsOutbox",
    "PURLAuditLog",
    "PURLDocumentRequest",

    # --- models/salesforce_sync_log.py ---
    "SalesforceSyncLog",
    "SalesforceFieldMapping",

    # --- models/sla_tracking.py ---
    "SLAMeasure",
    "LoanMilestoneHistory",
    "CompanyHoliday",
    "SLAPerformanceSnapshot",
    "SLAAlert",
    "SLAEfficiencyReport",

    # --- models/smart_docs_models.py ---
    "DocumentRequest",
    "SmartDocument",

    # --- models/surveying_models.py ---
    "SurveyTemplate",
    "SurveyResponse",
    "SurveyAnalytics",
    "SavingsValidation",

    # --- models/usage_tracking.py ---
    "AITokenUsageLog",
    "UserUsageSnapshot",
    "TeamUsageSnapshot",
    "OrgUsageSnapshot",
    "UsageForecast",
    "PricingRecommendation",
    "UsageAlert",

    # --- ai_receptionist_dashboard_models.py ---
    "AIReceptionistActivity",
    "AIReceptionistMetricsDaily",
    "AIReceptionistError",
    "AIReceptionistConversation",

    # --- conversation_memory_models.py ---
    "AIConversationMemory",
    "AIActionHistory",

    # --- microsite_models.py ---
    "MicrositeTheme",
    "UserMicrosite",

    # --- subscription_models.py ---
    "OrganizationSubscription",
    "FeatureUsage",
    "UsageWarning",
    "AdminAction",

    # --- vapi_models.py ---
    "VapiCall",
    "VapiCallNote",
    "VapiAssistant",
    "VapiPhoneNumber",
    "CallRoutingLog",
    "StaffAvailability",
    "CallTransferConfig",

    # --- video_clip_models.py ---
    "VideoClip",
    "ClipTemplate",

    # --- video_meeting_models.py ---
    "VideoMeetingRoom",
    "MeetingTemplate",
    "OrganizationVideoSettings",

    # --- workflow_config_models.py ---
    "WorkflowConfiguration",

    # --- scheduler_enhancements.py ---
    "SchedulerResource",
    "SoftHold",
    "ReminderProfile",
    "SchedulerAnalytics",
    "CampaignBooking",
    "GroupSession",
    "SeriesSchedule",
    "CalendarSync",
    "IntakeQuestion",

    # --- services/pipeline_appointment_trigger.py ---
    "PipelineAppointmentRuleModel",
    "PipelineAppointmentTriggerLog",

    # --- services/smart_scheduler_service.py ---
    "ScheduledAppointment",

    # --- services/holiday_service.py ---
    "Holiday",
    "PTORequest",

    # --- routes/ai_activity_routes.py ---
    "AIActivityLog",

    # --- routes/calendly_routes.py ---
    "CalendlyIntegration",
    "CalendlyBooking",

    # --- routes/file_collaborator_routes.py ---
    "FileCollaborator",

    # --- routes/support_tickets_routes.py ---
    "SupportTicket",

    # --- routes/pre_approval_letter_settings_routes.py ---
    "PreApprovalLetterSettings",

    # --- integrations/microsoft365/models.py ---
    "MSAccount",
    "MSGraphSubscription",
    "MSCalendarSyncMapping",
    "MSEmailReconciliation",
    "MSTeamsChatReconciliation",

    # --- models/workflow_sla.py ---
    "WorkflowInstance",
    "LeadWorkflowRoleAssignment",
    "LoanWorkflowRoleAssignment",

    # --- billing.py (StripeEvent has org_id via FK) ---
    "StripeEvent",

    # --- ab_testing_models.py ---
    "Experiment",
    "ExperimentResult",

}

# ---------------------------------------------------------------------------
# Models that are genuinely global (no tenant filtering needed) or scoped
# indirectly via FK to a tenant-scoped parent row.
# ---------------------------------------------------------------------------
SYSTEM_SCOPED_MODELS: set[str] = {
    # --- core.py: Organization IS the tenant ---
    "Organization",

    # --- core.py: Tied to user, no direct org_id ---
    "EmailSignature",
    "ImpersonationSession",
    "OnboardingProgress",
    "OnboardingError",
    "VerificationToken",
    "UserSettings",

    # --- security.py: System-wide or user-scoped ---
    "UserSession",
    "EmergencyRevocation",
    "AccessCertification",
    "SecuritySnapshotDaily",
    "IntegrationStatusLog",
    "SystemAlert",
    "SystemJobsLog",

    # --- permission.py: Role/page definitions are global ---
    "CRMPage",
    "RolePagePermission",
    "UserPagePermission",
    "UserPermission",
    "PermissionRequest",
    "AIQuickAction",
    "AIQuickActionRole",
    "Responsibility",
    "RoleResponsibility",
    "UserResponsibility",

    # --- workflow.py: Process templates are org-less ---
    "CalendarMapping",
    "OnboardingStep",
    "ProcessTemplate",
    "ProcessRole",
    "ProcessMilestone",
    "ProcessTask",

    # --- communication.py ---
    "EmailVerificationToken",
    "VoicemailEvent",

    # --- referral.py: FK to loan ---
    "LoanTeamMember",

    # --- microsoft.py ---
    "MicrosoftToken",
    "MicrosoftOAuthToken",

    # --- ai.py: Aggregate/daily tables without org_id ---
    "AIColleagueLearningMetric",
    "AIPerformanceDaily",
    "AIJourneyInsight",
    "AIHealthScore",
    "AIMetricsDaily",
    "AIChangelogDaily",
    "AITrainingEvent",

    # --- borrower.py: FK-scoped to BorrowerProfile or BorrowerApplication ---
    "BorrowerAuthEvent",
    "BorrowerMagicLink",
    "ApplicationDocument",
    "CoborrowerInvitation",
    "ApplicationEvent",
    "ApplicationNotification",
    "ApplicationSession",
    "VoiceApplicationSession",

    # --- esignature.py: FK-scoped to envelope ---
    "ESignatureRecipient",
    "ESignatureField",
    "ESignatureAuditEvent",
    "ESignKBASession",

    # --- credit_monitoring.py: FK to CreditAlert ---
    "CreditInquiryAlert",

    # --- refinance_intelligence.py: FK to RefiOpportunity ---
    "RefiScenario",

    # --- subscription.py: Global billing/plan data ---
    "SubscriptionPlan",
    # NOTE: Subscription is in TENANT list above (user-level, tablename='subscriptions')
    # OrgSubscription (models/billing.py) now uses separate 'org_subscriptions' table
    "PromoCode",
    "TeamMember",

    # --- data_reconciliation.py ---
    "IncomingDataEvent",
    "ExtractedData",
    "BlockedSender",
    "DuplicatePair",
    "MergeTrainingEvent",
    "MergeAIModel",

    # --- it_helpdesk.py ---
    "ITHelpdeskTicket",
    "ITHelpdeskTool",

    # --- client.py ---
    "ClientProfile",
    "TeamRole",
    "ProcessFlowDocument",
    "KPISnapshot",

    # --- hr_goals.py ---
    "UserJobDescription",
    "Skill",
    "EmployeeResponsibility",
    "ResponsibilitySkill",
    "UserGoal",
    "GoalKeyResult",
    "GoalEmployeeAssessment",
    "GoalManagerAssessment",
    "GoalResponsibility",
    "UserSkillAssessment",

    # --- state_disclosure.py: 50-state reference data ---
    "StateDisclosure",

    # --- webhook.py: Event catalog is global, delivery log FK'd to subscription ---
    "WebhookDeliveryLog",
    "WebhookEventCatalog",

    # --- agent_context.py (non-exported): No org_id ---
    "AgentContextStore",
    "AgentContextEvent",
    "ContextChangeAudit",

    # --- call_authorization.py (non-exported) ---
    "CallAuthorization",

    # --- notification_preference.py (non-exported) ---
    "NotificationPreference",

    # --- webhook_idempotency.py (non-exported) ---
    "WebhookIdempotencyRecord",

    # --- agent_registry.py (non-exported): No org_id ---
    "AgentRegistryEntry",
    "HarnessChangeProposal",

    # --- agent_memory.py (non-exported): AgentConversation, AgentMemory,
    # AgentContext have org_id -> moved to TENANT

    # --- agent_feedback.py (non-exported): AgentFeedback, AgentFeedbackSummary
    # have org_id -> moved to TENANT

    # --- autonomous_task.py (non-exported): TaskExecution, AgentAction
    # have org_id -> moved to TENANT

    # --- borrower_prep.py (non-exported): FK to BorrowerPrepSequence ---
    "BorrowerPrepStep",

    # --- content_governance.py (non-exported): FK-scoped ---
    "ContentApproval",
    "ContentUsageLog",

    # --- drip_enrollment.py (non-exported): FK to DripEnrollment ---
    "DripEnrollmentEvent",

    # --- email_tracking.py (non-exported) ---
    "TrackingLinkMap",

    # --- income_calculation.py (non-exported): FK to IncomeCalculation ---
    "IncomeSource",

    # --- learning_example.py (non-exported) ---
    "PromptOptimization",

    # --- pos.py (non-exported): FK to POSApplication ---
    "POSApplicationSection",
    "POSApplicationPII",
    "POSApplicationAudit",
    "POSAIQAMessage",

    # --- sms_conversation.py (non-exported): FK to SMSAIConversation ---
    "SMSAIConversationMessage",

    # --- doc_notification.py (non-exported): NotificationPreference inside doc module ---
    # NOTE: This is a DIFFERENT class from notification_preference.py's NotificationPreference
    # The doc_notification.py version inherits the same class name; SQLAlchemy considers
    # them the same mapper if they share __tablename__. Check at runtime.

    # --- memory_topic_config.py (non-exported) ---
    "MemoryExclusionRule",

    # --- calendar_label.py: FK to CalendarLabel ---
    "AppointmentLabel",

    # --- reminder_config.py: FK to appointment ---
    "ReminderLog",

    # --- approval_chain.py: FK to ApprovalRequest ---
    "ApprovalDecision",

    # --- partner.py: Session tokens ---
    "PartnerSession",

    # --- aria_campaign.py: FK to AriaCampaign ---
    "AriaCampaignRecipient",

    # --- voice_consent.py: FK to VoiceConsent ---
    "VoiceConsentAudit",

    # --- iMessage: Lookup cache keyed by line_id ---
    "IMessageLookupCache",

    # --- password_history.py: User-scoped, no org_id ---
    "PasswordHistory",
    "LoginAttempt",

    # =========================================================================
    # Legacy models (backend/models/ directory and scattered backend files)
    # =========================================================================

    # --- models/accounting/accounts_payable.py: Child records, no org_id ---
    "APBillLine",
    "APPaymentApplication",

    # --- models/accounting/accounts_receivable.py: Child records ---
    "ARInvoiceLine",
    "ARPaymentApplication",

    # --- models/accounting/budgeting.py: FK to BudgetTemplate ---
    "BudgetItem",

    # --- models/accounting/core.py: Child records ---
    "JournalEntryLine",
    "JournalEntryTemplateLine",

    # --- models/acquisition_engine/campaign_models.py: Template, no org_id ---
    "CampaignBlueprint",

    # --- models/acquisition_engine/scoring_models.py ---
    "LeadTemperature",
    "CampaignAttribution",

    # --- models/agent_governance.py ---
    "AgentTool",
    "AgentExecution",
    "GymTestScenario",
    "GymTestRun",
    "GymTestResult",
    "AgentAlert",
    "AgentMetricsTimeseries",
    "AgentChatSession",
    "AgentChatMessage",
    "TrainingScenario",
    "TrainingSession",

    # --- models/ai_daily_blog.py: All user-scoped ---
    "BlogVoiceProfile",
    "BlogComplianceProfile",
    "BlogSourceDocument",
    "BlogCampaign",
    "BlogContentItem",
    "BlogContentJob",
    "BlogImageAsset",
    "BlogSocialConnection",
    "BlogPublishLog",
    "BlogTopicQueue",
    "BlogAuditLog",
    "BlogPerformanceFeedback",
    "BlogUserSettings",

    # --- models/active_loan_profile.py ---
    "ActiveLoanProfile",

    # --- models/bank_statement_models.py ---
    "BankStatementWorksheet",
    "BankStatementAccount",
    "BankStatementMonth",
    "BankStatementIneligibleItem",

    # --- models/billing.py: Global plan definition ---
    "Plan",

    # --- models/call_monitoring_models.py: FK-scoped child ---
    "GuidelineSection",

    # --- models/carousel_builder.py: FK-scoped children ---
    "CarouselSlide",
    "CarouselTemplate",
    "CarouselExport",

    # --- models/content_marketing.py: FK-scoped children ---
    "ContentComment",
    "ContentBriefApproval",
    "PersonalizationToken",
    "ContentPublishLog",

    # --- models/conversation_intelligence_models.py: All no org_id ---
    "CICallRecording",
    "CICallTranscription",
    "CITranscriptionSegment",
    "CICallAnalysis",
    "CIQARubric",
    "CIQAScorecard",
    "CIQAScorecardItem",
    "CIRealtimeSession",
    "CIRealtimeSuggestion",
    "CICoachingClip",
    "CICoachingAssignment",
    "CICoachingComment",
    "CIComplianceRule",
    "CIComplianceViolation",
    "CIAgentMetrics",

    # --- models/call_screening_models.py ---
    "PhoneBlocklist",
    "PhoneWhitelist",
    "CallScreeningLog",
    "PhoneLookupCache",

    # --- models/data_conflict.py ---
    "DataConflict",

    # --- models/document_extraction.py ---
    "SmartDocumentExtraction",

    # --- models/document_visibility.py ---
    "DocumentVisibility",
    "DocumentVisibilityAudit",

    # --- models/email_interaction.py ---
    "EmailInteraction",

    # --- models/email_monitor.py ---
    "EmailMonitorAddress",
    "EmailMonitorKeyword",
    "EmailMonitorRule",
    "EmailMonitorCaptured",
    "EmailCRMLink",
    "EmailRelevanceAnalysis",
    "EmailFilterWhitelist",
    "EmailFilterBlacklist",
    "EmailProviderConfig",
    "GmailOAuthToken",
    "OutlookOAuthToken",
    "EmailMonitorLog",

    # --- models/esign_models.py ---
    "EsignEnvelope",
    "EsignSigner",
    "EsignField",
    "EsignFieldValue",
    "EsignAuditEvent",
    "EsignCompletedDocument",

    # --- models/feature_flags.py ---
    "SystemFeature",
    "CompanyFeatureAccess",
    "FeatureAuditLog",

    # --- models/field_update_history.py ---
    "FieldUpdateHistory",

    # --- models/followupboss_models.py ---
    "FUBUserConnection",
    "FUBLeadMapping",
    "FUBSyncEvent",
    "FUBStageMapping",

    # --- models/income_engine_models.py ---
    "IncomeSummary",
    "IncomeCalculationDetail",
    "IncomeFlag",
    "MileageDepreciationRate",
    "IncomeWorksheet",

    # --- models/income_models.py ---
    # NOTE: IncomeSource already in SYSTEM (income_calculation.py version).
    # Remaining models (PaystubExtraction, Employment, SelfEmploymentIncome,
    # RentalIncomeProperty, IncomeCalculationHistory) are NOT imported because
    # income_models.py is skipped to avoid 'income_sources' table conflict.

    # --- models/lead_profile.py ---
    "LeadProfile",

    # --- models/master_manager_models.py: No org_id --- (none found without)

    # --- models/microsite.py: FK-scoped children ---
    "MicrositeAsset",
    "MicrositePublishHistory",
    "MicrositeAnalyticsEvent",
    "MicrositeCustomPage",

    # --- models/mum_client_profile.py ---
    "MUMClientProfile",

    # --- models/perennia_docs.py ---
    # NOTE: perennia_docs models live inside create_perennia_docs_models() factory.
    # DocumentRequest (smart_docs version with org_id) is in TENANT above.
    # The following FK-scoped children have no org_id:
    "PerenniaDocument",
    "TemplatePack",
    "DocumentRule",
    "DocumentEvent",
    "DocumentNotification",
    "RetentionPolicy",
    "BorrowerPortalSession",

    # --- models/portal_models.py ---
    "PortalLoan",
    "LifecycleStateHistory",
    "MilestoneTemplate",
    "MilestoneInstance",
    "TaskTemplate",
    "TaskInstance",
    "FederalHoliday",
    "CloseOnTimeSchedule",
    "CloseOnTimeMilestone",
    "PortalDocument",
    "DocumentExtraction",
    "PropertyCosts",
    "HomePriceIndex",
    "PropertyValueBaseline",
    "PropertyValuation",
    "HomeValueInsight",
    "NotificationTemplate",
    "NotificationQueue",
    "LoanActivityLog",
    "RiskFlag",
    "PartnerAccessToken",
    "AnnualRefreshCycle",
    "PresentationSession",
    "PortalPresentationScenario",
    "PresentationCitation",

    # --- models/presentation.py ---
    "PresentationScenario",
    "QuoteRequest",

    # --- models/rate_monitor.py ---
    "RateMonitorTarget",
    "RateMonitorHistory",
    "RateMonitorAlert",
    "OptimalBlueRateCache",

    # --- models/rate_sheet.py ---
    "RateSheet",
    "RateSheetRate",
    "RefinanceOpportunity",

    # --- models/smart_docs_models.py: FK-scoped ---
    "DocPolicyEvent",
    "NeedsListTemplate",
    "ClientReminderSettings",

    # --- models/sms_models.py ---
    "SMSRateLimitLog",
    "SMSQueue",

    # --- models/profitability.py: No org_id ---
    "ExpenseCategory",
    "LoanAttribution",

    # --- models/surveying_models.py: FK-scoped children ---
    "SurveyQuestion",
    "SurveyAnswer",

    # --- models/usage_tracking.py: Global pricing reference ---
    "AIModelPricing",
    # NOTE: UsageAlert already in TENANT (usage_tracking.py version has org_id)

    # --- models/team_member_profile.py ---
    "TeamMemberProfile",

    # --- models/tenant.py ---
    "Tenant",

    # --- models/user_integration.py ---
    "UserIntegration",

    # --- models/user_onboarding.py ---
    # NOTE: Role, Category, RoleDefaultCategory, RoleDefaultResponsibility,
    # UserProfile, UserCategory, PermissionTemplate, UserPermissions,
    # KPIScorecard, BulkUploadSession, BulkUserDraft, UserAuditLog,
    # OnboardingSession share __tablename__ with Onboarding* equivalents
    # from user_onboarding_integration.py. The Onboarding* versions take
    # precedence at runtime, so only those names are listed.
    # Responsibility and UserResponsibility are already in SYSTEM (permission.py).

    # --- models/workflow_sla.py: AI confidence data ---
    "WorkflowAIConfidence",

    # --- ai_receptionist_dashboard_models.py: No org_id ---
    "AIReceptionistSkill",
    "AIReceptionistSystemHealth",

    # --- chat_state_machine_models.py ---
    "ChatSession",
    "ChatMessage",
    "CallRequest",

    # --- guideline_updates_models.py ---
    "GuidelineUpdate",
    "UserUpdateView",

    # --- microsite_models.py: FK-scoped ---
    "MicrositeProfile",
    "MicrositeContentPage",

    # --- models_mum.py ---
    # NOTE: MUMClient already in TENANT (database/models/referral.py version).
    # MUMTransaction NOT imported because models_mum.py is skipped to avoid
    # 'mum_clients' table conflict.

    # --- salesforce_integration_models.py ---
    "IntegrationProfile",
    "SfUserSchema",
    "FieldMapping",
    "IntegrationEvent",
    "SyncQueueItem",
    "OAuthState",
    "IntegrationRecordTracking",

    # --- subscription_models.py: Global feature catalog ---
    "FeatureDefinition",

    # --- user_onboarding_integration.py ---
    "OnboardingRole",
    "OnboardingCategory",
    "OnboardingResponsibility",
    "OnboardingPermissionTemplate",
    "OnboardingUserProfile",
    "OnboardingUserCategory",
    "OnboardingUserResponsibility",
    "OnboardingUserPermissions",
    "OnboardingKPIScorecard",
    "OnboardingRoleDefaultCategory",
    "OnboardingRoleDefaultResponsibility",
    "OnboardingSession",
    "OnboardingAuditLog",

    # --- video_clip_models.py: FK-scoped children ---
    "ClipShare",
    "ClipView",
    "ClipComment",
    "ClipNotification",

    # --- video_meeting_models.py: FK-scoped children ---
    "MeetingParticipant",
    "MeetingRecording",
    "RecordingTranscript",
    "MeetingAIAnalysis",
    "MeetingChat",
    "ParticipantAnalytics",
    "CoachingRecommendation",
    "MortgageIntelligence",
    "BreakoutRoom",

    # --- workflow_config_models.py: FK-scoped children ---
    "WorkflowDayConfig",
    "WorkflowRoleAssignment",
    "WorkflowTaskInstance",
    "BrokenTaskAlert",

    # --- workflow_models.py ---
    # NOTE: EmployerRecord, Opportunity, RecurringTask NOT imported because
    # workflow_models.py is skipped to avoid 'workflow_executions' table conflict.
    # WorkflowExecution already in TENANT (database/models/workflow.py version).

    # --- routes/analytics_tracking_routes.py ---
    "AnalyticsEvent",

    # --- routes/beta_routes.py ---
    "BetaApplication",

    # --- routes/ai_email_settings_routes.py ---
    "AIEmailSettings",

    # --- routes/email_integration_settings_routes.py ---
    "EmailIntegrationSettings",

    # --- routes/email_training_routes.py ---
    "EmailTrainingLog",

    # --- ab_testing_models.py: FK-scoped children ---
    "ExperimentVariant",
    "ExperimentAssignment",
    "ExperimentInsight",
}
