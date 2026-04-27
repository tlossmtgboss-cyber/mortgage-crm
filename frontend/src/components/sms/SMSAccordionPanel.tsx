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
  useState, useRef, useEffect, useCallback, useMemo, ReactNode
} from 'react'
import { toast } from 'react-toastify'
import { getToken, getUserData } from '../../utils/tokenStore';

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
  /** Override the full API base URL (e.g. https://api.perenniaai.com). Auto-detected if omitted. */
  apiBase?: string
  /** WebSocket base URL override (e.g. wss://api.perenniaai.com). Auto-detected if omitted. */
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
      {attach.url ? (
        <video
          src={attach.url}
          controls
          playsInline
          preload="metadata"
          style={{ width: '100%', maxHeight: 180, display: 'block', background: '#000' }}
        />
      ) : (
        <div style={styles.videoThumb}>
          <div style={styles.playBtn}>
            <svg width="14" height="14" viewBox="0 0 16 16">
              <polygon points="5,3 13,8 5,13" fill="#218d8d" />
            </svg>
          </div>
        </div>
      )}
      <div style={styles.videoMeta}>
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
      <span style={{ ...styles.msgSender, color: isOut ? '#218d8d' : '#666666' }}>
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
        {msg.direction === 'outbound' && msg.status !== 'failed' && ' · Sent'}
        {msg.direction === 'outbound' && msg.status === 'failed' && ' · Failed'}
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
            <VideoIcon color="#218d8d" />
            <span style={styles.recHint}>Initializing camera…</span>
          </div>
        )}
        {error && (
          <div style={styles.recPlaceholder}>
            <span style={{ ...styles.recHint, color: '#C0152F' }}>{error}</span>
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
            <span style={{ fontSize: 12, color: '#218d8d', fontFamily: FONT_MONO }}>
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
          icon={<VideoIcon color="#C0152F" />}
          label="Record Video"
          labelColor="#C0152F"
          sub="Shoot now · MMS"
          onClick={onRecordVideo}
        />
        <AttachOption
          icon={<VideoIcon color="#218d8d" />}
          label="Upload Video"
          sub="MP4, MOV · from library"
          onClick={() => onFilePick('video')}
        />
      </div>
    </div>
  )
}

function AttachOption({
  icon, label, sub, onClick, labelColor = '#1a1a1a',
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
        <div style={{ ...styles.attachOptLabel, color: labelColor || '#1a1a1a' }}>{label}</div>
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
        <div key={f.id}>
          {/* Show video preview for staged videos */}
          {(f.type === 'video' || f.type === 'recorded-video') && f.blobUrl && (
            <div style={styles.stagedVideoPreview}>
              <video
                src={f.blobUrl}
                controls
                playsInline
                preload="metadata"
                style={{ width: '100%', maxHeight: 120, display: 'block', borderRadius: 6, background: '#000' }}
              />
            </div>
          )}
          <div style={styles.stagedFile}>
            {(f.type === 'video' || f.type === 'recorded-video')
              ? <VideoIcon color="#218d8d" size={14} />
              : <FileIcon size={14} />
            }
            <span style={styles.stagedName}>{f.name}</span>
            <span style={styles.stagedSize}>{f.sizeLabel}</span>
            <span style={styles.stagedRemove} onClick={() => onRemove(f.id)}>×</span>
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── SVG Icons ────────────────────────────────────────────────────────────────

function FileIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="#218d8d" strokeWidth="1.5">
      <rect x="3" y="1" width="10" height="14" rx="1.5" />
      <path d="M6 5h4M6 8h4M6 11h2" />
    </svg>
  )
}

function ImageIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="#218d8d" strokeWidth="1.5">
      <rect x="2" y="3" width="12" height="10" rx="1.5" />
      <circle cx="5.5" cy="6.5" r="1" />
      <path d="M2 10l3.5-3 3 3 2-2 3 2" />
    </svg>
  )
}

function VideoIcon({ color = '#218d8d', size = 16 }: { color?: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5">
      <rect x="2" y="4" width="9" height="8" rx="1.5" />
      <path d="M11 6.5l3-2v7l-3-2" />
    </svg>
  )
}

function AttachIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#218d8d" strokeWidth="1.5">
      <path d="M13 7.5l-5.5 5.5a3.5 3.5 0 01-4.95-4.95l5.5-5.5a2 2 0 012.83 2.83L5.38 10.9a.5.5 0 01-.7-.7l4.24-4.25" />
    </svg>
  )
}

