# Stage-Based Permissions System

A comprehensive permission system for the Mortgage CRM that organizes access control around three loan lifecycle stages: Lead Management, Active Loan, and Portfolio.

## Overview

This system enables:
- **Subscription-based licensing** - Organizations pay only for the stages they need
- **Role-based templates** - Pre-configured permission sets for common roles
- **Granular control** - Fine-grained permissions within each stage
- **Data scoping** - Control what records users can see (all, team, assigned, etc.)

## Quick Start

### 1. Database Setup

```bash
# Run the schema migration
psql -d mortgage_crm -f docs/permissions/permissions-database-schema.sql
```

### 2. Backend Integration

```python
# Include the permissions router in your FastAPI app
from routers.permissions_routes import router as permissions_router

app.include_router(permissions_router)
```

### 3. Frontend Integration

```typescript
// Wrap your app with the PermissionProvider
import { PermissionProvider } from './contexts/PermissionContext';

function App() {
  return (
    <PermissionProvider>
      <YourApp />
    </PermissionProvider>
  );
}
```

## Loan Stages

| Stage | Description | Icon |
|-------|-------------|------|
| **Lead** | Lead intake, qualification, pre-approval, nurturing | 👥 |
| **Active Loan** | Processing, underwriting, closing, rate locks | 📄 |
| **Portfolio** | Client retention, MUM, referrals, anniversaries | 💼 |

## Subscription Tiers

| Tier | Stages Included | Use Case |
|------|-----------------|----------|
| **Starter** | Lead only | Inside sales teams, SDRs |
| **Professional** | Lead + Active Loan | Loan officers, processors |
| **Enterprise** | All stages | Full mortgage operations |
| **Custom** | Configurable | Specific business needs |

## Permission Templates

Each stage includes pre-built templates:

### Lead Stage
- **Full Access** - Complete admin control
- **Standard Loan Officer** - Lead management, pipeline, clients
- **SDR / Inside Sales** - Lead intake and qualification
- **Read Only** - View-only access

### Active Loan Stage
- **Full Access** - Complete admin control
- **Standard Loan Officer** - Origination, rate locks, documents
- **Processing Team** - Document processing and verification
- **Underwriter** - Underwriting decisions and conditions
- **Read Only** - View-only access

### Portfolio Stage
- **Full Access** - Complete admin control
- **Standard Loan Officer** - Client relationships, MUM, referrals
- **Analyst** - Portfolio analytics and reporting
- **Read Only** - View-only access

## Permission Key Format

Permissions follow the pattern: `{stage}.{category}.{action}`

Examples:
- `lead.intake.view_all` - View all leads
- `loan.processing.edit` - Edit loan processing data
- `portfolio.mum.analyze` - Access MUM analysis tools

## Data Scopes

Control what records a user can access:

| Scope | Description |
|-------|-------------|
| `all` | All records in the system |
| `team` | Records for team members |
| `territory` | Records in assigned territory |
| `branch` | Records in user's branch |
| `assigned` | Only personally assigned records |
| `none` | No direct record access |

## Usage Examples

### Check Permission (Frontend)

```typescript
import { usePermissions } from './contexts/PermissionContext';

function LeadActions() {
  const { hasPermission } = usePermissions();

  return (
    <div>
      {hasPermission('lead.intake.create') && (
        <button>Create Lead</button>
      )}
      {hasPermission('lead.intake.delete') && (
        <button>Delete Lead</button>
      )}
    </div>
  );
}
```

### Permission Gate Component

```typescript
import { PermissionGate } from './components/PermissionGate';

function Dashboard() {
  return (
    <div>
      <PermissionGate stage="lead">
        <LeadDashboard />
      </PermissionGate>

      <PermissionGate permission="loan.processing.view_pipeline">
        <LoanPipeline />
      </PermissionGate>

      <PermissionGate
        permissions={['admin.users.view', 'admin.users.edit']}
        requireAll
      >
        <UserManagement />
      </PermissionGate>
    </div>
  );
}
```

### Check Permission (Backend)

```python
from auth.permissions import require_permission

@router.get("/leads")
@require_permission("lead.intake.view_all")
async def get_leads(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # User has verified permission
    return await lead_service.get_all(db)
```

### Bulk Permission Setup

```typescript
// Set up user permissions during onboarding
const stages = [
  {
    stageCode: 'lead',
    templateCode: 'lead_officer',
    dataScope: 'assigned'
  },
  {
    stageCode: 'active_loan',
    templateCode: 'loan_officer',
    dataScope: 'assigned'
  }
];

await permissionsService.bulkSetupPermissions(userId, stages);
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/permissions/stages` | List all loan stages |
| GET | `/api/v1/permissions/templates` | Get permission templates |
| GET | `/api/v1/permissions/users/{id}` | Get user's permissions |
| POST | `/api/v1/permissions/users/stage-access` | Grant stage access |
| POST | `/api/v1/permissions/check` | Check specific permission |
| POST | `/api/v1/permissions/override` | Create permission override |
| GET | `/api/v1/permissions/audit-log` | View permission changes |

## Files in This System

| File | Purpose |
|------|---------|
| `permissions-matrix.md` | Complete permission definitions by stage |
| `permissions-database-schema.sql` | Database tables and functions |
| `ARCHITECTURE_DIAGRAM.md` | System architecture diagrams |
| `IMPLEMENTATION_GUIDE.md` | Step-by-step implementation guide |
| `permissionsService.ts` | Frontend API service |
| `permissions_routes.py` | Backend API routes |
| `PermissionsStep.tsx` | Onboarding wizard component |

## Permission Resolution Order

When checking permissions, the system resolves in this order:

1. **Subscription Tier** - Does the organization have access to this stage?
2. **Stage Access** - Does the user have access to this stage?
3. **Template Permissions** - What does the user's template allow?
4. **Overrides** - Are there any specific grants or denials?
5. **Temporary Grants** - Any time-limited special access?

## Best Practices

### Do's
- Use templates for standard roles
- Set appropriate data scopes
- Use overrides for exceptions
- Log permission changes
- Review permissions periodically

### Don'ts
- Don't give `all` scope unless necessary
- Don't bypass permission checks
- Don't hardcode permission strings
- Don't grant admin templates liberally

## Troubleshooting

### User can't access a feature
1. Check organization subscription tier
2. Verify user has stage access
3. Review template permissions
4. Check for denial overrides

### Permission check is slow
1. Enable permission caching
2. Use bulk permission fetch on login
3. Cache results in frontend context

### Override not working
1. Check override `is_active` flag
2. Verify `expires_at` hasn't passed
3. Ensure override matches exact permission key

## Support

For implementation help, see:
- [Architecture Diagram](./ARCHITECTURE_DIAGRAM.md)
- [Implementation Guide](./IMPLEMENTATION_GUIDE.md)
- [Permission Matrix](./permissions-matrix.md)

## License

Proprietary - Internal use only.
