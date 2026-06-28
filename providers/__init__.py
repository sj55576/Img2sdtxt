"""LLM provider implementations.

Providers are imported lazily by deps.create_llm_provider() to avoid
pulling in heavy SDKs (anthropic, google-generativeai) at startup
when they are not needed.
"""
