/**
 * streamMessage — Unit tests for the SSE streaming function used by Aria's
 * voice pipeline to stream AI responses token-by-token.
 *
 * Mocks: global fetch, dynamic import of ../utils/storage.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mock the api module (streamMessage imports it for baseURL + token refresh)
// ---------------------------------------------------------------------------

vi.mock('../services/api', () => ({
  default: {
    defaults: { baseURL: 'http://test-api.local' },
  },
  attemptTokenRefresh: vi.fn().mockResolvedValue(false),
}));

// ---------------------------------------------------------------------------
// Mock the in-memory token store (streamMessage reads the token synchronously
// via getToken() to build the SSE fetch Authorization header)
// ---------------------------------------------------------------------------

vi.mock('../utils/tokenStore', () => ({
  getToken: vi.fn().mockReturnValue('test-jwt-token'),
  setToken: vi.fn(),
  clearToken: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Import the module under test
// ---------------------------------------------------------------------------

import { streamMessage } from '../services/mobileAriaApi';

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

/** Encode a string as a Uint8Array (simulating ReadableStream chunks). */
function encode(str) {
  return new TextEncoder().encode(str);
}

/**
 * Build a mock ReadableStream reader that yields the given chunks
 * one at a time, then signals done.
 */
function makeStreamReader(chunks) {
  let index = 0;
  return {
    read: vi.fn().mockImplementation(async () => {
      if (index < chunks.length) {
        return { done: false, value: encode(chunks[index++]) };
      }
      return { done: true, value: undefined };
    }),
  };
}

/**
 * Build a mock fetch Response with a readable body stream.
 */
function makeFetchResponse(chunks, status = 200) {
  const reader = makeStreamReader(chunks);
  return {
    ok: status >= 200 && status < 300,
    status,
    body: { getReader: () => reader },
    json: vi.fn().mockResolvedValue({}),
  };
}

