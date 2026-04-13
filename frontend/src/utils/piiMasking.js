/**
 * PII Masking Utility
 *
 * Provides field-type-aware masking for sensitive mortgage data.
 * Designed to work alongside the DLP service (dataLossProtection.js)
 * for display-layer PII protection.
 *
 * Usage:
 *   import { maskSSN, maskDOB, formatMasked } from '../utils/piiMasking';
 *   maskSSN('123456789')       // "***-**-6789"
 *   formatMasked('123456789', 'ssn')  // "***-**-6789"
 */

const EMPTY = '\u2014'; // em dash

// =============================================================================
// INDIVIDUAL MASK FUNCTIONS
// =============================================================================

/**
 * Mask a Social Security Number, showing only the last 4 digits.
 * Accepts raw digits ("123456789") or formatted ("123-45-6789").
 * @param {string|number|null|undefined} value
 * @returns {string} e.g. "***-**-6789"
 */
export function maskSSN(value) {
  if (value == null || value === '') return EMPTY;

  const digits = String(value).replace(/\D/g, '');
  if (digits.length === 0) return EMPTY;

  if (digits.length < 4) {
    // Partial SSN — mask everything
    return '*'.repeat(digits.length);
  }

  const last4 = digits.slice(-4);
  return `***-**-${last4}`;
}

/**
 * Mask a date of birth, showing only the year.
 * Accepts ISO ("1990-03-15"), US format ("03/15/1990"), or Date objects.
 * @param {string|Date|null|undefined} value
 * @returns {string} e.g. "**/**/1990"
 */
export function maskDOB(value) {
  if (value == null || value === '') return EMPTY;

  let year = null;

  if (value instanceof Date) {
    if (isNaN(value.getTime())) return EMPTY;
    year = value.getFullYear();
  } else {
    const str = String(value).trim();
    if (str.length === 0) return EMPTY;

    // ISO format: YYYY-MM-DD
    const isoMatch = str.match(/^(\d{4})-\d{2}-\d{2}/);
    if (isoMatch) {
      year = isoMatch[1];
    } else {
      // US format: MM/DD/YYYY or MM-DD-YYYY
      const usMatch = str.match(/\d{1,2}[/\-]\d{1,2}[/\-](\d{4})/);
      if (usMatch) {
        year = usMatch[1];
      } else {
        // Try to extract any 4-digit year
        const yearMatch = str.match(/(\d{4})/);
        if (yearMatch) {
          year = yearMatch[1];
        }
      }
    }
  }

  if (!year) return EMPTY;
  return `**/**/` + year;
}

/**
 * Mask an income value, showing an approximate range instead of the exact amount.
 * @param {string|number|null|undefined} value
 * @returns {string} e.g. "$50k-$75k"
 */
export function maskIncome(value) {
  if (value == null || value === '') return EMPTY;

  // Parse to number, stripping currency symbols and commas
  const num = typeof value === 'number'
    ? value
    : parseFloat(String(value).replace(/[$,\s]/g, ''));

  if (isNaN(num) || num < 0) return EMPTY;

  // Define range buckets
  const ranges = [
    [0, 25000, 'Under $25k'],
    [25000, 50000, '$25k-$50k'],
    [50000, 75000, '$50k-$75k'],
    [75000, 100000, '$75k-$100k'],
    [100000, 150000, '$100k-$150k'],
    [150000, 200000, '$150k-$200k'],
    [200000, 300000, '$200k-$300k'],
    [300000, 500000, '$300k-$500k'],
    [500000, 750000, '$500k-$750k'],
    [750000, 1000000, '$750k-$1M'],
    [1000000, Infinity, '$1M+'],
  ];

  for (const [min, max, label] of ranges) {
    if (num >= min && num < max) {
      return label;
    }
  }

  return EMPTY;
}

/**
 * Mask a phone number, showing only the last 4 digits.
 * @param {string|number|null|undefined} value
 * @returns {string} e.g. "(***) ***-1234"
 */
export function maskPhone(value) {
  if (value == null || value === '') return EMPTY;

  const digits = String(value).replace(/\D/g, '');
  if (digits.length === 0) return EMPTY;

  if (digits.length < 4) {
    return '*'.repeat(digits.length);
  }

  const last4 = digits.slice(-4);
  return `(***) ***-${last4}`;
}

/**
 * Mask an email address, showing only the first character and the domain.
 * @param {string|null|undefined} value
 * @returns {string} e.g. "t***@gmail.com"
 */
export function maskEmail(value) {
  if (value == null || value === '') return EMPTY;

  const str = String(value).trim();
  const atIndex = str.indexOf('@');

  if (atIndex <= 0) return EMPTY;

  const firstChar = str[0];
  const domain = str.slice(atIndex);
  return `${firstChar}***${domain}`;
}

/**
 * Mask an account number (bank account, routing number, etc.),
 * showing only the last 4 digits.
 * @param {string|number|null|undefined} value
 * @returns {string} e.g. "****1234"
 */
export function maskAccountNumber(value) {
  if (value == null || value === '') return EMPTY;

  const str = String(value).replace(/\s/g, '');
  if (str.length === 0) return EMPTY;

  if (str.length <= 4) {
    return '*'.repeat(str.length);
  }

  const last4 = str.slice(-4);
  return '****' + last4;
}

// =============================================================================
// DISPATCHER
// =============================================================================

const MASK_FUNCTIONS = {
  ssn: maskSSN,
  dob: maskDOB,
  income: maskIncome,
  phone: maskPhone,
  email: maskEmail,
  account: maskAccountNumber,
};

/**
 * Dispatch to the correct mask function based on field type.
 * @param {*} value - The raw value to mask
 * @param {string} type - One of: ssn, dob, income, phone, email, account
 * @returns {string} The masked representation
 */
export function formatMasked(value, type) {
  if (!type) return EMPTY;

  const maskFn = MASK_FUNCTIONS[type.toLowerCase()];
  if (!maskFn) {
    // Unknown type — return the value as-is (caller should handle)
    return value != null ? String(value) : EMPTY;
  }

  return maskFn(value);
}

export default {
  maskSSN,
  maskDOB,
  maskIncome,
  maskPhone,
  maskEmail,
  maskAccountNumber,
  formatMasked,
};
