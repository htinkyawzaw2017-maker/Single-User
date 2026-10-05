"""LLM translation + natural rewrite (OpenAI-compatible API).

Configure:
  TRANSLATION_PROVIDER=llm
  LLM_BASE_URL=https://api.openai.com/v1   (or any compatible endpoint)
  LLM_API_KEY=...                          (store in Secrets Manager on AWS)
  LLM_MODEL=gpt-4o-mini

The provider receives every segment of a project in one batched request with
the user's optional rewrite instructions and voice style, and returns natural,
dubbing-friendly target text (not stiff literal translation).
"""
from __future__ import annotations

import json
import re

import httpx

from ...config import settings
from . import TranslationError

SYSTEM_PROMPT = """\
You are a professional movie dubbing translator between English and Burmese.
You rewrite dialogue so that it:
  1. sounds natural and spoken (not literal),
  2. fits roughly the same speaking duration as the original,
  3. keeps names, numbers and honorifics consistent,
  4. respects the requested voice style and any extra user instructions.
Return STRICT JSON only: {{"translations": ["...", ...]}} with exactly one
string per input segment, in the same order. Never add commentary."""


class LlmTranslator:
    provider = "llm"

    def translate(self, texts: list[str], source: str, target: str,
                  style: str = "natural",
                  instructions: str = "") -> list[str]:
        if not settings.llm_base_url:
            raise TranslationError("LLM_BASE_URL is not configured")
        lang_name = {"en": "English", "my": "Burmese"}
        user_prompt = {
            "source_language": lang_name[source],
            "target_language": lang_name[target],
            "voice_style": style,
            "user_instructions": instructions or "",
            "segments": texts,
        }
        try:
            resp = httpx.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model,
                    "temperature": 0.4,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
                    ],
                },
                timeout=180,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            match = re.search(r"\{.*\}", content, re.DOTALL)
            data = json.loads(match.group(0) if match else content)
            translations = data.get("translations", [])
        except Exception as exc:
            raise TranslationError(f"LLM translation failed: {exc}") from exc

        if len(translations) != len(texts):
            raise TranslationError(
                f"LLM returned {len(translations)} translations for {len(texts)} segments"
            )
        return [str(t) for t in translations]
