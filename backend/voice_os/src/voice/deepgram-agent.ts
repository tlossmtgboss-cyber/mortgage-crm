// voice-orchestrator/src/voice/deepgram-agent.ts
// Deepgram Voice Agent API - All-in-one STT + LLM + TTS
// Replaces separate stt.ts, llm.ts, and tts.ts with unified solution

import WebSocket from 'ws';
import { logger } from '../utils/logger';

export interface VoiceAgentConfig {
  systemPrompt: string;
  voiceModel?: string;
  llmModel?: string;
  sttModel?: string;
  greeting?: string;
}

export interface VoiceAgentCallbacks {
  onTranscript?: (text: string, isFinal: boolean) => void;
  onResponse?: (text: string) => void;
  onAudio?: (audioBuffer: Buffer) => void;
  onSpeechComplete?: () => void;
  onError?: (error: string) => void;
  onReady?: () => void;
}

export class DeepgramVoiceAgent {
  private ws: WebSocket | null = null;
  private isConnected = false;
  private config: VoiceAgentConfig;
  private callbacks: VoiceAgentCallbacks;

  constructor(config: VoiceAgentConfig, callbacks: VoiceAgentCallbacks) {
    this.config = config;
    this.callbacks = callbacks;
  }

  async connect(): Promise<boolean> {
    const apiKey = process.env.DEEPGRAM_API_KEY;
    if (!apiKey) {
      logger.error('[DeepgramAgent] No API key configured');
      this.callbacks.onError?.('Deepgram API key not configured');
      return false;
    }

    return new Promise((resolve) => {
      try {
        logger.info('[DeepgramAgent] Connecting to Deepgram Voice Agent API...');

        this.ws = new WebSocket('wss://agent.deepgram.com/agent', {
          headers: {
            'Authorization': `Token ${apiKey}`
          }
        });

        const timeout = setTimeout(() => {
          if (!this.isConnected) {
            logger.error('[DeepgramAgent] Connection timeout');
            this.callbacks.onError?.('Connection timeout');
            this.ws?.close();
            resolve(false);
          }
        }, 15000);

        this.ws.on('open', () => {
          logger.info('[DeepgramAgent] WebSocket connected, sending configuration...');
          this.sendConfiguration();
        });

        this.ws.on('message', (data: Buffer | string) => {
          this.handleMessage(data, timeout, resolve);
        });

        this.ws.on('error', (error) => {
          logger.error('[DeepgramAgent] WebSocket error:', error);
          clearTimeout(timeout);
          this.callbacks.onError?.(error.message);
          resolve(false);
        });

        this.ws.on('close', (code, reason) => {
          logger.info('[DeepgramAgent] WebSocket closed:', code, reason.toString());
          this.isConnected = false;
          clearTimeout(timeout);
        });

      } catch (error: any) {
        logger.error('[DeepgramAgent] Connection error:', error);
        this.callbacks.onError?.(error.message);
        resolve(false);
      }
    });
  }

  private sendConfiguration(): void {
    if (!this.ws) return;

    const config = {
      type: 'SettingsConfiguration',
      audio: {
        input: {
          encoding: 'mulaw',  // Twilio uses mulaw
          sample_rate: 8000   // Twilio uses 8kHz
        },
        output: {
          encoding: 'mulaw',  // Match Twilio format
          sample_rate: 8000,
          container: 'none'
        }
      },
      agent: {
        listen: {
          model: this.config.sttModel || 'nova-2'
        },
        think: {
          provider: {
            type: 'anthropic'
          },
          model: this.config.llmModel || 'claude-3-haiku-20240307',
          instructions: this.config.systemPrompt
        },
        speak: {
          model: this.config.voiceModel || 'aura-asteria-en'
        }
      }
    };

    this.ws.send(JSON.stringify(config));
    logger.info('[DeepgramAgent] Sent configuration');
  }

