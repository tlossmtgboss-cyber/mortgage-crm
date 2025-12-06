/**
 * Email Processor Interface and Base Class
 * Implements the Strategy pattern for email processing
 */

import { Pool } from 'pg';
import { Logger } from 'winston';
import Anthropic from '@anthropic-ai/sdk';
import { Email, ProcessingContext, ProcessingResult } from '../types';
import { EmailTemplateService } from '../services/EmailTemplateService';

/**
 * Interface that all email processors must implement
 */
export interface IEmailProcessor {
  /** Unique name for this processor */
  readonly name: string;

  /** Priority (higher = processed first). Range: 1-100 */
  readonly priority: number;

  /** Description of what this processor handles */
  readonly description: string;

  /**
   * Determine if this processor can handle the given email
   * @param email The email to evaluate
   * @returns true if this processor should handle the email
   */
  canProcess(email: Email): Promise<boolean>;

  /**
   * Process the email
   * @param email The email to process
   * @param context Processing context with user info and metadata
   * @returns Result of processing including actions taken
   */
  process(email: Email, context: ProcessingContext): Promise<ProcessingResult>;
}

/**
 * Base class providing common functionality for email processors
 */
export abstract class BaseEmailProcessor implements IEmailProcessor {
  abstract readonly name: string;
  abstract readonly priority: number;
  abstract readonly description: string;

  constructor(
    protected readonly pool: Pool,
    protected readonly logger: Logger,
    protected readonly anthropic: Anthropic,
    protected readonly templateService: EmailTemplateService
  ) {}

  abstract canProcess(email: Email): Promise<boolean>;
  abstract process(email: Email, context: ProcessingContext): Promise<ProcessingResult>;

  /**
   * Use Claude to analyze email content
   */
  protected async analyzeWithAI(
    email: Email,
    prompt: string,
    systemPrompt?: string
  ): Promise<string> {
    try {
      const response = await this.anthropic.messages.create({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 2000,
        system: systemPrompt || 'You are an AI assistant analyzing emails for a mortgage CRM system.',
        messages: [
          {
            role: 'user',
            content: `${prompt}\n\nEmail Subject: ${email.subject}\n\nEmail Body:\n${email.body}`
          }
        ]
      });

      const textBlock = response.content.find(block => block.type === 'text');
      return textBlock ? textBlock.text : '';
    } catch (error) {
      this.logger.error('AI analysis failed', { error, emailId: email.id });
      throw error;
    }
  }

  /**
   * Extract JSON from AI response
   */
  protected parseAIResponse<T>(response: string): T | null {
    try {
      // Try to find JSON in the response
      const jsonMatch = response.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]) as T;
      }
      return null;
    } catch (error) {
      this.logger.warn('Failed to parse AI response as JSON', { response });
      return null;
    }
  }

  /**
   * Check if email is from an internal domain
   */
  protected isInternalEmail(email: Email, internalDomains: string[]): boolean {
    const fromDomain = email.from.address.split('@')[1]?.toLowerCase();
    return internalDomains.some(domain =>
      fromDomain === domain.toLowerCase()
    );
  }

  /**
   * Log processing result to database
   */
  protected async logProcessing(
    email: Email,
    context: ProcessingContext,
    result: ProcessingResult
  ): Promise<void> {
    try {
      await this.pool.query(
        `INSERT INTO email_processing_log
         (email_id, message_id, processor_name, action, success, time_saved_minutes,
          created_records, sent_emails, error, metadata, processed_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())`,
        [
          email.id,
          email.messageId,
          this.name,
          result.action,
          result.success,
          result.timeSaved,
          JSON.stringify(result.createdRecords || []),
          JSON.stringify(result.sentEmails || []),
          result.error,
          JSON.stringify(result.metadata || {})
        ]
      );
    } catch (error) {
      this.logger.error('Failed to log processing result', { error, emailId: email.id });
    }
  }

  /**
   * Create a success result
   */
  protected successResult(
    action: string,
    timeSaved: number,
    options: Partial<ProcessingResult> = {}
  ): ProcessingResult {
    return {
      success: true,
      processor: this.name,
      action,
      timeSaved,
      ...options
    };
  }

  /**
   * Create a failure result
   */
  protected failureResult(action: string, error: string): ProcessingResult {
    return {
      success: false,
      processor: this.name,
      action,
      timeSaved: 0,
      error
    };
  }
}
