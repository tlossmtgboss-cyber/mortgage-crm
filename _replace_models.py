#!/usr/bin/env python3
"""Script to replace model definitions with imports in main.py"""

# Read the file
with open('backend/main.py', 'r') as f:
    lines = f.readlines()

print(f'Original file: {len(lines)} lines')

# Lines 1902-3866 (0-indexed: 1901-3865)
start_idx = 1901  # line 1902 (0-indexed)

# Verify the boundaries
assert 'class SubscriptionPlan' in lines[start_idx], f'Line {start_idx+1}: {lines[start_idx].strip()}'
assert 'logger.warning' in lines[3865], f'Line 3866: {lines[3865].strip()}'

replacement_text = """# ============================================================================
# REMAINING MODELS - Imported from database/models/
# ============================================================================
# These models were extracted from main.py to dedicated module files.
# They are imported here for backward compatibility (from main import X).
from database.models.subscription import SubscriptionPlan, Subscription, PromoCode, TeamMember
from database.models.microsoft import MicrosoftToken, MicrosoftOAuthToken, MicrosoftAppConfig
from database.models.data_reconciliation import IncomingDataEvent, ExtractedData, BlockedSender, DuplicatePair, MergeTrainingEvent, MergeAIModel
from database.models.it_helpdesk import ITHelpdeskTicket, ITHelpdeskTool
from database.models.client import ClientProfile, TeamRole, ProcessFlowDocument, KPISnapshot
from database.models.hr_goals import (
    UserJobDescription, Skill, EmployeeResponsibility, ResponsibilitySkill,
    UserGoal, GoalKeyResult, GoalEmployeeAssessment, GoalManagerAssessment,
    GoalResponsibility, UserSkillAssessment,
)
from database.models.dialer import (
    AgentTelephonySettings, VerifiedCallerId, DialerSession, DialerSessionTask,
    CallLog, ActiveCall, ContactDNCStatus,
)
from database.models.borrower import (
    BorrowerProfile, BorrowerAuthEvent, BorrowerMagicLink, BorrowerApplication,
    ApplicationDocument, CoborrowerInvitation, ApplicationEvent, ApplicationNotification,
    ApplicationSession, VoiceApplicationSession,
)
from database.models.estimate import EstimateParseCache, EstimateParseFailure, EstimateComparison

# Configure mappers after all models are loaded
from sqlalchemy.orm import configure_mappers
try:
    configure_mappers()
except Exception as e:
    logger.warning(f"Mapper configuration warning (may be handled later): {e}")
"""

replacement_lines = [line + '\n' for line in replacement_text.split('\n')]
# The last element will be an empty string + newline from the trailing newline, remove the extra
if replacement_lines and replacement_lines[-1] == '\n':
    replacement_lines = replacement_lines[:-1]

# Replace lines 1902-3866 (indices 1901 through 3865 inclusive)
new_lines = lines[:start_idx] + replacement_lines + lines[3866:]

with open('backend/main.py', 'w') as f:
    f.writelines(new_lines)

removed = 3866 - start_idx
print(f'Replaced lines 1902-3866 ({removed} lines removed) with {len(replacement_lines)} lines')
print(f'New file has {len(new_lines)} total line entries')
