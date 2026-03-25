# Aria Voice AI + Call Intelligence Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Call Intelligence into the Aria mobile app so LOs can start CI recording with one button, get real-time AI analysis from 6 agents, approve artifacts, and use voice commands to act on call results.

**Architecture:** The Aria voice app (AriaVoiceApp.js) gains a Call Intelligence mode triggered by a button. It reuses the existing `useCallIntelligenceSession` hook and `MobileCallIntelligencePanel` component as a slide-up panel. New voice tools let the LO query and act on CI results via voice commands. The backend gets a bridge service that connects voice session context to CI sessions, plus 8 new voice tools for CI operations.

**Tech Stack:** React 18, FastAPI, PostgreSQL, OpenAI Realtime API, Deepgram transcription, Capacitor (mobile)

---

## File Structure

### Frontend (Create)
- `frontend/src/components/aria/CallIntelligenceButton.js` — Floating CI trigger button for Aria app
- `frontend/src/components/aria/CallIntelligenceSlidePanel.js` — Slide-up panel wrapping MobileCallIntelligencePanel
- `frontend/src/components/aria/ArtifactActionCard.js` — Voice-friendly artifact display card
- `frontend/src/hooks/useAriaCallIntelligence.js` — Bridge hook connecting Aria voice state to CI session

### Frontend (Modify)
- `frontend/src/pages/AriaVoiceApp.js` — Add CI button, panel mount, CI-aware action handler
- `frontend/src/pages/AriaVoiceApp.css` — Styles for CI panel, button, artifacts
- `frontend/src/hooks/useVoiceConnection.js` — Add CI event message types

### Backend (Create)
- `backend/services/voice_ci_bridge_service.py` — Bridge between voice sessions and CI sessions
- `backend/routes/voice/ci_tools.py` — 8 new voice tool handlers for CI operations

### Backend (Modify)
- `backend/routes/voice/tool_handlers.py` — Add send_email, complete_task, send_preapproval handlers + CI tool dispatch
- `backend/routes/voice/openai_realtime.py` — Add 11 new tools to session config (3 broken fixes + 8 CI tools)
- `backend/routes/voice/__init__.py` — Register ci_tools routes
- `backend/routes/voice/utils.py` — Fix ai_config None stub

### Tests (Create)
- `backend/tests/test_voice_ci_bridge.py` — Bridge service tests
- `backend/tests/test_voice_ci_tools.py` — CI tool handler tests
- `backend/tests/test_voice_tool_handlers_extended.py` — Tests for fixed broken tools

---

## STREAM A: Fix Broken Voice Tools (Backend)

### Task 1: Fix ai_config None crash in utils.py

**Files:**
- Modify: `backend/routes/voice/utils.py`

- [ ] **Step 1: Read utils.py to find ai_config stub**
- [ ] **Step 2: Replace None stub with a default config dataclass**

```python
from dataclasses import dataclass

@dataclass
class DefaultAIConfig:
    system_prompt: str = "You are a helpful AI receptionist for a mortgage company."
    business_name: str = os.getenv("BUSINESS_NAME", "Perennia AI")
    greeting: str = "Hello, thank you for calling."

ai_config = DefaultAIConfig()
```

- [ ] **Step 3: Verify openai_realtime.py references resolve**

### Task 2: Add send_email tool to OpenAI session + handler

**Files:**
- Modify: `backend/routes/voice/openai_realtime.py` (add tool definition)
- Modify: `backend/routes/voice/tool_handlers.py` (add handler)

- [ ] **Step 1: Add send_email tool definition to session config tools array**

```python
{
    "type": "function",
    "name": "send_email",
    "description": "Send an email to a contact. Requires email address, subject, and body.",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Email subject line"},
            "body": {"type": "string", "description": "Email body text"},
            "contact_name": {"type": "string", "description": "Recipient name for logging"}
        },
        "required": ["email", "subject", "body"]
    }
}
```

- [ ] **Step 2: Add send_email handler in tool_handlers.py dispatch**

