/**
 * TTSQueue — Unit tests for the TTS playback queue used by Aria's streaming
 * voice pipeline.
 *
 * The class lives inside AriaVoiceHome.jsx and is not exported, so we
 * reproduce the exact implementation here and test it in isolation.
 *
 * Mocks: api.post (TTS synthesis endpoint), Audio constructor, URL APIs,
 * atob, window.speechSynthesis.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mock api module
// ---------------------------------------------------------------------------

const mockApiPost = vi.fn();

// Local api stub — mirrors the real api module's interface for TTSQueue
const api = { post: (...args) => mockApiPost(...args) };

// ---------------------------------------------------------------------------
// Reproduce TTSQueue (same as AriaVoiceHome.jsx)
// ---------------------------------------------------------------------------

class TTSQueue {
  constructor() {
    this._queue = [];
    this._playing = false;
    this._aborted = false;
    this._currentAudio = null;
    this._onAllDone = null;
  }

  enqueue(text) {
    if (this._aborted || !text.trim()) return;
    this._queue.push(text);
    if (!this._playing) this._playNext();
  }

  async _playNext() {
    if (this._aborted || this._queue.length === 0) {
      this._playing = false;
      this._onAllDone?.();
      return;
    }

    this._playing = true;
    const text = this._queue.shift();

    try {
      const res = await api.post('/api/v1/mobile-voice/tts/synthesize', { text });
      if (this._aborted) return;

      const b64 = res.data?.audio;
      if (!b64 || b64.length < 100) throw new Error('Empty audio');

      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const blob = new Blob([bytes], { type: 'audio/mpeg' });
      const url = URL.createObjectURL(blob);

      await new Promise((resolve) => {
        const audio = new Audio(url);
        this._currentAudio = audio;
        audio.onended = () => { URL.revokeObjectURL(url); this._currentAudio = null; resolve(); };
        audio.onerror = () => { URL.revokeObjectURL(url); this._currentAudio = null; resolve(); };
        audio.play().catch(resolve);
      });
    } catch (err) {
      if (this._aborted) return;
      // Fallback to browser SpeechSynthesis for this chunk
      await new Promise((resolve) => {
        const synth = window.speechSynthesis;
        if (!synth) { resolve(); return; }
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.0;
        utterance.onend = resolve;
        utterance.onerror = resolve;
        synth.speak(utterance);
      });
    }

    if (!this._aborted) this._playNext();
  }

  stop() {
    this._aborted = true;
    this._queue = [];
    if (this._currentAudio) {
      this._currentAudio.pause();
      this._currentAudio.currentTime = 0;
      this._currentAudio = null;
    }
    window.speechSynthesis?.cancel();
  }

  onAllDone(fn) { this._onAllDone = fn; }
}

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

// Generate a fake base64 string of at least 100 chars (the minimum length check)
const FAKE_B64_AUDIO = btoa('x'.repeat(200));

function makeSuccessfulTTSResponse() {
  return { data: { audio: FAKE_B64_AUDIO } };
}

/**
 * Create a mock Audio instance whose play() resolves immediately and
 * whose onended fires on the next microtask.
 */
