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
    "Subscription",
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

    # --- agent_context.py (non-exported) ---
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

    # --- agent_memory.py (non-exported): User-scoped ---
    "AgentConversation",
    "AgentMemory",
    "AgentContext",

    # --- agent_feedback.py (non-exported) ---
    "AgentFeedback",
    "AgentFeedbackSummary",

    # --- autonomous_task.py (non-exported): FK-scoped ---
    "TaskExecution",
    "AgentAction",

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
}