```python
elif func_name == "send_email":
    # Use email delivery service
    from services.email_delivery_service import EmailDeliveryService
    email_service = EmailDeliveryService(db)
    result = await email_service.send_email(
        to_email=args["email"],
        subject=args["subject"],
        body=args["body"],
        organization_id=organization_id,
        user_id=user_id,
    )
    return {"success": True, "message": f"Email sent to {args.get('contact_name', args['email'])}"}
```

### Task 3: Add complete_task tool to OpenAI session + handler

**Files:**
- Modify: `backend/routes/voice/openai_realtime.py`
- Modify: `backend/routes/voice/tool_handlers.py`

- [ ] **Step 1: Add complete_task tool definition**

```python
{
    "type": "function",
    "name": "complete_task",
    "description": "Mark a task as completed by its title or ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_title": {"type": "string", "description": "Title or partial title of the task to complete"},
            "task_id": {"type": "string", "description": "Task ID if known"}
        },
        "required": []
    }
}
```

- [ ] **Step 2: Add handler that finds task by title/ID and marks complete**

### Task 4: Add get_recent_call_summary tool (CI-aware)

**Files:**
- Modify: `backend/routes/voice/openai_realtime.py`
- Modify: `backend/routes/voice/tool_handlers.py`

- [ ] **Step 1: Add tool definition**

```python
{
    "type": "function",
    "name": "get_recent_call_summary",
    "description": "Get the AI-generated summary and action items from the most recent call intelligence session.",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Specific CI session ID. If omitted, uses most recent."}
        }
    }
}
```

- [ ] **Step 2: Add handler that queries call_sessions + call_artifacts**

### Task 5: Add get_call_artifacts tool

**Files:**
- Modify: `backend/routes/voice/openai_realtime.py`
- Modify: `backend/routes/voice/tool_handlers.py`

- [ ] **Step 1: Add tool definition for fetching artifacts by type**

```python
{
    "type": "function",
    "name": "get_call_artifacts",
    "description": "Get specific artifacts from a call intelligence session — action items, document requests, risk flags, or all.",
    "parameters": {
        "type": "object",
        "properties": {
            "artifact_type": {"type": "string", "enum": ["summary", "action_item", "document_request", "risk_flag", "intake_field", "all"], "description": "Type of artifacts to retrieve"},
            "session_id": {"type": "string", "description": "CI session ID. Omit for most recent."}
        }
    }
}
```

### Task 6: Add approve_artifact and execute_artifacts tools

**Files:**
- Modify: `backend/routes/voice/openai_realtime.py`
- Modify: `backend/routes/voice/tool_handlers.py`

- [ ] **Step 1: Add approve_artifact tool**

```python
{
    "type": "function",
    "name": "approve_artifact",
    "description": "Approve a call intelligence artifact for execution. Say the artifact title or type to approve.",
    "parameters": {
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string"},
            "artifact_title": {"type": "string", "description": "Partial title match if ID unknown"}
        }
    }
}
```

- [ ] **Step 2: Add execute_artifacts tool**

```python
{
    "type": "function",
    "name": "execute_artifacts",
    "description": "Execute all approved artifacts from a call intelligence session — creates tasks, sends documents, schedules follow-ups.",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"}
        }
    }
}
```

### Task 7: Add start_call_recording and stop_call_recording tools

**Files:**
- Modify: `backend/routes/voice/openai_realtime.py`
- Modify: `backend/routes/voice/tool_handlers.py`

- [ ] **Step 1: Add start_call_recording tool**

```python
{
    "type": "function",
    "name": "start_call_recording",
    "description": "Start recording and analyzing a call with Call Intelligence. Activates real-time transcription and AI analysis.",
    "parameters": {
        "type": "object",
        "properties": {
            "client_name": {"type": "string", "description": "Name of the person on the call, if known"},
            "client_phone": {"type": "string", "description": "Phone number of the person, if known"},
            "context": {"type": "string", "description": "Brief context like 'rate inquiry' or 'application follow-up'"}
        }
    }
}
```

- [ ] **Step 2: Add stop_call_recording tool**

### Task 8: Add send_document_checklist tool

