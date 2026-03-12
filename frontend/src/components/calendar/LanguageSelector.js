import React from 'react';
import { useTranslation } from '../../i18n';

/**
 * Compact language selector dropdown for the public booking page.
 * Shows a globe icon and native language name, persists selection to localStorage.
 */
const LanguageSelector = React.memo(() => {
  const { language, setLanguage, languages, t } = useTranslation();

  return (
    <div className="language-selector" role="navigation" aria-label={t('language.label')}>
      <svg
        className="language-icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        width="16"
        height="16"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="10" />
        <path d="M2 12h20" />
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      </svg>
      <select
        value={language}
        onChange={(e) => setLanguage(e.target.value)}
        className="language-select"
        aria-label={t('language.label')}
      >
        {languages.map((lang) => (
          <option key={lang.code} value={lang.code}>
            {lang.nativeName}
          </option>
        ))}
      </select>
    </div>
  );
});

LanguageSelector.displayName = 'LanguageSelector';

export default LanguageSelector;
