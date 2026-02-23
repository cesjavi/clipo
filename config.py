# config.py

class Config:
    MAX_CHARS = 4000
    GROQ_MODEL = "llama-3.1-70b-versatile"
    LOG_LEVEL = "INFO"
    PRIVATE_MODE = True  # Avoid storing sensitive logs by default

    # Toggle to enable/disable specific features if needed
    ENABLE_OCR_FALLBACK = False

config = Config()
