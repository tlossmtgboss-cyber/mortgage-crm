"""
TeXML Response Generator

TeXML is Telnyx's TwiML-compatible XML format for controlling calls.
This module provides a builder pattern for generating TeXML responses.

TeXML is nearly identical to TwiML, making it straightforward to use.
Reference: https://developers.telnyx.com/docs/voice/programmable-voice/texml
"""

from typing import Optional, List, Union
from xml.etree.ElementTree import Element, SubElement, tostring  # XML building only
import html


class TeXMLResponse:
    """
    Builder for TeXML responses.

    Usage:
        response = TeXMLResponse()
        response.say("Hello, welcome to our service.")
        response.gather(
            input_type="speech dtmf",
            action="/handle-input",
            speech_timeout="auto"
        ).say("Please say or press your selection.")
        return response.to_xml()
    """

    def __init__(self):
        self._root = Element("Response")
        self._current_parent = self._root

    def say(
        self,
        text: str,
        voice: str = "alice",
        language: str = "en-US",
        loop: int = 1,
    ) -> "TeXMLResponse":
        """
        Add a Say verb to speak text.

        Args:
            text: Text to speak
            voice: Voice to use (alice, man, woman, or Polly voices)
            language: Language code (en-US, es-ES, etc.)
            loop: Number of times to repeat (0 = infinite)
        """
        say_elem = SubElement(self._current_parent, "Say")
        say_elem.set("voice", voice)
        say_elem.set("language", language)
        if loop != 1:
            say_elem.set("loop", str(loop))
        say_elem.text = html.escape(text)
        return self

    def play(
        self,
        url: str,
        loop: int = 1,
        digits: str = None,
    ) -> "TeXMLResponse":
        """
        Add a Play verb to play audio.

        Args:
            url: URL of audio file to play
            loop: Number of times to repeat
            digits: DTMF digits to play
        """
        play_elem = SubElement(self._current_parent, "Play")
        if loop != 1:
            play_elem.set("loop", str(loop))
        if digits:
            play_elem.set("digits", digits)
        play_elem.text = url
        return self

    def pause(self, length: int = 1) -> "TeXMLResponse":
        """
        Add a Pause verb.

        Args:
            length: Pause duration in seconds
        """
        pause_elem = SubElement(self._current_parent, "Pause")
        pause_elem.set("length", str(length))
        return self

    def gather(
        self,
        input_type: str = "dtmf",
        action: str = None,
        method: str = "POST",
        timeout: int = 5,
        num_digits: int = None,
        finish_on_key: str = "#",
        speech_timeout: str = "auto",
        speech_model: str = None,
        language: str = "en-US",
        hints: str = None,
        action_on_empty_result: bool = False,
    ) -> "GatherContext":
        """
        Add a Gather verb for collecting input.

        Args:
            input_type: "dtmf", "speech", or "dtmf speech"
            action: URL to send results to
            method: HTTP method (GET or POST)
            timeout: Seconds to wait for input
            num_digits: Maximum digits to collect
            finish_on_key: Key that ends gathering
            speech_timeout: Seconds of silence before ending speech input
            speech_model: ASR model to use
            language: Language for speech recognition
            hints: Hints for speech recognition
            action_on_empty_result: Whether to call action URL if no input

        Returns:
            GatherContext for adding nested verbs
        """
        gather_elem = SubElement(self._current_parent, "Gather")
        gather_elem.set("input", input_type)

        if action:
            gather_elem.set("action", action)
        gather_elem.set("method", method)
        gather_elem.set("timeout", str(timeout))

        if num_digits:
            gather_elem.set("numDigits", str(num_digits))
        if finish_on_key:
            gather_elem.set("finishOnKey", finish_on_key)
        if "speech" in input_type:
            gather_elem.set("speechTimeout", speech_timeout)
            gather_elem.set("language", language)
            if speech_model:
                gather_elem.set("speechModel", speech_model)
            if hints:
                gather_elem.set("hints", hints)
        if action_on_empty_result:
            gather_elem.set("actionOnEmptyResult", "true")

        return GatherContext(self, gather_elem)

    def dial(
        self,
        number: str = None,
        action: str = None,
        method: str = "POST",
        timeout: int = 30,
        caller_id: str = None,
        record: str = None,
        recording_status_callback: str = None,
        ring_tone: str = None,
        answer_on_bridge: bool = False,
    ) -> "DialContext":
        """
        Add a Dial verb to connect to another party.

        Args:
            number: Phone number to dial (can also use nested Number elements)
            action: URL for dial status callback
            method: HTTP method
            timeout: Seconds to wait for answer
            caller_id: Caller ID to display
            record: Recording option (do-not-record, record-from-answer, etc.)
            recording_status_callback: URL for recording events
            ring_tone: Custom ringback tone URL
            answer_on_bridge: Wait for answer before connecting

        Returns:
            DialContext for adding nested elements (Number, Conference, etc.)
        """
        dial_elem = SubElement(self._current_parent, "Dial")

        if action:
            dial_elem.set("action", action)
        dial_elem.set("method", method)
        dial_elem.set("timeout", str(timeout))

        if caller_id:
            dial_elem.set("callerId", caller_id)
        if record:
            dial_elem.set("record", record)
        if recording_status_callback:
            dial_elem.set("recordingStatusCallback", recording_status_callback)
        if ring_tone:
            dial_elem.set("ringTone", ring_tone)
        if answer_on_bridge:
            dial_elem.set("answerOnBridge", "true")

        if number:
            dial_elem.text = number

        return DialContext(self, dial_elem)

    def conference(
        self,
        name: str,
        muted: bool = False,
        beep: str = "true",
        start_conference_on_enter: bool = True,
        end_conference_on_exit: bool = False,
        wait_url: str = None,
        max_participants: int = None,
        record: str = None,
        status_callback: str = None,
        status_callback_event: str = None,
    ) -> "TeXMLResponse":
        """
        Add a Conference verb to join a conference room.

        Args:
            name: Conference room name
            muted: Whether caller joins muted
            beep: Play beep on join/leave (true, false, onEnter, onExit)
            start_conference_on_enter: Start conference when this caller joins
            end_conference_on_exit: End conference when this caller leaves
            wait_url: URL for hold music while waiting
            max_participants: Maximum participants
            record: Recording option
            status_callback: URL for conference events
            status_callback_event: Events to send (start, end, join, leave, etc.)
        """
        # Conference must be inside Dial
        dial_elem = SubElement(self._current_parent, "Dial")
        conf_elem = SubElement(dial_elem, "Conference")

        conf_elem.text = name
        if muted:
            conf_elem.set("muted", "true")
        conf_elem.set("beep", beep)
        conf_elem.set("startConferenceOnEnter", "true" if start_conference_on_enter else "false")
        conf_elem.set("endConferenceOnExit", "true" if end_conference_on_exit else "false")

        if wait_url:
            conf_elem.set("waitUrl", wait_url)
        if max_participants:
            conf_elem.set("maxParticipants", str(max_participants))
        if record:
            conf_elem.set("record", record)
        if status_callback:
            conf_elem.set("statusCallback", status_callback)
        if status_callback_event:
            conf_elem.set("statusCallbackEvent", status_callback_event)

        return self

    def hangup(self) -> "TeXMLResponse":
        """Add a Hangup verb to end the call."""
        SubElement(self._current_parent, "Hangup")
        return self

    def redirect(self, url: str, method: str = "POST") -> "TeXMLResponse":
        """
        Add a Redirect verb to transfer control.

        Args:
            url: URL to fetch new TeXML from
            method: HTTP method
        """
        redirect_elem = SubElement(self._current_parent, "Redirect")
        redirect_elem.set("method", method)
        redirect_elem.text = url
        return self

    def reject(self, reason: str = "rejected") -> "TeXMLResponse":
        """
        Add a Reject verb to reject the call.

        Args:
            reason: Rejection reason (rejected, busy)
        """
        reject_elem = SubElement(self._current_parent, "Reject")
        reject_elem.set("reason", reason)
        return self

    def record(
        self,
        action: str = None,
        method: str = "POST",
        timeout: int = 5,
        finish_on_key: str = "#",
        max_length: int = 3600,
        play_beep: bool = True,
        transcribe: bool = False,
        transcribe_callback: str = None,
        recording_status_callback: str = None,
    ) -> "TeXMLResponse":
        """
        Add a Record verb to record audio.

        Args:
            action: URL to send recording to
            method: HTTP method
            timeout: Seconds of silence to stop recording
            finish_on_key: Key to stop recording
            max_length: Maximum recording length in seconds
            play_beep: Play beep before recording
            transcribe: Enable transcription
            transcribe_callback: URL for transcription results
            recording_status_callback: URL for recording events
        """
        record_elem = SubElement(self._current_parent, "Record")

        if action:
            record_elem.set("action", action)
        record_elem.set("method", method)
        record_elem.set("timeout", str(timeout))
        record_elem.set("finishOnKey", finish_on_key)
        record_elem.set("maxLength", str(max_length))
        record_elem.set("playBeep", "true" if play_beep else "false")

        if transcribe:
            record_elem.set("transcribe", "true")
            if transcribe_callback:
                record_elem.set("transcribeCallback", transcribe_callback)
        if recording_status_callback:
            record_elem.set("recordingStatusCallback", recording_status_callback)

        return self

    def stream(
        self,
        url: str,
        name: str = None,
        track: str = "inbound_track",
        status_callback: str = None,
    ) -> "TeXMLResponse":
        """
        Add a Stream verb for real-time audio streaming (WebSocket).

        Args:
            url: WebSocket URL for audio stream
            name: Stream name for reference
            track: Which track to stream (inbound_track, outbound_track, both_tracks)
            status_callback: URL for stream events
        """
        # Stream can be standalone or inside Connect
        stream_elem = SubElement(self._current_parent, "Stream")
        stream_elem.set("url", url)

        if name:
            stream_elem.set("name", name)
        stream_elem.set("track", track)
        if status_callback:
            stream_elem.set("statusCallback", status_callback)

        return self

    def connect(self) -> "ConnectContext":
        """
        Add a Connect verb for WebSocket streaming.

        Returns:
            ConnectContext for adding Stream elements
        """
        connect_elem = SubElement(self._current_parent, "Connect")
        return ConnectContext(self, connect_elem)

    def to_xml(self) -> str:
        """Generate XML string from the response."""
        return '<?xml version="1.0" encoding="UTF-8"?>' + tostring(
            self._root, encoding="unicode"
        )

    def __str__(self) -> str:
        return self.to_xml()


