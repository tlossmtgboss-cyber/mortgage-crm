/**
 * Accessibility utilities for Perennia AI mobile app.
 *
 * Provides screen reader announcements, focus management, and
 * formatters that produce human-readable text for VoiceOver / TalkBack.
 *
 * ADA / WCAG 2.1 AA compliance is a legal requirement for financial services.
 */

// ---------------------------------------------------------------------------
// Live region announcer
// ---------------------------------------------------------------------------

let _liveRegion = null;

/**
 * Get or create the shared aria-live region element.
 * Uses aria-live="assertive" so announcements interrupt ongoing speech,
 * which is appropriate for dynamic state changes in a mobile CRM.
 */
function _ensureLiveRegion() {
  if (_liveRegion && document.body.contains(_liveRegion)) {
    return _liveRegion;
  }

  _liveRegion = document.createElement('div');
  _liveRegion.setAttribute('role', 'status');
  _liveRegion.setAttribute('aria-live', 'assertive');
  _liveRegion.setAttribute('aria-atomic', 'true');

  // Visually hidden but accessible to screen readers
  Object.assign(_liveRegion.style, {
    position: 'absolute',
    width: '1px',
    height: '1px',
    padding: '0',
    margin: '-1px',
    overflow: 'hidden',
    clip: 'rect(0, 0, 0, 0)',
    whiteSpace: 'nowrap',
    border: '0',
  });

  _liveRegion.id = 'perennia-a11y-live';
  document.body.appendChild(_liveRegion);
  return _liveRegion;
}

/**
 * Announce a message to screen readers via an aria-live region.
 *
 * The message is cleared after a brief delay and then set, which forces
 * assistive technology to re-announce even if the text is identical to a
 * prior announcement.
 *
 * @param {string} message - The message to announce.
 * @param {'assertive'|'polite'} [priority='assertive'] - Announcement priority.
 */
export function announceToScreenReader(message, priority = 'assertive') {
  if (!message) return;

  const region = _ensureLiveRegion();
  region.setAttribute('aria-live', priority);

  // Clear first so repeated identical messages still trigger
  region.textContent = '';

  // Use rAF + setTimeout(0) to guarantee the DOM mutation is a distinct
  // step that assistive tech will observe.
  requestAnimationFrame(() => {
    setTimeout(() => {
      region.textContent = message;
    }, 50);
  });
}

// ---------------------------------------------------------------------------
// Focus management
// ---------------------------------------------------------------------------

/**
 * Programmatically move focus to an element referenced by a React ref.
 *
 * If the element does not have a tabindex, one is temporarily added so it
 * can receive focus (needed for non-interactive elements like headings or
 * section containers).
 *
 * @param {React.RefObject|HTMLElement} elementRef - A React ref or raw DOM element.
 * @param {{ preventScroll?: boolean }} [options] - Focus options.
 */
export function setFocusTo(elementRef, options = {}) {
  const el = elementRef && elementRef.current ? elementRef.current : elementRef;
  if (!el || typeof el.focus !== 'function') return;

  // Make the element focusable if it is not already
  const hadTabindex = el.hasAttribute('tabindex');
  if (!hadTabindex && !el.matches('a[href], button, input, select, textarea, [tabindex]')) {
    el.setAttribute('tabindex', '-1');
  }

  el.focus({ preventScroll: options.preventScroll ?? false });

  // Remove the temporary tabindex after a blur so the element does not
  // remain in the tab order permanently.
  if (!hadTabindex) {
    const cleanup = () => {
      el.removeAttribute('tabindex');
      el.removeEventListener('blur', cleanup);
    };
    el.addEventListener('blur', cleanup);
  }
}

// ---------------------------------------------------------------------------
// ID generation
// ---------------------------------------------------------------------------

let _idCounter = 0;

/**
 * Generate a unique ID suitable for aria-labelledby / aria-describedby.
 *
 * IDs are deterministic per session (incrementing counter) so they remain
 * stable during the component lifecycle.
 *
 * @param {string} [prefix='a11y'] - Prefix for the generated ID.
 * @returns {string} A unique DOM ID string.
 */
export function generateId(prefix = 'a11y') {
  _idCounter += 1;
  return `${prefix}-${_idCounter}`;
}

// ---------------------------------------------------------------------------
// Screen-reader-friendly formatters
// ---------------------------------------------------------------------------

/**
 * Number-to-words lookup tables. Covers values relevant to mortgage
 * amounts (up to trillions, though billions is the realistic max).
 */
const ONES = [
  '', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
  'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
  'seventeen', 'eighteen', 'nineteen',
];
const TENS = [
  '', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety',
];
const SCALES = ['', 'thousand', 'million', 'billion', 'trillion'];

/**
 * Convert a non-negative integer to English words.
 * @param {number} n
 * @returns {string}
 */
