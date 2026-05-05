/**
 * LetterDraftModal Component
 *
 * Modal for generating pre-qualification or pre-approval letters.
 * Allows realtors to specify property details and generate letters.
 */

import React, { useState, useCallback, useEffect } from 'react';
import { useLetterGeneration } from '../../hooks/useRealtorPortal';
import { toast } from '../../utils/toast';

// =============================================================================
// LETTER DRAFT MODAL COMPONENT
// =============================================================================

export default function LetterDraftModal({
  isOpen,
  onClose,
  loanId,
  letterType, // 'prequal' or 'preapproval'
  loan,
}) {
  const { generateLetter, generating, error } = useLetterGeneration(loanId);

  // Form state
  const [propertyAddress, setPropertyAddress] = useState('');
  const [purchasePrice, setPurchasePrice] = useState('');
  const [approvedAmount, setApprovedAmount] = useState('');
  const [formError, setFormError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [generatedLetter, setGeneratedLetter] = useState(null);

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setPropertyAddress('');
      setPurchasePrice('');
      setApprovedAmount(loan?.loan_amount?.toString() || '');
      setFormError(null);
      setSuccess(false);
      setGeneratedLetter(null);
    }
  }, [isOpen, loan]);

  // Handle form submission
  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    setFormError(null);

    // Validate
    if (!approvedAmount) {
      setFormError('Approved amount is required');
      return;
    }

    const amount = parseFloat(approvedAmount.replace(/,/g, ''));
    if (isNaN(amount) || amount <= 0) {
      setFormError('Please enter a valid approved amount');
      return;
    }

    try {
      const result = await generateLetter(letterType, {
        propertyAddress: propertyAddress || undefined,
        purchasePrice: purchasePrice ? parseFloat(purchasePrice.replace(/,/g, '')) : undefined,
        approvedAmount: amount,
      });

      setGeneratedLetter(result);
      setSuccess(true);
    } catch (err) {
      setFormError(err.message || 'Failed to generate letter');
    }
  }, [letterType, propertyAddress, purchasePrice, approvedAmount, generateLetter]);

  // Format currency input
  const formatCurrency = (value) => {
    const num = value.replace(/[^0-9]/g, '');
    if (!num) return '';
    return parseInt(num, 10).toLocaleString();
  };

  // Handle currency input change
  const handleCurrencyChange = (setter) => (e) => {
    setter(formatCurrency(e.target.value));
  };

  if (!isOpen) return null;

  const letterTypeLabel = letterType === 'prequal' ? 'Pre-Qualification' : 'Pre-Approval';

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-2xl shadow-xl max-w-lg w-full mx-auto transform transition-all">
          {/* Header */}
          <div className="px-6 py-4 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-gray-900">
                Generate {letterTypeLabel} Letter
              </h2>
              <button
                onClick={onClose}
                className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p className="text-sm text-gray-500 mt-1">
              For {loan?.borrower_name || 'Borrower'}
            </p>
          </div>

          {/* Content */}
          <div className="px-6 py-5">
            {success ? (
              // Success state
              <div className="text-center py-6">
                <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">
                  Letter Generated Successfully!
                </h3>
                <p className="text-sm text-gray-500 mb-6">
                  {letterTypeLabel} letter version {generatedLetter?.version} has been created.
                </p>

                <div className="space-y-3">
                  <button
                    onClick={() => {
                      const token = localStorage.getItem('realtor_token');
                      const apiUrl = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';
                      const url = `${apiUrl}/api/v1/realtor-portal/letters/${generatedLetter?.letter_id}/pdf`;
                      // Use fetch with Authorization header instead of token in URL
                      fetch(url, {
                        headers: { 'Authorization': `Bearer ${token}` }
                      })
                        .then(res => {
                          if (!res.ok) throw new Error('Download failed');
                          return res.blob();
                        })
                        .then(blob => {
                          const blobUrl = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = blobUrl;
                          a.download = `letter-${generatedLetter?.letter_id}.pdf`;
                          a.click();
                          URL.revokeObjectURL(blobUrl);
                        })
                        .catch(() => toast.error('Failed to download PDF'));
                    }}
                    className="block w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium text-center cursor-pointer"
                  >
                    Download PDF
                  </button>

                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(generatedLetter?.share_url || '');
                      toast.success('Share link copied to clipboard!');
                    }}
                    className="block w-full px-4 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors font-medium"
                  >
                    Copy Share Link
                  </button>

                  <p className="text-xs text-gray-400">
                    Expires: {new Date(generatedLetter?.expires_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
            ) : (
              // Form
              <form onSubmit={handleSubmit} className="space-y-5">
                {/* Property Address (optional) */}
                <div>
                  <label htmlFor="propertyAddress" className="block text-sm font-medium text-gray-700 mb-1">
                    Property Address
                    <span className="text-gray-400 font-normal ml-1">(Optional)</span>
                  </label>
                  <input
                    type="text"
                    id="propertyAddress"
                    value={propertyAddress}
                    onChange={(e) => setPropertyAddress(e.target.value)}
                    placeholder="123 Main St, City, State 12345"
                    className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Leave blank for a general letter without a specific property
                  </p>
                </div>

                {/* Purchase Price (optional) */}
                <div>
                  <label htmlFor="purchasePrice" className="block text-sm font-medium text-gray-700 mb-1">
                    Purchase Price
                    <span className="text-gray-400 font-normal ml-1">(Optional)</span>
                  </label>
                  <div className="relative">
                    <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500">$</span>
                    <input
                      type="text"
                      id="purchasePrice"
                      value={purchasePrice}
                      onChange={handleCurrencyChange(setPurchasePrice)}
                      placeholder="0"
                      className="w-full pl-8 pr-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    />
                  </div>
                </div>

                {/* Approved Amount (required) */}
                <div>
                  <label htmlFor="approvedAmount" className="block text-sm font-medium text-gray-700 mb-1">
                    {letterType === 'prequal' ? 'Pre-Qualification' : 'Pre-Approval'} Amount
                    <span className="text-red-500 ml-0.5">*</span>
                  </label>
                  <div className="relative">
                    <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500">$</span>
                    <input
                      type="text"
                      id="approvedAmount"
                      value={approvedAmount}
                      onChange={handleCurrencyChange(setApprovedAmount)}
                      placeholder="0"
                      required
                      className="w-full pl-8 pr-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    />
                  </div>
                </div>

                {/* Error message */}
                {(formError || error) && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                    <p className="text-sm text-red-600">{formError || error}</p>
                  </div>
                )}

                {/* Info box */}
                <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                  <div className="flex">
                    <svg className="w-5 h-5 text-blue-500 flex-shrink-0 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <div className="text-sm text-blue-700">
                      <p className="font-medium">Letter Information</p>
                      <ul className="mt-1 text-blue-600 list-disc list-inside">
                        <li>Valid for 90 days from generation</li>
                        <li>Includes your loan officer's contact info</li>
                        <li>Can be shared via secure link</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </form>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-4 bg-gray-50 rounded-b-2xl border-t border-gray-200">
            {success ? (
              <button
                onClick={onClose}
                className="w-full px-4 py-2.5 text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors font-medium"
              >
                Close
              </button>
            ) : (
              <div className="flex space-x-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="flex-1 px-4 py-2.5 text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={generating}
                  className={`flex-1 px-4 py-2.5 rounded-lg font-medium transition-colors ${
                    generating
                      ? 'bg-blue-400 cursor-not-allowed'
                      : 'bg-blue-600 hover:bg-blue-700'
                  } text-white`}
                >
                  {generating ? (
                    <span className="flex items-center justify-center">
                      <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Generating...
                    </span>
                  ) : (
                    'Generate Letter'
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
