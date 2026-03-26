import { useRef, useCallback } from 'react';

/**
 * Custom hook for voice audio capture and playback.
 * Manages AudioContext, microphone stream, audio queue, and PCM encoding.
 */
const useVoiceAudio = ({ wsRef, onStatusChange }) => {
  const audioContextRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const processorRef = useRef(null);
  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);
  // Track the current status locally so the audio-process callback has a stable
  // reference without needing to close over React state (which would go stale).
  const statusRef = useRef('idle');

  // Keep statusRef in sync — callers should invoke this whenever status changes.
  const setStatusRef = useCallback((s) => {
    statusRef.current = s;
  }, []);

  // Initialize audio context
  const initAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 16000,
      });
    }
    return audioContextRef.current;
  }, []);

  // Convert Float32Array to Int16Array (linear16 PCM)
  const floatTo16BitPCM = (float32Array) => {
    const int16Array = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return int16Array;
  };

  // Play next audio buffer in the queue
  const playNextInQueue = useCallback(() => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      onStatusChange('listening');
      return;
    }
    isPlayingRef.current = true;
    onStatusChange('speaking');
    const audioBuffer = audioQueueRef.current.shift();
    const audioContext = audioContextRef.current;
    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);
    source.onended = playNextInQueue;
    source.start();
  }, [onStatusChange]);

  // Decode base64 linear16 audio and enqueue for playback
  const playAudioChunk = useCallback(
    async (base64Audio) => {
      try {
        const audioContext = initAudioContext();
        const binaryString = atob(base64Audio);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }
        const int16Array = new Int16Array(bytes.buffer);
        const float32Array = new Float32Array(int16Array.length);
        for (let i = 0; i < int16Array.length; i++) {
          float32Array[i] = int16Array[i] / 32768.0;
        }
        const audioBuffer = audioContext.createBuffer(1, float32Array.length, 16000);
        audioBuffer.copyToChannel(float32Array, 0);
        audioQueueRef.current.push(audioBuffer);
        if (!isPlayingRef.current) {
          playNextInQueue();
        }
      } catch (err) {
        console.error('Error playing audio:', err);
      }
    },
    [initAudioContext, playNextInQueue],
  );

  // Start microphone capture and stream PCM over WebSocket
  const startCapture = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      mediaStreamRef.current = stream;
      const audioContext = initAudioContext();

      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }

      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        if (
          wsRef.current?.readyState === WebSocket.OPEN &&
          statusRef.current === 'listening'
        ) {
          const float32Data = e.inputBuffer.getChannelData(0);
          const int16Data = floatTo16BitPCM(float32Data);
          const base64Audio = btoa(
            String.fromCharCode(...new Uint8Array(int16Data.buffer)),
          );
          wsRef.current.send(
            JSON.stringify({ type: 'audio', data: base64Audio }),
          );
        }
      };

      source.connect(processor);
      processor.connect(audioContext.destination);
      onStatusChange('listening');
    } catch (err) {
      console.error('Microphone error:', err);
      throw err; // Let caller handle UI error state
    }
  }, [initAudioContext, wsRef, onStatusChange]);

  // Stop microphone capture and clean up audio resources
  const stopCapture = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    audioQueueRef.current = [];
    isPlayingRef.current = false;
  }, []);

  // Full cleanup (including AudioContext) — call on unmount
  const cleanup = useCallback(() => {
    stopCapture();
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
  }, [stopCapture]);

  return {
    startCapture,
    stopCapture,
    playAudioChunk,
    cleanup,
    setStatusRef,
  };
};

export default useVoiceAudio;
