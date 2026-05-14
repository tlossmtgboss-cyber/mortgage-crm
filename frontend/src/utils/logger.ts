/**
 * Production-safe logger utility
 * Automatically disables console.log in production builds while keeping error/warn logging
 */

const isProduction: boolean = process.env.NODE_ENV === 'production';

export interface Logger {
  log: (...args: unknown[]) => void;
  info: (...args: unknown[]) => void;
  warn: (...args: unknown[]) => void;
  error: (...args: unknown[]) => void;
  debug: (...args: unknown[]) => void;
  table: (...args: unknown[]) => void;
}

export const logger: Logger = {
  log: (...args: unknown[]) => {
    if (!isProduction) {
      console.log(...args);
    }
  },

  info: (...args: unknown[]) => {
    if (!isProduction) {
      console.info(...args);
    }
  },

  warn: (...args: unknown[]) => {
    console.warn(...args);
  },

  error: (...args: unknown[]) => {
    console.error(...args);
  },

  debug: (...args: unknown[]) => {
    if (!isProduction) {
      console.debug(...args);
    }
  },

  table: (...args: unknown[]) => {
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
