#!/usr/bin/env python3
"""
Phase 1: Migrate `from main import X` to proper module imports.

This script rewrites import statements across the codebase to break the
main.py dependency graph. It maps each symbol to its canonical module:
  - Auth functions → auth.dependencies
  - Models → database.models
  - Enums → database.enums
  - Database session/engine → database
  - Schemas → schemas.core

Symbols that don't have a clear alternative module are left as-is.
"""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict

# ============================================================================
# SYMBOL → MODULE MAPPING
# ============================================================================

AUTH_SYMBOLS = {
    'get_current_user', 'get_current_user_flexible', 'oauth2_scheme',
}

DB_SYMBOLS = {
    'SessionLocal', 'Base', 'engine', 'get_db',
}

ENUM_SYMBOLS = {
    'LeadStage', 'LoanStage', 'RateLockStatus', 'RateLockRecommendation',
    'BuyingTimelineCategory', 'BorrowerRiskProfile', 'TaskType', 'ActivityType',
    'EmailIntakeMatchStatus', 'AttachmentClassificationStatus', 'DocumentType',
    'DocumentCategory', 'InviteStatus', 'PermissionLevel',
    'DialerSessionStatus', 'DialerTaskStatus', 'CallOutcome',
    'SocialProvider', 'ApplicationStatus', 'ApplicationStep', 'CoachMode',
    'BuyerType',
}

MODEL_SYMBOLS = {
    # Core
    'Organization', 'Branch', 'User', 'ApiKey', 'UserSettings',
    'CalendarAssignment', 'EmailSignature', 'ImpersonationSession',
    'OnboardingProgress', 'OnboardingError', 'VerificationToken',
    # Lead & Loan
    'Lead', 'Loan',
    # Tasks
    'AITask', 'Task', 'EscalationRecord', 'HandoffLog',
    # Documents
    'EmailIntake', 'AttachmentIntake', 'Document',
    # Communication
    'Activity', 'StageHistory', 'Conversation', 'ConversationMemory',
    'SMSMessage', 'SMSConversation', 'EmailMessage', 'Email', 'EmailDraft',
    'EmailVerificationToken', 'TeamsMessage', 'VoicemailDrop',
    'VoicemailTemplate', 'VoicemailCampaign', 'VoicemailEvent',
    'CalendarEvent', 'IntegrationLog', 'IntegrationCredential',
    'ConversationSession', 'EntityExtraction', 'ChannelPreference',
    'MessageTemplate',
    # AI
    'AIDelegatedTask', 'AIFeedbackLog', 'AIAction', 'AILearningMetric',
    'AIKnowledgeBase', 'AIAuditLog', 'AIColleagueAction',
    'AIColleagueLearningMetric', 'AIPerformanceDaily', 'AIJourneyInsight',
    'AIHealthScore', 'AIMetricsDaily', 'AIChangelogDaily', 'AITrainingEvent',
    # Referral
    'ReferralPartner', 'LoanTeamMember', 'MUMClient',
    # Workflow
    'ScheduledWorkflow', 'WorkflowExecution', 'Workflow', 'CalendarMapping',
    'OnboardingStep', 'ProcessTemplate', 'ProcessRole', 'ProcessMilestone',
    'ProcessTask',
    # Permission
    'EmployeeInvite', 'CRMPage', 'RolePagePermission', 'UserPagePermission',
    'UserPermission', 'PermissionRequest', 'AIQuickAction', 'AIQuickActionRole',
    'Responsibility', 'RoleResponsibility', 'UserResponsibility',
    # Security
    'AuditLog', 'UserSession', 'EmergencyRevocation', 'AccessCertification',
    'SecuritySnapshotDaily', 'IntegrationStatusLog', 'SystemAlert',
    'SystemJobsLog', 'Notification',
    # Subscription
    'SubscriptionPlan', 'Subscription', 'PromoCode', 'TeamMember',
    # Microsoft
    'MicrosoftToken', 'MicrosoftOAuthToken', 'MicrosoftAppConfig',
    # Data Reconciliation
    'IncomingDataEvent', 'ExtractedData', 'BlockedSender', 'DuplicatePair',
    'MergeTrainingEvent', 'MergeAIModel',
    # IT Helpdesk
    'ITHelpdeskTicket', 'ITHelpdeskTool',
    # Client
    'ClientProfile', 'TeamRole', 'ProcessFlowDocument', 'KPISnapshot',
    # HR Goals
    'UserJobDescription', 'Skill', 'EmployeeResponsibility',
    'ResponsibilitySkill', 'UserGoal', 'GoalKeyResult',
    'GoalEmployeeAssessment', 'GoalManagerAssessment', 'GoalResponsibility',
    'UserSkillAssessment',
    # Dialer
    'AgentTelephonySettings', 'VerifiedCallerId', 'DialerSession',
    'DialerSessionTask', 'CallLog', 'ActiveCall', 'ContactDNCStatus',
    # Borrower Application
    'BorrowerProfile', 'BorrowerAuthEvent', 'BorrowerMagicLink',
    'BorrowerApplication', 'ApplicationDocument', 'CoborrowerInvitation',
    'ApplicationEvent', 'ApplicationNotification', 'ApplicationSession',
    'VoiceApplicationSession',
    # Loan Estimates
    'EstimateParseCache', 'EstimateParseFailure', 'EstimateComparison',
    # Platform Contracts
    'PlatformContract',
    # Refinance Intelligence
    'RefiOpportunity', 'RefiScenario', 'PortfolioMonitoringRun',
    # Rate Lock
    'RateLock', 'RateMarketData',
    # Marketing
    'AudienceSegment', 'CampaignDefinition', 'DripSequence',
    # LOS Sync
    'LosFieldMapping', 'LosSyncLog',
    # Compliance
    'LoanFee', 'DisclosureEvent', 'AdverseActionNotice', 'ComplianceAlert',
    'ToleranceCategory', 'DisclosureType', 'AdverseActionReason',
    # SSO
    'SSOConfig',
    # Webhooks
    'WebhookSubscription', 'WebhookDeliveryLog', 'WebhookEventCatalog',
    # Extra models not in __init__ but referenced from main
    'RecallAIBot',
}

