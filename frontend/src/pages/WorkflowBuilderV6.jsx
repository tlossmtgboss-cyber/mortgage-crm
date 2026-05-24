import React, { useState, useRef, useEffect } from 'react';

// ── Theme ──────────────────────────────────────────────────────────────────────
const T = {
  pageBg: '#FAF7F1',
  cardBg: '#FFFFFF',
  primary: '#1F3D2E',
  accent: '#B8924A',
  border: '#ECE6D8',
  text: '#1A1F1B',
  muted: '#8B8A7E',
  success: '#2D7A52',
  error: '#9B2C2C',
  warning: '#B25F18',
  fontHeader: "'Fraunces', serif",
  fontBody: "'Geist', 'Inter', sans-serif",
  fontMono: "'Geist Mono', monospace",
  radius: '12px',
  shadow: '0 1px 3px rgba(0,0,0,0.06)',
};

const CHANNEL_ICONS = { phone: '📞', text: '📱', email: '✉️', referral_partner: '🤝' };
const ROLES = ['LO', 'Processor', 'Concierge', 'AI', 'Manager', 'System'];

// ── Pre-loaded Chat Conversation ─────────────────────────────────────────────
const INITIAL_MESSAGES = [
  {
    id: 1,
    from: 'user',
    text: 'I want to build a pre-qualification follow-up workflow for new leads. The goal is to get them to submit documents and schedule a consultation within 3 weeks.',
    time: '9:01 AM',
  },
  {
    id: 2,
    from: 'ai',
    text: "Great, I'll help you build that out. Let me start with the initial contact. For new pre-qual leads, I'd recommend an immediate welcome text + call attempt within the first hour. The Concierge can handle this since it's a warm intro, not a technical conversation. Should I add that as Step 1?",
    time: '9:01 AM',
  },
  {
    id: 3,
    from: 'user',
    text: 'Yes, perfect. Make it text + phone, assigned to Concierge.',
    time: '9:02 AM',
  },
  {
    id: 4,
    from: 'ai',
    text: "Done! Added Step 1: Welcome text + warm call in the first 24 hours, assigned to Concierge. Now, what about follow-up if they don't respond? I'd suggest a personal LO call on Day 2 — research shows Day 2 callbacks have 3x higher connect rates than Day 3+.",
    time: '9:02 AM',
    stepAdded: 1,
  },
  {
    id: 5,
    from: 'user',
    text: 'Good call. Add that. Then on Day 3, send an email with the pre-qual document checklist and current rates.',
    time: '9:03 AM',
  },
  {
    id: 6,
    from: 'ai',
    text: "Added both! Step 2 is the LO follow-up call on Day 2 (for non-responders). Step 3 is an automated email on Day 3 with the pre-qual checklist and rate snapshot — I'll assign that to AI since it's template-driven. I'm also noting that we should include W-2s, pay stubs, and bank statements in that checklist. Want to add a referral partner touchpoint for leads that came through agents?",
    time: '9:03 AM',
    stepAdded: 3,
  },
  {
    id: 7,
    from: 'user',
    text: 'Yes, on Day 7 if no response, loop in the referring agent to re-engage.',
    time: '9:04 AM',
  },
  {
    id: 8,
    from: 'ai',
    text: "Smart move. Added Step 4: Referral partner co-outreach on Day 7 via text + email to the referring agent. This has a condition — only triggers for leads with a referring agent on file. I'll mark it with a condition flag. What about longer-term nurture?",
    time: '9:04 AM',
    stepAdded: 4,
  },
  {
    id: 9,
    from: 'user',
    text: 'Send weekly email updates with market rates starting Day 14. Keep it going for 3 weeks.',
    time: '9:05 AM',
  },
  {
    id: 10,
    from: 'ai',
    text: "Added Step 5: Weekly market update emails starting Day 14, repeating weekly. I'll make these AI-generated with personalized rate scenarios based on their loan amount. And finally, should we add a \"last chance\" personal touch before moving them to long-term nurture?",
    time: '9:05 AM',
    stepAdded: 5,
  },
  {
    id: 11,
    from: 'user',
    text: 'Yes, Day 21 — final personal outreach from the LO via all channels. If no response, move to Nurture workflow automatically.',
    time: '9:06 AM',
  },
  {
    id: 12,
    from: 'ai',
    text: "Done! Step 6: Final personal outreach on Day 21 using phone + text + email, assigned to the LO. If there's still no engagement, the lead automatically transitions to the Nurture workflow for quarterly check-ins. Your 6-step pre-qual workflow is ready! Here's what I'd recommend optimizing: the Day 7 referral partner step currently shows a 'broken' status — that typically means the template hasn't been configured yet. Would you like me to suggest a template?",
    time: '9:06 AM',
    stepAdded: 6,
  },
];

