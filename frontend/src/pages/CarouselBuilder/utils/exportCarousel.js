/**
 * Carousel Export Utilities
 *
 * Functions for exporting carousel slides as images using html2canvas.
 */

import html2canvas from 'html2canvas';

/**
 * Export a single slide element to an image
 * @param {HTMLElement} slideElement - The DOM element to capture
 * @param {Object} options - Export options
 * @returns {Promise<string>} - Data URL of the exported image
 */
export async function exportSlideToImage(slideElement, options = {}) {
  const {
    format = 'png',
    quality = 0.9,
    scale = 2,
    backgroundColor = null,
  } = options;

  const canvas = await html2canvas(slideElement, {
    scale,
    backgroundColor,
    useCORS: true,
    allowTaint: false,
    logging: false,
    width: slideElement.offsetWidth,
    height: slideElement.offsetHeight,
  });

  const mimeType = format === 'jpg' ? 'image/jpeg' : 'image/png';
  return canvas.toDataURL(mimeType, quality);
}

/**
 * Export all slides to images
 * @param {HTMLElement[]} slideElements - Array of DOM elements
 * @param {Object} options - Export options
 * @param {Function} onProgress - Progress callback (index, total)
 * @returns {Promise<string[]>} - Array of data URLs
 */
export async function exportAllSlides(slideElements, options = {}, onProgress = null) {
  const images = [];

  for (let i = 0; i < slideElements.length; i++) {
    if (onProgress) {
      onProgress(i, slideElements.length);
    }

    const dataUrl = await exportSlideToImage(slideElements[i], options);
    images.push(dataUrl);
  }

  if (onProgress) {
    onProgress(slideElements.length, slideElements.length);
  }

  return images;
}

/**
 * Convert data URL to Blob
 * @param {string} dataUrl - Data URL string
 * @returns {Blob}
 */
export function dataUrlToBlob(dataUrl) {
  const parts = dataUrl.split(',');
  const mimeMatch = parts[0].match(/:(.*?);/);
  const mime = mimeMatch ? mimeMatch[1] : 'image/png';
  const bstr = atob(parts[1]);
  let n = bstr.length;
  const u8arr = new Uint8Array(n);

  while (n--) {
    u8arr[n] = bstr.charCodeAt(n);
  }

  return new Blob([u8arr], { type: mime });
}

/**
 * Download a single image
 * @param {string} dataUrl - Image data URL
 * @param {string} filename - Download filename
 */
export function downloadImage(dataUrl, filename) {
  const link = document.createElement('a');
  link.href = dataUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

/**
 * Download all slides as a ZIP file
 * @param {string[]} dataUrls - Array of image data URLs
 * @param {string} projectName - Name for the ZIP file
 * @param {string} format - Image format (png/jpg)
 */
export async function downloadAsZip(dataUrls, projectName, format = 'png') {
  // Dynamically import JSZip for bundling efficiency
  const JSZip = (await import('jszip')).default;

  const zip = new JSZip();
  const folder = zip.folder(projectName);

  dataUrls.forEach((dataUrl, index) => {
    const blob = dataUrlToBlob(dataUrl);
    const filename = `slide_${(index + 1).toString().padStart(2, '0')}.${format}`;
    folder.file(filename, blob);
  });

  const content = await zip.generateAsync({ type: 'blob' });

  const link = document.createElement('a');
  link.href = URL.createObjectURL(content);
  link.download = `${projectName}.zip`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
}

/**
 * Create a hidden render container for exporting slides
 * @param {number} width - Canvas width
 * @param {number} height - Canvas height
 * @returns {HTMLElement}
 */
export function createRenderContainer(width, height) {
  const container = document.createElement('div');
  container.style.position = 'fixed';
  container.style.left = '-9999px';
  container.style.top = '0';
  container.style.width = `${width}px`;
  container.style.height = `${height}px`;
  container.style.overflow = 'hidden';
  document.body.appendChild(container);
  return container;
}

/**
 * Remove the render container
 * @param {HTMLElement} container
 */
export function removeRenderContainer(container) {
  if (container && container.parentNode) {
    container.parentNode.removeChild(container);
  }
}
