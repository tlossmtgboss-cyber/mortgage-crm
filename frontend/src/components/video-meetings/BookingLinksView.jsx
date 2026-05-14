import React from 'react';
import { toast } from '../../utils/toast';

const BookingLinksView = ({ bookingLinks, setShowNewLinkModal }) => (
  <div className="scheduler-links-view">
    <div className="links-header">
      <h3>Booking Links</h3>
      <button className="add-link-btn" onClick={() => setShowNewLinkModal(true)}>
        + New Link
      </button>
    </div>

    {bookingLinks.length === 0 ? (
      <div className="empty-state">
        <p>No booking links created</p>
        <p className="hint">Create shareable links for clients to book video meetings</p>
      </div>
    ) : (
      <div className="links-list">
        {bookingLinks.map(link => (
          <div key={link.id} className="link-card">
            <div className="link-info">
              <h4>{link.link_name}</h4>
              <p className="link-url">/meeting/book/{link.slug}</p>
              {link.description && <p className="link-description">{link.description}</p>}
            </div>
            <div className="link-stats">
              <span className="stat">
                <span className="stat-value">{link.view_count}</span>
                <span className="stat-label">Views</span>
              </span>
              <span className="stat">
                <span className="stat-value">{link.booking_count}</span>
                <span className="stat-label">Bookings</span>
              </span>
            </div>
            <div className="link-actions">
              <button
                className="copy-btn"
                onClick={() => {
                  navigator.clipboard.writeText(`${window.location.origin}/meeting/book/${link.slug}`);
                  toast.success('Link copied!');
                }}
              >
                Copy Link
              </button>
            </div>
          </div>
        ))}
      </div>
    )}
  </div>
);

export default BookingLinksView;
