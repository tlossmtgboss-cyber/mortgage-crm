import React, { useState, useEffect } from 'react';

const LiveRegion = ({ message, politeness = 'polite', clearAfter = 3000 }) => {
  const [announcement, setAnnouncement] = useState('');

  useEffect(() => {
    if (message) {
      setAnnouncement(message);
      if (clearAfter) {
        const timer = setTimeout(() => setAnnouncement(''), clearAfter);
        return () => clearTimeout(timer);
      }
    }
  }, [message, clearAfter]);

  return (
    <div
      aria-live={politeness}
      aria-atomic="true"
      style={{
        position: 'absolute',
        width: '1px',
        height: '1px',
        margin: '-1px',
        overflow: 'hidden',
        clip: 'rect(0, 0, 0, 0)',
        whiteSpace: 'nowrap',
      }}
    >
      {announcement}
    </div>
  );
};

export default LiveRegion;
