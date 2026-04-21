import { Suspense } from 'react';
import Navigation from '../components/Navigation';
import CoachCorner from '../components/CoachCorner';
import RouteErrorBoundary from '../components/RouteErrorBoundary';

// Simple loading component for lazy-loaded pages
const PageLoader = () => (
  <div style={{
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100vh',
    fontSize: '14px',
    color: '#666'
  }}>
    Loading...
  </div>
);

/**
 * MainLayout - Authenticated layout with sidebar navigation and header
 * Used for all protected routes that need the full app chrome
 *
 * @param {Object} props
 * @param {React.ReactNode} props.children - Page content to render
 * @param {Function} props.onToggleAssistant - Toggle AI assistant sidebar
 * @param {Function} props.onToggleCoach - Toggle coach corner
 * @param {Function} props.onToggleTaskSidebar - Toggle task sidebar
 * @param {boolean} props.assistantOpen - Whether AI assistant is open
 * @param {boolean} props.coachOpen - Whether coach corner is open
 * @param {boolean} props.taskSidebarOpen - Whether task sidebar is open
 * @param {Object} props.taskCounts - Task count badges for navigation
 * @param {boolean} props.showCoach - Whether to show coach corner (default: true)
 */
function MainLayout({
  children,
  onToggleAssistant,
  onToggleCoach,
  onToggleTaskSidebar,
  assistantOpen,
  coachOpen,
  taskSidebarOpen,
  taskCounts,
  showCoach = true,
}) {
  return (
    <div className="app-layout">
      <Navigation
        onToggleAssistant={onToggleAssistant}
        onToggleCoach={onToggleCoach}
        onToggleTaskSidebar={onToggleTaskSidebar}
        assistantOpen={assistantOpen}
        coachOpen={coachOpen}
        taskSidebarOpen={taskSidebarOpen}
        taskCounts={taskCounts}
      />
      <main className={`app-main ${assistantOpen ? 'with-assistant' : ''} ${taskSidebarOpen ? 'with-task-sidebar' : ''}`}>
        <RouteErrorBoundary>
          <Suspense fallback={<PageLoader />}>
            {children}
          </Suspense>
        </RouteErrorBoundary>
      </main>
      {showCoach && (
        <CoachCorner isOpen={coachOpen} onClose={() => onToggleCoach && onToggleCoach()} />
      )}
    </div>
  );
}

// Export PageLoader for use in routes
export { PageLoader };

export default MainLayout;