function createMockAudio() {
  const instance = {
    play: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn(),
    currentTime: 0,
    onended: null,
    onerror: null,
    // Helper to simulate playback completion
    _fireEnded() {
      this.onended?.();
    },
    _fireError() {
      this.onerror?.();
    },
  };
  return instance;
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

let mockAudioInstances;
let originalAudio;
let originalSpeechSynthesis;
let originalSpeechSynthesisUtterance;
let originalAtob;

beforeEach(() => {
  vi.clearAllMocks();
  mockAudioInstances = [];

  // Mock Audio constructor
  originalAudio = global.Audio;
  global.Audio = vi.fn().mockImplementation(() => {
    const instance = createMockAudio();
    mockAudioInstances.push(instance);
    // Auto-fire onended after play resolves so the queue advances
    const origPlay = instance.play;
    instance.play = vi.fn().mockImplementation(() => {
      return origPlay().then(() => {
        // Use setTimeout(0) to let the promise chain in _playNext resolve first
        setTimeout(() => instance._fireEnded(), 0);
      });
    });
    return instance;
  });

  // Mock SpeechSynthesis
  originalSpeechSynthesis = window.speechSynthesis;
  window.speechSynthesis = {
    speak: vi.fn(),
    cancel: vi.fn(),
  };

  // Mock SpeechSynthesisUtterance
  originalSpeechSynthesisUtterance = global.SpeechSynthesisUtterance;
  global.SpeechSynthesisUtterance = vi.fn().mockImplementation((text) => ({
    text,
    rate: 1.0,
    onend: null,
    onerror: null,
  }));

  // Default: api.post returns successful audio
  mockApiPost.mockResolvedValue(makeSuccessfulTTSResponse());
});

afterEach(() => {
  global.Audio = originalAudio;
  window.speechSynthesis = originalSpeechSynthesis;
  global.SpeechSynthesisUtterance = originalSpeechSynthesisUtterance;
});

// ---------------------------------------------------------------------------
// Helper to flush all microtasks / timers
// ---------------------------------------------------------------------------

async function flushPromises(count = 10) {
  for (let i = 0; i < count; i++) {
    await new Promise((r) => setTimeout(r, 0));
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TTSQueue', () => {
  // =========================================================================
  // Construction
  // =========================================================================

  describe('construction', () => {
    it('creates a new queue in idle state', () => {
      const queue = new TTSQueue();
      expect(queue._queue).toEqual([]);
      expect(queue._playing).toBe(false);
      expect(queue._aborted).toBe(false);
      expect(queue._currentAudio).toBeNull();
    });
  });

  // =========================================================================
  // Single enqueue
  // =========================================================================

  describe('enqueue single text', () => {
    it('calls the TTS API with the enqueued text', async () => {
      const queue = new TTSQueue();
      queue.enqueue('Hello world');

      await flushPromises();

      expect(mockApiPost).toHaveBeenCalledWith(
        '/api/v1/mobile-voice/tts/synthesize',
        { text: 'Hello world' }
      );
    });

    it('creates an Audio element for playback', async () => {
      const queue = new TTSQueue();
      queue.enqueue('Hello world');

      await flushPromises();

      expect(global.Audio).toHaveBeenCalled();
    });

    it('calls onAllDone after single item finishes playing', async () => {
      const onDone = vi.fn();
      const queue = new TTSQueue();
      queue.onAllDone(onDone);
      queue.enqueue('Hello');

      await flushPromises(20);

      expect(onDone).toHaveBeenCalledTimes(1);
    });
  });

  // =========================================================================
  // Multiple enqueue — sequential playback
  // =========================================================================

  describe('enqueue multiple texts', () => {
    it('calls TTS API for each enqueued text in order', async () => {
      const queue = new TTSQueue();
      queue.enqueue('First sentence.');
      queue.enqueue('Second sentence.');
      queue.enqueue('Third sentence.');

      await flushPromises(30);

      expect(mockApiPost).toHaveBeenCalledTimes(3);
      expect(mockApiPost.mock.calls[0][1]).toEqual({ text: 'First sentence.' });
      expect(mockApiPost.mock.calls[1][1]).toEqual({ text: 'Second sentence.' });
      expect(mockApiPost.mock.calls[2][1]).toEqual({ text: 'Third sentence.' });
    });

    it('calls onAllDone only once after all items finish', async () => {
      const onDone = vi.fn();
      const queue = new TTSQueue();
      queue.onAllDone(onDone);

      queue.enqueue('A');
      queue.enqueue('B');

      await flushPromises(30);

      expect(onDone).toHaveBeenCalledTimes(1);
    });
  });

  // =========================================================================
  // Stop mid-playback
  // =========================================================================

  describe('stop()', () => {
    it('clears the queue', () => {
      const queue = new TTSQueue();
      // Manually push items without triggering _playNext
      queue._queue = ['A', 'B', 'C'];
      queue.stop();
      expect(queue._queue).toEqual([]);
    });

    it('sets _aborted to true', () => {
      const queue = new TTSQueue();
      queue.stop();
      expect(queue._aborted).toBe(true);
    });

    it('pauses current audio if playing', () => {
      const queue = new TTSQueue();
      const fakeAudio = { pause: vi.fn(), currentTime: 5 };
      queue._currentAudio = fakeAudio;
      queue.stop();
      expect(fakeAudio.pause).toHaveBeenCalled();
      expect(fakeAudio.currentTime).toBe(0);
      expect(queue._currentAudio).toBeNull();
    });

    it('calls speechSynthesis.cancel()', () => {
      const queue = new TTSQueue();
      queue.stop();
      expect(window.speechSynthesis.cancel).toHaveBeenCalled();
    });

    it('prevents further items from being enqueued after stop', () => {
      const queue = new TTSQueue();
      queue.stop();
      queue.enqueue('Should not be added');
      expect(queue._queue).toEqual([]);
    });
  });

  // =========================================================================
  // Empty text handling
  // =========================================================================

  describe('empty text handling', () => {
    it('skips empty string', () => {
      const queue = new TTSQueue();
      queue.enqueue('');
      expect(queue._queue).toEqual([]);
      expect(queue._playing).toBe(false);
    });

    it('skips whitespace-only string', () => {
      const queue = new TTSQueue();
      queue.enqueue('   ');
      expect(queue._queue).toEqual([]);
      expect(queue._playing).toBe(false);
    });

    it('skips tab-only string', () => {
      const queue = new TTSQueue();
      queue.enqueue('\t\n ');
      expect(queue._queue).toEqual([]);
      expect(queue._playing).toBe(false);
    });

    it('does not call the TTS API for empty text', async () => {
      const queue = new TTSQueue();
      queue.enqueue('');
      queue.enqueue('   ');

      await flushPromises();

      expect(mockApiPost).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // Enqueue after abort
  // =========================================================================

  describe('enqueue after abort', () => {
    it('ignores enqueue calls after stop()', async () => {
      const queue = new TTSQueue();
      queue.stop();

      queue.enqueue('Should be ignored');
      queue.enqueue('Also ignored');

      await flushPromises();

      expect(queue._queue).toEqual([]);
      expect(mockApiPost).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // onAllDone callback
  // =========================================================================

  describe('onAllDone callback', () => {
    it('fires when queue is empty and no item is playing', async () => {
      const onDone = vi.fn();
      const queue = new TTSQueue();
      queue.onAllDone(onDone);

      queue.enqueue('Solo');

      await flushPromises(20);

      expect(onDone).toHaveBeenCalledTimes(1);
    });

    it('does not fire if stop() is called (aborted path)', async () => {
      const onDone = vi.fn();
      const queue = new TTSQueue();
      queue.onAllDone(onDone);

      // Make API slow so we can stop before it resolves
      mockApiPost.mockImplementation(() => new Promise(() => {})); // never resolves
      queue.enqueue('Hello');
      queue.stop();

      await flushPromises();

      expect(onDone).not.toHaveBeenCalled();
    });

    it('can be set via the onAllDone() method', () => {
      const queue = new TTSQueue();
      const fn = vi.fn();
      queue.onAllDone(fn);
      expect(queue._onAllDone).toBe(fn);
    });
  });

  // =========================================================================
  // TTS API error → fallback to SpeechSynthesis
  // =========================================================================

  describe('TTS API error fallback', () => {
    it('falls back to SpeechSynthesis when API call fails', async () => {
      mockApiPost.mockRejectedValue(new Error('Network error'));

      // Make speechSynthesis.speak trigger onend immediately
      window.speechSynthesis.speak = vi.fn().mockImplementation((utterance) => {
        setTimeout(() => utterance.onend?.(), 0);
      });

      const queue = new TTSQueue();
      queue.enqueue('Fallback text');

      await flushPromises(20);

      expect(window.speechSynthesis.speak).toHaveBeenCalled();
      expect(global.SpeechSynthesisUtterance).toHaveBeenCalledWith('Fallback text');
    });

    it('falls back when audio data is too short (< 100 chars)', async () => {
      mockApiPost.mockResolvedValue({ data: { audio: 'short' } });

      window.speechSynthesis.speak = vi.fn().mockImplementation((utterance) => {
        setTimeout(() => utterance.onend?.(), 0);
      });

      const queue = new TTSQueue();
      queue.enqueue('Needs fallback');

      await flushPromises(20);

      expect(window.speechSynthesis.speak).toHaveBeenCalled();
    });

    it('falls back when audio data is null', async () => {
      mockApiPost.mockResolvedValue({ data: { audio: null } });

      window.speechSynthesis.speak = vi.fn().mockImplementation((utterance) => {
        setTimeout(() => utterance.onend?.(), 0);
      });

      const queue = new TTSQueue();
      queue.enqueue('Needs fallback');

      await flushPromises(20);

      expect(window.speechSynthesis.speak).toHaveBeenCalled();
    });
  });

  // =========================================================================
  // Audio error handling
  // =========================================================================

  describe('audio playback errors', () => {
    it('continues to next item when Audio.play() rejects', async () => {
      // First call: play rejects, second call: normal
      let callCount = 0;
      global.Audio = vi.fn().mockImplementation(() => {
        callCount++;
        const instance = createMockAudio();
        if (callCount === 1) {
          instance.play = vi.fn().mockRejectedValue(new Error('autoplay blocked'));
        } else {
          instance.play = vi.fn().mockImplementation(() => {
            setTimeout(() => instance._fireEnded(), 0);
            return Promise.resolve();
          });
        }
        return instance;
      });

      const queue = new TTSQueue();
      queue.enqueue('First');
      queue.enqueue('Second');

      await flushPromises(30);

      // Both items should have been attempted via the API
      expect(mockApiPost).toHaveBeenCalledTimes(2);
    });
  });
});
