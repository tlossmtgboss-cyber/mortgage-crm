/**
 * Global Window augmentations used by the POS (borrower portal) flow.
 *
 * __PURL_TOKEN__         – Borrower PURL auth token, set after verification
 * __PERENNIA_API_BASE__  – Optional API base URL override for portal shells
 */
export {};

declare global {
  interface Window {
    __PURL_TOKEN__?: string;
    __PERENNIA_API_BASE__?: string;
  }
}
