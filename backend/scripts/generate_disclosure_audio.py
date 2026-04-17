"""
Generate the final recording disclosure audio file.
Run this locally (not in sandbox) — requires internet for TTS.

Usage:
  pip install edge-tts pydub
  python generate_disclosure_audio.py

Output: recording-disclosure.wav
Upload to S3 or Telnyx Media API.
"""
import asyncio
import struct
import math
import wave
import subprocess
import os
import tempfile


def generate_beep(filename, freq=850, duration_ms=600, sample_rate=16000, volume=0.35):
    """Professional beep tone — 850Hz, 600ms, smooth fade."""
    n_samples = int(sample_rate * duration_ms / 1000)
    fade_samples = int(sample_rate * 0.03)
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        sample = math.sin(2 * math.pi * freq * t) * volume
        if i < fade_samples:
            sample *= i / fade_samples
        elif i > n_samples - fade_samples:
            sample *= (n_samples - i) / fade_samples
        samples.append(int(sample * 32767))

    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f'<{len(samples)}h', *samples))
    print(f"  Beep: {filename} ({duration_ms}ms, {freq}Hz)")


def generate_silence(filename, duration_ms=400, sample_rate=16000):
    """Generate silence gap between beep and voice."""
    n_samples = int(sample_rate * duration_ms / 1000)
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f'<{n_samples}h', *([0] * n_samples)))
    print(f"  Silence: {filename} ({duration_ms}ms)")


async def generate_tts(filename):
    """Generate the verbal disclosure using Microsoft Edge TTS (free)."""
    import edge_tts

    text = "This call is now being recorded for quality and compliance purposes."

    communicate = edge_tts.Communicate(
        text=text,
        voice="en-US-AriaNeural",  # Professional, clear, neutral
        rate="-5%",
        volume="+0%"
    )
    await communicate.save(filename)
    print(f"  TTS: {filename}")


def combine_audio(beep, silence, tts, output):
    """Combine beep + silence + TTS into final WAV using ffmpeg."""
    # Normalize TTS to 16kHz mono WAV
    tts_wav = tempfile.mktemp(suffix=".wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", tts,
        "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
        tts_wav
    ], capture_output=True, check=True)

    # Concatenate all three
    subprocess.run([
        "ffmpeg", "-y",
        "-i", beep, "-i", silence, "-i", tts_wav,
        "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
        "-map", "[out]",
        "-ar", "16000", "-ac", "1",
        output
    ], capture_output=True, check=True)

    os.unlink(tts_wav)

    with wave.open(output, 'r') as wf:
        duration = wf.getnframes() / wf.getframerate()
        print(f"\n  Final: {output} ({duration:.1f}s, {wf.getframerate()}Hz)")


async def main():
    print("Generating recording disclosure audio...\n")

    beep = "beep.wav"
    silence = "silence.wav"
    tts = "disclosure-tts.mp3"
    output = "recording-disclosure.wav"

    generate_beep(beep)
    generate_silence(silence)
    await generate_tts(tts)
    combine_audio(beep, silence, tts, output)

    for f in [beep, silence, tts]:
        os.unlink(f)

    print(f"\nDone! Upload {output} to:")
    print("  - S3:    aws s3 cp recording-disclosure.wav s3://perennia-assets/audio/")
    print("  - Telnyx: POST https://api.telnyx.com/v2/media")


if __name__ == "__main__":
    asyncio.run(main())