**Files:**
- Modify: `backend/routes/voice/openai_realtime.py`
- Modify: `backend/routes/voice/tool_handlers.py`

- [ ] **Step 1: Add tool that sends CI-generated document checklist to borrower**

---

## STREAM B: Voice-CI Bridge Service (Backend)

### Task 9: Create voice_ci_bridge_service.py

**Files:**
- Create: `backend/services/voice_ci_bridge_service.py`

- [ ] **Step 1: Create the bridge service**

```python
"""Voice-CI Bridge — connects Aria voice sessions to Call Intelligence sessions.

Manages the lifecycle of CI sessions initiated from the Aria voice app,
handles audio routing, and provides voice-tool-friendly access to CI results.
"""

class VoiceCIBridgeService:
    def __init__(self, db: Session, organization_id: int, user_id: int):
        self.db = db
        self.organization_id = organization_id
        self.user_id = user_id

    async def start_ci_session(self, capture_mode="mobile_app", context=None):
        """Create a new CI session and return session_id."""

    async def stop_ci_session(self, session_id, run_agents=True):
        """End CI session and trigger agent processing."""

    async def get_latest_session(self):
        """Get most recent CI session for this user/org."""

    async def get_session_summary(self, session_id=None):
        """Get human-readable summary from most recent or specified session."""

    async def get_artifacts(self, session_id=None, artifact_type=None):
        """Get artifacts, optionally filtered by type."""

    async def approve_artifact(self, artifact_id=None, title_match=None):
        """Approve artifact by ID or fuzzy title match."""

    async def execute_approved(self, session_id=None):
        """Execute all approved artifacts for a session."""

    async def get_document_checklist(self, session_id=None):
        """Get the document checklist artifact content."""
```

- [ ] **Step 2: Implement each method with proper DB queries**
- [ ] **Step 3: Add tenant scoping (organization_id) to all queries**

---

## STREAM C: Frontend — CI Panel in Aria App

### Task 10: Create CallIntelligenceButton component

**Files:**
- Create: `frontend/src/components/aria/CallIntelligenceButton.js`

- [ ] **Step 1: Create floating CI button component**

```jsx
// Floating button with microphone+brain icon
// States: idle (gray), recording (red pulse), processing (amber), complete (green)
// Props: onClick, isRecording, isProcessing, artifactCount
```

### Task 11: Create CallIntelligenceSlidePanel component

**Files:**
- Create: `frontend/src/components/aria/CallIntelligenceSlidePanel.js`

- [ ] **Step 1: Create slide-up panel that wraps MobileCallIntelligencePanel**

```jsx
// Slides up from bottom of screen (80vh height)
// Has drag handle to dismiss
// Passes through initialContext to MobileCallIntelligencePanel
// Overlay backdrop dims the Aria voice UI behind it
```

### Task 12: Create useAriaCallIntelligence bridge hook

**Files:**
- Create: `frontend/src/hooks/useAriaCallIntelligence.js`

- [ ] **Step 1: Create hook that bridges Aria voice state to CI**

```javascript
const useAriaCallIntelligence = ({ voiceConnection, onArtifactsReady }) => {
  const ciSession = useCallIntelligenceSession({
    initialContext: { source: 'aria_voice_app' },
    skipBackendChunkSend: false,
  });

  // Start CI recording
  const startRecording = async () => { ... };

  // Stop and process
  const stopRecording = async () => { ... };

  // Voice command: "approve all artifacts"
  const approveAll = async () => { ... };

  return {
    ...ciSession,
    startRecording,
    stopRecording,
    approveAll,
    hasArtifacts: ciSession.artifacts.length > 0,
    pendingCount: ciSession.artifacts.filter(a => a.approval_status === 'pending').length,
  };
};
```

### Task 13: Create ArtifactActionCard component

**Files:**
- Create: `frontend/src/components/aria/ArtifactActionCard.js`

- [ ] **Step 1: Create mobile-friendly artifact card**

```jsx
// Compact card showing: icon (by type), title, confidence badge, priority
// Swipe right = approve, swipe left = reject
// Tap = expand to show full content + source evidence
// Types: summary (blue), action_item (orange), document_request (purple),
//        risk_flag (red), intake_field (green), scheduled_appointment (teal)
```