SCHEMA_SYMBOLS = {
    'UserCreate', 'UserResponse', 'TeamMemberCreate', 'TeamMemberUpdate',
    'ApiKeyCreate', 'ApiKeyResponse', 'ImpersonationStart', 'ImpersonationResponse',
    'LeadCreate', 'LeadUpdate', 'LeadResponse',
    'LoanCreate', 'LoanUpdate', 'LoanResponse',
    'TaskCreate', 'TaskUpdate', 'TaskResponse',
    'ReferralPartnerCreate', 'ReferralPartnerUpdate', 'ReferralPartnerResponse',
    'LoanTeamMemberCreate', 'LoanTeamMemberUpdate', 'LoanTeamMemberResponse',
    'MUMClientCreate', 'MUMClientUpdate', 'MUMClientResponse',
    'BorrowerApplicationCreate', 'BorrowerApplicationUpdate', 'StepDataUpdate',
    'CreditAuthCapture', 'PrequalificationRequest', 'PrequalificationResponse',
    'DocumentUploadResponse', 'CoborrowerInvitationCreate', 'CoborrowerInvitationResponse',
    'ApplicationEventCreate', 'BorrowerApplicationResponse', 'ApplicationPublicResponse',
    'ApplicationAnalytics', 'ErrorFixRequest',
    'UserProfileData', 'BrandingSettings', 'IntegrationSettings', 'AutomationSettings',
    'ReconciliationSettings', 'PipelineSettings', 'KPITargets', 'PortfolioSettings',
    'AdvancedSettings', 'ClientProfileCreate', 'ClientProfileUpdate', 'ClientProfileResponse',
    'TeamRoleCreate', 'TeamRoleUpdate', 'TeamRoleResponse',
    'ProcessFlowDocumentCreate', 'ProcessFlowDocumentResponse',
    'ActivityCreate', 'ActivityResponse',
    'ProcessTemplateCreate', 'ProcessTemplateUpdate', 'ProcessTemplateResponse',
    'ProcessRoleCreate', 'ProcessRoleResponse',
    'ProcessMilestoneCreate', 'ProcessMilestoneResponse',
    'ProcessTaskCreate', 'ProcessTaskResponse',
    'DocumentParseRequest', 'DocumentParseResponse',
    'ConversationCreate', 'ChatStreamRequest', 'ConversationResponse',
    'CoachRequest', 'CoachResponse',
    'CalendarEventCreate', 'CalendarEventUpdate', 'CalendarEventResponse',
    'CalendarAssignmentCreate', 'CalendarAssignmentUpdate', 'CalendarAssignmentResponse',
    'CALENDAR_PURPOSES',
    'IncomingDataEventCreate', 'ExtractedDataResponse',
    'ReconciliationApproval', 'ReconciliationRejection', 'BlockSenderRequest',
    'CreateLeadFromExtracted',
    'OrganizationCreate', 'OrganizationUpdate', 'OrganizationResponse',
    'MicrosoftOAuthConnect', 'MicrosoftTokenResponse', 'MicrosoftSyncSettings',
    'MicrosoftAppConfigRequest', 'MicrosoftAppConfigResponse',
    'RevokeSessionRequest', 'RevokeAllSessionsRequest', 'EmergencyRevokeRequest',
    'UpdateJobDescriptionRequest', 'JobDescriptionResponse',
    'SkillCreate', 'SkillResponse',
    'CreateResponsibilityRequest', 'UpdateResponsibilityRequest',
    'ResponsibilityResponse', 'ReorderResponsibilitiesRequest',
}

