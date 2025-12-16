/**
 * Perennia AI - Stage-Based Permissions Service
 *
 * This service handles all permission-related operations including:
 * - Stage access management (Lead, Active Loan, Portfolio)
 * - Permission template operations
 * - Individual permission checks
 * - Permission request workflows
 */

import api from './api';

// ============================================================================
// TYPES & INTERFACES
// ============================================================================

export type LoanStage = 'lead' | 'active_loan' | 'portfolio';

export type DataScope = 'all' | 'team' | 'territory' | 'branch' | 'assigned' | 'none';

export type RoleType =
  | 'admin'
  | 'standard'
  | 'readonly'
  | 'processor'
  | 'underwriter'
  | 'closer'
  | 'sdr'
  | 'analyst';

export type RequestStatus = 'pending' | 'approved' | 'denied' | 'more_info' | 'cancelled';

export type RequestUrgency = 'low' | 'medium' | 'high' | 'critical';

// Stage definition
export interface LoanStageDefinition {
  id: number;
  code: LoanStage;
  name: string;
  description: string;
  displayOrder: number;
  icon: string;
  color: string;
  isActive: boolean;
}

// Permission definition
export interface PermissionDefinition {
  id: number;
  key: string;
  stageCode: LoanStage | null;
  category: string;
  name: string;
  description: string;
  requiresSubscription: boolean;
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
  displayOrder: number;
  groupName?: string;
  isActive: boolean;
}

// Permission template
export interface PermissionTemplate {
  id: number;
  code: string;
  name: string;
  description: string;
  stageCode: LoanStage | null;
  roleType: RoleType;
  permissions: Record<string, boolean>;
  defaultScope: DataScope;
  isSystemDefault: boolean;
  isActive: boolean;
  displayOrder: number;
}

// User's stage access
export interface UserStageAccess {
  id: number;
  userId: number;
  stageCode: LoanStage;
  accessType: 'subscription' | 'granted' | 'trial';
  templateId: number | null;
  template?: PermissionTemplate;
  dataScope: DataScope;
  isActive: boolean;
  grantedAt: string;
  grantedBy: number | null;
  expiresAt: string | null;
}

// User's complete permission profile
export interface UserPermissionProfile {
  userId: number;
  email: string;
  // Stage access
  stageAccess: UserStageAccess[];
  enabledStages: LoanStage[];
  // Computed permissions
  permissions: Record<string, boolean>;
  permissionCount: number;
  // Overrides
  overrides: PermissionOverride[];
}

// Permission override
export interface PermissionOverride {
  id: number;
  userId: number;
  permissionKey: string;
  granted: boolean;
  scopeOverride: DataScope | null;
  isTemporary: boolean;
  expiresAt: string | null;
  reason: string | null;
  grantedBy: number;
  grantedAt: string;
}

// Permission request
export interface PermissionRequest {
  id: number;
  userId: number;
  requestType: 'stage_access' | 'permission' | 'template_change' | 'scope_upgrade';
  stageCode: LoanStage | null;
  permissionKey: string | null;
  templateId: number | null;
  requestedScope: DataScope | null;
  justification: string;
  urgency: RequestUrgency;
  isTemporary: boolean;
  durationDays: number | null;
  status: RequestStatus;
  reviewedBy: number | null;
  reviewedAt: string | null;
  reviewNotes: string | null;
  createdAt: string;
  updatedAt: string;
}

// Subscription tier
export interface SubscriptionTier {
  id: number;
  name: string;
  description: string;
  stages: LoanStage[];
  features: {
    maxUsers: number;
    maxLeads: number;
    maxLoans: number;
    aiAssistant: boolean;
    advancedAnalytics: boolean;
    customWorkflows: boolean;
    apiAccess: boolean;
    whiteLabeling: boolean;
    dedicatedSupport: boolean;
  };
  priceMonthly: number | null;
  priceAnnual: number | null;
  isActive: boolean;
}

