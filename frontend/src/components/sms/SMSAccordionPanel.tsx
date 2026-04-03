/**
 * SMSAccordionPanel — Perennia AI
 * Reusable SMS panel for Client, Partner, and Recruiting profile pages.
 * Drop onto any profile page with a single import.
 *
 * Usage:
 *   import SMSAccordionPanel from '@/components/sms/SMSAccordionPanel'
 *
 *   <SMSAccordionPanel
 *     contactId="uuid"
 *     contactName="Jennifer Marlow"
 *     phone="+18435550218"
 *     pageType="client"         // "client" | "partner" | "recruit"
 *     assignedUser="Marcus Webb"
 *   />
 *
 * Backend requirements:
 *   GET  /api/sms/conversations/:contactId          → SmsMessage[]
 *   POST /api/sms/send                              → { message, mediaUrls? }
 *   POST /api/sms/upload-media                      → { url: string }
 *   WS   /ws/sms/:contactId                         → push inbound SmsMessage
 *
 * Telnyx:
 *   - Outbound: POST https://api.telnyx.com/v2/messages
 *   - Webhooks: inbound message events → your /api/sms/webhook
 *   - MMS media_urls must be publicly accessible before sending
 */

import React, {
  useState, useRef, useEffect, useCallback, ReactNode
} from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

export type PageType = 'client' | 'partner' | 'recruit'

export interface SmsMessage {
  id: string
  direction: 'inbound' | 'outbound'
  body: string
  senderName: string
  senderRole?: string
  timestamp: string          // ISO 8601
  status?: 'sending' | 'delivered' | 'failed' | 'unread'
  mediaUrls?: MediaAttachment[]
}

export interface MediaAttachment {
  url: string
  type: 'document' | 'image' | 'video'
  filename: string
  sizeLabel?: string
  durationLabel?: string     // videos only
}

export interface StagedFile {
  id: string
  file?: File
  name: string
  sizeLabel: string
  type: 'document' | 'image' | 'video' | 'recorded-video'
  previewUrl?: string
  blobUrl?: string           // recorded video blob URL
}

export interface BorrowerOption {
  id: number | string
  name: string
  phone: string
  type: 'primary' | 'co-borrower' | string
}

export interface SMSAccordionPanelProps {
  contactId: string
  contactName: string
  phone: string
  pageType: PageType
  assignedUser?: string
  /** Multiple borrowers — shows a selector when length > 1 */
  borrowers?: BorrowerOption[]
  /** Pass existing messages for SSR/initial load; panel also fetches from API */
  initialMessages?: SmsMessage[]
  /** Override the API base path */
  apiBase?: string
  /** WebSocket URL override */
  wsUrl?: string
  /** Called when panel opens/closes */
  onToggle?: (isOpen: boolean) => void
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const h = d.getHours() % 12 || 12
  const m = String(d.getMinutes()).padStart(2, '0')
  const ap = d.getHours() >= 12 ? 'PM' : 'AM'
  return `${h}:${m} ${ap}`
}

