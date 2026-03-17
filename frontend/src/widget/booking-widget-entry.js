/**
 * Standalone entry point for the Perennia Booking Widget.
 *
 * This file is built as a separate bundle (no router, no full app shell)
 * and can be loaded on any third-party website via a script tag.
 *
 * Usage (script embed):
 *   <div id="perennia-booking"
 *        data-org="acme-mortgage"
 *        data-lo="john-smith"
 *        data-color="#1a73e8">
 *   </div>
 *   <script src="https://app.perenniaai.com/widget/booking.js" async></script>
 *
 * Usage (iframe embed):
 *   <iframe src="https://app.perenniaai.com/book/acme-mortgage/john-smith?embed=true"
 *     width="100%" height="600" frameborder="0"></iframe>
 *
 * Data attributes:
 *   data-org     (required) - Organization slug
 *   data-lo      (optional) - Loan officer slug
 *   data-color   (optional) - Primary accent color hex (e.g. "#1a73e8")
 *   data-type    (optional) - Default appointment type key (reserved for future use)
 *   data-api     (optional) - API base URL override (for self-hosted)
 */

import React from 'react';
import { createRoot } from 'react-dom/client';
import BookingWidget from '../components/calendar/BookingWidget';

// ============================================================================
// Auto-initialization on load
// ============================================================================

function initWidget() {
  // Find all widget mount points on the page
  const containers = document.querySelectorAll(
    '#perennia-booking, [data-perennia-booking]'
  );

  containers.forEach((container) => {
    // Skip if already initialized
    if (container.dataset.perenniaInitialized === 'true') return;
    container.dataset.perenniaInitialized = 'true';

    // Read configuration from data attributes
    const orgSlug = container.dataset.org || container.getAttribute('data-org');
    const loSlug = container.dataset.lo || container.getAttribute('data-lo');
    const color = container.dataset.color || container.getAttribute('data-color');
    const apiBase = container.dataset.api || container.getAttribute('data-api');

    if (!orgSlug) {
      console.warn('[Perennia Widget] Missing required data-org attribute on', container);
      return;
    }

    // Determine if we are in an iframe
    const isEmbedded = window.self !== window.top;

    // Create React root and render widget
    const root = createRoot(container);
    root.render(
      <BookingWidget
        orgSlug={orgSlug}
        loSlug={loSlug || undefined}
        accentColor={color || undefined}
        apiBase={apiBase || undefined}
        embedded={isEmbedded}
      />
    );
  });
}

// ============================================================================
// Iframe auto-resize listener (for parent pages embedding via iframe)
// ============================================================================

function setupIframeResizeListener() {
  if (window.self === window.top) {
    // We are the parent page -- listen for resize messages from widget iframes
    window.addEventListener('message', (event) => {
      if (
        event.data &&
        event.data.source === 'perennia-booking-widget' &&
        event.data.type === 'resize'
      ) {
        // Find the iframe that sent this message and resize it
        const iframes = document.querySelectorAll('iframe[src*="perenniaai.com"], iframe[src*="localhost"]');
        iframes.forEach((iframe) => {
          try {
            if (iframe.contentWindow === event.source) {
              iframe.style.height = `${event.data.height}px`;
            }
          } catch (e) {
            // Cross-origin access may throw -- ignore
          }
        });
      }

      // Forward booking completion events
      if (
        event.data &&
        event.data.source === 'perennia-booking-widget' &&
        event.data.type === 'booked'
      ) {
        // Dispatch a custom event on the parent document for tracking integrations
        const bookingEvent = new CustomEvent('perennia:booked', {
          detail: {
            appointmentId: event.data.appointmentId,
            date: event.data.date,
            time: event.data.time,
            type: event.data.type,
          },
        });
        document.dispatchEvent(bookingEvent);
      }
    });
  }
}

// ============================================================================
// Bootstrap
// ============================================================================

// Wait for DOM to be ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    initWidget();
    setupIframeResizeListener();
  });
} else {
  // DOM already loaded (async script)
  initWidget();
  setupIframeResizeListener();
}

// Expose a global API for programmatic initialization
window.PerenniaBooking = {
  init: initWidget,
  version: '1.0.0',
};
