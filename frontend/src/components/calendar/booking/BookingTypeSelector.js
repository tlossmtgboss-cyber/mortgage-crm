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
      <label style={styles.label}>Appointment Type</label>
      <div style={styles.typePills}>
        {appointmentTypes.map((t) => (
          <button
            key={t.id}
            onClick={() => onSelect(t)}
            style={{
              ...styles.typePill,
              ...(selectedType?.id === t.id ? styles.typePillActive : {}),
            }}
          >
            {t.type_name}
            <span style={styles.typeDuration}>{t.default_duration_minutes}m</span>
          </button>
        ))}
      </div>
    </div>
  );
}
