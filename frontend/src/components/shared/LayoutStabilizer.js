import React, { useEffect, useRef, useState } from 'react';

/**
 * LayoutStabilizer - A wrapper component that prevents layout shifts during async content loading.
 *
 * Usage:
 * ```jsx
 * <LayoutStabilizer isLoading={loading} minHeight="100vh">
 *   {loading ? <YourSkeleton /> : <YourContent />}
 * </LayoutStabilizer>
 * ```
 *
 * Or wrap the entire page:
 * ```jsx
 * <LayoutStabilizer>
 *   <YourPageContent />
 * </LayoutStabilizer>
 * ```
 *
 * @param {Object} props
 * @param {React.ReactNode} props.children - Content to render
 * @param {boolean} props.isLoading - Whether content is loading (triggers stabilization on change)
 * @param {string} props.minHeight - Minimum height for the container (default: 'calc(100vh - 60px)')
 * @param {string} props.className - Additional CSS classes
 */
const LayoutStabilizer = ({
  children,
  isLoading = false,
  minHeight = 'calc(100vh - 60px)',
  className = '',
}) => {
  const containerRef = useRef(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    // Reset ready state when loading changes
    setIsReady(false);

    if (!containerRef.current) return;

    // Multi-phase stabilization for maximum compatibility
    const stabilize = () => {
      if (containerRef.current) {
        // Force synchronous reflow
        void containerRef.current.offsetHeight;

        // Dispatch resize for responsive components
        window.dispatchEvent(new Event('resize'));
      }
    };

    // Phase 1: Immediate stabilization
    stabilize();

    // Phase 2: After micro-task queue
    const timer1 = setTimeout(stabilize, 0);

    // Phase 3: After first paint
    const timer2 = setTimeout(stabilize, 50);

    // Phase 4: After potential async children mount
    const timer3 = setTimeout(stabilize, 100);

    // Phase 5: Final stabilization + ready state
    const timer4 = setTimeout(() => {
      stabilize();
      setIsReady(true);
    }, 250);

    // Use double RAF for maximum browser compatibility
    let rafId;
    if (!isLoading) {
      rafId = requestAnimationFrame(() => {
        requestAnimationFrame(stabilize);
      });
    }

    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      clearTimeout(timer4);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [isLoading]);

  // Observe content changes for dynamic content
  useEffect(() => {
    if (!containerRef.current || typeof ResizeObserver === 'undefined') return;

    const observer = new ResizeObserver(() => {
      // Force reflow when content size changes
      if (containerRef.current) {
        void containerRef.current.offsetHeight;
      }
    });

    observer.observe(containerRef.current);

    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={containerRef}
      className={`layout-stable ${isReady && !isLoading ? 'loaded' : ''} ${className}`.trim()}
      style={{
        minHeight,
        opacity: isLoading || !isReady ? undefined : 1,
      }}
    >
      {children}
    </div>
  );
};

export default LayoutStabilizer;
