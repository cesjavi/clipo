import sys
import logging
import colorama
from colorama import Fore, Style

# Import modules
from config import config
from window_context import get_active_window_info, extract_text_uia
from text_cleaner import build_context
from groq_client import groq_client

# Configure logging
logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)

colorama.init(autoreset=True)

SYSTEM_PROMPT = """
You are a senior Windows 10 automation engineer assisting the user.
Your context is the text content of the currently active window.
Do not invent information not present in the context.
Provide concrete and actionable answers.
"""

USER_TEMPLATE = """
CONTEXT (Active Window):
{context}

QUESTION:
{question}
"""

MINI_PROMPT_WARNING = """
IMPORTANT Win10:
The extracted text is very short (< 200 chars). This might be a Chrome/Electron app that hides UIA text.
If the text is insufficient, suggest a fallback (but do not use OCR unless asked).
"""

def capture_context():
    """Captures and cleans context from active window."""
    try:
        info = get_active_window_info()
    except Exception as e:
        logger.error(f"Error getting window info: {e}")
        info = None

    if not info:
        return {"info": None, "text": "No active window found."}

    print(f"Active Window: {info.get('title', 'Unknown')} ({info.get('process_name', 'Unknown')})")

    try:
        raw_text = extract_text_uia(info['hwnd'])
    except Exception as e:
        logger.error(f"Error extracting text: {e}")
        raw_text = ""

    cleaned_text = build_context(info, raw_text, max_chars=config.MAX_CHARS)

    return {"info": info, "text": cleaned_text}

def main():
    print(Fore.CYAN + "=== Windows 10 Automation Assistant ===")
    print(Fore.YELLOW + "Commands: :refresh (force recapture), :quit (exit)")

    # Check for API Key
    if not groq_client.client:
        print(Fore.RED + "Error: GROQ_API_KEY not set. Please set it and restart.")
        return

    while True:
        try:
            user_input = input(Fore.GREEN + "\nUser > " + Style.RESET_ALL).strip()
        except EOFError:
            break

        if not user_input:
            continue

        if user_input.lower() in [":quit", ":exit"]:
            print(Fore.CYAN + "Exiting...")
            break

        if user_input.lower() == ":refresh":
            print(Fore.YELLOW + "Refreshing active window context (simulated)...")
            # In interactive mode, refresh usually updates the cache,
            # but since we capture every time, this is just a manual check.
            data = capture_context()
            print(Fore.GREEN + "Context captured.")
            continue

        # Default behavior: recapture context before each question
        print(Fore.YELLOW + "Capturing active window context...")
        context_data = capture_context()

        # Construct prompt
        context_str = context_data['text']

        # Check for short text warning (heuristic for bad UIA support)
        # We only check length of the cleaned text minus header roughly,
        # or just total length if it's very short.
        warning_msg = ""
        if len(context_str) < 300: # Context includes header, so 300 is a safe low bound
            warning_msg = MINI_PROMPT_WARNING

        final_user_msg = USER_TEMPLATE.format(context=context_str, question=user_input)
        if warning_msg:
            final_user_msg += "\n" + warning_msg

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": final_user_msg}
        ]

        print(Fore.BLUE + "Sending to Groq...")
        response = groq_client.ask_groq(messages, model=config.GROQ_MODEL)

        print(Fore.MAGENTA + "\nAssistant > " + Style.RESET_ALL + response)

if __name__ == "__main__":
    main()
