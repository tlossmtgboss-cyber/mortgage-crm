// Background service worker
console.log('Mortgage Guidelines Scraper: Background worker started');

// Listen for installation
chrome.runtime.onInstalled.addListener(() => {
  console.log('Mortgage Guidelines Scraper: Extension installed');
});

// Handle messages
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('Background received message:', request);
  return true;
});
