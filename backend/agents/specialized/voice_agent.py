"""
Voice OS Agent

Specialized agent for voice command processing with 8 tools:
1. process_voice_command - Parse and execute voice commands
2. get_voice_context - Get current voice session context
3. transcribe_audio - Convert audio to text
4. synthesize_speech - Convert text to speech
5. get_voice_shortcuts - Get available voice shortcuts
6. set_voice_preference - Set user voice preferences
7. log_voice_interaction - Log voice interaction for training
8. get_voice_history - Get voice interaction history
"""

from typing import Any, Dict, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class VoiceCommandInput(BaseModel):
    text: str = Field(..., description="Voice command text")
    confidence: Optional[float] = Field(None, description="Transcription confidence score")
    context: Optional[Dict] = Field(None, description="Current context")


class VoiceContextInput(BaseModel):
    session_id: Optional[str] = Field(None, description="Voice session ID")


class TranscribeInput(BaseModel):
    audio_data: str = Field(..., description="Base64 encoded audio data")
    language: str = Field(default="en-US", description="Language code")


class SynthesizeInput(BaseModel):
    text: str = Field(..., description="Text to synthesize")
    voice: str = Field(default="default", description="Voice ID")
    speed: float = Field(default=1.0, description="Speech speed")


class ShortcutsInput(BaseModel):
    category: Optional[str] = Field(None, description="Filter by category")


class PreferenceInput(BaseModel):
    preference_key: str = Field(..., description="Preference key")
    preference_value: Any = Field(..., description="Preference value")


class LogInteractionInput(BaseModel):
    command: str = Field(..., description="Voice command")
    response: str = Field(..., description="System response")
    success: bool = Field(..., description="Whether command succeeded")


class VoiceHistoryInput(BaseModel):
    limit: int = Field(default=20, description="Number of interactions to return")


# ============================================================================
# VOICE OS AGENT
# ============================================================================

