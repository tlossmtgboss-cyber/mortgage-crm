/**
 * Retry Manager - Implements exponential backoff retry logic
 * Based on patterns from "Automating Microsoft 365 with Python"
 */

import { Logger } from 'winston';
import { RetryConfig } from '../types';

export class RetryManager {
  constructor(
    private readonly config: RetryConfig,
    private readonly logger: Logger
  ) {}

  /**
   * Execute a function with retry logic using exponential backoff
   */
  async executeWithRetry<T>(
    fn: () => Promise<T>,
    operationName: string
  ): Promise<T> {
    let lastError: Error | undefined;

    for (let attempt = 1; attempt <= this.config.maxRetries; attempt++) {
      try {
        return await fn();
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));

        if (attempt === this.config.maxRetries) {
          this.logger.error(`Operation failed after ${attempt} attempts`, {
            operationName,
            error: lastError.message
          });
          throw lastError;
        }

        // Calculate delay with exponential backoff
        const delay = this.calculateDelay(attempt);

        this.logger.warn(`Retry attempt ${attempt}/${this.config.maxRetries}`, {
          operationName,
          error: lastError.message,
          nextRetryMs: delay
        });

        await this.sleep(delay);
      }
    }

    // This should never be reached, but TypeScript needs it
    throw lastError || new Error('Unexpected retry failure');
  }

  /**
   * Calculate delay using exponential backoff with jitter
   */
  private calculateDelay(attempt: number): number {
    // Exponential backoff: baseDelay * (multiplier ^ attempt)
    const exponentialDelay =
      this.config.baseDelayMs * Math.pow(this.config.backoffMultiplier, attempt - 1);

    // Cap at max delay
    const cappedDelay = Math.min(exponentialDelay, this.config.maxDelayMs);

    // Add jitter (±25% randomization) to prevent thundering herd
    const jitter = cappedDelay * 0.25 * (Math.random() * 2 - 1);

    return Math.floor(cappedDelay + jitter);
  }

  /**
   * Sleep for specified milliseconds
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Check if an error is retryable
   */
  static isRetryableError(error: Error): boolean {
    const retryablePatterns = [
      'ECONNRESET',
      'ETIMEDOUT',
      'ECONNREFUSED',
      'EHOSTUNREACH',
      'ENETUNREACH',
      'rate limit',
      'Rate limit',
      '429',
      '503',
      '504',
      'temporarily unavailable',
      'try again',
      'overloaded'
    ];

    const errorMessage = error.message.toLowerCase();
    return retryablePatterns.some(pattern =>
      errorMessage.includes(pattern.toLowerCase())
    );
  }
}

/**
 * Default retry configuration
 */
export const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  baseDelayMs: 1000,
  maxDelayMs: 30000,
  backoffMultiplier: 2
};
