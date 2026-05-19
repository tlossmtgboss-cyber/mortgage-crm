"""
VoiceFormattingMixin — response formatting helpers used when delivering
streamed/voice output (smooth chunking, etc.).

Extracted from the original monolithic AIAgentService (Wave 3 decomposition).
Mechanical method-move only; bodies and signatures are unchanged.

Note: the module-level helper `_summarize_tool_result_for_voice` and the
`VOICE_MODE_INSTRUCTIONS` constant remain at the top of the package's
__init__.py because they are referenced directly by ResponseGenerationMixin.
"""

from typing import List


class VoiceFormattingMixin:
    """Voice-mode and stream-friendly response formatting."""

    def _split_response_for_streaming(self, text: str) -> List[str]:
        """Split response text into chunks for smooth streaming."""
        chunks = []

        # First try to split by paragraphs
        paragraphs = text.split('\n\n')

        for para in paragraphs:
            if len(para) > 200:
                # Split long paragraphs by sentences
                sentences = para.replace('. ', '.|').split('|')
                for sentence in sentences:
                    if sentence.strip():
                        chunks.append(sentence + ' ')
            else:
                chunks.append(para + '\n\n')

        return chunks
