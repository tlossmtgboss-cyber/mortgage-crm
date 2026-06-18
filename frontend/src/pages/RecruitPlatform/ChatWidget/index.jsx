import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import './ChatWidget.css';

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';

function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function isEmailQuestion(text) {
  const lower = (text || '').toLowerCase();
  return lower.includes('email') && (lower.includes('?') || lower.includes('what is') || lower.includes('share') || lower.includes('provide'));
}

// ── Collect info mini-form ─────────────────────────────────────────────────────
function CollectForm({ onSubmit }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');

  function handleSubmit(e) {
    e.preventDefault();
    if (!name.trim() || !email.trim()) return;
    onSubmit({ name: name.trim(), email: email.trim(), phone: phone.trim() });
  }

  return (
    <form className="cw-collect-form" onSubmit={handleSubmit}>
      <div className="cw-collect-row">
        <input
          className="cw-collect-input"
          placeholder="Your name *"
          value={name}
          onChange={e => setName(e.target.value)}
          required
        />
      </div>
      <div className="cw-collect-row">
        <input
          className="cw-collect-input"
          placeholder="Email address *"
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          required
        />
      </div>
      <div className="cw-collect-row">
        <input
          className="cw-collect-input"
          placeholder="Phone (optional)"
          type="tel"
          value={phone}
          onChange={e => setPhone(e.target.value)}
        />
      </div>
      <button className="cw-collect-submit" type="submit">Submit Application</button>
    </form>
  );
}

// ── Main chat widget ───────────────────────────────────────────────────────────
export default function ChatWidget() {
  const { tenantSlug } = useParams();
  const [orgName, setOrgName] = useState('');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [showCollect, setShowCollect] = useState(false);
  const [collectIndex, setCollectIndex] = useState(null);
  const bottomRef = useRef(null);

  const sessionId = useRef(
    (() => {
      const key = `recruit_session_${tenantSlug}`;
      let id = sessionStorage.getItem(key);
      if (!id) { id = generateUUID(); sessionStorage.setItem(key, id); }
      return id;
    })()
  );

  // Fetch org info
  useEffect(() => {
    fetch(`${API_BASE}/api/v1/recruit-platform/apply/${tenantSlug}`)
      .then(r => r.ok ? r.json() : {})
      .then(data => {
        const name = data.org_name || data.name || tenantSlug;
        setOrgName(name);
        setMessages([{
          role: 'assistant',
          text: `Hi! I'm the recruiting assistant for ${name}. Ask me anything about our open positions, culture, or how to apply!`,
        }]);
      })
      .catch(() => {
        setOrgName(tenantSlug);
        setMessages([{
          role: 'assistant',
          text: `Hi! I'm the recruiting assistant. Ask me anything about our open positions, culture, or how to apply!`,
        }]);
      });
  }, [tenantSlug]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, typing, showCollect]);

  async function sendMessage(text) {
    setMessages(prev => [...prev, { role: 'user', text }]);
    setTyping(true);
    setShowCollect(false);
    try {
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/chat/${tenantSlug}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId.current, message: text }),
      });
      const data = await res.json();
      const reply = data.response || data.message || 'No response received.';
      setMessages(prev => {
        const next = [...prev, { role: 'assistant', text: reply }];
        if (isEmailQuestion(reply)) {
          setShowCollect(true);
          setCollectIndex(next.length - 1);
        }
        return next;
      });
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', text: 'Sorry, something went wrong. Please try again.' }]);
    } finally {
      setTyping(false);
    }
  }

  function handleSend(e) {
    e.preventDefault();
    if (!input.trim() || typing) return;
    const text = input.trim();
    setInput('');
    sendMessage(text);
  }

  function handleCollectSubmit({ name, email, phone }) {
    setShowCollect(false);
    const phoneStr = phone ? `, phone is ${phone}` : '';
    sendMessage(`My name is ${name}, email is ${email}${phoneStr}`);
  }

  const avatarInitial = orgName ? orgName[0].toUpperCase() : '?';

  return (
    <div className="cw-root">
      <div className="cw-header">
        <div className="cw-header-icon">🤖</div>
        <div>
          <div className="cw-header-title">{orgName || tenantSlug} Recruiting Assistant</div>
          <div className="cw-header-sub">Ask me anything about working here</div>
        </div>
      </div>

      <div className="cw-messages">
        {messages.map((msg, i) => (
          <React.Fragment key={i}>
            <div className={`cw-msg-row ${msg.role}`}>
              {msg.role === 'assistant' && (
                <span className="cw-avatar">{avatarInitial}</span>
              )}
              <div className={`cw-bubble cw-bubble-${msg.role === 'user' ? 'user' : 'assistant'}`}>
                {msg.text}
              </div>
            </div>
            {showCollect && collectIndex === i && (
              <CollectForm onSubmit={handleCollectSubmit} />
            )}
          </React.Fragment>
        ))}
        {typing && <div className="cw-typing">···</div>}
        <div ref={bottomRef} />
      </div>

      <form className="cw-input-bar" onSubmit={handleSend}>
        <input
          className="cw-input"
          placeholder="Type a message…"
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={typing}
        />
        <button className="cw-send-btn" type="submit" disabled={typing || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
