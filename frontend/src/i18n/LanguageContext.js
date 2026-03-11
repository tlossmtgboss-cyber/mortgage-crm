import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';

import en from './translations/en.json';
import es from './translations/es.json';
import zh from './translations/zh.json';
import vi from './translations/vi.json';
import ko from './translations/ko.json';

const translations = { en, es, zh, vi, ko };

const SUPPORTED_LANGUAGES = [
  { code: 'en', name: 'English', nativeName: 'English' },
  { code: 'es', name: 'Spanish', nativeName: 'Espa\u00f1ol' },
  { code: 'zh', name: 'Chinese', nativeName: '\u4e2d\u6587' },
  { code: 'vi', name: 'Vietnamese', nativeName: 'Ti\u1ebfng Vi\u1ec7t' },
  { code: 'ko', name: 'Korean', nativeName: '\ud55c\uad6d\uc5b4' },
];

const STORAGE_KEY = 'perennia_booking_lang';

/**
 * Detect the best language to use.
 * Priority: URL ?lang= param > localStorage > browser language > 'en'
 */
function detectLanguage() {
  // 1. URL parameter
  try {
    const params = new URLSearchParams(window.location.search);
    const langParam = params.get('lang');
    if (langParam && translations[langParam]) {
      return langParam;
    }
  } catch (_e) {
    // URLSearchParams not available or parse error
  }

  // 2. localStorage
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && translations[stored]) {
      return stored;
    }
  } catch (_e) {
    // localStorage not available
  }

  // 3. Browser language (navigator.language or navigator.languages)
  try {
    const browserLangs = navigator.languages || [navigator.language];
    for (const lang of browserLangs) {
      // Match exact code first (e.g., 'es'), then prefix (e.g., 'zh-CN' -> 'zh')
      const code = lang.toLowerCase();
      if (translations[code]) return code;
      const prefix = code.split('-')[0];
      if (translations[prefix]) return prefix;
    }
  } catch (_e) {
    // navigator not available
  }

  // 4. Fallback
  return 'en';
}

/**
 * Resolve a dot-separated key path against a translations object.
 * Returns the value at the path, or undefined if not found.
 */
function getNestedValue(obj, keyPath) {
  const keys = keyPath.split('.');
  let current = obj;
  for (const key of keys) {
    if (current == null || typeof current !== 'object') return undefined;
    current = current[key];
  }
  return current;
}

const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(detectLanguage);

  const setLanguage = useCallback((code) => {
    if (!translations[code]) return;
    setLanguageState(code);
    try {
      localStorage.setItem(STORAGE_KEY, code);
    } catch (_e) {
      // localStorage not available
    }
    // Update URL param without full reload
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('lang', code);
      window.history.replaceState({}, '', url.toString());
    } catch (_e) {
      // URL manipulation not available
    }
  }, []);

  /**
   * Translate a key with optional interpolation.
   * Usage:
   *   t('booking.title')
   *   t('booking.step', { current: 2, total: 5 })  ->  "Step 2 of 5"
   *
   * Falls back to English if key not found in current language.
   * Falls back to the key itself if not found in English either.
   */
  const t = useCallback((key, params) => {
    let value = getNestedValue(translations[language], key);

    // Fallback to English
    if (value === undefined && language !== 'en') {
      value = getNestedValue(translations.en, key);
    }

    // Fallback to raw key
    if (value === undefined) {
      return key;
    }

    // Interpolation: replace {name} with params.name
    if (params && typeof value === 'string') {
      return value.replace(/\{(\w+)\}/g, (match, paramName) => {
        return params[paramName] !== undefined ? String(params[paramName]) : match;
      });
    }

    return value;
  }, [language]);

  /**
   * Get the locale string for date/time formatting.
   * Maps our language codes to BCP 47 locale tags.
   */
  const locale = useMemo(() => {
    const localeMap = {
      en: 'en-US',
      es: 'es-US',
      zh: 'zh-CN',
      vi: 'vi-VN',
      ko: 'ko-KR',
    };
    return localeMap[language] || 'en-US';
  }, [language]);

  const contextValue = useMemo(() => ({
    language,
    setLanguage,
    t,
    locale,
    languages: SUPPORTED_LANGUAGES,
  }), [language, setLanguage, t, locale]);

  return (
    <LanguageContext.Provider value={contextValue}>
      {children}
    </LanguageContext.Provider>
  );
}

/**
 * Hook to access translation function and language state.
 * Returns { t, language, setLanguage, locale, languages }
 */
export function useTranslation() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useTranslation must be used within a LanguageProvider');
  }
  return context;
}

export { SUPPORTED_LANGUAGES };
export default LanguageContext;
