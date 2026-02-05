// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// Vitest compatibility - use vi for mocks when available, fall back to jest
const mockFn = typeof vi !== 'undefined' ? vi.fn : jest.fn;

// Mock URL APIs
global.URL.createObjectURL = mockFn(() => 'mock-url');
global.URL.revokeObjectURL = mockFn();

// Mock window.open
global.open = mockFn();

// Suppress React Router deprecation warnings in tests
const originalWarn = console.warn;
console.warn = (...args) => {
  if (
    typeof args[0] === 'string' &&
    args[0].includes('React Router Future Flag Warning')
  ) {
    return;
  }
  originalWarn.apply(console, args);
};
