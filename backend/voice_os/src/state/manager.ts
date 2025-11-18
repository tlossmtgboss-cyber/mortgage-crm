// voice-orchestrator/src/state/manager.ts
// Call State Manager for tracking conversation context

import Redis from 'ioredis';
import { logger } from '../utils/logger';

const redis = new Redis(process.env.REDIS_URL || 'redis://localhost:6379');

export class CallStateManager {
  private state: CallState;
  private callId: string;

  constructor(callId: string, agent: any, contact?: any) {
    this.callId = callId;
    this.state = {
      id: callId,
      sessionId: callId,
      agent,
      contact,
      messages: [],
      currentTask: undefined,
      pendingTools: [],
      bargeInCount: 0,
      escalationRequested: false,
      tasksCreated: [],
      appointmentsCreated: [],
      metadata: {}
    };
  }

  async addUserMessage(text: string) {
    this.state.messages.push({
      role: 'user',
      content: text,
      timestamp: new Date().toISOString()
    });
    await this.persist();
  }

  async addAssistantMessage(text: string) {
    this.state.messages.push({
      role: 'assistant',
      content: text,
      timestamp: new Date().toISOString()
    });
    await this.persist();
  }

  async addSystemMessage(text: string) {
    this.state.messages.push({
      role: 'system',
      content: text,
      timestamp: new Date().toISOString()
    });
    await this.persist();
  }

  async addToolResult(toolName: string, result: any) {
    this.state.messages.push({
      role: 'tool',
      name: toolName,
      content: JSON.stringify(result),
      timestamp: new Date().toISOString()
    });

    // Track created resources
    if (toolName === 'create_task' && result.id) {
      this.state.tasksCreated.push(result.id);
    } else if (toolName === 'schedule_appointment' && result.id) {
      this.state.appointmentsCreated.push(result.id);
    }

    await this.persist();
  }

  setContact(contact: any) {
    this.state.contact = contact;
    this.persist();
  }

  setCurrentTask(task: string) {
    this.state.currentTask = task;
    this.persist();
  }

  markBargeIn() {
    this.state.bargeInCount++;
    this.persist();
  }

  requestEscalation(reason: string) {
    this.state.escalationRequested = true;
    this.state.metadata.escalationReason = reason;
    this.persist();
  }

  getMessages(): Message[] {
    return this.state.messages.filter(m => m.role !== 'system');
  }

  getAllMessages(): Message[] {
    return this.state.messages;
  }

  getTasksCreated(): string[] {
    return this.state.tasksCreated;
  }

  getAppointmentsCreated(): string[] {
    return this.state.appointmentsCreated;
  }

  get agent() {
    return this.state.agent;
  }

  get contact() {
    return this.state.contact;
  }

  get bargeInCount() {
    return this.state.bargeInCount;
  }

  get escalationRequested() {
    return this.state.escalationRequested;
  }

  /**
   * Persist state to Redis for recovery and monitoring
   */
  async persist() {
    try {
      await redis.setex(
        `call_state:${this.callId}`,
        3600, // 1 hour TTL
        JSON.stringify(this.state)
      );
    } catch (error) {
      logger.error('Failed to persist call state', { callId: this.callId, error });
    }
  }

  /**
   * Load existing state from Redis
   */
  static async load(callId: string): Promise<CallStateManager | null> {
    try {
      const data = await redis.get(`call_state:${callId}`);
      if (!data) return null;

      const state = JSON.parse(data);
      const manager = new CallStateManager(callId, state.agent, state.contact);
      manager.state = state;
      return manager;
    } catch (error) {
      logger.error('Failed to load call state', { callId, error });
      return null;
    }
  }

  /**
   * Delete state from Redis (call ended)
   */
  async destroy() {
    try {
      await redis.del(`call_state:${this.callId}`);
    } catch (error) {
      logger.error('Failed to destroy call state', { callId: this.callId, error });
    }
  }

  /**
   * Get conversation summary for context
   */
  getSummary(): string {
    const recentMessages = this.state.messages.slice(-10);
    return recentMessages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => `${m.role}: ${m.content}`)
      .join('\n');
  }
}

export interface CallState {
  id: string;
  sessionId: string;
  agent: any;
  contact?: any;
  loan?: any;
  messages: Message[];
  currentTask?: string;
  pendingTools: any[];
  bargeInCount: number;
  escalationRequested: boolean;
  tasksCreated: string[];
  appointmentsCreated: string[];
  metadata: Record<string, any>;
}

export interface Message {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  name?: string;
  timestamp: string;
}