### Task 14: Wire CI into AriaVoiceApp.js

**Files:**
- Modify: `frontend/src/pages/AriaVoiceApp.js`

- [ ] **Step 1: Import new components and hook**

```javascript
import CallIntelligenceButton from '../components/aria/CallIntelligenceButton';
import CallIntelligenceSlidePanel from '../components/aria/CallIntelligenceSlidePanel';
import useAriaCallIntelligence from '../hooks/useAriaCallIntelligence';
```

- [ ] **Step 2: Add CI state and hook integration**

```javascript
const [showCIPanel, setShowCIPanel] = useState(false);
const ci = useAriaCallIntelligence({
  voiceConnection,
  onArtifactsReady: (artifacts) => {
    // Show notification badge
  },
});
```

- [ ] **Step 3: Add CI button to the UI (next to voice orb)**

```jsx
<CallIntelligenceButton
  onClick={() => {
    if (ci.isActive) {
      ci.stopRecording();
    } else {
      ci.startRecording();
      setShowCIPanel(true);
    }
  }}
  isRecording={ci.isActive}
  isProcessing={ci.isStopping}
  artifactCount={ci.pendingCount}
/>
```

- [ ] **Step 4: Add slide panel mount**

```jsx
{showCIPanel && (
  <CallIntelligenceSlidePanel
    onClose={() => setShowCIPanel(false)}
    ciSession={ci}
  />
)}
```

- [ ] **Step 5: Add CI actions to handleCRMAction dispatcher**

```javascript
case 'start_call_recording':
  await ci.startRecording();
  setShowCIPanel(true);
  break;
case 'stop_call_recording':
  await ci.stopRecording();
  break;
case 'get_recent_call_summary':
case 'get_call_artifacts':
case 'approve_artifact':
case 'execute_artifacts':
  // These are handled server-side by voice tools, but update UI
  break;
```

### Task 15: Add CI styles to AriaVoiceApp.css

**Files:**
- Modify: `frontend/src/pages/AriaVoiceApp.css`

- [ ] **Step 1: Add CI button styles (floating, positioned, animated states)**
- [ ] **Step 2: Add slide panel styles (slide-up animation, backdrop, drag handle)**
- [ ] **Step 3: Add artifact card styles (swipe gestures, type-colored borders)**
- [ ] **Step 4: Add CI status indicator styles (recording dot, agent badges)**

---

## STREAM D: Frontend — CI Voice Tool UI Updates

### Task 16: Add CI event handling to useVoiceConnection

**Files:**
- Modify: `frontend/src/hooks/useVoiceConnection.js`

- [ ] **Step 1: Add CI-specific WebSocket message handling**

```javascript
// In the message handler, add:
case 'ci_session_started':
  onCISessionStarted?.(data);
  break;
case 'ci_artifact_generated':
  onCIArtifactGenerated?.(data);
  break;
case 'ci_processing_complete':
  onCIProcessingComplete?.(data);
  break;
```

---

## STREAM E: Backend — CI Tool Implementations

### Task 17: Implement CI tool handlers in ci_tools.py

**Files:**
- Create: `backend/routes/voice/ci_tools.py`

- [ ] **Step 1: Create module with all CI tool handler functions**

