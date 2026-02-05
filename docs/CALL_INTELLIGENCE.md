# Call Intelligence & Monitoring

AI-powered call analysis platform for mortgage loan officers, providing real-time transcription, intelligent data extraction, and seamless call-to-application conversion.

## Overview

Call Intelligence transforms phone conversations into actionable mortgage data. The system captures calls across multiple channels, transcribes in real-time using Deepgram, extracts borrower information with AI agents, and enables one-click conversion to loan applications.

## Key Capabilities

| Capability | Description |
|------------|-------------|
| **Live Monitoring** | Real-time dashboard showing active calls with live transcription |
| **Auto-Transcribe** | Deepgram-powered transcription with speaker diarization |
| **QA Scoring** | Automated quality assessment and coaching recommendations |
| **Data Extraction** | AI extraction of borrower details, property info, income data |
| **Call Screening** | Spam detection and intelligent call routing |
| **Call-to-App Conversion** | Convert captured call data directly to loan applications |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Capture Sources                          │
├───────────────┬───────────────┬─────────────────┬───────────────┤
│  Mobile App   │  CRM Web Call │  Ambient Mic    │  Video Call   │
└───────┬───────┴───────┬───────┴────────┬────────┴───────┬───────┘
        │               │                │                │
        └───────────────┴────────────────┴────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  Call Monitoring      │
                    │  Orchestrator         │
                    └───────────┬───────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐     ┌───────────────────┐    ┌──────────────────┐
│   Deepgram    │     │    AI Agents      │    │   Telnyx Voice   │
│  Transcription│     │  (Data Extract)   │    │   + Retell AI    │
└───────────────┘     └───────────────────┘    └──────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   Artifact Store      │
                    │  (Tasks, Notes, Data) │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   Review Queue        │
                    │  (Human Approval)     │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   CRM Execution       │
                    │  (Create/Update)      │
                    └───────────────────────┘
```

## Technology Stack

| Component | Provider | Purpose |
|-----------|----------|---------|
| **Telephony** | Telnyx | Voice calls, SMS, Call Control API, TeXML |
| **Voice AI** | Retell AI | Conversational AI agents, voice synthesis |
| **Transcription** | Deepgram | Real-time STT with speaker diarization |
| **Data Extraction** | Claude/OpenAI | Mortgage-specific entity extraction |

## Telnyx Integration

### Call Control API
- Programmable voice with Call Control API
- TeXML (TwiML-compatible) for call flows
- AMD (Answering Machine Detection) for outbound
- SIP bridging to Retell AI agents

### Inbound Flow
```
Phone Call → Telnyx → TeXML App → SIP Forward → Retell AI Agent
                                                      ↓
                                              AI Conversation
                                                      ↓
                                              Deepgram Transcription
                                                      ↓
                                              Call Intelligence
```

### Outbound Flow
```
Retell AI Agent → SIP Termination → Telnyx → Phone Call
```

### Configuration
```env
TELNYX_API_KEY=your_telnyx_api_key
TELNYX_PUBLIC_KEY=your_telnyx_public_key
TELNYX_CONNECTION_ID=your_telnyx_connection_id
TELNYX_MESSAGING_PROFILE_ID=your_messaging_profile_id
RETELL_API_KEY=your_retell_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
```

## User Interface

### Dashboard Tab
- **Metrics Cards**: Pending reviews, active calls, completed today, conversion rate
- **Urgent Calls**: Calls requiring immediate attention (active >30 min, pending >24h)
- **Quick Actions**: Jump to review queue or active calls

### Active Calls Tab
- Real-time call monitoring with live transcription
- Speaker identification and timestamps
- Duration tracking and participant info
- Live AI suggestions during calls

### Review Queue Tab
- List of completed calls pending human review
- AI-extracted artifacts (tasks, notes, borrower data)
- Approve/Reject controls for each artifact
- Bulk execute approved actions

### Completed Tab
- Historical view of reviewed calls
- Read-only access to transcripts and artifacts
- Search and filter by date, LO, outcome

## API Endpoints

### Session Management
```
POST   /api/v1/call-monitoring/sessions              # Create new session
GET    /api/v1/call-monitoring/sessions              # List all sessions
GET    /api/v1/call-monitoring/sessions/{id}         # Get session details
PATCH  /api/v1/call-monitoring/sessions/{id}         # Update session
POST   /api/v1/call-monitoring/sessions/{id}/end     # End session & process
DELETE /api/v1/call-monitoring/sessions/{id}         # Delete session
```

### Transcription
```
POST   /api/v1/call-monitoring/sessions/{id}/transcript   # Add transcript chunk
GET    /api/v1/call-monitoring/sessions/{id}/transcript   # Get full transcript
```

### Review & Artifacts
```
GET    /api/v1/call-monitoring/sessions/{id}/review       # Get review data
POST   /api/v1/call-monitoring/sessions/{id}/approve      # Approve artifacts
POST   /api/v1/call-monitoring/sessions/{id}/reject       # Reject artifacts
POST   /api/v1/call-monitoring/sessions/{id}/execute      # Execute approved
```

### Telnyx Webhooks
```
POST   /api/v1/telnyx/webhook                        # Main Telnyx webhook
POST   /api/v1/telnyx/voice/inbound                  # Inbound call handler
POST   /api/v1/telnyx/voice/status                   # Call status updates
POST   /api/v1/telnyx/amd                            # AMD results
```

## Capture Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `mobile_app` | iOS/Android app with Aria voice | Field LOs on the go |
| `crm_web_call` | Browser-based softphone | Desktop users |
| `ambient_mic` | Background listening | In-person meetings |
| `video_call` | Zoom/Teams integration | Virtual meetings |

## AI Agents

The system runs specialized AI agents on completed transcripts:

1. **Borrower Info Extractor** - Names, contact info, SSN (redacted)
2. **Property Data Extractor** - Address, type, value, occupancy
3. **Income Analyzer** - Employment, income sources, documentation
4. **Task Generator** - Follow-up tasks based on conversation
5. **Note Summarizer** - Key points and action items
6. **Compliance Checker** - Recording disclosure, TCPA

## Artifact Types

| Type | Description | CRM Action |
|------|-------------|------------|
| `task` | Follow-up tasks | Create in task list |
| `note` | Call summaries | Add to loan/lead notes |
| `lead_data` | Extracted borrower info | Update lead record |
| `loan_data` | Loan parameters | Update loan record |
| `document_request` | Missing docs identified | Send doc request |

## Approval Workflow

```
Artifacts Generated
        │
        ▼
   ┌─────────┐
   │ Pending │ ◄── Human reviews each artifact
   └────┬────┘
        │
   ┌────┴────┐
   │         │
   ▼         ▼
