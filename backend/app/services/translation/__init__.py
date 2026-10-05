"""Translation / rewrite provider factory."""
from __future__ import annotations

from ...config import settings


class TranslationError(RuntimeError):
    pass


def get_translator():
    if settings.translation_provider == "llm" and settings.llm_base_url:
        from .llm import LlmTranslator

        return LlmTranslator()
    from .mock import MockTranslator

    return MockTranslator()
