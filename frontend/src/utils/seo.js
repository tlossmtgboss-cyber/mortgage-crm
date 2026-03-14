export const generateBookingPageMeta = ({ orgName } = {}) => {
  const title = orgName ? `Book with ${orgName}` : 'Book an Appointment';
  const description = `Schedule your appointment${orgName ? ` with ${orgName}` : ''}. Fast, easy booking.`;
  return { title, description };
};

export const generateStructuredData = ({ orgName, url, description } = {}) => ({
  '@context': 'https://schema.org',
  '@type': 'LocalBusiness',
  name: orgName || 'Appointment Booking',
  url: url || (typeof window !== 'undefined' ? window.location.href : ''),
  description: description || 'Online appointment booking service',
});

export const generateBreadcrumbs = (items = []) => ({
  '@context': 'https://schema.org',
  '@type': 'BreadcrumbList',
  itemListElement: items.map((item, index) => ({
    '@type': 'ListItem',
    position: index + 1,
    name: item.name,
    item: item.url,
  })),
});

export const injectJsonLd = (data) => {
  try {
    const existing = document.getElementById('json-ld-data');
    if (existing) existing.remove();
    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.id = 'json-ld-data';
    script.textContent = JSON.stringify(data);
    document.head.appendChild(script);
  } catch (e) {
    console.warn('Failed to inject JSON-LD:', e);
  }
};

export const cleanupJsonLd = () => {
  try {
    const script = document.getElementById('json-ld-data');
    if (script) script.remove();
  } catch (e) {
    console.warn('Failed to cleanup JSON-LD:', e);
  }
};
