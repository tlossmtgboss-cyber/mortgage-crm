/**
 * DocumentViewer
 *
 * Displays documents (PDF/images) in the review modal.
 * Uses iframe for PDFs and img for images.
 */

import React, { useState, useRef, useEffect } from 'react';
import './DocumentViewer.css';

const DocumentViewer = ({
  documentUrl,
  mimeType,
  fileName,
}) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [zoom, setZoom] = useState(100);
  const [rotation, setRotation] = useState(0);
  const containerRef = useRef(null);

  const isPdf = mimeType?.includes('pdf') || fileName?.toLowerCase().endsWith('.pdf');
  const isImage = mimeType?.startsWith('image/') ||
    /\.(jpg|jpeg|png|gif|webp|bmp|tiff?)$/i.test(fileName || '');

  useEffect(() => {
    setLoading(true);
    setError(null);
  }, [documentUrl]);

  const handleLoad = () => {
    setLoading(false);
  };

  const handleError = () => {
    setLoading(false);
    setError('Failed to load document');
  };

  const handleZoomIn = () => {
    setZoom(prev => Math.min(prev + 25, 200));
  };

  const handleZoomOut = () => {
    setZoom(prev => Math.max(prev - 25, 50));
  };

  const handleRotate = () => {
    setRotation(prev => (prev + 90) % 360);
  };

  const handleReset = () => {
    setZoom(100);
    setRotation(0);
  };

  if (!documentUrl) {
    return (
      <div className="document-viewer-empty">
        <p>No document to display</p>
      </div>
    );
  }

  return (
    <div className="document-viewer" ref={containerRef}>
      {/* Toolbar */}
      <div className="viewer-toolbar">
        <div className="toolbar-left">
          <span className="file-name" title={fileName}>
            {fileName || 'Document'}
          </span>
        </div>
        <div className="toolbar-center">
          <button
            className="toolbar-btn"
            onClick={handleZoomOut}
            disabled={zoom <= 50}
            title="Zoom Out"
          >
            −
          </button>
          <span className="zoom-level">{zoom}%</span>
          <button
            className="toolbar-btn"
            onClick={handleZoomIn}
            disabled={zoom >= 200}
            title="Zoom In"
          >
            +
          </button>
          {isImage && (
            <button
              className="toolbar-btn"
              onClick={handleRotate}
              title="Rotate"
            >
              ⟳
            </button>
          )}
          <button
            className="toolbar-btn"
            onClick={handleReset}
            title="Reset View"
          >
            ↺
          </button>
        </div>
        <div className="toolbar-right">
          <a
            href={documentUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="toolbar-btn"
            title="Open in New Tab"
          >
            ↗
          </a>
        </div>
      </div>

      {/* Document Content */}
      <div className="viewer-content">
        {loading && (
          <div className="viewer-loading">
            <div className="spinner" />
            <p>Loading document...</p>
          </div>
        )}

        {error && (
          <div className="viewer-error">
            <p>{error}</p>
            <a href={documentUrl} target="_blank" rel="noopener noreferrer">
              Open in new tab
            </a>
          </div>
        )}

        {isPdf && (
          <iframe
            src={`${documentUrl}#view=FitH`}
            title={fileName || 'Document'}
            className="pdf-viewer"
            onLoad={handleLoad}
            onError={handleError}
            style={{
              transform: `scale(${zoom / 100})`,
              transformOrigin: 'top left',
              width: `${10000 / zoom}%`,
              height: `${10000 / zoom}%`,
            }}
          />
        )}

        {isImage && !isPdf && (
          <div
            className="image-container"
            style={{
              transform: `scale(${zoom / 100}) rotate(${rotation}deg)`,
            }}
          >
            <img
              src={documentUrl}
              alt={fileName || 'Document'}
              onLoad={handleLoad}
              onError={handleError}
              draggable={false}
            />
          </div>
        )}

        {!isPdf && !isImage && (
          <div className="unsupported-format">
            <p>Preview not available for this file type</p>
            <p className="mime-type">{mimeType}</p>
            <a
              href={documentUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="download-link"
            >
              Download File
            </a>
          </div>
        )}
      </div>
    </div>
  );
};

export default DocumentViewer;
