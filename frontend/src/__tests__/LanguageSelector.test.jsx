/**
 * Tests for LanguageSelector component and i18n LanguageProvider/useTranslation.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import LanguageSelector from '../components/calendar/LanguageSelector';
import { LanguageProvider, useTranslation, SUPPORTED_LANGUAGES } from '../i18n';

// Helper to render LanguageSelector within LanguageProvider
function renderWithLanguageProvider(ui) {
  return render(
    <LanguageProvider>
      {ui}
    </LanguageProvider>
  );
}

describe('LanguageSelector', () => {
  it('renders a select dropdown', () => {
    renderWithLanguageProvider(<LanguageSelector />);
    // Both the nav wrapper and the select have aria-label="Language"
    const selects = screen.getAllByLabelText('Language');
    const selectEl = selects.find(el => el.tagName === 'SELECT');
    expect(selectEl).toBeInTheDocument();
    expect(selectEl.tagName).toBe('SELECT');
  });

  it('renders all supported languages as options', () => {
    renderWithLanguageProvider(<LanguageSelector />);
    const selects = screen.getAllByLabelText('Language');
    const selectEl = selects.find(el => el.tagName === 'SELECT');
    const options = selectEl.querySelectorAll('option');

    expect(options.length).toBe(SUPPORTED_LANGUAGES.length);

    const optionValues = Array.from(options).map(o => o.value);
    SUPPORTED_LANGUAGES.forEach(lang => {
      expect(optionValues).toContain(lang.code);
    });
  });

  it('shows native language names in dropdown', () => {
    renderWithLanguageProvider(<LanguageSelector />);

    expect(screen.getByText('English')).toBeInTheDocument();
    // Spanish native name
    expect(screen.getByText('Espa\u00f1ol')).toBeInTheDocument();
  });

  it('defaults to English', () => {
    renderWithLanguageProvider(<LanguageSelector />);
    const selects = screen.getAllByLabelText('Language');
    const selectEl = selects.find(el => el.tagName === 'SELECT');
    expect(selectEl.value).toBe('en');
  });

  it('has navigation role with aria-label', () => {
    renderWithLanguageProvider(<LanguageSelector />);
    const nav = screen.getByRole('navigation');
    expect(nav).toHaveAttribute('aria-label', 'Language');
  });
});

// ---------------------------------------------------------------------------
// LanguageProvider / useTranslation integration tests
// ---------------------------------------------------------------------------

function TranslationTestComponent({ translationKey, params }) {
  const { t, language, locale } = useTranslation();
  return (
    <div>
      <span data-testid="translated">{t(translationKey, params)}</span>
      <span data-testid="language">{language}</span>
      <span data-testid="locale">{locale}</span>
    </div>
  );
}

describe('LanguageProvider / useTranslation', () => {
  it('provides a default English translation', () => {
    render(
      <LanguageProvider>
        <TranslationTestComponent translationKey="booking.loading" />
      </LanguageProvider>
    );

    expect(screen.getByTestId('translated').textContent).toBe('Loading...');
    expect(screen.getByTestId('language').textContent).toBe('en');
    expect(screen.getByTestId('locale').textContent).toBe('en-US');
  });

  it('returns the key itself when translation is not found', () => {
    render(
      <LanguageProvider>
        <TranslationTestComponent translationKey="nonexistent.key" />
      </LanguageProvider>
    );

    expect(screen.getByTestId('translated').textContent).toBe('nonexistent.key');
  });

  it('translates nested keys (e.g. datetime.pickDate)', () => {
    render(
      <LanguageProvider>
        <TranslationTestComponent translationKey="datetime.pickDate" />
      </LanguageProvider>
    );

    expect(screen.getByTestId('translated').textContent).toBe('Pick a date');
  });

  it('translates form labels', () => {
    render(
      <LanguageProvider>
        <TranslationTestComponent translationKey="form.firstName" />
      </LanguageProvider>
    );

    expect(screen.getByTestId('translated').textContent).toBe('First Name');
  });

  it('translates confirmation messages', () => {
    render(
      <LanguageProvider>
        <TranslationTestComponent translationKey="confirmation.title" />
      </LanguageProvider>
    );

    expect(screen.getByTestId('translated').textContent).toBe('Your request has been made');
  });

  it('throws error when useTranslation is used outside LanguageProvider', () => {
    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(() => {
      render(<TranslationTestComponent translationKey="test" />);
    }).toThrow('useTranslation must be used within a LanguageProvider');

    consoleSpy.mockRestore();
  });

  it('SUPPORTED_LANGUAGES contains expected language codes', () => {
    expect(SUPPORTED_LANGUAGES.map(l => l.code)).toEqual(['en', 'es', 'zh', 'vi', 'ko']);
  });
});
