// voice-orchestrator/src/orchestrator.ts
import { WebSocket } from 'ws';
import { StreamingSTT } from './voice/stt';
import { StreamingTTS } from './voice/tts';
import { LLMClient } from './ai/llm';
import { DeepgramVoiceAgent, createTwilioVoiceAgent, VoiceAgentConfig } from './voice/deepgram-agent';
import { CallStateManager } from './state/manager';
import { ToolExecutor } from './tools/executor';
import { CRMAPIClient } from './crm/client';
import { logger } from './utils/logger';
import { metrics } from './monitoring/metrics';

// Use Deepgram Voice Agent for all-in-one voice processing
const USE_DEEPGRAM_VOICE_AGENT = process.env.USE_DEEPGRAM_VOICE_AGENT === 'true';

interface OutboundCallRequest {
  agentId: string;
  toNumber: string;
  fromNumber: string;
  context?: Record<string, any>;
}

export class VoiceOrchestrator {
  private activeCallSessions: Map<string, CallSession> = new Map();

  constructor(private crmClient: CRMAPIClient) {}

  async initiateOutbound(req: OutboundCallRequest): Promise<any> {
    logger.info('Initiating outbound call', req);

    // Create call session in database
    const callSession = await this.crmClient.createCallSession({
      agent_id: req.agentId,
      direction: 'outbound',
      to_number: req.toNumber,
      from_number: req.fromNumber,
      status: 'initiating',
      metadata: req.context
    });

    // Trigger Twilio to dial
    // This will be handled by TwilioHandler

    return callSession;
  }

