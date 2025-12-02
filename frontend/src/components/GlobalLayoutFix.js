import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * Global layout fix component that ensures proper page rendering.
 * Watches for route changes and DOM mutations to force layout recalculation.
 * This provides a safety net for all pages, especially those with async content.
 */
const GlobalLayoutFix = () => {
  const location = useLocation();

  useEffect(() => {
    const recalculateLayout = () => {
      // Force browser to recalculate layout
      window.dispatchEvent(new Event('resize'));

      // Ensure body allows scrolling
      document.body.style.overflow = 'auto';
      document.body.style.minHeight = '100vh';

      // Ensure root element doesn't constrain height
      const root = document.getElementById('root');
      if (root) {
        root.style.minHeight = '100vh';
        root.style.height = 'auto';
      }

      // Find and fix any app-main containers
      const appMain = document.querySelector('.app-main');
      if (appMain) {
        appMain.style.minHeight = 'auto';
        appMain.style.overflow = 'visible';
      }
    };

    // Run recalculation at multiple intervals to catch all loading stages
    const delays = [0, 50, 100, 200, 500, 1000];
    const timeouts = delays.map(delay =>
      setTimeout(recalculateLayout, delay)
    );

    // Watch for DOM changes that might affect layout
    const observer = new MutationObserver(() => {
      requestAnimationFrame(recalculateLayout);
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['style', 'class']
    });

    // Also run on images/iframes load which can change layout
    const handleLoad = () => recalculateLayout();
    window.addEventListener('load', handleLoad);

    return () => {
      timeouts.forEach(clearTimeout);
      observer.disconnect();
      window.removeEventListener('load', handleLoad);
    };
  }, [location.pathname]);

  // This component doesn't render anything
  return null;
};

export default GlobalLayoutFix;
