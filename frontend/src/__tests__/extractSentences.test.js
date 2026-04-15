/**
 * extractSentences — Unit tests for the sentence-splitting helper used by
 * Aria's streaming TTS pipeline.
 *
 * The function lives inside AriaVoiceHome.jsx and is not exported, so we
 * reproduce the exact implementation here (same regex + logic) and test it
 * in isolation.
 */

import { describe, it, expect } from 'vitest';

// ---------------------------------------------------------------------------
// Reproduce the implementation (same as AriaVoiceHome.jsx)
// ---------------------------------------------------------------------------

const SENTENCE_END = /(?<=[.!?])\s+|(?<=\n)/;

function extractSentences(buffer) {
  const parts = buffer.split(SENTENCE_END);
  if (parts.length <= 1) return { sentences: [], leftover: buffer };
  const leftover = parts.pop();
  return { sentences: parts.filter(Boolean), leftover };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('extractSentences', () => {
  // =========================================================================
  // Simple sentence endings
  // =========================================================================

  describe('period-terminated sentences', () => {
    it('splits a single complete sentence from trailing text', () => {
      const { sentences, leftover } = extractSentences('Hello there. How are');
      expect(sentences).toEqual(['Hello there.']);
      expect(leftover).toBe('How are');
    });

    it('returns the first sentence with empty leftover when text ends after period+space', () => {
      const { sentences, leftover } = extractSentences('Hello there. ');
      expect(sentences).toEqual(['Hello there.']);
      expect(leftover).toBe('');
    });
  });

  describe('multiple sentences', () => {
    it('splits first sentence and keeps second as leftover when second is incomplete', () => {
      const { sentences, leftover } = extractSentences('First sentence. Second sentence.');
      // "Second sentence." has no trailing space, so it stays as leftover
      expect(sentences).toEqual(['First sentence.']);
      expect(leftover).toBe('Second sentence.');
    });

    it('splits two complete sentences when both are followed by text', () => {
      const { sentences, leftover } = extractSentences('First. Second. Third');
      expect(sentences).toEqual(['First.', 'Second.']);
      expect(leftover).toBe('Third');
    });

    it('splits three complete sentences', () => {
      const { sentences, leftover } = extractSentences('A. B. C. D');
      expect(sentences).toEqual(['A.', 'B.', 'C.']);
      expect(leftover).toBe('D');
    });
  });

  // =========================================================================
  // Question marks
  // =========================================================================

  describe('question marks', () => {
    it('splits on question mark followed by space', () => {
      const { sentences, leftover } = extractSentences("How are you? I'm fine");
      expect(sentences).toEqual(['How are you?']);
      expect(leftover).toBe("I'm fine");
    });

    it('handles question mark at end without trailing space', () => {
      const { sentences, leftover } = extractSentences('How are you?');
      expect(sentences).toEqual([]);
      expect(leftover).toBe('How are you?');
    });
  });

  // =========================================================================
  // Exclamation marks
  // =========================================================================

  describe('exclamation marks', () => {
    it('splits on exclamation mark followed by space', () => {
      const { sentences, leftover } = extractSentences("Great news! You're approved");
      expect(sentences).toEqual(['Great news!']);
      expect(leftover).toBe("You're approved");
    });

    it('handles mixed punctuation', () => {
      const { sentences, leftover } = extractSentences('Wow! Really? Yes. Done');
      expect(sentences).toEqual(['Wow!', 'Really?', 'Yes.']);
      expect(leftover).toBe('Done');
    });
  });

  // =========================================================================
  // No sentence ending
  // =========================================================================

  describe('no sentence boundary', () => {
    it('returns empty sentences and full text as leftover for partial text', () => {
      const { sentences, leftover } = extractSentences('partial text without');
      expect(sentences).toEqual([]);
      expect(leftover).toBe('partial text without');
    });

    it('returns empty sentences for a single word', () => {
      const { sentences, leftover } = extractSentences('Hello');
      expect(sentences).toEqual([]);
      expect(leftover).toBe('Hello');
    });
  });

  // =========================================================================
  // Newline splitting
  // =========================================================================

  describe('newline splitting', () => {
    it('splits on newline character (newline stays with preceding fragment)', () => {
      // The lookbehind (?<=\n) splits *after* \n, so \n remains in the left part
      const { sentences, leftover } = extractSentences('Line one\nLine two');
      expect(sentences).toEqual(['Line one\n']);
      expect(leftover).toBe('Line two');
    });

    it('splits on multiple newlines', () => {
      const { sentences, leftover } = extractSentences('A\nB\nC');
      expect(sentences).toEqual(['A\n', 'B\n']);
      expect(leftover).toBe('C');
    });

    it('does not split when newline is at the very end with nothing after it', () => {
      // "Line one\n".split(regex) yields ["Line one\n"] — only 1 part,
      // so parts.length <= 1 returns no sentences (whole buffer is leftover)
      const { sentences, leftover } = extractSentences('Line one\n');
      expect(sentences).toEqual([]);
      expect(leftover).toBe('Line one\n');
    });
  });

  // =========================================================================
  // Empty string
  // =========================================================================

  describe('empty string', () => {
    it('returns empty sentences and empty leftover', () => {
      const { sentences, leftover } = extractSentences('');
      expect(sentences).toEqual([]);
      expect(leftover).toBe('');
    });
  });

  // =========================================================================
  // Abbreviations
  // =========================================================================

  describe('abbreviations (regex-based limitations)', () => {
    it('splits on abbreviation period when followed by space (known limitation)', () => {
      // The regex splits on ANY period+space, so "Dr. " triggers a split.
      // This is a known trade-off for streaming TTS — speed over perfection.
      const { sentences, leftover } = extractSentences('Dr. Smith is here.');
      expect(sentences).toEqual(['Dr.']);
      expect(leftover).toBe('Smith is here.');
    });

    it('does not split abbreviation without trailing space', () => {
      const { sentences, leftover } = extractSentences('Dr.Smith');
      expect(sentences).toEqual([]);
      expect(leftover).toBe('Dr.Smith');
    });
  });

  // =========================================================================
  // Edge cases
  // =========================================================================

  describe('edge cases', () => {
    it('handles multiple spaces after punctuation', () => {
      const { sentences, leftover } = extractSentences('Hello.  World');
      // The regex splits on one or more spaces after punctuation
      expect(sentences.length).toBeGreaterThanOrEqual(1);
      expect(sentences[0]).toBe('Hello.');
    });

    it('handles text with only punctuation', () => {
      const { sentences, leftover } = extractSentences('...');
      expect(sentences).toEqual([]);
      expect(leftover).toBe('...');
    });

    it('filters out empty string fragments', () => {
      const { sentences } = extractSentences('Hello. World. ');
      // .filter(Boolean) should remove any empty strings from split artifacts
      sentences.forEach((s) => {
        expect(s).toBeTruthy();
      });
    });

    it('handles sentence ending at very end with trailing space', () => {
      const { sentences, leftover } = extractSentences('Done. ');
      expect(sentences).toEqual(['Done.']);
      expect(leftover).toBe('');
    });

    it('handles mixed newlines and punctuation', () => {
      const { sentences, leftover } = extractSentences('Hello.\nWorld! Next');
      expect(sentences.length).toBeGreaterThanOrEqual(2);
      expect(leftover).toBe('Next');
    });
  });
});
