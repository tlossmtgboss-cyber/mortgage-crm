import React, { useState, useRef, useEffect, useCallback } from 'react';

const CallIntelligenceSlidePanel = ({ onClose, ciSession }) => {
  const [isClosing, setIsClosing] = useState(false);
  const [dragOffset, setDragOffset] = useState(0);
  const panelRef = useRef(null);
  const dragStartY = useRef(0);
  const isDragging = useRef(false);

  // Close with animation
  const handleClose = useCallback(() => {
    setIsClosing(true);
    setTimeout(() => onClose(), 300);
  }, [onClose]);

  // Touch drag handlers for dismissal
  const handleTouchStart = (e) => {
    const touch = e.touches[0];
    dragStartY.current = touch.clientY;
    isDragging.current = true;
    setDragOffset(0);
  };

  const handleTouchMove = (e) => {
    if (!isDragging.current) return;
    const touch = e.touches[0];
    const diff = touch.clientY - dragStartY.current;
    if (diff > 0) { // Only allow dragging down
      setDragOffset(diff);
    }
  };

  const handleTouchEnd = () => {
    isDragging.current = false;
    if (dragOffset > 150) {
      // Dragged far enough — close
      handleClose();
    } else {
      // Snap back
      setDragOffset(0);
    }
  };

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') handleClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleClose]);

  // Lazy import MobileCallIntelligencePanel to avoid circular deps
  const [MobilePanel, setMobilePanel] = useState(null);
  useEffect(() => {
    import('../MobileCallIntelligencePanel')
      .then((mod) => setMobilePanel(() => mod.default))
      .catch((err) => {
        console.error('Failed to load MobileCallIntelligencePanel:', err);
      });
  }, []);

  const panelStyle = {
    position: 'fixed',
    bottom: 0,
    left: 0,
    right: 0,
    height: '80vh',
    background: '#0f1923',
    borderTopLeftRadius: '20px',
    borderTopRightRadius: '20px',
    zIndex: 1100,
    display: 'flex',
    flexDirection: 'column',
    transform: isClosing
      ? 'translateY(100%)'
      : `translateY(${dragOffset}px)`,
    transition: isDragging.current ? 'none' : 'transform 0.3s cubic-bezier(0.32, 0.72, 0, 1)',
    animation: !isClosing && dragOffset === 0 ? 'ci-slide-up 0.3s cubic-bezier(0.32, 0.72, 0, 1)' : undefined,
    boxShadow: '0 -8px 30px rgba(0, 0, 0, 0.5)',
    overflow: 'hidden',
  };

  const backdropStyle = {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'rgba(0, 0, 0, 0.5)',
    zIndex: 1099,
    opacity: isClosing ? 0 : 1 - (dragOffset / 300),
    transition: isClosing ? 'opacity 0.3s ease' : 'none',
    animation: !isClosing ? 'ci-fade-in 0.3s ease' : undefined,
  };

  return (
    <>
      <style>{`
        @keyframes ci-slide-up {
          from { transform: translateY(100%); }
          to { transform: translateY(0); }
        }
        @keyframes ci-fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes ci-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>

      {/* Backdrop */}
      <div style={backdropStyle} onClick={handleClose} />

      {/* Panel */}
      <div ref={panelRef} style={panelStyle} role="dialog" aria-label="Call Intelligence">
        {/* Drag handle */}
        <div
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          style={{
            padding: '12px 0 8px',
            display: 'flex',
            justifyContent: 'center',
            cursor: 'grab',
            flexShrink: 0,
          }}
        >
          <div style={{
            width: '40px',
            height: '4px',
            borderRadius: '2px',
            background: 'rgba(255, 255, 255, 0.3)',
          }} />
        </div>

        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 16px 12px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '18px' }}>&#129504;</span>
            <h2 style={{
              margin: 0,
              fontSize: '16px',
              fontWeight: '600',
              color: '#fff',
            }}>
              Call Intelligence
            </h2>
            {ciSession?.isActive && (
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '2px 8px',
                borderRadius: '12px',
                background: 'rgba(239, 68, 68, 0.2)',
                color: '#ef4444',
                fontSize: '11px',
                fontWeight: '600',
              }}>
                <span style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  background: '#ef4444',
                  animation: 'ci-pulse 1.5s infinite',
                }} />
                LIVE
              </span>
            )}
          </div>
          <button
            onClick={handleClose}
            aria-label="Close call intelligence panel"
            style={{
              background: 'rgba(255, 255, 255, 0.1)',
              border: 'none',
              borderRadius: '50%',
              width: '32px',
              height: '32px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              color: '#fff',
              fontSize: '16px',
            }}
          >
            &#10005;
          </button>
        </div>

        {/* Content — embedded MobileCallIntelligencePanel or loading */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          {MobilePanel ? (
            <MobilePanel
              onClose={handleClose}
              initialContext={{ source: 'aria_voice_app' }}
            />
          ) : (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: 'rgba(255, 255, 255, 0.5)',
            }}>
              Loading Call Intelligence...
            </div>
          )}
        </div>
      </div>
    </>
  );
};

export default CallIntelligenceSlidePanel;
