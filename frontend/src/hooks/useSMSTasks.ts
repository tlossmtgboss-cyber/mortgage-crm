import { useState, useEffect, useCallback, useRef } from 'react'

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000'
  : 'https://api.perenniaai.com'

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('token') || ''
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  }
}

export interface SMSTask {
  id: number
  organization_id: number
  assigned_user_id: number | null
  lead_id: number | null
  phone_number: string
  contact_name: string | null
  inbound_message: string
  inbound_received_at: string
  status: 'pending' | 'in_progress' | 'completed' | 'auto_responded' | 'dismissed' | 'expired'
  priority: 'low' | 'normal' | 'high' | 'urgent'
  category: string | null
  ai_recommendation: string | null
  ai_confidence: number
  ai_reasoning: string | null
  response_text: string | null
  response_source: string | null
  response_sent_at: string | null
  user_feedback: string | null
  created_at: string
  updated_at: string
  lead_name?: string
  lead_email?: string
  lead_stage?: string
}

export interface SMSTaskStats {
  counts: {
    pending: number
    in_progress: number
    completed_today: number
    auto_responded_today: number
    dismissed_today: number
  }
  confidence: Array<{
    category: string
    confidence_score: number
    auto_respond_enabled: boolean
    total_recommendations: number
  }>
}

interface AutoRespondSetting {
  category: string
  enabled: boolean
  threshold: number
}

interface UseSMSTasksOptions {
  status?: string
  category?: string
  mine?: boolean
  pollInterval?: number
}

export function useSMSTasks(options: UseSMSTasksOptions = {}) {
  const { status, category, mine, pollInterval = 30000 } = options
  const [tasks, setTasks] = useState<SMSTask[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hasNewTasks, setHasNewTasks] = useState(false)
  const previousCountRef = useRef<number | null>(null)
  const mountedRef = useRef(true)

  const fetchTasks = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (status) params.set('status', status)
      if (category) params.set('category', category)
      if (mine) params.set('mine', 'true')
      const qs = params.toString()
      const url = `${API_BASE}/api/v1/sms-tasks${qs ? `?${qs}` : ''}`
      const res = await fetch(url, { headers: getAuthHeaders() })
      if (!res.ok) throw new Error(`Failed to fetch SMS tasks: ${res.status}`)
      const data = await res.json()
      if (!mountedRef.current) return
      const newTasks = data.tasks ?? data.items ?? []
      const newTotal = data.total ?? newTasks.length
      if (previousCountRef.current !== null && newTotal > previousCountRef.current) {
        setHasNewTasks(true)
      }
      previousCountRef.current = newTotal
      setTasks(newTasks)
      setTotal(newTotal)
      setError(null)
    } catch (err: any) {
      if (!mountedRef.current) return
      setError(err.message ?? String(err))
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [status, category, mine])

  useEffect(() => {
    mountedRef.current = true
    setLoading(true)
    fetchTasks()
    const interval = setInterval(fetchTasks, pollInterval)
    return () => {
      mountedRef.current = false
      clearInterval(interval)
    }
  }, [fetchTasks, pollInterval])

  const refetch = useCallback(() => {
    setHasNewTasks(false)
    return fetchTasks()
  }, [fetchTasks])

  return { tasks, total, loading, error, hasNewTasks, refetch }
}

export function useSMSTask(taskId: string | null) {
  const [task, setTask] = useState<SMSTask | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const mountedRef = useRef(true)

  const fetchTask = useCallback(async () => {
    if (!taskId) return
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/v1/sms-tasks/${taskId}`, { headers: getAuthHeaders() })
      if (!res.ok) throw new Error(`Failed to fetch SMS task: ${res.status}`)
      const data = await res.json()
      if (!mountedRef.current) return
      setTask(data)
      setError(null)
    } catch (err: any) {
      if (!mountedRef.current) return
      setError(err.message ?? String(err))
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [taskId])

  useEffect(() => {
    mountedRef.current = true
    if (taskId) {
      setTask(null)
      fetchTask()
    } else {
      setTask(null)
      setLoading(false)
      setError(null)
    }
    return () => { mountedRef.current = false }
  }, [fetchTask, taskId])

  return { task, loading, error, refetch: fetchTask }
}

export function useSMSTaskActions() {
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({})

  const execute = useCallback(async (action: string, taskId: string, body: Record<string, any> = {}) => {
    setActionLoading(prev => ({ ...prev, [action]: true }))
    try {
      const res = await fetch(`${API_BASE}/api/v1/sms-tasks/${taskId}/${action}`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || `Action ${action} failed: ${res.status}`)
      }
      return await res.json()
    } finally {
      setActionLoading(prev => ({ ...prev, [action]: false }))
    }
  }, [])

  const respond = useCallback(
    (taskId: string, responseText: string, responseSource: string) =>
      execute('respond', taskId, { response_text: responseText, response_source: responseSource }),
    [execute]
  )

  const dismiss = useCallback(
    (taskId: string) => execute('dismiss', taskId),
    [execute]
  )

  const regenerate = useCallback(
    (taskId: string, feedback?: string) =>
      execute('regenerate', taskId, feedback ? { feedback } : {}),
    [execute]
  )

  const sendFeedback = useCallback(
    (taskId: string, rating: string) =>
      execute('feedback', taskId, { rating }),
    [execute]
  )

  return {
    respond,
    dismiss,
    regenerate,
    sendFeedback,
    loading: actionLoading,
  }
}

export function useSMSTaskStats() {
  const [stats, setStats] = useState<SMSTaskStats | null>(null)
  const [loading, setLoading] = useState(true)
  const mountedRef = useRef(true)

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/sms-tasks/stats`, { headers: getAuthHeaders() })
      if (!res.ok) throw new Error(`Failed to fetch stats: ${res.status}`)
      const data = await res.json()
      if (!mountedRef.current) return
      setStats(data)
    } catch (err: any) {
      if (!mountedRef.current) return
      console.error('SMS task stats fetch error:', err)
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    fetchStats()
    const interval = setInterval(fetchStats, 60000)
    return () => {
      mountedRef.current = false
      clearInterval(interval)
    }
  }, [fetchStats])

  return { stats, loading, refetch: fetchStats }
}

export function useAutoRespondSettings() {
  const [settings, setSettings] = useState<AutoRespondSetting[]>([])
  const [loading, setLoading] = useState(true)
  const mountedRef = useRef(true)

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/sms-tasks/settings`, { headers: getAuthHeaders() })
      if (!res.ok) throw new Error(`Failed to fetch settings: ${res.status}`)
      const data = await res.json()
      if (!mountedRef.current) return
      setSettings(data.settings ?? data)
    } catch (err: any) {
      if (!mountedRef.current) return
      console.error('Auto-respond settings fetch error:', err)
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    fetchSettings()
    return () => { mountedRef.current = false }
  }, [fetchSettings])

  const updateSetting = useCallback(async (category: string, enabled: boolean, threshold: number) => {
    const res = await fetch(`${API_BASE}/api/v1/sms-tasks/settings`, {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: JSON.stringify({ category, enabled, threshold }),
    })
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      throw new Error(errData.detail || `Failed to update setting: ${res.status}`)
    }
    const data = await res.json()
    await fetchSettings()
    return data
  }, [fetchSettings])

  return { settings, loading, updateSetting }
}