/** Flush async microtasks/timers. */
async function flushPromises(count = 15) {
  for (let i = 0; i < count; i++) {
    await new Promise((r) => setTimeout(r, 0));
  }
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

let originalFetch;

beforeEach(() => {
  vi.clearAllMocks();
  originalFetch = global.fetch;
});

afterEach(() => {
  global.fetch = originalFetch;
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('streamMessage', () => {
  // =========================================================================
  // Successful stream
  // =========================================================================

  describe('successful stream', () => {
    it('calls onChunk for each content event', async () => {
      const onChunk = vi.fn();
      const onDone = vi.fn();

      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([
          'data: {"content":"Hello "}\n\n',
          'data: {"content":"world"}\n\n',
          'data: {"done":true,"session_id":"s1"}\n\n',
        ])
      );

      streamMessage('test', 'session-1', { onChunk, onDone });
      await flushPromises(20);

      expect(onChunk).toHaveBeenCalledTimes(2);
      expect(onChunk).toHaveBeenCalledWith('Hello ', 'Hello ');
      expect(onChunk).toHaveBeenCalledWith('world', 'Hello world');
    });

    it('accumulates fullText across chunks', async () => {
      const onChunk = vi.fn();
      const onDone = vi.fn();

      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([
          'data: {"content":"A"}\n\n',
          'data: {"content":"B"}\n\n',
          'data: {"content":"C"}\n\n',
          'data: {"done":true}\n\n',
        ])
      );

      streamMessage('test', null, { onChunk, onDone });
      await flushPromises(20);

      // Last onChunk call should have full accumulated text
      const lastCall = onChunk.mock.calls[onChunk.mock.calls.length - 1];
      expect(lastCall[1]).toBe('ABC');
    });

    it('calls onDone when done event arrives', async () => {
      const onDone = vi.fn();

      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([
          'data: {"content":"Hello"}\n\n',
          'data: {"done":true,"session_id":"sess-42"}\n\n',
        ])
      );

      streamMessage('test', null, { onDone });
      await flushPromises(20);

      expect(onDone).toHaveBeenCalledWith('Hello', 'sess-42');
    });

    it('calls onDone with fullText when stream ends without done event', async () => {
      const onDone = vi.fn();

      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([
          'data: {"content":"Partial response"}\n\n',
        ])
      );

      streamMessage('test', 'my-session', { onDone });
      await flushPromises(20);

      // Should fire onDone with the accumulated text and the original sessionId
      expect(onDone).toHaveBeenCalledWith('Partial response', 'my-session');
    });
  });

  // =========================================================================
  // Error response
  // =========================================================================

  describe('error response', () => {
    it('calls onError when HTTP response is not ok', async () => {
      const onError = vi.fn();
      const onChunk = vi.fn();

      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: vi.fn().mockResolvedValue({ detail: 'Server error' }),
      });

      streamMessage('test', null, { onChunk, onError });
      await flushPromises(20);

      expect(onError).toHaveBeenCalledWith('Server error');
      expect(onChunk).not.toHaveBeenCalled();
    });

    it('calls onError with HTTP status when no detail in response', async () => {
      const onError = vi.fn();

      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: vi.fn().mockResolvedValue({}),
      });

      streamMessage('test', null, { onError });
      await flushPromises(20);

      expect(onError).toHaveBeenCalledWith('HTTP 422');
    });

    it('calls onError when error event arrives in SSE stream', async () => {
      const onError = vi.fn();

      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([
          'data: {"error":"Rate limit exceeded"}\n\n',
        ])
      );

      streamMessage('test', null, { onError });
      await flushPromises(20);

      expect(onError).toHaveBeenCalledWith('Rate limit exceeded');
    });

    it('calls onError when fetch rejects (network failure)', async () => {
      const onError = vi.fn();

      global.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

      streamMessage('test', null, { onError });
      await flushPromises(20);

      expect(onError).toHaveBeenCalledWith('Failed to fetch');
    });

    it('calls onError with fallback message when error has no message', async () => {
      const onError = vi.fn();

      const err = new Error();
      err.message = '';
      global.fetch = vi.fn().mockRejectedValue(err);

      streamMessage('test', null, { onError });
      await flushPromises(20);

      expect(onError).toHaveBeenCalledWith('Stream failed');
    });
  });

  // =========================================================================
  // Abort
  // =========================================================================

  describe('abort', () => {
    it('returns an object with an abort function', () => {
      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([])
      );

      const result = streamMessage('test', null, {});
      expect(result).toHaveProperty('abort');
      expect(typeof result.abort).toBe('function');
    });

    it('does not call onError after abort (AbortError is suppressed)', async () => {
      const onError = vi.fn();
      const onChunk = vi.fn();

      // Simulate a fetch that rejects with AbortError when aborted
      global.fetch = vi.fn().mockImplementation((_url, opts) => {
        return new Promise((resolve, reject) => {
          opts?.signal?.addEventListener('abort', () => {
            const err = new DOMException('The user aborted a request.', 'AbortError');
            reject(err);
          });
          // Never resolves naturally — we abort first
        });
      });

      const handle = streamMessage('test', null, { onChunk, onError });
      handle.abort();

      await flushPromises(20);

      expect(onError).not.toHaveBeenCalled();
      expect(onChunk).not.toHaveBeenCalled();
    });

    it('passes AbortController signal to fetch', async () => {
      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([])
      );

      streamMessage('test', null, {});
      await flushPromises();

      const [, fetchOpts] = global.fetch.mock.calls[0];
      expect(fetchOpts.signal).toBeInstanceOf(AbortSignal);
    });
  });

  // =========================================================================
  // Malformed SSE lines
  // =========================================================================

  describe('malformed SSE lines', () => {
    it('skips lines that do not start with "data: "', async () => {
      const onChunk = vi.fn();
      const onDone = vi.fn();

      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([
          ': comment line\n',
          'event: heartbeat\n',
          'data: {"content":"Valid"}\n\n',
          'data: {"done":true}\n\n',
        ])
      );

      streamMessage('test', null, { onChunk, onDone });
      await flushPromises(20);

      expect(onChunk).toHaveBeenCalledTimes(1);
      expect(onChunk).toHaveBeenCalledWith('Valid', 'Valid');
    });

    it('skips data lines with invalid JSON without crashing', async () => {
      const onChunk = vi.fn();
      const onDone = vi.fn();
      const onError = vi.fn();

      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([
          'data: {malformed json\n\n',
          'data: {"content":"OK"}\n\n',
          'data: not even close\n\n',
          'data: {"done":true}\n\n',
        ])
      );

      streamMessage('test', null, { onChunk, onDone, onError });
      await flushPromises(20);

      // Only the valid content line should trigger onChunk
      expect(onChunk).toHaveBeenCalledTimes(1);
      expect(onChunk).toHaveBeenCalledWith('OK', 'OK');
      // onError should NOT be called for malformed SSE — those are silently skipped
      expect(onError).not.toHaveBeenCalled();
    });

    it('handles empty data lines gracefully', async () => {
      const onChunk = vi.fn();

      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([
          'data: \n\n',
          'data: {"content":"After empty"}\n\n',
          'data: {"done":true}\n\n',
        ])
      );

      streamMessage('test', null, { onChunk });
      await flushPromises(20);

      expect(onChunk).toHaveBeenCalledTimes(1);
      expect(onChunk).toHaveBeenCalledWith('After empty', 'After empty');
    });
  });

  // =========================================================================
  // Empty stream
  // =========================================================================

  describe('empty stream', () => {
    it('does not call onDone when stream is completely empty (no content)', async () => {
      const onDone = vi.fn();
      const onChunk = vi.fn();

      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([])
      );

      streamMessage('test', null, { onChunk, onDone });
      await flushPromises(20);

      // fullText is empty string, so the "if (fullText)" guard prevents onDone
      expect(onChunk).not.toHaveBeenCalled();
      expect(onDone).not.toHaveBeenCalled();
    });

    it('calls onDone when stream has only a done event with no prior content', async () => {
      const onDone = vi.fn();

      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([
          'data: {"done":true,"session_id":"s1"}\n\n',
        ])
      );

      streamMessage('test', null, { onDone });
      await flushPromises(20);

      // The done event fires onDone, but fullText is empty so the fallback guard won't fire again
      expect(onDone).toHaveBeenCalledWith('', 's1');
    });
  });

  // =========================================================================
  // Request format
  // =========================================================================

  describe('request format', () => {
    it('sends POST with JSON body including message and voice_mode', async () => {
      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([])
      );

      streamMessage('Hello Aria', 'sess-1', {});
      await flushPromises();

      expect(global.fetch).toHaveBeenCalledTimes(1);
      const [url, opts] = global.fetch.mock.calls[0];

      expect(url).toBe('http://test-api.local/api/v1/ai/orchestrator-chat-stream');
      expect(opts.method).toBe('POST');
      expect(opts.headers['Content-Type']).toBe('application/json');
      expect(opts.headers['Authorization']).toBe('Bearer test-jwt-token');

      const body = JSON.parse(opts.body);
      expect(body.message).toBe('Hello Aria');
      expect(body.voice_mode).toBe(true);
      expect(body.session_id).toBe('sess-1');
    });

    it('omits session_id from body when null', async () => {
      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([])
      );

      streamMessage('Hello', null, {});
      await flushPromises();

      const body = JSON.parse(global.fetch.mock.calls[0][1].body);
      expect(body).not.toHaveProperty('session_id');
    });

    it('omits Authorization header when no token is available', async () => {
      // Re-mock the token store to return null
      const tokenStore = await import('../utils/tokenStore');
      tokenStore.getToken.mockReturnValueOnce(null);

      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([])
      );

      streamMessage('Hello', null, {});
      await flushPromises();

      const headers = global.fetch.mock.calls[0][1].headers;
      expect(headers['Authorization']).toBeUndefined();
    });
  });

  // =========================================================================
  // Chunked SSE delivery (partial lines across chunks)
  // =========================================================================

  describe('chunked SSE delivery', () => {
    it('reassembles SSE lines split across multiple stream chunks', async () => {
      const onChunk = vi.fn();

      // Simulate a single SSE line split across two stream chunks
      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([
          'data: {"conten',        // partial line
          't":"Reassembled"}\n\n', // rest of line
          'data: {"done":true}\n\n',
        ])
      );

      streamMessage('test', null, { onChunk });
      await flushPromises(20);

      expect(onChunk).toHaveBeenCalledTimes(1);
      expect(onChunk).toHaveBeenCalledWith('Reassembled', 'Reassembled');
    });

    it('handles multiple SSE lines in a single stream chunk', async () => {
      const onChunk = vi.fn();

      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([
          'data: {"content":"A"}\ndata: {"content":"B"}\ndata: {"content":"C"}\n\n',
          'data: {"done":true}\n\n',
        ])
      );

      streamMessage('test', null, { onChunk });
      await flushPromises(20);

      expect(onChunk).toHaveBeenCalledTimes(3);
    });
  });

  // =========================================================================
  // Callback safety (no callbacks provided)
  // =========================================================================

  describe('callback safety', () => {
    it('does not throw when no callbacks are provided', async () => {
      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([
          'data: {"content":"No one is listening"}\n\n',
          'data: {"done":true}\n\n',
        ])
      );

      // Should not throw
      const handle = streamMessage('test', null, {});
      await flushPromises(20);

      expect(handle).toHaveProperty('abort');
    });

    it('does not throw when callbacks object is undefined', async () => {
      global.fetch = vi.fn().mockResolvedValue(
        makeFetchResponse([
          'data: {"content":"Hello"}\n\n',
          'data: {"done":true}\n\n',
        ])
      );

      // streamMessage's third arg defaults to {}
      const handle = streamMessage('test', null);
      await flushPromises(20);

      expect(handle).toHaveProperty('abort');
    });
  });
});