// Organization subscription
export interface OrganizationSubscription {
  id: number;
  organizationId: number;
  subscriptionTierId: number;
  tier?: SubscriptionTier;
  enabledStages: LoanStage[];
  status: 'active' | 'trial' | 'suspended' | 'cancelled';
  trialEndsAt: string | null;
  billingCycle: 'monthly' | 'annual';
  currentPeriodStart: string;
  currentPeriodEnd: string;
  currentUserCount: number;
}

// Permission check result
export interface PermissionCheckResult {
  hasPermission: boolean;
  reason?: string;
  scope?: DataScope;
}

// Grouped permissions for UI display
export interface GroupedPermissions {
  stage: LoanStageDefinition | null;
  categories: {
    name: string;
    permissions: PermissionDefinition[];
  }[];
}

// ============================================================================
// API ENDPOINTS
// ============================================================================

const PERMISSIONS_API = '/api/v1/permissions';
const STAGES_API = '/api/v1/stages';
const SUBSCRIPTIONS_API = '/api/v1/subscriptions';

// ============================================================================
// STAGE MANAGEMENT
// ============================================================================

/**
 * Get all available loan stages
 */
export async function getStages(): Promise<LoanStageDefinition[]> {
  const response = await api.get(`${STAGES_API}`);
  return response.data.stages;
}

/**
 * Get stages enabled for the current organization's subscription
 */
export async function getEnabledStages(): Promise<LoanStage[]> {
  const response = await api.get(`${STAGES_API}/enabled`);
  return response.data.enabledStages;
}

/**
 * Check if user has access to a specific stage
 */
export async function checkStageAccess(userId: number, stageCode: LoanStage): Promise<boolean> {
  const response = await api.get(`${PERMISSIONS_API}/users/${userId}/stages/${stageCode}/access`);
  return response.data.hasAccess;
}

// ============================================================================
// PERMISSION DEFINITIONS
// ============================================================================

/**
 * Get all permission definitions
 */
export async function getPermissionDefinitions(): Promise<PermissionDefinition[]> {
  const response = await api.get(`${PERMISSIONS_API}/definitions`);
  return response.data.permissions;
}

/**
 * Get permission definitions grouped by stage and category
 */
export async function getGroupedPermissions(): Promise<GroupedPermissions[]> {
  const response = await api.get(`${PERMISSIONS_API}/definitions/grouped`);
  return response.data.groups;
}

/**
 * Get permissions for a specific stage
 */
export async function getStagePermissions(stageCode: LoanStage): Promise<PermissionDefinition[]> {
  const response = await api.get(`${PERMISSIONS_API}/definitions/stage/${stageCode}`);
  return response.data.permissions;
}

// ============================================================================
// PERMISSION TEMPLATES
// ============================================================================

/**
 * Get all permission templates
 */
export async function getTemplates(): Promise<PermissionTemplate[]> {
  const response = await api.get(`${PERMISSIONS_API}/templates`);
  return response.data.templates;
}

/**
 * Get templates for a specific stage
 */
export async function getStageTemplates(stageCode: LoanStage): Promise<PermissionTemplate[]> {
  const response = await api.get(`${PERMISSIONS_API}/templates/stage/${stageCode}`);
  return response.data.templates;
}

/**
 * Get a specific template by code
 */
export async function getTemplateByCode(code: string): Promise<PermissionTemplate> {
  const response = await api.get(`${PERMISSIONS_API}/templates/${code}`);
  return response.data.template;
}

/**
 * Create a custom template
 */
export async function createTemplate(template: Partial<PermissionTemplate>): Promise<PermissionTemplate> {
  const response = await api.post(`${PERMISSIONS_API}/templates`, template);
  return response.data.template;
}

/**
 * Update a template
 */
export async function updateTemplate(
  templateId: number,
  updates: Partial<PermissionTemplate>
): Promise<PermissionTemplate> {
  const response = await api.patch(`${PERMISSIONS_API}/templates/${templateId}`, updates);
  return response.data.template;
}

