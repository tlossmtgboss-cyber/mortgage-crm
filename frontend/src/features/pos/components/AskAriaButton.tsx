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
        <SparkIcon size={22} />
        <span className="aria-fab__label">Ask Aria</span>
      </button>
    );
  }

  return (
    <button type="button" className="ask-aria-btn" onClick={onClick}>
      <span className="ask-aria-btn__icon">
        <SparkIcon size={14} />
      </span>
      <span className="ask-aria-btn__text">
        <span className="ask-aria-btn__title">Ask Aria a question</span>
        <span className="ask-aria-btn__sub">{subtitle}</span>
      </span>
      <ChevronRightIcon />
    </button>
  );
};

const SparkIcon: React.FC<{ size?: number }> = ({ size = 14 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="currentColor"
    aria-hidden
  >
    <path d="M12 2L13.5 8.5 20 10 13.5 11.5 12 18 10.5 11.5 4 10 10.5 8.5z" />
  </svg>
);

const ChevronRightIcon: React.FC = () => (
  <svg
    width="13"
    height="13"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
  >
    <polyline points="9 18 15 12 9 6" />
  </svg>
);
