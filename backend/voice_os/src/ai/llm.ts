// voice-orchestrator/src/ai/llm.ts
// LLM Client with Streaming Support

import OpenAI from 'openai';
import Anthropic from '@anthropic-ai/sdk';
import { logger } from '../utils/logger';

export class LLMClient {
  private provider: string;
  private model: string;
  private systemPrompt: string;
  private openai?: OpenAI;
  private anthropic?: Anthropic;

  constructor(model: string = 'gpt-4-turbo', systemPrompt: string = '') {
    this.model = model;
    this.systemPrompt = systemPrompt;

    // Determine provider from model name
    if (model.startsWith('gpt-') || model.startsWith('o1-')) {
      this.provider = 'openai';
      this.openai = new OpenAI({
        apiKey: process.env.OPENAI_API_KEY!
      });
    } else if (model.startsWith('claude-')) {
      this.provider = 'anthropic';
      this.anthropic = new Anthropic({
        apiKey: process.env.ANTHROPIC_API_KEY!
      });
    } else {
      throw new Error(`Unsupported model: ${model}`);
    }
  }

  async *streamCompletion(params: CompletionParams): AsyncGenerator<StreamChunk> {
    if (this.provider === 'openai') {
      yield* this.streamOpenAI(params);
    } else if (this.provider === 'anthropic') {
      yield* this.streamAnthropic(params);
    }
  }

  private async *streamOpenAI(params: CompletionParams): AsyncGenerator<StreamChunk> {
    try {
      const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [
        { role: 'system', content: this.systemPrompt },
        ...params.messages.map(m => ({
          role: m.role as 'user' | 'assistant' | 'system',
          content: m.content
        }))
      ];

      const tools: OpenAI.Chat.ChatCompletionTool[] = params.tools?.map(tool => ({
        type: 'function',
        function: {
          name: tool.name,
          description: tool.description,
          parameters: tool.parameters
        }
      })) || [];

      const stream = await this.openai!.chat.completions.create({
        model: this.model,
        messages,
        tools: tools.length > 0 ? tools : undefined,
        temperature: params.temperature || 0.7,
        max_tokens: params.max_tokens || 1000,
        stream: true
      });

      for await (const chunk of stream) {
        const delta = chunk.choices[0]?.delta;

        if (delta?.content) {
          yield {
            type: 'text',
            text: delta.content
          };
        }

        if (delta?.tool_calls) {
          for (const toolCall of delta.tool_calls) {
            if (toolCall.function) {
              yield {
                type: 'tool_call',
                name: toolCall.function.name || '',
                arguments: JSON.parse(toolCall.function.arguments || '{}')
              };
            }
          }
        }
      }
    } catch (error) {
      logger.error('OpenAI streaming error', { error });
      throw error;
    }
  }

  private async *streamAnthropic(params: CompletionParams): AsyncGenerator<StreamChunk> {
    try {
      const messages = params.messages.map(m => ({
        role: m.role === 'user' ? 'user' as const : 'assistant' as const,
        content: m.content
      }));

      const tools = params.tools?.map(tool => ({
        name: tool.name,
        description: tool.description,
        input_schema: tool.parameters
      })) || [];

      const stream = await (this.anthropic as any).messages.stream({
        model: this.model,
        max_tokens: params.max_tokens || 1000,
        temperature: params.temperature || 0.7,
        system: this.systemPrompt,
        messages,
        tools: tools.length > 0 ? tools : undefined
      });

      for await (const event of stream) {
        if (event.type === 'content_block_delta') {
          if ('text' in event.delta) {
            yield {
              type: 'text',
              text: event.delta.text
            };
          }
        }

        if (event.type === 'content_block_start') {
          if (event.content_block.type === 'tool_use') {
            yield {
              type: 'tool_call',
              name: event.content_block.name,
              arguments: event.content_block.input
            };
          }
        }
      }
    } catch (error) {
      logger.error('Anthropic streaming error', { error });
      throw error;
    }
  }

  /**
   * Generate a complete response (non-streaming)
   */
  async generateCompletion(params: CompletionParams): Promise<string> {
    const chunks: string[] = [];

    for await (const chunk of this.streamCompletion(params)) {
      if (chunk.type === 'text') {
        chunks.push(chunk.text);
      }
    }

    return chunks.join('');
  }

  /**
   * Generate JSON response for structured data extraction
   */
  async generateJSON(prompt: string): Promise<any> {
    try {
      if (this.provider === 'openai') {
        const response = await this.openai!.chat.completions.create({
          model: this.model,
          messages: [
            { role: 'system', content: 'You are a helpful assistant that returns valid JSON.' },
            { role: 'user', content: prompt }
          ],
          response_format: { type: 'json_object' },
          temperature: 0.3
        });

        const content = response.choices[0]?.message?.content || '{}';
        return JSON.parse(content);
      } else if (this.provider === 'anthropic') {
        const response = await (this.anthropic as any).messages.create({
          model: this.model,
          max_tokens: 1000,
          messages: [
            { role: 'user', content: prompt }
          ]
        });

        const content = response.content[0];
        if (content.type === 'text') {
          // Extract JSON from text (Claude doesn't have json_object mode yet)
          const jsonMatch = content.text.match(/\{[\s\S]*\}/);
          if (jsonMatch) {
            return JSON.parse(jsonMatch[0]);
          }
        }
        throw new Error('No JSON found in response');
      }
    } catch (error) {
      logger.error('JSON generation error', { error, prompt });
      throw error;
    }
  }
}

export interface CompletionParams {
  messages: Message[];
  tools?: Tool[];
  temperature?: number;
  max_tokens?: number;
}

export interface Message {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
}

export interface Tool {
  name: string;
  description: string;
  parameters: any;
}

export type StreamChunk = {
  type: 'text';
  text: string;
} | {
  type: 'tool_call';
  name: string;
  arguments: any;
};
