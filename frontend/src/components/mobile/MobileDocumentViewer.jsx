import React, { useState, useRef, useCallback, useEffect } from 'react';
import './MobileDocumentViewer.css';

/**
 * MobileDocumentViewer
 *
 * Full-screen mobile document viewer with pinch-to-zoom, pan, double-tap zoom,
 * multi-page navigation, and auto-hiding controls.
 *
 * Props:
 * @param {boolean}  isOpen       - Whether the viewer is visible
 * @param {Function} onClose      - Called when the user closes the viewer
 * @param {string}   url          - URL of the document to display
 * @param {string}   fileName     - Display name for the document
 * @param {string}   fileType     - MIME type or extension (e.g. "application/pdf", "image/jpeg", "pdf", "jpg")
 * @param {Array}    pages        - Optional array of image URLs for multi-page documents (pre-rendered pages)
 * @param {Function} onShare      - Optional callback for the Share action
 * @param {Function} onDownload   - Optional callback for the Download action
 * @param {Function} onPrint      - Optional callback for the Print action
 */

// ── Helpers ──────────────────────────────────────────────────────────────────

const ZOOM_MIN = 1;
const ZOOM_MAX = 5;
const DOUBLE_TAP_ZOOM = 2;
const DOUBLE_TAP_THRESHOLD_MS = 300;
const CONTROLS_HIDE_DELAY_MS = 3000;

function getDistance(t1, t2) {
  const dx = t1.clientX - t2.clientX;
  const dy = t1.clientY - t2.clientY;
  return Math.sqrt(dx * dx + dy * dy);
}

function getMidpoint(t1, t2) {
  return {
    x: (t1.clientX + t2.clientX) / 2,
    y: (t1.clientY + t2.clientY) / 2,
  };
}

function clamp(val, min, max) {
  return Math.min(Math.max(val, min), max);
}

function isPdf(type) {
  if (!type) return false;
  const lower = type.toLowerCase();
  return lower === 'pdf' || lower === 'application/pdf' || lower.endsWith('.pdf');
}

function isImage(type) {
  if (!type) return false;
  const lower = type.toLowerCase();
  const imageTypes = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif', 'bmp', 'svg'];
  if (imageTypes.some(t => lower === t || lower === `image/${t}` || lower.endsWith(`.${t}`))) {
    return true;
  }
  return lower.startsWith('image/');
}


// ── Icons (inline SVG to avoid dependencies) ────────────────────────────────

const CloseIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const ShareIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
    <polyline points="16 6 12 2 8 6" />
    <line x1="12" y1="2" x2="12" y2="15" />
  </svg>
);

const DownloadIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

const PrintIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="6 9 6 2 18 2 18 9" />
    <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
    <rect x="6" y="14" width="12" height="8" />
  </svg>
);

const RotateIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="1 4 1 10 7 10" />
    <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
  </svg>
);

const ChevronLeftIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="15 18 9 12 15 6" />
  </svg>
);

const ChevronRightIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="9 18 15 12 9 6" />
  </svg>
);

const ErrorIcon = () => (
  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);


// ── Component ────────────────────────────────────────────────────────────────

