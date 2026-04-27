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

export interface PanelProps {
  section?: SectionResponse;
  onChange: (data: Record<string, unknown>) => void;
  onComplete: () => void;
  application?: ApplicationResponse | null;
  onSubmit?: (
    body: ApplicationSubmitRequest,
  ) => Promise<ApplicationSubmitResponse | null>;
  onAskAria?: () => void;
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
  cols?: 1 | 2 | 3;
  options?: { value: string; label: string }[]; // for select
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
  const inputType = isCurrency ? 'number' : type;

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
          inputMode={inputMode as any}
          className="urla-field__input"
          value={(value as string | number) ?? ''}
          placeholder={placeholder}
          onChange={e =>
            onChange(
              name,
              type === 'number' || isCurrency
                ? e.target.value === ''
                  ? null
                  : Number(e.target.value)
                : e.target.value,
            )
          }
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
      >
        Yes
      </button>
      <button
        type="button"
        className={`urla-yesno__btn${value === false ? ' is-selected' : ''}`}
        onClick={() => onChange(name, false)}
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
  onClick: () => void;
  disabled?: boolean;
  label?: string;
}> = ({ onClick, disabled, label = 'Save & Continue' }) => (
  <div className="urla-actions">
    <button
      type="button"
      className="urla-btn urla-btn--primary"
      onClick={onClick}
      disabled={disabled}
    >
      {label}
    </button>
  </div>
);

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
