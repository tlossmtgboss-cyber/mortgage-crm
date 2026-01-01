/**
 * Recruiting Workflow CRM API Service
 * Multi-year relationship development for Loan Officers and Realtors
 */

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    'Authorization': token ? `Bearer ${token}` : ''
  };
};

// =============================================================================
// PERSON ENDPOINTS
// =============================================================================

export const createPerson = async (data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/people`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to create person');
  return response.json();
};

export const getPeople = async (params = {}) => {
  const searchParams = new URLSearchParams();
  if (params.person_type) searchParams.append('person_type', params.person_type);
  if (params.relationship_stage) searchParams.append('relationship_stage', params.relationship_stage);
  if (params.owner_user_id) searchParams.append('owner_user_id', params.owner_user_id);
  if (params.min_timing_score) searchParams.append('min_timing_score', params.min_timing_score);
  if (params.search) searchParams.append('search', params.search);
  if (params.limit) searchParams.append('limit', params.limit);
  if (params.offset) searchParams.append('offset', params.offset);
  if (params.order_by) searchParams.append('order_by', params.order_by);

  const url = `${API_URL}/api/v1/recruiting-crm/people?${searchParams}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch people');
  return response.json();
};

export const getHotLeads = async (params = {}) => {
  const searchParams = new URLSearchParams();
  if (params.person_type) searchParams.append('person_type', params.person_type);
  if (params.limit) searchParams.append('limit', params.limit);

  const url = `${API_URL}/api/v1/recruiting-crm/people/hot-leads?${searchParams}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch hot leads');
  return response.json();
};

export const getPerson = async (personId) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/people/${personId}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch person');
  return response.json();
};

export const getPersonSummary = async (personId) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/people/${personId}/summary`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch person summary');
  return response.json();
};

export const updatePerson = async (personId, data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/people/${personId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to update person');
  return response.json();
};

// =============================================================================
// TIMING INTELLIGENCE ENDPOINTS
// =============================================================================

export const getTimingIntelligence = async (personId) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/people/${personId}/timing`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch timing intelligence');
  return response.json();
};

export const getNextBestAction = async (personId) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/people/${personId}/next-best-action`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch next best action');
  return response.json();
};

export const getBestContactTime = async (personId) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/people/${personId}/best-contact-time`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch best contact time');
  return response.json();
};

// =============================================================================
// SIGNAL ENDPOINTS
// =============================================================================

export const createSignal = async (data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/signals`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to create signal');
  return response.json();
};

export const decayTimingScores = async () => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/timing/decay`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to decay timing scores');
  return response.json();
};

// =============================================================================
// CONNECTION ENDPOINTS
// =============================================================================

export const createConnection = async (data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/connections`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to create connection');
  return response.json();
};

export const getTopConnections = async (personId, limit = 10) => {
  const url = `${API_URL}/api/v1/recruiting-crm/people/${personId}/connections?limit=${limit}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch connections');
  return response.json();
};

export const findMutualConnections = async (personAId, personBId) => {
  const url = `${API_URL}/api/v1/recruiting-crm/connections/mutual?person_a_id=${personAId}&person_b_id=${personBId}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to find mutual connections');
  return response.json();
};

// =============================================================================
// OBJECTION ENDPOINTS
// =============================================================================

export const createObjection = async (data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/objections`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to create objection');
  return response.json();
};

export const getObjections = async (personId, status = null) => {
  let url = `${API_URL}/api/v1/recruiting-crm/people/${personId}/objections`;
  if (status) url += `?status=${status}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch objections');
  return response.json();
};

export const updateObjection = async (objectionId, data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/objections/${objectionId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to update objection');
  return response.json();
};

export const getObjectionsDueForRevisit = async (limit = 50) => {
  const url = `${API_URL}/api/v1/recruiting-crm/objections/due-revisit?limit=${limit}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch objections due');
  return response.json();
};

// =============================================================================
// CADENCE ENDPOINTS
// =============================================================================

export const enrollInCadence = async (data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/cadence-enrollments`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to enroll in cadence');
  return response.json();
};

export const getCadencesDue = async (limit = 100) => {
  const url = `${API_URL}/api/v1/recruiting-crm/cadences/due?limit=${limit}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch cadences due');
  return response.json();
};

export const advanceCadenceStep = async (enrollmentId) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/cadence-enrollments/${enrollmentId}/advance`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to advance cadence step');
  return response.json();
};

export const pauseCadence = async (enrollmentId, reason = null, pauseUntil = null) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/cadence-enrollments/${enrollmentId}/pause`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ reason, pause_until: pauseUntil })
  });
  if (!response.ok) throw new Error('Failed to pause cadence');
  return response.json();
};

// =============================================================================
// PLAYBOOK ENDPOINTS
// =============================================================================

export const getPlaybookRuns = async (params = {}) => {
  const searchParams = new URLSearchParams();
  if (params.person_id) searchParams.append('person_id', params.person_id);
  if (params.status) searchParams.append('status', params.status);
  if (params.limit) searchParams.append('limit', params.limit);

  const url = `${API_URL}/api/v1/recruiting-crm/playbook-runs?${searchParams}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch playbook runs');
  return response.json();
};

