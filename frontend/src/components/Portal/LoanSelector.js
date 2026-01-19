import React, { useState, useRef, useEffect } from 'react';
import { usePortal, PORTAL_MODES } from '../../contexts/PortalContext';

/**
 * LoanSelector Component
 *
 * Dropdown component for switching between loans in the borrower portal.
 * Displays current loan and allows selection from available loans.
 * Groups loans by portal mode (Transaction vs Servicing).
 */
function LoanSelector({ className = '', showModeIndicator = true }) {
  const {
    currentLoan,
    availableLoans,
    hasMultipleLoans,
    switchLoan,
    switching,
    formatAddress,
    formatCurrency,
    getTransactionLoans,
    getServicingLoans,
  } = usePortal();

  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Handle loan selection
  const handleSelectLoan = async (loan) => {
    if (loan.id === currentLoan?.id) {
      setIsOpen(false);
      return;
    }

    try {
      await switchLoan(loan.id, 'user_selection');
      setIsOpen(false);
    } catch (error) {
      console.error('Failed to switch loan:', error);
    }
  };

  // Don't render if no loans or only one loan
  if (!hasMultipleLoans || availableLoans.length <= 1) {
    return null;
  }

  const transactionLoans = getTransactionLoans();
  const servicingLoans = getServicingLoans();

  // Get mode badge color
  const getModeColor = (mode) => {
    return mode === PORTAL_MODES.TRANSACTION
      ? 'bg-blue-100 text-blue-800'
      : 'bg-green-100 text-green-800';
  };

  // Get mode label
  const getModeLabel = (mode) => {
    return mode === PORTAL_MODES.TRANSACTION ? 'In Progress' : 'Active';
  };

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      {/* Dropdown Trigger */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        disabled={switching}
        className="flex items-center justify-between w-full px-4 py-3 bg-white border border-gray-200 rounded-lg shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <div className="flex items-center min-w-0 flex-1">
          {/* Home icon */}
          <svg
            className="w-5 h-5 text-gray-400 mr-3 flex-shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
            />
          </svg>

          {/* Current loan info */}
          <div className="min-w-0 flex-1 text-left">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-900 truncate">
                {currentLoan?.loan_number || 'Select Loan'}
              </span>
              {showModeIndicator && currentLoan && (
                <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getModeColor(currentLoan.portal_mode)}`}>
                  {getModeLabel(currentLoan.portal_mode)}
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500 truncate">
              {currentLoan ? formatAddress(currentLoan) : 'Choose a loan to view'}
            </p>
          </div>
        </div>

        {/* Dropdown arrow / loading spinner */}
        {switching ? (
          <svg
            className="w-5 h-5 ml-2 text-gray-400 animate-spin"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        ) : (
          <svg
            className={`w-5 h-5 ml-2 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 9l-7 7-7-7"
            />
          </svg>
        )}
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute z-50 w-full mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-80 overflow-auto">
          {/* Transaction Loans Section */}
          {transactionLoans.length > 0 && (
            <div>
              <div className="px-4 py-2 bg-blue-50 border-b border-gray-100">
                <span className="text-xs font-semibold text-blue-700 uppercase tracking-wider">
                  In Progress ({transactionLoans.length})
                </span>
              </div>
              {transactionLoans.map((loan) => (
                <LoanOption
                  key={loan.id}
                  loan={loan}
                  isSelected={currentLoan?.id === loan.id}
                  onClick={() => handleSelectLoan(loan)}
                  formatAddress={formatAddress}
                  formatCurrency={formatCurrency}
                />
              ))}
            </div>
          )}

          {/* Servicing Loans Section */}
          {servicingLoans.length > 0 && (
            <div>
              <div className="px-4 py-2 bg-green-50 border-b border-gray-100">
                <span className="text-xs font-semibold text-green-700 uppercase tracking-wider">
                  Active Loans ({servicingLoans.length})
                </span>
              </div>
              {servicingLoans.map((loan) => (
                <LoanOption
                  key={loan.id}
                  loan={loan}
                  isSelected={currentLoan?.id === loan.id}
                  onClick={() => handleSelectLoan(loan)}
                  formatAddress={formatAddress}
                  formatCurrency={formatCurrency}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Individual loan option in the dropdown
 */
function LoanOption({ loan, isSelected, onClick, formatAddress, formatCurrency }) {
  // Get status indicator color
  const getStatusColor = (status) => {
    switch (status) {
      case 'processing':
      case 'underwriting':
        return 'bg-yellow-400';
      case 'closing':
        return 'bg-blue-400';
      case 'closed':
        return 'bg-green-400';
      default:
        return 'bg-gray-400';
    }
  };

  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full px-4 py-3 text-left hover:bg-gray-50 focus:outline-none focus:bg-gray-50 border-b border-gray-100 last:border-b-0 ${
        isSelected ? 'bg-blue-50' : ''
      }`}
    >
      <div className="flex items-start">
        {/* Status indicator */}
        <span
          className={`w-2 h-2 mt-2 mr-3 rounded-full flex-shrink-0 ${getStatusColor(loan.status)}`}
        />

        <div className="min-w-0 flex-1">
          {/* Loan number and amount */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-900">
              {loan.loan_number || `Loan #${loan.id}`}
            </span>
            <span className="text-sm text-gray-600 ml-2">
              {formatCurrency(loan.loan_amount)}
            </span>
          </div>

          {/* Address */}
          <p className="text-xs text-gray-500 truncate mt-0.5">
            {formatAddress(loan)}
          </p>

          {/* Status badge */}
          <div className="flex items-center mt-1">
            <span className="text-xs text-gray-400 capitalize">
              {loan.status}
            </span>
            {isSelected && (
              <span className="ml-2 text-xs text-blue-600 font-medium">
                Currently Viewing
              </span>
            )}
          </div>
        </div>

        {/* Checkmark for selected */}
        {isSelected && (
          <svg
            className="w-5 h-5 text-blue-600 ml-2 flex-shrink-0"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
        )}
      </div>
    </button>
  );
}

export default LoanSelector;
