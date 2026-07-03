"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Iterator, Optional


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

    def supports_streaming(self) -> bool:
        return False

    def generate_response_stream(self, prompt: str, max_tokens: int = 500) -> Iterator[str]:
        """レスポンスを逐次 yield する。デフォルトは非ストリーミング呼び出しへのフォールバック（一括1チャンク）。"""
        text = self.generate_response(prompt, max_tokens=max_tokens)
        if text:
            yield text

    def generate_response_with_image_stream(
        self, prompt: str, image_bytes: bytes, max_tokens: int = 500
    ) -> Iterator[str]:
        """画像付きレスポンスを逐次 yield する。デフォルトは非ストリーミング呼び出しへのフォールバック。"""
        text = self.generate_response_with_image(prompt, image_bytes, max_tokens=max_tokens)
        if text:
            yield text
