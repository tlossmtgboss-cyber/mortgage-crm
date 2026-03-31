/**
 * Array Helper Utilities
 *
 * Provides safe array handling to prevent React error #426
 * Use these helpers throughout the application to ensure data is always an array
 */

/**
 * Ensures the input is always an array
 * @param {any} data - Data that should be an array
 * @param {...string} keys - Optional property names to try extracting from object (checked in order)
 * @returns {Array} - Always returns an array
 */
export const ensureArray = (data, ...keys) => {
  // If already an array, return it
  if (Array.isArray(data)) {
    return data;
  }

  // If null or undefined, return empty array
  if (data === null || data === undefined) {
    return [];
  }

  // If explicit keys were provided, try each in order
  if (keys.length > 0 && data && typeof data === 'object') {
    for (const key of keys) {
      if (key && data[key] && Array.isArray(data[key])) {
        return data[key];
      }
    }
  }

  // If it's an object, check for common array wrapper properties
  if (typeof data === 'object') {
    // Check common property names
    const commonProps = ['items', 'data', 'results', 'list', 'rows', 'records'];
    for (const prop of commonProps) {
      if (Array.isArray(data[prop])) {
        return data[prop];
      }
    }

    // If object has numeric keys, convert to array
    const objKeys = Object.keys(data);
    if (objKeys.length > 0 && objKeys.every(key => !isNaN(key))) {
      return Object.values(data);
    }
  }

  // Last resort: wrap in array if it's a valid value
  if (data !== null && data !== undefined) {
    console.warn('ensureArray: Unexpected data type, wrapping in array:', typeof data, data);
    return [data];
  }

  // Return empty array as final fallback
  return [];
};

/**
 * Safely get array length
 * @param {any} data - Data that should be an array
 * @returns {number} - Length of array, or 0 if not an array
 */
export const safeArrayLength = (data) => {
  const arr = ensureArray(data);
  return arr.length;
};

/**
 * Safely filter array
 * @param {any} data - Data that should be an array
 * @param {Function} filterFn - Filter function
 * @returns {Array} - Filtered array
 */
export const safeFilter = (data, filterFn) => {
  const arr = ensureArray(data);
  return arr.filter(filterFn);
};

/**
 * Safely map array
 * @param {any} data - Data that should be an array
 * @param {Function} mapFn - Map function
 * @returns {Array} - Mapped array
 */
export const safeMap = (data, mapFn) => {
  const arr = ensureArray(data);
  return arr.map(mapFn);
};

/**
 * Safely check if array is empty
 * @param {any} data - Data that should be an array
 * @returns {boolean} - True if empty or not an array
 */
export const isEmptyArray = (data) => {
  const arr = ensureArray(data);
  return arr.length === 0;
};

/**
 * Filter out null, undefined, and falsy values from array
 * @param {any} data - Data that should be an array
 * @returns {Array} - Array with falsy values removed
 */
export const compactArray = (data) => {
  const arr = ensureArray(data);
  return arr.filter(item => item != null && item !== false && item !== '');
};

/**
 * Safely get first element of array
 * @param {any} data - Data that should be an array
 * @param {any} defaultValue - Default value if array is empty
 * @returns {any} - First element or default value
 */
export const safeFirst = (data, defaultValue = null) => {
  const arr = ensureArray(data);
  return arr.length > 0 ? arr[0] : defaultValue;
};

/**
 * Safely slice array
 * @param {any} data - Data that should be an array
 * @param {number} start - Start index
 * @param {number} end - End index
 * @returns {Array} - Sliced array
 */
export const safeSlice = (data, start = 0, end = undefined) => {
  const arr = ensureArray(data);
  return arr.slice(start, end);
};

export default {
  ensureArray,
  safeArrayLength,
  safeFilter,
  safeMap,
  isEmptyArray,
  compactArray,
  safeFirst,
  safeSlice
};
