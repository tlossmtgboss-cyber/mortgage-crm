/**
 * Shared form primitives for URLA panels.
 *
 * Each panel uses these to stay consistent in look, accessibility, and
 * data flow. All panels share the same prop shape — see the PanelProps
 * interface below.
 */
import React from 'react';

import type { ApplicationResponse, SectionResponse } from '../../types';
import type { ApplicationSubmitRequest, ApplicationSubmitResponse } from '../../types';

// ---------- Currency helpers ----------
//
// Money is stored as a canonical decimal string (e.g. "250000" or "250000.10")
// — never as a JS `number`. Doubles silently drop trailing zeros and drift
// under arithmetic, both of which break TRID tolerance math downstream. The
// helpers below convert between the canonical store representation and the
// comma-formatted display string used by the input. Use them ONLY at the
// input boundary.

export function decimalToDisplay(s: string | number | null | undefined): string {
  if (s === null || s === undefined || s === '') return '';
  const raw = String(s);
  // Strip anything that isn't a digit, dot, or leading minus.
  const cleaned = raw.replace(/[^\d.]/g, '');
  if (!cleaned) return '';
  const [intPart, fracPart] = cleaned.split('.', 2);
  const grouped = (intPart || '0').replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return fracPart !== undefined ? `${grouped}.${fracPart}` : grouped;
}

export function displayToDecimal(s: string): string {
  if (s === null || s === undefined) return '';
  // Strip thousands separators / whitespace; keep digits and the decimal point.
  const cleaned = String(s).replace(/[^\d.]/g, '');
  if (!cleaned) return '';
  // Collapse any accidental multi-dot inputs to a single decimal point.
  const firstDot = cleaned.indexOf('.');
  if (firstDot === -1) return cleaned;
  return (
    cleaned.slice(0, firstDot + 1) +
    cleaned.slice(firstDot + 1).replace(/\./g, '')
  );
}

export interface IntakeData {
  is_veteran: boolean | null;
  loan_purpose: 'purchase' | 'refinance' | null;
  has_co_borrower: boolean | null;
  co_borrowers: Array<{ first_name: string; last_name: string }>;
}

export interface PanelProps {
  section?: SectionResponse;
  onChange: (data: Record<string, unknown>) => void;
  onComplete: () => void;
  application?: ApplicationResponse | null;
  onSubmit?: (
    body: ApplicationSubmitRequest,
  ) => Promise<ApplicationSubmitResponse | null>;
  onAskAria?: () => void;
  intakeData?: IntakeData;
  intakeLoanPurpose?: 'purchase' | 'refinance' | null;
  allSections?: Partial<Record<import('../../types').SectionKey, SectionResponse>>;
  onNavigate?: (key: import('../../types').SectionKey, highlightField?: string) => void;
}

// ---------- Field primitives ----------

export interface FieldProps {
  label: string;
  name: string;
  value: unknown;
  onChange: (name: string, value: unknown) => void;
  type?: 'text' | 'email' | 'tel' | 'number' | 'date' | 'currency';
  placeholder?: string;
  required?: boolean;
  helpText?: string;
  cols?: 1 | 2 | 3 | 4;
  options?: { value: string; label: string }[];
  inputMode?: string;
}

export const TextField: React.FC<FieldProps> = ({
  label,
  name,
  value,
  onChange,
  type = 'text',
  placeholder,
  required,
  helpText,
  cols = 1,
  inputMode,
}) => {
  const isCurrency = type === 'currency';
  // Currency uses a text input so we can render grouped thousands
  // separators on display. We NEVER coerce currency to Number() — see the
  // helpers at the top of this file for the rationale.
  const inputType = isCurrency ? 'text' : type;
  const resolvedInputMode = inputMode ?? (isCurrency ? 'decimal' : undefined);

  // Value rendered in the input. For currency, format the canonical decimal
  // string into a display string with commas. For other fields, pass through.
  const displayValue = isCurrency
    ? decimalToDisplay(value as string | number | null | undefined)
    : ((value as string | number | null | undefined) ?? '');

  return (
    <div
      className={`urla-field urla-field--cols-${cols}${required ? ' is-required' : ''}`}
    >
      <label className="urla-field__label" htmlFor={`f-${name}`}>
        {label}
        {required && <span className="urla-field__required" aria-label="required"> *</span>}
      </label>
      <div className={`urla-field__control${isCurrency ? ' urla-field__control--currency' : ''}`}>
        {isCurrency && <span className="urla-field__prefix">$</span>}
        <input
          id={`f-${name}`}
          name={name}
          type={inputType}
          inputMode={resolvedInputMode as any}
          className="urla-field__input"
          value={displayValue as string | number}
          placeholder={placeholder}
          onChange={e => {
            if (isCurrency) {
              // Store the canonical decimal string. Never Number().
              onChange(name, displayToDecimal(e.target.value));
            } else if (type === 'number') {
              // Plain numeric (non-money) fields like counts / years still
              // use JS number — losing trailing zeros is fine for integers.
              onChange(
                name,
                e.target.value === '' ? null : Number(e.target.value),
              );
            } else {
              onChange(name, e.target.value);
            }
          }}
        />
      </div>
      {helpText && <p className="urla-field__help">{helpText}</p>}
    </div>
  );
};

