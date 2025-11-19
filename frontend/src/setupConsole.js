/**
 * Console override for production builds
 * This file disables console.log in production while keeping error and warn logging
 * Import this at the top of index.js
 */

if (process.env.NODE_ENV === 'production') {
  // Save original console methods
  const originalConsoleLog = console.log;
  const originalConsoleDebug = console.debug;
  const originalConsoleInfo = console.info;

  // Override console.log to do nothing in production
  console.log = () => {};
  console.debug = () => {};
  console.info = () => {};

  // Keep console.error and console.warn for production error tracking
  // These remain unchanged

  // Optional: Provide a way to re-enable logging for debugging
  window.enableDebugLogs = () => {
    console.log = originalConsoleLog;
    console.debug = originalConsoleDebug;
    console.info = originalConsoleInfo;
    console.log('Debug logging enabled');
  };
}
