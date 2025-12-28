import React from 'react';
import { usePermissions } from '../contexts/PermissionContext';
import './PermissionGate.css';

/**
 * PermissionGate - A component for conditional rendering based on permissions
 *
 * Usage examples:
 *
 * 1. Basic permission check:
 *    <PermissionGate permission="leads.create">
 *      <button>Create Lead</button>
 *    </PermissionGate>
 *
 * 2. Write operation (also checks read-only mode):
 *    <PermissionGate permission="leads.create" isWriteOperation>
 *      <button>Create Lead</button>
 *    </PermissionGate>
 *
 * 3. Any of multiple permissions:
 *    <PermissionGate anyOf={['leads.edit_all', 'leads.edit_own']}>
 *      <button>Edit Lead</button>
 *    </PermissionGate>
 *
 * 4. All of multiple permissions:
 *    <PermissionGate allOf={['leads.view_all', 'leads.edit_all']}>
 *      <button>Admin Action</button>
 *    </PermissionGate>
 *
 * 5. Show disabled state instead of hiding:
 *    <PermissionGate permission="leads.delete" showDisabled>
 *      <button>Delete Lead</button>
 *    </PermissionGate>
 *
 * 6. Custom fallback:
 *    <PermissionGate permission="leads.create" fallback={<span>No access</span>}>
 *      <button>Create Lead</button>
 *    </PermissionGate>
 */

const PermissionGate = ({
  children,
  permission,
  anyOf,
  allOf,
  isWriteOperation = false,
  showDisabled = false,
  fallback = null,
  disabledTooltip = 'You do not have permission to perform this action',
  readOnlyTooltip = 'Read-only mode - editing is disabled'
}) => {
  const { hasPermission, hasAnyPermission, hasAllPermissions, isReadOnlyMode, canPerformAction } = usePermissions();

  // Determine if user has the required permission(s)
  let hasAccess = true;

  if (permission) {
    hasAccess = isWriteOperation
      ? canPerformAction(permission, true)
      : hasPermission(permission);
  } else if (anyOf && anyOf.length > 0) {
    hasAccess = hasAnyPermission(anyOf);
    // For write operations, also check read-only mode
    if (hasAccess && isWriteOperation && isReadOnlyMode()) {
      hasAccess = false;
    }
  } else if (allOf && allOf.length > 0) {
    hasAccess = hasAllPermissions(allOf);
    // For write operations, also check read-only mode
    if (hasAccess && isWriteOperation && isReadOnlyMode()) {
      hasAccess = false;
    }
  }

  // Determine the reason for denial (for tooltip)
  const isBlockedByReadOnly = isWriteOperation && isReadOnlyMode();
  const tooltipText = isBlockedByReadOnly ? readOnlyTooltip : disabledTooltip;

  // If user has access, render children normally
  if (hasAccess) {
    return <>{children}</>;
  }

  // If showDisabled, render children with disabled styling
  if (showDisabled) {
    return (
      <div
        className="permission-gate-disabled"
        title={tooltipText}
        aria-disabled="true"
      >
        {React.Children.map(children, child => {
          if (React.isValidElement(child)) {
            return React.cloneElement(child, {
              disabled: true,
              onClick: (e) => e.preventDefault(),
              className: `${child.props.className || ''} permission-disabled`.trim()
            });
          }
          return child;
        })}
      </div>
    );
  }

  // Otherwise, render fallback (or nothing)
  return fallback;
};

/**
 * ReadOnlyGate - Specialized gate for write operations in read-only mode
 * Shows children but disables them with a visual indicator when in read-only impersonation
 */
export const ReadOnlyGate = ({ children, showWhenReadOnly = false }) => {
  const { isReadOnlyMode } = usePermissions();

  const readOnly = isReadOnlyMode();

  if (readOnly && !showWhenReadOnly) {
    return (
      <div
        className="permission-gate-readonly"
        title="Read-only mode - editing is disabled"
      >
        {React.Children.map(children, child => {
          if (React.isValidElement(child)) {
            return React.cloneElement(child, {
              disabled: true,
              onClick: (e) => e.preventDefault(),
              className: `${child.props.className || ''} readonly-disabled`.trim()
            });
          }
          return child;
        })}
      </div>
    );
  }

  return <>{children}</>;
};

/**
 * useCanPerform - Hook version for programmatic access checks
 *
 * Usage:
 *   const canCreateLead = useCanPerform('leads.create', true);
 *   if (canCreateLead) { ... }
 */
export const useCanPerform = (permission, isWriteOperation = false) => {
  const { canPerformAction, hasPermission } = usePermissions();
  return isWriteOperation ? canPerformAction(permission, true) : hasPermission(permission);
};

export default PermissionGate;
