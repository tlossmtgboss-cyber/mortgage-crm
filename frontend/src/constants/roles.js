/**
 * Permission Roles — Single source of truth for the frontend.
 * Mirrors backend/utils/roles.py
 */

export const ROLES = {
  admin: { label: 'Admin', className: 'role-admin' },
  site_admin: { label: 'Site Admin', className: 'role-site-admin' },
  leadership: { label: 'Leadership', className: 'role-leadership' },
  management: { label: 'Management', className: 'role-management' },
  sales: { label: 'Sales', className: 'role-sales' },
  processing: { label: 'Processing', className: 'role-processing' },
  operations: { label: 'Operations', className: 'role-operations' },
};

export const PASSWORD_REQUIREMENTS = {
  minLength: 8,
  requireUppercase: true,
  requireLowercase: true,
  requireDigit: true,
};
