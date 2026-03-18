import React, { Suspense } from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock Navigation component
vi.mock('../../components/Navigation', () => ({
  default: (props) => (
    <nav data-testid="navigation">
      {props.assistantOpen && <span data-testid="assistant-open" />}
      {props.coachOpen && <span data-testid="coach-open" />}
      {props.taskSidebarOpen && <span data-testid="task-sidebar-open" />}
      {props.taskCounts && <span data-testid="task-counts">{JSON.stringify(props.taskCounts)}</span>}
    </nav>
  ),
}));

// Mock CoachCorner component
vi.mock('../../components/CoachCorner', () => ({
  default: ({ isOpen, onClose }) =>
    isOpen ? (
      <div data-testid="coach-corner">
        <button onClick={onClose} data-testid="close-coach">Close Coach</button>
      </div>
    ) : null,
}));

// Mock CSS
vi.mock('../../components/Navigation.css', () => ({}));
vi.mock('../../components/CoachCorner.css', () => ({}));

import MainLayout, { PageLoader } from '../MainLayout';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderLayout(props = {}) {
  const defaultProps = {
    onToggleAssistant: vi.fn(),
    onToggleCoach: vi.fn(),
    onToggleTaskSidebar: vi.fn(),
    assistantOpen: false,
    coachOpen: false,
    taskSidebarOpen: false,
    taskCounts: {},
    showCoach: true,
  };

  return render(
    <MemoryRouter>
      <MainLayout {...defaultProps} {...props}>
        <div data-testid="page-content">Test Page Content</div>
      </MainLayout>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MainLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // =========================================================================
  // Structure
  // =========================================================================

  describe('Layout structure', () => {
    it('renders with app-layout class', () => {
      const { container } = renderLayout();
      expect(container.querySelector('.app-layout')).toBeInTheDocument();
    });

    it('renders the Navigation component', () => {
      renderLayout();
      expect(screen.getByTestId('navigation')).toBeInTheDocument();
    });

    it('renders main content area with app-main class', () => {
      const { container } = renderLayout();
      expect(container.querySelector('main.app-main')).toBeInTheDocument();
    });

    it('renders children inside main content area', () => {
      renderLayout();
      expect(screen.getByTestId('page-content')).toBeInTheDocument();
      expect(screen.getByText('Test Page Content')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // CSS class modifiers
  // =========================================================================

  describe('CSS class modifiers based on sidebar state', () => {
    it('adds with-assistant class when assistantOpen is true', () => {
      const { container } = renderLayout({ assistantOpen: true });
      const main = container.querySelector('main');
      expect(main).toHaveClass('with-assistant');
    });

    it('does not add with-assistant class when assistantOpen is false', () => {
      const { container } = renderLayout({ assistantOpen: false });
      const main = container.querySelector('main');
      expect(main).not.toHaveClass('with-assistant');
    });

    it('adds with-task-sidebar class when taskSidebarOpen is true', () => {
      const { container } = renderLayout({ taskSidebarOpen: true });
      const main = container.querySelector('main');
      expect(main).toHaveClass('with-task-sidebar');
    });

    it('does not add with-task-sidebar class when taskSidebarOpen is false', () => {
      const { container } = renderLayout({ taskSidebarOpen: false });
      const main = container.querySelector('main');
      expect(main).not.toHaveClass('with-task-sidebar');
    });

    it('adds both modifier classes when both sidebars are open', () => {
      const { container } = renderLayout({ assistantOpen: true, taskSidebarOpen: true });
      const main = container.querySelector('main');
      expect(main).toHaveClass('with-assistant');
      expect(main).toHaveClass('with-task-sidebar');
    });
  });

  // =========================================================================
  // Prop passing to Navigation
  // =========================================================================

  describe('Prop passing to Navigation', () => {
    it('passes assistantOpen to Navigation', () => {
      renderLayout({ assistantOpen: true });
      expect(screen.getByTestId('assistant-open')).toBeInTheDocument();
    });

    it('passes coachOpen to Navigation', () => {
      renderLayout({ coachOpen: true });
      expect(screen.getByTestId('coach-open')).toBeInTheDocument();
    });

    it('passes taskCounts to Navigation', () => {
      renderLayout({ taskCounts: { urgentTasks: 3, leads: 5 } });
      const countsEl = screen.getByTestId('task-counts');
      expect(countsEl.textContent).toContain('urgentTasks');
      expect(countsEl.textContent).toContain('3');
    });
  });

  // =========================================================================
  // CoachCorner visibility
  // =========================================================================

  describe('CoachCorner visibility', () => {
    it('shows CoachCorner when showCoach is true and coachOpen is true', () => {
      renderLayout({ showCoach: true, coachOpen: true });
      expect(screen.getByTestId('coach-corner')).toBeInTheDocument();
    });

    it('does not show CoachCorner when showCoach is false', () => {
      renderLayout({ showCoach: false, coachOpen: true });
      expect(screen.queryByTestId('coach-corner')).not.toBeInTheDocument();
    });

    it('does not show CoachCorner when coachOpen is false', () => {
      renderLayout({ showCoach: true, coachOpen: false });
      expect(screen.queryByTestId('coach-corner')).not.toBeInTheDocument();
    });

    it('defaults showCoach to true when not specified', () => {
      // Render without showCoach prop — it defaults to true
      const defaultProps = {
        onToggleAssistant: vi.fn(),
        onToggleCoach: vi.fn(),
        onToggleTaskSidebar: vi.fn(),
        assistantOpen: false,
        coachOpen: true,
        taskSidebarOpen: false,
        taskCounts: {},
        // showCoach intentionally omitted — should default to true
      };
      render(
        <MemoryRouter>
          <MainLayout {...defaultProps}>
            <div>content</div>
          </MainLayout>
        </MemoryRouter>
      );
      expect(screen.getByTestId('coach-corner')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Suspense fallback
  // =========================================================================

  describe('Suspense boundary', () => {
    it('wraps children in a Suspense boundary', () => {
      // Verify the component renders without throwing even with regular children
      // The Suspense boundary catches lazy-loaded component loading states
      renderLayout();
      expect(screen.getByTestId('page-content')).toBeInTheDocument();
    });
  });
});

// ===========================================================================
// PageLoader
// ===========================================================================

describe('PageLoader', () => {
  it('renders Loading... text', () => {
    render(<PageLoader />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('has centered flex layout', () => {
    const { container } = render(<PageLoader />);
    const div = container.firstChild;
    expect(div.style.display).toBe('flex');
    expect(div.style.justifyContent).toBe('center');
    expect(div.style.alignItems).toBe('center');
  });

  it('has full viewport height', () => {
    const { container } = render(<PageLoader />);
    const div = container.firstChild;
    expect(div.style.height).toBe('100vh');
  });
});

// ===========================================================================
// AuthLayout
// ===========================================================================

describe('AuthLayout', () => {
  let AuthLayout;

  beforeEach(async () => {
    const mod = await import('../AuthLayout');
    AuthLayout = mod.default;
  });

  it('renders children without navigation', () => {
    render(
      <AuthLayout>
        <div data-testid="auth-content">Login Form</div>
      </AuthLayout>
    );
    expect(screen.getByTestId('auth-content')).toBeInTheDocument();
    expect(screen.queryByTestId('navigation')).not.toBeInTheDocument();
  });

  it('wraps content in Suspense', () => {
    render(
      <AuthLayout>
        <div>Auth Content</div>
      </AuthLayout>
    );
    expect(screen.getByText('Auth Content')).toBeInTheDocument();
  });
});
