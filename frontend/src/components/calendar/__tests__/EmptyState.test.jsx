import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('../EmptyState.css', () => ({}));

import EmptyState from '../EmptyState';

// ============================================================================
// Basic rendering
// ============================================================================

describe('EmptyState', () => {
  describe('Rendering title and description', () => {
    it('renders title when provided', () => {
      render(<EmptyState title="No data available" />);
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });

    it('renders description when provided', () => {
      render(<EmptyState description="Please try again later." />);
      expect(screen.getByText('Please try again later.')).toBeInTheDocument();
    });

    it('renders both title and description', () => {
      render(<EmptyState title="Empty" description="Nothing here yet" />);
      expect(screen.getByText('Empty')).toBeInTheDocument();
      expect(screen.getByText('Nothing here yet')).toBeInTheDocument();
    });

    it('renders with role="status"', () => {
      render(<EmptyState title="Test" />);
      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('uses title as aria-label', () => {
      render(<EmptyState title="No appointments" />);
      expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'No appointments');
    });

    it('falls back to "Empty state" aria-label when no title', () => {
      render(<EmptyState />);
      expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'Empty state');
    });
  });

  // =========================================================================
  // Action button
  // =========================================================================

  describe('Action button', () => {
    it('renders action button when provided', () => {
      const onClick = vi.fn();
      render(
        <EmptyState
          title="No results"
          action={{ label: 'Add New', onClick }}
        />
      );

      const button = screen.getByRole('button', { name: 'Add New' });
      expect(button).toBeInTheDocument();
      expect(button).toHaveTextContent('Add New');
    });

    it('calls action.onClick when button is clicked', () => {
      const onClick = vi.fn();
      render(
        <EmptyState
          title="No results"
          action={{ label: 'Add New', onClick }}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: 'Add New' }));
      expect(onClick).toHaveBeenCalledTimes(1);
    });

    it('does not render action button when not provided', () => {
      render(<EmptyState title="No results" />);
      expect(screen.queryByRole('button')).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // Secondary action button
  // =========================================================================

  describe('Secondary action button', () => {
    it('renders secondary action when provided', () => {
      const primaryClick = vi.fn();
      const secondaryClick = vi.fn();
      render(
        <EmptyState
          title="No results"
          action={{ label: 'Primary', onClick: primaryClick }}
          secondaryAction={{ label: 'Secondary', onClick: secondaryClick }}
        />
      );

      expect(screen.getByRole('button', { name: 'Primary' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Secondary' })).toBeInTheDocument();
    });

    it('calls secondaryAction.onClick when clicked', () => {
      const secondaryClick = vi.fn();
      render(
        <EmptyState
          title="No results"
          secondaryAction={{ label: 'Go Back', onClick: secondaryClick }}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: 'Go Back' }));
      expect(secondaryClick).toHaveBeenCalledTimes(1);
    });

    it('secondary button has the --secondary CSS class', () => {
      render(
        <EmptyState
          title="No results"
          secondaryAction={{ label: 'Cancel', onClick: vi.fn() }}
        />
      );

      const btn = screen.getByRole('button', { name: 'Cancel' });
      expect(btn.classList.contains('cal-empty-action--secondary')).toBe(true);
    });

    it('renders only secondary action without primary action', () => {
      render(
        <EmptyState
          title="No results"
          secondaryAction={{ label: 'Other', onClick: vi.fn() }}
        />
      );

      expect(screen.getByRole('button', { name: 'Other' })).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Icon rendering
  // =========================================================================

  describe('Icon rendering', () => {
    it('renders custom icon using FA class prefix', () => {
      const { container } = render(<EmptyState icon="fa-calendar-check" title="Custom Icon" />);
      const iconEl = container.querySelector('.cal-empty-icon i');
      expect(iconEl).toBeTruthy();
      expect(iconEl.className).toContain('fa-calendar-check');
    });

    it('renders shorthand icon name', () => {
      const { container } = render(<EmptyState icon="calendar" title="Shorthand" />);
      const iconEl = container.querySelector('.cal-empty-icon i');
      expect(iconEl).toBeTruthy();
      expect(iconEl.className).toContain('fa-calendar');
    });

    it('renders default icon when none specified', () => {
      const { container } = render(<EmptyState title="Default Icon" />);
      const iconEl = container.querySelector('.cal-empty-icon i');
      expect(iconEl).toBeTruthy();
      expect(iconEl.className).toContain('fa-info-circle');
    });

    it('icon container has aria-hidden="true"', () => {
      const { container } = render(<EmptyState icon="search" title="Test" />);
      const iconContainer = container.querySelector('.cal-empty-icon');
      expect(iconContainer.getAttribute('aria-hidden')).toBe('true');
    });

    it('resolves bare icon name to fas fa- prefixed class', () => {
      const { container } = render(<EmptyState icon="search" title="Search" />);
      const iconEl = container.querySelector('.cal-empty-icon i');
      expect(iconEl.className).toBe('fas fa-search');
    });

    it('resolves fa- prefixed icon to fas prefix', () => {
      const { container } = render(<EmptyState icon="fa-exclamation-triangle" title="Warning" />);
      const iconEl = container.querySelector('.cal-empty-icon i');
      expect(iconEl.className).toBe('fas fa-exclamation-triangle');
    });
  });

  // =========================================================================
  // Variants
  // =========================================================================

  describe('Variants', () => {
    it('renders no-appointments variant with correct title and description', () => {
      render(<EmptyState variant="no-appointments" />);
      expect(screen.getByText('No appointments scheduled')).toBeInTheDocument();
      expect(screen.getByText(/Your schedule is clear/)).toBeInTheDocument();
    });

    it('renders no-tasks variant', () => {
      render(<EmptyState variant="no-tasks" />);
      expect(screen.getByText('All caught up!')).toBeInTheDocument();
    });

    it('renders no-results variant', () => {
      render(<EmptyState variant="no-results" />);
      expect(screen.getByText('No results found')).toBeInTheDocument();
    });

    it('renders error variant', () => {
      render(<EmptyState variant="error" />);
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('error variant has error tone CSS class', () => {
      const { container } = render(<EmptyState variant="error" />);
      const root = container.querySelector('.cal-empty-container');
      expect(root.classList.contains('cal-empty-container--error')).toBe(true);
    });

    it('no-tasks variant has success tone CSS class', () => {
      const { container } = render(<EmptyState variant="no-tasks" />);
      const root = container.querySelector('.cal-empty-container');
      expect(root.classList.contains('cal-empty-container--success')).toBe(true);
    });

    it('explicit props override variant defaults', () => {
      render(
        <EmptyState
          variant="no-appointments"
          title="Custom Title"
          description="Custom Description"
        />
      );
      expect(screen.getByText('Custom Title')).toBeInTheDocument();
      expect(screen.getByText('Custom Description')).toBeInTheDocument();
      expect(screen.queryByText('No appointments scheduled')).not.toBeInTheDocument();
    });

    it('handles unknown variant gracefully', () => {
      render(<EmptyState variant="nonexistent" title="Fallback" />);
      expect(screen.getByText('Fallback')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Custom className
  // =========================================================================

  describe('Custom className', () => {
    it('appends custom className to container', () => {
      const { container } = render(<EmptyState title="Test" className="my-custom-class" />);
      const root = container.querySelector('.cal-empty-container');
      expect(root.classList.contains('my-custom-class')).toBe(true);
    });

    it('default className is empty string (no extra whitespace issues)', () => {
      const { container } = render(<EmptyState title="Test" />);
      const root = container.querySelector('.cal-empty-container');
      // Should not have trailing spaces
      expect(root.className.endsWith(' ')).toBe(false);
    });
  });

  // =========================================================================
  // Children
  // =========================================================================

  describe('Children', () => {
    it('renders custom children content', () => {
      render(
        <EmptyState title="Test">
          <div data-testid="custom-child">Custom Content</div>
        </EmptyState>
      );
      expect(screen.getByTestId('custom-child')).toBeInTheDocument();
      expect(screen.getByText('Custom Content')).toBeInTheDocument();
    });

    it('renders children alongside title, description, and actions', () => {
      render(
        <EmptyState
          title="Title"
          description="Desc"
          action={{ label: 'Act', onClick: vi.fn() }}
        >
          <span>Extra</span>
        </EmptyState>
      );
      expect(screen.getByText('Title')).toBeInTheDocument();
      expect(screen.getByText('Desc')).toBeInTheDocument();
      expect(screen.getByText('Extra')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Act' })).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Edge cases
  // =========================================================================

  describe('Edge cases', () => {
    it('renders without any props', () => {
      const { container } = render(<EmptyState />);
      expect(container.querySelector('.cal-empty-container')).toBeTruthy();
    });

    it('does not render title h3 when title is empty string', () => {
      const { container } = render(<EmptyState title="" />);
      expect(container.querySelector('.cal-empty-title')).not.toBeTruthy();
    });

    it('does not render description p when description is empty string', () => {
      const { container } = render(<EmptyState description="" />);
      expect(container.querySelector('.cal-empty-description')).not.toBeTruthy();
    });

    it('does not render button container when neither action is provided', () => {
      const { container } = render(<EmptyState title="Test" />);
      // No buttons should be rendered
      expect(container.querySelectorAll('button')).toHaveLength(0);
    });
  });
});
