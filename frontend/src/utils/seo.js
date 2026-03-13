/**
 * SEO utilities for public booking pages and other public-facing pages.
 *
 * Provides helpers to generate:
 *  - Page meta tags (title, description, OG, Twitter Card)
 *  - JSON-LD structured data (LocalBusiness, Event, BreadcrumbList)
 *  - Canonical URLs for booking pages
 */

const DEFAULT_OG_IMAGE = 'https://app.perenniaai.com/og-default.png';
const SITE_NAME = 'Perennia AI';
const BASE_URL = 'https://app.perenniaai.com';

/**
 * Generate SEO metadata for a booking page.
 *
 * @param {string} orgName       - Organization name
 * @param {string} appointmentType - Appointment type display name (e.g., "Mortgage Consultation")
 * @param {string} loName        - Loan officer display name
 * @param {object} options       - Optional overrides
 * @param {string} options.image - Custom OG image URL
 * @param {string} options.slug  - Booking link slug for canonical URL
 * @returns {object} { title, description, image, url, type }
 */
export function generateBookingPageMeta(orgName, appointmentType, loName, options = {}) {
  const parts = [];

  if (appointmentType) {
    parts.push(`Book ${appointmentType}`);
  } else {
    parts.push('Book an Appointment');
  }

  if (loName) {
    parts.push(`with ${loName}`);
  }

  const titleCore = parts.join(' ');
  const title = orgName
    ? `${titleCore} | ${orgName}`
    : `${titleCore} | ${SITE_NAME}`;

  const descParts = [];
  if (appointmentType) {
    descParts.push(`Schedule your ${appointmentType}`);
  } else {
    descParts.push('Schedule your appointment');
  }
  if (loName) {
    descParts.push(`with ${loName}`);
  }
  descParts.push('. Choose from available times and book online instantly.');
  const description = descParts.join(' ').replace(/\s+/g, ' ').trim();

  const image = options.image || DEFAULT_OG_IMAGE;

  let url = null;
  if (options.slug) {
    url = `${BASE_URL}/book/${options.slug}`;
  }

  return {
    title,
    description,
    image,
    url,
    type: 'website',
  };
}


/**
 * Generate a canonical URL for a booking page.
 *
 * @param {string} bookingSlug - The booking link slug
 * @returns {string} Fully-qualified canonical URL
 */
export function generateCanonicalUrl(bookingSlug) {
  if (!bookingSlug) {
    return BASE_URL;
  }
  // Strip leading/trailing slashes and whitespace
  const cleaned = bookingSlug.replace(/^\/+|\/+$/g, '').trim();
  return `${BASE_URL}/book/${cleaned}`;
}


/**
 * Generate JSON-LD structured data for a LocalBusiness schema.
 * Injected on page load to identify the mortgage business / loan officer.
 *
 * @param {object} loProfile
 * @param {string} loProfile.name        - Loan officer or business display name
 * @param {string} loProfile.description  - Business description
 * @param {string} loProfile.image        - Logo or headshot URL
 * @param {string} loProfile.telephone    - Contact phone (optional)
 * @param {string} loProfile.email        - Contact email (optional)
 * @param {string} loProfile.orgName      - Parent organization name
 * @param {string} loProfile.nmlsId       - NMLS license ID (optional)
 * @param {object} loProfile.address      - Address object with street, city, state, zip (optional)
 * @param {string} bookingLink            - Full canonical URL to the booking page
 * @returns {object} JSON-LD object
 */
