import { useEffect, useRef } from 'react';
import ariaTestHtml from '../assets/aria-test.html?raw';

export default function AriaTestPage() {
  const iframeRef = useRef(null);

  useEffect(() => {
    // Hide the SPA chrome — this page should be full-screen
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, []);

  return (
    <iframe
      ref={iframeRef}
      srcDoc={ariaTestHtml}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        border: 'none',
        zIndex: 9999,
      }}
      title="Aria Test Console"
    />
  );
}
