"""
Voice AI Co-Presenter Pipeline
STT (Deepgram) → LLM (Claude) → TTS (ElevenLabs)
"""

import os
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

import httpx
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)


class AIMode(str, Enum):
    PASSIVE = "passive"
    COPILOT = "copilot"
    PRESENTER = "presenter"


class SpeechEventType(str, Enum):
    TRANSCRIPT_PARTIAL = "transcript_partial"
    TRANSCRIPT_FINAL = "transcript_final"
    AI_RESPONSE_START = "ai_response_start"
    AI_RESPONSE_CHUNK = "ai_response_chunk"
    AI_RESPONSE_END = "ai_response_end"
    TTS_AUDIO_CHUNK = "tts_audio_chunk"
    TTS_AUDIO_END = "tts_audio_end"
    ERROR = "error"


@dataclass
class PipelineConfig:
    """Configuration for the voice pipeline."""
    deepgram_api_key: str = field(default_factory=lambda: os.getenv("DEEPGRAM_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    elevenlabs_api_key: str = field(default_factory=lambda: os.getenv("ELEVENLABS_API_KEY", ""))

    # Deepgram settings
    stt_model: str = "nova-2"
    stt_language: str = "en-US"
    stt_punctuate: bool = True
    stt_diarize: bool = True
    stt_smart_format: bool = True

    # Claude settings
    llm_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 1024
    llm_temperature: float = 0.7

    # ElevenLabs settings
    tts_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice
    tts_model_id: str = "eleven_turbo_v2"
    tts_stability: float = 0.5
    tts_similarity_boost: float = 0.75
    tts_output_format: str = "mp3_44100_128"


@dataclass
class ConversationContext:
    """Maintains conversation state and context."""
    call_session_id: str
    client_id: Optional[str] = None
    borrower_name: Optional[str] = None
    loan_officer_name: Optional[str] = None
    current_tab: str = "process"
    loan_context: Dict[str, Any] = field(default_factory=dict)
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    playbook_chunks: List[Dict[str, Any]] = field(default_factory=list)
    ai_mode: AIMode = AIMode.COPILOT
    is_muted: bool = False
    is_speaking: bool = False


class DeepgramSTT:
    """Deepgram Speech-to-Text integration."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.ws_url = "wss://api.deepgram.com/v1/listen"

    async def create_stream(self, on_transcript: Callable[[str, bool], None]) -> Any:
        """Create a streaming STT connection."""
        import websockets

        params = {
            "model": self.config.stt_model,
            "language": self.config.stt_language,
            "punctuate": str(self.config.stt_punctuate).lower(),
            "diarize": str(self.config.stt_diarize).lower(),
            "smart_format": str(self.config.stt_smart_format).lower(),
            "encoding": "linear16",
            "sample_rate": "16000",
            "channels": "1"
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.ws_url}?{query_string}"

        headers = {
            "Authorization": f"Token {self.config.deepgram_api_key}"
        }

        async def message_handler(websocket):
            async for message in websocket:
                data = json.loads(message)
                if data.get("type") == "Results":
                    channel = data.get("channel", {})
                    alternatives = channel.get("alternatives", [])
                    if alternatives:
                        transcript = alternatives[0].get("transcript", "")
                        is_final = data.get("is_final", False)
                        if transcript:
                            await on_transcript(transcript, is_final)

        ws = await websockets.connect(url, extra_headers=headers)
        asyncio.create_task(message_handler(ws))
        return ws

    async def transcribe_file(self, audio_data: bytes) -> str:
        """Transcribe audio file."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.deepgram.com/v1/listen",
                headers={
                    "Authorization": f"Token {self.config.deepgram_api_key}",
                    "Content-Type": "audio/wav"
                },
                params={
                    "model": self.config.stt_model,
                    "language": self.config.stt_language,
                    "punctuate": "true",
                    "smart_format": "true"
                },
                content=audio_data
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
            else:
                logger.error(f"Deepgram error: {response.text}")
                return ""


class ClaudeLLM:
    """Claude LLM integration for mortgage consultation."""

    SYSTEM_PROMPT = """You are an AI co-presenter assisting a loan officer during a video consultation with a borrower. Your role is to:

1. Explain mortgage concepts clearly and professionally
2. Answer borrower questions accurately
3. Present rate options and scenarios objectively
4. Guide the conversation through the loan process
5. Maintain a warm, professional tone

Current Context:
- Borrower: {borrower_name}
- Loan Officer: {loan_officer_name}
- Current Tab: {current_tab}
- Loan Details: {loan_context}

Available Playbook Knowledge:
{playbook_context}

Guidelines:
- Keep responses concise (2-3 sentences max for verbal delivery)
- Use simple language, avoid jargon unless explaining it
- Always be accurate with numbers and rates
- If unsure, say so and defer to the loan officer
- Reference specific numbers from the loan context when relevant"""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.client = AsyncAnthropic(api_key=config.anthropic_api_key)

    def _build_system_prompt(self, context: ConversationContext) -> str:
        """Build system prompt with current context."""
        playbook_text = "\n".join([
            f"- {chunk.get('topic', 'General')}: {chunk.get('content', '')[:200]}..."
            for chunk in context.playbook_chunks[:5]
        ]) or "No specific playbook loaded."

        return self.SYSTEM_PROMPT.format(
            borrower_name=context.borrower_name or "the borrower",
            loan_officer_name=context.loan_officer_name or "the loan officer",
            current_tab=context.current_tab,
            loan_context=json.dumps(context.loan_context, indent=2)[:500],
            playbook_context=playbook_text
        )

    async def generate_response(
        self,
        user_message: str,
        context: ConversationContext,
        stream: bool = True
    ) -> str:
        """Generate AI response based on conversation context."""

        messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in context.conversation_history[-10:]  # Last 10 messages
        ]
        messages.append({"role": "user", "content": user_message})

        if stream:
            full_response = ""
            async with self.client.messages.stream(
                model=self.config.llm_model,
                max_tokens=self.config.llm_max_tokens,
                temperature=self.config.llm_temperature,
                system=self._build_system_prompt(context),
                messages=messages
            ) as stream:
                async for text in stream.text_stream:
                    full_response += text
                    yield text

            # Update conversation history
            context.conversation_history.append({"role": "user", "content": user_message})
            context.conversation_history.append({"role": "assistant", "content": full_response})
        else:
            response = await self.client.messages.create(
                model=self.config.llm_model,
                max_tokens=self.config.llm_max_tokens,
                temperature=self.config.llm_temperature,
                system=self._build_system_prompt(context),
                messages=messages
            )

            full_response = response.content[0].text
            context.conversation_history.append({"role": "user", "content": user_message})
            context.conversation_history.append({"role": "assistant", "content": full_response})
            yield full_response

    async def generate_tab_explanation(
        self,
        tab_name: str,
        tab_data: Dict[str, Any],
        context: ConversationContext
    ) -> str:
        """Generate explanation for current tab content."""

        prompt = f"""Please provide a brief, natural explanation of the {tab_name} tab content for the borrower.

Tab Data:
{json.dumps(tab_data, indent=2)[:1000]}

Keep the explanation:
- Conversational and warm
- Under 3 sentences
- Focused on what matters most to the borrower
- Reference specific numbers when relevant"""

        response = await self.client.messages.create(
            model=self.config.llm_model,
            max_tokens=256,
            temperature=0.7,
            system=self._build_system_prompt(context),
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text


class ElevenLabsTTS:
    """ElevenLabs Text-to-Speech integration."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.base_url = "https://api.elevenlabs.io/v1"

    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to speech."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/text-to-speech/{self.config.tts_voice_id}",
                headers={
                    "xi-api-key": self.config.elevenlabs_api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "text": text,
                    "model_id": self.config.tts_model_id,
                    "voice_settings": {
                        "stability": self.config.tts_stability,
                        "similarity_boost": self.config.tts_similarity_boost
                    }
                },
                params={
                    "output_format": self.config.tts_output_format
                }
            )

            if response.status_code == 200:
                return response.content
            else:
                logger.error(f"ElevenLabs error: {response.text}")
                return b""

    async def synthesize_stream(self, text: str) -> Any:
        """Synthesize text to speech with streaming."""
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/text-to-speech/{self.config.tts_voice_id}/stream",
                headers={
                    "xi-api-key": self.config.elevenlabs_api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "text": text,
                    "model_id": self.config.tts_model_id,
                    "voice_settings": {
                        "stability": self.config.tts_stability,
                        "similarity_boost": self.config.tts_similarity_boost
                    }
                },
                params={
                    "output_format": self.config.tts_output_format
                }
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk


class VoiceCopresenterPipeline:
    """Main orchestrator for the voice co-presenter pipeline."""

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.stt = DeepgramSTT(self.config)
        self.llm = ClaudeLLM(self.config)
        self.tts = ElevenLabsTTS(self.config)
        self.contexts: Dict[str, ConversationContext] = {}
        self.event_handlers: Dict[str, List[Callable]] = {}

    def get_or_create_context(
        self,
        call_session_id: str,
        **kwargs
    ) -> ConversationContext:
        """Get or create conversation context for a call session."""
        if call_session_id not in self.contexts:
            self.contexts[call_session_id] = ConversationContext(
                call_session_id=call_session_id,
                **kwargs
            )
        return self.contexts[call_session_id]

    def on(self, event_type: SpeechEventType, handler: Callable):
        """Register event handler."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)

    async def _emit(self, event_type: SpeechEventType, data: Dict[str, Any]):
        """Emit event to handlers."""
        handlers = self.event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Error in event handler: {e}")

    async def process_audio_stream(
        self,
        call_session_id: str,
        audio_stream: Any
    ):
        """Process incoming audio stream through STT → LLM → TTS pipeline."""
        context = self.get_or_create_context(call_session_id)

        async def on_transcript(text: str, is_final: bool):
            await self._emit(
                SpeechEventType.TRANSCRIPT_PARTIAL if not is_final else SpeechEventType.TRANSCRIPT_FINAL,
                {"call_session_id": call_session_id, "text": text, "is_final": is_final}
            )

            if is_final and context.ai_mode != AIMode.PASSIVE and not context.is_muted:
                await self.generate_and_speak(call_session_id, text)

        stt_stream = await self.stt.create_stream(on_transcript)

        try:
            async for chunk in audio_stream:
                await stt_stream.send(chunk)
        finally:
            await stt_stream.close()

    async def generate_and_speak(
        self,
        call_session_id: str,
        user_message: str,
        require_approval: bool = None
    ):
        """Generate AI response and speak it."""
        context = self.get_or_create_context(call_session_id)

        if context.is_muted:
            return

        # Determine if approval is needed
        if require_approval is None:
            require_approval = context.ai_mode == AIMode.COPILOT

        await self._emit(SpeechEventType.AI_RESPONSE_START, {
            "call_session_id": call_session_id,
            "require_approval": require_approval
        })

        full_response = ""
        async for chunk in self.llm.generate_response(user_message, context):
            full_response += chunk
            await self._emit(SpeechEventType.AI_RESPONSE_CHUNK, {
                "call_session_id": call_session_id,
                "chunk": chunk
            })

        await self._emit(SpeechEventType.AI_RESPONSE_END, {
            "call_session_id": call_session_id,
            "full_response": full_response,
            "require_approval": require_approval
        })

        # If approval not needed or already approved, speak
        if not require_approval:
            await self.speak_text(call_session_id, full_response)

    async def speak_text(self, call_session_id: str, text: str):
        """Convert text to speech and emit audio events."""
        context = self.get_or_create_context(call_session_id)

        if context.is_muted:
            return

        context.is_speaking = True

        try:
            async for audio_chunk in self.tts.synthesize_stream(text):
                await self._emit(SpeechEventType.TTS_AUDIO_CHUNK, {
                    "call_session_id": call_session_id,
                    "audio": audio_chunk
                })

            await self._emit(SpeechEventType.TTS_AUDIO_END, {
                "call_session_id": call_session_id
            })
        finally:
            context.is_speaking = False

    async def explain_tab(
        self,
        call_session_id: str,
        tab_name: str,
        tab_data: Dict[str, Any]
    ):
        """Generate and speak explanation for a tab."""
        context = self.get_or_create_context(call_session_id)

        explanation = await self.llm.generate_tab_explanation(tab_name, tab_data, context)

        if context.ai_mode == AIMode.COPILOT:
            # Return for approval
            await self._emit(SpeechEventType.AI_RESPONSE_END, {
                "call_session_id": call_session_id,
                "full_response": explanation,
                "require_approval": True,
                "action_type": "explain_tab",
                "tab_name": tab_name
            })
        else:
            # Speak directly
            await self.speak_text(call_session_id, explanation)

    def set_mode(self, call_session_id: str, mode: AIMode):
        """Set AI mode for a call session."""
        context = self.get_or_create_context(call_session_id)
        context.ai_mode = mode

    def set_muted(self, call_session_id: str, muted: bool):
        """Set mute state for a call session."""
        context = self.get_or_create_context(call_session_id)
        context.is_muted = muted

    def update_context(
        self,
        call_session_id: str,
        current_tab: Optional[str] = None,
        loan_context: Optional[Dict[str, Any]] = None,
        playbook_chunks: Optional[List[Dict[str, Any]]] = None
    ):
        """Update conversation context."""
        context = self.get_or_create_context(call_session_id)

        if current_tab:
            context.current_tab = current_tab
        if loan_context:
            context.loan_context.update(loan_context)
        if playbook_chunks:
            context.playbook_chunks = playbook_chunks

    def cleanup_session(self, call_session_id: str):
        """Clean up session context."""
        if call_session_id in self.contexts:
            del self.contexts[call_session_id]


# Global pipeline instance
_pipeline_instance: Optional[VoiceCopresenterPipeline] = None


def get_pipeline() -> VoiceCopresenterPipeline:
    """Get or create the global pipeline instance."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = VoiceCopresenterPipeline()
    return _pipeline_instance