class GatherContext:
    """Context manager for nested Gather verbs."""

    def __init__(self, response: TeXMLResponse, gather_elem: Element):
        self._response = response
        self._gather_elem = gather_elem
        self._original_parent = response._current_parent
        response._current_parent = gather_elem

    def say(self, text: str, **kwargs) -> "GatherContext":
        """Add Say inside Gather."""
        self._response.say(text, **kwargs)
        return self

    def play(self, url: str, **kwargs) -> "GatherContext":
        """Add Play inside Gather."""
        self._response.play(url, **kwargs)
        return self

    def pause(self, length: int = 1) -> "GatherContext":
        """Add Pause inside Gather."""
        self._response.pause(length)
        return self

    def end_gather(self) -> TeXMLResponse:
        """End the Gather context and return to main response."""
        self._response._current_parent = self._original_parent
        return self._response


class DialContext:
    """Context manager for nested Dial verbs."""

    def __init__(self, response: TeXMLResponse, dial_elem: Element):
        self._response = response
        self._dial_elem = dial_elem
        self._original_parent = response._current_parent

    def number(
        self,
        phone_number: str,
        status_callback: str = None,
        status_callback_event: str = None,
        status_callback_method: str = "POST",
    ) -> "DialContext":
        """
        Add a Number to dial.

        Args:
            phone_number: Phone number in E.164 format
            status_callback: URL for call status events
            status_callback_event: Events to send
            status_callback_method: HTTP method
        """
        number_elem = SubElement(self._dial_elem, "Number")
        number_elem.text = phone_number

        if status_callback:
            number_elem.set("statusCallback", status_callback)
        if status_callback_event:
            number_elem.set("statusCallbackEvent", status_callback_event)
        number_elem.set("statusCallbackMethod", status_callback_method)

        return self

    def sip(
        self,
        sip_uri: str,
        username: str = None,
        password: str = None,
    ) -> "DialContext":
        """
        Add a SIP endpoint to dial.

        Args:
            sip_uri: SIP URI to dial
            username: SIP auth username
            password: SIP auth password
        """
        sip_elem = SubElement(self._dial_elem, "Sip")
        sip_elem.text = sip_uri

        if username:
            sip_elem.set("username", username)
        if password:
            sip_elem.set("password", password)

        return self

    def conference(
        self,
        name: str,
        **kwargs,
    ) -> "DialContext":
        """
        Add a Conference inside Dial.

        Args:
            name: Conference room name
            **kwargs: Conference attributes
        """
        conf_elem = SubElement(self._dial_elem, "Conference")
        conf_elem.text = name

        for key, value in kwargs.items():
            if value is not None:
                # Convert snake_case to camelCase
                attr_name = "".join(
                    word.capitalize() if i > 0 else word
                    for i, word in enumerate(key.split("_"))
                )
                conf_elem.set(attr_name, str(value).lower() if isinstance(value, bool) else str(value))

        return self

    def end_dial(self) -> TeXMLResponse:
        """End the Dial context and return to main response."""
        self._response._current_parent = self._original_parent
        return self._response


