/**
 * Internationalization (i18n) for the public booking page.
 *
 * Lightweight approach using React Context + JSON translation files.
 * No heavy i18n library required.
 *
 * Supported languages:
 *   en - English (default / fallback)
 *   es - Spanish
 *   zh - Chinese (Simplified)
 *   vi - Vietnamese
 *   ko - Korean
 *
 * Language detection priority:
 *   1. URL parameter: ?lang=es
 *   2. localStorage (persisted from LanguageSelector)
 *   3. Browser language (navigator.language)
 *   4. Fallback to English
 *
 * Usage in components:
 *   import { LanguageProvider, useTranslation } from '../i18n';
 *
 *   // Wrap your page/app:
 *   <LanguageProvider>
 *     <PublicBooking />
 *   </LanguageProvider>
 *
 *   // Inside components:
 *   const { t, language, setLanguage, locale, languages } = useTranslation();
 *   <h1>{t('booking.title')}</h1>
 *   <p>{t('booking.step', { current: 2, total: 5 })}</p>
 *
 *   // For date formatting with locale:
 *   date.toLocaleDateString(locale, { weekday: 'long' })
 */

export { LanguageProvider, useTranslation, SUPPORTED_LANGUAGES } from './LanguageContext';
