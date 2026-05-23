/**
 * useAriaChat — Aria conversation state.
 *
 * Loads existing history on mount, exposes `ask` for new turns, and keeps
 * a `thinking` flag for the typing indicator. Also surfaces follow-up
 * suggestions from Aria's last response so the panel can render chips.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { posApi } from '../api';
import type {
  AskResponse,
  Confidence,
  QAMessageResponse,
  Source,
} from '../types';

export interface UIMessage {
  id?: number; // server id (undefined for optimistic borrower turns)
  role: 'borrower' | 'aria';
  content: string;
  sources?: Source[];
  followUps?: string[];
  confidence?: Confidence | string;
  createdAt?: string;
  isOptimistic?: boolean;
}

export function useAriaChat(applicationId: string | undefined, currentStep?: string) {
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [thinking, setThinking] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inFlight = useRef<AbortController | null>(null);

  // ---------- load history ----------

  useEffect(() => {
    if (!applicationId) return;
    let cancelled = false;

    (async () => {
      setLoading(true);
      try {
        const [history, ctx] = await Promise.all([
          posApi.getQAHistory(applicationId),
          posApi.getAriaContext(applicationId).catch(() => null),
        ]);
        if (cancelled) return;
        const ui = history.messages.map(toUIMessage);
        if (ui.length === 0) {
          ui.push(buildSeedGreeting(currentStep, ctx?.borrower_name, ctx?.lo_name));
        }
        setMessages(ui);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load history');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      inFlight.current?.abort();
    };
  }, [applicationId]);

  // ---------- ask ----------

  const ask = useCallback(
    async (text: string) => {
      if (!applicationId || !text.trim() || thinking) return;

      const trimmed = text.trim();

      // Optimistic borrower turn.
      setMessages(prev => [
        ...prev,
        {
          role: 'borrower',
          content: trimmed,
          isOptimistic: true,
        },
      ]);
      setThinking(true);
      setError(null);

      try {
        // Abort any previous in-flight request.
        inFlight.current?.abort();
        const controller = new AbortController();
        inFlight.current = controller;

        const result: AskResponse = await posApi.ask(
          {
            application_id: applicationId,
            message: trimmed,
            current_step: currentStep ?? null,
          },
          controller.signal,
        );

        setMessages(prev => [
          // Replace the optimistic stub with a confirmed one (no id on borrower
          // side from server, so we just clear the flag).
          ...prev.map(m =>
            m.isOptimistic && m.role === 'borrower' && m.content === trimmed
              ? { ...m, isOptimistic: false }
              : m,
          ),
          {
            id: result.message_id,
            role: 'aria',
            content: result.content,
            sources: result.sources,
            followUps: result.follow_ups,
            confidence: result.confidence,
            createdAt: result.created_at,
          },
        ]);
      } catch (e) {
        // Silently ignore aborted requests.
        if (e instanceof DOMException && e.name === 'AbortError') return;
        // Remove the optimistic borrower turn on error.
        setMessages(prev => prev.filter(m => !m.isOptimistic));
        setError(e instanceof Error ? e.message : 'Aria is unavailable');
      } finally {
        setThinking(false);
      }
    },
    [applicationId, currentStep, thinking],
  );

  return {
    messages,
    thinking,
    loading,
    error,
    ask,
  };
}

function toUIMessage(m: QAMessageResponse): UIMessage {
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    sources: m.sources ?? undefined,
    followUps: m.follow_ups ?? undefined,
    confidence: m.confidence ?? undefined,
    createdAt: m.created_at,
  };
}

function buildSeedGreeting(currentStep?: string, borrowerName?: string | null, loName?: string | null): UIMessage {
  const nameGreeting = borrowerName ? `Hi ${borrowerName}!` : 'Hi!';
  const stepLine = currentStep
    ? `You're on the ${prettyStep(currentStep)} step. `
    : '';
  const loLine = loName
    ? `If I'm not sure about something, I'll loop in ${loName} directly.`
    : "If I'm not sure about something, I'll loop in your loan officer.";
  return {
    role: 'aria',
    content:
      `${nameGreeting} I'm Aria, your AI loan assistant. I can answer questions about ` +
      "your application, mortgage guidelines, or what comes next. " +
      stepLine +
      loLine,
    sources: [],
    followUps: [
      'How are my numbers looking?',
      'Can I use gift funds?',
      "What's left to do?",
      'Will I need PMI?',
    ],
  };
}

function prettyStep(key: string): string {
  return (
    {
      personal: 'Personal Info',
      residence: 'Residence',
      employment: 'Employment',
      assets: 'Assets',
      liabilities: 'Liabilities',
      reo: 'Real Estate',
      loan: 'Loan & Property',
      declarations: 'Declarations',
      review: 'Review & eSign',
    }[key] || key
  );
}
