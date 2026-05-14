/**
 * Currency formatting utilities
 * Handles formatting numbers with commas and parsing formatted values
 */

/**
 * Format a number with commas for display
 */
export const formatCurrency = (value: number | string | null | undefined): string => {
  if (value === null || value === undefined || value === '') {
    return '';
  }

  // Convert to string and remove any existing formatting
  const numStr = String(value).replace(/[^0-9.-]/g, '');

  if (numStr === '' || numStr === '-') {
    return numStr;
  }

  // Parse the number
  const num = parseFloat(numStr);

  if (isNaN(num)) {
    return '';
  }

  // Format with commas
  return num.toLocaleString('en-US', {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0
  });
};

/**
 * Format a number as currency with dollar sign
 */
export const formatDollarAmount = (value: number | string | null | undefined): string => {
  const formatted = formatCurrency(value);
  if (formatted === '' || formatted === '-') {
    return formatted;
  }
  return `$${formatted}`;
};

/**
 * Parse a formatted currency string back to a number
 */
export const parseCurrency = (value: string | number | null | undefined): number | null => {
  if (value === null || value === undefined || value === '') {
    return null;
  }

  // Remove currency symbol, commas, and spaces
  const cleaned = String(value).replace(/[$,\s]/g, '');

  if (cleaned === '' || cleaned === '-') {
    return null;
  }

  const num = parseFloat(cleaned);

  return isNaN(num) ? null : num;
};

export interface CurrencyInputResult {
  displayValue: string;
  numericValue: number | null;
}

/**
 * Handle currency input change - formats as user types
 */
export const handleCurrencyInput = (
  inputValue: string | null | undefined,
  _previousValue: string = ''
): CurrencyInputResult => {
  // Allow empty value
  if (inputValue === '' || inputValue === null || inputValue === undefined) {
    return { displayValue: '', numericValue: null };
  }

  // Remove all non-numeric characters except decimal point and minus
  let cleaned = inputValue.replace(/[^0-9.-]/g, '');

  // Handle multiple decimal points - keep only the first one
  const parts = cleaned.split('.');
  if (parts.length > 2) {
    cleaned = parts[0] + '.' + parts.slice(1).join('');
  }

  // Limit decimal places to 2
  if (parts.length === 2 && parts[1].length > 2) {
    cleaned = parts[0] + '.' + parts[1].slice(0, 2);
  }

  // Parse to number
  const numericValue = cleaned === '' || cleaned === '-' || cleaned === '.'
    ? null
    : parseFloat(cleaned);

  // Format for display
  if (cleaned === '' || cleaned === '-' || cleaned === '.') {
    return { displayValue: cleaned, numericValue: null };
  }

  // If user is typing decimal places, preserve them
  if (cleaned.includes('.')) {
    const [whole, decimal] = cleaned.split('.');
    const formattedWhole = parseInt(whole || '0', 10).toLocaleString('en-US');
    return {
      displayValue: `${formattedWhole}.${decimal}`,
      numericValue: numericValue
    };
  }

  // Format whole number with commas
  const num = parseInt(cleaned, 10);
  if (isNaN(num)) {
    return { displayValue: '', numericValue: null };
  }

  return {
    displayValue: num.toLocaleString('en-US'),
    numericValue: num
  };
};

export default {
  formatCurrency,
  formatDollarAmount,
  parseCurrency,
  handleCurrencyInput
};
