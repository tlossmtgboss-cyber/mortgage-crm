import React, { useState, useEffect, useRef } from 'react';
import './VoiceInput.css';

const VoiceInput = ({ onTranscriptChange, onSend, placeholder = "Type or speak your message..." }) => {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [isSupported, setIsSupported] = useState(true);
  const recognitionRef = useRef(null);

  useEffect(() => {
    // Check if browser supports Speech Recognition
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setIsSupported(false);
      console.warn('Speech Recognition not supported in this browser');
      return;
    }

    // Initialize Speech Recognition
    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      console.log('Voice recognition started');
      setIsListening(true);
    };

    recognition.onresult = (event) => {
      let interimText = '';
      let finalText = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcriptPiece = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalText += transcriptPiece + ' ';
        } else {
          interimText += transcriptPiece;
        }
      }

      if (finalText) {
        const newTranscript = transcript + finalText;
        setTranscript(newTranscript);
        setInterimTranscript('');
        if (onTranscriptChange) {
          onTranscriptChange(newTranscript);
        }
      } else {
        setInterimTranscript(interimText);
      }
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);

      if (event.error === 'not-allowed') {
        alert('Microphone access denied. Please allow microphone access in your browser settings.');
      }
    };

    recognition.onend = () => {
      console.log('Voice recognition ended');
      setIsListening(false);
    };

    recognitionRef.current = recognition;

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, [transcript, onTranscriptChange]);

  const toggleListening = () => {
    if (!recognitionRef.current) return;

    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      try {
        recognitionRef.current.start();
        setIsListening(true);
      } catch (error) {
        console.error('Error starting recognition:', error);
      }
    }
  };

  const handleTextChange = (e) => {
    const newTranscript = e.target.value;
    setTranscript(newTranscript);
    if (onTranscriptChange) {
      onTranscriptChange(newTranscript);
    }
  };

  const handleSend = () => {
    const finalTranscript = transcript.trim();
    if (!finalTranscript) return;

    if (onSend) {
      onSend(finalTranscript);
    }

    // Clear transcript after sending
    setTranscript('');
    setInterimTranscript('');
    if (onTranscriptChange) {
      onTranscriptChange('');
    }

    // Stop listening after sending
    if (isListening && recognitionRef.current) {
      recognitionRef.current.stop();
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const displayText = transcript + (interimTranscript ? ' ' + interimTranscript : '');

  return (
    <div className="voice-input-container">
      <div className="voice-input-box">
        <textarea
          className="voice-input-textarea"
          value={displayText}
          onChange={handleTextChange}
          onKeyPress={handleKeyPress}
          placeholder={placeholder}
          rows="3"
        />
        {interimTranscript && (
          <div className="interim-indicator">
            <span className="listening-dots">●●●</span> Listening...
          </div>
        )}
      </div>

      <div className="voice-input-controls">
        {isSupported ? (
          <button
            className={`voice-btn ${isListening ? 'listening' : ''}`}
            onClick={toggleListening}
            title={isListening ? 'Stop recording' : 'Start voice input'}
          >
            {isListening ? (
              <>
                <span className="mic-icon recording">🎙️</span>
                <span className="voice-status">Recording...</span>
              </>
            ) : (
              <>
                <span className="mic-icon">🎤</span>
                <span className="voice-status">Voice Input</span>
              </>
            )}
          </button>
        ) : (
          <div className="voice-not-supported">
            <span>🎤</span>
            <span className="not-supported-text">Voice not supported in this browser</span>
          </div>
        )}

        <button
          className="send-btn"
          onClick={handleSend}
          disabled={!transcript.trim()}
        >
          <span className="send-icon">📤</span>
          <span>Send</span>
        </button>
      </div>

      {isListening && (
        <div className="listening-hint">
          Speak now... Press the microphone button again to stop
        </div>
      )}
    </div>
  );
};

export default VoiceInput;
