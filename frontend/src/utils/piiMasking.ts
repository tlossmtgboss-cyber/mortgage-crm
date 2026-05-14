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

const EMPTY = '—'; // em dash

export type MaskFieldType = 'ssn' | 'dob' | 'income' | 'phone' | 'email' | 'account';

type MaskableValue = string | number | Date | null | undefined;

// =============================================================================
// INDIVIDUAL MASK FUNCTIONS
// =============================================================================

/**
 * Mask a Social Security Number, showing only the last 4 digits.
 * Accepts raw digits ("123456789") or formatted ("123-45-6789").
 */
export function maskSSN(value: string | number | null | undefined): string {
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
 */
export function maskDOB(value: string | Date | null | undefined): string {
  if (value == null || value === '') return EMPTY;

  let year: string | number | null = null;

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
 */
export function maskIncome(value: string | number | null | undefined): string {
  if (value == null || value === '') return EMPTY;

  // Parse to number, stripping currency symbols and commas
  const num = typeof value === 'number'
    ? value
    : parseFloat(String(value).replace(/[$,\s]/g, ''));

  if (isNaN(num) || num < 0) return EMPTY;

  // Define range buckets
  const ranges: [number, number, string][] = [
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
 */
export function maskPhone(value: string | number | null | undefined): string {
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
 */
export function maskEmail(value: string | null | undefined): string {
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
 */
export function maskAccountNumber(value: string | number | null | undefined): string {
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

const MASK_FUNCTIONS: Record<MaskFieldType, (value: MaskableValue) => string> = {
  ssn: maskSSN as (value: MaskableValue) => string,
  dob: maskDOB as (value: MaskableValue) => string,
  income: maskIncome as (value: MaskableValue) => string,
  phone: maskPhone as (value: MaskableValue) => string,
  email: maskEmail as (value: MaskableValue) => string,
  account: maskAccountNumber as (value: MaskableValue) => string,
};

/**
 * Dispatch to the correct mask function based on field type.
 */
export function formatMasked(value: MaskableValue, type: string): string {
  if (!type) return EMPTY;

  const maskFn = MASK_FUNCTIONS[type.toLowerCase() as MaskFieldType];
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
