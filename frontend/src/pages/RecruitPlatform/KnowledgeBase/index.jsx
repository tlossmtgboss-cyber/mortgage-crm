import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useRecruitPlatform } from '../../../contexts/RecruitPlatformContext';
import './KnowledgeBase.css';

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';
const ALLOWED_TYPES = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain', 'text/markdown'];
const ALLOWED_EXT = ['.pdf', '.docx', '.txt', '.md'];
const MAX_BYTES = 10 * 1024 * 1024; // 10 MB

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function StatusBadge({ status }) {
  if (status === 'processing' || status === 'pending') {
    return <span className="kb-badge kb-badge-processing"><span className="kb-spinner" />Processing</span>;
  }
  if (status === 'ready' || status === 'complete') {
    return <span className="kb-badge kb-badge-ready">✓ Ready</span>;
  }
  return <span className="kb-badge kb-badge-failed">✗ Failed</span>;
}

// ── Section A: Document Library ───────────────────────────────────────────────
function DocumentLibrary({ recruitToken, orgSlug }) {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stagedFile, setStagedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);
  const refreshTimerRef = useRef(null);

  const fetchDocs = useCallback(() => {
    fetch(`${API_BASE}/api/v1/recruit-platform/kb/documents`, {
      headers: { Authorization: `Bearer ${recruitToken}` },
    })
      .then(r => r.ok ? r.json() : [])
      .then(data => setDocs(Array.isArray(data) ? data : (data.items || [])))
      .catch(() => setDocs([]))
      .finally(() => setLoading(false));
  }, [recruitToken]);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  // Auto-refresh while any doc is processing
  useEffect(() => {
    const hasProcessing = docs.some(d => d.status === 'processing' || d.status === 'pending');
    if (hasProcessing && !refreshTimerRef.current) {
      refreshTimerRef.current = setInterval(fetchDocs, 5000);
    } else if (!hasProcessing && refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
    return () => {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    };
  }, [docs, fetchDocs]);

  function validateFile(file) {
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXT.includes(ext) && !ALLOWED_TYPES.includes(file.type)) {
      return 'Only PDF, DOCX, TXT, and MD files are allowed.';
    }
    if (file.size > MAX_BYTES) {
      return `File too large. Max 10 MB (this file is ${formatBytes(file.size)}).`;
    }
    return null;
  }

  function handleFilePick(file) {
    setError('');
    const err = validateFile(file);
    if (err) { setError(err); return; }
    setStagedFile(file);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFilePick(file);
  }

  async function handleUpload() {
    if (!stagedFile) return;
    setUploading(true);
    setUploadProgress(0);
    setError('');

    const formData = new FormData();
    formData.append('file', stagedFile);

    // Use XMLHttpRequest for progress tracking
    await new Promise((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) setUploadProgress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = () => {
        setUploading(false);
        setStagedFile(null);
        setUploadProgress(0);
        fetchDocs();
        resolve();
      };
      xhr.onerror = () => {
        setError('Upload failed. Please try again.');
        setUploading(false);
        resolve();
      };
      xhr.open('POST', `${API_BASE}/api/v1/recruit-platform/kb/documents/upload`);
      xhr.setRequestHeader('Authorization', `Bearer ${recruitToken}`);
      xhr.send(formData);
    });
  }

  async function handleDelete(doc) {
    if (!window.confirm(`Delete "${doc.filename}"? This cannot be undone.`)) return;
    await fetch(`${API_BASE}/api/v1/recruit-platform/kb/documents/${doc.id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${recruitToken}` },
    });
    fetchDocs();
  }

  async function handleReprocess(doc) {
    await fetch(`${API_BASE}/api/v1/recruit-platform/kb/documents/${doc.id}/reprocess`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${recruitToken}` },
    });
    fetchDocs();
  }

  const fileExt = (filename) => filename ? filename.split('.').pop().toUpperCase() : '—';

  return (
    <div className="kb-section">
      <div className="kb-section-header">
        <h1 className="kb-title">Knowledge Base</h1>
        <p className="kb-subtitle">Upload collateral the AI will use to answer candidate questions</p>
      </div>

      <div className="kb-upload-area">
        <div
          className={`kb-drop-zone${dragOver ? ' drag-over' : ''}`}
          onClick={() => fileInputRef.current?.click()}
          onDrop={handleDrop}
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
        >
          <div className="kb-drop-icon">📄</div>
          <div className="kb-drop-label">Drop a file here, or click to browse</div>
          <div className="kb-drop-sub">PDF, DOCX, TXT, MD — max 10 MB</div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            onChange={e => e.target.files[0] && handleFilePick(e.target.files[0])}
          />
        </div>

        {error && <div style={{ marginTop: 10, color: '#dc2626', fontSize: 13 }}>{error}</div>}

        {stagedFile && (
          <>
            <div className="kb-staged-file">
              <span className="kb-staged-filename">{stagedFile.name}</span>
              <span className="kb-staged-size">{formatBytes(stagedFile.size)}</span>
            </div>
            {uploading && (
              <div className="kb-progress-bar-wrap">
                <div className="kb-progress-bar" style={{ width: `${uploadProgress}%` }} />
              </div>
            )}
            <div className="kb-upload-actions">
              <button className="kb-btn-primary" onClick={handleUpload} disabled={uploading}>
                {uploading ? `Uploading… ${uploadProgress}%` : 'Upload'}
              </button>
              <button className="kb-btn-secondary" onClick={() => setStagedFile(null)} disabled={uploading}>
                Cancel
              </button>
            </div>
          </>
        )}
      </div>

      <div className="kb-table-wrap">
        {loading ? (
          <div className="kb-empty">Loading documents…</div>
        ) : docs.length === 0 ? (
          <div className="kb-empty">No documents uploaded yet. Upload one above to get started.</div>
        ) : (
          <table className="kb-table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Type</th>
                <th>Size</th>
                <th>Status</th>
                <th>Chunks</th>
                <th>Uploaded</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {docs.map(doc => (
                <tr key={doc.id}>
                  <td style={{ fontWeight: 600 }}>{doc.filename || doc.name}</td>
                  <td>{fileExt(doc.filename || doc.name)}</td>
                  <td>{doc.file_size ? formatBytes(doc.file_size) : '—'}</td>
                  <td><StatusBadge status={doc.status} /></td>
                  <td>{doc.chunk_count ?? '—'}</td>
                  <td>{formatDate(doc.created_at || doc.uploaded_at)}</td>
                  <td>
                    <button className="kb-action-btn kb-action-btn-delete" onClick={() => handleDelete(doc)}>
                      Delete
                    </button>
                    {(doc.status === 'failed' || doc.status === 'error') && (
                      <button className="kb-action-btn kb-action-btn-reprocess" onClick={() => handleReprocess(doc)}>
                        Reprocess
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── Section B: Test the AI ────────────────────────────────────────────────────
function TestAI({ recruitToken, orgSlug }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const sessionId = useRef(`test-${Date.now()}`);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, typing]);

  async function handleSend(e) {
    e.preventDefault();
    if (!input.trim() || typing) return;
    const text = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text }]);
    setTyping(true);

    try {
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/chat/${orgSlug}/message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${recruitToken}`,
        },
        body: JSON.stringify({ session_id: sessionId.current, message: text }),
      });
      const data = await res.json();
      setMessages(prev => [...prev, { role: 'ai', text: data.response || data.message || 'No response.' }]);
    } catch {
      setMessages(prev => [...prev, { role: 'ai', text: 'Error reaching AI. Check your network and try again.' }]);
    } finally {
      setTyping(false);
    }
  }

  return (
    <div className="kb-section">
      <div className="kb-section-header">
        <h2 className="kb-title" style={{ fontSize: 17 }}>Test your AI assistant</h2>
      </div>
      <div className="kb-test-section">
        <p className="kb-test-label">This tests what candidates will experience when chatting from your landing page.</p>
        <div className="kb-chat-messages">
          {messages.length === 0 && <span className="kb-chat-empty">Ask a question to test the AI…</span>}
          {messages.map((m, i) => (
            <div key={i} className={`kb-msg kb-msg-${m.role === 'user' ? 'user' : 'ai'}`}>{m.text}</div>
          ))}
          {typing && <div className="kb-msg-typing">···</div>}
          <div ref={bottomRef} />
        </div>
        <form onSubmit={handleSend} className="kb-chat-input-row">
          <input
            className="kb-chat-input"
            placeholder="Ask a question…"
            value={input}
            onChange={e => setInput(e.target.value)}
            disabled={typing}
          />
          <button className="kb-btn-primary" type="submit" disabled={typing || !input.trim()}>
            Send
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function KnowledgeBase() {
  const { recruitToken, recruitUser } = useRecruitPlatform();
  const orgSlug = recruitUser?.org_slug || recruitUser?.tenant_slug || 'test';

  return (
    <div className="kb-layout">
      <DocumentLibrary recruitToken={recruitToken} orgSlug={orgSlug} />
      <TestAI recruitToken={recruitToken} orgSlug={orgSlug} />
    </div>
  );
}