// =============================================================================
// TASK ENDPOINTS
// =============================================================================

export const createTask = async (data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/tasks`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to create task');
  return response.json();
};

export const getTasks = async (params = {}) => {
  const searchParams = new URLSearchParams();
  if (params.person_id) searchParams.append('person_id', params.person_id);
  if (params.assigned_to) searchParams.append('assigned_to', params.assigned_to);
  if (params.status) searchParams.append('status', params.status);
  if (params.overdue_only) searchParams.append('overdue_only', params.overdue_only);
  if (params.limit) searchParams.append('limit', params.limit);

  const url = `${API_URL}/api/v1/recruiting-crm/tasks?${searchParams}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch tasks');
  return response.json();
};

export const completeTask = async (taskId, outcome = null, outcomeNotes = null) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/tasks/${taskId}/complete`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ outcome, outcome_notes: outcomeNotes })
  });
  if (!response.ok) throw new Error('Failed to complete task');
  return response.json();
};

// =============================================================================
// NOTE ENDPOINTS
// =============================================================================

export const createNote = async (data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/notes`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to create note');
  return response.json();
};

export const getNotes = async (personId, noteType = null, limit = 50) => {
  let url = `${API_URL}/api/v1/recruiting-crm/people/${personId}/notes?limit=${limit}`;
  if (noteType) url += `&note_type=${noteType}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch notes');
  return response.json();
};

// =============================================================================
// COMMUNICATION OUTCOME ENDPOINTS
// =============================================================================

export const recordCommOutcome = async (data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/comm-outcomes`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to record communication outcome');
  return response.json();
};

