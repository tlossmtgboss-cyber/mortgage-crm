// Perennia iMessage — useThread hook
// Live conversation state with optimistic sends and WebSocket reconciliation.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { imessageApi } from "../api/imessageApi";

// Stub: Perennia's WebSocket system uses a different pattern. This no-op
// hook prevents import errors. Replace with the real realtime subscription
// once the WS broadcast layer is wired into the iMessage integration.
function useRealtimeChannel<T>(_channel: string, _handler: (evt: T) => void): void {
  // no-op — realtime events will be wired later
}
import type {
  Channel,
  ConversationMessage,
  ConversationThread,
  RealtimeEvent,
  SendMessageRequest,
  SendStyle,
} from "../types";

interface UseThreadOptions {
  contactId: string;
  /** Debounce typing indicator pings to BB (default 1500ms). */
  typingDwellMs?: number;
}

interface UseThreadReturn {
  thread: ConversationThread | null;
  loading: boolean;
  error: Error | null;
  sending: boolean;
  remoteIsTyping: boolean;
  send: (input: {
    body?: string;
    mediaUrl?: string;
    channel?: Channel;
    sendStyle?: SendStyle;
    replyToMessageId?: string;
  }) => Promise<void>;
  notifyTyping: () => void;
  refresh: () => Promise<void>;
}

export function useThread({
  contactId,
  typingDwellMs = 1500,
}: UseThreadOptions): UseThreadReturn {
  const [thread, setThread] = useState<ConversationThread | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);
  const [sending, setSending] = useState<boolean>(false);
  const [remoteIsTyping, setRemoteIsTyping] = useState<boolean>(false);
  const typingTimer = useRef<number | null>(null);
  const typingPingTimer = useRef<number | null>(null);
  const typingActive = useRef<boolean>(false);

  // Initial load
  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const t = await imessageApi.getThread(contactId);
      setThread(t);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setLoading(false);
    }
  }, [contactId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Realtime: merge events into local state ----------------------------------
  useRealtimeChannel<RealtimeEvent>("imessage", (evt) => {
    if (!thread) return;
    switch (evt.type) {
      case "imessage.message.created":
        if (evt.message.contact_id !== contactId) return;
        setThread((prev) => prev && upsertMessage(prev, evt.message));
        break;
      case "imessage.message.received":
        if (evt.contact_id !== contactId) return;
        setThread((prev) => prev && upsertMessage(prev, evt.message));
        break;
      case "imessage.message.updated":
        setThread((prev) => prev && updateStatus(prev, evt));
        break;
      case "imessage.typing":
        if (thread.chat_guid && evt.chat_guid === thread.chat_guid) {
          setRemoteIsTyping(evt.display);
          if (typingTimer.current) window.clearTimeout(typingTimer.current);
          if (evt.display) {
            typingTimer.current = window.setTimeout(
              () => setRemoteIsTyping(false),
              5000,
            );
          }
        }
        break;
    }
  });

  // Send with optimistic insert ---------------------------------------------
  const send = useCallback(
    async (input: {
      body?: string;
      mediaUrl?: string;
      channel?: Channel;
      sendStyle?: SendStyle;
      replyToMessageId?: string;
    }) => {
      if (!input.body && !input.mediaUrl) return;
      setSending(true);

      const optimistic: ConversationMessage = {
        id: `optimistic-${Date.now()}`,
        contact_id: contactId,
        direction: "outbound",
        body: input.body ?? null,
        media_urls: input.mediaUrl ? [input.mediaUrl] : [],
        channel: input.channel ?? "auto",
        status: "queued",
        send_style: input.sendStyle ?? null,
        bb_message_guid: null,
        reply_to_message_id: input.replyToMessageId ?? null,
        created_at: new Date().toISOString(),
      };
      setThread((prev) => prev && upsertMessage(prev, optimistic));

      try {
        const req: SendMessageRequest = {
          contact_id: contactId,
          body: input.body ?? null,
          media_url: input.mediaUrl ?? null,
          channel: input.channel ?? "auto",
          send_style: input.sendStyle ?? null,
          reply_to_message_id: input.replyToMessageId ?? null,
        };
        const resp = await imessageApi.send(req);

        // Reconcile the optimistic row with the server-assigned id
        setThread((prev) =>
          prev
            ? {
                ...prev,
                messages: prev.messages.map((m) =>
                  m.id === optimistic.id
                    ? {
                        ...m,
                        id: resp.message_id,
                        status: resp.status,
                        bb_message_guid: resp.bb_message_guid,
                        channel: resp.channel,
                      }
                    : m,
                ),
              }
            : prev,
        );
      } catch (e) {
        // Mark optimistic row as failed
        setThread((prev) =>
          prev
            ? {
                ...prev,
                messages: prev.messages.map((m) =>
                  m.id === optimistic.id
                    ? {
                        ...m,
                        status: "failed",
                        error_message: e instanceof Error ? e.message : String(e),
                      }
                    : m,
                ),
              }
            : prev,
        );
        setError(e instanceof Error ? e : new Error(String(e)));
      } finally {
        setSending(false);
      }
    },
    [contactId],
  );

  // Typing indicator: debounced pings to keep BB's "..." alive --------------
  const notifyTyping = useCallback(() => {
    if (typingPingTimer.current) {
      window.clearTimeout(typingPingTimer.current);
    }
    if (!typingActive.current) {
      typingActive.current = true;
      void imessageApi.typing(contactId, true).catch(() => {});
    }
    typingPingTimer.current = window.setTimeout(() => {
      typingActive.current = false;
      void imessageApi.typing(contactId, false).catch(() => {});
    }, typingDwellMs);
  }, [contactId, typingDwellMs]);

  useEffect(
    () => () => {
      if (typingPingTimer.current) window.clearTimeout(typingPingTimer.current);
      if (typingTimer.current) window.clearTimeout(typingTimer.current);
    },
    [],
  );

  return useMemo(
    () => ({
      thread,
      loading,
      error,
      sending,
      remoteIsTyping,
      send,
      notifyTyping,
      refresh,
    }),
    [thread, loading, error, sending, remoteIsTyping, send, notifyTyping, refresh],
  );
}

// ---------------------------------------------------------------------------
function upsertMessage(
  thread: ConversationThread,
  msg: ConversationMessage,
): ConversationThread {
  const idx = thread.messages.findIndex(
    (m) =>
      m.id === msg.id ||
      (m.bb_message_guid && m.bb_message_guid === msg.bb_message_guid),
  );
  if (idx === -1) {
    return { ...thread, messages: [...thread.messages, msg] };
  }
  const next = thread.messages.slice();
  next[idx] = { ...next[idx], ...msg };
  return { ...thread, messages: next };
}

function updateStatus(
  thread: ConversationThread,
  evt: Extract<RealtimeEvent, { type: "imessage.message.updated" }>,
): ConversationThread {
  return {
    ...thread,
    messages: thread.messages.map((m) =>
      m.id === evt.message_id
        ? {
            ...m,
            status: evt.status,
            delivered_at: evt.delivered_at ?? m.delivered_at,
            read_at: evt.read_at ?? m.read_at,
          }
        : m,
    ),
  };
}
