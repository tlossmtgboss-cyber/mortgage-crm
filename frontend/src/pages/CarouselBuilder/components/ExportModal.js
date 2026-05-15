/**
 * Export Modal
 *
 * Modal for exporting carousel slides as images.
 * Supports PNG/JPG format, quality settings, and ZIP download.
 */

import React, { useState, useRef, useCallback } from 'react';
import { useCarouselBuilder, ASPECT_RATIO_SIZES } from '../CarouselBuilderContext';
import {
  exportSlideToImage,
  downloadImage,
  downloadAsZip,
} from '../utils/exportCarousel';

export default function ExportModal({ open, onClose }) {
  const { currentProject, slides } = useCarouselBuilder();

  const [format, setFormat] = useState('png');
  const [quality, setQuality] = useState(90);
  const [scale, setScale] = useState(2);
  const [exporting, setExporting] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [exportedImages, setExportedImages] = useState([]);
  const [error, setError] = useState(null);

  const renderContainerRef = useRef(null);

  const dimensions = ASPECT_RATIO_SIZES[currentProject?.aspect_ratio] || { width: 1080, height: 1080 };

  const handleExport = useCallback(async () => {
    if (!slides.length) return;

    setExporting(true);
    setError(null);
    setExportedImages([]);
    setProgress({ current: 0, total: slides.length });

    try {
      // Create a hidden container for rendering slides at full size
      const container = document.createElement('div');
      container.style.position = 'fixed';
      container.style.left = '-9999px';
      container.style.top = '0';
      container.style.width = `${dimensions.width}px`;
      container.style.height = `${dimensions.height}px`;
      container.style.overflow = 'hidden';
      document.body.appendChild(container);
      renderContainerRef.current = container;

      const images = [];

      for (let i = 0; i < slides.length; i++) {
        setProgress({ current: i, total: slides.length });

        const slide = slides[i];

        // Build background styles (sanitize all CSS values to prevent injection)
        let backgroundStyle = '';
        if (slide.background_type === 'gradient' && slide.background_gradient) {
          const angle = parseInt(slide.background_gradient.angle, 10) || 135;
          const colors = (slide.background_gradient.colors || ['#1F3D2E', '#2D7A52'])
            .map(c => sanitizeCSSValue(c));
          backgroundStyle = `background: linear-gradient(${angle}deg, ${colors.join(', ')});`;
        } else if (slide.background_type === 'image' && slide.background_image_url) {
          const safeUrl = sanitizeCSSUrl(slide.background_image_url);
          backgroundStyle = safeUrl
            ? `background-image: url(${safeUrl}); background-size: cover; background-position: center;`
            : `background-color: #1F3D2E;`;
        } else {
          backgroundStyle = `background-color: ${sanitizeCSSValue(slide.background_color) || '#1F3D2E'};`;
        }

        // Sanitize text color
        const textColor = sanitizeCSSValue(slide.custom_styles?.textColor) || '#ffffff';

        // Create slide HTML
        const slideHtml = `
          <div style="
            width: ${dimensions.width}px;
            height: ${dimensions.height}px;
            ${backgroundStyle}
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            padding: 8%;
            box-sizing: border-box;
            font-family: Inter, -apple-system, sans-serif;
          ">
            ${slide.title ? `
              <div style="
                font-size: 48px;
                font-weight: bold;
                color: ${textColor};
                text-align: center;
                margin-bottom: 16px;
                word-wrap: break-word;
                max-width: 90%;
              ">${escapeHtml(slide.title)}</div>
            ` : ''}
            ${slide.subtitle ? `
              <div style="
                font-size: 24px;
                font-weight: 500;
                color: ${textColor};
                opacity: 0.9;
                text-align: center;
                margin-bottom: 12px;
                word-wrap: break-word;
                max-width: 90%;
              ">${escapeHtml(slide.subtitle)}</div>
            ` : ''}
            ${slide.body_text ? `
              <div style="
                font-size: 18px;
                color: ${textColor};
                opacity: 0.85;
                text-align: center;
                line-height: 1.5;
                word-wrap: break-word;
                max-width: 85%;
              ">${escapeHtml(slide.body_text)}</div>
            ` : ''}
          </div>
        `;

        container.innerHTML = slideHtml;
        const slideElement = container.firstElementChild;

        // Wait for any images to load
        await new Promise(resolve => setTimeout(resolve, 100));

        // Export the slide
        const dataUrl = await exportSlideToImage(slideElement, {
          format,
          quality: quality / 100,
          scale,
        });

        images.push(dataUrl);
      }

      setProgress({ current: slides.length, total: slides.length });
      setExportedImages(images);

      // Clean up
      if (renderContainerRef.current) {
        document.body.removeChild(renderContainerRef.current);
        renderContainerRef.current = null;
      }

    } catch (err) {
      console.error('Export failed:', err);
      setError('Export failed. Please try again.');
    } finally {
      setExporting(false);
    }
  }, [slides, dimensions, format, quality, scale]);

  const handleDownloadAll = async () => {
    if (exportedImages.length === 0) return;

    const projectName = currentProject?.name?.replace(/[^a-z0-9]/gi, '_') || 'carousel';
    await downloadAsZip(exportedImages, projectName, format);
  };

  const handleDownloadSingle = (index) => {
    const projectName = currentProject?.name?.replace(/[^a-z0-9]/gi, '_') || 'carousel';
    downloadImage(exportedImages[index], `${projectName}_slide_${index + 1}.${format}`);
  };

  const handleClose = () => {
    setExportedImages([]);
    setProgress({ current: 0, total: 0 });
    setError(null);
    onClose();
  };

  if (!open) return null;

  return (
    <div className="carousel-modal-overlay" onClick={handleClose}>
      <div className="carousel-modal carousel-export-modal" onClick={e => e.stopPropagation()}>
        <div className="carousel-modal-header">
          <h2>Export Carousel</h2>
          <button className="carousel-modal-close" onClick={handleClose}>&times;</button>
        </div>

        <div className="carousel-modal-body">
          {exportedImages.length === 0 ? (
            <>
              {/* Export Settings */}
              <div className="carousel-form-group">
                <label>Format</label>
                <div className="carousel-button-group">
                  <button
                    type="button"
                    className={`carousel-toggle-btn ${format === 'png' ? 'active' : ''}`}
                    onClick={() => setFormat('png')}
                  >
                    PNG
                  </button>
                  <button
                    type="button"
                    className={`carousel-toggle-btn ${format === 'jpg' ? 'active' : ''}`}
                    onClick={() => setFormat('jpg')}
                  >
                    JPG
                  </button>
                </div>
              </div>

              {format === 'jpg' && (
                <div className="carousel-form-group">
                  <label>Quality: {quality}%</label>
                  <input
                    type="range"
                    min="50"
                    max="100"
                    value={quality}
                    onChange={(e) => setQuality(parseInt(e.target.value))}
                  />
                </div>
              )}

              <div className="carousel-form-group">
                <label>Resolution</label>
                <select value={scale} onChange={(e) => setScale(parseInt(e.target.value))}>
                  <option value={1}>1x ({dimensions.width}x{dimensions.height})</option>
                  <option value={2}>2x ({dimensions.width * 2}x{dimensions.height * 2})</option>
                  <option value={3}>3x ({dimensions.width * 3}x{dimensions.height * 3})</option>
                </select>
              </div>

              <div className="carousel-export-summary">
                <p>{slides.length} slide{slides.length !== 1 ? 's' : ''} will be exported</p>
                <p className="carousel-export-size">
                  Final size: {dimensions.width * scale} x {dimensions.height * scale} pixels
                </p>
              </div>

              {error && (
                <div className="carousel-export-error">
                  {error}
                </div>
              )}

              {exporting && (
                <div className="carousel-export-progress">
                  <div className="carousel-progress-bar">
                    <div
                      className="carousel-progress-fill"
                      style={{ width: `${(progress.current / progress.total) * 100}%` }}
                    />
                  </div>
                  <p>Exporting slide {progress.current + 1} of {progress.total}...</p>
                </div>
              )}
            </>
          ) : (
            <>
              {/* Export Results */}
              <div className="carousel-export-success">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
                  <path d="M22 4L12 14.01l-3-3" />
                </svg>
                <h3>Export Complete!</h3>
                <p>{exportedImages.length} slide{exportedImages.length !== 1 ? 's' : ''} exported successfully</p>
              </div>

              <div className="carousel-export-previews">
                {exportedImages.map((dataUrl, index) => (
                  <div key={index} className="carousel-export-preview-item">
                    <img src={dataUrl} alt={`Slide ${index + 1}`} />
                    <button
                      className="btn-secondary btn-sm"
                      onClick={() => handleDownloadSingle(index)}
                    >
                      Download
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="carousel-modal-footer">
          <button type="button" className="btn-secondary" onClick={handleClose}>
            {exportedImages.length > 0 ? 'Close' : 'Cancel'}
          </button>
          {exportedImages.length === 0 ? (
            <button
              type="button"
              className="btn-primary"
              onClick={handleExport}
              disabled={exporting || slides.length === 0}
            >
              {exporting ? 'Exporting...' : 'Export'}
            </button>
          ) : (
            <button
              type="button"
              className="btn-primary"
              onClick={handleDownloadAll}
            >
              Download All (ZIP)
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Sanitize a CSS value to prevent CSS injection.
 * Strips characters that could break out of a CSS property value context.
 */
function sanitizeCSSValue(value) {
  if (!value) return '';
  // Remove characters that can break out of CSS context: ; { } < > " '
  return String(value).replace(/[;{}<>"'\\]/g, '');
}

/**
 * Sanitize a URL for use in CSS url().
 * Only allows http:, https:, and data: (for blob URLs) protocols.
 */
function sanitizeCSSUrl(url) {
  if (!url) return '';
  const trimmed = String(url).trim();
  // Only allow safe protocols
  if (!/^(https?:|data:image\/)/i.test(trimmed)) return '';
  // Remove characters that could break out of url() context
  return trimmed.replace(/[)"'\\;{}]/g, '');
}