// ============================================================================
// USER PERMISSIONS
// ============================================================================

/**
 * Get user's complete permission profile
 */
export async function getUserPermissionProfile(userId: number): Promise<UserPermissionProfile> {
  const response = await api.get(`${PERMISSIONS_API}/users/${userId}/profile`);
  return response.data;
}

/**
 * Get user's stage access records
 */
export async function getUserStageAccess(userId: number): Promise<UserStageAccess[]> {
  const response = await api.get(`${PERMISSIONS_API}/users/${userId}/stages`);
  return response.data.stageAccess;
}

/**
 * Grant stage access to a user
 */
export async function grantStageAccess(
  userId: number,
  stageCode: LoanStage,
  options: {
    templateCode?: string;
    dataScope?: DataScope;
    expiresAt?: string;
    reason?: string;
  } = {}
): Promise<UserStageAccess> {
  const response = await api.post(`${PERMISSIONS_API}/users/${userId}/stages`, {
    stageCode,
    ...options
  });
  return response.data.stageAccess;
}

/**
 * Revoke stage access from a user
 */
export async function revokeStageAccess(
  userId: number,
  stageCode: LoanStage,
  reason?: string
): Promise<void> {
  await api.delete(`${PERMISSIONS_API}/users/${userId}/stages/${stageCode}`, {
    data: { reason }
  });
}

/**
 * Apply a template to user's stage access
 */
export async function applyTemplate(
  userId: number,
  stageCode: LoanStage,
  templateCode: string
): Promise<{
  stageAccess: UserStageAccess;
  changesApplied: { key: string; oldValue: boolean; newValue: boolean }[]
}> {
  const response = await api.post(`${PERMISSIONS_API}/users/${userId}/stages/${stageCode}/apply-template`, {
    templateCode
  });
  return response.data;
}

/**
 * Update user's data scope for a stage
 */
export async function updateDataScope(
  userId: number,
  stageCode: LoanStage,
  dataScope: DataScope
): Promise<UserStageAccess> {
  const response = await api.patch(`${PERMISSIONS_API}/users/${userId}/stages/${stageCode}`, {
    dataScope
  });
  return response.data.stageAccess;
}

// ============================================================================
// PERMISSION OVERRIDES
// ============================================================================

/**
 * Get user's permission overrides
 */
export async function getUserOverrides(userId: number): Promise<PermissionOverride[]> {
  const response = await api.get(`${PERMISSIONS_API}/users/${userId}/overrides`);
  return response.data.overrides;
}

/**
 * Add a permission override for a user
 */
export async function addOverride(
  userId: number,
  permissionKey: string,
  granted: boolean,
  options: {
    scopeOverride?: DataScope;
    isTemporary?: boolean;
    expiresAt?: string;
    reason?: string;
  } = {}
): Promise<PermissionOverride> {
  const response = await api.post(`${PERMISSIONS_API}/users/${userId}/overrides`, {
    permissionKey,
    granted,
    ...options
  });
  return response.data.override;
}

/**
 * Remove a permission override
 */
export async function removeOverride(userId: number, permissionKey: string): Promise<void> {
  await api.delete(`${PERMISSIONS_API}/users/${userId}/overrides/${encodeURIComponent(permissionKey)}`);
}

// ============================================================================
// PERMISSION CHECKS
// ============================================================================

/**
 * Check if user has a specific permission
 */
export async function checkPermission(
  userId: number,
  permissionKey: string
): Promise<PermissionCheckResult> {
  const response = await api.get(
    `${PERMISSIONS_API}/users/${userId}/check/${encodeURIComponent(permissionKey)}`
  );
  return response.data;
}

/**
 * Check if user has any of the specified permissions
 */
