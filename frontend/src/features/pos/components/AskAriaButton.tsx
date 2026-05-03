/**
 * AskAriaButton — the prominent CTA that opens the Aria slide-over panel.
 *
 * Used in three places:
 *   - In the sidebar's Loan File card
 *   - Below the assigned loan officer card
 *   - As a floating action button (use the FloatingAskAriaButton variant)
 */
import React from 'react';

export interface AskAriaButtonProps {
  onClick: () => void;
  variant?: 'sidebar' | 'floating';
  subtitle?: string;
}

export const AskAriaButton: React.FC<AskAriaButtonProps> = ({
  onClick,
  variant = 'sidebar',
  subtitle = 'Instant answers, anytime',
}) => {
  if (variant === 'floating') {
    return (
      <button
        type="button"
        className="aria-fab"
        onClick={onClick}
        aria-label="Ask Aria"
      >
        <SparkIcon size={18} />
        <span className="aria-fab__label">Ask Aria</span>
      </button>
    );
  }

  return (
    <button type="button" className="ask-aria-btn" onClick={onClick}>
      <span className="ask-aria-btn__icon">
        <SparkIcon size={16} />
      </span>
      <span className="ask-aria-btn__text">
        <span className="ask-aria-btn__title">Ask Aria a question</span>
        <span className="ask-aria-btn__sub">{subtitle}</span>
      </span>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <polyline points="9 18 15 12 9 6" />
      </svg>
    </button>
  );
};

const SparkIcon: React.FC<{ size?: number }> = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
    <path
      d="M12 2L13.8 8.2L20 10L13.8 11.8L12 18L10.2 11.8L4 10L10.2 8.2Z"
      fill="currentColor"
    />
    <path
      d="M19 14L19.8 16.2L22 17L19.8 17.8L19 20L18.2 17.8L16 17L18.2 16.2Z"
      fill="currentColor"
      opacity="0.6"
    />
  </svg>
);