  async handleMediaStream(callId: string, ws: WebSocket): Promise<void> {
    logger.info('Handling media stream', { callId });

    // Route to Deepgram Voice Agent if enabled
    if (USE_DEEPGRAM_VOICE_AGENT) {
      return this.handleMediaStreamWithDeepgramAgent(callId, ws);
    }

    try {
      // Get call session from database (or use defaults for testing)
      let callSession: any;
      let agent: any;

      try {
        callSession = await this.crmClient.getCall(callId);
        agent = await this.crmClient.getAgent(callSession.agent_id);
      } catch (error) {
        // Use defaults when CRM is not available
        logger.info('Using default agent configuration (CRM not available)');
        callSession = {
          id: callId,
          direction: 'inbound',
          from_number: callId, // Will be set by Twilio
          agent_id: 'default'
        };
        agent = {
          id: 'default',
          name: 'Sam - AI Receptionist',
          llm_model: process.env.OPENAI_MODEL || 'gpt-4o',
          system_prompt: process.env.DEFAULT_SYSTEM_PROMPT || 'You are Sam, an AI receptionist.',
          voice_id: process.env.TTS_VOICE || 'alloy',
          voice_config: {
            stt_provider: process.env.STT_PROVIDER || 'openai',
            tts_provider: process.env.TTS_PROVIDER || 'openai'
          }
        };
      }

      // Log call start to AI Receptionist Dashboard
      await this.crmClient.logAIReceptionistActivity({
        client_phone: callSession.from_number,
        action_type: 'incoming_call',
        channel: 'voice',
        outcome_status: 'in_progress',
        conversation_id: callId,
        extra_data: {
          agent_id: agent.id,
          agent_name: agent.name,
          call_direction: callSession.direction
        }
      });

      // Initialize call state
      const state = new CallStateManager(callId, agent);

      // Initialize voice services
      const sttProvider = agent.voice_config?.stt_provider || process.env.STT_PROVIDER || 'openai';
      const ttsProvider = agent.voice_config?.tts_provider || process.env.TTS_PROVIDER || 'openai';
      const voiceId = agent.voice_id || process.env.TTS_VOICE || 'alloy';

      const stt = new StreamingSTT(sttProvider);
      const tts = new StreamingTTS(ttsProvider, voiceId);
      const llm = new LLMClient(agent.llm_model, agent.system_prompt);
      const toolExecutor = new ToolExecutor(this.crmClient);

      // Track metrics
      const callStartTime = Date.now();
      metrics.activeCalls.inc({ agent_id: agent.id });

      // Play consent message
      await this.playConsentMessage(ws, tts);

      // Identify caller and set context
      if (callSession.direction === 'inbound') {
        // Add caller phone number to system context FIRST
        await state.addSystemMessage(`The caller is calling from phone number: ${callSession.from_number}. This is already in your system - do not ask for it again.`);

        const contact = await this.identifyCaller(callSession.from_number);
        if (contact) {
          state.setContact(contact);
          await state.addSystemMessage(`Caller identified: ${contact.first_name} ${contact.last_name}`);
        }
      }

      // Main conversation loop
      let isCallActive = true;
      let audioBuffer: Buffer[] = [];

      ws.on('message', async (data: Buffer) => {
        try {
          // Parse Twilio media message
          const message = JSON.parse(data.toString());

          if (message.event === 'media') {
            // Accumulate audio
            const audioChunk = Buffer.from(message.media.payload, 'base64');
            audioBuffer.push(audioChunk);

            // Process when we have enough audio (streaming)
            if (audioBuffer.length >= 10) { // ~200ms of audio
              const audio = Buffer.concat(audioBuffer);
              audioBuffer = [];

              const sttStart = Date.now();
              const transcript = await stt.process(audio);
              metrics.sttLatency.observe(Date.now() - sttStart);

              if (transcript && transcript.isFinal) {
                logger.info('User said', { callId, text: transcript.text });
                await state.addUserMessage(transcript.text);

                // Check for escalation keywords
                if (this.shouldEscalate(transcript.text)) {
                  await this.handleEscalation(callId, ws, state);
                  return;
                }

                // Generate AI response
                const llmStart = Date.now();
                const response = await llm.streamCompletion({
                  messages: state.getMessages(),
                  tools: agent.tools_allowed,
                  temperature: agent.temperature || 0.7
                });
                metrics.llmLatency.observe(Date.now() - llmStart);

                let fullResponseText = '';

                // Process streaming response
                for await (const chunk of response) {
                  if (chunk.type === 'tool_call') {
                    logger.info('Tool call', { callId, tool: chunk.name, args: chunk.arguments });

                    const toolStart = Date.now();
                    const result = await toolExecutor.execute(
                      chunk.name,
                      chunk.arguments,
                      { callId, contactId: state.contact?.id }
                    );
                    metrics.toolExecutionLatency.observe(Date.now() - toolStart);

                    await state.addToolResult(chunk.name, result);
                  }

                  if (chunk.type === 'text') {
                    fullResponseText += chunk.text;

                    // Stream to TTS when we have a complete sentence
                    if (chunk.text.match(/[.!?]$/)) {
                      const ttsStart = Date.now();
                      const audio = await tts.synthesize(chunk.text);
                      metrics.ttsLatency.observe(Date.now() - ttsStart);

                      // Send audio to caller
                      const audioMessage = {
                        event: 'media',
                        media: {
                          payload: audio.toString('base64')
                        }
                      };
                      ws.send(JSON.stringify(audioMessage));
                    }
                  }
                }

                if (fullResponseText) {
                  logger.info('Assistant said', { callId, text: fullResponseText });
                  await state.addAssistantMessage(fullResponseText);
                }
              }
            }
          }

          if (message.event === 'stop') {
            logger.info('Call ended', { callId });
            isCallActive = false;
            await this.finalizeCall(callId, state, callStartTime);
            ws.close();
          }

        } catch (error) {
          logger.error('Error processing message', { callId, error });
          // Continue processing - don't crash on single error
        }
      });

      ws.on('close', async () => {
        logger.info('WebSocket closed', { callId });
        metrics.activeCalls.dec({ agent_id: agent.id });

        if (isCallActive) {
          await this.finalizeCall(callId, state, callStartTime);
        }
      });

      ws.on('error', (error) => {
        logger.error('WebSocket error', { callId, error });
        metrics.activeCalls.dec({ agent_id: agent.id });
      });

    } catch (error) {
      logger.error('Failed to handle media stream', { callId, error });
      ws.close(1011, 'Internal server error');
    }
  }

