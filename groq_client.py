import os
import time
import logging
from groq import Groq, APIConnectionError, RateLimitError, APIStatusError

# Configure logger
logger = logging.getLogger(__name__)

class GroqClient:
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            logger.warning("GROQ_API_KEY not found in environment variables.")

        try:
            self.client = Groq(api_key=self.api_key)
        except Exception as e:
            logger.error(f"Failed to initialize Groq client: {e}")
            self.client = None

    def ask_groq(self, messages, model="llama-3.1-70b-versatile", retries=2, timeout=30):
        """
        Sends a chat completion request to Groq API.

        Args:
            messages (list): List of message dicts (role, content).
            model (str): Model name.
            retries (int): Number of retries.
            timeout (int): Timeout in seconds.

        Returns:
            str: The response content.
        """
        if not self.client:
            return "Error: Groq client not initialized (missing API key?)."

        for attempt in range(retries + 1):
            try:
                # Log attempt (avoid logging full content)
                logger.info(f"Sending request to Groq (model={model}, attempt={attempt+1})")

                completion = self.client.chat.completions.create(
                    messages=messages,
                    model=model,
                    timeout=timeout
                )

                response = completion.choices[0].message.content
                return response

            except RateLimitError as e:
                logger.warning(f"Rate limit hit: {e}. Retrying in 2s...")
                time.sleep(2)
            except APIConnectionError as e:
                logger.warning(f"Connection error: {e}. Retrying in 2s...")
                time.sleep(2)
            except APIStatusError as e:
                logger.error(f"API status error: {e}")
                return f"Error: Groq API returned {e.status_code} - {e.message}"
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return f"Error: Unexpected failure - {str(e)}"

        return "Error: Failed to get response from Groq after retries."

# Singleton instance
groq_client = GroqClient()

def ask_groq(messages, model="llama-3.1-70b-versatile"):
    return groq_client.ask_groq(messages, model=model)
