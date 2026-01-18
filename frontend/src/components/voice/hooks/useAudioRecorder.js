// Audio recorder hook for capturing microphone input and playing TTS audio
import { useState, useRef, useCallback, useEffect } from 'react';

const SAMPLE_RATE = 16000; // 16kHz for Deepgram STT

const useAudioRecorder = ({ onAudioChunk, enabled = true }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [hasPermission, setHasPermission] = useState(null);
  const [error, setError] = useState(null);

  const audioContextRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const processorRef = useRef(null);
  const sourceRef = useRef(null);
  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);

  // Convert Float32Array to Int16Array (linear16)
  const floatTo16BitPCM = useCallback((float32Array) => {
    const int16Array = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return int16Array;
  }, []);

  // Initialize audio context
  const initAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: SAMPLE_RATE
      });
    }
    return audioContextRef.current;
  }, []);

  // Request microphone permission and start recording
  const startRecording = useCallback(async () => {
    if (!enabled) return;

    setError(null);

    try {
      console.log('[useAudioRecorder] Requesting microphone access...');

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      setHasPermission(true);
      mediaStreamRef.current = stream;

      const audioContext = initAudioContext();

      // Resume audio context if suspended (required for some browsers)
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }

      // Create audio processing pipeline
      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;

      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        if (isRecording) {
          const float32Data = e.inputBuffer.getChannelData(0);
          const int16Data = floatTo16BitPCM(float32Data);
          const base64Audio = btoa(String.fromCharCode(...new Uint8Array(int16Data.buffer)));

          onAudioChunk?.(base64Audio);
        }
      };

      source.connect(processor);
      processor.connect(audioContext.destination);

      setIsRecording(true);
      console.log('[useAudioRecorder] Recording started');

    } catch (err) {
      console.error('[useAudioRecorder] Error starting recording:', err);

      if (err.name === 'NotAllowedError') {
        setHasPermission(false);
        setError('Microphone access denied. Please allow microphone access in your browser settings.');
      } else if (err.name === 'NotFoundError') {
        setError('No microphone found. Please connect a microphone and try again.');
      } else {
        setError(`Failed to start recording: ${err.message}`);
      }
    }
  }, [enabled, initAudioContext, floatTo16BitPCM, onAudioChunk, isRecording]);

  // Stop recording
  const stopRecording = useCallback(() => {
    console.log('[useAudioRecorder] Stopping recording...');

    setIsRecording(false);

    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }
  }, []);

  // Play audio from base64 MP3 data
  const playAudio = useCallback(async (base64Audio, format = 'mp3') => {
    try {
      const audioContext = initAudioContext();

      // Resume audio context if suspended
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }

      // Decode base64 to ArrayBuffer
      const binaryString = atob(base64Audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Decode audio data
      const audioBuffer = await audioContext.decodeAudioData(bytes.buffer.slice(0));

      // Queue the audio
      audioQueueRef.current.push(audioBuffer);

      // Play if not already playing
      if (!isPlayingRef.current) {
        playNextInQueue();
      }

    } catch (err) {
      console.error('[useAudioRecorder] Error playing audio:', err);
    }
  }, [initAudioContext]);

  // Play next audio in queue
  const playNextInQueue = useCallback(() => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      return;
    }

    isPlayingRef.current = true;
    const audioBuffer = audioQueueRef.current.shift();
    const audioContext = audioContextRef.current;

    if (!audioContext) {
      isPlayingRef.current = false;
      return;
    }

    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);
    source.onended = playNextInQueue;
    source.start();
  }, []);

  // Clear audio queue and stop playback
  const stopPlayback = useCallback(() => {
    audioQueueRef.current = [];
    isPlayingRef.current = false;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopRecording();
      stopPlayback();

      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }
    };
  }, [stopRecording, stopPlayback]);

  return {
    isRecording,
    hasPermission,
    error,
    startRecording,
    stopRecording,
    playAudio,
    stopPlayback,
    isPlaying: isPlayingRef.current
  };
};

export default useAudioRecorder;
