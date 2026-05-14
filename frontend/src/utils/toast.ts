/**
 * Perennia AI - Toast Notification Utility
 *
 * Simple toast notification system.
 * Can be replaced with react-hot-toast or react-toastify if needed.
 */

import DOMPurify from 'dompurify';

type ToastType = 'success' | 'error' | 'warning' | 'info' | 'loading';

export interface ToastOptions {
  duration?: number | null;
  icon?: string;
  allowDuplicate?: boolean;
}

export interface ToastHandle {
  id: string | null;
  dismiss: () => void;
  update: (newMessage: string) => void;
}

export interface ToastPromiseMessages<T> {
  loading?: string;
  success?: string | ((result: T) => string);
  error?: string | ((error: Error) => string);
}

interface ToastConfig {
  duration: number | null;
  icon: string;
  className: string;
  bgColor: string;
}

/**
 * Escape a string for safe insertion into HTML.
 * Uses the browser's own text encoding to neutralize any HTML/script content.
 */
function escapeHtml(str: string): string {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Toast container element
let toastContainer: HTMLDivElement | null = null;

// Deduplication: track recent messages to prevent spam
const recentMessages = new Map<string, number>();
const DEDUPE_WINDOW_MS = 2000; // Don't show same message within 2 seconds
const MAX_VISIBLE_TOASTS = 5; // Maximum toasts visible at once

/**
 * Toast configuration
 */
const CONFIG: Record<ToastType, ToastConfig> = {
  success: {
    duration: 3000,
    icon: '✅', // checkmark
    className: 'toast-success',
    bgColor: '#10B981',
  },
  error: {
    duration: 5000,
    icon: '❌', // X
    className: 'toast-error',
    bgColor: '#EF4444',
  },
  warning: {
    duration: 4000,
    icon: '⚠️', // warning
    className: 'toast-warning',
    bgColor: '#F59E0B',
  },
  info: {
    duration: 3000,
    icon: 'ℹ️', // info
    className: 'toast-info',
    bgColor: '#3B82F6',
  },
  loading: {
    duration: null, // Doesn't auto-dismiss
    icon: '⏳', // hourglass
    className: 'toast-loading',
    bgColor: '#6B7280',
  },
};

/**
 * Initialize toast container
 */
function initContainer(): HTMLDivElement {
  if (toastContainer) return toastContainer;

  // Create container
  toastContainer = document.createElement('div');
  toastContainer.id = 'toast-container';
  toastContainer.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 10000;
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-width: 400px;
  `;

  // Add styles
  const style = document.createElement('style');
  style.textContent = `
    .toast {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 14px 20px;
      border-radius: 8px;
      color: white;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 14px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      animation: toast-slide-in 0.3s ease-out;
      cursor: pointer;
      transition: opacity 0.2s, transform 0.2s;
    }

    .toast:hover {
      opacity: 0.95;
      transform: translateX(-2px);
    }

    .toast-icon {
      font-size: 18px;
      flex-shrink: 0;
    }

    .toast-message {
      flex: 1;
      line-height: 1.4;
    }

    .toast-close {
      background: none;
      border: none;
      color: white;
      font-size: 18px;
      cursor: pointer;
      opacity: 0.7;
      padding: 0 0 0 8px;
      margin: -4px -8px -4px 0;
    }

    .toast-close:hover {
      opacity: 1;
    }

    .toast-exiting {
      animation: toast-slide-out 0.2s ease-in forwards;
    }

    @keyframes toast-slide-in {
      from {
        transform: translateX(100%);
        opacity: 0;
      }
      to {
        transform: translateX(0);
        opacity: 1;
      }
    }

    @keyframes toast-slide-out {
      from {
        transform: translateX(0);
        opacity: 1;
      }
      to {
        transform: translateX(100%);
        opacity: 0;
      }
    }
  `;

  document.head.appendChild(style);
  document.body.appendChild(toastContainer);

  return toastContainer;
}

/**
 * Check if message was recently shown (deduplication)
 */
function isDuplicate(message: string, type: ToastType): boolean {
  const key = `${type}:${message}`;
  const lastShown = recentMessages.get(key);
  const now = Date.now();

  if (lastShown && (now - lastShown) < DEDUPE_WINDOW_MS) {
    return true; // Duplicate within window
  }

  // Update timestamp
  recentMessages.set(key, now);

  // Clean up old entries
  if (recentMessages.size > 50) {
    for (const [k, timestamp] of recentMessages) {
      if (now - timestamp > DEDUPE_WINDOW_MS * 2) {
        recentMessages.delete(k);
      }
    }
  }

  return false;
}

/**
 * Create and show a toast
 */
function createToast(message: string, type: ToastType = 'info', options: ToastOptions = {}): ToastHandle {
  // Skip duplicates (unless explicitly allowed)
  if (!options.allowDuplicate && isDuplicate(message, type)) {
    return { id: null, dismiss: () => {}, update: () => {} };
  }

  const container = initContainer();
  const config = CONFIG[type] || CONFIG.info;

  // Limit visible toasts - remove oldest if at max
  const existingToasts = container.querySelectorAll('.toast:not(.toast-exiting)');
  if (existingToasts.length >= MAX_VISIBLE_TOASTS) {
    const oldest = existingToasts[0];
    if (oldest) {
      oldest.classList.add('toast-exiting');
      setTimeout(() => oldest.remove(), 200);
    }
  }

  // Create toast element
  const toastEl = document.createElement('div');
  toastEl.className = `toast ${config.className}`;
  toastEl.style.backgroundColor = config.bgColor;

  // Generate unique ID
  const toastId = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  toastEl.id = toastId;

  // Build toast content safely using DOM APIs (no innerHTML with user data)
  const iconSpan = document.createElement('span');
  iconSpan.className = 'toast-icon';
  iconSpan.textContent = options.icon || config.icon;

  const messageSpan = document.createElement('span');
  messageSpan.className = 'toast-message';
  messageSpan.textContent = message;

  const closeBtn = document.createElement('button');
  closeBtn.className = 'toast-close';
  closeBtn.setAttribute('aria-label', 'Close');
  closeBtn.innerHTML = '&times;';

  toastEl.appendChild(iconSpan);
  toastEl.appendChild(messageSpan);
  toastEl.appendChild(closeBtn);

  // Close handler
  const dismiss = (): void => {
    toastEl.classList.add('toast-exiting');
    setTimeout(() => {
      if (toastEl.parentNode) {
        toastEl.parentNode.removeChild(toastEl);
      }
    }, 200);
  };

  closeBtn.addEventListener('click', (e: Event) => {
    e.stopPropagation();
    dismiss();
  });

  toastEl.addEventListener('click', (e: MouseEvent) => {
    // Don't dismiss if clicking a link — let the link navigate
    if ((e.target as HTMLElement).tagName === 'A') return;
    dismiss();
  });

  // Add to container
  container.appendChild(toastEl);

  // Auto-dismiss
  const duration = options.duration !== undefined ? options.duration : config.duration;
  if (duration) {
    setTimeout(dismiss, duration);
  }

  return {
    id: toastId,
    dismiss,
    update: (newMessage: string) => {
      const msgEl = toastEl.querySelector('.toast-message');
      if (msgEl) msgEl.textContent = newMessage;
    },
  };
}

/**
 * Toast API
 */
export const toast = {
  /**
   * Show success toast
   */
  success(message: string, options: ToastOptions = {}): ToastHandle {
    return createToast(message, 'success', options);
  },

  /**
   * Show error toast
   */
  error(message: string, options: ToastOptions = {}): ToastHandle {
    return createToast(message, 'error', { duration: 5000, ...options });
  },

  /**
   * Show warning toast
   */
  warning(message: string, options: ToastOptions = {}): ToastHandle {
    return createToast(message, 'warning', options);
  },

  /**
   * Show info toast
   */
  info(message: string, options: ToastOptions = {}): ToastHandle {
    return createToast(message, 'info', options);
  },

  /**
   * Show loading toast (doesn't auto-dismiss)
   */
  loading(message: string, options: ToastOptions = {}): ToastHandle {
    return createToast(message, 'loading', { duration: null, ...options });
  },

  /**
   * Show toast for a promise
   */
  async promise<T>(promise: Promise<T>, messages: ToastPromiseMessages<T> = {}): Promise<T> {
    const loadingToast = this.loading(messages.loading || 'Loading...');

    try {
      const result = await promise;
      loadingToast.dismiss();

      const successMsg = typeof messages.success === 'function'
        ? messages.success(result)
        : messages.success || 'Success!';
      this.success(successMsg);

      return result;
    } catch (error) {
      loadingToast.dismiss();

      const err = error as Error;
      const errorMsg = typeof messages.error === 'function'
        ? messages.error(err)
        : messages.error || err.message || 'An error occurred';
      this.error(errorMsg);

      throw error;
    }
  },

  /**
   * Show a toast with sanitized HTML content.
   * Use ONLY when you need formatting (bold, links, etc.) in the message.
   * The HTML is sanitized via DOMPurify before rendering.
   */
  html(htmlMessage: string, type: ToastType = 'info', options: ToastOptions = {}): ToastHandle {
    const result = createToast('', type, options);
    if (result.id) {
      const toastEl = document.getElementById(result.id);
      if (toastEl) {
        const msgEl = toastEl.querySelector('.toast-message');
        if (msgEl) {
          // Sanitize HTML: allow only safe formatting tags
          const clean = DOMPurify.sanitize(htmlMessage, {
            ALLOWED_TAGS: ['b', 'strong', 'i', 'em', 'a', 'br', 'span', 'code'],
            ALLOWED_ATTR: ['href', 'target', 'rel', 'class'],
          });
          msgEl.innerHTML = clean;
        }
      }
    }
    return result;
  },

  /**
   * Dismiss all toasts
   */
  dismissAll(): void {
    const container = document.getElementById('toast-container');
    if (container) {
      while (container.firstChild) {
        container.removeChild(container.firstChild);
      }
    }
  },
};

export { escapeHtml };
export default toast;