# Symbols that should remain as `from main import ...`
KEEP_FROM_MAIN = {
    'app', 'logger', 'SECRET_KEY', 'ENVIRONMENT', 'DATABASE_URL',
    'pwd_context', 'openai_client', 'scheduler',
    'get_password_hash', 'verify_password',
    'create_access_token', 'create_refresh_token',
    'get_cached', 'set_cached', 'clear_cache',
    'log_ai_action_to_mission_control', 'update_ai_action_to_mission_control',
    'update_ai_action_outcome', 'security_stats',
    # DRE re-exports (complex dependency chain, leave for now)
    'process_microsoft_email_to_dre', 'fetch_microsoft_emails',
    'generate_email_signature_html', 'calculate_lead_score',
    'get_entity_name', 'classify_email_intent', 'generate_recommended_action',
    'classify_email_content', 'extract_loan_fields', 'extract_borrower_from_subject',
    'match_entity', 'apply_extracted_data', 'delete_microsoft_email',
}

# Files to skip entirely
SKIP_FILES = {
    'main.py',                     # Don't modify main.py itself
    'auth/dependencies.py',        # This IS the bridge, uses lazy import from main
    'tests/conftest.py',           # Test config needs app from main
    'tests/qa/security_tests.py',  # Test files that import app
    'tests/qa/e2e_journey_tests.py',
    'scripts/validate_workflow_sla_system.py',  # Uses app
}


def classify_symbol(sym: str) -> str:
    """Classify a symbol to its target module."""
    # Strip alias (handle `Lead as Contact`)
    base = sym.split(' as ')[0].strip() if ' as ' in sym else sym.strip()

    if base in AUTH_SYMBOLS:
        return 'auth'
    elif base in DB_SYMBOLS:
        return 'database'
    elif base in ENUM_SYMBOLS:
        return 'enum'
    elif base in MODEL_SYMBOLS:
        return 'model'
    elif base in SCHEMA_SYMBOLS:
        return 'schema'
    elif base in KEEP_FROM_MAIN:
        return 'keep'
    else:
        # Unknown symbol — keep from main to be safe
        return 'keep'


