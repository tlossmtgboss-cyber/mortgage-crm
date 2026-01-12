import React, { useState, useEffect } from 'react';
import { formatCurrency, parseCurrency, handleCurrencyInput } from '../../utils/currencyUtils';

/**
 * Currency Input Component
 * Automatically formats numbers with commas as user types
 *
 * @param {object} props
 * @param {number|string} props.value - The numeric value
 * @param {function} props.onChange - Called with numeric value when changed
 * @param {string} props.placeholder - Placeholder text
 * @param {string} props.className - Additional CSS classes
 * @param {boolean} props.disabled - Whether input is disabled
 * @param {object} props.style - Additional inline styles
 */
const CurrencyInput = ({
  value,
  onChange,
  placeholder = '$0',
  className = '',
  disabled = false,
  style = {},
  ...rest
}) => {
  // Display value (formatted with commas)
  const [displayValue, setDisplayValue] = useState('');

  // Initialize display value when value prop changes
  useEffect(() => {
    if (value !== null && value !== undefined && value !== '') {
      setDisplayValue(formatCurrency(value));
    } else {
      setDisplayValue('');
    }
  }, [value]);

  const handleChange = (e) => {
    const inputValue = e.target.value;
    const { displayValue: newDisplayValue, numericValue } = handleCurrencyInput(inputValue);

    setDisplayValue(newDisplayValue);

    // Call onChange with the numeric value
    if (onChange) {
      onChange(numericValue);
    }
  };

  return (
    <input
      type="text"
      inputMode="decimal"
      value={displayValue}
      onChange={handleChange}
      placeholder={placeholder}
      className={className}
      disabled={disabled}
      style={style}
      {...rest}
    />
  );
};

export default CurrencyInput;