┌────────┐ ┌────────┐
│Approved│ │Rejected│
└───┬────┘ └────────┘
    │
    ▼
┌────────┐
│Execute │ ◄── One-click to apply all approved
└────────┘
```

## Retell AI Integration

Voice AI agents powered by Retell for:
- **AI Receptionist**: Automated call answering and routing
- **Lead Qualification**: Pre-screen callers with AI
- **Appointment Scheduling**: Book directly during calls
- **FAQ Handling**: Answer common mortgage questions

### Telnyx-Retell Bridge
```python
# SIP forwarding from Telnyx to Retell
Inbound: Telnyx → SIP → Retell AI Agent
Outbound: Retell → SIP Termination → Telnyx → PSTN
```

## Deepgram Transcription

Real-time speech-to-text features:
- **Nova-2 Model**: High accuracy for mortgage terminology
- **Speaker Diarization**: Distinguish LO from borrower
- **Smart Formatting**: Numbers, addresses, dollar amounts
- **Streaming**: Live transcription during calls

### Audio Requirements
- Supported: WAV, MP3, FLAC, WebM
- Sample rate: 8kHz minimum (16kHz recommended)
- Dual-channel preferred for speaker separation

## Mobile Integration

The iOS app includes Call Intelligence with:

- **Aria Voice Activation**: "Start call capture" voice command
- **CarPlay Support**: Hands-free call intelligence while driving
- **Push Notifications**: Alerts when calls need review
- **Offline Mode**: Queue recordings for later processing

## Data Model

### CallSession
```
- id: UUID
- user_id: int
- capture_mode: enum
- status: active | completed | reviewed
- approval_status: pending | approved | rejected
- started_at: timestamp
- ended_at: timestamp
- telnyx_call_control_id: optional
- loan_id: optional
- lead_id: optional
- metadata: jsonb
```

### CallTranscript
```
- session_id: UUID
- speaker_label: string
- text: string
- start_time_ms: int
- end_time_ms: int
- confidence: float
- is_final: bool
```

### CallArtifact
```
- session_id: UUID
- artifact_type: enum
- content: jsonb
- approval_status: pending | approved | rejected
- executed_at: optional timestamp
```

## Metrics & Analytics

- **Calls per day/week/month**: Volume tracking
- **Average call duration**: Efficiency metrics
- **Conversion rate**: Calls → Applications
- **Review turnaround**: Time from completed to reviewed
- **Agent accuracy**: AI extraction quality scores
- **QA scores**: Call quality distribution

## Best Practices

1. **Review within 24 hours** - Keep the queue manageable
2. **Train the AI** - Reject inaccurate artifacts to improve models
3. **Use call-to-app** - Convert qualified leads immediately
4. **Monitor active calls** - Jump in with coaching if needed
5. **Check compliance** - Verify recording disclosures
