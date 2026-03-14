import React from 'react';
import './EmptyState.css';

/**
 * Pre-built variant configurations for common calendar empty states.
 */
const VARIANTS = {
  'no-appointments': {
    icon: 'fa-calendar',
    title: 'No appointments scheduled',
    description: 'Your schedule is clear. Time to follow up on leads!',
    tone: 'default',
  },
  'no-tasks': {
    icon: 'fa-clipboard-check',
    title: 'All caught up!',
    description: 'You have no pending tasks. Great job staying on top of things.',
    tone: 'success',
  },
  'no-results': {
    icon: 'fa-search',
    title: 'No results found',
    description: 'Try adjusting your search or filters to find what you are looking for.',
    tone: 'default',
  },
  'error': {
    icon: 'fa-exclamation-triangle',
    title: 'Something went wrong',
    description: 'We could not load this section. Please try again.',
    tone: 'error',
  },
};

/**
 * Map of icon names to Font Awesome class names.
 * Accepts either a bare name ("calendar") or an FA class ("fa-calendar").
 */
function resolveIconClass(icon) {
  if (!icon) return 'fas fa-info-circle';
  // Already a full FA class (e.g. "fa-calendar-check")
  if (icon.startsWith('fa-')) return `fas ${icon}`;
  // Bare name shorthand
  const shorthand = {
    calendar: 'fas fa-calendar',
    clipboard: 'fas fa-clipboard-check',
    search: 'fas fa-search',
    warning: 'fas fa-exclamation-triangle',
    error: 'fas fa-exclamation-triangle',
    info: 'fas fa-info-circle',
    check: 'fas fa-check-circle',
    empty: 'fas fa-inbox',
  };
  return shorthand[icon] || `fas fa-${icon}`;
}

/**
 * EmptyState -- Reusable empty-state display for calendar sections with icon, text, and optional CTAs.
 *
 * Supports pre-built variants ('no-appointments', 'no-tasks', 'no-results', 'error')
 * or fully custom props. Explicit props override variant defaults.
 *
 * Used in: Calendar, CalendarSettings, and anywhere empty/error states are needed
 *
 * @param {Object} props
 * @param {string} [props.variant] - Pre-built variant key ('no-appointments'|'no-tasks'|'no-results'|'error')
 * @param {string} [props.icon] - Icon name or FA class (e.g. 'calendar', 'fa-search'). Overrides variant icon.
 * @param {string} [props.title] - Heading text. Overrides variant title.
 * @param {string} [props.description] - Body text. Overrides variant description.
 * @param {{label: string, onClick: Function}} [props.action] - Primary CTA button
 * @param {{label: string, onClick: Function}} [props.secondaryAction] - Secondary CTA button
 * @param {string} [props.className=''] - Additional CSS class names on the container
 * @param {React.ReactNode} [props.children] - Custom content rendered below the description
 * @returns {React.ReactElement}
 *
 * @example
 * <EmptyState variant="no-appointments" />
 *
 * @example
 * <EmptyState
 *   icon="calendar"
 *   title="No appointments today"
 *   description="Your schedule is clear."
 *   action={{ label: 'View Leads', onClick: () => navigate('/leads') }}
 * />
 */
function EmptyState({
  variant,
  icon,
  title,
  description,
  action,
  secondaryAction,
  className = '',
  children,
}) {
  // Merge variant defaults with explicit props (explicit wins)
  const base = variant ? VARIANTS[variant] || {} : {};
  const resolvedIcon = icon || base.icon || 'info';
  const resolvedTitle = title || base.title || '';
  const resolvedDescription = description || base.description || '';
  const tone = base.tone || 'default';

  const toneClass =
    tone === 'error'
      ? 'cal-empty-container--error'
      : tone === 'success'
      ? 'cal-empty-container--success'
      : '';

  return (
    <div
      className={`cal-empty-container ${toneClass} ${className}`.trim()}
      role="status"
      aria-label={resolvedTitle || 'Empty state'}
    >
      <div className="cal-empty-icon" aria-hidden="true">
        <i className={resolveIconClass(resolvedIcon)} />
      </div>

      {resolvedTitle && (
        <h3 className="cal-empty-title">{resolvedTitle}</h3>
      )}

      {resolvedDescription && (
        <p className="cal-empty-description">{resolvedDescription}</p>
      )}

      {children}

      {(action || secondaryAction) && (
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center' }}>
          {action && (
            <button
              className="cal-empty-action"
              onClick={action.onClick}
              type="button"
              aria-label={action.label}
            >
              {action.label}
            </button>
          )}
          {secondaryAction && (
            <button
              className="cal-empty-action cal-empty-action--secondary"
              onClick={secondaryAction.onClick}
              type="button"
              aria-label={secondaryAction.label}
            >
              {secondaryAction.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default EmptyState;
