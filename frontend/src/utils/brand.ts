/**
 * Brand utility — static default brand name.
 *
 * For components that cannot access React context (utility files, non-component
 * modules, etc.), import DEFAULT_BRAND_NAME from here.
 *
 * For React components, prefer useBranding() from BrandingContext which returns
 * the per-org brandName dynamically fetched from the backend.
 */

export const DEFAULT_BRAND_NAME = 'Perennia AI';
