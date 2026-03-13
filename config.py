# config.py
import os

class Config:
    MAX_CHARS = 4000
    GROQ_MODEL = "llama-3.3-70b-versatile"
    LOG_LEVEL = "INFO"
    PRIVATE_MODE = True  # Avoid storing sensitive logs by default

    # Transcription Settings
    # Options: "local" (faster-whisper), "groq" (cloud api)
    TRANSCRIPTION_PROVIDER = os.getenv("TRANSCRIPTION_PROVIDER", "groq") # Default to groq for better accuracy
    GROQ_STT_MODEL = "whisper-large-v3"

    # Toggle to enable/disable specific features if needed
    ENABLE_OCR_FALLBACK = False

config = Config()
