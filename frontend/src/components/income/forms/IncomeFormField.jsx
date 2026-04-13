import React from 'react';
import './forms.css';

/**
 * Shared wrapper for income form fields.
 * Renders a label with optional required asterisk, optional note text,
 * then the children (the actual input / select / textarea).
 *
 * @param {Object}  props
 * @param {string}  props.label     - Field label text
 * @param {boolean} [props.required] - Show required asterisk
 * @param {string}  [props.note]    - Optional note below the input
 * @param {string}  [props.htmlFor] - id to connect label to input
 * @param {boolean} [props.checkbox] - Render in checkbox layout
 * @param {string}  [props.className] - Extra class name
 * @param {React.ReactNode} props.children - The input element(s)
 */
export default function IncomeFormField({
  label,
  required = false,
  note,
  htmlFor,
  checkbox = false,
  className = '',
  children,
}) {
  const fieldClass = [
    'income-form-field',
    checkbox ? 'checkbox-field' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={fieldClass}>
      <label className="income-form-field-label" htmlFor={htmlFor}>
        {label}
        {required && <span className="required-asterisk">*</span>}
      </label>
      {children}
      {note && <span className="income-form-field-note">{note}</span>}
    </div>
  );
}
