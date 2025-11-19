/**
 * Production-safe logger utility
 * Automatically disables console.log in production builds while keeping error/warn logging
 */

const isProduction = process.env.NODE_ENV === 'production';

export const logger = {
  log: (...args) => {
    if (!isProduction) {
      console.log(...args);
    }
  },

  info: (...args) => {
    if (!isProduction) {
      console.info(...args);
    }
  },

  warn: (...args) => {
    console.warn(...args);
  },

  error: (...args) => {
    console.error(...args);
  },

  debug: (...args) => {
    if (!isProduction) {
      console.debug(...args);
    }
  },

  table: (...args) => {
    if (!isProduction) {
      console.table(...args);
    }
  }
};

// For backwards compatibility, you can also use these directly
export const log = logger.log;
export const warn = logger.warn;
export const error = logger.error;
export const debug = logger.debug;

export default logger;
