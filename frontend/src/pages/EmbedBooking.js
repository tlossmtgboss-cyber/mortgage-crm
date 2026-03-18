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
          if (window.parent !== window) {
            window.parent.postMessage({
              type: 'perennia-booking-complete',
              appointment: result,
            }, '*');
          }
        }}
      />
    </div>
  );
}