// ── Pre-loaded Workflow Steps (built through conversation) ───────────────────
const INITIAL_STEPS = [
  {
    id: 1,
    dayLabel: 'First 24 Hours',
    action: 'Welcome text + warm call attempt',
    channels: { phone: true, text: true, email: false, referral_partner: false },
    role: 'Concierge',
    status: 'healthy',
    description: 'Send personalized welcome text and attempt a warm call within the first hour.',
    timeOfDay: 'AM',
    repeatWeekly: false,
    condition: '',
  },
  {
    id: 2,
    dayLabel: 'Day 2',
    action: 'LO follow-up call (non-responders)',
    channels: { phone: true, text: false, email: false, referral_partner: false },
    role: 'LO',
    status: 'healthy',
    description: 'Personal call from the loan officer. Leave voicemail with callback number and current rate teaser.',
    timeOfDay: 'AM',
    repeatWeekly: false,
    condition: 'No response to Day 1 outreach',
  },
  {
    id: 3,
    dayLabel: 'Day 3',
    action: 'Email pre-qual checklist + rate snapshot',
    channels: { phone: false, text: false, email: true, referral_partner: false },
    role: 'AI',
    status: 'healthy',
    description: 'Automated email with document checklist (W-2s, pay stubs, bank statements) and personalized rate snapshot.',
    timeOfDay: 'AM',
    repeatWeekly: false,
    condition: '',
  },
  {
    id: 4,
    dayLabel: 'Day 7',
    action: 'Referral partner co-outreach',
    channels: { phone: false, text: true, email: true, referral_partner: true },
    role: 'AI',
    status: 'broken',
    description: 'Alert referring agent that lead is unresponsive. Joint email showing LO + agent collaboration.',
    timeOfDay: 'PM',
    repeatWeekly: false,
    condition: 'Lead has referring agent AND no response',
  },
  {
    id: 5,
    dayLabel: 'Day 14',
    action: 'Weekly market update email',
    channels: { phone: false, text: false, email: true, referral_partner: false },
    role: 'AI',
    status: 'healthy',
    description: 'Personalized weekly email with market updates, rate changes, and soft CTA to schedule consultation.',
    timeOfDay: 'AM',
    repeatWeekly: true,
    condition: '',
  },
  {
    id: 6,
    dayLabel: 'Day 21',
    action: 'Final personal outreach or move to Nurture',
    channels: { phone: true, text: true, email: true, referral_partner: false },
    role: 'LO',
    status: 'disabled',
    description: 'Last personal touchpoint. If no response, automatically transition to long-term Nurture workflow.',
    timeOfDay: 'PM',
    repeatWeekly: false,
    condition: 'No engagement after 3 weeks',
  },
];

const statusColor = (s) => (s === 'healthy' ? T.success : s === 'broken' ? T.error : T.muted);

// ── AI Suggestions ───────────────────────────────────────────────────────────
const AI_SUGGESTIONS = [
  'Consider adding a voicemail drop on Day 2 — pre-recorded personal messages see 28% higher callback rates.',
  'The Day 7 referral partner step needs a template. I recommend: "Hi [Agent], wanted to loop you in — your client [Lead] hasn\'t responded yet. Quick text from you could help!"',
  'Best practice: Add a credit pull authorization step between Day 3 and Day 7. Most pre-quals stall because borrowers forget to submit their SSN consent.',
  'Your workflow covers 21 days. Top-performing LOs in your market add a "Day 30 market change" touchpoint for leads that went cold but didn\'t opt out.',
];

