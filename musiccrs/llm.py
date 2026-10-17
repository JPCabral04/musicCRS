"""The course LLM (Gemma 4 31B, served by Open WebUI): its settings and the client.

The API key is read from the LLM_API_KEY environment variable, so it is never written
in the code and cannot be committed by mistake.
"""
import os

from openai import OpenAI

LLM_BASE_URL = "https://openwebui.ux.uis.no/api"
LLM_MODEL = "gorina10.gemma-4-31b"


def create_client():
    """An OpenAI client for the course LLM, or None when LLM_API_KEY is not set.

    LLM_API_KEY="sk-123"  -> OpenAI(api_key="sk-123", base_url=LLM_BASE_URL)
    no LLM_API_KEY        -> None (the agent then runs with slash commands only)
    """
    # os.environ.get gives "" when the variable does not exist.
    api_key = os.environ.get("LLM_API_KEY", "")
    api_key = api_key.strip()
    if api_key == "":
        return None
    return OpenAI(api_key=api_key, base_url=LLM_BASE_URL)