class ConnectContext:
    """Context manager for Connect verb (WebSocket streaming)."""

    def __init__(self, response: TeXMLResponse, connect_elem: Element):
        self._response = response
        self._connect_elem = connect_elem
        self._original_parent = response._current_parent
        response._current_parent = connect_elem

    def stream(
        self,
        url: str,
        name: str = None,
        track: str = "inbound_track",
        status_callback: str = None,
    ) -> "ConnectContext":
        """Add a Stream inside Connect."""
        self._response.stream(url, name, track, status_callback)
        return self

    def end_connect(self) -> TeXMLResponse:
        """End the Connect context and return to main response."""
        self._response._current_parent = self._original_parent
        return self._response


# Helper functions for common patterns

def say_and_hangup(text: str, voice: str = "alice") -> str:
    """Generate TeXML to say a message and hang up."""
    return TeXMLResponse().say(text, voice=voice).hangup().to_xml()


def play_and_hangup(url: str) -> str:
    """Generate TeXML to play audio and hang up."""
    return TeXMLResponse().play(url).hangup().to_xml()


def redirect_to(url: str) -> str:
    """Generate TeXML to redirect to another URL."""
    return TeXMLResponse().redirect(url).to_xml()


def connect_to_conference(
    room_name: str,
    wait_music_url: str = None,
    end_on_exit: bool = False,
) -> str:
    """Generate TeXML to join a conference room."""
    return (
        TeXMLResponse()
        .conference(
            room_name,
            wait_url=wait_music_url,
            end_conference_on_exit=end_on_exit,
        )
        .to_xml()
    )


def connect_to_websocket(
    ws_url: str,
    track: str = "both_tracks",
) -> str:
    """Generate TeXML to connect audio to a WebSocket."""
    return (
        TeXMLResponse()
        .connect()
        .stream(ws_url, track=track)
        .end_connect()
        .to_xml()
    )