function formatDateDivider(iso: string): string {
  const d = new Date(iso)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function groupByDate(messages: SmsMessage[]): Array<{ label: string; messages: SmsMessage[] }> {
  const groups: Record<string, SmsMessage[]> = {}
  messages.forEach(m => {
    const label = formatDateDivider(m.timestamp)
    if (!groups[label]) groups[label] = []
    groups[label].push(m)
  })
  return Object.entries(groups).map(([label, messages]) => ({ label, messages }))
}

function pageLabel(type: PageType): string {
  return { client: 'Client', partner: 'Partner', recruit: 'Candidate' }[type]
}

function uniqId() {
  return Math.random().toString(36).slice(2, 10)
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function DocBubble({ attach }: { attach: MediaAttachment }) {
  return (
    <div style={styles.docBubble}>
      <div style={styles.docIcon}>
        <FileIcon />
      </div>
      <div style={styles.docInfo}>
        <div style={styles.docName}>{attach.filename}</div>
        <div style={styles.docSize}>{attach.sizeLabel} · {attach.type.toUpperCase()}</div>
      </div>
    </div>
  )
}

function VideoBubble({ attach }: { attach: MediaAttachment }) {
  return (
    <div style={styles.videoBubble}>
      <div style={styles.videoThumb}>
        <div style={styles.playBtn}>
          <svg width="14" height="14" viewBox="0 0 16 16">
            <polygon points="5,3 13,8 5,13" fill="#7EB8F7" />
          </svg>
        </div>
        <span style={styles.videoLabel}>{attach.filename}</span>
        {attach.durationLabel && (
          <span style={styles.videoDuration}>{attach.durationLabel}</span>
        )}
      </div>
    </div>
  )
}

function MessageBubble({ msg }: { msg: SmsMessage }) {
  const isOut = msg.direction === 'outbound'
  const rowStyle = {
    ...styles.msgRow,
    alignItems: isOut ? 'flex-end' : 'flex-start',
  } as React.CSSProperties

  return (
    <div style={rowStyle}>
      <span style={{ ...styles.msgSender, color: isOut ? '#5A9ED4' : '#7EB8F7' }}>
        {msg.senderName}{msg.senderRole ? ` · ${msg.senderRole}` : ''}
      </span>

      {msg.body && (
        <div style={{
          ...styles.msgBubble,
          ...(isOut ? styles.msgBubbleOut : styles.msgBubbleIn),
          ...(msg.status === 'unread' ? styles.msgBubbleUnread : {}),
        }}>
          {msg.body}
        </div>
      )}

      {msg.mediaUrls?.map((att, i) => {
        if (att.type === 'video') return <VideoBubble key={i} attach={att} />
        if (att.type === 'document' || att.type === 'image') return <DocBubble key={i} attach={att} />
        return null
      })}

      <span style={styles.msgMeta}>
        {formatTime(msg.timestamp)}
        {msg.status && msg.direction === 'outbound' && ` · ${msg.status.charAt(0).toUpperCase() + msg.status.slice(1)}`}
        {msg.status === 'unread' && msg.direction === 'inbound' && ' · Unread'}
      </span>
    </div>
  )
}

// ─── Video Recorder ───────────────────────────────────────────────────────────

interface VideoRecorderProps {
  onAttach: (staged: StagedFile) => void
  onClose: () => void
}

function VideoRecorder({ onAttach, onClose }: VideoRecorderProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [phase, setPhase] = useState<'idle' | 'previewing' | 'recording' | 'done'>('idle')
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const intervalRef = useRef<number>(0)

  useEffect(() => {
    initCamera()
    return () => stopStream()
  }, [])

  async function initCamera() {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
      streamRef.current = s
      if (videoRef.current) {
        videoRef.current.srcObject = s
        videoRef.current.play()
      }
      setPhase('previewing')
    } catch {
      setError('Camera access denied — check browser permissions')
    }
  }

  function startRecording() {
    if (!streamRef.current) return
    chunksRef.current = []
    const mr = new MediaRecorder(streamRef.current)
    mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data) }
    mr.onstop = () => setPhase('done')
    mr.start()
    recorderRef.current = mr
    setSeconds(0)
    setPhase('recording')
    intervalRef.current = window.setInterval(() => setSeconds(s => s + 1), 1000)
  }

  function stopRecording() {
    recorderRef.current?.stop()
    clearInterval(intervalRef.current)
  }

  function stopStream() {
    streamRef.current?.getTracks().forEach(t => t.stop())
    clearInterval(intervalRef.current)
  }

  function handleAttach() {
    const blob = new Blob(chunksRef.current, { type: 'video/mp4' })
    const blobUrl = URL.createObjectURL(blob)
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    onAttach({
      id: uniqId(),
      name: `Video_${new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}.mp4`,
      sizeLabel: `${m}:${String(s).padStart(2, '0')} · recorded`,
      type: 'recorded-video',
      blobUrl,
      file: new File(chunksRef.current, 'recording.mp4', { type: 'video/mp4' }),
    })
    stopStream()
    onClose()
  }

  const fmtTime = (sec: number) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`

  return (
    <div style={styles.recorderPanel}>
      <div style={styles.recPreview}>
        <video
          ref={videoRef}
          muted
          playsInline
          style={{ width: '100%', height: '100%', objectFit: 'cover', display: phase === 'idle' ? 'none' : 'block' }}
        />
        {phase === 'idle' && !error && (
          <div style={styles.recPlaceholder}>
            <VideoIcon color="#7EB8F7" />
            <span style={styles.recHint}>Initializing camera…</span>
          </div>
        )}
        {error && (
          <div style={styles.recPlaceholder}>
            <span style={{ ...styles.recHint, color: '#E87070' }}>{error}</span>
          </div>
        )}
        {phase === 'recording' && (
          <div style={styles.recTimer}>
            <span style={styles.recDot} />
            {fmtTime(seconds)}
          </div>
        )}
        {phase === 'done' && (
          <div style={styles.recDoneOverlay}>
            <span style={{ fontSize: 12, color: '#7EB8F7', fontFamily: 'DM Mono, monospace' }}>
              Recording complete · {fmtTime(seconds)}
            </span>
          </div>
        )}
      </div>
      <div style={styles.recControls}>
        {phase === 'previewing' && (
          <button style={{ ...styles.recBtn, ...styles.recBtnStart }} onClick={startRecording}>
            Start Recording
          </button>
        )}
        {phase === 'recording' && (
          <button style={{ ...styles.recBtn, ...styles.recBtnStop }} onClick={stopRecording}>
            Stop
          </button>
        )}
        {phase === 'done' && (
          <button style={{ ...styles.recBtn, ...styles.recBtnAttach }} onClick={handleAttach}>
            Attach Video
          </button>
        )}
        <button style={{ ...styles.recBtn, ...styles.recBtnCancel }} onClick={() => { stopStream(); onClose() }}>
          Cancel
        </button>
      </div>
    </div>
  )
}

// ─── Attach Tray ──────────────────────────────────────────────────────────────

interface AttachTrayProps {
  onFilePick: (type: 'document' | 'image' | 'video') => void
  onRecordVideo: () => void
}

function AttachTray({ onFilePick, onRecordVideo }: AttachTrayProps) {
  return (
    <div style={styles.attachTray}>
      <div style={styles.attachRow}>
        <AttachOption
          icon={<FileIcon />}
          label="Document"
          sub="PDF, DOCX, XLSX"
          onClick={() => onFilePick('document')}
        />
        <AttachOption
          icon={<ImageIcon />}
          label="Photo / Image"
          sub="JPG, PNG, HEIC"
          onClick={() => onFilePick('image')}
        />
      </div>
      <div style={styles.attachRow}>
        <AttachOption
          icon={<VideoIcon color="#E87070" />}
          label="Record Video"
          labelColor="#E8A0A0"
          sub="Shoot now · MMS"
          onClick={onRecordVideo}
        />
        <AttachOption
          icon={<VideoIcon color="#7EB8F7" />}
          label="Upload Video"
          sub="MP4, MOV · from library"
          onClick={() => onFilePick('video')}
        />
      </div>
    </div>
  )
}

function AttachOption({
  icon, label, sub, onClick, labelColor = '#A8C0D8',
}: {
  icon: ReactNode
  label: string
  sub: string
  onClick: () => void
  labelColor?: string
}) {
  const [hov, setHov] = useState(false)
  return (
    <div
      style={{ ...styles.attachOpt, ...(hov ? styles.attachOptHov : {}) }}
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      <div style={styles.attachOptIcon}>{icon}</div>
      <div>
        <div style={{ ...styles.attachOptLabel, color: labelColor }}>{label}</div>
        <div style={styles.attachOptSub}>{sub}</div>
      </div>
    </div>
  )
}

// ─── Staged Files ─────────────────────────────────────────────────────────────

function StagedFiles({ files, onRemove }: { files: StagedFile[]; onRemove: (id: string) => void }) {
  if (!files.length) return null
  return (
    <div style={styles.stagedArea}>
      {files.map(f => (
        <div key={f.id} style={styles.stagedFile}>
          {(f.type === 'video' || f.type === 'recorded-video')
            ? <VideoIcon color="#7EB8F7" size={14} />
            : <FileIcon size={14} />
          }
          <span style={styles.stagedName}>{f.name}</span>
          <span style={styles.stagedSize}>{f.sizeLabel}</span>
          <span style={styles.stagedRemove} onClick={() => onRemove(f.id)}>×</span>
        </div>
      ))}
    </div>
  )
}

// ─── SVG Icons ────────────────────────────────────────────────────────────────

function FileIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="#7EB8F7" strokeWidth="1.5">
      <rect x="3" y="1" width="10" height="14" rx="1.5" />
      <path d="M6 5h4M6 8h4M6 11h2" />
    </svg>
  )
}

function ImageIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="#7EB8F7" strokeWidth="1.5">
      <rect x="2" y="3" width="12" height="10" rx="1.5" />
      <circle cx="5.5" cy="6.5" r="1" />
      <path d="M2 10l3.5-3 3 3 2-2 3 2" />
    </svg>
  )
}

function VideoIcon({ color = '#7EB8F7', size = 16 }: { color?: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5">
      <rect x="2" y="4" width="9" height="8" rx="1.5" />
      <path d="M11 6.5l3-2v7l-3-2" />
    </svg>
  )
}

function AttachIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#7EB8F7" strokeWidth="1.5">
      <path d="M13 7.5l-5.5 5.5a3.5 3.5 0 01-4.95-4.95l5.5-5.5a2 2 0 012.83 2.83L5.38 10.9a.5.5 0 01-.7-.7l4.24-4.25" />
    </svg>
  )
}

function ChevronIcon({ up }: { up: boolean }) {
  return (
    <svg
      width="16" height="16" viewBox="0 0 16 16" fill="none"
      stroke="#6B7A99" strokeWidth="1.5"
      style={{ transition: 'transform 0.3s ease', transform: up ? 'rotate(180deg)' : 'none' }}
    >
      <path d="M4 6l4 4 4-4" />
    </svg>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function SMSAccordionPanel({
  contactId,
  contactName,
  phone,
  pageType,
  assignedUser,
  borrowers,
  initialMessages = [],
  apiBase = '/api',
  wsUrl,
  onToggle,
}: SMSAccordionPanelProps) {
  // Borrower selection — default to primary phone/name
  const [selectedBorrowerIdx, setSelectedBorrowerIdx] = useState(0)
  const hasBorrowerChoice = borrowers && borrowers.length > 1
  const activeBorrower = borrowers && borrowers.length > 0
    ? borrowers[selectedBorrowerIdx] || borrowers[0]
    : null
  const activePhone = activeBorrower?.phone || phone
  const activeName = activeBorrower?.name || contactName

  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<SmsMessage[]>(initialMessages)
  const [staged, setStaged] = useState<StagedFile[]>([])
  const [text, setText] = useState('')
  const [tray, setTray] = useState<'none' | 'attach' | 'recorder'>('none')
  const [sending, setSending] = useState(false)
  const [unreadCount, setUnreadCount] = useState(
    () => initialMessages.filter(m => m.status === 'unread' && m.direction === 'inbound').length
  )

  const threadRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const filePickType = useRef<'document' | 'image' | 'video'>('document')
  const wsRef = useRef<WebSocket | null>(null)

  // When borrower changes, reload conversation for that phone number
  useEffect(() => {
    if (open && activePhone) {
      setMessages([])
      fetchHistory()
      wsRef.current?.close()
      connectWS()
    }
  }, [selectedBorrowerIdx])

  // Fetch history on open
  useEffect(() => {
    if (!open) return
    if (messages.length === 0) fetchHistory()
    scrollToBottom()
    setUnreadCount(0)
    connectWS()
    return () => wsRef.current?.close()
  }, [open])

  async function fetchHistory() {
    try {
      const phoneParam = encodeURIComponent(activePhone)
      const res = await fetch(`${apiBase}/v1/sms/conversations/${phoneParam}`)
      if (!res.ok) return
      const data: SmsMessage[] = await res.json()
      setMessages(data)
    } catch (e) {
      console.error('[SMS] Failed to fetch history', e)
    }
  }

  function connectWS() {
    const phoneParam = encodeURIComponent(activePhone)
    const url = wsUrl || `${window.location.origin.replace(/^http/, 'ws')}/ws/sms/${phoneParam}`
    const ws = new WebSocket(url)
    ws.onmessage = e => {
      const msg: SmsMessage = JSON.parse(e.data)
      setMessages(prev => [...prev, msg])
      if (msg.direction === 'inbound') scrollToBottom()
    }
    ws.onerror = () => { /* silent — WS optional for real-time */ }
    wsRef.current = ws
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      if (threadRef.current) threadRef.current.scrollTop = 99999
    })
  }

  function toggle() {
    const next = !open
    setOpen(next)
    setTray('none')
    onToggle?.(next)
  }

  // ── File picker ──

  function openFilePicker(type: 'document' | 'image' | 'video') {
    filePickType.current = type
    if (!fileInputRef.current) return
    fileInputRef.current.accept =
      type === 'document' ? '.pdf,.docx,.doc,.xlsx,.xls,.txt'
      : type === 'image' ? 'image/*'
      : 'video/*'
    fileInputRef.current.click()
  }

  function onFilePicked(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setStaged(prev => [...prev, {
      id: uniqId(),
      file,
      name: file.name,
      sizeLabel: formatBytes(file.size),
      type: filePickType.current,
    }])
    setTray('none')
    e.target.value = ''
  }

  function removeStaged(id: string) {
    setStaged(prev => prev.filter(f => f.id !== id))
  }

  // ── Send ──

  async function sendMessage() {
    if (!text.trim() && !staged.length) return
    setSending(true)

    // Optimistic UI
    const optimisticId = uniqId()
    const now = new Date().toISOString()
    const optimistic: SmsMessage = {
      id: optimisticId,
      direction: 'outbound',
      body: text.trim(),
      senderName: assignedUser || 'You',
      timestamp: now,
      status: 'sending',
      mediaUrls: staged.map(f => ({
        url: f.blobUrl || '',
        type: f.type === 'recorded-video' ? 'video' : f.type,
        filename: f.name,
        sizeLabel: f.sizeLabel,
      })),
    }
    setMessages(prev => [...prev, optimistic])
    setText('')
    setStaged([])
    scrollToBottom()

    try {
      // Upload media files first → get public URLs for Telnyx
      const mediaUrls: string[] = []
      for (const sf of staged) {
        if (sf.file) {
          const form = new FormData()
          form.append('file', sf.file)
          form.append('contactId', contactId)
          const res = await fetch(`${apiBase}/v1/sms/upload-media`, { method: 'POST', body: form })
          if (res.ok) {
            const { url } = await res.json()
            mediaUrls.push(url)
          }
        }
      }

      // Send via FastAPI → Telnyx endpoint
      const res = await fetch(`${apiBase}/v1/sms/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contactId,
          to: activePhone,
          message: text.trim(),
          mediaUrls,
          pageType,
          borrowerType: activeBorrower?.type || 'primary',
        }),
      })

      if (!res.ok) throw new Error('Send failed')

      // Update optimistic → delivered
      setMessages(prev =>
        prev.map(m => m.id === optimisticId ? { ...m, status: 'delivered' } : m)
      )
    } catch {
      setMessages(prev =>
        prev.map(m => m.id === optimisticId ? { ...m, status: 'failed' } : m)
      )
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  function autoResize(el: HTMLTextAreaElement) {
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 80) + 'px'
  }

  // ── Computed ──

  const hasAttachments = staged.length > 0
  const isMMS = hasAttachments
  const charCount = text.length

  const grouped = groupByDate(messages)

  // ─── Render ─────────────────────────────────────────────────────────────────

  return (
    <>
      {/* Hidden file input */}
      <input ref={fileInputRef} type="file" style={{ display: 'none' }} onChange={onFilePicked} />

      <div style={{
        ...styles.panel,
        transform: open ? 'translateY(0)' : `translateY(calc(100% - 52px))`,
      }}>
        {/* ── Handle bar ── */}
        <div style={styles.handle} onClick={toggle}>
          <div style={styles.handleLeft}>
            <div style={{
              ...styles.smsDot,
              animation: unreadCount > 0 && !open ? 'smsPulse 2s infinite' : 'none',
              opacity: unreadCount > 0 && !open ? 1 : 0.4,
            }} />
            <span style={styles.handleTitle}>
              SMS · {activeName}
              {hasBorrowerChoice && (
                <span style={styles.handleSub}> ({activeBorrower?.type})</span>
              )}
              <span style={styles.handleSub}> — {pageLabel(pageType)}</span>
            </span>
            {unreadCount > 0 && !open && (
              <span style={styles.unreadBadge}>{unreadCount} new</span>
            )}
          </div>
          <ChevronIcon up={open} />
        </div>

        {/* ── Body ── */}
        <div style={styles.body}>

          {/* Borrower selector — only when multiple borrowers */}
          {hasBorrowerChoice && (
            <div style={styles.borrowerSelector} onClick={e => e.stopPropagation()}>
              <span style={styles.borrowerLabel}>Messaging:</span>
              <div style={styles.borrowerPills}>
                {borrowers!.map((b, idx) => (
                  <button
                    key={b.id}
                    style={{
                      ...styles.borrowerPill,
                      ...(idx === selectedBorrowerIdx ? styles.borrowerPillActive : {}),
                    }}
                    onClick={() => setSelectedBorrowerIdx(idx)}
                  >
                    <span style={styles.borrowerPillName}>{b.name}</span>
                    <span style={styles.borrowerPillType}>
                      {b.type === 'primary' ? 'Primary' : 'Co-Borrower'}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Top bar */}
          <div style={styles.topBar}>
            <span style={styles.topContact}>
              To: <span style={{ color: '#7EB8F7' }}>{activePhone}</span> · {activeName}
            </span>
            <div style={styles.topActions}>
              <button style={styles.iconBtn}>Call</button>
              <button style={styles.iconBtn}>Note</button>
              <button style={styles.iconBtn}>Archive</button>
            </div>
          </div>

          {/* Message thread */}
          <div ref={threadRef} style={styles.thread}>
            {grouped.map(group => (
              <React.Fragment key={group.label}>
                <div style={styles.dateDivider}>
                  <span style={styles.dateDividerSpan}>{group.label}</span>
                </div>
                {group.messages.map(msg => (
                  <MessageBubble key={msg.id} msg={msg} />
                ))}
              </React.Fragment>
            ))}
            {messages.length === 0 && (
              <div style={styles.emptyThread}>
                No messages yet — send the first one below
              </div>
            )}
          </div>

          {/* Staged files */}
          <StagedFiles files={staged} onRemove={removeStaged} />

          {/* Attach tray */}
          {tray === 'attach' && (
            <AttachTray
              onFilePick={t => { openFilePicker(t) }}
              onRecordVideo={() => setTray('recorder')}
            />
          )}

          {/* Video recorder */}
          {tray === 'recorder' && (
            <VideoRecorder
              onAttach={sf => {
                setStaged(prev => [...prev, sf])
                setTray('none')
              }}
              onClose={() => setTray('none')}
            />
          )}

          {/* Compose */}
          <div style={styles.compose}>
            <div style={styles.toolbar}>
              <button
                style={{ ...styles.toolBtn, ...(tray === 'attach' ? styles.toolBtnActive : {}) }}
                title="Attach file"
                onClick={() => setTray(t => t === 'attach' ? 'none' : 'attach')}
              >
                <AttachIcon />
              </button>
              <button
                style={{ ...styles.toolBtn, ...(tray === 'recorder' ? styles.toolBtnActive : {}) }}
                title="Record video"
                onClick={() => setTray(t => t === 'recorder' ? 'none' : 'recorder')}
              >
                <VideoIcon color={tray === 'recorder' ? '#E87070' : '#7EB8F7'} size={14} />
              </button>
              <div style={{ flex: 1 }} />
              {isMMS && <span style={styles.mmsBadge}>MMS</span>}
              <span style={styles.charCount}>{charCount} / 160</span>
            </div>

            <div style={styles.composeRow}>
              <textarea
                ref={textareaRef}
                style={styles.textarea}
                placeholder={`Reply to ${activeName}…`}
                value={text}
                rows={1}
                onChange={e => {
                  setText(e.target.value)
                  autoResize(e.target)
                }}
                onKeyDown={handleKeyDown}
              />
              <button
                style={{
                  ...styles.sendBtn,
                  opacity: sending ? 0.6 : 1,
                  cursor: sending ? 'not-allowed' : 'pointer',
                }}
                onClick={sendMessage}
                disabled={sending}
              >
                {sending ? 'Sending…' : 'Send'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Keyframe injection */}
      <style>{`
        @keyframes smsPulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.35; }
        }
      `}</style>
    </>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = {
  panel: {
    position: 'fixed' as const,
    bottom: 0,
    left: 0,
    right: 0,
    transition: 'transform 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
    zIndex: 100,
    fontFamily: "'DM Sans', sans-serif",
  },
  handle: {
    background: 'rgba(10, 18, 32, 0.97)',
    backdropFilter: 'blur(12px)',
    borderTop: '1px solid rgba(126, 184, 247, 0.25)',
    borderLeft: '0.5px solid rgba(126, 184, 247, 0.1)',
    borderRight: '0.5px solid rgba(126, 184, 247, 0.1)',
    borderRadius: '12px 12px 0 0',
    padding: '0 16px',
    cursor: 'pointer',
    height: 52,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  handleLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
  },
  smsDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    background: '#7EB8F7',
    flexShrink: 0,
  },
  handleTitle: {
    fontSize: 13,
    fontWeight: 500,
    color: '#E8EEF7',
  },
  handleSub: {
    fontSize: 12,
    color: '#6B7A99',
    fontWeight: 400,
  },
  unreadBadge: {
    background: 'rgba(126, 184, 247, 0.15)',
    border: '0.5px solid rgba(126, 184, 247, 0.4)',
    borderRadius: 20,
    padding: '2px 9px',
    fontSize: 11,
    color: '#7EB8F7',
    fontFamily: "'DM Mono', monospace",
  },
  body: {
    background: 'rgba(8, 14, 26, 0.98)',
    height: 460,
    display: 'flex',
    flexDirection: 'column' as const,
    borderLeft: '0.5px solid rgba(126, 184, 247, 0.1)',
    borderRight: '0.5px solid rgba(126, 184, 247, 0.1)',
  },
  borrowerSelector: {
    padding: '8px 16px',
    borderBottom: '0.5px solid rgba(126, 184, 247, 0.12)',
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    flexShrink: 0,
  },
  borrowerLabel: {
    fontSize: 11,
    color: '#4A6080',
    fontFamily: "'DM Mono', monospace",
    whiteSpace: 'nowrap' as const,
  },
  borrowerPills: {
    display: 'flex',
    gap: 6,
    flex: 1,
    overflow: 'auto' as const,
  },
  borrowerPill: {
    background: 'rgba(126,184,247,0.06)',
    border: '0.5px solid rgba(126,184,247,0.18)',
    borderRadius: 8,
    padding: '5px 10px',
    cursor: 'pointer',
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'flex-start' as const,
    minWidth: 0,
    flexShrink: 0,
    transition: 'all 0.2s',
  },
  borrowerPillActive: {
    background: 'rgba(126,184,247,0.18)',
    borderColor: 'rgba(126,184,247,0.5)',
  },
  borrowerPillName: {
    fontSize: 12,
    fontWeight: 500,
    color: '#B8D8F5',
    whiteSpace: 'nowrap' as const,
  },
  borrowerPillType: {
    fontSize: 10,
    color: '#4A6080',
    fontFamily: "'DM Mono', monospace",
  },
  topBar: {
    padding: '10px 16px',
    borderBottom: '0.5px solid rgba(255, 255, 255, 0.07)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexShrink: 0,
  },
  topContact: {
    fontSize: 12,
    color: '#6B7A99',
    fontFamily: "'DM Mono', monospace",
  },
  topActions: {
    display: 'flex',
    gap: 8,
  },
  iconBtn: {
    background: 'rgba(126, 184, 247, 0.07)',
    border: '0.5px solid rgba(126, 184, 247, 0.2)',
    borderRadius: 6,
    padding: '4px 8px',
    fontSize: 11,
    color: '#7EB8F7',
    cursor: 'pointer',
    fontFamily: "'DM Mono', monospace",
  },
  thread: {
    flex: 1,
    overflowY: 'auto' as const,
    padding: 16,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 12,
    scrollBehavior: 'smooth' as const,
  },
  emptyThread: {
    textAlign: 'center' as const,
    fontSize: 12,
    color: '#3D4E66',
    fontFamily: "'DM Mono', monospace",
    marginTop: 40,
  },
  dateDivider: {
    textAlign: 'center' as const,
    fontSize: 10,
    color: '#3D4E66',
    fontFamily: "'DM Mono', monospace",
    padding: '4px 0',
    position: 'relative' as const,
    borderTop: '0.5px solid rgba(255,255,255,0.06)',
  },
  dateDividerSpan: {
    background: '#08101A',
    padding: '0 12px',
    position: 'relative' as const,
    top: -8,
  },
  msgRow: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 3,
  },
  msgSender: {
    fontSize: 10,
    fontFamily: "'DM Mono', monospace",
    fontWeight: 500,
  },
  msgBubble: {
    maxWidth: '72%',
    padding: '9px 13px',
    borderRadius: 12,
    fontSize: 13,
    lineHeight: 1.5,
  },
  msgBubbleIn: {
    background: 'rgba(255,255,255,0.07)',
    border: '0.5px solid rgba(255,255,255,0.1)',
    color: '#C8D4E8',
    borderBottomLeftRadius: 3,
  },
  msgBubbleOut: {
    background: 'rgba(126,184,247,0.12)',
    border: '0.5px solid rgba(126,184,247,0.25)',
    color: '#B8D8F5',
    borderBottomRightRadius: 3,
  },
  msgBubbleUnread: {
    borderColor: 'rgba(126,184,247,0.45)',
  },
  msgMeta: {
    fontSize: 10,
    color: '#4A5568',
    fontFamily: "'DM Mono', monospace",
    padding: '0 4px',
  },
  docBubble: {
    maxWidth: '72%',
    padding: '10px 13px',
    borderRadius: 12,
    borderBottomRightRadius: 3,
    background: 'rgba(126,184,247,0.08)',
    border: '0.5px solid rgba(126,184,247,0.25)',
    display: 'flex',
    alignItems: 'center',
    gap: 10,
  },
  docIcon: {
    width: 32,
    height: 32,
    borderRadius: 6,
    background: 'rgba(126,184,247,0.15)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  docInfo: {
    flex: 1,
    minWidth: 0,
  },
  docName: {
    fontSize: 12,
    color: '#B8D8F5',
    fontFamily: "'DM Mono', monospace",
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  docSize: {
    fontSize: 10,
    color: '#4A6080',
    fontFamily: "'DM Mono', monospace",
    marginTop: 2,
  },
  videoBubble: {
    maxWidth: '72%',
    borderRadius: 12,
    borderBottomRightRadius: 3,
    overflow: 'hidden',
    border: '0.5px solid rgba(126,184,247,0.3)',
    cursor: 'pointer',
  },
  videoThumb: {
    width: 220,
    height: 124,
    background: 'linear-gradient(135deg,#0d1f35,#152d4a)',
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  playBtn: {
    width: 36,
    height: 36,
    borderRadius: '50%',
    background: 'rgba(126,184,247,0.2)',
    border: '1.5px solid rgba(126,184,247,0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  videoLabel: {
    fontSize: 10,
    color: '#6B8AAA',
    fontFamily: "'DM Mono', monospace",
  },
  videoDuration: {
    fontSize: 10,
    color: '#7EB8F7',
    fontFamily: "'DM Mono', monospace",
  },
  stagedArea: {
    padding: '6px 14px',
    borderTop: '0.5px solid rgba(126,184,247,0.1)',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 5,
    flexShrink: 0,
  },
  stagedFile: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    background: 'rgba(126,184,247,0.06)',
    border: '0.5px solid rgba(126,184,247,0.2)',
    borderRadius: 7,
    padding: '7px 10px',
  },
  stagedName: {
    flex: 1,
    fontSize: 11,
    color: '#7EB8F7',
    fontFamily: "'DM Mono', monospace",
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  stagedSize: {
    fontSize: 10,
    color: '#4A6080',
    fontFamily: "'DM Mono', monospace",
  },
  stagedRemove: {
    cursor: 'pointer',
    color: '#4A6080',
    fontSize: 16,
    lineHeight: 1,
    padding: '0 2px',
  },
  attachTray: {
    background: 'rgba(6,12,22,0.95)',
    borderTop: '0.5px solid rgba(126,184,247,0.15)',
    padding: '10px 14px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 8,
    flexShrink: 0,
  },
  attachRow: {
    display: 'flex',
    gap: 8,
  },
  attachOpt: {
    flex: 1,
    background: 'rgba(126,184,247,0.06)',
    border: '0.5px solid rgba(126,184,247,0.18)',
    borderRadius: 8,
    padding: '10px 12px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: 9,
    transition: 'background 0.2s',
  },
  attachOptHov: {
    background: 'rgba(126,184,247,0.12)',
  },
  attachOptIcon: {
    width: 28,
    height: 28,
    borderRadius: 6,
    background: 'rgba(126,184,247,0.12)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  attachOptLabel: {
    fontSize: 12,
    fontWeight: 500,
  },
  attachOptSub: {
    fontSize: 10,
    color: '#4A6080',
    fontFamily: "'DM Mono', monospace",
    marginTop: 1,
  },
  recorderPanel: {
    background: 'rgba(6,10,18,0.98)',
    borderTop: '0.5px solid rgba(126,184,247,0.15)',
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 10,
    flexShrink: 0,
  },
  recPreview: {
    width: '100%',
    height: 140,
    background: '#050C18',
    border: '0.5px solid rgba(126,184,247,0.2)',
    borderRadius: 8,
    overflow: 'hidden',
    position: 'relative' as const,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  recPlaceholder: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    gap: 6,
  },
  recHint: {
    fontSize: 11,
    color: '#4A6080',
    fontFamily: "'DM Mono', monospace",
  },
  recTimer: {
    position: 'absolute' as const,
    top: 8,
    left: 10,
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    fontSize: 14,
    fontWeight: 500,
    color: '#E87070',
    fontFamily: "'DM Mono', monospace",
  },
  recDot: {
    display: 'inline-block',
    width: 7,
    height: 7,
    borderRadius: '50%',
    background: '#E87070',
  },
  recDoneOverlay: {
    position: 'absolute' as const,
    bottom: 8,
    left: 0,
    right: 0,
    display: 'flex',
    justifyContent: 'center',
  },
  recControls: {
    display: 'flex',
    gap: 8,
    alignItems: 'center',
  },
  recBtn: {
    flex: 1,
    padding: '8px 0',
    borderRadius: 8,
    fontSize: 12,
    fontFamily: "'DM Mono', monospace",
    cursor: 'pointer',
    textAlign: 'center' as const,
    border: 'none',
  },
  recBtnStart: {
    background: 'rgba(232,112,112,0.12)',
    border: '0.5px solid rgba(232,112,112,0.35)',
    color: '#E87070',
  },
  recBtnStop: {
    background: 'rgba(232,112,112,0.2)',
    border: '0.5px solid rgba(232,112,112,0.5)',
    color: '#F09090',
  },
  recBtnAttach: {
    background: 'rgba(126,184,247,0.12)',
    border: '0.5px solid rgba(126,184,247,0.35)',
    color: '#7EB8F7',
  },
  recBtnCancel: {
    background: 'rgba(255,255,255,0.04)',
    border: '0.5px solid rgba(255,255,255,0.12)',
    color: '#6B7A99',
  },
  compose: {
    padding: '10px 14px',
    borderTop: '0.5px solid rgba(255,255,255,0.07)',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 7,
    flexShrink: 0,
  },
  toolbar: {
    display: 'flex',
    gap: 6,
    alignItems: 'center',
  },
  toolBtn: {
    width: 30,
    height: 30,
    borderRadius: 7,
    background: 'rgba(126,184,247,0.07)',
    border: '0.5px solid rgba(126,184,247,0.18)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    flexShrink: 0,
  },
  toolBtnActive: {
    background: 'rgba(126,184,247,0.2)',
    borderColor: 'rgba(126,184,247,0.45)',
  },
  mmsBadge: {
    fontSize: 10,
    color: '#A87040',
    background: 'rgba(168,112,64,0.1)',
    border: '0.5px solid rgba(168,112,64,0.3)',
    borderRadius: 4,
    padding: '1px 6px',
    fontFamily: "'DM Mono', monospace",
  },
  charCount: {
    fontSize: 10,
    color: '#3D4E66',
    fontFamily: "'DM Mono', monospace",
  },
  composeRow: {
    display: 'flex',
    gap: 8,
    alignItems: 'flex-end',
  },
  textarea: {
    flex: 1,
    background: 'rgba(255,255,255,0.05)',
    border: '0.5px solid rgba(126,184,247,0.2)',
    borderRadius: 10,
    padding: '9px 13px',
    color: '#C8D4E8',
    fontSize: 13,
    fontFamily: "'DM Sans', sans-serif",
    resize: 'none' as const,
    outline: 'none',
    minHeight: 38,
    maxHeight: 80,
  },
  sendBtn: {
    background: 'rgba(126,184,247,0.15)',
    border: '0.5px solid rgba(126,184,247,0.35)',
    borderRadius: 8,
    padding: '8px 16px',
    color: '#7EB8F7',
    fontSize: 12,
    fontFamily: "'DM Mono', monospace",
    whiteSpace: 'nowrap' as const,
    height: 38,
  },
} as const
