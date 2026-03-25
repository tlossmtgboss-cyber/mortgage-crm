/**
 * BookingWidget Styles — extracted from BookingWidget.js for maintainability.
 *
 * Inline CSS-in-JS (no external CSS dependency for embeddability).
 * Returns a styles object keyed by component section.
 *
 * @param {string} color - Accent/brand color
 * @param {Function} darken - Color darkening utility
 * @returns {Object} Style definitions for all widget sections
 */
export function buildStyles(color, darken) {
  return {
    container: {
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      maxWidth: '420px',
      width: '100%',
      background: '#ffffff',
      borderRadius: '12px',
      boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
      overflow: 'hidden',
      fontSize: '14px',
      lineHeight: '1.5',
      color: '#1a1a1a',
      boxSizing: 'border-box',
    },
    header: {
      padding: '20px 20px 16px',
      borderBottom: '1px solid #f0f0f0',
      textAlign: 'center',
    },
    logo: {
      maxHeight: '40px',
      maxWidth: '160px',
      objectFit: 'contain',
      marginBottom: '12px',
    },
    loInfo: {
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      justifyContent: 'center',
      marginBottom: '12px',
    },
    loPhoto: {
      width: '48px',
      height: '48px',
      borderRadius: '50%',
      objectFit: 'cover',
    },
    loName: {
      fontWeight: '600',
      fontSize: '15px',
      textAlign: 'left',
    },
    loTitle: {
      fontSize: '12px',
      color: '#666',
      textAlign: 'left',
    },
    loNmls: {
      fontSize: '11px',
      color: '#999',
      textAlign: 'left',
    },
    title: {
      margin: '0',
      fontSize: '18px',
      fontWeight: '600',
      color: '#1a1a1a',
    },
    section: {
      padding: '0 20px',
      marginBottom: '16px',
    },
    label: {
      display: 'block',
      fontSize: '13px',
      fontWeight: '600',
      color: '#555',
      marginBottom: '8px',
    },
    // Appointment type pills
    typePills: {
      display: 'flex',
      gap: '8px',
      flexWrap: 'wrap',
    },
    typePill: {
      padding: '8px 14px',
      borderRadius: '20px',
      border: '1px solid #ddd',
      background: '#fff',
      cursor: 'pointer',
      fontSize: '13px',
      fontWeight: '500',
      color: '#333',
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
      transition: 'all 0.15s ease',
    },
    typePillActive: {
      borderColor: color,
      background: `${color}12`,
      color: color,
    },
    typeDuration: {
      fontSize: '11px',
      color: '#999',
    },
    // Week date picker
    weekNav: {
      display: 'flex',
      alignItems: 'center',
      gap: '4px',
    },
    navBtn: {
      background: 'none',
      border: 'none',
      fontSize: '24px',
      cursor: 'pointer',
      color: '#666',
      padding: '4px 8px',
      borderRadius: '6px',
      lineHeight: '1',
    },
    weekDates: {
      display: 'flex',
      gap: '4px',
      flex: 1,
      justifyContent: 'center',
    },
    dateCard: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      padding: '8px 4px',
      borderRadius: '8px',
      border: '1px solid #e5e5e5',
      background: '#fff',
      cursor: 'pointer',
      minWidth: '44px',
      transition: 'all 0.15s ease',
    },
    dateCardSelected: {
      color: '#fff',
      border: '1px solid',
    },
    dateCardDisabled: {
      opacity: 0.35,
      cursor: 'default',
    },
    dateCardToday: {
      borderColor: color,
    },
    dayName: {
      fontSize: '10px',
      fontWeight: '600',
      color: 'inherit',
      letterSpacing: '0.5px',
    },
    dayNumber: {
      fontSize: '16px',
      fontWeight: '700',
      color: 'inherit',
    },
    // Time grid
    timeGrid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(3, 1fr)',
      gap: '6px',
    },
    timeSlot: {
      padding: '10px 4px',
      borderRadius: '8px',
      border: '1px solid #e5e5e5',
      background: '#fff',
      cursor: 'pointer',
      fontSize: '13px',
      fontWeight: '500',
      textAlign: 'center',
      transition: 'all 0.15s ease',
      color: '#333',
    },
    timeSlotSelected: {
      color: '#fff',
    },
    noSlots: {
      textAlign: 'center',
      color: '#999',
      fontSize: '13px',
      padding: '16px 0',
    },
    // Primary button
    primaryBtn: {
      display: 'block',
      width: 'calc(100% - 40px)',
      margin: '16px 20px 0',
      padding: '12px',
      borderRadius: '8px',
      border: 'none',
      color: '#fff',
      fontSize: '15px',
      fontWeight: '600',
      cursor: 'pointer',
      transition: 'background-color 0.15s ease',
    },
    primaryBtnDisabled: {
      opacity: 0.5,
      cursor: 'default',
    },
    secondaryBtn: {
      display: 'block',
      width: 'calc(100% - 40px)',
      margin: '12px 20px 0',
      padding: '10px',
      borderRadius: '8px',
      border: '2px solid',
      background: '#fff',
      fontSize: '14px',
      fontWeight: '600',
      cursor: 'pointer',
      textAlign: 'center',
    },
    // Back link
    backLink: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '4px',
      padding: '8px 20px',
      background: 'none',
      border: 'none',
      cursor: 'pointer',
      fontSize: '13px',
      color: '#666',
      fontWeight: '500',
    },
    // Summary badge
    summaryBadge: {
      margin: '0 20px 16px',
      padding: '10px 14px',
      borderRadius: '8px',
      background: '#f8f9fa',
      fontSize: '13px',
      fontWeight: '500',
      color: '#333',
      textAlign: 'center',
    },
    // Form
    form: {
      padding: '0 20px',
    },
    formRow: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: '10px',
      marginBottom: '10px',
    },
    formGroup: {
      marginBottom: '10px',
    },
    formLabel: {
      display: 'block',
      fontSize: '12px',
      fontWeight: '600',
      color: '#555',
      marginBottom: '4px',
    },
    input: {
      width: '100%',
      padding: '10px 12px',
      borderRadius: '8px',
      border: '1px solid #ddd',
      fontSize: '14px',
      outline: 'none',
      transition: 'border-color 0.15s',
      boxSizing: 'border-box',
    },
    inputError: {
      borderColor: '#dc2626',
    },
    textarea: {
      width: '100%',
      padding: '10px 12px',
      borderRadius: '8px',
      border: '1px solid #ddd',
      fontSize: '14px',
      outline: 'none',
      resize: 'vertical',
      fontFamily: 'inherit',
      boxSizing: 'border-box',
    },
    fieldError: {
      fontSize: '11px',
      color: '#dc2626',
      marginTop: '2px',
    },
    // Confirmation
    confirmContainer: {
      padding: '24px 20px',
      textAlign: 'center',
    },
    checkCircle: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: '56px',
      height: '56px',
      borderRadius: '50%',
      border: '3px solid',
      marginBottom: '12px',
    },
    confirmTitle: {
      margin: '0 0 4px',
      fontSize: '18px',
      fontWeight: '700',
    },
    confirmSubtitle: {
      margin: '0 0 16px',
      fontSize: '13px',
      color: '#666',
    },
    confirmDetails: {
      background: '#f8f9fa',
      borderRadius: '8px',
      padding: '14px 16px',
      marginBottom: '4px',
      textAlign: 'left',
    },
    confirmRow: {
      display: 'flex',
      justifyContent: 'space-between',
      padding: '4px 0',
      fontSize: '13px',
    },
    confirmLabel: {
      color: '#666',
      fontWeight: '500',
    },
    confirmValue: {
      fontWeight: '600',
      color: '#1a1a1a',
    },
    // Error
    errorContainer: {
      padding: '40px 20px',
      textAlign: 'center',
    },
    errorText: {
      color: '#666',
      marginTop: '12px',
      fontSize: '14px',
    },
    errorBanner: {
      margin: '8px 20px',
      padding: '10px 14px',
      borderRadius: '8px',
      background: '#fef2f2',
      color: '#dc2626',
      fontSize: '13px',
    },
    // Footer
    footer: {
      padding: '12px 20px 16px',
      textAlign: 'center',
      borderTop: '1px solid #f0f0f0',
      marginTop: '16px',
    },
    footerLink: {
      fontSize: '11px',
      color: '#999',
      textDecoration: 'none',
    },
  };
}
