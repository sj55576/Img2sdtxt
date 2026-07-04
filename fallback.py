"""複数の LLM プロバイダーを優先順位付きで束ね、障害時に自動フォールバックする。"""

import logging
import threading
from typing import Iterator, List, Optional

from llm_provider import LLMProvider

logger = logging.getLogger("img2sdtxt.fallback")


class FallbackChain(LLMProvider):
    """優先順位順に並んだプロバイダーを順に試行する LLMProvider 実装。

    先頭のプロバイダーで例外が発生した場合、警告ログを出して次のプロバイダーに
    フォールバックする。全プロバイダーが失敗した場合は最後に発生した例外を送出する。
    """

    def __init__(self, providers: List[LLMProvider]):
        if not providers:
            raise ValueError("FallbackChain requires at least one provider")
        self.providers = providers
        self._lock = threading.Lock()
        self._last_used_provider: Optional[str] = None

    @property
    def provider_name(self) -> str:
        return "fallback"

    @property
    def model(self) -> str:
        return self.providers[0].model

    @property
    def last_used_provider(self) -> Optional[str]:
        with self._lock:
            return self._last_used_provider

    def _set_last_used_provider(self, name: str) -> None:
        with self._lock:
            self._last_used_provider = name

    def is_available(self) -> bool:
        return any(_safe_is_available(p) for p in self.providers)

    def supports_vision(self) -> bool:
        return any(p.supports_vision() for p in self.providers)

    def supports_streaming(self) -> bool:
        return any(p.supports_streaming() and _safe_is_available(p) for p in self.providers)

    def _vision_providers(self) -> List[LLMProvider]:
        return [p for p in self.providers if p.supports_vision()]

    def _try_providers(self, providers: List[LLMProvider], call) -> Optional[str]:
        """providers を順に試し、成功した結果を返す。全滅なら最後の例外を送出する。"""
        if not providers:
            raise RuntimeError("No providers available for this request")

        last_exc: Optional[Exception] = None
        for provider in providers:
            try:
                result = call(provider)
                self._set_last_used_provider(provider.provider_name)
                return result
            except Exception as e:
                last_exc = e
                logger.warning(
                    "Provider %s failed, falling back to next provider: %s",
                    provider.provider_name,
                    e,
                )

        assert last_exc is not None
        raise last_exc

    def generate_response(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        return self._try_providers(
            self.providers,
            lambda p: p.generate_response(prompt, max_tokens=max_tokens),
        )

    def generate_response_with_image(self, prompt: str, image_bytes: bytes, max_tokens: int = 500) -> Optional[str]:
        return self._try_providers(
            self._vision_providers(),
            lambda p: p.generate_response_with_image(prompt, image_bytes, max_tokens=max_tokens),
        )

    def _first_streaming_provider(self, candidates: List[LLMProvider]) -> Optional[LLMProvider]:
        for provider in candidates:
            if provider.supports_streaming() and _safe_is_available(provider):
                return provider
        return None

    def generate_response_stream(self, prompt: str, max_tokens: int = 500) -> Iterator[str]:
        provider = self._first_streaming_provider(self.providers)
        if provider is None:
            text = self.generate_response(prompt, max_tokens=max_tokens)
            if text:
                yield text
            return

        try:
            for chunk in provider.generate_response_stream(prompt, max_tokens=max_tokens):
                yield chunk
            self._set_last_used_provider(provider.provider_name)
        except Exception as e:
            logger.warning(
                "Streaming provider %s failed, falling back to non-streaming chain: %s",
                provider.provider_name,
                e,
            )
            text = self.generate_response(prompt, max_tokens=max_tokens)
            if text:
                yield text

    def generate_response_with_image_stream(
        self, prompt: str, image_bytes: bytes, max_tokens: int = 500
    ) -> Iterator[str]:
        vision_providers = self._vision_providers()
        provider = self._first_streaming_provider(vision_providers)
        if provider is None:
            text = self.generate_response_with_image(prompt, image_bytes, max_tokens=max_tokens)
            if text:
                yield text
            return

        try:
            for chunk in provider.generate_response_with_image_stream(prompt, image_bytes, max_tokens=max_tokens):
                yield chunk
            self._set_last_used_provider(provider.provider_name)
        except Exception as e:
            logger.warning(
                "Streaming vision provider %s failed, falling back to non-streaming chain: %s",
                provider.provider_name,
                e,
            )
            text = self.generate_response_with_image(prompt, image_bytes, max_tokens=max_tokens)
            if text:
                yield text


def _safe_is_available(provider: LLMProvider) -> bool:
    try:
        return provider.is_available()
    except Exception as e:
        logger.warning("is_available() check raised for provider %s: %s", provider.provider_name, e)
        return False
