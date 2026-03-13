import { useEffect, useRef } from 'react';

/**
 * SEOHead - Sets document.title, meta description, Open Graph tags, Twitter Card tags,
 * canonical URL, and optional JSON-LD structured data.
 *
 * Props:
 *   title          - Page title (required)
 *   description    - Meta description (required)
 *   image          - Open Graph / Twitter image URL (optional)
 *   url            - Canonical URL (optional)
 *   type           - OG type, e.g. "website", "event" (default: "website")
 *   structuredData - JSON-LD object or array of objects to inject as
 *                    <script type="application/ld+json"> tags (optional)
 *
 * On unmount, restores the original document title and removes injected
 * meta tags and structured data scripts.
 */
const SEOHead = ({ title, description, image, url, type = 'website', structuredData }) => {
  const originalTitle = useRef(document.title);
  const injectedTags = useRef([]);

  useEffect(() => {
    // Store original title on first render
    originalTitle.current = document.title;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    // Remove previously injected tags
    injectedTags.current.forEach((tag) => {
      if (tag && tag.parentNode) {
        tag.parentNode.removeChild(tag);
      }
    });
    injectedTags.current = [];

    // Set document title
    if (title) {
      document.title = title;
    }

    // Helper to create or update a meta tag
    const setMeta = (attr, attrValue, content) => {
      if (!content) return;
      let tag = document.querySelector(`meta[${attr}="${attrValue}"]`);
      if (!tag) {
        tag = document.createElement('meta');
        tag.setAttribute(attr, attrValue);
        document.head.appendChild(tag);
        injectedTags.current.push(tag);
      }
      tag.setAttribute('content', content);
    };

    // Standard meta description
    setMeta('name', 'description', description);

    // Open Graph tags
    setMeta('property', 'og:title', title);
    setMeta('property', 'og:description', description);
    setMeta('property', 'og:type', type);
    if (url) {
      setMeta('property', 'og:url', url);
    }
    if (image) {
      setMeta('property', 'og:image', image);
      setMeta('property', 'og:image:width', '1200');
      setMeta('property', 'og:image:height', '630');
    }
    setMeta('property', 'og:site_name', 'Perennia AI');

    // Twitter Card tags
    setMeta('name', 'twitter:card', image ? 'summary_large_image' : 'summary');
    setMeta('name', 'twitter:title', title);
    setMeta('name', 'twitter:description', description);
    if (image) {
      setMeta('name', 'twitter:image', image);
    }

    // Canonical URL
    let canonicalLink = document.querySelector('link[rel="canonical"]');
    if (url) {
      if (!canonicalLink) {
        canonicalLink = document.createElement('link');
        canonicalLink.setAttribute('rel', 'canonical');
        document.head.appendChild(canonicalLink);
        injectedTags.current.push(canonicalLink);
      }
      canonicalLink.setAttribute('href', url);
    }

    // JSON-LD structured data
    if (structuredData) {
      const dataItems = Array.isArray(structuredData) ? structuredData : [structuredData];
      dataItems.forEach((item) => {
        if (!item) return;
        const script = document.createElement('script');
        script.type = 'application/ld+json';
        script.textContent = JSON.stringify(item);
        script.setAttribute('data-seohead', 'true');
        document.head.appendChild(script);
        injectedTags.current.push(script);
      });
    }

    // Cleanup on unmount
    return () => {
      document.title = originalTitle.current;
      injectedTags.current.forEach((tag) => {
        if (tag && tag.parentNode) {
          tag.parentNode.removeChild(tag);
        }
      });
      injectedTags.current = [];
    };
  }, [title, description, image, url, type, structuredData]);

  // This component renders nothing to the DOM
  return null;
};

export default SEOHead;
