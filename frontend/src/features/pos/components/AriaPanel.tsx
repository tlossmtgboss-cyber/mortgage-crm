/**
 * AriaPanel — slide-over chat panel for the Aria AI Q&A assistant.
 *
 * Renders a fixed-width column on the right that slides in when `open` is
 * true. Maintains conversation state via the `useAriaChat` hook. Closes on
 * the X button, the overlay click, or the ESC key.
 */
import React, { useEffect, useRef, useState } from 'react';

import { useAriaChat, UIMessage } from '../hooks/useAriaChat';
import type { Source } from '../types';

export interface AriaPanelProps {
  open: boolean;
  onClose: () => void;
  applicationId: string;
  currentStep?: string;
}

export const AriaPanel: React.FC<AriaPanelProps> = ({
  open,
  onClose,
  applicationId,
  currentStep,
}) => {
  const { messages, thinking, ask, error } = useAriaChat(applicationId, currentStep);
  const [draft, setDraft] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  // Focus on open.
  useEffect(() => {
    if (open) {
      const t = setTimeout(() => inputRef.current?.focus(), 380);
      return () => clearTimeout(t);
    }
  }, [open]);

  // ESC to close.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  // Auto-scroll on new messages.
  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [messages, thinking]);

  // Lock body scroll while panel open.
  useEffect(() => {
    if (open) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [open]);

  const submit = (text: string) => {
    if (!text.trim() || thinking) return;
    ask(text);
    setDraft('');
    if (inputRef.current) inputRef.current.style.height = 'auto';
  };

  return (
    <>
      <div
        className={`aria-overlay${open ? ' is-open' : ''}`}
        onClick={onClose}
        aria-hidden={!open}
      />

      <aside
        className={`aria-panel${open ? ' is-open' : ''}`}
        role="dialog"
        aria-label="Aria AI Assistant"
        aria-hidden={!open}
      >
        <header className="aria-panel__header">
          <div className="aria-panel__identity">
            <div className="aria-panel__seal" aria-hidden>A</div>
            <div className="aria-panel__title-wrap">
              <h2 className="aria-panel__title">
                Aria{' '}
                <span className="aria-panel__online-pill">
                  <span className="aria-panel__online-dot" />
                  Online
                </span>
              </h2>
              <p className="aria-panel__subtitle">
                AI loan assistant · Loan file + Agency guidelines
              </p>
            </div>
            <button
              type="button"
              className="aria-icon-btn"
              onClick={onClose}
              aria-label="Close"
            >
              <CloseIcon />
            </button>
          </div>

          <div className="aria-panel__capabilities">
            <span className="aria-chip">
              <FileIcon /> Your loan file
            </span>
            <span className="aria-chip">
              <BookIcon /> FNMA · FHLMC · FHA · VA
            </span>
          </div>
        </header>

        <div className="aria-panel__body" ref={bodyRef}>
          {messages.map((m, i) => (
            <Message key={m.id ?? `optimistic-${i}`} message={m} />
          ))}
          {thinking && <TypingIndicator />}
          {error && <div className="aria-error">{error}</div>}
        </div>

        <footer className="aria-panel__footer">
          {!thinking && lastSuggestions(messages).length > 0 && (
            <div className="aria-suggestions">
              {lastSuggestions(messages).map(s => (
                <button
                  key={s}
                  type="button"
                  className="aria-suggestion"
                  onClick={() => submit(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          <form
            className="aria-input-row"
            onSubmit={e => {
              e.preventDefault();
              submit(draft);
            }}
          >
            <textarea
              ref={inputRef}
              className="aria-input"
              rows={1}
              placeholder="Ask anything about your loan…"
              value={draft}
              onChange={e => {
                setDraft(e.target.value);
                const ta = e.target;
                ta.style.height = 'auto';
                ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
              }}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  submit(draft);
                }
              }}
            />
            <button type="button" className="aria-icon-btn" aria-label="Voice" title="Voice input">
              <MicIcon />
            </button>
            <button
              type="submit"
              className="aria-icon-btn aria-send-btn"
              disabled={!draft.trim() || thinking}
              aria-label="Send"
              title="Send"
            >
              <ArrowUpIcon />
            </button>
          </form>

          <p className="aria-panel__disclaimer">
            Aria can make mistakes. For final decisions, your loan officer is your source of truth.
          </p>
        </footer>
      </aside>
    </>
  );
};

// ---------- Sub-components ----------

const Message: React.FC<{ message: UIMessage }> = ({ message }) => {
  if (message.role === 'borrower') {
    return (
      <div className="aria-msg-row aria-msg-row--user">
        <div className="aria-msg-bubble">{message.content}</div>
      </div>
    );
  }
  return (
    <div className="aria-msg-row aria-msg-row--aria">
      <div className="aria-msg-seal" aria-hidden>A</div>
      <div className="aria-msg-bubble">
        <AriaContent content={message.content} />
        {message.sources && message.sources.length > 0 && (
          <div className="aria-sources">
            <div className="aria-sources__label">Sources</div>
            {message.sources.map((s, i) => (
              <SourceChip key={i} source={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const AriaContent: React.FC<{ content: string }> = ({ content }) => {
  // Aria responses are markdown — for now we render line breaks as <br/> and
  // bullets as a simple list. For richer markdown, swap to a marked / remark
  // pipeline. The deliberate minimalism here protects against XSS via an
  // accidentally-passed tool output.
  const blocks = content.split(/\n\n+/);
  return (
    <>
      {blocks.map((block, i) => {
        if (block.match(/^\s*[-*]\s/m)) {
          const items = block
            .split('\n')
            .filter(line => line.match(/^\s*[-*]\s/))
            .map(line => line.replace(/^\s*[-*]\s/, ''));
          return (
            <ul key={i}>
              {items.map((item, j) => (
                <li key={j}>{renderInline(item)}</li>
              ))}
            </ul>
          );
        }
        return <p key={i}>{renderInline(block)}</p>;
      })}
    </>
  );
};

function renderInline(text: string): React.ReactNode {
  // Bold via **...**.
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

const SourceChip: React.FC<{ source: Source }> = ({ source }) => {
  const node = (
    <span className="aria-source-chip">
      <CheckIcon />
      {source.label}
    </span>
  );
  if (source.anchor && source.type === 'guideline' && source.anchor.startsWith('http')) {
    return (
      <a
        href={source.anchor}
        target="_blank"
        rel="noreferrer"
        className="aria-source-link"
      >
        {node}
      </a>
    );
  }
  return node;
};

const TypingIndicator: React.FC = () => (
  <div className="aria-msg-row aria-msg-row--aria">
    <div className="aria-msg-seal" aria-hidden>A</div>
    <div className="aria-typing">
      <span className="aria-typing__dot" />
      <span className="aria-typing__dot" />
      <span className="aria-typing__dot" />
    </div>
  </div>
);

function lastSuggestions(messages: UIMessage[]): string[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === 'aria' && m.followUps && m.followUps.length > 0) {
      return m.followUps;
    }
  }
  return [];
}

// ---------- Icons ----------

const CloseIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const FileIcon: React.FC = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6" />
  </svg>
);

const BookIcon: React.FC = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
  </svg>
);

const CheckIcon: React.FC = () => (
  <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const MicIcon: React.FC = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden>
    <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="23" />
    <line x1="8" y1="23" x2="16" y2="23" />
  </svg>
);

const ArrowUpIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
    <line x1="12" y1="19" x2="12" y2="5" />
    <polyline points="5 12 12 5 19 12" />
  </svg>
);
