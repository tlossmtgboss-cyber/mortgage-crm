// Voice OS Components
// Export all voice-related components for easy importing

export { default as AgentStudio } from './AgentStudio';
export { default as LiveCallsMonitor } from './LiveCallsMonitor';
export { default as AgentBuilder } from './AgentBuilder';
export { default as TalkToAgent } from './TalkToAgent';
export { default as CallQueueDashboard } from './CallQueueDashboard';
export { default as ConferenceRoomDashboard } from './ConferenceRoomDashboard';

// Usage example:
// import { AgentStudio, LiveCallsMonitor, AgentBuilder, CallQueueDashboard } from './components/voice';
//
// Or in routing:
// <Route path="/voice/agents" element={<AgentStudio />} />
// <Route path="/voice/live" element={<LiveCallsMonitor />} />
// <Route path="/voice/agents/new" element={<AgentBuilder />} />
// <Route path="/voice/queues" element={<CallQueueDashboard />} />