  /**
   * Handle media stream using Deepgram Voice Agent (all-in-one STT + LLM + TTS)
   * This provides a unified, low-latency voice experience
   */
  private async handleMediaStreamWithDeepgramAgent(callId: string, ws: WebSocket): Promise<void> {
    logger.info('[DeepgramAgent] Handling media stream with unified Voice Agent', { callId });

    try {
      // Get call session from database (or use defaults for testing)
      let callSession: any;
      let agent: any;

      try {
        callSession = await this.crmClient.getCall(callId);
        agent = await this.crmClient.getAgent(callSession.agent_id);
      } catch (error) {
        logger.info('[DeepgramAgent] Using default agent configuration (CRM not available)');
        callSession = {
          id: callId,
          direction: 'inbound',
          from_number: callId,
          agent_id: 'default'
        };
        agent = {
          id: 'default',
          name: 'Aria - AI Assistant',
          llm_model: 'claude-3-haiku-20240307',
          system_prompt: process.env.DEFAULT_SYSTEM_PROMPT || `You are Aria, a warm and professional AI assistant for mortgage loan officers.
You help them manage their pipeline, follow up with leads, schedule appointments, and answer questions.

Voice conversation guidelines:
- Keep responses concise and conversational (under 50 words when possible)
- Use natural speech patterns
- Be warm, friendly, and professional
- When asked to perform actions, confirm what you're doing
- Ask clarifying questions when needed`,
          voice_id: 'aura-asteria-en'
        };
      }

      // Log call start to AI Receptionist Dashboard
      await this.crmClient.logAIReceptionistActivity({
        client_phone: callSession.from_number,
        action_type: 'incoming_call',
        channel: 'voice',
        outcome_status: 'in_progress',
        conversation_id: callId,
        extra_data: {
          agent_id: agent.id,
          agent_name: agent.name,
          call_direction: callSession.direction,
          voice_provider: 'deepgram_voice_agent'
        }
      });

      // Initialize call state
      const state = new CallStateManager(callId, agent);

      // Track metrics
      const callStartTime = Date.now();
      metrics.activeCalls.inc({ agent_id: agent.id });

      // Identify caller and set context
      if (callSession.direction === 'inbound') {
        const contact = await this.identifyCaller(callSession.from_number);
        if (contact) {
          state.setContact(contact);
        }
      }

      // Build system prompt with caller context
      let systemPrompt = agent.system_prompt;
      if (callSession.from_number) {
        systemPrompt += `\n\nThe caller is calling from phone number: ${callSession.from_number}.`;
      }
      if (state.contact) {
        systemPrompt += `\nCaller identified: ${state.contact.first_name} ${state.contact.last_name}`;
      }

      // Create Deepgram Voice Agent
      const voiceAgent = createTwilioVoiceAgent(
        systemPrompt,
        (audioBase64: string) => {
          // Send audio back to Twilio
          const audioMessage = {
            event: 'media',
            media: {
              payload: audioBase64
            }
          };
          ws.send(JSON.stringify(audioMessage));
        },
        {
          voiceModel: agent.voice_id || 'aura-asteria-en',
          llmModel: agent.llm_model || 'claude-3-haiku-20240307',
          sttModel: 'nova-2'
        }
      );

      // Connect to Deepgram
      const connected = await voiceAgent.connect();
      if (!connected) {
        logger.error('[DeepgramAgent] Failed to connect to Deepgram Voice Agent');
        ws.close(1011, 'Voice agent connection failed');
        return;
      }

      logger.info('[DeepgramAgent] Connected to Deepgram Voice Agent', { callId });

      // Handle incoming Twilio messages
      ws.on('message', async (data: Buffer) => {
        try {
          const message = JSON.parse(data.toString());

          if (message.event === 'media') {
            // Forward audio to Deepgram Voice Agent
            const audioChunk = Buffer.from(message.media.payload, 'base64');
            voiceAgent.sendAudio(audioChunk);
          }

          if (message.event === 'stop') {
            logger.info('[DeepgramAgent] Call ended', { callId });
            voiceAgent.close();
            await this.finalizeCall(callId, state, callStartTime);
            ws.close();
          }

        } catch (error) {
          logger.error('[DeepgramAgent] Error processing message', { callId, error });
        }
      });

      ws.on('close', async () => {
        logger.info('[DeepgramAgent] WebSocket closed', { callId });
        metrics.activeCalls.dec({ agent_id: agent.id });
        voiceAgent.close();
        await this.finalizeCall(callId, state, callStartTime);
      });

      ws.on('error', (error) => {
        logger.error('[DeepgramAgent] WebSocket error', { callId, error });
        metrics.activeCalls.dec({ agent_id: agent.id });
        voiceAgent.close();
      });

    } catch (error) {
      logger.error('[DeepgramAgent] Failed to handle media stream', { callId, error });
      ws.close(1011, 'Internal server error');
    }
  }

  private async identifyCaller(phoneNumber: string): Promise<any> {
    try {
      return await this.crmClient.findContactByPhone(phoneNumber);
    } catch (error) {
      logger.warn('Failed to identify caller', { phoneNumber, error });
      return null;
    }
  }