function _intToWords(n) {
  if (n === 0) return 'zero';

  let result = '';
  let scaleIdx = 0;

  while (n > 0) {
    const chunk = n % 1000;
    if (chunk !== 0) {
      let chunkStr = '';
      const hundreds = Math.floor(chunk / 100);
      const remainder = chunk % 100;

      if (hundreds > 0) {
        chunkStr += ONES[hundreds] + ' hundred';
        if (remainder > 0) chunkStr += ' ';
      }

      if (remainder >= 20) {
        chunkStr += TENS[Math.floor(remainder / 10)];
        if (remainder % 10 > 0) chunkStr += ' ' + ONES[remainder % 10];
      } else if (remainder > 0) {
        chunkStr += ONES[remainder];
      }

      if (SCALES[scaleIdx]) {
        chunkStr += ' ' + SCALES[scaleIdx];
      }

      result = chunkStr + (result ? ' ' + result : '');
    }

    n = Math.floor(n / 1000);
    scaleIdx += 1;
  }

  return result.trim();
}

/**
 * Format a currency amount into a screen-reader-friendly string.
 *
 * "$350,000" becomes "three hundred fifty thousand dollars"
 * "$1,250.50" becomes "one thousand two hundred fifty dollars and fifty cents"
 *
 * @param {number|string} amount - Dollar amount (numeric or formatted string like "$350,000").
 * @returns {string} Human-readable English text.
 */
export function formatCurrencyForScreenReader(amount) {
  if (amount == null || amount === '') return 'zero dollars';

  // Strip non-numeric characters except decimal and minus
  const cleaned = String(amount).replace(/[^0-9.\-]/g, '');
  const num = parseFloat(cleaned);

  if (isNaN(num)) return 'zero dollars';

  const isNegative = num < 0;
  const abs = Math.abs(num);
  const dollars = Math.floor(abs);
  const cents = Math.round((abs - dollars) * 100);

  let text = '';
  if (isNegative) text += 'negative ';

  text += _intToWords(dollars);
  text += dollars === 1 ? ' dollar' : ' dollars';

  if (cents > 0) {
    text += ' and ' + _intToWords(cents);
    text += cents === 1 ? ' cent' : ' cents';
  }

  return text;
}

/**
 * Format a date string into a screen-reader-friendly string.
 *
 * "03/30/2026" becomes "March 30, 2026"
 * Also handles ISO date strings and Date objects.
 *
 * @param {string|Date} dateInput - Date in MM/DD/YYYY, ISO 8601, or Date object.
 * @returns {string} Human-readable date string.
 */
export function formatDateForScreenReader(dateInput) {
  if (!dateInput) return '';

  let dateObj;

  if (dateInput instanceof Date) {
    dateObj = dateInput;
  } else if (typeof dateInput === 'string') {
    // Try MM/DD/YYYY format first
    const slashMatch = dateInput.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (slashMatch) {
      const [, month, day, year] = slashMatch;
      dateObj = new Date(parseInt(year, 10), parseInt(month, 10) - 1, parseInt(day, 10));
    } else {
      // Fallback: ISO or other parseable format
      dateObj = new Date(dateInput);
    }
  }

  if (!dateObj || isNaN(dateObj.getTime())) return '';

  return dateObj.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

/**
 * Format a phone number into a screen-reader-friendly string.
 *
 * "+18434169589" becomes "1 843 416 9589"
 * "(843) 416-9589" becomes "843 416 9589"
 *
 * Digits are grouped so screen readers announce them as number groups
 * rather than attempting to read the entire number as one large integer.
 *
 * @param {string} phone - Phone number in any format.
 * @returns {string} Space-separated digit groups for screen reader.
 */
export function formatPhoneForScreenReader(phone) {
  if (!phone) return '';

  const digits = String(phone).replace(/\D/g, '');

  if (digits.length === 0) return '';

  // 11 digits: country code + 10 digit number
  if (digits.length === 11 && digits[0] === '1') {
    return `${digits[0]} ${digits.slice(1, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`;
  }

  // 10 digits: standard US number
  if (digits.length === 10) {
    return `${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6)}`;
  }

  // Anything else: group into chunks of 3-4 for readability
  const chunks = [];
  for (let i = 0; i < digits.length; i += 3) {
    chunks.push(digits.slice(i, i + 3));
  }
  return chunks.join(' ');
}

// ---------------------------------------------------------------------------
// Screen reader detection heuristic
// ---------------------------------------------------------------------------

/**
 * Heuristic check for whether a screen reader may be active.
 *
 * There is no reliable API for this. We check:
 * 1. Whether the user has explicitly set prefers-reduced-motion (common among
 *    VoiceOver users).
 * 2. Whether focus-visible polyfill data attributes are present (indicates
 *    keyboard-first navigation).
 *
 * This should be used for progressive enhancement only, never to gate
 * accessibility features.
 *
 * @returns {boolean} True if a screen reader is likely active.
 */
export function detectScreenReaderHeuristic() {
  if (typeof window === 'undefined') return false;

  // iOS VoiceOver detection: check if the user agent is iOS and
  // the page has been interacted with via accessibility APIs
  // (no reliable detection exists, so we lean on reduced-motion)
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Check for aria-hidden manipulation or focus management that
  // suggests accessibility tooling is in use
  const hasAccessibilityFocus = document.querySelector('[data-focus-visible-added]') !== null;

  return prefersReducedMotion || hasAccessibilityFocus;
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export default {
  announceToScreenReader,
  setFocusTo,
  generateId,
  formatCurrencyForScreenReader,
  formatDateForScreenReader,
  formatPhoneForScreenReader,
  detectScreenReaderHeuristic,
};