function ChevronIcon({ up }: { up: boolean }) {
  return (
    <svg
      width="16" height="16" viewBox="0 0 16 16" fill="none"
      stroke="#999999" strokeWidth="1.5"
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
  apiBase,
  wsUrl,
  onToggle,
}: SMSAccordionPanelProps) {
  // ── API base: always route to the backend API domain ──
  const resolvedApiBase = apiBase || (() => {
    const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    return isLocalhost
      ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
      : 'https://api.perenniaai.com'
  })()

  // ── Resolve sender display name: prefer assignedUser if it's a real name,
  //    otherwise fall back to current user's name from token store ──
  const senderDisplayName = useMemo(() => {
    if (assignedUser && !/^\d+$/.test(String(assignedUser))) return assignedUser
    const userData = getUserData()
    if (userData) {
      const full = userData.full_name || `${userData.first_name || ''} ${userData.last_name || ''}`.trim()
      if (full) return full
      if (userData.email) return userData.email
    }
    return 'You'
  }, [assignedUser])

  // ── Auth helper: read JWT from localStorage (same pattern as rest of app) ──
  function getAuthHeaders(): Record<string, string> {
    const token = getToken()
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    return headers
  }

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

  // TCPA consent state
  const [tcpaStatus, setTcpaStatus] = useState<{
    has_active_consent: boolean
    sms_permitted: boolean
    consent_type?: string | null
    message: string
  } | null>(null)
  const [tcpaLoading, setTcpaLoading] = useState(false)
  const smsBlocked = tcpaStatus !== null && !tcpaStatus.sms_permitted

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

  // Check TCPA consent when panel opens or phone changes
  useEffect(() => {
    if (!open || !activePhone) return
    let cancelled = false
    async function checkTcpa() {
      setTcpaLoading(true)
      setTcpaStatus(null)
      try {
        const res = await fetch(
          `${resolvedApiBase}/api/v1/compliance/tcpa/consent/${encodeURIComponent(activePhone)}`,
          { headers: getAuthHeaders() }
        )
        if (cancelled) return
        if (res.ok) {
          const data = await res.json()
          setTcpaStatus(data)
        } else {
          setTcpaStatus({
            has_active_consent: false,
            sms_permitted: false,
            message: 'Unable to verify TCPA consent status.',
          })
        }
      } catch {
        if (!cancelled) {
          setTcpaStatus({
            has_active_consent: false,
            sms_permitted: false,
            message: 'Unable to verify TCPA consent status.',
          })
        }
      } finally {
        if (!cancelled) setTcpaLoading(false)
      }
    }
    checkTcpa()
    return () => { cancelled = true }
  }, [open, activePhone])

  // Fetch history when panel opens or phone changes
  useEffect(() => {
    if (!open || !activePhone) return
    fetchHistory()
    scrollToBottom()
    setUnreadCount(0)
    connectWS()
    return () => wsRef.current?.close()
  }, [open, activePhone])

  async function fetchHistory() {
    if (!activePhone) return
    try {
      const phoneParam = encodeURIComponent(activePhone)
      const res = await fetch(`${resolvedApiBase}/api/v1/sms/conversations/${phoneParam}`, {
        headers: getAuthHeaders(),
      })
      if (!res.ok) {
        console.warn(`[SMS] History fetch failed: ${res.status} ${res.statusText}`)
        return
      }
      const data: SmsMessage[] = await res.json()
      setMessages(data)
    } catch (e) {
      console.error('[SMS] Failed to fetch history', e)
    }
  }

  function connectWS() {
    // Build WS URL pointing to the API domain (not frontend domain)
    const phoneParam = encodeURIComponent(activePhone)
    const token = getToken() || ''
    const apiWsBase = wsUrl || (() => {
      const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
      return isLocalhost ? 'ws://localhost:8000' : 'wss://api.perenniaai.com'
    })()
    const ws = new WebSocket(`${apiWsBase}/ws/sms/${phoneParam}?token=${encodeURIComponent(token)}`)

    ws.onmessage = e => {
      try {
        const data = JSON.parse(e.data)

        // Handle status updates (delivered, failed) for existing messages
        if (data.type === 'status_update' && data.messageId) {
          setMessages(prev =>
            prev.map(m =>
              (m.id === data.messageId) ? { ...m, status: data.status } : m
            )
          )
          return
        }

        // Handle new messages (inbound or outbound from another tab)
        if (data.type === 'new_message' || data.direction) {
          const msg: SmsMessage = {
            id: data.id,
            direction: data.direction,
            body: data.body,
            senderName: data.senderName || (data.direction === 'inbound' ? 'Customer' : 'System'),
            senderRole: data.senderRole,
            timestamp: data.timestamp,
            status: data.status || 'delivered',
            mediaUrls: data.mediaUrls || [],
          }
          setMessages(prev => {
            // Avoid duplicates (may already exist from optimistic update)
            if (prev.some(m => m.id === msg.id)) return prev
            return [...prev, msg]
          })
          if (data.direction === 'inbound') {
            scrollToBottom()
            if (!open) setUnreadCount(c => c + 1)
          }
        }
      } catch {
        // ignore parse errors
      }
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
    if (smsBlocked) return
    setSending(true)

    // Optimistic UI
    const optimisticId = uniqId()
    const now = new Date().toISOString()
    const optimistic: SmsMessage = {
      id: optimisticId,
      direction: 'outbound',
      body: text.trim(),
      senderName: senderDisplayName,
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
      const token = getToken()
      for (const sf of staged) {
        if (sf.file) {
          const form = new FormData()
          form.append('file', sf.file)
          form.append('contactId', contactId)
          const uploadHeaders: Record<string, string> = {}
          if (token) uploadHeaders['Authorization'] = `Bearer ${token}`
          const res = await fetch(`${resolvedApiBase}/api/v1/sms/upload-media`, {
            method: 'POST',
            headers: uploadHeaders,
            body: form,
          })
          if (res.ok) {
            const { url } = await res.json()
            mediaUrls.push(url)
          }
        }
      }

      // Send via FastAPI → Telnyx endpoint
      const res = await fetch(`${resolvedApiBase}/api/v1/sms/send`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          contactId,
          to: activePhone,
          message: text.trim(),
          mediaUrls,
          pageType,
          borrowerType: activeBorrower?.type || 'primary',
        }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
        const detail = Array.isArray(err.detail)
          ? err.detail.map((e: any) => e.msg || e.message || JSON.stringify(e)).join('; ')
          : (err.detail || err.error || 'Send failed')
        throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
      }

      // Update optimistic → delivered, and use server-assigned id + senderName
      const serverMsg = await res.json().catch(() => ({}))
      setMessages(prev =>
        prev.map(m => m.id === optimisticId ? {
          ...m,
          id: serverMsg.id || m.id,
          status: serverMsg.status || 'sent',
          senderName: serverMsg.senderName || m.senderName,
        } : m)
      )
    } catch (err: any) {
      const msg = err?.message || 'Send failed'
      toast.error(`SMS failed: ${msg}`)
      console.error('[SMS] Send error:', msg)
      setMessages(prev =>
        prev.map(m => m.id === optimisticId ? { ...m, status: 'failed' } : m)
      )
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !smsBlocked) {
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
        transform: open ? 'translateY(0)' : `translateY(calc(100% - 44px))`,
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
              To: <span style={{ color: '#218d8d' }}>{activePhone}</span> · {activeName}
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

          {/* TCPA Consent Status */}
          {tcpaLoading && (
            <div style={{
              padding: '8px 12px',
              background: '#f3f4f6',
              borderTop: '1px solid #e5e7eb',
              fontSize: 12,
              color: '#6b7280',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}>
              Checking TCPA consent...
            </div>
          )}
          {!tcpaLoading && smsBlocked && (
            <div style={{
              padding: '10px 12px',
              background: '#fef2f2',
              borderTop: '1px solid #fca5a5',
              fontSize: 12,
              color: '#991b1b',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontWeight: 600,
            }}>
              <span style={{ fontSize: 16 }}>{'\u26D4'}</span>
              <span>SMS Blocked -- No TCPA consent on file. {tcpaStatus?.message || ''}</span>
            </div>
          )}
          {!tcpaLoading && tcpaStatus && tcpaStatus.sms_permitted && (
            <div style={{
              padding: '6px 12px',
              background: '#f0fdf4',
              borderTop: '1px solid #86efac',
              fontSize: 11,
              color: '#166534',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}>
              <span>{'\u2705'}</span>
              <span>TCPA consent active</span>
            </div>
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
                <VideoIcon color={tray === 'recorder' ? '#C0152F' : '#218d8d'} size={14} />
              </button>
              <div style={{ flex: 1 }} />
              {isMMS && <span style={styles.mmsBadge}>MMS</span>}
              <span style={styles.charCount}>{charCount} / 160</span>
            </div>

            <div style={styles.composeRow}>
              <textarea
                ref={textareaRef}
                style={{
                  ...styles.textarea,
                  ...(smsBlocked ? { opacity: 0.5, cursor: 'not-allowed' } : {}),
                }}
                placeholder={smsBlocked ? 'SMS blocked -- no TCPA consent on file' : `Reply to ${activeName}…`}
                value={text}
                rows={1}
                onChange={e => {
                  if (!smsBlocked) {
                    setText(e.target.value)
                    autoResize(e.target)
                  }
                }}
                onKeyDown={handleKeyDown}
                disabled={smsBlocked}
              />
              <button
                style={{
                  ...styles.sendBtn,
                  opacity: (sending || smsBlocked) ? 0.6 : 1,
                  cursor: (sending || smsBlocked) ? 'not-allowed' : 'pointer',
                  ...(smsBlocked ? { background: '#dc2626' } : {}),
                }}
                onClick={sendMessage}
                disabled={sending || smsBlocked || tcpaLoading}
                title={smsBlocked ? 'SMS blocked -- no TCPA consent on file' : ''}
              >
                {sending ? 'Sending…' : smsBlocked ? '\u26D4 Blocked' : 'Send'}
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
// Uses the site's CSS custom properties from index.css for theme consistency.
// Teal primary (#218d8d), warm borders, light surface, system font stack.

const TEAL = '#218d8d'
const TEAL_HOVER = '#1a6670'
const BORDER = 'rgba(139,92,68,0.15)'
const BORDER_LIGHT = 'rgba(139,92,68,0.08)'
const TEXT_PRI = '#1a1a1a'
const TEXT_SEC = '#666666'
const TEXT_TER = '#999999'
const BG_BASE = '#FCFCF9'
const BG_SURFACE = '#FFFFFF'
const BG_HOVER = 'rgba(139,92,68,0.08)'
const FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Inter', sans-serif"
const FONT_MONO = "'Berkeley Mono', 'Courier New', monospace"

const styles = {
  panel: {
    position: 'fixed' as const,
    bottom: 0,
    right: 16,
    width: 500,
    transition: 'transform 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
    zIndex: 100,
    fontFamily: FONT,
  },
  handle: {
    background: BG_SURFACE,
    backdropFilter: 'blur(12px)',
    borderTop: `1px solid ${BORDER}`,
    borderLeft: `0.5px solid ${BORDER_LIGHT}`,
    borderRight: `0.5px solid ${BORDER_LIGHT}`,
    borderRadius: '6px 6px 0 0',
    padding: '0 16px',
    cursor: 'pointer',
    height: 44,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    boxShadow: '0 -1px 4px rgba(0,0,0,0.04)',
  },
  handleLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
  },
  smsDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: TEAL,
    flexShrink: 0,
  },
  handleTitle: {
    fontSize: 16,
    fontWeight: 600,
    color: TEXT_PRI,
  },
  handleSub: {
    fontSize: 15,
    color: TEXT_TER,
    fontWeight: 400,
  },
  unreadBadge: {
    background: 'rgba(33,141,141,0.1)',
    border: `0.5px solid rgba(33,141,141,0.35)`,
    borderRadius: 20,
    padding: '2px 9px',
    fontSize: 13,
    color: TEAL,
    fontFamily: FONT_MONO,
  },
  body: {
    background: BG_BASE,
    height: 'calc(100vh - 640px)',
    minHeight: 200,
    display: 'flex',
    flexDirection: 'column' as const,
    borderLeft: `0.5px solid ${BORDER_LIGHT}`,
    borderRight: `0.5px solid ${BORDER_LIGHT}`,
  },
  borrowerSelector: {
    padding: '3px 12px',
    borderBottom: `0.5px solid ${BORDER_LIGHT}`,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    flexShrink: 0,
  },
  borrowerLabel: {
    fontSize: 15,
    color: TEXT_TER,
    fontFamily: FONT_MONO,
    whiteSpace: 'nowrap' as const,
  },
  borrowerPills: {
    display: 'flex',
    gap: 6,
    flex: 1,
    overflow: 'auto' as const,
  },
  borrowerPill: {
    background: 'rgba(33,141,141,0.05)',
    border: `0.5px solid ${BORDER}`,
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
    background: 'rgba(33,141,141,0.12)',
    borderColor: TEAL,
  },
  borrowerPillName: {
    fontSize: 15,
    fontWeight: 500,
    color: TEXT_PRI,
    whiteSpace: 'nowrap' as const,
  },
  borrowerPillType: {
    fontSize: 13,
    color: TEXT_TER,
    fontFamily: FONT_MONO,
  },
  topBar: {
    padding: '6px 14px',
    borderBottom: `0.5px solid ${BORDER_LIGHT}`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexShrink: 0,
  },
  topContact: {
    fontSize: 15,
    color: TEXT_SEC,
    fontFamily: FONT_MONO,
  },
  topActions: {
    display: 'flex',
    gap: 8,
  },
  iconBtn: {
    background: 'rgba(33,141,141,0.06)',
    border: `0.5px solid ${BORDER}`,
    borderRadius: 6,
    padding: '5px 12px',
    fontSize: 14,
    color: TEAL,
    cursor: 'pointer',
    fontFamily: FONT_MONO,
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
    fontSize: 16,
    color: TEXT_TER,
    fontFamily: FONT_MONO,
    marginTop: 40,
  },
  dateDivider: {
    textAlign: 'center' as const,
    fontSize: 13,
    color: TEXT_TER,
    fontFamily: FONT_MONO,
    padding: '4px 0',
    position: 'relative' as const,
    borderTop: `0.5px solid ${BORDER_LIGHT}`,
  },
  dateDividerSpan: {
    background: BG_BASE,
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
    fontSize: 14,
    fontFamily: FONT_MONO,
    fontWeight: 500,
  },
  msgBubble: {
    maxWidth: '80%',
    padding: '10px 14px',
    borderRadius: 12,
    fontSize: 16,
    lineHeight: 1.5,
  },
  msgBubbleIn: {
    background: BG_SURFACE,
    border: `0.5px solid ${BORDER}`,
    color: TEXT_PRI,
    borderBottomLeftRadius: 3,
  },
  msgBubbleOut: {
    background: 'rgba(33,141,141,0.08)',
    border: '0.5px solid rgba(33,141,141,0.25)',
    color: TEXT_PRI,
    borderBottomRightRadius: 3,
  },
  msgBubbleUnread: {
    borderColor: TEAL,
  },
  msgMeta: {
    fontSize: 12,
    color: TEXT_TER,
    fontFamily: FONT_MONO,
    padding: '0 4px',
  },
  docBubble: {
    maxWidth: '72%',
    padding: '10px 13px',
    borderRadius: 12,
    borderBottomRightRadius: 3,
    background: 'rgba(33,141,141,0.05)',
    border: `0.5px solid ${BORDER}`,
    display: 'flex',
    alignItems: 'center',
    gap: 10,
  },
  docIcon: {
    width: 32,
    height: 32,
    borderRadius: 6,
    background: 'rgba(33,141,141,0.1)',
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
    fontSize: 13,
    color: TEXT_PRI,
    fontFamily: FONT_MONO,
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  docSize: {
    fontSize: 11,
    color: TEXT_TER,
    fontFamily: FONT_MONO,
    marginTop: 2,
  },
  videoBubble: {
    maxWidth: '72%',
    borderRadius: 12,
    borderBottomRightRadius: 3,
    overflow: 'hidden',
    border: `0.5px solid ${BORDER}`,
  },
  videoThumb: {
    width: '100%',
    height: 100,
    background: '#f0efec',
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
    background: 'rgba(33,141,141,0.15)',
    border: `1.5px solid ${TEAL}`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  videoMeta: {
    padding: '4px 10px 6px',
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    background: BG_SURFACE,
  },
  videoLabel: {
    fontSize: 10,
    color: TEXT_SEC,
    fontFamily: FONT_MONO,
  },
  videoDuration: {
    fontSize: 10,
    color: TEAL,
    fontFamily: FONT_MONO,
  },
  stagedArea: {
    padding: '6px 14px',
    borderTop: `0.5px solid ${BORDER_LIGHT}`,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 5,
    flexShrink: 0,
    maxHeight: 160,
    overflowY: 'auto' as const,
  },
  stagedVideoPreview: {
    marginBottom: 4,
    borderRadius: 6,
    overflow: 'hidden',
    border: `0.5px solid ${BORDER}`,
  },
  stagedFile: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    background: 'rgba(33,141,141,0.04)',
    border: `0.5px solid ${BORDER}`,
    borderRadius: 7,
    padding: '7px 10px',
  },
  stagedName: {
    flex: 1,
    fontSize: 11,
    color: TEAL,
    fontFamily: FONT_MONO,
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  stagedSize: {
    fontSize: 10,
    color: TEXT_TER,
    fontFamily: FONT_MONO,
  },
  stagedRemove: {
    cursor: 'pointer',
    color: TEXT_TER,
    fontSize: 16,
    lineHeight: 1,
    padding: '0 2px',
  },
  attachTray: {
    background: BG_SURFACE,
    borderTop: `0.5px solid ${BORDER}`,
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
    background: 'rgba(33,141,141,0.04)',
    border: `0.5px solid ${BORDER}`,
    borderRadius: 8,
    padding: '10px 12px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: 9,
    transition: 'background 0.2s',
  },
  attachOptHov: {
    background: BG_HOVER,
  },
  attachOptIcon: {
    width: 28,
    height: 28,
    borderRadius: 6,
    background: 'rgba(33,141,141,0.08)',
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
    color: TEXT_TER,
    fontFamily: FONT_MONO,
    marginTop: 1,
  },
  recorderPanel: {
    background: BG_SURFACE,
    borderTop: `0.5px solid ${BORDER}`,
    padding: '8px 14px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 6,
    flex: 1,
    minHeight: 0,
  },
  recPreview: {
    width: '100%',
    flex: 1,
    minHeight: 80,
    background: '#f0efec',
    border: `0.5px solid ${BORDER}`,
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
    color: TEXT_TER,
    fontFamily: FONT_MONO,
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
    color: '#C0152F',
    fontFamily: FONT_MONO,
  },
  recDot: {
    display: 'inline-block',
    width: 7,
    height: 7,
    borderRadius: '50%',
    background: '#C0152F',
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
    padding: '6px 0',
    borderRadius: 6,
    fontSize: 11,
    fontFamily: FONT_MONO,
    cursor: 'pointer',
    textAlign: 'center' as const,
    border: 'none',
  },
  recBtnStart: {
    background: 'rgba(192,21,47,0.08)',
    border: '0.5px solid rgba(192,21,47,0.3)',
    color: '#C0152F',
  },
  recBtnStop: {
    background: 'rgba(192,21,47,0.12)',
    border: '0.5px solid rgba(192,21,47,0.4)',
    color: '#C0152F',
  },
  recBtnAttach: {
    background: 'rgba(33,141,141,0.08)',
    border: `0.5px solid rgba(33,141,141,0.3)`,
    color: TEAL,
  },
  recBtnCancel: {
    background: 'rgba(139,92,68,0.05)',
    border: `0.5px solid ${BORDER}`,
    color: TEXT_SEC,
  },
  compose: {
    padding: '6px 14px 8px',
    borderTop: `0.5px solid ${BORDER_LIGHT}`,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 4,
    flexShrink: 0,
  },
  toolbar: {
    display: 'flex',
    gap: 6,
    alignItems: 'center',
  },
  toolBtn: {
    width: 28,
    height: 28,
    borderRadius: 6,
    background: 'rgba(33,141,141,0.06)',
    border: `0.5px solid ${BORDER}`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    flexShrink: 0,
  },
  toolBtnActive: {
    background: 'rgba(33,141,141,0.15)',
    borderColor: TEAL,
  },
  mmsBadge: {
    fontSize: 10,
    color: '#A84B2F',
    background: 'rgba(168,75,47,0.08)',
    border: '0.5px solid rgba(168,75,47,0.25)',
    borderRadius: 4,
    padding: '1px 6px',
    fontFamily: FONT_MONO,
  },
  charCount: {
    fontSize: 10,
    color: TEXT_TER,
    fontFamily: FONT_MONO,
  },
  composeRow: {
    display: 'flex',
    gap: 8,
    alignItems: 'flex-end',
  },
  textarea: {
    flex: 1,
    background: BG_SURFACE,
    border: `0.5px solid ${BORDER}`,
    borderRadius: 10,
    padding: '8px 12px',
    color: TEXT_PRI,
    fontSize: 16,
    fontFamily: FONT,
    resize: 'none' as const,
    outline: 'none',
    minHeight: 40,
    maxHeight: 80,
  },
  sendBtn: {
    background: TEAL,
    border: 'none',
    borderRadius: 8,
    padding: '8px 18px',
    color: '#FFFFFF',
    fontSize: 15,
    fontFamily: FONT_MONO,
    whiteSpace: 'nowrap' as const,
    height: 40,
  },
} as const
