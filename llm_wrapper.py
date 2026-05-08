"""Multi-provider LLM router. Returns a LangChain chat model.

BYOK: callers can pass `api_key` to override config.OPENAI_API_KEY for that
single LLM client. The override is never stored anywhere — only held in the
returned LangChain client until it goes out of scope.
"""
from typing import Optional

import config


def get_llm(model: Optional[str] = None,
            temperature: float = 0.0,
            api_key: Optional[str] = None):
    """Create a LangChain chat model. `api_key` (when given) overrides config."""
    provider = config.LLM_PROVIDER

    # Bumped from default (2) so transient TPM rate-limits during parallel
    # BM_Results extraction don't fail the whole run. LangChain uses
    # exponential backoff between retries.
    max_retries = 8

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or config.OPENAI_COMPLETION_MODEL,
            temperature=temperature,
            api_key=api_key or config.OPENAI_API_KEY,
            max_retries=max_retries,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model or config.ANTHROPIC_COMPLETION_MODEL,
            temperature=temperature,
            api_key=api_key or config.ANTHROPIC_API_KEY,
            max_tokens=8192,
            max_retries=max_retries,
        )

    if provider == "azure-openai":
        from langchain_openai import AzureChatOpenAI
        return AzureChatOpenAI(
            azure_deployment=model or config.AZURE_OPENAI_COMPLETION_DEPLOYMENT,
            api_version=config.AZURE_OPENAI_API_VERSION,
            azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
            api_key=api_key or config.AZURE_OPENAI_API_KEY,
            temperature=temperature,
            max_retries=max_retries,
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}")


def get_embeddings():
    if config.EMBEDDING_PROVIDER == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=config.EMBEDDING_MODEL,
            api_key=config.OPENAI_API_KEY,
        )
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {config.EMBEDDING_PROVIDER!r}")
