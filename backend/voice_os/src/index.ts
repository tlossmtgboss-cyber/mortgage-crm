// voice-orchestrator/src/index.ts
import 'dotenv/config'; // Load environment variables FIRST
import express from 'express';
import { createServer } from 'http';
import { WebSocketServer } from 'ws';
import { VoiceOrchestrator } from './orchestrator';
import { TwilioHandler } from './telephony/twilio';
import { CRMAPIClient } from './crm/client';
import { logger } from './utils/logger';
import { setupMonitoring } from './monitoring';

const app = express();
const server = createServer(app);
const wss = new WebSocketServer({ server });

// Initialize services
const crmClient = new CRMAPIClient(process.env.CRM_API_URL!);
const orchestrator = new VoiceOrchestrator(crmClient);
const twilioHandler = new TwilioHandler(orchestrator);

// Setup monitoring
setupMonitoring(app);

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

// Twilio webhooks
app.post('/twilio/voice', twilioHandler.handleInbound.bind(twilioHandler));
app.post('/api/voice/twilio/inbound', twilioHandler.handleInbound.bind(twilioHandler));
app.post('/api/voice/twilio/status', twilioHandler.handleStatus.bind(twilioHandler));

// WebSocket for media streams
wss.on('connection', (ws, req) => {
  logger.info('New WebSocket connection', { url: req.url });

  // Extract callId from URL path (e.g., /media/CA123...)
  const urlPath = req.url || '';
  const callIdMatch = urlPath.match(/\/media\/([^?]+)/);
  const callId = callIdMatch ? callIdMatch[1] : new URL(urlPath, `http://${req.headers.host}`).searchParams.get('callId');

  if (!callId) {
    logger.error('Missing callId in WebSocket connection', { url: req.url });
    ws.close(1008, 'Missing callId parameter');
    return;
  }

  logger.info('Handling media stream for call', { callId });
  orchestrator.handleMediaStream(callId, ws);
});

// API endpoints
app.post('/api/voice/calls/outbound', async (req, res) => {
  try {
    const { agent_id, to_number, from_number, context } = req.body;

    const call = await orchestrator.initiateOutbound({
      agentId: agent_id,
      toNumber: to_number,
      fromNumber: from_number,
      context
    });

    res.json(call);
  } catch (error) {
    logger.error('Failed to initiate outbound call', { error });
    res.status(500).json({ error: 'Failed to initiate call' });
  }
});

app.get('/api/voice/calls/:callId', async (req, res) => {
  try {
    const call = await crmClient.getCall(req.params.callId);
    res.json(call);
  } catch (error) {
    logger.error('Failed to fetch call', { error, callId: req.params.callId });
    res.status(500).json({ error: 'Failed to fetch call' });
  }
});

app.get('/api/voice/calls', async (req, res) => {
  try {
    const { agent_id, status, from_date, to_date } = req.query;
    const calls = await crmClient.listCalls({
      agentId: agent_id as string,
      status: status as string,
      fromDate: from_date as string,
      toDate: to_date as string
    });
    res.json(calls);
  } catch (error) {
    logger.error('Failed to list calls', { error });
    res.status(500).json({ error: 'Failed to list calls' });
  }
});

const PORT = process.env.PORT || 8080;
const HOST = '0.0.0.0'; // Railway requires binding to 0.0.0.0

server.listen(PORT, HOST, () => {
  logger.info(`Voice Orchestrator running on ${HOST}:${PORT}`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  logger.info('SIGTERM received, shutting down gracefully');
  server.close(() => {
    logger.info('Server closed');
    process.exit(0);
  });
});