export const SelectField: React.FC<FieldProps> = ({
  label,
  name,
  value,
  onChange,
  options = [],
  required,
  cols = 1,
  helpText,
}) => (
  <div className={`urla-field urla-field--cols-${cols}${required ? ' is-required' : ''}`}>
    <label className="urla-field__label" htmlFor={`f-${name}`}>
      {label}
      {required && <span className="urla-field__required" aria-label="required"> *</span>}
    </label>
    <select
      id={`f-${name}`}
      name={name}
      className="urla-field__select"
      value={(value as string) ?? ''}
      onChange={e => onChange(name, e.target.value)}
    >
      <option value="">Select…</option>
      {options.map(opt => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
    {helpText && <p className="urla-field__help">{helpText}</p>}
  </div>
);

export interface YesNoFieldProps {
  label: string;
  name: string;
  value: boolean | null | undefined;
  onChange: (name: string, value: boolean) => void;
  cols?: 1 | 2 | 3;
}

export const YesNoField: React.FC<YesNoFieldProps> = ({
  label,
  name,
  value,
  onChange,
  cols = 1,
}) => (
  <div className={`urla-field urla-field--cols-${cols}`}>
    <span className="urla-field__label">{label}</span>
    <div className="urla-yesno">
      <button
        type="button"
        className={`urla-yesno__btn${value === true ? ' is-selected' : ''}`}
        onClick={() => onChange(name, true)}
        aria-pressed={value === true}
      >
        Yes
      </button>
      <button
        type="button"
        className={`urla-yesno__btn${value === false ? ' is-selected' : ''}`}
        onClick={() => onChange(name, false)}
        aria-pressed={value === false}
      >
        No
      </button>
    </div>
  </div>
);

// ---------- Layout primitives ----------

export const FormSection: React.FC<{
  title?: string;
  description?: string;
  children: React.ReactNode;
}> = ({ title, description, children }) => (
  <section className="urla-form-section">
    {title && <h3 className="urla-form-section__title">{title}</h3>}
    {description && <p className="urla-form-section__desc">{description}</p>}
    <div className="urla-form-grid">{children}</div>
  </section>
);

// ---------- Continue button ----------

export const ContinueButton: React.FC<{
  onClick: () => void | Promise<void>;
  disabled?: boolean;
  label?: string;
}> = ({ onClick, disabled, label = 'Save & Continue' }) => {
  const [saving, setSaving] = React.useState(false);

  const handleClick = async () => {
    if (saving || disabled) return;
    setSaving(true);
    try {
      await onClick();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="urla-actions">
      <button
        type="button"
        className="urla-btn urla-btn--primary"
        onClick={handleClick}
        disabled={disabled || saving}
      >
        {saving ? 'Saving...' : label}
      </button>
    </div>
  );
};

// ---------- Hook: section data with field-level updater ----------

export function usePanelData(
  section: SectionResponse | undefined,
  onChange: (data: Record<string, unknown>) => void,
) {
  const data = (section?.data as Record<string, unknown> | undefined) || {};

  const updateField = (name: string, value: unknown) => {
    // Dot-path support for nested fields like "current_address.street".
    if (name.includes('.')) {
      const [parent, child] = name.split('.', 2);
      const parentValue = (data[parent] as Record<string, unknown>) || {};
      onChange({
        ...data,
        [parent]: { ...parentValue, [child]: value },
      });
      return;
    }
    onChange({ ...data, [name]: value });
  };

  return { data, updateField };
}