def build_import_line(module: str, symbols: list, indent: str) -> str:
    """Build a properly formatted import line."""
    sym_str = ', '.join(symbols)
    line = f"{indent}from {module} import {sym_str}"
    if len(line) > 100 and len(symbols) > 2:
        # Multi-line format
        lines = [f"{indent}from {module} import ("]
        for i, sym in enumerate(symbols):
            comma = ',' if i < len(symbols) - 1 else ','
            lines.append(f"{indent}    {sym}{comma}")
        lines.append(f"{indent})")
        return '\n'.join(lines)
    return line


MODULE_MAP = {
    'auth': 'auth.dependencies',
    'database': 'database',
    'enum': 'database.enums',
    'model': 'database.models',
    'schema': 'schemas.core',
    'keep': 'main',
}


def extract_import_block(content: str, start_pos: int):
    """
    Extract a complete `from main import ...` block starting at start_pos.
    Returns (full_match_text, list_of_symbols, end_pos).
    Handles both single-line and multi-line (parenthesized) imports.
    """
    # Find the line start
    line_start = content.rfind('\n', 0, start_pos) + 1

    # Get indentation
    indent = ''
    for ch in content[line_start:]:
        if ch in ' \t':
            indent += ch
        else:
            break

    # Check if it's a multi-line import (has opening paren)
    rest = content[start_pos:]

    # Match: from main import (...)  or  from main import X, Y, Z
    # First try parenthesized
    paren_match = re.match(r'from\s+main\s+import\s*\(', rest)
    if paren_match:
        # Find closing paren
        paren_start = start_pos + paren_match.end() - 1  # position of (
        depth = 1
        i = paren_start + 1
        while i < len(content) and depth > 0:
            if content[i] == '(':
                depth += 1
            elif content[i] == ')':
                depth -= 1
            i += 1

        full_text = content[line_start:i]
        # Extract symbols between parens
        inner = content[paren_start + 1:i - 1]
        # Parse symbols: split by comma, strip whitespace and comments
        symbols = []
        for part in inner.split(','):
            part = part.strip()
            # Remove inline comments
            if '#' in part:
                part = part[:part.index('#')].strip()
            if part and part not in ('', '\n'):
                # Handle multi-word (with alias)
                part = ' '.join(part.split())  # normalize whitespace
                if part:
                    symbols.append(part)

        return full_text, symbols, indent, i

    # Single-line import
    line_end = content.find('\n', start_pos)
    if line_end == -1:
        line_end = len(content)

    full_text = content[line_start:line_end]

    # Check for line continuation with backslash
    while full_text.rstrip().endswith('\\'):
        next_line_end = content.find('\n', line_end + 1)
        if next_line_end == -1:
            next_line_end = len(content)
        full_text = content[line_start:next_line_end]
        line_end = next_line_end

    # Extract symbols
    match = re.match(r'.*from\s+main\s+import\s+(.+)', full_text, re.DOTALL)
    if not match:
        return full_text, [], indent, line_end

    sym_text = match.group(1).strip()
    # Remove trailing comments on the line
    if '#' in sym_text and 'as' not in sym_text.split('#')[1]:
        sym_text = sym_text[:sym_text.index('#')].strip()

    symbols = []
    for part in sym_text.split(','):
        part = part.strip().rstrip('\\').strip()
        if '#' in part:
            part = part[:part.index('#')].strip()
        if part:
            symbols.append(part)

    return full_text, symbols, indent, line_end


