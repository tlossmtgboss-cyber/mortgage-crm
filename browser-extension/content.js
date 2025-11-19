// Content script - runs on mortgageguidelines.com pages
console.log('Mortgage Guidelines Scraper: Content script loaded');

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractGuidelines') {
    const guidelines = extractGuidelinesFromPage();
    sendResponse({ guidelines });
  }
  return true;
});

// Mark that we're ready
window.addEventListener('load', () => {
  console.log('Mortgage Guidelines Scraper: Page loaded, ready to extract');
});
