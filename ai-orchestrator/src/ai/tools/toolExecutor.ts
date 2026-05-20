import { PlannedAction, ActionType } from "../orchestrator/types";

const API_BASE_URL = process.env.CRM_API_URL || "https://api.perenniaai.com";

interface ExecutionResult {
  success: boolean;
  actionType: ActionType;
  result?: any;
  error?: string;
}

interface ExecutionContext {
  userId: string;
  leadId?: string;
  loanId?: string;
  authToken?: string;
}

async function apiCall(
  endpoint: string,
  method: string,
  body?: any,
  token?: string
): Promise<any> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json"
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);

  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal
    });
    clearTimeout(timeout);

    if (!response.ok) {
      const errorText = await response.text().catch(() => "");
      throw new Error(`API error ${response.status}: ${errorText.slice(0, 200)}`);
    }

    const text = await response.text();
    try {
      return JSON.parse(text);
    } catch {
      return { raw: text };
    }
  } catch (error: any) {
    clearTimeout(timeout);
    if (error.name === "AbortError") {
      throw new Error(`API timeout after 15s for ${method} ${endpoint}`);
    }
    throw error;
  }
}

export async function executeActions(
  actions: PlannedAction[],
  context: ExecutionContext
): Promise<ExecutionResult[]> {
  const results: ExecutionResult[] = [];

  for (const action of actions) {
    try {
      const result = await executeAction(action, context);
      results.push({
        success: true,
        actionType: action.type,
        result
      });
    } catch (error) {
      results.push({
        success: false,
        actionType: action.type,
        error: error instanceof Error ? error.message : "Unknown error"
      });
    }
  }

  return results;
}

async function executeAction(
  action: PlannedAction,
  context: ExecutionContext
): Promise<any> {
  switch (action.type) {
    case "CREATE_TASK":
      return createTask(action.payload, context);
    case "ADD_NOTE":
      return addNote(action.payload, context);
    case "UPDATE_LOAN_STATUS":
      return updateLoanStatus(action.payload, context);
    case "SCHEDULE_APPOINTMENT":
      return scheduleAppointment(action.payload, context);
    case "SEND_EMAIL_DRAFT":
      return createEmailDraft(action.payload, context);
    case "SEND_SMS_DRAFT":
      return createSmsDraft(action.payload, context);
    default:
      throw new Error(`Unknown action type: ${action.type}`);
  }
}

async function createTask(
  payload: Record<string, any>,
  context: ExecutionContext
): Promise<any> {
  const taskData = {
    title: payload.title,
    description: payload.description || "",
    due_date: payload.dueDate,
    priority: payload.priority || "medium",
    status: "pending",
    lead_id: context.leadId ? parseInt(context.leadId) : undefined,
    loan_id: context.loanId ? parseInt(context.loanId) : undefined,
    assigned_to: payload.assignee || context.userId
  };

  return apiCall("/api/v1/tasks/", "POST", taskData, context.authToken);
}

async function addNote(
  payload: Record<string, any>,
  context: ExecutionContext
): Promise<any> {
  // Notes are stored on leads/loans, so we update the entity
  const noteContent = payload.content || payload.note;
  const timestamp = new Date().toISOString();
  const formattedNote = `[${timestamp}] ${noteContent}`;

  if (context.loanId) {
    const loanData = await apiCall(
      `/api/v1/loans/${context.loanId}`,
      "GET",
      undefined,
      context.authToken
    );
    const existingNotes = loanData.notes || "";
    const updatedNotes = existingNotes
      ? `${existingNotes}\n\n${formattedNote}`
      : formattedNote;

    return apiCall(
      `/api/v1/loans/${context.loanId}`,
      "PATCH",
      { notes: updatedNotes },
      context.authToken
    );
  } else if (context.leadId) {
    const leadData = await apiCall(
      `/api/v1/leads/${context.leadId}`,
      "GET",
      undefined,
      context.authToken
    );
    const existingNotes = leadData.notes || "";
    const updatedNotes = existingNotes
      ? `${existingNotes}\n\n${formattedNote}`
      : formattedNote;

    return apiCall(
      `/api/v1/leads/${context.leadId}`,
      "PATCH",
      { notes: updatedNotes },
      context.authToken
    );
  }

  throw new Error("No lead or loan context provided for adding note");
}

async function updateLoanStatus(
  payload: Record<string, any>,
  context: ExecutionContext
): Promise<any> {
  if (!context.loanId) {
    throw new Error("No loan ID provided for status update");
  }

  return apiCall(
    `/api/v1/loans/${context.loanId}`,
    "PATCH",
    { status: payload.status, stage: payload.stage },
    context.authToken
  );
}

async function scheduleAppointment(
  payload: Record<string, any>,
  context: ExecutionContext
): Promise<any> {
  const eventData = {
    title: payload.title || "Scheduled Appointment",
    description: payload.description || "",
    start_time: payload.datetime || payload.startTime,
    end_time: payload.endTime || calculateEndTime(payload.datetime, payload.duration || 30),
    event_type: payload.type || "meeting",
    lead_id: context.leadId ? parseInt(context.leadId) : undefined,
    loan_id: context.loanId ? parseInt(context.loanId) : undefined,
    attendees: payload.attendees || []
  };

  return apiCall("/api/v1/calendar/events", "POST", eventData, context.authToken);
}

async function createEmailDraft(
  payload: Record<string, any>,
  context: ExecutionContext
): Promise<any> {
  // For now, create as a task to draft email
  const taskData = {
    title: `Draft Email: ${payload.subject}`,
    description: `To: ${payload.to}\nSubject: ${payload.subject}\n\nBody:\n${payload.body}`,
    due_date: new Date().toISOString(),
    priority: "high",
    status: "pending",
    lead_id: context.leadId ? parseInt(context.leadId) : undefined,
    loan_id: context.loanId ? parseInt(context.loanId) : undefined
  };

  return apiCall("/api/v1/tasks/", "POST", taskData, context.authToken);
}

async function createSmsDraft(
  payload: Record<string, any>,
  context: ExecutionContext
): Promise<any> {
  // For now, create as a task to send SMS
  const taskData = {
    title: `Send SMS to ${payload.to}`,
    description: `Message: ${payload.message}`,
    due_date: new Date().toISOString(),
    priority: "high",
    status: "pending",
    lead_id: context.leadId ? parseInt(context.leadId) : undefined,
    loan_id: context.loanId ? parseInt(context.loanId) : undefined
  };

  return apiCall("/api/v1/tasks/", "POST", taskData, context.authToken);
}

function calculateEndTime(startTime: string, durationMinutes: number): string {
  const start = new Date(startTime);
  start.setMinutes(start.getMinutes() + durationMinutes);
  return start.toISOString();
}
