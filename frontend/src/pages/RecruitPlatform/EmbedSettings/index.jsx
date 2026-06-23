import React, { useState } from 'react';
import { useRecruitPlatform } from '../../../contexts/RecruitPlatformContext';
import './EmbedSettings.css';

const APP_BASE = 'https://recruit.perenniaai.com';
const API_BASE_PUB = 'https://api.perenniaai.com';

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <button className={`es-copy-btn${copied ? ' copied' : ''}`} onClick={handleCopy}>
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  );
}

function CodeBlock({ code }) {
  return (
    <div className="es-code-wrap">
      <pre className="es-code">{code}</pre>
      <CopyButton text={code} />
    </div>
  );
}

// ── Tab 1: Chat Widget ────────────────────────────────────────────────────────
function ChatWidgetTab({ orgSlug }) {
  const scriptCode = `<!-- Perennia Recruiting Chat Widget -->\n<script src="${API_BASE_PUB}/api/v1/recruit-platform/chat/embed/${orgSlug}/widget.js"></script>`;
  const iframeSrc = `${APP_BASE}/recruit/chat-widget/${orgSlug}`;

  return (
    <>
      <div className="es-card">
        <div className="es-card-label">Embed Code</div>
        <CodeBlock code={scriptCode} />
        <div className="es-instructions">
          Add this script tag before the closing <code>&lt;/body&gt;</code> tag on your landing page.
          The chat bubble will appear automatically in the bottom-right corner.
        </div>
      </div>
      <div className="es-card">
        <div className="es-preview-label">Live Preview</div>
        <div className="es-preview-frame">
          <iframe
            src={iframeSrc}
            width="100%"
            height="500px"
            frameBorder="0"
            title="Chat Widget Preview"
          />
        </div>
      </div>
    </>
  );
}

// ── Tab 2: Application Form ───────────────────────────────────────────────────
function ApplicationFormTab({ orgSlug }) {
  const iframeSrc = `${APP_BASE}/recruit/apply/${orgSlug}`;
  const iframeCode = `<iframe\n  src="${iframeSrc}"\n  width="100%"\n  height="700px"\n  frameborder="0"\n></iframe>`;

  return (
    <>
      <div className="es-card">
        <div className="es-card-label">Embed Code</div>
        <CodeBlock code={iframeCode} />
        <div className="es-instructions">
          Paste this into your landing page HTML to embed the application form directly.
          Candidates can apply without leaving your site.
        </div>
      </div>
      <div className="es-card">
        <div className="es-preview-label">Preview</div>
        <div className="es-preview-frame">
          <iframe
            src={iframeSrc}
            width="100%"
            height="700px"
            frameBorder="0"
            title="Application Form Preview"
          />
        </div>
      </div>
    </>
  );
}

// ── Tab 3: Job Listings ───────────────────────────────────────────────────────
function JobListingsTab({ orgSlug }) {
  const iframeSrc = `${APP_BASE}/recruit/jobs-public/${orgSlug}`;
  const iframeCode = `<iframe\n  src="${iframeSrc}"\n  width="100%"\n  height="500px"\n  frameborder="0"\n></iframe>`;

  return (
    <>
      <div className="es-card">
        <div className="es-card-label">Embed Code</div>
        <CodeBlock code={iframeCode} />
        <div className="es-instructions">
          Embed your current job openings on any page. Updates automatically when you add or close positions.
        </div>
      </div>
      <div className="es-card">
        <div className="es-preview-label">Preview</div>
        <div className="es-preview-frame">
          <iframe
            src={iframeSrc}
            width="100%"
            height="500px"
            frameBorder="0"
            title="Job Listings Preview"
          />
        </div>
      </div>
    </>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function EmbedSettings() {
  const { recruitUser } = useRecruitPlatform();
  const orgSlug = recruitUser?.org_slug || recruitUser?.tenant_slug || 'your-org';
  const [activeTab, setActiveTab] = useState('chat');

  const tabs = [
    { id: 'chat', label: 'Chat Widget' },
    { id: 'form', label: 'Application Form' },
    { id: 'jobs', label: 'Job Listings' },
  ];

  return (
    <div className="es-layout">
      <div className="es-header">
        <h1 className="es-title">Embed & Share</h1>
        <p className="es-subtitle">Copy these embed codes to add Perennia Recruit to your landing pages</p>
      </div>

      <div className="es-tabs">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`es-tab${activeTab === tab.id ? ' active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'chat' && <ChatWidgetTab orgSlug={orgSlug} />}
      {activeTab === 'form' && <ApplicationFormTab orgSlug={orgSlug} />}
      {activeTab === 'jobs' && <JobListingsTab orgSlug={orgSlug} />}
    </div>
  );
}