export function generateLocalBusinessData(loProfile, bookingLink) {
  if (!loProfile || !loProfile.name) {
    return null;
  }

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'FinancialService',
    name: loProfile.name,
    description: loProfile.description || `Mortgage services by ${loProfile.name}`,
    url: bookingLink || BASE_URL,
  };

  if (loProfile.image) {
    jsonLd.image = loProfile.image;
  }

  if (loProfile.telephone) {
    jsonLd.telephone = loProfile.telephone;
  }

  if (loProfile.email) {
    jsonLd.email = loProfile.email;
  }

  if (loProfile.orgName) {
    jsonLd.parentOrganization = {
      '@type': 'Organization',
      name: loProfile.orgName,
    };
  }

  if (loProfile.address) {
    jsonLd.address = {
      '@type': 'PostalAddress',
    };
    if (loProfile.address.street) jsonLd.address.streetAddress = loProfile.address.street;
    if (loProfile.address.city) jsonLd.address.addressLocality = loProfile.address.city;
    if (loProfile.address.state) jsonLd.address.addressRegion = loProfile.address.state;
    if (loProfile.address.zip) jsonLd.address.postalCode = loProfile.address.zip;
    jsonLd.address.addressCountry = 'US';
  }

  if (loProfile.nmlsId) {
    jsonLd.identifier = {
      '@type': 'PropertyValue',
      name: 'NMLS ID',
      value: loProfile.nmlsId,
    };
  }

  // Available appointment types as offered services
  if (loProfile.appointmentTypes && loProfile.appointmentTypes.length > 0) {
    jsonLd.hasOfferCatalog = {
      '@type': 'OfferCatalog',
      name: 'Available Appointments',
      itemListElement: loProfile.appointmentTypes.map((typeName) => ({
        '@type': 'Offer',
        itemOffered: {
          '@type': 'Service',
          name: typeName,
        },
      })),
    };
  }

  return jsonLd;
}


/**
 * Generate JSON-LD structured data for an Event schema.
 * Used when a user selects a specific time slot on the booking page.
 *
 * @param {object} appointment
 * @param {string} appointment.name         - Event name / appointment type
 * @param {string} appointment.description  - Event description
 * @param {string} appointment.startTime    - ISO 8601 start time
 * @param {string} appointment.endTime      - ISO 8601 end time
 * @param {string} appointment.locationName - Location name or "Online"
 * @param {string} appointment.organizerName - Organizer name (LO or org)
 * @param {string} appointment.url          - Booking page URL
 * @param {string} appointment.image        - Event image URL
 * @returns {object} JSON-LD object
 */
export function generateStructuredData(appointment) {
  if (!appointment || !appointment.name) {
    return null;
  }

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Event',
    name: appointment.name,
    description: appointment.description || `Book ${appointment.name} online`,
    eventAttendanceMode: 'https://schema.org/OnlineEventAttendanceMode',
    eventStatus: 'https://schema.org/EventScheduled',
  };

  if (appointment.startTime) {
    jsonLd.startDate = appointment.startTime;
  }

  if (appointment.endTime) {
    jsonLd.endDate = appointment.endTime;
  }

  if (appointment.locationName) {
    jsonLd.location = {
      '@type': 'VirtualLocation',
      name: appointment.locationName,
    };
  } else {
    jsonLd.location = {
      '@type': 'VirtualLocation',
      name: 'Online',
    };
  }

  if (appointment.organizerName) {
    jsonLd.organizer = {
      '@type': 'Organization',
      name: appointment.organizerName,
    };
  }

  if (appointment.url) {
    jsonLd.url = appointment.url;
  }

  if (appointment.image) {
    jsonLd.image = appointment.image;
  }

  // Offer for free booking
  jsonLd.offers = {
    '@type': 'Offer',
    price: '0',
    priceCurrency: 'USD',
    availability: 'https://schema.org/InStock',
    url: appointment.url || '',
  };

  return jsonLd;
}


/**
 * Generate JSON-LD BreadcrumbList structured data.
 *
 * @param {Array<{name: string, url: string}>} steps - Breadcrumb items in order
 * @returns {object} JSON-LD BreadcrumbList object
 */
export function generateBreadcrumbs(steps) {
  if (!steps || steps.length === 0) {
    return null;
  }

  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: steps.map((step, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: step.name,
      item: step.url || undefined,
    })),
  };
}


/**
 * Inject a JSON-LD script tag into the document head.
 * Returns a cleanup function that removes the tag.
 *
 * @param {object} jsonLdData - The JSON-LD object to inject
 * @returns {function} cleanup - Call to remove the script tag
 */
export function injectJsonLd(jsonLdData) {
  if (!jsonLdData) {
    return () => {};
  }

  const script = document.createElement('script');
  script.type = 'application/ld+json';
  script.textContent = JSON.stringify(jsonLdData);
  script.setAttribute('data-seo-injected', 'true');
  document.head.appendChild(script);

  return () => {
    if (script.parentNode) {
      script.parentNode.removeChild(script);
    }
  };
}


/**
 * Remove all SEO-injected JSON-LD script tags from the document head.
 */
export function cleanupJsonLd() {
  const scripts = document.querySelectorAll('script[data-seo-injected="true"]');
  scripts.forEach((s) => {
    if (s.parentNode) {
      s.parentNode.removeChild(s);
    }
  });
}
