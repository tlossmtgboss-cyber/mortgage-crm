/**
 * PreApprovalLetterModal Component
 *
 * Multi-step modal for generating pre-approval letters with:
 * - Property address option
 * - Purchase price with LTV calculation
 * - Over-limit warning and LO notification
 * - Letter preview and download/email
 */

import React, { useState, useEffect } from 'react';
import { sanitizeHTML } from '../utils/sanitize';
import './PreApprovalLetterModal.css';
import api from '../services/api';
import { getToken } from '../utils/tokenStore';

// Steps in the modal flow
const STEPS = {
  OPTIONS: 'options',
  OVER_LIMIT: 'over_limit',
  GENERATING: 'generating',
  PREVIEW: 'preview',
  SUCCESS: 'success',
  ERROR: 'error'
};

const PreApprovalLetterModal = ({
  isOpen,
  onClose,
  clientData,
  partnerId,
  onLetterGenerated
}) => {
  const [step, setStep] = useState(STEPS.OPTIONS);
  const [includePropertyAddress, setIncludePropertyAddress] = useState(false);
  const [propertyAddress, setPropertyAddress] = useState('');
  const [includePurchasePrice, setIncludePurchasePrice] = useState(false);
  const [purchasePrice, setPurchasePrice] = useState('');
  const [calculatedLoanAmount, setCalculatedLoanAmount] = useState(null);
  const [isOverLimit, setIsOverLimit] = useState(false);
  const [letterData, setLetterData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [emailSending, setEmailSending] = useState(false);
  const [emailSent, setEmailSent] = useState(false);

  // Get loan details from client data
  const client = clientData?.client || {};
  const maxLoanAmount = client.loan_amount || 0;
  const ltvRatio = client.ltv_ratio || 80; // Default to 80% LTV
  const downPaymentPercent = 100 - ltvRatio;

  // Calculate max purchase price based on loan amount and LTV
  const maxPurchasePrice = maxLoanAmount > 0 ? maxLoanAmount / (ltvRatio / 100) : 0;

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setStep(STEPS.OPTIONS);
      setIncludePropertyAddress(false);
      setPropertyAddress(client.property_address || '');
      setIncludePurchasePrice(false);
      setPurchasePrice('');
      setCalculatedLoanAmount(null);
      setIsOverLimit(false);
      setLetterData(null);
      setError(null);
      setEmailSent(false);
    }
  }, [isOpen, client.property_address]);

  // Calculate loan amount when purchase price changes
  useEffect(() => {
    if (purchasePrice && includePurchasePrice) {
      const priceNum = parseFloat(purchasePrice.replace(/[,$]/g, ''));
      if (!isNaN(priceNum) && priceNum > 0) {
        const calculated = priceNum * (ltvRatio / 100);
        setCalculatedLoanAmount(calculated);
        setIsOverLimit(priceNum > maxPurchasePrice);
      } else {
        setCalculatedLoanAmount(null);
        setIsOverLimit(false);
      }
    } else {
      setCalculatedLoanAmount(null);
      setIsOverLimit(false);
    }
  }, [purchasePrice, includePurchasePrice, ltvRatio, maxPurchasePrice]);

  const formatCurrency = (amount) => {
    if (!amount) return '$0';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  const handlePurchasePriceChange = (e) => {
    const value = e.target.value.replace(/[^0-9.]/g, '');
    setPurchasePrice(value);
  };

  const handleProceedOverLimit = async () => {
    // Notify LO about over-limit request
    try {
      await notifyLoanOfficer();
    } catch (err) {
      console.error('Error notifying LO:', err);
    }
    // Show message and close
    setStep(STEPS.OVER_LIMIT);
  };

  // Helper: get auth token (supports partner portal fallback)
  const getAuthToken = () => getToken() || localStorage.getItem('partnerToken');

  const notifyLoanOfficer = async () => {
    const priceNum = parseFloat(purchasePrice.replace(/[,$]/g, ''));

    try {
      await api.post('/api/v1/realtor-portal/preapproval/notify-overlimit', {
        lead_id: client.id,
        partner_id: partnerId,
        requested_purchase_price: priceNum,
        max_approved_amount: maxLoanAmount,
        max_purchase_price: maxPurchasePrice,
        borrower_name: client.borrower_name || client.name
      }, {
        headers: { 'Authorization': `Bearer ${getAuthToken()}` }
      });
    } catch (err) {
      console.error('Error notifying LO:', err);
    }
  };

  const handleGenerateLetter = async () => {
    setStep(STEPS.GENERATING);
    setLoading(true);
    setError(null);

    const priceNum = includePurchasePrice ? parseFloat(purchasePrice.replace(/[,$]/g, '')) : null;
    const finalLoanAmount = calculatedLoanAmount || maxLoanAmount;

    try {
      const { data } = await api.post(`/api/v1/realtor-portal/leads/${client.id}/generate-preapproval`, {
        include_property_address: includePropertyAddress,
        property_address: includePropertyAddress ? propertyAddress : null,
        include_purchase_price: includePurchasePrice,
        purchase_price: priceNum,
        calculated_loan_amount: finalLoanAmount,
        partner_id: partnerId
      }, {
        headers: { 'Authorization': `Bearer ${getAuthToken()}` }
      });

      if (data.success) {
        setLetterData(data);
        setStep(STEPS.PREVIEW);
        if (onLetterGenerated) {
          onLetterGenerated(data);
        }
      } else {
        setError(data.error || 'Failed to generate letter');
        setStep(STEPS.ERROR);
      }
    } catch (err) {
      console.error('Error generating letter:', err);
      setError('An error occurred while generating the letter. Please try again.');
      setStep(STEPS.ERROR);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPDF = async () => {
    if (!letterData?.letter_id) return;

    try {
      const response = await api.get(`/api/v1/realtor-portal/letters/${letterData.letter_id}/pdf`, {
        responseType: 'blob',
        headers: { 'Authorization': `Bearer ${getAuthToken()}` }
      });

      const blob = response.data;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `PreApproval_${client.borrower_name || client.name}_${new Date().toISOString().split('T')[0]}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Error downloading PDF:', err);
    }
  };

  const handleSendEmail = async () => {
    if (!letterData?.letter_id) return;

    setEmailSending(true);

    try {
      const { data } = await api.post(`/api/v1/realtor-portal/letters/${letterData.letter_id}/email`, {}, {
        headers: { 'Authorization': `Bearer ${getAuthToken()}` }
      });
      if (data.success) {
        setEmailSent(true);
      }
    } catch (err) {
      console.error('Error sending email:', err);
    } finally {
      setEmailSending(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="preapproval-modal-overlay" onClick={onClose}>
      <div className="preapproval-modal" onClick={e => e.stopPropagation()}>
        <button className="modal-close-btn" onClick={onClose}>
          &times;
        </button>

        {/* Step: Options */}
        {step === STEPS.OPTIONS && (
          <div className="modal-step options-step">
            <div className="modal-header">
              <h2>Generate Pre-Approval Letter</h2>
              <p className="modal-subtitle">
                Customize the pre-approval letter for {client.borrower_name || client.name}
              </p>
            </div>

            <div className="approval-summary">
              <div className="summary-item">
                <span className="label">Approved Amount</span>
                <span className="value">{formatCurrency(maxLoanAmount)}</span>
              </div>
              <div className="summary-item">
                <span className="label">LTV Ratio</span>
                <span className="value">{ltvRatio}%</span>
              </div>
              <div className="summary-item">
                <span className="label">Max Purchase Price</span>
                <span className="value">{formatCurrency(maxPurchasePrice)}</span>
              </div>
            </div>

            <div className="option-group">
              <label className="option-checkbox">
                <input
                  type="checkbox"
                  checked={includePropertyAddress}
                  onChange={(e) => setIncludePropertyAddress(e.target.checked)}
                />
                <span className="checkbox-label">
                  <strong>Include Property Address</strong>
                  <small>Add a specific property address to the letter</small>
                </span>
              </label>

              {includePropertyAddress && (
                <div className="option-input">
                  <input
                    type="text"
                    value={propertyAddress}
                    onChange={(e) => setPropertyAddress(e.target.value)}
                    placeholder="123 Main Street, City, State ZIP"
                    className="text-input"
                  />
                </div>
              )}
            </div>

            <div className="option-group">
              <label className="option-checkbox">
                <input
                  type="checkbox"
                  checked={includePurchasePrice}
                  onChange={(e) => setIncludePurchasePrice(e.target.checked)}
                />
                <span className="checkbox-label">
                  <strong>Include Purchase Price</strong>
                  <small>Specify an offer amount (loan calculated at same LTV)</small>
                </span>
              </label>

              {includePurchasePrice && (
                <div className="option-input">
                  <div className="currency-input-wrapper">
                    <span className="currency-symbol">$</span>
                    <input
                      type="text"
                      value={purchasePrice}
                      onChange={handlePurchasePriceChange}
                      placeholder="400,000"
                      className="currency-input"
                    />
                  </div>

                  {calculatedLoanAmount && (
                    <div className={`calculation-result ${isOverLimit ? 'over-limit' : ''}`}>
                      <div className="calc-row">
                        <span>Loan Amount ({ltvRatio}% LTV):</span>
                        <span className="calc-value">{formatCurrency(calculatedLoanAmount)}</span>
                      </div>
                      <div className="calc-row">
                        <span>Down Payment ({downPaymentPercent}%):</span>
                        <span className="calc-value">
                          {formatCurrency(parseFloat(purchasePrice.replace(/[,$]/g, '')) - calculatedLoanAmount)}
                        </span>
                      </div>
                      {isOverLimit && (
                        <div className="over-limit-warning">
                          <span className="warning-icon">&#9888;</span>
                          <span>Exceeds pre-approved terms ({formatCurrency(maxPurchasePrice)} max)</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="modal-actions">
              <button className="btn-secondary" onClick={onClose}>
                Cancel
              </button>
              {isOverLimit ? (
                <button className="btn-warning" onClick={handleProceedOverLimit}>
                  Request Higher Amount
                </button>
              ) : (
                <button className="btn-primary" onClick={handleGenerateLetter}>
                  Generate Letter
                </button>
              )}
            </div>
          </div>
        )}

        {/* Step: Over Limit */}
        {step === STEPS.OVER_LIMIT && (
          <div className="modal-step over-limit-step">
            <div className="status-icon warning">&#9888;</div>
            <h2>Amount Exceeds Pre-Approval</h2>
            <p>
              The requested purchase price of {formatCurrency(parseFloat(purchasePrice.replace(/[,$]/g, '')))} exceeds
              the current pre-approved terms (max {formatCurrency(maxPurchasePrice)}).
            </p>
            <p className="notification-sent">
              Your loan officer has been notified and will contact you to discuss options for a higher approval amount.
            </p>
            <div className="modal-actions centered">
              <button className="btn-primary" onClick={onClose}>
                Got It
              </button>
            </div>
          </div>
        )}

        {/* Step: Generating */}
        {step === STEPS.GENERATING && (
          <div className="modal-step generating-step">
            <div className="loading-animation">
              <div className="spinner" />
            </div>
            <h2>Generating Your Letter</h2>
            <p>Please wait while we prepare the pre-approval letter...</p>
          </div>
        )}

        {/* Step: Preview */}
        {step === STEPS.PREVIEW && letterData && (
          <div className="modal-step preview-step">
            <div className="modal-header">
              <div className="status-icon success">&#10003;</div>
              <h2>Letter Generated Successfully</h2>
              <p className="modal-subtitle">
                Your pre-approval letter is ready for {client.borrower_name || client.name}
              </p>
            </div>

            <div className="letter-summary">
              <div className="summary-row">
                <span className="label">Loan Amount:</span>
                <span className="value">{formatCurrency(letterData.calculated_loan_amount || maxLoanAmount)}</span>
              </div>
              {letterData.property_address && (
                <div className="summary-row">
                  <span className="label">Property:</span>
                  <span className="value">{letterData.property_address}</span>
                </div>
              )}
              {letterData.purchase_price && (
                <div className="summary-row">
                  <span className="label">Purchase Price:</span>
                  <span className="value">{formatCurrency(letterData.purchase_price)}</span>
                </div>
              )}
              <div className="summary-row">
                <span className="label">Expires:</span>
                <span className="value">{letterData.expires_at ? new Date(letterData.expires_at).toLocaleDateString() : '90 days'}</span>
              </div>
            </div>

            {letterData.letter_html && (
              <div className="letter-preview-container">
                <h4>Letter Preview</h4>
                <div
                  className="letter-preview"
                  dangerouslySetInnerHTML={{ __html: sanitizeHTML(letterData.letter_html, { allowedTags: ['p', 'br', 'strong', 'em', 'b', 'i', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'span', 'div', 'table', 'tr', 'td', 'th', 'thead', 'tbody', 'hr', 'img'] }) }}
                />
              </div>
            )}

            <div className="modal-actions">
              <button className="btn-secondary" onClick={handleDownloadPDF}>
                <span className="btn-icon">&#8595;</span>
                Download PDF
              </button>
              <button
                className={`btn-primary ${emailSent ? 'sent' : ''}`}
                onClick={handleSendEmail}
                disabled={emailSending || emailSent}
              >
                {emailSending ? (
                  <span>Sending...</span>
                ) : emailSent ? (
                  <span>&#10003; Email Sent</span>
                ) : (
                  <span>
                    <span className="btn-icon">&#9993;</span>
                    Send via Email
                  </span>
                )}
              </button>
            </div>

            <div className="modal-footer-actions">
              <button className="btn-text" onClick={onClose}>
                Close
              </button>
            </div>
          </div>
        )}

        {/* Step: Error */}
        {step === STEPS.ERROR && (
          <div className="modal-step error-step">
            <div className="status-icon error">&#10007;</div>
            <h2>Unable to Generate Letter</h2>
            <p className="error-message">{error}</p>
            <div className="modal-actions centered">
              <button className="btn-secondary" onClick={onClose}>
                Close
              </button>
              <button className="btn-primary" onClick={() => setStep(STEPS.OPTIONS)}>
                Try Again
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default PreApprovalLetterModal;
