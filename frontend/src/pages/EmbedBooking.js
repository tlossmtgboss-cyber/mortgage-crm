/**
 * Embed Booking Page
 *
 * Standalone page for iframe embedding.
 * URL: /embed/book/:slug
 *
 * Usage in external website:
 * <iframe src="https://app.perenniaai.com/embed/book/your-booking-slug"
 *         width="500" height="600" frameborder="0"></iframe>
 */
import { useParams } from 'react-router-dom';
import EmbeddableBookingWidget from '../components/calendar/EmbeddableBookingWidget';

export default function EmbedBooking() {
  const { slug } = useParams();

  // Parse theme from URL params
  const params = new URLSearchParams(window.location.search);
  const theme = {};
  if (params.get('bg')) theme.background = `#${params.get('bg')}`;
  if (params.get('accent')) theme['--accent'] = `#${params.get('accent')}`;

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: theme.background || '#f8fafc',
      padding: 16,
    }}>
      <EmbeddableBookingWidget
        slug={slug}
        theme={theme}
        onBooked={(result) => {
          // Post message to parent window for iframe communication
          // V3-C4: Only send appointment ID and status — no PII in postMessage
          if (window.parent !== window) {
            const safeResult = {
              appointment_id: result?.id || result?.appointment_id,
              status: result?.status || 'booked',
              scheduled_start: result?.scheduled_start,
            };
            // Only send postMessage if we can determine the parent origin.
            // Never use '*' — it would leak data to any embedding page.
            let targetOrigin = null;
            try {
              if (document.referrer) {
                targetOrigin = new URL(document.referrer).origin;
              }
            } catch {
              // Malformed referrer — do not send
            }
            if (targetOrigin && targetOrigin !== 'null') {
              window.parent.postMessage({
                type: 'perennia-booking-complete',
                appointment: safeResult,
              }, targetOrigin);
            }
          }
        }}
      />
    </div>
  );
}