def process_file(filepath: str, dry_run: bool = False) -> dict:
    """Process a single file, rewriting `from main import` statements."""
    rel_path = os.path.relpath(filepath, BACKEND_DIR)

    # Check skip list
    for skip in SKIP_FILES:
        if rel_path == skip or rel_path.endswith('/' + skip):
            return {'skipped': True, 'reason': 'in skip list'}

    with open(filepath, 'r') as f:
        content = f.read()

    if 'from main import' not in content:
        return {'skipped': True, 'reason': 'no main imports'}

    original = content
    changes = []

    # Find all `from main import` occurrences
    # Process from end to start so positions remain valid
    positions = []
    for m in re.finditer(r'from\s+main\s+import\s', content):
        positions.append(m.start())

    positions.reverse()  # Process from end to start

    for pos in positions:
        full_text, symbols, indent, end_pos = extract_import_block(content, pos)

        if not symbols:
            continue

        # Classify each symbol
        grouped = defaultdict(list)
        for sym in symbols:
            category = classify_symbol(sym)
            grouped[category].append(sym)

        # If everything stays as 'keep', no change needed
        if list(grouped.keys()) == ['keep']:
            continue

        # Build replacement import lines
        new_lines = []
        for category in ['auth', 'database', 'enum', 'model', 'schema', 'keep']:
            if category in grouped:
                module = MODULE_MAP[category]
                syms = grouped[category]
                new_lines.append(build_import_line(module, syms, indent))

        replacement = '\n'.join(new_lines)

        # Find the actual start of the line (including indentation)
        line_start = content.rfind('\n', 0, pos)
        line_start = line_start + 1 if line_start != -1 else 0

        changes.append({
            'original': full_text.strip(),
            'replacement': replacement.strip(),
            'symbols': symbols,
            'grouped': dict(grouped),
        })

        content = content[:line_start] + replacement + content[end_pos:]

    if not changes:
        return {'skipped': True, 'reason': 'no changes needed'}

    if not dry_run:
        with open(filepath, 'w') as f:
            f.write(content)

    return {
        'modified': True,
        'changes': len(changes),
        'details': changes,
    }


def find_python_files(root: str) -> list:
    """Find all Python files under root, excluding venv and __pycache__."""
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip directories
        dirnames[:] = [d for d in dirnames if d not in {
            '__pycache__', '.venv', 'venv', 'node_modules', '.git',
        }]
        for fn in filenames:
            if fn.endswith('.py'):
                files.append(os.path.join(dirpath, fn))
    return sorted(files)


# ============================================================================
# MAIN
# ============================================================================

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR.endswith('/scripts'):
    BACKEND_DIR = os.path.dirname(BACKEND_DIR)

# Allow running from backend/ directly
if os.path.basename(BACKEND_DIR) != 'backend':
    # Try to find backend dir
    candidate = os.path.join(BACKEND_DIR, 'backend')
    if os.path.isdir(candidate):
        BACKEND_DIR = candidate

def main():
    dry_run = '--dry-run' in sys.argv
    verbose = '--verbose' in sys.argv or '-v' in sys.argv

    if dry_run:
        print("=== DRY RUN MODE — no files will be modified ===\n")

    files = find_python_files(BACKEND_DIR)
    print(f"Scanning {len(files)} Python files in {BACKEND_DIR}\n")

    modified_count = 0
    skipped_count = 0
    total_changes = 0
    migration_details = []

    for filepath in files:
        rel = os.path.relpath(filepath, BACKEND_DIR)
        result = process_file(filepath, dry_run=dry_run)

        if result.get('skipped'):
            skipped_count += 1
            if verbose and result.get('reason') != 'no main imports':
                print(f"  SKIP {rel}: {result['reason']}")
        elif result.get('modified'):
            modified_count += 1
            total_changes += result['changes']
            migration_details.append((rel, result))
            print(f"  {'WOULD MODIFY' if dry_run else 'MODIFIED'} {rel} ({result['changes']} import blocks)")
            if verbose:
                for detail in result['details']:
                    print(f"    - {detail['original'][:80]}...")
                    for cat, syms in detail['grouped'].items():
                        if cat != 'keep':
                            print(f"      → {MODULE_MAP[cat]}: {', '.join(syms)}")

    print(f"\n{'=' * 60}")
    print(f"Summary:")
    print(f"  Files scanned: {len(files)}")
    print(f"  Files modified: {modified_count}")
    print(f"  Files skipped: {skipped_count}")
    print(f"  Import blocks rewritten: {total_changes}")

    if dry_run:
        print(f"\nRe-run without --dry-run to apply changes.")


if __name__ == '__main__':
    main()
