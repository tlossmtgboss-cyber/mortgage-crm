# Perennia AI - Stage-Based Permissions Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           PERENNIA AI PERMISSIONS SYSTEM                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                        SUBSCRIPTION LAYER                                │   │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐ │   │
│  │  │   Starter   │   │Professional │   │ Enterprise  │   │   Custom    │ │   │
│  │  │  Lead Only  │   │ Lead + Loan │   │ All Stages  │   │ Pick Stages │ │   │
│  │  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                          │
│                                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                          LOAN STAGES                                     │   │
│  │                                                                          │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │   │
│  │  │      LEAD       │  │   ACTIVE LOAN   │  │    PORTFOLIO    │         │   │
│  │  │                 │  │                 │  │                 │         │   │
│  │  │ • Lead Intake   │  │ • Processing    │  │ • Client Mgmt   │         │   │
│  │  │ • Qualification │  │ • Underwriting  │  │ • MUM Dashboard │         │   │
│  │  │ • Communication │  │ • Closing       │  │ • Campaigns     │         │   │
│  │  │ • Analytics     │  │ • Rate Lock     │  │ • Referrals     │         │   │
│  │  │ • Automation    │  │ • Compliance    │  │ • Analytics     │         │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘         │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                          │
│                                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                      PERMISSION TEMPLATES                                │   │
│  │                                                                          │   │
│  │  Per-Stage Templates:                                                    │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │   │
│  │  │  Full Access │  │   Standard   │  │  Read Only   │  │ Specialized  │ │   │
│  │  │    (Admin)   │  │  (LO/User)   │  │   (Viewer)   │  │ (Processor)  │ │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                          │
│                                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         USER PERMISSIONS                                 │   │
│  │                                                                          │   │
│  │  User Permission = Subscription ∩ Stage Access ∩ Template ∪ Overrides   │   │
│  │                                                                          │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │   │
│  │  │  Stage Access    │  Template Perms  │  Overrides  │  Data Scope  │    │   │
│  │  │  (lead: ✓)       │  lead_officer    │  +custom    │  assigned    │    │   │
│  │  │  (active: ✓)     │  loan_processor  │  -specific  │  team        │    │   │
│  │  │  (portfolio: ✗)  │  N/A             │  N/A        │  N/A         │    │   │
│  │  └─────────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            PERMISSION CHECK FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   User Request                                                                   │
│        │                                                                         │
│        ▼                                                                         │
│   ┌─────────────────────────────────────────────┐                              │
│   │  1. CHECK SUBSCRIPTION                       │                              │
│   │     Does org subscription include stage?     │                              │
│   │     ┌─────────────────────────────────────┐ │                              │
│   │     │ org_subscriptions.enabled_stages    │ │                              │
│   │     │ CONTAINS requested_stage?           │ │                              │
│   │     └─────────────────────────────────────┘ │                              │
│   └─────────────────────────────────────────────┘                              │
│        │ Yes                    │ No                                            │
│        ▼                        ▼                                               │
│   ┌──────────────────┐    ┌──────────────────┐                                 │
│   │  Continue        │    │  DENY ACCESS     │                                 │
│   └──────────────────┘    │  (Upgrade sub)   │                                 │
│        │                   └──────────────────┘                                 │
│        ▼                                                                         │
│   ┌─────────────────────────────────────────────┐                              │
│   │  2. CHECK STAGE ACCESS                       │                              │
│   │     Does user have this stage enabled?       │                              │
│   │     ┌─────────────────────────────────────┐ │                              │
│   │     │ user_stage_access                   │ │                              │
│   │     │ WHERE user_id AND stage_code        │ │                              │
│   │     │ AND is_active = TRUE                │ │                              │
│   │     │ AND (expires_at IS NULL OR > NOW)   │ │                              │
│   │     └─────────────────────────────────────┘ │                              │
│   └─────────────────────────────────────────────┘                              │
│        │ Yes                    │ No                                            │
│        ▼                        ▼                                               │
│   ┌──────────────────┐    ┌──────────────────┐                                 │
│   │  Continue        │    │  DENY ACCESS     │                                 │
│   └──────────────────┘    │  (Request access)│                                 │
│        │                   └──────────────────┘                                 │
│        ▼                                                                         │
│   ┌─────────────────────────────────────────────┐                              │
│   │  3. CHECK OVERRIDE (FIRST PRIORITY)          │                              │
│   │     Is there a specific override?            │                              │
│   │     ┌─────────────────────────────────────┐ │                              │
│   │     │ user_permission_overrides           │ │                              │
│   │     │ WHERE permission_key = requested    │ │                              │
│   │     │ AND (expires_at IS NULL OR > NOW)   │ │                              │
│   │     └─────────────────────────────────────┘ │                              │
│   └─────────────────────────────────────────────┘                              │
│        │ Found                  │ Not Found                                     │
│        ▼                        ▼                                               │
│   ┌──────────────────┐    ┌──────────────────────────────────────┐             │
│   │  Return override │    │  4. CHECK TEMPLATE PERMISSION        │             │
│   │  granted value   │    │     Is permission in user's template?│             │
│   └──────────────────┘    │     ┌──────────────────────────────┐ │             │
│                           │     │ stage_permission_templates   │ │             │
│                           │     │ .permissions->>key = true    │ │             │
│                           │     └──────────────────────────────┘ │             │
│                           └──────────────────────────────────────┘             │
│                                │ True              │ False                      │
│                                ▼                   ▼                            │
│                           ┌──────────┐        ┌──────────┐                     │
│                           │  ALLOW   │        │  DENY    │                     │
│                           └──────────┘        └──────────┘                     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Database Schema Relationships

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          DATABASE ENTITY RELATIONSHIPS                           │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌───────────────────────┐          ┌───────────────────────┐                   │
│  │  subscription_tiers   │          │       loan_stages     │                   │
│  ├───────────────────────┤          ├───────────────────────┤                   │
│  │ id                    │          │ id                    │                   │
│  │ name                  │          │ code (PK)             │◄─────────┐        │
│  │ stages[] (JSON)       │──────────│ name                  │          │        │
│  │ features (JSON)       │          │ description           │          │        │
│  │ price_monthly         │          │ icon, color           │          │        │
│  └───────────────────────┘          └───────────────────────┘          │        │
│           │                                    │                        │        │
│           │                                    │                        │        │
│           ▼                                    ▼                        │        │
│  ┌───────────────────────┐          ┌───────────────────────┐          │        │
│  │ organization_subs     │          │ permission_definitions│          │        │
│  ├───────────────────────┤          ├───────────────────────┤          │        │
│  │ id                    │          │ id                    │          │        │
│  │ organization_id       │          │ key (unique)          │          │        │
│  │ subscription_tier_id  │◄─────────│ stage_code (FK)       │──────────┘        │
│  │ enabled_stages[]      │          │ category              │                   │
│  │ status                │          │ name, description     │                   │
│  │ billing_cycle         │          │ risk_level            │                   │
│  └───────────────────────┘          └───────────────────────┘                   │
│           │                                                                      │
│           │                                                                      │
│           ▼                                                                      │
│  ┌───────────────────────┐          ┌───────────────────────┐                   │
│  │        users          │          │ stage_perm_templates  │                   │
│  ├───────────────────────┤          ├───────────────────────┤                   │
│  │ id                    │◄────┐    │ id                    │                   │
│  │ email                 │     │    │ code (unique)         │                   │
│  │ organization_id       │     │    │ name                  │                   │
│  └───────────────────────┘     │    │ stage_code (FK)       │───────────────────┤
│           │                    │    │ role_type             │                   │
│           │                    │    │ permissions (JSON)    │                   │
│           ▼                    │    │ default_scope         │                   │
│  ┌───────────────────────┐     │    └───────────────────────┘                   │
│  │   user_stage_access   │     │              │                                 │
│  ├───────────────────────┤     │              │                                 │
│  │ id                    │     │              │                                 │
│  │ user_id (FK)          │─────┘              │                                 │
│  │ stage_code (FK)       │────────────────────┤                                 │
│  │ template_id (FK)      │◄───────────────────┘                                 │
│  │ data_scope            │                                                      │
│  │ is_active             │                                                      │
│  │ expires_at            │                                                      │
│  └───────────────────────┘                                                      │
│           │                                                                      │
│           ▼                                                                      │
│  ┌───────────────────────┐          ┌───────────────────────┐                   │
│  │ user_perm_overrides   │          │ stage_perm_requests   │                   │
│  ├───────────────────────┤          ├───────────────────────┤                   │
│  │ id                    │          │ id                    │                   │
│  │ user_id (FK)          │          │ user_id (FK)          │                   │
│  │ permission_key        │          │ request_type          │                   │
│  │ granted               │          │ stage_code            │                   │
│  │ scope_override        │          │ permission_key        │                   │
│  │ is_temporary          │          │ justification         │                   │
│  │ expires_at            │          │ status                │                   │
│  │ reason                │          │ reviewed_by           │                   │
│  └───────────────────────┘          └───────────────────────┘                   │
│                                                                                  │
│                                     │                                            │
│                                     ▼                                            │
│                            ┌───────────────────────┐                            │
│                            │  permission_audit_log │                            │
│                            ├───────────────────────┤                            │
│                            │ id                    │                            │
│                            │ user_id, actor_id     │                            │
│                            │ action, entity_type   │                            │
│                            │ previous_value (JSON) │                            │
│                            │ new_value (JSON)      │                            │
│                            │ timestamp             │                            │
│                            └───────────────────────┘                            │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Frontend Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND PERMISSIONS ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                          PermissionProvider                              │   │
│  │                     (Context at App Root Level)                          │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │   │
│  │  │ State:                                                          │    │   │
│  │  │   - userPermissions: Record<string, boolean>                    │    │   │
│  │  │   - enabledStages: LoanStage[]                                  │    │   │
│  │  │   - stageAccess: UserStageAccess[]                              │    │   │
│  │  │   - loading: boolean                                            │    │   │
│  │  │                                                                 │    │   │
│  │  │ Methods:                                                        │    │   │
│  │  │   - hasPermission(key: string): boolean                         │    │   │
│  │  │   - hasStageAccess(stage: LoanStage): boolean                   │    │   │
│  │  │   - getDataScope(stage: LoanStage): DataScope                   │    │   │
│  │  │   - refreshPermissions(): Promise<void>                         │    │   │
│  │  └─────────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                          │
│          ┌───────────────────────────┼───────────────────────────┐              │
│          ▼                           ▼                           ▼              │
│  ┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐         │
│  │   PermissionGate  │   │  StageGate        │   │  ScopeGate        │         │
│  │   (HOC/Component) │   │  (HOC/Component)  │   │  (HOC/Component)  │         │
│  ├───────────────────┤   ├───────────────────┤   ├───────────────────┤         │
│  │ Props:            │   │ Props:            │   │ Props:            │         │
│  │ - permission      │   │ - stage           │   │ - requiredScope   │         │
│  │ - fallback        │   │ - fallback        │   │ - currentRecord   │         │
│  │ - children        │   │ - children        │   │ - children        │         │
│  └───────────────────┘   └───────────────────┘   └───────────────────┘         │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                          Page Components                                 │   │
│  │                                                                          │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐          │   │
│  │  │   LeadsPage     │  │   LoansPage     │  │  PortfolioPage  │          │   │
│  │  │  (Lead Stage)   │  │ (Active Loan)   │  │ (Portfolio)     │          │   │
│  │  │                 │  │                 │  │                 │          │   │
│  │  │ <StageGate      │  │ <StageGate      │  │ <StageGate      │          │   │
│  │  │   stage="lead"> │  │  stage="active_ │  │  stage="port-   │          │   │
│  │  │   <LeadsList/>  │  │  loan">         │  │  folio">        │          │   │
│  │  │ </StageGate>    │  │   <LoansList/>  │  │   <ClientList/> │          │   │
│  │  │                 │  │ </StageGate>    │  │ </StageGate>    │          │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘          │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                        Admin/Settings Pages                              │   │
│  │                                                                          │   │
│  │  ┌─────────────────────────┐   ┌─────────────────────────┐              │   │
│  │  │    PermissionsStep      │   │    UserPermissions      │              │   │
│  │  │   (Onboarding Wizard)   │   │   (Admin Settings)      │              │   │
│  │  │                         │   │                         │              │   │
│  │  │ - Stage selection       │   │ - View user access      │              │   │
│  │  │ - Template selection    │   │ - Grant/revoke stages   │              │   │
│  │  │ - Custom permissions    │   │ - Apply templates       │              │   │
│  │  │ - Preview & confirm     │   │ - Set overrides         │              │   │
│  │  └─────────────────────────┘   │ - Audit log             │              │   │
│  │                                 └─────────────────────────┘              │   │
│  │  ┌─────────────────────────┐   ┌─────────────────────────┐              │   │
│  │  │  SubscriptionSettings   │   │  PermissionRequests     │              │   │
│  │  │    (Org Settings)       │   │   (Self-Service)        │              │   │
│  │  │                         │   │                         │              │   │
│  │  │ - Current tier          │   │ - Request new access    │              │   │
│  │  │ - Stage enablement      │   │ - View pending requests │              │   │
│  │  │ - Upgrade options       │   │ - Request history       │              │   │
│  │  └─────────────────────────┘   └─────────────────────────┘              │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## API Endpoint Structure

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              API ENDPOINTS                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  /api/v1/permissions                                                            │
│  │                                                                               │
│  ├── /stages                                                                     │
│  │   ├── GET /                           # List all stages                      │
│  │   └── GET /enabled                    # Get org's enabled stages            │
│  │                                                                               │
│  ├── /definitions                                                                │
│  │   ├── GET /                           # List all permission definitions      │
│  │   ├── GET /grouped                    # Grouped by stage & category          │
│  │   └── GET /stage/{code}               # Permissions for specific stage       │
│  │                                                                               │
│  ├── /templates                                                                  │
│  │   ├── GET /                           # List all templates                   │
│  │   ├── GET /stage/{code}               # Templates for specific stage         │
│  │   ├── GET /{code}                     # Get specific template                │
│  │   ├── POST /                          # Create custom template               │
│  │   └── PATCH /{id}                     # Update template                      │
│  │                                                                               │
│  ├── /users/{user_id}                                                           │
│  │   ├── GET /profile                    # Full permission profile              │
│  │   ├── GET /stages                     # User's stage access                  │
│  │   ├── POST /stages                    # Grant stage access                   │
│  │   ├── DELETE /stages/{code}           # Revoke stage access                  │
│  │   ├── POST /stages/{code}/apply-template  # Apply template                   │
│  │   ├── PATCH /stages/{code}            # Update scope                         │
│  │   │                                                                           │
│  │   ├── GET /overrides                  # Get permission overrides             │
│  │   ├── POST /overrides                 # Add override                         │
│  │   ├── DELETE /overrides/{key}         # Remove override                      │
│  │   │                                                                           │
│  │   ├── GET /check/{key}                # Check single permission              │
│  │   ├── POST /check-any                 # Check any of permissions             │
│  │   ├── POST /check-all                 # Check all permissions                │
│  │   ├── GET /effective                  # All effective permissions            │
│  │   │                                                                           │
│  │   └── GET /audit                      # Permission audit log                 │
│  │                                                                               │
│  └── /requests                                                                   │
│      ├── POST /                          # Create permission request            │
│      ├── GET /my                         # User's own requests                  │
│      ├── GET /pending                    # Pending requests (for managers)      │
│      ├── POST /{id}/approve              # Approve request                      │
│      ├── POST /{id}/deny                 # Deny request                         │
│      ├── POST /{id}/more-info            # Request more info                    │
│      └── POST /{id}/cancel               # Cancel request                       │
│                                                                                  │
│  /api/v1/subscriptions                                                          │
│  │                                                                               │
│  ├── GET /tiers                          # Available subscription tiers         │
│  ├── GET /current                        # Current org subscription             │
│  └── PATCH /current/stages               # Update enabled stages (custom)       │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Caching Strategy

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            CACHING ARCHITECTURE                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                          REDIS CACHE LAYER                               │   │
│  │                                                                          │   │
│  │  Key Pattern                        TTL       Description                │   │
│  │  ─────────────────────────────────────────────────────────────────────  │   │
│  │  perm:user:{user_id}:effective      60s       All effective permissions  │   │
│  │  perm:user:{user_id}:stages         60s       User's stage access        │   │
│  │  perm:org:{org_id}:subscription     300s      Org subscription details   │   │
│  │  perm:templates                     3600s     All permission templates   │   │
│  │  perm:definitions                   3600s     Permission definitions     │   │
│  │                                                                          │   │
│  │  Cache Invalidation Triggers:                                            │   │
│  │  • User stage access change → invalidate perm:user:{id}:*                │   │
│  │  • Permission override change → invalidate perm:user:{id}:effective      │   │
│  │  • Template change → invalidate perm:templates + all users with template │   │
│  │  • Subscription change → invalidate perm:org:{id}:subscription           │   │
│  │                                                                          │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                        FRONTEND CACHE (React Query)                      │   │
│  │                                                                          │   │
│  │  Query Key                           Stale Time   Description            │   │
│  │  ─────────────────────────────────────────────────────────────────────  │   │
│  │  ['permissions', userId, 'profile']    30s        User's full profile   │   │
│  │  ['permissions', 'templates']          5min       All templates         │   │
│  │  ['permissions', 'definitions']        5min       Permission definitions│   │
│  │  ['subscription', 'current']           1min       Current subscription  │   │
│  │                                                                          │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Security Considerations

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           SECURITY ARCHITECTURE                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  1. AUTHORIZATION CHECKS                                                        │
│     ─────────────────────                                                       │
│     • All permission modifications require 'team.manage_permissions'             │
│     • Users can only view their own permissions (unless admin)                   │
│     • Subscription changes require org admin role                                │
│                                                                                  │
│  2. AUDIT LOGGING                                                               │
│     ─────────────────                                                           │
│     • Every permission change is logged with:                                    │
│       - Actor ID (who made the change)                                          │
│       - Previous and new values                                                 │
│       - Timestamp and IP address                                                │
│       - Reason (if provided)                                                    │
│                                                                                  │
│  3. SEPARATION OF DUTIES                                                        │
│     ────────────────────────                                                    │
│     • permission_conflicts table defines incompatible permissions               │
│     • High-risk combinations require executive approval                         │
│     • Conflict check before granting permissions                                │
│                                                                                  │
│  4. TEMPORARY PERMISSIONS                                                       │
│     ──────────────────────                                                      │
│     • Permissions can have expiration dates                                      │
│     • Automatic cleanup of expired grants                                        │
│     • Clear audit trail for temporary access                                     │
│                                                                                  │
│  5. DATA SCOPING                                                                │
│     ───────────────                                                             │
│     • Row-level security through scope checks                                    │
│     • Scopes: all, team, territory, branch, assigned                            │
│     • Applied at query level for data filtering                                  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```