@AgentRegistry.register
class VoiceAgent(SpecializedAgent):
    """
    Voice OS agent for voice command processing.

    Handles voice input, command parsing, and audio synthesis
    with 8 specialized tools.
    """

    @property
    def name(self) -> str:
        return "VoiceAgent"

    @property
    def description(self) -> str:
        return "Processes voice commands, transcription, and speech synthesis"

    def _register_tools(self):
        """Register all voice tools"""

        self.register_tool(AgentTool(
            name="process_voice_command",
            description="Parse and execute a voice command",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._process_voice_command,
            input_schema=VoiceCommandInput
        ))

        self.register_tool(AgentTool(
            name="get_voice_context",
            description="Get current voice session context",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_voice_context,
            input_schema=VoiceContextInput
        ))

        self.register_tool(AgentTool(
            name="transcribe_audio",
            description="Convert audio to text using speech recognition",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._transcribe_audio,
            input_schema=TranscribeInput
        ))

        self.register_tool(AgentTool(
            name="synthesize_speech",
            description="Convert text to speech audio",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._synthesize_speech,
            input_schema=SynthesizeInput
        ))

        self.register_tool(AgentTool(
            name="get_voice_shortcuts",
            description="Get available voice command shortcuts",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_voice_shortcuts,
            input_schema=ShortcutsInput
        ))

        self.register_tool(AgentTool(
            name="set_voice_preference",
            description="Set user voice preferences",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._set_voice_preference,
            input_schema=PreferenceInput
        ))

        self.register_tool(AgentTool(
            name="log_voice_interaction",
            description="Log voice interaction for training and analytics",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._log_voice_interaction,
            input_schema=LogInteractionInput
        ))

        self.register_tool(AgentTool(
            name="get_voice_history",
            description="Get voice interaction history",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_voice_history,
            input_schema=VoiceHistoryInput
        ))

    async def _process_voice_command(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Process voice command"""
        command = input_data["text"].lower()

        # Command patterns
        patterns = {
            "show": {"intent": "view", "action": "display"},
            "create": {"intent": "create", "action": "new"},
            "add": {"intent": "create", "action": "add"},
            "call": {"intent": "communication", "action": "call"},
            "email": {"intent": "communication", "action": "email"},
            "schedule": {"intent": "calendar", "action": "schedule"},
            "search": {"intent": "search", "action": "find"},
            "find": {"intent": "search", "action": "find"}
        }

        parsed = {"original": command, "intent": "unknown", "action": "unknown", "entities": []}

        for keyword, mapping in patterns.items():
            if keyword in command:
                parsed["intent"] = mapping["intent"]
                parsed["action"] = mapping["action"]
                break

        # Extract entities (simplified)
        if "lead" in command:
            parsed["entities"].append({"type": "entity", "value": "lead"})
        if "loan" in command:
            parsed["entities"].append({"type": "entity", "value": "loan"})
        if "pipeline" in command:
            parsed["entities"].append({"type": "entity", "value": "pipeline"})

        return ToolResult(
            success=True,
            data={
                "parsed": parsed,
                "confidence": input_data.get("confidence", 0.9),
                "executable": parsed["intent"] != "unknown"
            },
            message=f"Parsed command: {parsed['intent']} - {parsed['action']}"
        )

    async def _get_voice_context(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get voice session context"""
        voice_context = {
            "session_id": input_data.get("session_id") or "default",
            "current_view": "dashboard",
            "last_entity": None,
            "conversation_history": [],
            "preferences": {
                "voice": "default",
                "speed": 1.0,
                "confirmations": True
            }
        }

        return ToolResult(
            success=True,
            data=voice_context,
            message="Voice context retrieved"
        )

    async def _transcribe_audio(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Transcribe audio to text"""
        # In production, this would use a speech-to-text service
        return ToolResult(
            success=True,
            data={
                "text": "Simulated transcription",
                "language": input_data.get("language", "en-US"),
                "confidence": 0.95,
                "alternatives": []
            },
            message="Audio transcribed"
        )

    async def _synthesize_speech(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Synthesize text to speech"""
        # In production, this would use a text-to-speech service
        return ToolResult(
            success=True,
            data={
                "text": input_data["text"],
                "voice": input_data.get("voice", "default"),
                "speed": input_data.get("speed", 1.0),
                "audio_url": None,  # Would be actual audio URL
                "duration_ms": len(input_data["text"]) * 60  # Rough estimate
            },
            message="Speech synthesized"
        )

    async def _get_voice_shortcuts(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get available voice shortcuts"""
        shortcuts = {
            "navigation": [
                {"phrase": "Go to dashboard", "action": "navigate_dashboard"},
                {"phrase": "Show my pipeline", "action": "navigate_pipeline"},
                {"phrase": "Open leads", "action": "navigate_leads"}
            ],
            "actions": [
                {"phrase": "Create new lead", "action": "create_lead"},
                {"phrase": "Schedule a call", "action": "schedule_call"},
                {"phrase": "Send email", "action": "compose_email"}
            ],
            "queries": [
                {"phrase": "How many leads do I have", "action": "count_leads"},
                {"phrase": "What's my pipeline value", "action": "pipeline_value"},
                {"phrase": "Show today's tasks", "action": "todays_tasks"}
            ]
        }

        category = input_data.get("category")
        if category and category in shortcuts:
            filtered = {category: shortcuts[category]}
        else:
            filtered = shortcuts

        return ToolResult(
            success=True,
            data={"shortcuts": filtered},
            message="Voice shortcuts retrieved"
        )

    async def _set_voice_preference(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Set voice preference"""
        return ToolResult(
            success=True,
            data={
                "key": input_data["preference_key"],
                "value": input_data["preference_value"],
                "updated_at": datetime.now().isoformat()
            },
            message=f"Preference '{input_data['preference_key']}' updated"
        )

    async def _log_voice_interaction(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Log voice interaction"""
        return ToolResult(
            success=True,
            data={
                "logged": True,
                "command": input_data["command"],
                "success": input_data["success"],
                "timestamp": datetime.now().isoformat()
            },
            message="Voice interaction logged"
        )

    async def _get_voice_history(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get voice history"""
        # Simulated history
        history = [
            {
                "command": "Show my pipeline",
                "response": "Displaying pipeline view",
                "success": True,
                "timestamp": datetime.now().isoformat()
            }
        ]

        return ToolResult(
            success=True,
            data={"history": history, "count": len(history)},
            message=f"Retrieved {len(history)} voice interactions"
        )
