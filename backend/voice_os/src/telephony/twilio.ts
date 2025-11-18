// voice-orchestrator/src/telephony/twilio.ts
// Twilio Integration Handler

import twilio from 'twilio';
import { Request, Response } from 'express';
import { VoiceOrchestrator } from '../orchestrator';
import { logger } from '../utils/logger';

const VoiceResponse = twilio.twiml.VoiceResponse;

export class TwilioHandler {
  private client: twilio.Twilio;
  private orchestrator: VoiceOrchestrator;

  constructor(orchestrator: VoiceOrchestrator) {
    this.client = twilio(
      process.env.TWILIO_ACCOUNT_SID!,
      process.env.TWILIO_AUTH_TOKEN!
    );
    this.orchestrator = orchestrator;
  }

  /**
   * Handle inbound calls from Twilio
   */
  async handleInbound(req: Request, res: Response): Promise<void> {
    try {
      const callSid = req.body.CallSid;
      const from = req.body.From;
      const to = req.body.To;

      logger.info('Inbound call received', { callSid, from, to });

      // Generate TwiML response with WebSocket stream
      const twiml = new VoiceResponse();

      // Start media stream to our WebSocket server
      const connect = twiml.connect();
      const stream = connect.stream({
        url: `wss://${req.get('host')}/media/${callSid}?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        track: 'both_tracks'
      });

      res.type('text/xml');
      res.send(twiml.toString());

      logger.info('TwiML response sent', { callSid, from, to });
    } catch (error) {
      logger.error('Error handling inbound call', { error });
      res.type('text/xml');
      res.send(this.generateErrorResponse('An error occurred. Please try again.'));
    }
  }

  /**
   * Handle call status callbacks from Twilio
   */
  async handleStatus(req: Request, res: Response): Promise<void> {
    try {
      const callSid = req.body.CallSid;
      const callStatus = req.body.CallStatus;
      const duration = req.body.CallDuration;

      logger.info('Call status update', { callSid, callStatus, duration });

      // Update call session in database
      const updates: any = { status: callStatus };

      if (callStatus === 'completed' || callStatus === 'failed') {
        updates.end_time = new Date().toISOString();
        if (duration) {
          updates.duration_seconds = parseInt(duration, 10);
        }
      }

      // Find call session by call_id and update
      // This would need to be implemented in the CRM client
      // await this.orchestrator['crmClient'].updateCallSessionByCallId(callSid, updates);

      res.sendStatus(200);
    } catch (error) {
      logger.error('Error handling status callback', { error });
      res.sendStatus(500);
    }
  }

  /**
   * Initiate outbound call via Twilio
   */
  async initiateOutboundCall(params: {
    to: string;
    from: string;
    agentId: string;
    callSessionId: string;
  }): Promise<any> {
    try {
      logger.info('Initiating outbound call', params);

      const call = await this.client.calls.create({
        to: params.to,
        from: params.from,
        url: `https://${process.env.DOMAIN}/api/voice/twilio/outbound?callSessionId=${params.callSessionId}&agentId=${params.agentId}`,
        statusCallback: `https://${process.env.DOMAIN}/api/voice/twilio/status`,
        statusCallbackEvent: ['initiated', 'ringing', 'answered', 'completed'],
        record: true, // Enable call recording
        recordingStatusCallback: `https://${process.env.DOMAIN}/api/voice/twilio/recording`
      });

      logger.info('Outbound call initiated', {
        callSid: call.sid,
        callSessionId: params.callSessionId
      });

      return call;
    } catch (error) {
      logger.error('Failed to initiate outbound call', { error, params });
      throw error;
    }
  }

  /**
   * Handle outbound call TwiML
   */
  async handleOutbound(req: Request, res: Response): Promise<void> {
    try {
      const callSessionId = req.query.callSessionId as string;
      const agentId = req.query.agentId as string;

      logger.info('Outbound call answered', { callSessionId, agentId });

      const twiml = new VoiceResponse();

      // Start media stream
      const connect = twiml.connect();
      connect.stream({
        url: `wss://${process.env.DOMAIN}/api/voice/stream?callId=${callSessionId}`,
        track: 'both_tracks',
        statusCallback: `https://${process.env.DOMAIN}/api/voice/twilio/status`
      });

      res.type('text/xml');
      res.send(twiml.toString());
    } catch (error) {
      logger.error('Error handling outbound call', { error });
      res.type('text/xml');
      res.send(this.generateErrorResponse('An error occurred.'));
    }
  }

  /**
   * Handle recording callbacks
   */
  async handleRecording(req: Request, res: Response): Promise<void> {
    try {
      const callSid = req.body.CallSid;
      const recordingUrl = req.body.RecordingUrl;
      const recordingDuration = req.body.RecordingDuration;

      logger.info('Recording completed', {
        callSid,
        recordingUrl,
        duration: recordingDuration
      });

      // Update call session with recording URL
      // This would be implemented in the CRM client
      // await this.orchestrator['crmClient'].updateCallSessionByCallId(callSid, {
      //   recording_url: recordingUrl,
      //   recording_duration_seconds: parseInt(recordingDuration, 10)
      // });

      res.sendStatus(200);
    } catch (error) {
      logger.error('Error handling recording callback', { error });
      res.sendStatus(500);
    }
  }

  /**
   * Get agent configuration for a phone number
   */
  private async getAgentForNumber(phoneNumber: string): Promise<any> {
    try {
      // This would query the database to find which agent handles this number
      // For now, we'll use the CRM API client
      const agents = await this.orchestrator['crmClient'].listAgents({ status: 'active' });

      // Find agent assigned to this number
      // In production, this would be a proper database query
      const agent = agents.find((a: any) => a.phone_number === phoneNumber);

      return agent || null;
    } catch (error) {
      logger.error('Error getting agent for number', { error, phoneNumber });
      return null;
    }
  }

  /**
   * Generate error TwiML response
   */
  private generateErrorResponse(message: string): string {
    const twiml = new VoiceResponse();
    twiml.say({
      voice: 'Polly.Joanna',
      language: 'en-US'
    }, message);
    twiml.hangup();
    return twiml.toString();
  }

  /**
   * End an active call
   */
  async endCall(callSid: string): Promise<void> {
    try {
      await this.client.calls(callSid).update({ status: 'completed' });
      logger.info('Call ended', { callSid });
    } catch (error) {
      logger.error('Failed to end call', { error, callSid });
      throw error;
    }
  }
}
