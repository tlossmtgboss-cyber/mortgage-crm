/**
 * DownpaymentInput - Combined amount or percentage input for down payment
 */

import React, { useState, useEffect } from 'react';
import './DownpaymentInput.css';

const DownpaymentInput = ({
  value,
  onChange,
  error,
  helpText,
  disabled = false,
  required = false,
}) => {
  const [inputType, setInputType] = useState('amount'); // 'amount' or 'percent'
  const [amount, setAmount] = useState('');
  const [percent, setPercent] = useState('');

  // Parse incoming value
  useEffect(() => {
    if (value && typeof value === 'object') {
      if (value.amount !== undefined) {
        setAmount(value.amount?.toString() || '');
        setInputType('amount');
      }
      if (value.percent !== undefined) {
        setPercent(value.percent?.toString() || '');
        if (!value.amount) setInputType('percent');
      }
    } else if (value && typeof value === 'string') {
      // Handle string value
      if (value.includes('%')) {
        setPercent(value.replace('%', ''));
        setInputType('percent');
      } else {
        setAmount(value.replace(/[^0-9]/g, ''));
        setInputType('amount');
      }
    }
  }, [value]);

  const formatCurrency = (val) => {
    if (!val) return '';
    const num = parseInt(val.replace(/[^0-9]/g, ''), 10);
    if (isNaN(num)) return '';
    return num.toLocaleString('en-US');
  };

  const handleAmountChange = (e) => {
    const rawVal = e.target.value.replace(/[^0-9]/g, '');
    setAmount(rawVal);
    onChange({
      amount: rawVal ? parseInt(rawVal, 10) : 0,
      percent: null,
      type: 'amount',
    });
  };

  const handlePercentChange = (e) => {
    const rawVal = e.target.value.replace(/[^0-9.]/g, '');
    // Limit to 99%
    const numVal = parseFloat(rawVal);
    if (numVal > 99) return;
    setPercent(rawVal);
    onChange({
      amount: null,
      percent: rawVal ? parseFloat(rawVal) : 0,
      type: 'percent',
    });
  };

  const switchType = (type) => {
    setInputType(type);
    if (type === 'amount') {
      setPercent('');
      onChange({
        amount: amount ? parseInt(amount, 10) : 0,
        percent: null,
        type: 'amount',
      });
    } else {
      setAmount('');
      onChange({
        amount: null,
        percent: percent ? parseFloat(percent) : 0,
        type: 'percent',
      });
    }
  };

  return (
    <div className={`downpayment-input ${error ? 'has-error' : ''}`}>
      <div className="downpayment-toggle">
        <button
          type="button"
          className={`toggle-btn ${inputType === 'amount' ? 'active' : ''}`}
          onClick={() => switchType('amount')}
          disabled={disabled}
        >
          Dollar Amount
        </button>
        <button
          type="button"
          className={`toggle-btn ${inputType === 'percent' ? 'active' : ''}`}
          onClick={() => switchType('percent')}
          disabled={disabled}
        >
          Percentage
        </button>
      </div>

      <div className="downpayment-field">
        {inputType === 'amount' ? (
          <div className="input-with-prefix">
            <span className="input-prefix">$</span>
            <input
              type="text"
              value={formatCurrency(amount)}
              onChange={handleAmountChange}
              placeholder="0"
              disabled={disabled}
              className="downpayment-input-field"
              inputMode="numeric"
            />
          </div>
        ) : (
          <div className="input-with-suffix">
            <input
              type="text"
              value={percent}
              onChange={handlePercentChange}
              placeholder="20"
              disabled={disabled}
              className="downpayment-input-field"
              inputMode="decimal"
            />
            <span className="input-suffix">%</span>
          </div>
        )}
      </div>

      {helpText && <p className="help-text">{helpText}</p>}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
};

export default DownpaymentInput;