export async function checkAnyPermission(
  userId: number,
  permissionKeys: string[]
): Promise<PermissionCheckResult> {
  const response = await api.post(`${PERMISSIONS_API}/users/${userId}/check-any`, {
    permissionKeys
  });
  return response.data;
}

/**
 * Check if user has all of the specified permissions
 */
export async function checkAllPermissions(
  userId: number,
  permissionKeys: string[]
): Promise<PermissionCheckResult> {
  const response = await api.post(`${PERMISSIONS_API}/users/${userId}/check-all`, {
    permissionKeys
  });
  return response.data;
}

/**
 * Get all permissions the user currently has
 */
export async function getEffectivePermissions(userId: number): Promise<Record<string, boolean>> {
  const response = await api.get(`${PERMISSIONS_API}/users/${userId}/effective`);
  return response.data.permissions;
}

// ============================================================================
// PERMISSION REQUESTS
// ============================================================================

/**
 * Create a permission request
 */
export async function createPermissionRequest(
  request: {
    requestType: PermissionRequest['requestType'];
    stageCode?: LoanStage;
    permissionKey?: string;
    templateId?: number;
    requestedScope?: DataScope;
    justification: string;
    urgency?: RequestUrgency;
    isTemporary?: boolean;
    durationDays?: number;
  }
): Promise<PermissionRequest> {
  const response = await api.post(`${PERMISSIONS_API}/requests`, request);
  return response.data.request;
}

/**
 * Get permission requests for a user (as requester)
 */
export async function getMyRequests(status?: RequestStatus): Promise<PermissionRequest[]> {
  const params = status ? { status } : {};
  const response = await api.get(`${PERMISSIONS_API}/requests/my`, { params });
  return response.data.requests;
}

/**
 * Get pending requests for review (as manager)
 */
export async function getPendingRequests(): Promise<PermissionRequest[]> {
  const response = await api.get(`${PERMISSIONS_API}/requests/pending`);
  return response.data.requests;
}

/**
 * Approve a permission request
 */
export async function approveRequest(
  requestId: number,
  notes?: string
): Promise<PermissionRequest> {
  const response = await api.post(`${PERMISSIONS_API}/requests/${requestId}/approve`, { notes });
  return response.data.request;
}

/**
 * Deny a permission request
 */
export async function denyRequest(
  requestId: number,
  reason: string
): Promise<PermissionRequest> {
  const response = await api.post(`${PERMISSIONS_API}/requests/${requestId}/deny`, { reason });
  return response.data.request;
}

/**
 * Request more information
 */
export async function requestMoreInfo(
  requestId: number,
  questions: string
): Promise<PermissionRequest> {
  const response = await api.post(`${PERMISSIONS_API}/requests/${requestId}/more-info`, { questions });
  return response.data.request;
}

/**
 * Cancel a pending request
 */
export async function cancelRequest(requestId: number): Promise<void> {
  await api.post(`${PERMISSIONS_API}/requests/${requestId}/cancel`);
}

// ============================================================================
// SUBSCRIPTION MANAGEMENT
// ============================================================================

/**
 * Get available subscription tiers
 */
export async function getSubscriptionTiers(): Promise<SubscriptionTier[]> {
  const response = await api.get(`${SUBSCRIPTIONS_API}/tiers`);
  return response.data.tiers;
}

/**
 * Get current organization's subscription
 */
export async function getCurrentSubscription(): Promise<OrganizationSubscription> {
  const response = await api.get(`${SUBSCRIPTIONS_API}/current`);
  return response.data.subscription;
}

/**
 * Update subscription stages (for custom tier)
 */
export async function updateSubscriptionStages(stages: LoanStage[]): Promise<OrganizationSubscription> {
  const response = await api.patch(`${SUBSCRIPTIONS_API}/current/stages`, { stages });
  return response.data.subscription;
}

// ============================================================================
// AUDIT & HISTORY
// ============================================================================

/**
 * Get permission audit log for a user
 */
