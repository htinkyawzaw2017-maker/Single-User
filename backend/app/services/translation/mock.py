"""Offline mock translation with a small EN<->MY phrase dictionary.

Real translation should use the LLM provider (TRANSLATION_PROVIDER=llm with an
OpenAI-compatible endpoint). The mock exists so the whole pipeline — including
the review editor and timing alignment — works offline with zero API keys.
The user reviews and edits every segment after translation, so mock output is
safe for demos.
"""
from __future__ import annotations

from . import TranslationError

# A tiny demo dictionary — enough to show the bilingual editor working.
EN_TO_MY = {
    "hello": "မင်္ဂလာပါ",
    "hi": "ဟိုင်း",
    "yes": "ဟုတ်ကဲ့",
    "no": "မဟုတ်ဘူး",
    "thank you": "ကျေးဇူးတင်ပါတယ်",
    "please": "တောင်းပန်ပါတယ်",
    "sorry": "တောင်းပန်ပါတယ်",
    "love": "ချစ်တယ်",
    "friend": "မိတ်ဆွေ",
    "family": "မိသားစု",
    "mother": "အမေ",
    "father": "အဖေ",
    "brother": "ညီကို",
    "sister": "အစ်မ",
    "man": "လူယောက်ျား",
    "woman": "မိန်းမ",
    "house": "အိမ်",
    "city": "မြို့",
    "village": "ရွာ",
    "car": "ကား",
    "money": "ငွေ",
    "police": "ရဲ",
    "gun": "သေနတ်",
    "night": "ည",
    "day": "နေ့",
    "morning": "မနက်",
    "time": "အချိန်",
    "today": "ဒီနေ့",
    "tomorrow": "မနက်ဖြန်",
    "yesterday": "မနေ့က",
    "now": "အခု",
    "why": "ဘာလဲ",
    "what": "ဘာ",
    "who": "ဘယ်သူ",
    "where": "ဘယ်မှာ",
    "when": "ဘယ်အချိန်",
    "how": "ဘယ်လို",
    "come": "လာတယ်",
    "go": "သွားတယ်",
    "run": "ပြေးတယ်",
    "stop": "ရပ်တယ်",
    "wait": "စောင့်ပါ",
    "listen": "နားထောင်ပါ",
    "look": "ကြည့်ပါ",
    "help": "ကူညီပါ",
    "danger": "အန္တရာယ်",
    "kill": "သတ်တယ်",
    "die": "သေတယ်",
    "live": "ရှင်တယ်",
    "fight": "တိုက်တယ်",
    "movie": "ရုပ်ရှင်",
    "story": "ဇာတ်လမ်း",
    "end": "ပြီးဆုံး",
    "begin": "စတင်",
    "good": "ကောင်းတယ်",
    "bad": "ဆိုးတယ်",
    "big": "ကြီးတယ်",
    "small": "သေးတယ်",
    "beautiful": "လှတယ်",
    "true": "မှန်တယ်",
    "false": "မှားတယ်",
}
MY_TO_EN = {v: k for k, v in EN_TO_MY.items()}

MOCK_TAG = {
    "my": "[မြန်မာ-mock]",
    "en": "[EN-mock]",
}


class MockTranslator:
    provider = "mock"

    def translate(self, texts: list[str], source: str, target: str,
                  style: str = "natural",
                  instructions: str = "") -> list[str]:
        if source == target:
            raise TranslationError("source and target languages must differ")
        return [self._one(t, source, target) for t in texts]

    def _one(self, text: str, source: str, target: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        if source == "en":
            # word-level dictionary replacement (try 2-word phrases first)
            words = text.split()
            out: list[str] = []
            i = 0
            while i < len(words):
                bigram = " ".join(words[i:i + 2]).lower().strip(".,!?;:")
                if bigram in EN_TO_MY:
                    out.append(EN_TO_MY[bigram])
                    i += 2
                    continue
                token = words[i].lower().strip(".,!?;:")
                out.append(EN_TO_MY.get(token, words[i]))
                i += 1
            return f"{MOCK_TAG['my']} " + " ".join(out)
        words = text.split()
        out = [MY_TO_EN.get(w, w) for w in words]
        return f"{MOCK_TAG['en']} " + " ".join(out)
