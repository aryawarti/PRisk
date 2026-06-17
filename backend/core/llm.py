"""
LLM Factory
-----------
Creates the right LangChain LLM object based on your .env settings.
All agents import `get_llm()` so you only change the provider in one place.
"""

import os
from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel

load_dotenv()


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
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=0,
            groq_api_key=_require_env("GROQ_API_KEY"),
        )

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER='{provider}'. "
            "Choose from: openai, gemini, groq"
        )
