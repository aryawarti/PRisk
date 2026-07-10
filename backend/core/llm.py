"""
LLM Factory
-----------
Creates the right LangChain LLM object based on your .env settings.
All agents import `get_llm()` so you only change the provider in one place.
"""

import os
import time

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel

from core.fallbacks import parse_json_response

load_dotenv()

# Groq deprecated llama-3.3-70b-versatile (June 2026). openai/gpt-oss-120b is
# their recommended replacement for free/developer tiers.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


class LLMUnavailable(Exception):
    """Raised when the LLM could not produce a valid response after retries."""


def _require_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        raise ValueError(f"Missing required environment variable: {var_name}")
    return value


def get_llm() -> BaseChatModel:
    """
    Returns a LangChain chat model based on the LLM_PROVIDER env var.

    Usage:
        from core.llm import get_llm
        llm = get_llm()
        response = llm.invoke("Hello!")
    """
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            temperature=0,
            api_key=_require_env("OPENAI_API_KEY"),
        )

    elif provider in {"gemini", "google"}:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-1.5-pro"),
            temperature=0,
            google_api_key=_require_env("GOOGLE_API_KEY"),
        )

    elif provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL),
            temperature=0,
            groq_api_key=_require_env("GROQ_API_KEY"),
        )

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER='{provider}'. "
            "Choose from: openai, gemini, groq"
        )


def invoke_llm_json(
    prompt: str,
    required_keys: tuple[str, ...] = (),
    retries: int = 1,
) -> dict:
    """
    The single, trustworthy path from prompt → validated dict.

    Guarantees before returning:
      1. The LLM responded (with `retries` extra attempts on failure —
         covers transient rate limits and hiccups).
      2. The response parsed as JSON.
      3. Every key in `required_keys` is present.

    If any of that fails, raises LLMUnavailable so callers fall back to
    heuristics EXPLICITLY — an invalid or half-formed AI answer must never
    silently become part of a score users trust.
    """
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            llm = get_llm()
            response = llm.invoke(prompt)
            data = parse_json_response(response.content)
            if not isinstance(data, dict):
                raise ValueError("LLM returned non-object JSON")
            missing = [key for key in required_keys if key not in data]
            if missing:
                raise ValueError(f"LLM response missing required keys: {missing}")
            return data
        except Exception as e:  # noqa: BLE001 — every failure means "retry, then degrade"
            last_error = e
            if attempt < retries:
                time.sleep(0.8 * (attempt + 1))

    raise LLMUnavailable(str(last_error))


def invoke_llm_text(prompt: str, retries: int = 1) -> str:
    """Same retry semantics for plain-text responses (summaries)."""
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            llm = get_llm()
            response = llm.invoke(prompt)
            text = (response.content or "").strip()
            if not text:
                raise ValueError("LLM returned empty response")
            return text
        except Exception as e:  # noqa: BLE001
            last_error = e
            if attempt < retries:
                time.sleep(0.8 * (attempt + 1))

    raise LLMUnavailable(str(last_error))
