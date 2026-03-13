import logging
import os
import sys
import tempfile
import wave
from config import config
from groq_client import groq_client

logger = logging.getLogger(__name__)

try:
    import numpy as np
    import sounddevice as sd
    from faster_whisper import WhisperModel
except ImportError:
    np = None
    sd = None
    WhisperModel = None


SAMPLE_RATE = 16000
CHANNELS = 1
DEFAULT_MODEL_SIZE = "tiny"
DEFAULT_COMPUTE_TYPE = "int8"
CHUNK_DURATION_SECONDS = 0.25
SILENCE_THRESHOLD = 0.015
MIN_SPEECH_SECONDS = 0.35
MAX_SILENCE_SECONDS = 1.0

_MODEL = None


def _get_model():
    global _MODEL

    if WhisperModel is None:
        raise RuntimeError(
            f"faster-whisper is not available in {sys.executable}. Install faster-whisper and sounddevice in that interpreter."
        )

    if _MODEL is None:
        model_size = os.getenv("CLIPO_WHISPER_MODEL", DEFAULT_MODEL_SIZE)
        compute_type = os.getenv("CLIPO_WHISPER_COMPUTE_TYPE", DEFAULT_COMPUTE_TYPE)
        _MODEL = WhisperModel(model_size, compute_type=compute_type)
    return _MODEL


def _record_audio(duration_seconds):
    if sd is None or np is None:
        raise RuntimeError(
            f"sounddevice is not available in {sys.executable}. Install sounddevice in that interpreter to capture microphone audio."
        )

    frame_count = int(duration_seconds * SAMPLE_RATE)
    recording = sd.rec(
        frame_count,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
    )
    sd.wait()
    audio = np.squeeze(recording)
    if audio.size == 0:
        raise RuntimeError("No microphone audio was captured.")
    return audio


def _record_until_silence(max_duration_seconds):
    if sd is None or np is None:
        raise RuntimeError(
            f"sounddevice is not available in {sys.executable}. Install sounddevice in that interpreter to capture microphone audio."
        )

    if max_duration_seconds <= 0:
        raise ValueError("max_duration_seconds must be greater than zero.")

    chunk_frames = max(1, int(CHUNK_DURATION_SECONDS * SAMPLE_RATE))
    min_speech_chunks = max(1, int(MIN_SPEECH_SECONDS / CHUNK_DURATION_SECONDS))
    max_silence_chunks = max(1, int(MAX_SILENCE_SECONDS / CHUNK_DURATION_SECONDS))
    max_chunks = max(1, int(max_duration_seconds / CHUNK_DURATION_SECONDS))

    chunks = []
    speech_chunks = 0
    silent_after_speech = 0
    heard_speech = False

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=chunk_frames,
    ) as stream:
        for _ in range(max_chunks):
            data, _overflowed = stream.read(chunk_frames)
            chunk = np.squeeze(data.copy())
            if chunk.size == 0:
                continue

            chunks.append(chunk)
            level = float(np.sqrt(np.mean(np.square(chunk))))

            if level >= SILENCE_THRESHOLD:
                speech_chunks += 1
                silent_after_speech = 0
                if speech_chunks >= min_speech_chunks:
                    heard_speech = True
            elif heard_speech:
                silent_after_speech += 1
                if silent_after_speech >= max_silence_chunks:
                    break

    if not chunks:
        raise RuntimeError("No microphone audio was captured.")

    audio = np.concatenate(chunks)
    if audio.size == 0:
        raise RuntimeError("No microphone audio was captured.")
    if not heard_speech:
        raise RuntimeError("No speech was detected.")
    return audio


def _save_temp_wav(audio):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        temp_path = temp_file.name

    pcm_audio = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    with wave.open(temp_path, "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm_audio.tobytes())
    return temp_path


def _strip_wake_phrase(text):
    normalized = " ".join((text or "").strip().split())
    lowered = normalized.lower()
    wake_phrases = (
        "clipo hacer ",
        "clipo hace ",
        "clipo ",
    )
    for phrase in wake_phrases:
        if lowered.startswith(phrase):
            return normalized[len(phrase):].strip()
    return normalized


def recognize_once(timeout_seconds=10):
    """
    Records from the default microphone and transcribes once using faster-whisper.
    Recording stops early after speech is followed by silence.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero.")

    audio = _record_until_silence(timeout_seconds)
    temp_path = _save_temp_wav(audio)

    try:
        if config.TRANSCRIPTION_PROVIDER == "groq":
            text = groq_client.transcribe_audio(temp_path, model=config.GROQ_STT_MODEL)
        else:
            model = _get_model()
            segments, _info = model.transcribe(
                temp_path,
                language="es",
                vad_filter=True,
                beam_size=5,
            )
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        
        text = _strip_wake_phrase(text)
        if not text:
            raise RuntimeError("No speech was recognized.")
        return text
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            logger.debug("Could not remove temporary audio file.", exc_info=True)