```python
"""Voice tool handlers for Call Intelligence operations.

These functions are called by the OpenAI Realtime function-call pipeline
when the LO uses voice commands related to Call Intelligence.
"""

from services.voice_ci_bridge_service import VoiceCIBridgeService

async def handle_start_call_recording(args, db, organization_id, user_id):
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    session_id = await bridge.start_ci_session(
        context=args.get("context"),
    )
    return {"success": True, "session_id": session_id, "message": "Call recording started. I'll analyze the conversation in real-time."}

async def handle_stop_call_recording(args, db, organization_id, user_id):
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    result = await bridge.stop_ci_session(args.get("session_id"), run_agents=True)
    return {"success": True, "message": "Recording stopped. Processing with AI agents now."}

async def handle_get_recent_call_summary(args, db, organization_id, user_id):
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    summary = await bridge.get_session_summary(args.get("session_id"))
    return {"success": True, "summary": summary}

async def handle_get_call_artifacts(args, db, organization_id, user_id):
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    artifacts = await bridge.get_artifacts(
        session_id=args.get("session_id"),
        artifact_type=args.get("artifact_type"),
    )
    return {"success": True, "artifacts": artifacts, "count": len(artifacts)}

async def handle_approve_artifact(args, db, organization_id, user_id):
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    result = await bridge.approve_artifact(
        artifact_id=args.get("artifact_id"),
        title_match=args.get("artifact_title"),
    )
    return {"success": True, "message": f"Artifact approved: {result.get('title', 'unknown')}"}

async def handle_execute_artifacts(args, db, organization_id, user_id):
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    result = await bridge.execute_approved(args.get("session_id"))
    return {"success": True, "message": f"Executed {result.get('count', 0)} artifacts.", "results": result}

async def handle_send_document_checklist(args, db, organization_id, user_id):
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    checklist = await bridge.get_document_checklist(args.get("session_id"))
    # Send via SMS or email
    ...
    return {"success": True, "message": "Document checklist sent to borrower."}
```

- [ ] **Step 2: Wire CI tool dispatch into tool_handlers.py**

```python
# In handle_browser_function_call, add CI tool routing:
CI_TOOLS = {
    "start_call_recording": handle_start_call_recording,
    "stop_call_recording": handle_stop_call_recording,
    "get_recent_call_summary": handle_get_recent_call_summary,
    "get_call_artifacts": handle_get_call_artifacts,
    "approve_artifact": handle_approve_artifact,
    "execute_artifacts": handle_execute_artifacts,
    "send_document_checklist": handle_send_document_checklist,
}

if func_name in CI_TOOLS:
    from routes.voice.ci_tools import CI_TOOLS as ci_dispatch
    return await ci_dispatch[func_name](args, db, organization_id, user_id)
```

### Task 18: Register CI tools in __init__.py

**Files:**
- Modify: `backend/routes/voice/__init__.py`

- [ ] **Step 1: Import ci_tools module and add to re-exports**

---

## STREAM F: Tests

### Task 19: Test voice_ci_bridge_service

**Files:**
- Create: `backend/tests/test_voice_ci_bridge.py`

- [ ] **Step 1: Write tests for bridge service**

Tests: session creation, session retrieval, artifact querying, artifact approval by ID, artifact approval by title match, execute approved, tenant isolation.

### Task 20: Test CI tool handlers

**Files:**
- Create: `backend/tests/test_voice_ci_tools.py`

- [ ] **Step 1: Write tests for each CI tool handler**

Tests: start_call_recording returns session_id, stop_call_recording triggers agents, get_recent_call_summary returns formatted text, get_call_artifacts filters by type, approve_artifact by ID, approve_artifact by title, execute_artifacts count.

### Task 21: Test fixed broken tools

**Files:**
- Create: `backend/tests/test_voice_tool_handlers_extended.py`

- [ ] **Step 1: Write tests for send_email, complete_task handlers**

---

## Parallel Execution Groups

These task groups can run simultaneously:

| Group | Tasks | Agent Count | Dependencies |
|-------|-------|-------------|--------------|
| **G1: Backend fixes** | 1, 2, 3 | 3 agents | None |
| **G2: Backend CI tools** | 4, 5, 6, 7, 8 | 5 agents | None |
| **G3: Backend bridge** | 9 | 1 agent | None |
| **G4: Frontend components** | 10, 11, 12, 13 | 4 agents | None |
| **G5: Frontend wiring** | 14, 15, 16 | 3 agents | G4 |
| **G6: Backend CI handlers** | 17, 18 | 2 agents | G3 |
| **G7: Tests** | 19, 20, 21 | 3 agents | G1, G2, G3 |

**Wave 1 (parallel):** G1 + G2 + G3 + G4 = 13 agents
**Wave 2 (parallel):** G5 + G6 + G7 = 8 agents

Total: 21 tasks, 21 agents across 2 waves.
