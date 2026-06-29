"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Optional


class LLMProvider(ABC):
    """Interface that all LLM providers must implement."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def generate_response(self, prompt: str, max_tokens: int = 500) -> Optional[str]: ...

    @abstractmethod
    def generate_response_with_image(self, prompt: str, image_bytes: bytes, max_tokens: int = 500) -> Optional[str]: ...

    def supports_vision(self) -> bool:
        return True