export default function MobileDocumentViewer({
  isOpen,
  onClose,
  url,
  fileName = 'Document',
  fileType = '',
  pages = null,
  onShare,
  onDownload,
  onPrint,
}) {
  // --- State ---
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(0);
  const [rotation, setRotation] = useState(0);
  const [controlsVisible, setControlsVisible] = useState(true);
  const [zoomIndicator, setZoomIndicator] = useState(null);
  const [closing, setClosing] = useState(false);

  // Transform state stored in ref for perf (avoids re-render per touch frame)
  const transformRef = useRef({ scale: 1, x: 0, y: 0 });
  const [, forceRender] = useState(0);

  // Refs
  const viewportRef = useRef(null);
  const canvasRef = useRef(null);
  const contentSizeRef = useRef({ width: 0, height: 0 });
  const touchStateRef = useRef(null);
  const lastTapRef = useRef(0);
  const controlsTimerRef = useRef(null);
  const zoomTimerRef = useRef(null);
  const prevBodyOverflow = useRef('');

  // Total pages
  const totalPages = pages ? pages.length : 1;
  const isMultiPage = totalPages > 1;
  const useDots = totalPages <= 10;

  // Current page URL
  const currentUrl = pages ? pages[currentPage] : url;

  // Determine rendering mode
  const renderAsPdf = !pages && isPdf(fileType);
  const renderAsImage = isImage(fileType) || (pages && pages.length > 0);

  // --- Lock body scroll ---
  useEffect(() => {
    if (isOpen) {
      prevBodyOverflow.current = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.body.style.overflow = prevBodyOverflow.current;
    };
  }, [isOpen]);

  // --- Reset state when document changes ---
  useEffect(() => {
    if (isOpen) {
      setLoading(true);
      setError(null);
      setCurrentPage(0);
      setRotation(0);
      setControlsVisible(true);
      setClosing(false);
      transformRef.current = { scale: 1, x: 0, y: 0 };
      applyTransform();
    }
  }, [isOpen, url]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- Auto-hide controls ---
  const resetControlsTimer = useCallback(() => {
    setControlsVisible(true);
    if (controlsTimerRef.current) clearTimeout(controlsTimerRef.current);
    controlsTimerRef.current = setTimeout(() => {
      // Only hide if zoomed in, otherwise keep visible
      if (transformRef.current.scale > 1) {
        setControlsVisible(false);
      }
    }, CONTROLS_HIDE_DELAY_MS);
  }, []);

  useEffect(() => {
    if (isOpen) resetControlsTimer();
    return () => {
      if (controlsTimerRef.current) clearTimeout(controlsTimerRef.current);
    };
  }, [isOpen, resetControlsTimer]);

  // --- Apply CSS transform ---
  const applyTransform = useCallback(() => {
    if (!canvasRef.current) return;
    const { scale, x, y } = transformRef.current;
    canvasRef.current.style.transform =
      `translate(${x}px, ${y}px) scale(${scale}) rotate(${rotation}deg)`;
  }, [rotation]);

  // Re-apply transform when rotation changes
  useEffect(() => {
    applyTransform();
  }, [rotation, applyTransform]);

  // --- Constrain pan so document stays in view ---
  const constrainPan = useCallback((x, y, scale) => {
    const viewport = viewportRef.current;
    if (!viewport) return { x, y };

    const vw = viewport.clientWidth;
    const vh = viewport.clientHeight;
    const cw = contentSizeRef.current.width * scale;
    const ch = contentSizeRef.current.height * scale;

    if (scale <= 1) return { x: 0, y: 0 };

    // Allow panning to edges but not beyond
    const minX = Math.min(0, vw - cw);
    const maxX = Math.max(0, vw - cw);
    const minY = Math.min(0, vh - ch);
    const maxY = Math.max(0, vh - ch);

    // Center if content smaller than viewport along an axis
    const cx = cw <= vw ? (vw - cw) / 2 : clamp(x, minX, maxX);
    const cy = ch <= vh ? (vh - ch) / 2 : clamp(y, minY, maxY);

    return { x: cx, y: cy };
  }, []);

  // --- Flash zoom indicator ---
  const showZoomLevel = useCallback((scale) => {
    setZoomIndicator(`${Math.round(scale * 100)}%`);
    if (zoomTimerRef.current) clearTimeout(zoomTimerRef.current);
    zoomTimerRef.current = setTimeout(() => setZoomIndicator(null), 800);
  }, []);

  // --- Touch Handlers ---

  const handleTouchStart = useCallback((e) => {
    // Prevent default to stop iOS scroll / bounce
    e.preventDefault();
    resetControlsTimer();

    const touches = e.touches;
    const t = transformRef.current;

    if (touches.length === 2) {
      // Pinch start
      const dist = getDistance(touches[0], touches[1]);
      const mid = getMidpoint(touches[0], touches[1]);
      touchStateRef.current = {
        type: 'pinch',
        initialDistance: dist,
        initialScale: t.scale,
        midpoint: mid,
        lastX: t.x,
        lastY: t.y,
      };
    } else if (touches.length === 1) {
      // Potential pan or double-tap
      const now = Date.now();
      const timeSinceLastTap = now - lastTapRef.current;

      touchStateRef.current = {
        type: 'pan',
        startX: touches[0].clientX,
        startY: touches[0].clientY,
        lastX: t.x,
        lastY: t.y,
        moved: false,
        tapTime: now,
        isDoubleTap: timeSinceLastTap < DOUBLE_TAP_THRESHOLD_MS,
      };
    }
  }, [resetControlsTimer]);

  const handleTouchMove = useCallback((e) => {
    e.preventDefault();
    const ts = touchStateRef.current;
    if (!ts) return;

    const touches = e.touches;

    if (ts.type === 'pinch' && touches.length === 2) {
      const dist = getDistance(touches[0], touches[1]);
      const mid = getMidpoint(touches[0], touches[1]);
      let newScale = clamp(ts.initialScale * (dist / ts.initialDistance), ZOOM_MIN, ZOOM_MAX);

      // Calculate pan offset to keep the pinch midpoint stable
      const viewport = viewportRef.current;
      if (viewport) {
        const rect = viewport.getBoundingClientRect();
        const pivotX = mid.x - rect.left;
        const pivotY = mid.y - rect.top;

        // Scale around the midpoint
        const scaleRatio = newScale / ts.initialScale;
        let newX = pivotX - (pivotX - ts.lastX) * scaleRatio;
        let newY = pivotY - (pivotY - ts.lastY) * scaleRatio;

        const constrained = constrainPan(newX, newY, newScale);
        transformRef.current = { scale: newScale, x: constrained.x, y: constrained.y };
      } else {
        transformRef.current.scale = newScale;
      }

      applyTransform();
      showZoomLevel(newScale);
    } else if (ts.type === 'pan' && touches.length === 1) {
      const dx = touches[0].clientX - ts.startX;
      const dy = touches[0].clientY - ts.startY;

      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
        ts.moved = true;
      }

      const t = transformRef.current;

      if (t.scale > 1) {
        // Panning zoomed content
        let newX = ts.lastX + dx;
        let newY = ts.lastY + dy;
        const constrained = constrainPan(newX, newY, t.scale);
        transformRef.current = { ...t, x: constrained.x, y: constrained.y };
        applyTransform();
      } else if (isMultiPage && Math.abs(dx) > Math.abs(dy)) {
        // Horizontal swipe for page nav (visual feedback)
        transformRef.current = { ...t, x: dx * 0.3 };
        applyTransform();
      }
    }
  }, [applyTransform, constrainPan, isMultiPage, showZoomLevel]);

  const handleTouchEnd = useCallback((e) => {
    e.preventDefault();
    const ts = touchStateRef.current;
    if (!ts) return;

    const t = transformRef.current;

    if (ts.type === 'pan' && !ts.moved) {
      // It was a tap
      if (ts.isDoubleTap) {
        // Double-tap: toggle zoom
        lastTapRef.current = 0;
        const viewport = viewportRef.current;

        if (t.scale > 1) {
          // Zoom out to 1x
          transformRef.current = { scale: 1, x: 0, y: 0 };
          showZoomLevel(1);
        } else if (viewport) {
          // Zoom in to 2x centered on tap point
          const rect = viewport.getBoundingClientRect();
          const tapX = ts.startX - rect.left;
          const tapY = ts.startY - rect.top;
          const newScale = DOUBLE_TAP_ZOOM;

          let newX = tapX - tapX * newScale;
          let newY = tapY - tapY * newScale;
          const constrained = constrainPan(newX, newY, newScale);
          transformRef.current = { scale: newScale, x: constrained.x, y: constrained.y };
          showZoomLevel(newScale);
        }
        applyTransform();
      } else {
        // Single tap: toggle controls
        lastTapRef.current = ts.tapTime;
        setControlsVisible(prev => !prev);
      }
    } else if (ts.type === 'pan' && ts.moved && t.scale <= 1 && isMultiPage) {
      // Horizontal swipe -> page change
      const dx = (e.changedTouches?.[0]?.clientX ?? ts.startX) - ts.startX;
      if (dx < -50 && currentPage < totalPages - 1) {
        setCurrentPage(prev => prev + 1);
        resetTransform();
      } else if (dx > 50 && currentPage > 0) {
        setCurrentPage(prev => prev - 1);
        resetTransform();
      } else {
        // Snap back
        transformRef.current = { scale: 1, x: 0, y: 0 };
        applyTransform();
      }
    }

    // If pinch ended and zoomed to near 1x, snap to exactly 1x
    if (ts.type === 'pinch' && t.scale < 1.05) {
      transformRef.current = { scale: 1, x: 0, y: 0 };
      applyTransform();
    }

    touchStateRef.current = null;
  }, [applyTransform, constrainPan, currentPage, isMultiPage, showZoomLevel, totalPages]);

  // --- Utility ---
  const resetTransform = useCallback(() => {
    transformRef.current = { scale: 1, x: 0, y: 0 };
    applyTransform();
  }, [applyTransform]);

  // --- Image load handler ---
  const handleContentLoad = useCallback((e) => {
    setLoading(false);
    setError(null);
    // Store natural content size for pan constraining
    if (e.target.tagName === 'IMG') {
      const viewport = viewportRef.current;
      if (viewport) {
        // Use displayed size, not natural size
        const vw = viewport.clientWidth;
        const vRatio = vw / e.target.naturalWidth;
        contentSizeRef.current = {
          width: vw,
          height: e.target.naturalHeight * vRatio,
        };
      }
    }
  }, []);

  const handleContentError = useCallback(() => {
    setLoading(false);
    setError('Unable to load document');
  }, []);

  // --- Actions ---
  const handleClose = useCallback(() => {
    setClosing(true);
    setTimeout(() => {
      onClose();
    }, 200);
  }, [onClose]);

  const handleRotate = useCallback(() => {
    setRotation(prev => (prev + 90) % 360);
    resetControlsTimer();
  }, [resetControlsTimer]);

  const handleShare = useCallback(() => {
    if (onShare) {
      onShare({ url: currentUrl, fileName, fileType });
    } else if (navigator.share) {
      navigator.share({ title: fileName, url: currentUrl }).catch(() => {});
    }
    resetControlsTimer();
  }, [onShare, currentUrl, fileName, fileType, resetControlsTimer]);

  const handleDownload = useCallback(() => {
    if (onDownload) {
      onDownload({ url: currentUrl, fileName, fileType });
    } else {
      const a = document.createElement('a');
      a.href = currentUrl;
      a.download = fileName;
      a.click();
    }
    resetControlsTimer();
  }, [onDownload, currentUrl, fileName, fileType, resetControlsTimer]);

  const handlePrint = useCallback(() => {
    if (onPrint) {
      onPrint({ url: currentUrl, fileName, fileType });
    } else {
      // Open in new window for printing
      const win = window.open(currentUrl, '_blank');
      if (win) {
        win.addEventListener('load', () => win.print());
      }
    }
    resetControlsTimer();
  }, [onPrint, currentUrl, fileName, fileType, resetControlsTimer]);

  const handleRetry = useCallback(() => {
    setError(null);
    setLoading(true);
    // Force re-render by toggling a key
    forceRender(prev => prev + 1);
  }, []);

  // --- Page navigation ---
  const goToPage = useCallback((pageIndex) => {
    setCurrentPage(clamp(pageIndex, 0, totalPages - 1));
    resetTransform();
    setLoading(true);
    setError(null);
    resetControlsTimer();
  }, [totalPages, resetTransform, resetControlsTimer]);

  // --- Keyboard support for page nav ---
  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e) => {
      if (e.key === 'Escape') handleClose();
      if (e.key === 'ArrowLeft' && isMultiPage) goToPage(currentPage - 1);
      if (e.key === 'ArrowRight' && isMultiPage) goToPage(currentPage + 1);
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isOpen, handleClose, goToPage, currentPage, isMultiPage]);

  // --- PDF iframe load ---
  const handleIframeLoad = useCallback(() => {
    setLoading(false);
    setError(null);
    const viewport = viewportRef.current;
    if (viewport) {
      contentSizeRef.current = {
        width: viewport.clientWidth,
        height: viewport.clientHeight,
      };
    }
  }, []);

  // --- Don't render when closed ---
  if (!isOpen) return null;

  // --- Render ---
  return (
    <div
      className={`mdv-overlay${closing ? ' mdv-overlay--closing' : ''}`}
      role="dialog"
      aria-modal="true"
      aria-label={`Document viewer: ${fileName}`}
    >
      {/* Header */}
      <div className={`mdv-header${controlsVisible ? '' : ' mdv-header--hidden'}`}>
        <button className="mdv-header__btn" onClick={handleClose} aria-label="Close viewer">
          <CloseIcon />
        </button>
        <div className="mdv-header__info">
          <div className="mdv-header__title">{fileName}</div>
          {isMultiPage && (
            <div className="mdv-header__subtitle">
              Page {currentPage + 1} of {totalPages}
            </div>
          )}
        </div>
        {/* Spacer to balance the close button */}
        <div style={{ width: 40 }} />
      </div>

      {/* Document Viewport */}
      <div
        ref={viewportRef}
        className="mdv-viewport"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Loading */}
        {loading && !error && (
          <div className="mdv-loading">
            <div className="mdv-spinner" />
            <span>Loading document...</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mdv-error">
            <div className="mdv-error__icon">
              <ErrorIcon />
            </div>
            <div className="mdv-error__title">Unable to load document</div>
            <div className="mdv-error__message">{error}</div>
            <button className="mdv-error__retry" onClick={handleRetry}>
              Try Again
            </button>
          </div>
        )}

        {/* Content Canvas */}
        {!error && (
          <div
            ref={canvasRef}
            className="mdv-canvas"
            style={{
              width: '100%',
              height: renderAsPdf ? '100%' : 'auto',
              opacity: loading ? 0 : 1,
              transition: 'opacity 0.2s ease',
            }}
          >
            {renderAsPdf ? (
              <iframe
                src={`${currentUrl}#toolbar=0&navpanes=0`}
                title={fileName}
                onLoad={handleIframeLoad}
                onError={handleContentError}
                style={{ width: '100%', height: '100%' }}
              />
            ) : (
              <img
                src={currentUrl}
                alt={`${fileName}${isMultiPage ? ` - Page ${currentPage + 1}` : ''}`}
                onLoad={handleContentLoad}
                onError={handleContentError}
                draggable={false}
              />
            )}
          </div>
        )}

        {/* Zoom Indicator */}
        <div className={`mdv-zoom-indicator${zoomIndicator ? ' mdv-zoom-indicator--visible' : ''}`}>
          {zoomIndicator}
        </div>
      </div>

      {/* Page Navigation */}
      {isMultiPage && !error && (
        useDots ? (
          <div className={`mdv-page-dots${controlsVisible ? '' : ' mdv-page-dots--hidden'}`}>
            {Array.from({ length: totalPages }, (_, i) => (
              <button
                key={i}
                className={`mdv-page-dot${i === currentPage ? ' mdv-page-dot--active' : ''}`}
                onClick={() => goToPage(i)}
                aria-label={`Go to page ${i + 1}`}
              />
            ))}
          </div>
        ) : (
          <div className={`mdv-page-nav${controlsVisible ? '' : ' mdv-page-nav--hidden'}`}>
            <button
              className="mdv-page-nav__btn"
              onClick={() => goToPage(currentPage - 1)}
              disabled={currentPage === 0}
              aria-label="Previous page"
            >
              <ChevronLeftIcon />
            </button>
            <span className="mdv-page-nav__label">
              {currentPage + 1} / {totalPages}
            </span>
            <button
              className="mdv-page-nav__btn"
              onClick={() => goToPage(currentPage + 1)}
              disabled={currentPage === totalPages - 1}
              aria-label="Next page"
            >
              <ChevronRightIcon />
            </button>
          </div>
        )
      )}

      {/* Action Bar */}
      <div className={`mdv-actions${controlsVisible ? '' : ' mdv-actions--hidden'}`}>
        <button className="mdv-action-btn" onClick={handleShare} aria-label="Share document">
          <span className="mdv-action-btn__icon"><ShareIcon /></span>
          <span className="mdv-action-btn__label">Share</span>
        </button>
        <button className="mdv-action-btn" onClick={handleDownload} aria-label="Download document">
          <span className="mdv-action-btn__icon"><DownloadIcon /></span>
          <span className="mdv-action-btn__label">Download</span>
        </button>
        <button className="mdv-action-btn" onClick={handlePrint} aria-label="Print document">
          <span className="mdv-action-btn__icon"><PrintIcon /></span>
          <span className="mdv-action-btn__label">Print</span>
        </button>
        <button className="mdv-action-btn" onClick={handleRotate} aria-label="Rotate document">
          <span className="mdv-action-btn__icon"><RotateIcon /></span>
          <span className="mdv-action-btn__label">Rotate</span>
        </button>
      </div>
    </div>
  );
}
