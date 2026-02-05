import { Suspense } from 'react';

// Simple loading component
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
 * AuthLayout - Layout for authentication pages (login, register, etc.)
 * Minimal chrome with no navigation sidebar
 *
 * @param {Object} props
 * @param {React.ReactNode} props.children - Page content to render
 */
function AuthLayout({ children }) {
  return (
    <Suspense fallback={<PageLoader />}>
      {children}
    </Suspense>
  );
}

export default AuthLayout;
