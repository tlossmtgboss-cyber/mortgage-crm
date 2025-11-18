// voice-orchestrator/src/voice/stt.ts
// Streaming Speech-to-Text Service

import { createClient, LiveTranscriptionEvents } from '@deepgram/sdk';
import OpenAI from 'openai';
import { logger } from '../utils/logger';

export interface TranscriptResult {
  text: string;
  isFinal: boolean;
  confidence: number;
}

export class StreamingSTT {
  private client: any;
  private provider: string;
  private openaiClient?: OpenAI;

  constructor(provider: string = 'openai') {
    this.provider = provider;

    if (provider === 'deepgram') {
      this.client = createClient(process.env.DEEPGRAM_API_KEY!);
    } else if (provider === 'openai') {
      this.openaiClient = new OpenAI({
        apiKey: process.env.OPENAI_API_KEY!
      });
    }
  }

  async process(audioChunk: Buffer): Promise<TranscriptResult | null> {
    if (this.provider === 'deepgram') {
      return this.processDeepgram(audioChunk);
    } else if (this.provider === 'openai') {
      return this.processOpenAI(audioChunk);
    }

    throw new Error(`Unsupported STT provider: ${this.provider}`);
  }

  private async processDeepgram(audioChunk: Buffer): Promise<TranscriptResult | null> {
    try {
      // For streaming, we'd maintain a persistent connection
      // This is a simplified version - in production, you'd maintain the connection
      const connection = this.client.listen.live({
        model: 'nova-2',
        language: 'en-US',
        smart_format: true,
        punctuate: true,
        interim_results: true,
        endpointing: 300,
        vad_events: true,
        encoding: 'mulaw',
        sample_rate: 8000,
        channels: 1
      });

      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          connection.finish();
          resolve(null);
        }, 5000);

        connection.on(LiveTranscriptionEvents.Transcript, (data: any) => {
          clearTimeout(timeout);

          const transcript = data.channel.alternatives[0].transcript;
          const confidence = data.channel.alternatives[0].confidence;

          if (transcript && transcript.length > 0) {
            resolve({
              text: transcript,
              isFinal: data.is_final,
              confidence: confidence || 0.9
            });
          } else {
            resolve(null);
          }

          connection.finish();
        });

        connection.on(LiveTranscriptionEvents.Error, (error: any) => {
          clearTimeout(timeout);
          logger.error('Deepgram STT error', { error });
          reject(error);
        });

        // Send audio chunk
        connection.send(audioChunk);
      });
    } catch (error) {
      logger.error('STT processing error', { error });
      return null;
    }
  }

  private async processOpenAI(audioChunk: Buffer): Promise<TranscriptResult | null> {
    try {
      if (!this.openaiClient) {
        throw new Error('OpenAI client not initialized');
      }

      // Convert buffer to File object for OpenAI API
      const audioFile = new File([audioChunk], 'audio.wav', { type: 'audio/wav' });

      const transcription = await this.openaiClient.audio.transcriptions.create({
        file: audioFile,
        model: 'whisper-1',
        language: 'en',
        response_format: 'verbose_json'
      });

      if (transcription.text && transcription.text.length > 0) {
        return {
          text: transcription.text,
          isFinal: true, // OpenAI Whisper doesn't support streaming, so always final
          confidence: 0.95 // OpenAI doesn't provide confidence, use default high value
        };
      }

      return null;
    } catch (error) {
      logger.error('OpenAI Whisper STT error', { error });
      return null;
    }
  }

  /**
   * Create a persistent streaming connection for real-time transcription
   */
  createPersistentStream(onTranscript: (result: TranscriptResult) => void) {
    if (this.provider === 'deepgram') {
      const connection = this.client.listen.live({
        model: 'nova-2',
        language: 'en-US',
        smart_format: true,
        punctuate: true,
        interim_results: true,
        endpointing: 300,
        vad_events: true,
        encoding: 'mulaw',
        sample_rate: 8000,
        channels: 1
      });

      connection.on(LiveTranscriptionEvents.Transcript, (data: any) => {
        const transcript = data.channel.alternatives[0].transcript;
        const confidence = data.channel.alternatives[0].confidence;

        if (transcript && transcript.length > 0) {
          onTranscript({
            text: transcript,
            isFinal: data.is_final,
            confidence: confidence || 0.9
          });
        }
      });

      connection.on(LiveTranscriptionEvents.Error, (error: any) => {
        logger.error('Deepgram streaming error', { error });
      });

      return {
        send: (audioChunk: Buffer) => connection.send(audioChunk),
        close: () => connection.finish()
      };
    } else if (this.provider === 'openai') {
      // OpenAI Whisper doesn't support true streaming, so we buffer audio chunks
      let audioBuffer: Buffer[] = [];
      let isProcessing = false;

      return {
        send: async (audioChunk: Buffer) => {
          audioBuffer.push(audioChunk);

          // Process every ~1 second of audio (8000 samples for mulaw 8kHz)
          if (!isProcessing && audioBuffer.length >= 8) {
            isProcessing = true;
            const combinedAudio = Buffer.concat(audioBuffer);
            audioBuffer = [];

            const result = await this.processOpenAI(combinedAudio);
            if (result) {
              onTranscript(result);
            }
            isProcessing = false;
          }
        },
        close: async () => {
          // Process any remaining audio
          if (audioBuffer.length > 0) {
            const combinedAudio = Buffer.concat(audioBuffer);
            const result = await this.processOpenAI(combinedAudio);
            if (result) {
              onTranscript(result);
            }
          }
        }
      };
    }

    throw new Error(`Unsupported STT provider: ${this.provider}`);
  }
}