export const updateCommOutcome = async (outcomeId, data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/comm-outcomes/${outcomeId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to update communication outcome');
  return response.json();
};

// =============================================================================
// EVENT ENDPOINTS
// =============================================================================

export const getEvents = async (params = {}) => {
  const searchParams = new URLSearchParams();
  if (params.person_id) searchParams.append('person_id', params.person_id);
  if (params.event_type) searchParams.append('event_type', params.event_type);
  if (params.limit) searchParams.append('limit', params.limit);

  const url = `${API_URL}/api/v1/recruiting-crm/events?${searchParams}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch events');
  return response.json();
};

// =============================================================================
// STATISTICS ENDPOINTS
// =============================================================================

export const getWorkflowStats = async () => {
  const response = await fetch(`${API_URL}/api/v1/recruiting-crm/stats`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch workflow stats');
  return response.json();
};

// =============================================================================
// BATCH OPERATIONS
// =============================================================================

export const loadDashboardData = async () => {
  const [stats, hotLeads, tasksDue, cadencesDue, objectionsDue] = await Promise.all([
    getWorkflowStats(),
    getHotLeads({ limit: 10 }),
    getTasks({ overdue_only: true, limit: 10 }),
    getCadencesDue(10),
    getObjectionsDueForRevisit(10)
  ]);
  return { stats, hotLeads, tasksDue, cadencesDue, objectionsDue };
};

// =============================================================================
// CONSTANTS
// =============================================================================

export const PERSON_TYPES = [
  { value: 'LOAN_OFFICER', label: 'Loan Officer', icon: '🏦' },
  { value: 'REALTOR', label: 'Realtor', icon: '🏠' }
];

export const RELATIONSHIP_STAGES = [
  { value: 'DISCOVERED', label: 'Discovered', color: '#9ca3af', icon: '🔍' },
  { value: 'CONNECTED', label: 'Connected', color: '#60a5fa', icon: '🔗' },
  { value: 'NURTURING', label: 'Nurturing', color: '#818cf8', icon: '🌱' },
  { value: 'WARMING', label: 'Warming', color: '#fbbf24', icon: '🌡️' },
  { value: 'ACTIVE_CONVERSATION', label: 'Active Conversation', color: '#fb923c', icon: '💬' },
  { value: 'EVALUATING_SWITCH', label: 'Evaluating Switch', color: '#f87171', icon: '🤔' },
  { value: 'COMMITTED', label: 'Committed', color: '#34d399', icon: '✅' },
  { value: 'ONBOARDING', label: 'Onboarding', color: '#22d3ee', icon: '🚀' },
  { value: 'ACTIVE_PARTNER', label: 'Active Partner', color: '#10b981', icon: '🤝' },
  { value: 'DORMANT', label: 'Dormant', color: '#6b7280', icon: '💤' },
  { value: 'DO_NOT_CONTACT', label: 'Do Not Contact', color: '#ef4444', icon: '🚫' }
];

export const SIGNAL_TYPES = [
  { value: 'MEETING_INTENT', label: 'Meeting Intent', weight: 35 },
  { value: 'BRANCH_INSTABILITY', label: 'Branch Instability', weight: 25 },
  { value: 'OPS_PAIN', label: 'Operations Pain', weight: 20 },
  { value: 'TECH_PAIN', label: 'Tech Pain', weight: 15 },
  { value: 'JOB_CHANGE', label: 'Job Change', weight: 30 },
  { value: 'PRODUCTION_DROP', label: 'Production Drop', weight: 20 },
  { value: 'COMMISSION_CHANGE', label: 'Commission Change', weight: 22 },
  { value: 'LENDER_DISSATISFACTION', label: 'Lender Dissatisfaction', weight: 25 },
  { value: 'REFERRAL_ACTIVITY', label: 'Referral Activity', weight: 20 },
  { value: 'TEAM_GROWTH', label: 'Team Growth', weight: 15 },
  { value: 'ENGAGEMENT_SPIKE', label: 'Engagement Spike', weight: 18 },
  { value: 'OBJECTION_SOFTENED', label: 'Objection Softened', weight: 15 },
  { value: 'TIME_WINDOW', label: 'Time Window', weight: 10 },
  { value: 'SEASONAL_SURGE', label: 'Seasonal Surge', weight: 12 }
];

export const OBJECTION_CATEGORIES = [
  { value: 'COMPENSATION', label: 'Compensation', icon: '💰' },
  { value: 'TECH_STACK', label: 'Technology/Tools', icon: '💻' },
  { value: 'SUPPORT_STAFF', label: 'Support Staff', icon: '👥' },
  { value: 'OPERATIONS', label: 'Operations', icon: '⚙️' },
  { value: 'PROCESSING', label: 'Processing', icon: '📋' },
  { value: 'UNDERWRITING', label: 'Underwriting', icon: '✍️' },
  { value: 'BRAND_REPUTATION', label: 'Brand/Reputation', icon: '🏆' },
  { value: 'LEAD_FLOW', label: 'Lead Flow', icon: '📊' },
  { value: 'MARKETING', label: 'Marketing', icon: '📢' },
  { value: 'CULTURE', label: 'Culture', icon: '🌟' },
  { value: 'MANAGEMENT', label: 'Management', icon: '👔' },
  { value: 'TRAINING', label: 'Training', icon: '📚' },
  { value: 'COMPLIANCE_RISK', label: 'Compliance Risk', icon: '⚠️' },
  { value: 'NON_COMPETE', label: 'Non-Compete', icon: '📝' },
  { value: 'TIMING', label: 'Timing', icon: '⏰' },
  { value: 'INERTIA', label: 'Inertia', icon: '🦥' },
  { value: 'LOYALTY', label: 'Loyalty', icon: '💝' },
  { value: 'GEOGRAPHY', label: 'Geography', icon: '📍' },
  { value: 'PRODUCT_LIMITATION', label: 'Product Limitation', icon: '🎯' },
  { value: 'PRICING_RATES', label: 'Pricing/Rates', icon: '💵' },
  { value: 'OTHER', label: 'Other', icon: '❓' }
];

export const COMM_CHANNELS = [
  { value: 'EMAIL', label: 'Email', icon: '📧' },
  { value: 'SMS', label: 'SMS', icon: '💬' },
  { value: 'PHONE', label: 'Phone', icon: '📞' },
  { value: 'LINKEDIN', label: 'LinkedIn', icon: '💼' },
  { value: 'INSTAGRAM', label: 'Instagram', icon: '📸' },
  { value: 'FACEBOOK', label: 'Facebook', icon: '👤' },
  { value: 'IN_PERSON', label: 'In Person', icon: '🤝' },
  { value: 'DIRECT_MAIL', label: 'Direct Mail', icon: '📬' }
];

export const TASK_PRIORITIES = [
  { value: 'URGENT', label: 'Urgent', color: '#ef4444' },
  { value: 'HIGH', label: 'High', color: '#f97316' },
  { value: 'MEDIUM', label: 'Medium', color: '#eab308' },
  { value: 'LOW', label: 'Low', color: '#22c55e' }
];

export const TIMING_GRADES = {
  HOT: { label: 'Hot', color: '#ef4444', minScore: 70 },
  WARM: { label: 'Warm', color: '#f97316', minScore: 50 },
  COOL: { label: 'Cool', color: '#3b82f6', minScore: 30 },
  COLD: { label: 'Cold', color: '#6b7280', minScore: 0 }
};

export const getTimingGrade = (score) => {
  if (score >= 70) return TIMING_GRADES.HOT;
  if (score >= 50) return TIMING_GRADES.WARM;
  if (score >= 30) return TIMING_GRADES.COOL;
  return TIMING_GRADES.COLD;
};

export const getStageInfo = (stage) => {
  return RELATIONSHIP_STAGES.find(s => s.value === stage) || RELATIONSHIP_STAGES[0];
};

export const getObjectionInfo = (category) => {
  return OBJECTION_CATEGORIES.find(c => c.value === category) || OBJECTION_CATEGORIES[OBJECTION_CATEGORIES.length - 1];
};
