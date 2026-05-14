/**
 * Frontend Sanitization Utilities
 * ================================
 * XSS prevention for user-generated content displayed in React components.
 *
 * Uses DOMPurify for robust HTML sanitization.
 *
 * Usage:
 *   import { sanitizeHTML, sanitizeText, sanitizeURL } from '../utils/sanitize';
 *
 *   // For rich text content (descriptions, comments with formatting)
 *   <div dangerouslySetInnerHTML={{ __html: sanitizeHTML(userContent) }} />
 *
 *   // For plain text (titles, names)
 *   <span>{sanitizeText(userName)}</span>
 *
 *   // For URLs (links, images)
 *   <a href={sanitizeURL(userUrl)}>Link</a>
 */

import React from 'react';
import DOMPurify from 'dompurify';

// Configure DOMPurify defaults
const ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'b', 'i', 'ul', 'ol', 'li', 'a', 'span'];
const ALLOWED_ATTR = ['href', 'title', 'class'];

// Register DOMPurify hooks at module level to avoid race conditions
DOMPurify.addHook('afterSanitizeAttributes', (node: Element) => {
  if (node.tagName === 'A') {
    node.setAttribute('rel', 'noopener noreferrer');
    const href = node.getAttribute('href');
    if (href && (href.startsWith('http://') || href.startsWith('https://'))) {
      node.setAttribute('target', '_blank');
    }
  }
});

export interface SanitizeHTMLOptions {
  allowedTags?: string[];
  allowedAttr?: string[];
  ALLOW_DATA_ATTR?: boolean;
  [key: string]: unknown;
}

/**
 * Sanitize HTML content - allows basic formatting tags
 * Use for rich text descriptions, comments with formatting
 */
export const sanitizeHTML = (dirty: string | null | undefined, options: SanitizeHTMLOptions = {}): string => {
  if (!dirty) return '';

  const config = {
    ALLOWED_TAGS: options.allowedTags || ALLOWED_TAGS,
    ALLOWED_ATTR: options.allowedAttr || ALLOWED_ATTR,
    ALLOW_DATA_ATTR: false,
    ...options
  };

  return DOMPurify.sanitize(dirty, config);
};

/**
 * Sanitize text - removes ALL HTML tags
 * Use for plain text fields: titles, names, labels
 */
export const sanitizeText = (dirty: string | null | undefined, maxLength: number = 1000): string => {
  if (!dirty) return '';

  // Remove all HTML tags
  const clean = DOMPurify.sanitize(dirty, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] });

  // Decode HTML entities
  const textarea = document.createElement('textarea');
  textarea.innerHTML = clean;
  const decoded = textarea.value;

  // Truncate if needed
  return decoded.substring(0, maxLength).trim();
};

/**
 * Sanitize URL - validates and cleans URLs
 * Prevents javascript:, data:, vbscript: URLs
 */
export const sanitizeURL = (
  url: string | null | undefined,
  allowedProtocols: string[] = ['http:', 'https:', 'mailto:']
): string | null => {
  if (!url) return null;

  try {
    // Trim and decode
    const trimmed = url.trim();

    // Block dangerous protocols
    const lowerUrl = trimmed.toLowerCase();
    const dangerousProtocols = ['javascript:', 'data:', 'vbscript:', 'file:'];
    if (dangerousProtocols.some(proto => lowerUrl.startsWith(proto))) {
      console.warn('Blocked dangerous URL:', url);
      return null;
    }

    // Parse URL to validate
    const parsed = new URL(trimmed, window.location.origin);

    // Check protocol
    if (!allowedProtocols.includes(parsed.protocol)) {
      console.warn('Blocked URL with disallowed protocol:', parsed.protocol);
      return null;
    }

    return trimmed;
  } catch (e) {
    // Invalid URL
    console.warn('Invalid URL:', url);
    return null;
  }
};

/**
 * Sanitize filename - removes path traversal and special chars
 */
export const sanitizeFilename = (filename: string | null | undefined): string => {
  if (!filename) return 'unnamed';

  // Remove path components
  let clean = filename.split(/[/\\]/).pop() || 'unnamed';

  // Remove dangerous characters
  clean = clean.replace(/[^a-zA-Z0-9._-]/g, '_');

  // Prevent hidden files
  clean = clean.replace(/^\.+/, '');

  // Limit length
  if (clean.length > 100) {
    const ext = clean.lastIndexOf('.');
    if (ext > 0) {
      clean = clean.substring(0, 90) + clean.substring(ext);
    } else {
      clean = clean.substring(0, 100);
    }
  }

  return clean || 'unnamed';
};

/**
 * Escape text for safe display in React
 * Alternative to sanitizeText when you need to preserve special chars for display
 */
export const escapeForDisplay = (text: string | null | undefined): string => {
  if (!text) return '';

  const escapeMap: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#x27;',
  };

  return text.replace(/[&<>"']/g, char => escapeMap[char]);
};

/**
 * Create a safe HTML renderer component
 * Wraps dangerouslySetInnerHTML with automatic sanitization
 *
 * Usage:
 *   <SafeHTML html={userContent} />
 *   <SafeHTML html={userContent} allowedTags={['p', 'br']} />
 */
export interface SafeHTMLProps extends React.HTMLAttributes<HTMLDivElement> {
  html: string | null | undefined;
  allowedTags?: string[];
  allowedAttr?: string[];
}

export const SafeHTML: React.FC<SafeHTMLProps> = ({ html, allowedTags, allowedAttr, className, ...props }) => {
  const sanitized = sanitizeHTML(html, { allowedTags, allowedAttr });

  return (
    <div
      className={className}
      dangerouslySetInnerHTML={{ __html: sanitized }}
      {...props}
    />
  );
};

export default {
  sanitizeHTML,
  sanitizeText,
  sanitizeURL,
  sanitizeFilename,
  escapeForDisplay,
  SafeHTML
};
