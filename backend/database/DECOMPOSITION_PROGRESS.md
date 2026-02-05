# Main.py Decomposition Progress

## Overview
The 75,847-line main.py is being decomposed into a modular structure. This document tracks progress and provides patterns for continuing the work.

## Completed

### 1. Database Package Restructuring
- Renamed `database.py` to `db.py` to avoid naming conflict with `database/` package
- Updated `database/__init__.py` to re-export from `db.py`
- All existing `from database import ...` statements continue to work

### 2. Enums Extraction
**File:** `database/enums.py`

Extracted 21 enum classes:
- Pipeline: `LeadStage`, `LoanStage`
- Rate Lock: `RateLockStatus`, `RateLockRecommendation`, `BuyingTimelineCategory`, `BorrowerRiskProfile`
- Tasks: `TaskType`, `ActivityType`
- Documents: `EmailIntakeMatchStatus`, `AttachmentClassificationStatus`, `DocumentType`, `DocumentCategory`
- Permissions: `InviteStatus`, `PermissionLevel`
- Dialer: `DialerSessionStatus`, `DialerTaskStatus`, `CallOutcome`
- Borrower: `SocialProvider`, `ApplicationStatus`, `ApplicationStep`
- AI: `CoachMode`

### 3. Core Models Extraction
**File:** `database/models/core.py`

Extracted 11 core models:
- Organization: `Organization`, `Branch`
- User/Auth: `User`, `ApiKey`, `UserSettings`
- Calendar: `CalendarAssignment`
- Email: `EmailSignature`
- Security: `ImpersonationSession`
- Onboarding: `OnboardingProgress`, `OnboardingError`, `VerificationToken`

### 4. Lead & Loan Models Extraction
**File:** `database/models/lead_loan.py`

Extracted 2 core pipeline models:
- `Lead` - Full lead model with 100+ fields (Salesforce sync, rate lock, workflow, etc.)
- `Loan` - Full loan model with 100+ fields (SLA dates, rate lock, disclosure tracking, etc.)

## Remaining Work

### Models to Extract (~90 more models)
Source: main.py lines ~638-3845

| Module | Models | main.py Lines |
|--------|--------|---------------|
| `lead_loan.py` | Lead, Loan, StageHistory | 638-1024 |
| `communication.py` | Activity, SMSMessage, EmailMessage, TeamsMessage, Conversation | 1361-1757 |
| `document.py` | Document, EmailIntake, AttachmentIntake | 1104-1253 |
| `ai.py` | AITask, AIDelegatedTask, AIFeedbackLog, AIAction, etc. | 1024-1100, 1417-1500 |
| `dialer.py` | DialerSession, DialerSessionTask, CallLog, ActiveCall, etc. | 3174-3311 |
| `borrower.py` | BorrowerProfile, BorrowerApplication, ApplicationDocument, etc. | 3320-3733 |
| `compliance.py` | AuditLog, UserSession, SecuritySnapshot, etc. | 2865-3000 |

### Pydantic Schemas to Extract
Source: main.py lines ~3845-5450

Target: `backend/schemas/` directory

### Pattern for Extracting Models

1. **Copy the model class from main.py**
2. **Update imports at top of file:**
   ```python
   from datetime import datetime, timezone
   from sqlalchemy import Column, Integer, String, ...
   from sqlalchemy.orm import relationship
   from db import Base
   ```
3. **Add to module's `__all__` list**
4. **Add import to `models/__init__.py`**
5. **Test imports:** `python -c "from database.models.X import Y"`

### Pattern for Updating main.py

Once all models are extracted:
1. Replace inline model definitions with imports
2. Remove enum definitions (now in database/enums.py)
3. Remove model definitions (now in database/models/)
4. Keep: FastAPI app setup, middleware, auth functions, route registrations

## Testing

```bash
# Test database package
python -c "from database import Base, SessionLocal, LeadStage"

# Test models
python -c "from database.models.core import User, Organization"

# Test enums
python -c "from database.enums import DocumentType, LeadStage"
```

## Files Changed

| File | Change |
|------|--------|
| `database.py` | Renamed to `db.py` |
| `database/__init__.py` | Updated to import from `db.py`, export enums |
| `database/enums.py` | NEW - All enum definitions |
| `database/models/__init__.py` | NEW - Model package init |
| `database/models/core.py` | NEW - Core models |