// ── Component ──────────────────────────────────────────────────────────────────
export default function WorkflowBuilderV6() {
  const [messages, setMessages] = useState(INITIAL_MESSAGES);
  const [steps, setSteps] = useState(INITIAL_STEPS);
  const [inputText, setInputText] = useState('');
  const [editingStep, setEditingStep] = useState(null);
  const [showSuggestion, setShowSuggestion] = useState(null);
  const [isAiTyping, setIsAiTyping] = useState(false);
  const chatEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isAiTyping]);

  // ── Chat Handlers ──────────────────────────────────────────────────────────
  const sendMessage = () => {
    if (!inputText.trim()) return;
    const userMsg = {
      id: Date.now(),
      from: 'user',
      text: inputText,
      time: new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setIsAiTyping(true);

    // Simulate AI response
    setTimeout(() => {
      const text = inputText.toLowerCase();
      let aiResponse = '';
      let newStep = null;

      if (text.includes('add') || text.includes('create') || text.includes('want')) {
        // Try to create a step from the message
        const dayMatch = text.match(/day\s*(\d+)/i);
        const day = dayMatch ? `Day ${dayMatch[1]}` : `Day ${steps.length * 3 + 1}`;
        const hasPhone = text.includes('call') || text.includes('phone');
        const hasText = text.includes('text') || text.includes('sms');
        const hasEmail = text.includes('email') || text.includes('send');
        const hasRP = text.includes('referral') || text.includes('partner') || text.includes('agent');

        newStep = {
          id: Date.now(),
          dayLabel: day,
          action: inputText.slice(0, 60),
          channels: { phone: hasPhone, text: hasText, email: hasEmail, referral_partner: hasRP },
          role: text.includes('ai') || text.includes('automat') ? 'AI' : text.includes('processor') ? 'Processor' : 'LO',
          status: 'healthy',
          description: inputText,
          timeOfDay: text.includes('morning') || text.includes('am') ? 'AM' : 'PM',
          repeatWeekly: text.includes('weekly') || text.includes('recurring') || text.includes('repeat'),
          condition: '',
        };

        aiResponse = `Done! I've added a new step: "${newStep.action}" on ${day}. I assigned it to ${newStep.role} with ${Object.entries(newStep.channels).filter(([, v]) => v).map(([k]) => k).join(' + ') || 'email'} channels. You can edit it directly on the right panel. Anything else to add?`;
      } else if (text.includes('optimize') || text.includes('improve') || text.includes('suggest')) {
        aiResponse = AI_SUGGESTIONS[Math.floor(Math.random() * AI_SUGGESTIONS.length)];
      } else if (text.includes('delete') || text.includes('remove')) {
        aiResponse = "I can remove a step for you. Which step number would you like to delete? Or you can click the trash icon on the right panel to remove it directly.";
      } else if (text.includes('status') || text.includes('broken')) {
        aiResponse = `Your workflow currently has ${steps.filter((s) => s.status === 'healthy').length} healthy steps, ${steps.filter((s) => s.status === 'broken').length} that need attention, and ${steps.filter((s) => s.status === 'disabled').length} disabled. The Day 7 referral partner step shows "broken" because it needs a configured template. Want me to fix that?`;
      } else {
        aiResponse = `Got it. I can help you with that. Would you like me to add a new step to the workflow, modify an existing one, or suggest optimizations based on industry best practices? Just describe what you'd like and I'll make it happen.`;
      }

      const aiMsg = {
        id: Date.now() + 1,
        from: 'ai',
        text: aiResponse,
        time: new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
        stepAdded: newStep ? steps.length + 1 : null,
      };

      setMessages((prev) => [...prev, aiMsg]);
      if (newStep) setSteps((prev) => [...prev, newStep]);
      setIsAiTyping(false);
    }, 1200 + Math.random() * 800);
  };

  // ── Step Editing ───────────────────────────────────────────────────────────
  const updateStep = (stepId, field, value) => {
    setSteps((prev) => prev.map((s) => (s.id === stepId ? { ...s, [field]: value } : s)));
  };

  const deleteStep = (stepId) => {
    setSteps((prev) => prev.filter((s) => s.id !== stepId));
    if (editingStep === stepId) setEditingStep(null);
  };

  const toggleChannel = (stepId, channel) => {
    setSteps((prev) =>
      prev.map((s) =>
        s.id === stepId ? { ...s, channels: { ...s.channels, [channel]: !s.channels[channel] } } : s
      )
    );
  };

  // ── Toolbar Actions ────────────────────────────────────────────────────────
  const handleOptimize = () => {
    setIsAiTyping(true);
    setTimeout(() => {
      const suggestion = AI_SUGGESTIONS[Math.floor(Math.random() * AI_SUGGESTIONS.length)];
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          from: 'ai',
          text: `Optimization suggestion: ${suggestion}`,
          time: new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
        },
      ]);
      setIsAiTyping(false);
    }, 1500);
  };

  const handleSuggestMissing = () => {
    setIsAiTyping(true);
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          from: 'ai',
          text: "Analyzing your workflow against 200+ top-performing pre-qual sequences... I found 2 gaps:\n\n1. Missing: Credit pull authorization step (typically Day 3-5). Without this, the pre-qual can't progress to underwriting.\n\n2. Missing: Post-consultation follow-up. After the initial consultation, a same-day summary email increases document submission by 41%.\n\nWant me to add either of these?",
          time: new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
        },
      ]);
      setIsAiTyping(false);
    }, 2000);
  };

  const handleCompareBestPractices = () => {
    setShowSuggestion({
      title: 'Best Practice Comparison',
      items: [
        { label: 'Speed to lead', score: 95, note: 'Your first touch is within 24 hours — excellent.' },
        { label: 'Multi-channel coverage', score: 80, note: 'Good mix, but Day 3 is email-only. Consider adding SMS.' },
        { label: 'Referral partner engagement', score: 70, note: 'Day 7 is good timing, but template needs setup.' },
        { label: 'Escalation path', score: 60, note: 'No manager escalation for high-value leads. Consider adding.' },
        { label: 'Nurture transition', score: 90, note: 'Day 21 cutoff with auto-transition is industry best practice.' },
      ],
    });
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ minHeight: '100vh', background: T.pageBg, fontFamily: T.fontBody, color: T.text, display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 24px',
          borderBottom: `1px solid ${T.border}`,
          background: T.cardBg,
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <a
            href="/workflows"
            onClick={(e) => { e.preventDefault(); window.history.back(); }}
            style={{ color: T.muted, textDecoration: 'none', fontSize: 14 }}
          >
            &larr; Back to Workflows
          </a>
          <div style={{ width: 1, height: 24, background: T.border }} />
          <h1 style={{ fontFamily: T.fontHeader, fontSize: 22, margin: 0, fontWeight: 600 }}>
            Pre-Qualification Workflow
          </h1>
          <span
            style={{
              fontSize: 11,
              fontFamily: T.fontMono,
              padding: '3px 8px',
              background: '#D1FAE5',
              color: T.success,
              borderRadius: 6,
              fontWeight: 600,
            }}
          >
            V6 AI COPILOT
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: T.muted, fontFamily: T.fontMono }}>
            {steps.length} steps
          </span>
          <button
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: 'none',
              background: T.primary,
              color: '#fff',
              fontFamily: T.fontBody,
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Apply Changes
          </button>
        </div>
      </div>

      {/* Main Split View */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* LEFT: Chat */}
        <div
          style={{
            width: '45%',
            display: 'flex',
            flexDirection: 'column',
            borderRight: `1px solid ${T.border}`,
            background: T.cardBg,
          }}
        >
          {/* Chat Messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
            {/* Intro */}
            <div
              style={{
                textAlign: 'center',
                padding: '12px 0 20px',
                borderBottom: `1px solid ${T.border}`,
                marginBottom: 16,
              }}
            >
              <div style={{ fontSize: 28, marginBottom: 4 }}>🧠</div>
              <div style={{ fontFamily: T.fontHeader, fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
                Workflow Copilot
              </div>
              <div style={{ fontSize: 12, color: T.muted }}>
                Describe your workflow in plain English and I'll build it for you.
              </div>
            </div>

            {messages.map((msg) => (
              <div
                key={msg.id}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: msg.from === 'user' ? 'flex-end' : 'flex-start',
                  marginBottom: 12,
                }}
              >
                <div
                  style={{
                    maxWidth: '85%',
                    padding: '10px 14px',
                    borderRadius: 12,
                    background: msg.from === 'user' ? T.primary : T.pageBg,
                    color: msg.from === 'user' ? '#fff' : T.text,
                    fontSize: 13,
                    lineHeight: 1.5,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {msg.text}
                  {msg.stepAdded && (
                    <div
                      style={{
                        marginTop: 8,
                        padding: '4px 8px',
                        background: msg.from === 'user' ? 'rgba(255,255,255,0.15)' : T.success + '14',
                        borderRadius: 6,
                        fontSize: 11,
                        fontFamily: T.fontMono,
                        color: msg.from === 'user' ? 'rgba(255,255,255,0.8)' : T.success,
                        fontWeight: 600,
                      }}
                    >
                      + Step {msg.stepAdded} added to workflow
                    </div>
                  )}
                </div>
                <span style={{ fontSize: 10, color: T.muted, marginTop: 3, padding: '0 4px' }}>
                  {msg.time}
                </span>
              </div>
            ))}

            {isAiTyping && (
              <div style={{ display: 'flex', alignItems: 'flex-start', marginBottom: 12 }}>
                <div
                  style={{
                    padding: '10px 14px',
                    borderRadius: 12,
                    background: T.pageBg,
                    fontSize: 13,
                    color: T.muted,
                  }}
                >
                  <span style={{ animation: 'blink 1.2s infinite' }}>Thinking</span>
                  <span style={{ animation: 'blink 1.2s infinite 0.2s' }}>.</span>
                  <span style={{ animation: 'blink 1.2s infinite 0.4s' }}>.</span>
                  <span style={{ animation: 'blink 1.2s infinite 0.6s' }}>.</span>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Chat Input */}
          <div
            style={{
              padding: '12px 16px',
              borderTop: `1px solid ${T.border}`,
              background: T.cardBg,
            }}
          >
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                ref={inputRef}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
                placeholder="Describe a workflow step... (e.g., 'Add a text on Day 5 if they opened the email')"
                style={{
                  flex: 1,
                  padding: '10px 14px',
                  borderRadius: 10,
                  border: `1px solid ${T.border}`,
                  fontFamily: T.fontBody,
                  fontSize: 13,
                  outline: 'none',
                  background: T.pageBg,
                }}
              />
              <button
                onClick={sendMessage}
                disabled={!inputText.trim() || isAiTyping}
                style={{
                  padding: '10px 18px',
                  borderRadius: 10,
                  border: 'none',
                  background: !inputText.trim() || isAiTyping ? T.border : T.primary,
                  color: '#fff',
                  fontFamily: T.fontBody,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: !inputText.trim() || isAiTyping ? 'not-allowed' : 'pointer',
                }}
              >
                Send
              </button>
            </div>
          </div>

          {/* Bottom Toolbar */}
          <div
            style={{
              padding: '8px 16px 12px',
              display: 'flex',
              gap: 6,
              borderTop: `1px solid ${T.border}`,
              background: T.pageBg,
            }}
          >
            <button
              onClick={handleOptimize}
              style={{
                padding: '6px 12px',
                borderRadius: 8,
                border: `1px solid ${T.accent}44`,
                background: T.accent + '0A',
                color: T.accent,
                fontSize: 11,
                fontWeight: 600,
                cursor: 'pointer',
                fontFamily: T.fontBody,
              }}
            >
              ✨ Use AI to Optimize
            </button>
            <button
              onClick={handleSuggestMissing}
              style={{
                padding: '6px 12px',
                borderRadius: 8,
                border: `1px solid ${T.border}`,
                background: T.cardBg,
                color: T.text,
                fontSize: 11,
                fontWeight: 500,
                cursor: 'pointer',
                fontFamily: T.fontBody,
              }}
            >
              Suggest Missing Steps
            </button>
            <button
              onClick={handleCompareBestPractices}
              style={{
                padding: '6px 12px',
                borderRadius: 8,
                border: `1px solid ${T.border}`,
                background: T.cardBg,
                color: T.text,
                fontSize: 11,
                fontWeight: 500,
                cursor: 'pointer',
                fontFamily: T.fontBody,
              }}
            >
              Compare with Best Practices
            </button>
          </div>
        </div>

        {/* RIGHT: Live Workflow Preview */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '20px 24px',
            background: T.pageBg,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <h2 style={{ fontFamily: T.fontHeader, fontSize: 16, margin: 0, fontWeight: 600 }}>
              Live Workflow Preview
            </h2>
            <span style={{ fontSize: 11, fontFamily: T.fontMono, color: T.muted }}>
              {steps.filter((s) => s.status === 'healthy').length} active / {steps.length} total
            </span>
          </div>

          {/* Step cards */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {steps.map((step, idx) => {
              const isEditing = editingStep === step.id;
              return (
                <div key={step.id}>
                  {/* Connector line */}
                  {idx > 0 && (
                    <div
                      style={{
                        width: 2,
                        height: 16,
                        background: T.border,
                        marginLeft: 24,
                      }}
                    />
                  )}
                  <div
                    style={{
                      background: T.cardBg,
                      border: `1px solid ${isEditing ? T.accent : T.border}`,
                      borderRadius: T.radius,
                      padding: '14px 18px',
                      boxShadow: isEditing ? `0 0 0 3px ${T.accent}22, ${T.shadow}` : T.shadow,
                      opacity: step.status === 'disabled' ? 0.55 : 1,
                      transition: 'all 0.2s',
                    }}
                  >
                    {/* Step Header */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                      {/* Step number */}
                      <div
                        style={{
                          width: 26,
                          height: 26,
                          borderRadius: '50%',
                          background: statusColor(step.status) + '18',
                          border: `2px solid ${statusColor(step.status)}`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: 11,
                          fontWeight: 700,
                          color: statusColor(step.status),
                          fontFamily: T.fontMono,
                          flexShrink: 0,
                        }}
                      >
                        {idx + 1}
                      </div>
                      {/* Day label */}
                      {isEditing ? (
                        <input
                          value={step.dayLabel}
                          onChange={(e) => updateStep(step.id, 'dayLabel', e.target.value)}
                          style={{
                            fontFamily: T.fontMono,
                            fontSize: 12,
                            fontWeight: 600,
                            padding: '2px 6px',
                            border: `1px solid ${T.border}`,
                            borderRadius: 4,
                            outline: 'none',
                            width: 100,
                          }}
                        />
                      ) : (
                        <span style={{ fontFamily: T.fontMono, fontSize: 12, fontWeight: 600, color: T.primary }}>
                          {step.dayLabel}
                        </span>
                      )}
                      {/* Channels */}
                      <div style={{ display: 'flex', gap: 4 }}>
                        {Object.entries(step.channels)
                          .filter(([, v]) => v)
                          .map(([ch]) => (
                            <span
                              key={ch}
                              style={{
                                fontSize: 13,
                                cursor: isEditing ? 'pointer' : 'default',
                              }}
                              onClick={() => isEditing && toggleChannel(step.id, ch)}
                              title={ch.replace('_', ' ')}
                            >
                              {CHANNEL_ICONS[ch]}
                            </span>
                          ))}
                        {isEditing &&
                          Object.entries(step.channels)
                            .filter(([, v]) => !v)
                            .map(([ch]) => (
                              <span
                                key={ch}
                                style={{ fontSize: 13, opacity: 0.3, cursor: 'pointer' }}
                                onClick={() => toggleChannel(step.id, ch)}
                                title={`Add ${ch.replace('_', ' ')}`}
                              >
                                {CHANNEL_ICONS[ch]}
                              </span>
                            ))}
                      </div>
                      {/* Role */}
                      {isEditing ? (
                        <select
                          value={step.role}
                          onChange={(e) => updateStep(step.id, 'role', e.target.value)}
                          style={{
                            fontSize: 11,
                            fontFamily: T.fontMono,
                            padding: '2px 6px',
                            border: `1px solid ${T.border}`,
                            borderRadius: 4,
                            outline: 'none',
                            background: T.cardBg,
                          }}
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>{r}</option>
                          ))}
                        </select>
                      ) : (
                        <span
                          style={{
                            fontSize: 10,
                            fontFamily: T.fontMono,
                            padding: '2px 8px',
                            borderRadius: 4,
                            background: step.role === 'AI' ? '#EDE9FE' : step.role === 'LO' ? '#DBEAFE' : '#F3F4F6',
                            color: step.role === 'AI' ? '#6366f1' : step.role === 'LO' ? '#2563EB' : T.text,
                            fontWeight: 600,
                          }}
                        >
                          {step.role}
                        </span>
                      )}
                      {step.repeatWeekly && (
                        <span style={{ fontSize: 10, color: T.accent, fontFamily: T.fontMono, fontWeight: 600 }}>
                          &#x21BB; Weekly
                        </span>
                      )}
                      <div style={{ flex: 1 }} />
                      {/* Status */}
                      <div
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          background: statusColor(step.status),
                        }}
                      />
                      {/* Edit/Delete */}
                      <button
                        onClick={() => setEditingStep(isEditing ? null : step.id)}
                        style={{
                          background: 'none',
                          border: 'none',
                          fontSize: 14,
                          cursor: 'pointer',
                          color: isEditing ? T.accent : T.muted,
                          padding: '0 4px',
                        }}
                        title={isEditing ? 'Done editing' : 'Edit step'}
                      >
                        {isEditing ? '✓' : '✎'}
                      </button>
                      <button
                        onClick={() => deleteStep(step.id)}
                        style={{
                          background: 'none',
                          border: 'none',
                          fontSize: 14,
                          cursor: 'pointer',
                          color: T.muted,
                          padding: '0 4px',
                        }}
                        title="Delete step"
                      >
                        🗑
                      </button>
                    </div>

                    {/* Action */}
                    {isEditing ? (
                      <input
                        value={step.action}
                        onChange={(e) => updateStep(step.id, 'action', e.target.value)}
                        style={{
                          width: '100%',
                          padding: '6px 8px',
                          border: `1px solid ${T.border}`,
                          borderRadius: 6,
                          fontSize: 13,
                          fontFamily: T.fontBody,
                          fontWeight: 500,
                          outline: 'none',
                          marginBottom: 6,
                          boxSizing: 'border-box',
                        }}
                      />
                    ) : (
                      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 4, paddingLeft: 36 }}>
                        {step.action}
                      </div>
                    )}

                    {/* Description */}
                    {isEditing ? (
                      <textarea
                        value={step.description}
                        onChange={(e) => updateStep(step.id, 'description', e.target.value)}
                        rows={2}
                        style={{
                          width: '100%',
                          padding: '6px 8px',
                          border: `1px solid ${T.border}`,
                          borderRadius: 6,
                          fontSize: 12,
                          fontFamily: T.fontBody,
                          outline: 'none',
                          resize: 'vertical',
                          color: T.muted,
                          boxSizing: 'border-box',
                        }}
                      />
                    ) : (
                      <div style={{ fontSize: 12, color: T.muted, paddingLeft: 36, lineHeight: 1.4 }}>
                        {step.description}
                      </div>
                    )}

                    {/* Condition */}
                    {(step.condition || isEditing) && (
                      <div style={{ marginTop: 6, paddingLeft: 36 }}>
                        {isEditing ? (
                          <input
                            value={step.condition}
                            onChange={(e) => updateStep(step.id, 'condition', e.target.value)}
                            placeholder="Condition (e.g., 'No response to Day 1')"
                            style={{
                              width: '100%',
                              padding: '4px 8px',
                              border: `1px solid ${T.warning}44`,
                              borderRadius: 4,
                              fontSize: 11,
                              fontFamily: T.fontMono,
                              outline: 'none',
                              background: T.warning + '08',
                              color: T.warning,
                              boxSizing: 'border-box',
                            }}
                          />
                        ) : step.condition ? (
                          <span
                            style={{
                              fontSize: 11,
                              fontFamily: T.fontMono,
                              padding: '2px 8px',
                              borderRadius: 4,
                              background: T.warning + '10',
                              color: T.warning,
                            }}
                          >
                            if: {step.condition}
                          </span>
                        ) : null}
                      </div>
                    )}

                    {/* Editing extras */}
                    {isEditing && (
                      <div style={{ marginTop: 10, paddingLeft: 36, display: 'flex', gap: 8, alignItems: 'center' }}>
                        <select
                          value={step.status}
                          onChange={(e) => updateStep(step.id, 'status', e.target.value)}
                          style={{
                            fontSize: 11,
                            padding: '3px 8px',
                            border: `1px solid ${T.border}`,
                            borderRadius: 4,
                            fontFamily: T.fontMono,
                            outline: 'none',
                            background: T.cardBg,
                          }}
                        >
                          <option value="healthy">Healthy</option>
                          <option value="broken">Broken</option>
                          <option value="disabled">Disabled</option>
                        </select>
                        <select
                          value={step.timeOfDay}
                          onChange={(e) => updateStep(step.id, 'timeOfDay', e.target.value)}
                          style={{
                            fontSize: 11,
                            padding: '3px 8px',
                            border: `1px solid ${T.border}`,
                            borderRadius: 4,
                            fontFamily: T.fontMono,
                            outline: 'none',
                            background: T.cardBg,
                          }}
                        >
                          <option value="AM">Morning</option>
                          <option value="PM">Afternoon</option>
                        </select>
                        <label style={{ fontSize: 11, color: T.muted, display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={step.repeatWeekly}
                            onChange={() => updateStep(step.id, 'repeatWeekly', !step.repeatWeekly)}
                            style={{ accentColor: T.primary }}
                          />
                          Repeat weekly
                        </label>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Empty state */}
          {steps.length === 0 && (
            <div
              style={{
                textAlign: 'center',
                padding: '60px 20px',
                color: T.muted,
              }}
            >
              <div style={{ fontSize: 36, marginBottom: 12 }}>💬</div>
              <div style={{ fontSize: 14, fontWeight: 500 }}>
                Start describing your workflow in the chat
              </div>
              <div style={{ fontSize: 12, marginTop: 4 }}>
                Steps will appear here as you build them
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Best Practices Modal */}
      {showSuggestion && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setShowSuggestion(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: T.cardBg,
              borderRadius: 16,
              padding: 24,
              width: 440,
              maxHeight: '80vh',
              overflowY: 'auto',
              boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 style={{ fontFamily: T.fontHeader, fontSize: 18, margin: 0 }}>{showSuggestion.title}</h3>
              <button
                onClick={() => setShowSuggestion(null)}
                style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: T.muted }}
              >
                &times;
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {showSuggestion.items.map((item, i) => (
                <div
                  key={i}
                  style={{
                    padding: '12px 14px',
                    border: `1px solid ${T.border}`,
                    borderRadius: 10,
                    background: T.pageBg,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{item.label}</span>
                    <span
                      style={{
                        fontSize: 12,
                        fontFamily: T.fontMono,
                        fontWeight: 700,
                        color: item.score >= 80 ? T.success : item.score >= 60 ? T.warning : T.error,
                      }}
                    >
                      {item.score}/100
                    </span>
                  </div>
                  {/* Score bar */}
                  <div
                    style={{
                      width: '100%',
                      height: 4,
                      borderRadius: 2,
                      background: T.border,
                      marginBottom: 6,
                    }}
                  >
                    <div
                      style={{
                        width: `${item.score}%`,
                        height: '100%',
                        borderRadius: 2,
                        background: item.score >= 80 ? T.success : item.score >= 60 ? T.warning : T.error,
                        transition: 'width 0.5s',
                      }}
                    />
                  </div>
                  <div style={{ fontSize: 12, color: T.muted, lineHeight: 1.4 }}>{item.note}</div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setShowSuggestion(null)}
                style={{
                  padding: '8px 18px',
                  borderRadius: 8,
                  border: 'none',
                  background: T.primary,
                  color: '#fff',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontFamily: T.fontBody,
                }}
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Animations */}
      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </div>
  );
}
