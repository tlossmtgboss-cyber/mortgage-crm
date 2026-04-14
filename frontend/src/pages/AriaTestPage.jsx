import { useEffect } from 'react';

export default function AriaTestPage() {
  useEffect(() => {
    // Redirect to the static HTML file which runs in the top-level
    // window context with proper Origin header for CORS
    window.location.replace('/static/aria-test.html');
  }, []);

  return null;
}