  private shouldEscalate(text: string): boolean {
    const escalationKeywords = [
      'speak to a person',
      'talk to someone',
      'human',
      'representative',
      'agent',
      'manager',
      'supervisor',
      'real person'
    ];

    const lowerText = text.toLowerCase();
    return escalationKeywords.some(keyword => lowerText.includes(keyword));
  }

  private async handleEscalation(callId: string, ws: WebSocket, state: CallStateManager): Promise<void> {
    logger.info('Escalating call to human', { callId });

    // Add to state
    await state.requestEscalation('User requested human');

    // Create task for human follow-up
    await this.crmClient.createTask({
      contact_id: state.contact?.id,
      title: 'Call escalation - User requested human',
      description: `Call ${callId} was escalated. Recent conversation:\n${this.getRecentConversation(state)}`,
      priority: 'high',
      due_date: new Date().toISOString()
    });

    // Play transfer message
    // In production, this would actually transfer to a human
    const message = "I understand. Let me connect you with someone who can help. Please hold.";
    // Convert to audio and send...
  }

  private getRecentConversation(state: CallStateManager, lastN: number = 5): string {
    const messages = state.getMessages().slice(-lastN);
    return messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => `${m.role}: ${m.content}`)
      .join('\n');
  }

  private async playConsentMessage(ws: WebSocket, tts: StreamingTTS): Promise<void> {
    const messages = [
      "This call may be recorded for quality and training purposes.",
      "You'll be speaking with an AI assistant. You can ask for a human at any time."
    ];

    for (const message of messages) {
      const audio = await tts.synthesize(message);
      const audioMessage = {
        event: 'media',
        media: {
          payload: audio.toString('base64')
        }
      };
      ws.send(JSON.stringify(audioMessage));

      // Wait for audio to finish playing
      await new Promise(resolve => setTimeout(resolve, message.length * 60)); // ~60ms per character
    }
  }

  private async finalizeCall(callId: string, state: CallStateManager, startTime: number): Promise<void> {
    try {
      logger.info('Finalizing call', { callId });

      const duration = Math.floor((Date.now() - startTime) / 1000);
      metrics.callDuration.observe({ agent_id: state.agent.id }, duration);

      // Generate call summary using LLM
      const summary = await this.generateCallSummary(state.getMessages());

      // Update call session
      await this.crmClient.updateCallSession(callId, {
        status: 'completed',
        end_time: new Date().toISOString(),
        duration_seconds: duration,
        transcript: state.getMessages(),
        summary: summary.text,
        sentiment: summary.sentiment,
        outcome: summary.outcome,
        tasks_created: state.getTasksCreated()
      });

      // Log call note to CRM if contact exists
      if (state.contact) {
        await this.crmClient.logCallNote({
          contact_id: state.contact.id,
          note: summary.text,
          category: 'general',
          source: 'voice_ai'
        });
      }

      // Log call end to AI Receptionist Dashboard
      await this.crmClient.logAIReceptionistActivity({
        client_name: state.contact ? `${state.contact.first_name} ${state.contact.last_name}` : undefined,
        client_phone: state.contact?.phone,
        action_type: 'call_ended',
        channel: 'voice',
        message_out: summary.text,
        outcome_status: summary.outcome,
        conversation_id: callId,
        extra_data: {
          agent_id: state.agent.id,
          agent_name: state.agent.name,
          duration_seconds: duration,
          sentiment: summary.sentiment,
          tasks_created: state.getTasksCreated()
        }
      });

      // Track metrics
      metrics.callsTotal.inc({
        agent_id: state.agent.id,
        direction: 'inbound',
        outcome: summary.outcome
      });

      logger.info('Call finalized', { callId, duration, outcome: summary.outcome });

    } catch (error) {
      logger.error('Failed to finalize call', { callId, error });
    }
  }

  private async generateCallSummary(messages: any[]): Promise<{
    text: string;
    sentiment: string;
    outcome: string;
  }> {
    // Use LLM to generate structured summary
    const summaryPrompt = `
Analyze this call transcript and provide a structured summary:

${messages.map(m => `${m.role}: ${m.content}`).join('\n')}

Provide a JSON response with:
- text: 2-3 sentence summary of the call
- sentiment: "positive", "neutral", or "negative"
- outcome: "appointment_booked", "docs_requested", "info_provided", "escalated", "no_resolution"
`;

    const llm = new LLMClient('gpt-4-turbo', 'You are a call analyst.');
    const response = await llm.generateJSON(summaryPrompt);

    return response;
  }
}

interface CallSession {
  id: string;
  agent_id: string;
  direction: string;
  from_number: string;
  to_number: string;
  status: string;
}
