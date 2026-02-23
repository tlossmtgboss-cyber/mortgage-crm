/**
 * EmailInput - Email input with typo validation
 * Catches common email typos like .ocm instead of .com
 */

import React, { forwardRef, useState, useCallback, useEffect } from 'react';
import './EmailInput.css';

// Common email domain typos and their corrections
const DOMAIN_TYPOS = {
  // .com typos
  '.ocm': '.com',
  '.con': '.com',
  '.cpm': '.com',
  '.vom': '.com',
  '.coM': '.com',
  // Note: '.co' removed — it's a valid TLD (Colombia, also used by tech companies)
  '.om': '.com',
  '.cm': '.com',
  '.comn': '.com',
  '.comm': '.com',
  '.copm': '.com',
  '.coom': '.com',
  '.xom': '.com',
  // .net typos
  '.nte': '.net',
  '.nett': '.net',
  '.ent': '.net',
  '.neet': '.net',
  // .org typos
  '.ogr': '.org',
  '.oeg': '.org',
  '.orgg': '.org',
  '.rog': '.org',
  // .edu typos
  '.eud': '.edu',
  '.ed': '.edu',
  '.eduu': '.edu',
  // Gmail specific
  'gmial.com': 'gmail.com',
  'gmal.com': 'gmail.com',
  'gamil.com': 'gmail.com',
  'gmaill.com': 'gmail.com',
  'gmeil.com': 'gmail.com',
  'gnail.com': 'gmail.com',
  'gmai.com': 'gmail.com',
  'gmail.co': 'gmail.com',
  'gmail.om': 'gmail.com',
  // Yahoo specific
  'yahooo.com': 'yahoo.com',
  'yaho.com': 'yahoo.com',
  'yhaoo.com': 'yahoo.com',
  'yaoo.com': 'yahoo.com',
  'yahoo.co': 'yahoo.com',
  // Hotmail specific
  'hotmal.com': 'hotmail.com',
  'hotmial.com': 'hotmail.com',
  'hotmai.com': 'hotmail.com',
  'hotmil.com': 'hotmail.com',
  // Outlook specific
  'outlok.com': 'outlook.com',
  'outloo.com': 'outlook.com',
  'outlookk.com': 'outlook.com',
  // iCloud specific
  'icoud.com': 'icloud.com',
  'iclod.com': 'icloud.com',
  'icloud.co': 'icloud.com',
  // AOL specific
  'aoll.com': 'aol.com',
  'ao.com': 'aol.com',
};

// Check email for typos and return suggestion if found
const checkEmailTypo = (email) => {
  if (!email || !email.includes('@')) return null;

  const lowercaseEmail = email.toLowerCase();
  const atIndex = lowercaseEmail.lastIndexOf('@');
  const domain = lowercaseEmail.substring(atIndex + 1);

  // Check full domain matches (e.g., gmial.com → gmail.com)
  if (DOMAIN_TYPOS[domain]) {
    return {
      original: email,
      suggested: email.substring(0, atIndex + 1) + DOMAIN_TYPOS[domain],
      typo: domain,
      correction: DOMAIN_TYPOS[domain],
    };
  }

  // Check TLD typos (e.g., .ocm → .com)
  for (const [typo, correction] of Object.entries(DOMAIN_TYPOS)) {
    if (typo.startsWith('.') && domain.endsWith(typo.substring(1))) {
      const correctedDomain = domain.replace(new RegExp(typo.substring(1) + '$'), correction.substring(1));
      return {
        original: email,
        suggested: email.substring(0, atIndex + 1) + correctedDomain,
        typo: typo,
        correction: correction,
      };
    }
  }

  return null;
};

// Basic email format validation
const isValidEmailFormat = (email) => {
  if (!email) return false;
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
};

const EmailInput = forwardRef(({
  value = '',
  onChange,
  onBlur,
  placeholder = 'email@example.com',
  label,
  required = false,
  disabled = false,
  error,
  helpText,
  className = '',
  autoComplete = 'email',
  ...props
}, ref) => {
  const [typoSuggestion, setTypoSuggestion] = useState(null);
  const [localValue, setLocalValue] = useState(value);
  const [validationError, setValidationError] = useState(null);

  // Sync localValue when external value changes (e.g., from state restore)
  useEffect(() => {
    setLocalValue(value || '');
  }, [value]);

  const handleChange = useCallback((e) => {
    const newValue = e.target.value;
    setLocalValue(newValue);
    setTypoSuggestion(null); // Clear suggestion while typing
    if (validationError) setValidationError(null); // Clear error while typing
    onChange(newValue);
  }, [onChange, validationError]);

  const handleBlur = useCallback((e) => {
    const email = e.target.value.trim();

    if (email) {
      // Validate email format
      if (!isValidEmailFormat(email)) {
        setValidationError('Please enter a valid email address');
      } else {
        setValidationError(null);
        // Check for typos only if format is valid
        const suggestion = checkEmailTypo(email);
        setTypoSuggestion(suggestion);
      }
    } else {
      setValidationError(null);
    }

    if (onBlur) {
      onBlur(e);
    }
  }, [onBlur]);

  const handleAcceptSuggestion = useCallback(() => {
    if (typoSuggestion) {
      setLocalValue(typoSuggestion.suggested);
      onChange(typoSuggestion.suggested);
      setTypoSuggestion(null);
    }
  }, [typoSuggestion, onChange]);

  const handleDismissSuggestion = useCallback(() => {
    setTypoSuggestion(null);
  }, []);

  const displayError = error || validationError;

  return (
    <div className={`email-input-wrapper ${className} ${displayError ? 'has-error' : ''} ${typoSuggestion ? 'has-suggestion' : ''}`}>
      {label && (
        <label className="email-input-label">
          {label}
          {required && <span className="required">*</span>}
        </label>
      )}

      <div className="email-input-container">
        <input
          ref={ref}
          type="email"
          value={localValue || ''}
          onChange={handleChange}
          onBlur={handleBlur}
          placeholder={placeholder}
          disabled={disabled}
          className="email-input"
          autoComplete={autoComplete}
          inputMode="email"
          {...props}
        />
      </div>

      {/* Typo Suggestion Banner */}
      {typoSuggestion && (
        <div className="email-typo-suggestion">
          <div className="suggestion-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <div className="suggestion-content">
            <p className="suggestion-text">
              Did you mean <strong>{typoSuggestion.suggested}</strong>?
            </p>
            <div className="suggestion-actions">
              <button
                type="button"
                className="suggestion-btn accept"
                onClick={handleAcceptSuggestion}
              >
                Yes, fix it
              </button>
              <button
                type="button"
                className="suggestion-btn dismiss"
                onClick={handleDismissSuggestion}
              >
                No, keep it
              </button>
            </div>
          </div>
        </div>
      )}

      {helpText && !displayError && !typoSuggestion && (
        <div className="email-input-help">{helpText}</div>
      )}

      {displayError && <div className="email-input-error" role="alert">{displayError}</div>}
    </div>
  );
});

EmailInput.displayName = 'EmailInput';

export default EmailInput;