export async function getPermissionAuditLog(
  userId: number,
  options: {
    limit?: number;
    offset?: number;
    action?: string;
    startDate?: string;
    endDate?: string;
  } = {}
): Promise<{
  logs: {
    id: number;
    userId: number;
    actorId: number;
    action: string;
    entityType: string;
    entityId: string;
    previousValue: any;
    newValue: any;
    reason: string | null;
    timestamp: string;
  }[];
  total: number;
}> {
  const response = await api.get(`${PERMISSIONS_API}/users/${userId}/audit`, { params: options });
  return response.data;
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Parse a permission key into its components
 */
export function parsePermissionKey(key: string): {
  stage: string | null;
  category: string;
  action: string;
} {
  const parts = key.split('.');
  if (parts.length === 3) {
    return { stage: parts[0], category: parts[1], action: parts[2] };
  } else if (parts.length === 2) {
    return { stage: null, category: parts[0], action: parts[1] };
  }
  return { stage: null, category: 'unknown', action: key };
}

/**
 * Get display name for a stage
 */
export function getStageName(stageCode: LoanStage): string {
  const names: Record<LoanStage, string> = {
    lead: 'Lead Management',
    active_loan: 'Active Loan',
    portfolio: 'Portfolio'
  };
  return names[stageCode] || stageCode;
}

/**
 * Get icon for a stage
 */
export function getStageIcon(stageCode: LoanStage): string {
  const icons: Record<LoanStage, string> = {
    lead: 'UserPlus',
    active_loan: 'FileText',
    portfolio: 'Briefcase'
  };
  return icons[stageCode] || 'Circle';
}

/**
 * Get color for a stage
 */
export function getStageColor(stageCode: LoanStage): string {
  const colors: Record<LoanStage, string> = {
    lead: '#3B82F6',
    active_loan: '#10B981',
    portfolio: '#8B5CF6'
  };
  return colors[stageCode] || '#6B7280';
}

/**
 * Get display name for a data scope
 */
export function getScopeName(scope: DataScope): string {
  const names: Record<DataScope, string> = {
    all: 'All Records',
    team: 'Team Records',
    territory: 'Territory Records',
    branch: 'Branch Records',
    assigned: 'Assigned Records Only',
    none: 'No Access'
  };
  return names[scope] || scope;
}

/**
 * Check if a scope is more permissive than another
 */
export function isScopeMorePermissive(scope1: DataScope, scope2: DataScope): boolean {
  const scopeOrder: DataScope[] = ['none', 'assigned', 'branch', 'territory', 'team', 'all'];
  return scopeOrder.indexOf(scope1) > scopeOrder.indexOf(scope2);
}

// ============================================================================
// EXPORT DEFAULT
// ============================================================================

export default {
  // Stages
  getStages,
  getEnabledStages,
  checkStageAccess,

  // Definitions
  getPermissionDefinitions,
  getGroupedPermissions,
  getStagePermissions,

  // Templates
  getTemplates,
  getStageTemplates,
  getTemplateByCode,
  createTemplate,
  updateTemplate,

  // User Permissions
  getUserPermissionProfile,
  getUserStageAccess,
  grantStageAccess,
  revokeStageAccess,
  applyTemplate,
  updateDataScope,

  // Overrides
  getUserOverrides,
  addOverride,
  removeOverride,

  // Checks
  checkPermission,
  checkAnyPermission,
  checkAllPermissions,
  getEffectivePermissions,

  // Requests
  createPermissionRequest,
  getMyRequests,
  getPendingRequests,
  approveRequest,
  denyRequest,
  requestMoreInfo,
  cancelRequest,

  // Subscriptions
  getSubscriptionTiers,
  getCurrentSubscription,
  updateSubscriptionStages,

  // Audit
  getPermissionAuditLog,

  // Utilities
  parsePermissionKey,
  getStageName,
  getStageIcon,
  getStageColor,
  getScopeName,
  isScopeMorePermissive
};
