/**
 * BookingTypeSelector - Appointment type pill selector for the booking widget.
 *
 * Only renders when there are multiple appointment types to choose from.
 *
 * Props:
 *   appointmentTypes - Array of appointment type objects
 *   selectedType     - Currently selected type object
 *   onSelect         - Callback when a type is selected
 *   styles           - Style objects from the parent widget
 *   accentColor      - Brand accent color
 */
import React from 'react';

export default function BookingTypeSelector({
  appointmentTypes,
  selectedType,
  onSelect,
  styles,
  accentColor,
}) {
  if (!appointmentTypes || appointmentTypes.length <= 1) return null;

  return (
    <div style={styles.section}>
      <label style={styles.label} id="bw-type-label">Appointment Type</label>
      <div
        style={styles.typePills}
        role="radiogroup"
        aria-labelledby="bw-type-label"
      >
        {appointmentTypes.map((t) => {
          const isSelected = selectedType?.id === t.id;
          return (
            <button
              key={t.id}
              onClick={() => onSelect(t)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onSelect(t);
                }
              }}
              role="radio"
              aria-checked={isSelected}
              aria-label={`${t.type_name}, ${t.default_duration_minutes} minutes`}
              style={{
                ...styles.typePill,
                ...(isSelected ? styles.typePillActive : {}),
              }}
            >
              {t.type_name}
              <span style={styles.typeDuration} aria-hidden="true">{t.default_duration_minutes}m</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