  private handleMessage(data: Buffer | string, timeout: NodeJS.Timeout, resolveConnect: (value: boolean) => void): void {
    // Check if binary (audio) or text (JSON)
    if (Buffer.isBuffer(data)) {
      // Audio data from TTS
      this.callbacks.onAudio?.(data);
      return;
    }

    try {
      const message = JSON.parse(data.toString());
      const msgType = message.type;

      logger.debug('[DeepgramAgent] Received:', msgType);

      switch (msgType) {
        case 'Welcome':
          logger.info('[DeepgramAgent] Welcome received');
          break;

        case 'SettingsApplied':
          logger.info('[DeepgramAgent] Settings applied, ready for audio');
          clearTimeout(timeout);
          this.isConnected = true;
          this.callbacks.onReady?.();
          resolveConnect(true);
          break;

        case 'ConversationText':
          const role = message.role;
          const content = message.content;

          if (role === 'user') {
            this.callbacks.onTranscript?.(content, true);
          } else if (role === 'assistant') {
            this.callbacks.onResponse?.(content);
          }
          break;

        case 'UserStartedSpeaking':
          logger.debug('[DeepgramAgent] User started speaking');
          break;

        case 'AgentThinking':
          logger.debug('[DeepgramAgent] Agent thinking...');
          break;

        case 'AgentStartedSpeaking':
          logger.debug('[DeepgramAgent] Agent started speaking');
          break;

        case 'AgentAudioDone':
          this.callbacks.onSpeechComplete?.();
          break;

        case 'Error':
          const errorMsg = message.message || 'Unknown error';
          logger.error('[DeepgramAgent] Error:', errorMsg);
          this.callbacks.onError?.(errorMsg);
          break;
      }

    } catch (error) {
      logger.warn('[DeepgramAgent] Could not parse message');
    }
  }

  /**
   * Send audio data to the voice agent
   * @param audioBuffer - Raw audio in mulaw 8kHz format (Twilio format)
   */
  sendAudio(audioBuffer: Buffer): void {
    if (this.ws && this.isConnected) {
      this.ws.send(audioBuffer);
    }
  }

  /**
   * Send text input directly (for testing or when audio is not available)
   */
  sendText(text: string): void {
    if (this.ws && this.isConnected) {
      const message = {
        type: 'InjectAgentMessage',
        message: text
      };
      this.ws.send(JSON.stringify(message));
    }
  }

  /**
   * Interrupt the agent's speech
   */
  interrupt(): void {
    if (this.ws && this.isConnected) {
      const message = { type: 'ClearPlayback' };
      this.ws.send(JSON.stringify(message));
    }
  }

  /**
   * Close the connection
   */
  close(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
      this.isConnected = false;
    }
  }

  isReady(): boolean {
    return this.isConnected;
  }
}

/**
 * Create a voice agent session for handling Twilio calls
 *
 * Voice model options for human-like speech:
 * - aura-asteria-en: Female, warm and professional (default)
 * - aura-luna-en: Female, soft and gentle
 * - aura-stella-en: Female, confident and clear
 * - aura-athena-en: Female, mature and authoritative
 * - aura-helios-en: Male, warm and friendly
 * - aura-arcas-en: Male, confident and professional
 * - aura-perseus-en: Male, deep and resonant
 */
export function createTwilioVoiceAgent(
  systemPrompt: string,
  onAudioForTwilio: (audioBase64: string) => void,
  options?: Partial<VoiceAgentConfig>
): DeepgramVoiceAgent {
  const config: VoiceAgentConfig = {
    systemPrompt,
    // aura-asteria-en is the most natural-sounding female voice for phone calls
    voiceModel: options?.voiceModel || 'aura-asteria-en',
    llmModel: options?.llmModel || 'claude-3-5-haiku-20241022',  // Updated to latest Haiku
    sttModel: options?.sttModel || 'nova-2',  // Best accuracy for phone audio
    greeting: options?.greeting
  };

  const callbacks: VoiceAgentCallbacks = {
    onAudio: (buffer) => {
      // Convert buffer to base64 for Twilio
      const base64Audio = buffer.toString('base64');
      onAudioForTwilio(base64Audio);
    },
    onTranscript: (text, isFinal) => {
      if (isFinal) {
        logger.info('[TwilioVoiceAgent] User said:', text);
      }
    },
    onResponse: (text) => {
      logger.info('[TwilioVoiceAgent] Agent said:', text);
    },
    onError: (error) => {
      logger.error('[TwilioVoiceAgent] Error:', error);
    }
  };

  return new DeepgramVoiceAgent(config, callbacks);
}
