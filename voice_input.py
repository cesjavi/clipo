import logging
import os
import sys
import tempfile
import wave

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


def recognize_once(timeout_seconds=10):
    """
    Records from the default microphone and transcribes once using faster-whisper.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero.")

    audio = _record_audio(timeout_seconds)
    temp_path = _save_temp_wav(audio)

    try:
        model = _get_model()
        segments, _info = model.transcribe(
            temp_path,
            language="es",
            vad_filter=True,
            beam_size=5,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        if not text:
            raise RuntimeError("No speech was recognized.")
        return text
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            logger.debug("Could not remove temporary audio file.", exc_info=True)
