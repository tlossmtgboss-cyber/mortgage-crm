import React from 'react';
import { usePortal, PORTAL_MODES } from '../../contexts/PortalContext';

/**
 * PortalModeIndicator Component
 *
 * Displays the current portal mode (Transaction or Servicing)
 * with appropriate styling and optional loan count information.
 */
function PortalModeIndicator({ showCounts = false, size = 'default' }) {
  const {
    portalMode,
    transactionLoansCount,
    servicingLoansCount,
    isTransactionMode,
    isServicingMode,
  } = usePortal();

  // Size classes
  const sizeClasses = {
    small: 'px-2 py-0.5 text-xs',
    default: 'px-3 py-1 text-sm',
    large: 'px-4 py-1.5 text-base',
  };

  // Mode-specific styles
  const modeStyles = {
    [PORTAL_MODES.TRANSACTION]: {
      bg: 'bg-blue-100',
      text: 'text-blue-800',
      border: 'border-blue-200',
      icon: (
        <svg
          className={`${size === 'small' ? 'w-3 h-3' : 'w-4 h-4'} mr-1.5`}
          style={{ width: size === 'small' ? '12px' : '16px', height: size === 'small' ? '12px' : '16px' }}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      ),
      label: 'Transaction',
      description: 'Loan in progress',
    },
    [PORTAL_MODES.SERVICING]: {
      bg: 'bg-green-100',
      text: 'text-green-800',
      border: 'border-green-200',
      icon: (
        <svg
          className={`${size === 'small' ? 'w-3 h-3' : 'w-4 h-4'} mr-1.5`}
          style={{ width: size === 'small' ? '12px' : '16px', height: size === 'small' ? '12px' : '16px' }}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      ),
      label: 'Servicing',
      description: 'Active loan',
    },
  };

  const currentStyle = modeStyles[portalMode] || modeStyles[PORTAL_MODES.TRANSACTION];

  return (
    <div className="flex items-center gap-2">
      {/* Mode badge */}
      <span
        className={`inline-flex items-center ${sizeClasses[size]} font-medium rounded-full border ${currentStyle.bg} ${currentStyle.text} ${currentStyle.border}`}
      >
        {currentStyle.icon}
        {currentStyle.label}
      </span>

      {/* Optional loan counts */}
      {showCounts && (
        <div className="flex items-center gap-1 text-xs text-gray-500">
          {isTransactionMode ? (
            <>
              <span className="font-medium text-blue-600">{transactionLoansCount}</span>
              <span>in progress</span>
              {servicingLoansCount > 0 && (
                <>
                  <span className="mx-1">|</span>
                  <span className="font-medium text-green-600">{servicingLoansCount}</span>
                  <span>active</span>
                </>
              )}
            </>
          ) : (
            <>
              <span className="font-medium text-green-600">{servicingLoansCount}</span>
              <span>active</span>
              {transactionLoansCount > 0 && (
                <>
                  <span className="mx-1">|</span>
                  <span className="font-medium text-blue-600">{transactionLoansCount}</span>
                  <span>in progress</span>
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Standalone mode badge component (no context required)
 */
export function ModeBadge({ mode, size = 'default', showIcon = true }) {
  const sizeClasses = {
    small: 'px-2 py-0.5 text-xs',
    default: 'px-3 py-1 text-sm',
    large: 'px-4 py-1.5 text-base',
  };

  const isTransaction = mode === PORTAL_MODES.TRANSACTION || mode === 'transaction';

  if (isTransaction) {
    return (
      <span
        className={`inline-flex items-center ${sizeClasses[size]} font-medium rounded-full bg-blue-100 text-blue-800 border border-blue-200`}
      >
        {showIcon && (
          <svg
            className={`${size === 'small' ? 'w-3 h-3' : 'w-4 h-4'} mr-1.5`}
            style={{ width: size === 'small' ? '12px' : '16px', height: size === 'small' ? '12px' : '16px' }}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        )}
        In Progress
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center ${sizeClasses[size]} font-medium rounded-full bg-green-100 text-green-800 border border-green-200`}
    >
      {showIcon && (
        <svg
          className={`${size === 'small' ? 'w-3 h-3' : 'w-4 h-4'} mr-1.5`}
          style={{ width: size === 'small' ? '12px' : '16px', height: size === 'small' ? '12px' : '16px' }}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      )}
      Active
    </span>
  );
}

export default PortalModeIndicator;
