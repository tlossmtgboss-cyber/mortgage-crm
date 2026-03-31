/**
 * speechService.js - Unified speech recognition for Capacitor + Web
 *
 * Uses @capacitor-community/speech-recognition on native iOS/Android,
 * falls back to Web Speech API on browsers.
 */
import { Capacitor } from '@capacitor/core';

let SpeechRecognitionPlugin = null;

// Lazy-load the native plugin only on native platforms
async function getNativePlugin() {
  if (SpeechRecognitionPlugin) return SpeechRecognitionPlugin;
  try {
    const mod = await import('@capacitor-community/speech-recognition');
    SpeechRecognitionPlugin = mod.SpeechRecognition;
    return SpeechRecognitionPlugin;
  } catch {
    return null;
  }
}

const isNative = Capacitor.isNativePlatform();

/**
 * Check if speech recognition is available on this platform
 */
export async function isAvailable() {
  if (isNative) {
    const plugin = await getNativePlugin();
    if (!plugin) return false;
    const result = await plugin.available();
    return result.available;
  }
  return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
}

/**
 * Request speech recognition permission
 * @returns {Promise<boolean>} true if granted
 */
export async function requestPermission() {
  if (isNative) {
    const plugin = await getNativePlugin();
    if (!plugin) return false;
    const result = await plugin.requestPermissions();
    return result.speechRecognition === 'granted';
  }
  // Web: permission is implicitly requested when starting
  return true;
}

/**
 * Start listening for speech.
 * @param {Object} options
 * @param {string} [options.language='en-US']
 * @param {boolean} [options.partialResults=true]
 * @param {Function} options.onPartialResult - Called with interim transcript text
 * @param {Function} options.onResult - Called with final transcript text
 * @param {Function} [options.onError] - Called with error string
 * @param {Function} [options.onEnd] - Called when recognition ends
 * @returns {Promise<{ stop: () => Promise<void> }>} Controller with stop method
 */
export async function startListening({
  language = 'en-US',
  partialResults = true,
  onPartialResult,
  onResult,
  onError,
  onEnd,
} = {}) {
  if (isNative) {
    return startNativeListening({ language, partialResults, onPartialResult, onResult, onError, onEnd });
  }
  return startWebListening({ language, partialResults, onPartialResult, onResult, onError, onEnd });
}

// -- Native (Capacitor) implementation --

async function startNativeListening({ language, partialResults, onPartialResult, onResult, onError, onEnd }) {
  const plugin = await getNativePlugin();
  if (!plugin) {
    onError?.('Speech recognition plugin not available');
    return { stop: async () => {} };
  }

  // Request permission if needed
  const hasPermission = await requestPermission();
  if (!hasPermission) {
    onError?.('Speech recognition permission denied');
    return { stop: async () => {} };
  }

  // Remove any existing listeners
  await plugin.removeAllListeners();

  // Listen for partial results
  await plugin.addListener('partialResults', (data) => {
    const text = data.matches?.[0] || data.value || '';
    if (text) {
      onPartialResult?.(text);
    }
  });

  // Start recognition
  try {
    await plugin.start({
      language,
      partialResults,
      popup: false,
    });
  } catch (err) {
    onError?.(err.message || 'Failed to start speech recognition');
    return { stop: async () => {} };
  }

  return {
    stop: async () => {
      try {
        const result = await plugin.stop();
        const finalText = result?.matches?.[0] || result?.value || '';
        if (finalText) {
          onResult?.(finalText);
        }
        onEnd?.();
      } catch {
        onEnd?.();
      }
      await plugin.removeAllListeners();
    },
  };
}

// -- Web Speech API implementation --

const MAX_RESTARTS = 5;
const RESTART_RESET_INTERVAL = 30000; // Reset counter after 30s of stable operation

function startWebListening({ language, partialResults, onPartialResult, onResult, onError, onEnd }) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    onError?.('Speech recognition not supported in this browser');
    return Promise.resolve({ stop: async () => {} });
  }

  const recognition = new SR();
  recognition.continuous = true;
  recognition.interimResults = partialResults;
  recognition.lang = language;
  recognition.maxAlternatives = 1;
  let stopped = false;
  let restartCount = 0;
  let restartResetTimer = null;

  recognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      if (result.isFinal) {
        onResult?.(result[0].transcript.trim());
      } else {
        onPartialResult?.(result[0].transcript);
      }
    }
  };

  recognition.onerror = (event) => {
    if (event.error === 'aborted' || event.error === 'no-speech') return;
    onError?.(event.error);
  };

  recognition.onend = () => {
    if (!stopped) {
      // Auto-restart on mobile Safari which stops recognition spontaneously
      restartCount++;

      if (restartCount > MAX_RESTARTS) {
        console.error('[SpeechService] Max restart attempts reached (' + MAX_RESTARTS + '). Stopping auto-restart.');
        clearTimeout(restartResetTimer);
        restartCount = 0;
        onError?.('Speech recognition failed after ' + MAX_RESTARTS + ' restart attempts');
        onEnd?.();
        return;
      }

      console.warn('[SpeechService] Restarting speech recognition (attempt ' + restartCount + '/' + MAX_RESTARTS + ')');

      // Reset counter after stable operation
      clearTimeout(restartResetTimer);
      restartResetTimer = setTimeout(() => {
        restartCount = 0;
      }, RESTART_RESET_INTERVAL);

      try { recognition.start(); } catch { onEnd?.(); }
    } else {
      clearTimeout(restartResetTimer);
      onEnd?.();
    }
  };

  try {
    recognition.start();
  } catch (err) {
    onError?.(err.message || 'Failed to start speech recognition');
    return Promise.resolve({ stop: async () => {} });
  }

  return Promise.resolve({
    stop: async () => {
      stopped = true;
      clearTimeout(restartResetTimer);
      restartCount = 0;
      try { recognition.stop(); } catch {}
    },
  });
}

export default { isAvailable, requestPermission, startListening };
