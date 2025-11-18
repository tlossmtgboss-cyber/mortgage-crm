// voice-orchestrator/src/voice/tts.ts
// Streaming Text-to-Speech Service

import { ElevenLabsClient, stream } from 'elevenlabs';
import OpenAI from 'openai';
import { logger } from '../utils/logger';

export class StreamingTTS {
  private client: ElevenLabsClient | undefined;
  private openaiClient: OpenAI | undefined;
  private provider: string;
  private voiceId: string;

  constructor(provider: string = 'openai', voiceId: string = 'alloy') {
    this.provider = provider;
    this.voiceId = voiceId;

    if (provider === 'elevenlabs') {
      this.client = new ElevenLabsClient({
        apiKey: process.env.ELEVENLABS_API_KEY!
      });
    } else if (provider === 'openai') {
      this.openaiClient = new OpenAI({
        apiKey: process.env.OPENAI_API_KEY!
      });
    }
  }

  async synthesize(text: string, options?: SynthesizeOptions): Promise<Buffer> {
    if (this.provider === 'elevenlabs') {
      return this.synthesizeElevenLabs(text, options);
    } else if (this.provider === 'openai') {
      return this.synthesizeOpenAI(text, options);
    }

    throw new Error(`Unsupported TTS provider: ${this.provider}`);
  }

  private async synthesizeElevenLabs(text: string, options?: SynthesizeOptions): Promise<Buffer> {
    try {
      if (!this.client) {
        throw new Error('ElevenLabs client not initialized');
      }

      const audioStream = await this.client.textToSpeech.convertAsStream(this.voiceId, {
        text,
        model_id: options?.model || 'eleven_turbo_v2_5',
        voice_settings: {
          stability: options?.stability || 0.5,
          similarity_boost: options?.similarity || 0.75,
          style: options?.style || 0.5,
          use_speaker_boost: true
        },
        output_format: 'ulaw_8000' // Match Twilio format
      });

      const chunks: Buffer[] = [];
      for await (const chunk of audioStream) {
        chunks.push(chunk);
      }

      return Buffer.concat(chunks);
    } catch (error) {
      logger.error('ElevenLabs TTS error', { error, text });
      throw error;
    }
  }

  private async synthesizeOpenAI(text: string, options?: SynthesizeOptions): Promise<Buffer> {
    try {
      if (!this.openaiClient) {
        throw new Error('OpenAI client not initialized');
      }

      // OpenAI TTS available voices: alloy, echo, fable, onyx, nova, shimmer
      const response = await this.openaiClient.audio.speech.create({
        model: options?.model || 'tts-1', // or 'tts-1-hd' for higher quality
        voice: this.voiceId as 'alloy' | 'echo' | 'fable' | 'onyx' | 'nova' | 'shimmer',
        input: text,
        speed: options?.speed || 1.0,
        response_format: 'pcm' // We'll convert to mulaw for Twilio
      });

      // Convert response to buffer
      const arrayBuffer = await response.arrayBuffer();
      return Buffer.from(arrayBuffer);
    } catch (error) {
      logger.error('OpenAI TTS error', { error, text });
      throw error;
    }
  }

  /**
   * Stream audio in chunks for low-latency playback
   */
  async *synthesizeStreaming(text: string, options?: SynthesizeOptions): AsyncGenerator<Buffer> {
    if (this.provider === 'elevenlabs') {
      if (!this.client) {
        throw new Error('ElevenLabs client not initialized');
      }

      const audioStream = await this.client.textToSpeech.convertAsStream(this.voiceId, {
        text,
        model_id: options?.model || 'eleven_turbo_v2_5',
        voice_settings: {
          stability: options?.stability || 0.5,
          similarity_boost: options?.similarity || 0.75,
          style: options?.style || 0.5,
          use_speaker_boost: true
        },
        output_format: 'ulaw_8000'
      });

      for await (const chunk of audioStream) {
        yield chunk;
      }
    } else if (this.provider === 'openai') {
      // OpenAI doesn't support true streaming yet, return full audio
      const audio = await this.synthesizeOpenAI(text, options);

      // Split into chunks for streaming effect
      const chunkSize = 4096;
      for (let i = 0; i < audio.length; i += chunkSize) {
        yield audio.slice(i, i + chunkSize);
      }
    } else {
      throw new Error(`Unsupported TTS provider: ${this.provider}`);
    }
  }

  /**
   * Convert text to audio optimized for phone calls
   */
  async synthesizeForPhone(text: string): Promise<Buffer> {
    // Split into sentences for more natural pauses
    const sentences = this.splitIntoSentences(text);
    const audioChunks: Buffer[] = [];

    for (const sentence of sentences) {
      if (sentence.trim()) {
        const audio = await this.synthesize(sentence.trim(), {
          stability: 0.6, // Slightly more stable for phone calls
          similarity: 0.8
        });
        audioChunks.push(audio);

        // Add natural pause between sentences (silence)
        const pauseDuration = this.getPauseDuration(sentence);
        const silenceBuffer = Buffer.alloc(pauseDuration);
        audioChunks.push(silenceBuffer);
      }
    }

    return Buffer.concat(audioChunks);
  }

  private splitIntoSentences(text: string): string[] {
    return text.split(/(?<=[.!?])\s+/);
  }

  private getPauseDuration(sentence: string): number {
    // Longer pause after questions, shorter after statements
    if (sentence.trim().endsWith('?')) {
      return 400; // 400ms pause after questions
    } else if (sentence.trim().endsWith('!')) {
      return 300;
    } else {
      return 200; // 200ms pause after statements
    }
  }
}

export interface SynthesizeOptions {
  model?: string;
  stability?: number;
  similarity?: number;
  style?: number;
  speed?: number;
}
