/**
 * Phone number formatting utilities
 */

/**
 * Format a phone number string as (XXX) XXX-XXXX
 * @param {string} value - The raw input value
 * @returns {string} - Formatted phone number
 */
export const formatPhoneNumber = (value) => {
  if (!value) return '';

  // Remove all non-digits
  const digits = value.replace(/\D/g, '');

  // Limit to 10 digits
  const limitedDigits = digits.slice(0, 10);

  // Format as (XXX) XXX-XXXX
  if (limitedDigits.length === 0) return '';
  if (limitedDigits.length <= 3) return `(${limitedDigits}`;
  if (limitedDigits.length <= 6) return `(${limitedDigits.slice(0, 3)}) ${limitedDigits.slice(3)}`;
  return `(${limitedDigits.slice(0, 3)}) ${limitedDigits.slice(3, 6)}-${limitedDigits.slice(6)}`;
};

/**
 * Get raw digits from a formatted phone number
 * @param {string} value - The formatted phone number
 * @returns {string} - Just the digits
 */
export const getPhoneDigits = (value) => {
  if (!value) return '';
  return value.replace(/\D/g, '');
};

/**
 * Check if a phone number is complete (10 digits)
 * @param {string} value - The phone number (formatted or raw)
 * @returns {boolean}
 */
export const isPhoneComplete = (value) => {
  return getPhoneDigits(value).length === 10;
};

/**
 * Format phone for display (handles already formatted or raw input)
 * @param {string} value - Phone number in any format
 * @returns {string} - Formatted as (XXX) XXX-XXXX
 */
export const formatPhoneForDisplay = (value) => {
  const digits = getPhoneDigits(value);
  if (digits.length !== 10) return value || '';
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
};
