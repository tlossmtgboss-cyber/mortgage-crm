/**
 * DurationInput - Combined years and months input
 */

import React, { useState, useEffect } from 'react';
import './DurationInput.css';

const DurationInput = ({
  value,
  onChange,
  error,
  helpText,
  disabled = false,
  required = false,
}) => {
  const [years, setYears] = useState('');
  const [months, setMonths] = useState('');

  // Parse incoming value
  useEffect(() => {
    if (value && typeof value === 'object') {
      setYears(value.years?.toString() || '');
      setMonths(value.months?.toString() || '');
    }
  }, [value]);

  const handleYearsChange = (e) => {
    const val = e.target.value;
    if (val === '' || /^\d+$/.test(val)) {
      const numVal = val === '' ? '' : Math.min(99, parseInt(val, 10));
      setYears(numVal.toString());
      onChange({
        years: numVal === '' ? 0 : numVal,
        months: months === '' ? 0 : parseInt(months, 10),
      });
    }
  };

  const handleMonthsChange = (e) => {
    const val = e.target.value;
    if (val === '' || /^\d+$/.test(val)) {
      const numVal = val === '' ? '' : Math.min(11, parseInt(val, 10));
      setMonths(numVal.toString());
      onChange({
        years: years === '' ? 0 : parseInt(years, 10),
        months: numVal === '' ? 0 : numVal,
      });
    }
  };

  return (
    <div className={`duration-input ${error ? 'has-error' : ''}`}>
      <div className="duration-fields">
        <div className="duration-field">
          <input
            type="number"
            value={years}
            onChange={handleYearsChange}
            placeholder="0"
            min="0"
            max="99"
            disabled={disabled}
            className="duration-input-field"
          />
          <label className="duration-label">Years</label>
        </div>
        <div className="duration-field">
          <input
            type="number"
            value={months}
            onChange={handleMonthsChange}
            placeholder="0"
            min="0"
            max="11"
            disabled={disabled}
            className="duration-input-field"
          />
          <label className="duration-label">Months</label>
        </div>
      </div>
      {helpText && <p className="help-text">{helpText}</p>}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
};

export default DurationInput;
