"""Google Cloud Text-to-Speech Service Integration

Provides text-to-speech functionality using Google Cloud TTS API.
Supports multiple voices and languages with high-quality speech synthesis.
"""

import os
import logging
from typing import Optional, Dict, Any
from google.cloud import texttospeech
import base64

logger = logging.getLogger(__name__)


class GoogleTTSService:
    """Service for Google Cloud Text-to-Speech API integration"""
    
    def __init__(self):
        """Initialize the Google TTS client"""
        try:
            # Client will use GOOGLE_APPLICATION_CREDENTIALS env variable
            self.client = texttospeech.TextToSpeechClient()
            logger.info("Google TTS client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Google TTS client: {e}")
            raise
    
    def synthesize_speech(
        self,
        text: str,
        language_code: str = "en-US",
        voice_name: Optional[str] = None,
        ssml_gender: str = "NEUTRAL",
        audio_encoding: str = "MP3",
        speaking_rate: float = 1.0,
        pitch: float = 0.0
    ) -> Optional[bytes]:
        """
        Convert text to speech using Google Cloud TTS
        
        Args:
            text: Text to convert to speech
            language_code: Language code (e.g., "en-US", "en-GB")
            voice_name: Specific voice name (e.g., "en-US-Neural2-C")
            ssml_gender: Voice gender (NEUTRAL, FEMALE, MALE)
            audio_encoding: Audio format (MP3, LINEAR16, OGG_OPUS)
            speaking_rate: Speech speed (0.25 to 4.0, default 1.0)
            pitch: Speech pitch (-20.0 to 20.0, default 0.0)
            
        Returns:
            Audio content as bytes, or None if error
        """
        try:
            # Set the text input
            synthesis_input = texttospeech.SynthesisInput(text=text)
            
            # Build the voice request
            voice_params = {
                "language_code": language_code,
            }
            
            # Add specific voice name if provided
            if voice_name:
                voice_params["name"] = voice_name
            else:
                # Map gender string to enum
                gender_map = {
                    "NEUTRAL": texttospeech.SsmlVoiceGender.NEUTRAL,
                    "FEMALE": texttospeech.SsmlVoiceGender.FEMALE,
                    "MALE": texttospeech.SsmlVoiceGender.MALE,
                }
                voice_params["ssml_gender"] = gender_map.get(
                    ssml_gender.upper(), 
                    texttospeech.SsmlVoiceGender.NEUTRAL
                )
            
            voice = texttospeech.VoiceSelectionParams(**voice_params)
            
            # Select the audio file type
            encoding_map = {
                "MP3": texttospeech.AudioEncoding.MP3,
                "LINEAR16": texttospeech.AudioEncoding.LINEAR16,
                "OGG_OPUS": texttospeech.AudioEncoding.OGG_OPUS,
            }
            
            audio_config = texttospeech.AudioConfig(
                audio_encoding=encoding_map.get(
                    audio_encoding.upper(),
                    texttospeech.AudioEncoding.MP3
                ),
                speaking_rate=speaking_rate,
                pitch=pitch
            )
            
            # Perform the text-to-speech request
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            
            logger.info(f"Successfully synthesized speech for text length: {len(text)}")
            return response.audio_content
            
        except Exception as e:
            logger.error(f"Error synthesizing speech: {e}")
            return None
    
    def synthesize_ssml(
        self,
        ssml: str,
        language_code: str = "en-US",
        voice_name: Optional[str] = None,
        audio_encoding: str = "MP3"
    ) -> Optional[bytes]:
        """
        Convert SSML to speech
        
        Args:
            ssml: SSML markup text
            language_code: Language code
            voice_name: Specific voice name
            audio_encoding: Audio format
            
        Returns:
            Audio content as bytes, or None if error
        """
        try:
            synthesis_input = texttospeech.SynthesisInput(ssml=ssml)
            
            voice_params = {"language_code": language_code}
            if voice_name:
                voice_params["name"] = voice_name
            
            voice = texttospeech.VoiceSelectionParams(**voice_params)
            
            encoding_map = {
                "MP3": texttospeech.AudioEncoding.MP3,
                "LINEAR16": texttospeech.AudioEncoding.LINEAR16,
                "OGG_OPUS": texttospeech.AudioEncoding.OGG_OPUS,
            }
            
            audio_config = texttospeech.AudioConfig(
                audio_encoding=encoding_map.get(
                    audio_encoding.upper(),
                    texttospeech.AudioEncoding.MP3
                )
            )
            
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            
            logger.info("Successfully synthesized SSML")
            return response.audio_content
            
        except Exception as e:
            logger.error(f"Error synthesizing SSML: {e}")
            return None
    
    def list_voices(self, language_code: Optional[str] = None) -> list:
        """
        List available voices
        
        Args:
            language_code: Optional language code to filter voices
            
        Returns:
            List of available voices
        """
        try:
            response = self.client.list_voices(language_code=language_code)
            voices = []
            for voice in response.voices:
                voices.append({
                    "name": voice.name,
                    "language_codes": voice.language_codes,
                    "ssml_gender": texttospeech.SsmlVoiceGender(voice.ssml_gender).name,
                    "natural_sample_rate_hertz": voice.natural_sample_rate_hertz
                })
            return voices
        except Exception as e:
            logger.error(f"Error listing voices: {e}")
            return []
    
    def synthesize_to_base64(
        self,
        text: str,
        **kwargs
    ) -> Optional[str]:
        """
        Synthesize speech and return as base64 string
        
        Args:
            text: Text to convert
            **kwargs: Additional arguments for synthesize_speech
            
        Returns:
            Base64 encoded audio string, or None if error
        """
        audio_content = self.synthesize_speech(text, **kwargs)
        if audio_content:
            return base64.b64encode(audio_content).decode('utf-8')
        return None


# Singleton instance
_tts_service = None


def get_tts_service() -> GoogleTTSService:
    """Get or create the TTS service instance"""
    global _tts_service
    if _tts_service is None:
        _tts_service = GoogleTTSService()
    return _tts_service
