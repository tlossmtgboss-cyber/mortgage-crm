/**
 * ReconciliationCenter - Helper Functions
 *
 * Pure utility functions for formatting, cleaning, and display logic.
 */

/**
 * Clean email preview text by removing URLs, images, HTML entities, etc.
 */
export const cleanEmailPreview = (text) => {
  if (!text) return '';

  let cleaned = text
    // Remove URLs (http, https, www)
    .replace(/https?:\/\/[^\s<>"{}|\\^`[\]]+/gi, '')
    .replace(/www\.[^\s<>"{}|\\^`[\]]+/gi, '')
    // Remove image references and file paths
    .replace(/[^\s]+\.(png|jpg|jpeg|gif|svg|webp|ico|pdf)[^\s]*/gi, '')
    // Remove HTML-like encoded characters
    .replace(/&[a-z]+;/gi, ' ')
    .replace(/&#\d+;/gi, ' ')
    // Remove email addresses
    .replace(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g, '')
    // Remove markdown image syntax
    .replace(/!\[.*?\]\(.*?\)/g, '')
    // Remove excessive whitespace, newlines, and special chars
    .replace(/[\r\n\t]+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    // Remove common email cruft
    .replace(/cid:[^\s]+/gi, '')
    .replace(/\[image:.*?\]/gi, '')
    .replace(/\[cid:.*?\]/gi, '')
    // Trim
    .trim();

  // If we cleaned everything away, return a generic message
  if (!cleaned || cleaned.length < 10) {
    return 'Email content (contains images/attachments)';
  }

  return cleaned;
};

/**
 * Get color for confidence score display.
 */
export const getConfidenceColor = (confidence) => {
  if (confidence >= 0.85) return '#2D7A52'; // green
  if (confidence >= 0.65) return '#f59e0b'; // orange
  return '#ef4444'; // red
};

/**
 * Get badge label for confidence score.
 */
export const getConfidenceBadge = (confidence) => {
  if (confidence >= 0.85) return 'HIGH';
  if (confidence >= 0.65) return 'MEDIUM';
  return 'LOW';
};

/**
 * Format a snake_case field name to Title Case.
 */
export const formatFieldName = (fieldName) => {
  return fieldName
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

/**
 * Extract a display name from an email address.
 */
export const extractNameFromEmail = (email) => {
  if (!email) return 'Unknown';
  const namePart = email.split('@')[0];
  return namePart
    .split('.')
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
};

/**
 * Format a field value based on field name (dates, currency, rates).
 */
export const formatFieldValue = (fieldName, value) => {
  if (!value) return 'N/A';

  if (fieldName.includes('date')) {
    try {
      return new Date(value).toLocaleDateString();
    } catch {
      return value;
    }
  }

  if (fieldName === 'loan_amount' || fieldName === 'appraisal_value') {
    return `$${parseFloat(value).toLocaleString()}`;
  }

  if (fieldName === 'rate' || fieldName === 'interest_rate') {
    const numValue = parseFloat(value);
    if (!isNaN(numValue)) {
      if (numValue < 1) {
        return `${(numValue * 100).toFixed(3).replace(/\.?0+$/, '')}%`;
      }
      return `${numValue}%`;
    }
    return `${value}%`;
  }

  return value;
};

/**
 * Format field value for display - handles rate conversion and currency formatting.
 */
export const formatDisplayValue = (fieldName, value) => {
  if (!value && value !== 0) return value;

  // Handle rate/interest_rate - convert decimal to percentage
  if (fieldName === 'rate' || fieldName === 'interest_rate') {
    const numValue = parseFloat(value);
    if (!isNaN(numValue)) {
      if (numValue < 1) {
        return `${(numValue * 100).toFixed(3).replace(/\.?0+$/, '')}%`;
      }
      return `${numValue}%`;
    }
  }

  // Handle loan amounts
  if (fieldName === 'loan_amount' || fieldName === 'appraisal_value' || fieldName === 'purchase_price') {
    const numValue = parseFloat(value);
    if (!isNaN(numValue)) {
      return `$${numValue.toLocaleString()}`;
    }
  }

  return value;
};
