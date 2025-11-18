// voice-orchestrator/src/monitoring/metrics.ts
// Prometheus Metrics

import { Counter, Histogram, Gauge, Registry } from 'prom-client';

export const register = new Registry();

// Call Metrics
export const metrics = {
  // Total calls counter
  callsTotal: new Counter({
    name: 'voice_calls_total',
    help: 'Total number of voice calls',
    labelNames: ['agent_id', 'direction', 'outcome'],
    registers: [register]
  }),

  // Active calls gauge
  activeCalls: new Gauge({
    name: 'voice_active_calls',
    help: 'Number of currently active calls',
    labelNames: ['agent_id'],
    registers: [register]
  }),

  // Call duration histogram
  callDuration: new Histogram({
    name: 'voice_call_duration_seconds',
    help: 'Call duration in seconds',
    labelNames: ['agent_id'],
    buckets: [10, 30, 60, 120, 300, 600, 1800, 3600],
    registers: [register]
  }),

  // STT latency
  sttLatency: new Histogram({
    name: 'voice_stt_latency_ms',
    help: 'Speech-to-text processing latency in milliseconds',
    buckets: [50, 100, 200, 500, 1000, 2000, 5000],
    registers: [register]
  }),

  // TTS latency
  ttsLatency: new Histogram({
    name: 'voice_tts_latency_ms',
    help: 'Text-to-speech synthesis latency in milliseconds',
    buckets: [50, 100, 200, 500, 1000, 2000, 5000],
    registers: [register]
  }),

  // LLM latency
  llmLatency: new Histogram({
    name: 'voice_llm_latency_ms',
    help: 'LLM generation latency in milliseconds',
    buckets: [100, 500, 1000, 2000, 5000, 10000, 20000],
    registers: [register]
  }),

  // Tool execution latency
  toolExecutionLatency: new Histogram({
    name: 'voice_tool_execution_latency_ms',
    help: 'Tool execution latency in milliseconds',
    labelNames: ['tool_name'],
    buckets: [100, 500, 1000, 2000, 5000],
    registers: [register]
  }),

  // Tool calls counter
  toolCalls: new Counter({
    name: 'voice_tool_calls_total',
    help: 'Total number of tool calls',
    labelNames: ['tool_name', 'status'],
    registers: [register]
  }),

  // Errors counter
  errors: new Counter({
    name: 'voice_errors_total',
    help: 'Total number of errors',
    labelNames: ['error_type', 'component'],
    registers: [register]
  }),

  // WebSocket connections
  wsConnections: new Gauge({
    name: 'voice_websocket_connections',
    help: 'Number of active WebSocket connections',
    registers: [register]
  }),

  // Escalations counter
  escalations: new Counter({
    name: 'voice_escalations_total',
    help: 'Total number of escalations to human',
    labelNames: ['agent_id', 'reason'],
    registers: [register]
  }),

  // Appointments booked
  appointmentsBooked: new Counter({
    name: 'voice_appointments_booked_total',
    help: 'Total number of appointments booked via voice AI',
    labelNames: ['agent_id'],
    registers: [register]
  }),

  // Leads created
  leadsCreated: new Counter({
    name: 'voice_leads_created_total',
    help: 'Total number of leads created via voice AI',
    labelNames: ['agent_id'],
    registers: [register]
  })
};

// Collect default metrics (CPU, memory, etc.)
import { collectDefaultMetrics } from 'prom-client';
collectDefaultMetrics({ register });

export default metrics;
