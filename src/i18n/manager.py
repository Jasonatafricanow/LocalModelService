"""Multi-language template manager.

Provides template loading/caching/filling, language detection, session-level
language locking, and LLM language instructions.

Generic by design — any module can create its own :class:`LangManager`
pointing to its own template directory.
"""
import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Language signatures for heuristic detection
#
# High-signal words per language.  Short messages (greetings, simple queries)
# often lack syntax cues, so we rely on distinctive function words and
# common customer-service vocabulary.
# ---------------------------------------------------------------------------

_LANG_SIGNATURES: dict[str, set[str]] = {
    "pt": {
        "olá", "oi", "obrigado", "obrigada", "obg", "brigado",
        "por favor", "pfv", "tudo bem", "bom dia", "boa tarde",
        "boa noite", "tchau", "sim", "não", "gostaria", "queria",
        "meu", "minha", "você", "vc", "pode", "para", "com",
        "prazo", "entrega", "pedido", "produto", "pagamento",
        "devolução", "reembolso", "garantia", "troca", "preço",
        "estoque", "modelo", "cor", "senhor", "cliente", "loja",
        "compra", "vendas", "caro", "barato", "muito", "pouco",
        "ainda", "já", "sobre", "mais", "menos", "esse", "essa",
        "isto", "isso", "aquele", "aquela", "da", "do", "das",
        "dos", "na", "no", "nas", "nos", "num", "numa",
    },
    "en": {
        "hello", "hi", "hey", "thanks", "thank", "ty",
        "please", "pls", "good morning", "good afternoon",
        "good evening", "goodbye", "bye", "yes", "yeah", "no",
        "nope", "i'd", "i'll", "i'm", "i've", "my", "me",
        "you", "your", "can", "could", "would", "should",
        "want", "need", "have", "has", "had", "get", "got",
        "order", "product", "delivery", "shipping", "return",
        "refund", "warranty", "price", "stock", "payment",
        "customer", "store", "purchase", "help", "question",
        "please", "send", "receive", "waiting", "status",
        "tracking", "arrived", "damaged", "broken", "wrong",
        "this", "that", "these", "those", "is", "are", "was",
        "were", "the", "a", "an", "of", "to", "in", "for",
        "on", "with", "at", "by", "from", "about",
    },
    "zh": {
        "你好", "您好", "谢谢", "感谢", "抱歉", "不好意思",
        "请问", "再见", "好的", "是的", "不是", "不要",
        "可以", "能够", "需要", "想要", "这个", "那个",
        "我", "你", "他", "她", "我们", "你们", "他们",
        "的", "了", "是", "在", "有", "和", "就", "不",
        "也", "都", "要", "会", "能", "去", "来", "给",
        "订单", "商品", "产品", "快递", "物流", "发货",
        "退货", "退款", "保修", "价格", "库存", "付款",
        "客服", "帮助", "问题", "多久", "什么时候",
        "怎么", "为什么", "因为", "所以", "但是", "如果",
    },
    "ja": {
        "こんにちは", "こんばんは", "おはよう",
        "ありがとう", "ありがとうございます", "すみません",
        "お願いします", "おねがいします", "失礼します",
        "はい", "いいえ", "そうです", "違います",
        "私", "あなた", "私たち", "これ", "それ", "あれ",
        "この", "その", "あの", "です", "ます", "ました",
        "たい", "ください", "できます", "できません",
        "注文", "商品", "製品", "配達", "発送", "返品",
        "返金", "保証", "価格", "在庫", "支払い", "お支払い",
        "カスタマー", "ヘルプ", "質問", "問題", "何", "誰",
        "いつ", "どこ", "なぜ", "どうして", "から", "まで",
        "ですが", "けど", "そして", "それで", "ために",
    },
    "es": {
        "hola", "buenos días", "buenas tardes", "buenas noches",
        "gracias", "muchas gracias", "por favor",
        "adiós", "chao", "sí", "si", "no",
        "quisiera", "me gustaría", "puede", "podría",
        "mi", "mí", "tu", "tú", "su", "usted",
        "este", "esta", "esto", "ese", "esa", "eso",
        "pedido", "producto", "entrega", "envío",
        "devolución", "reembolso", "garantía", "precio",
        "stock", "inventario", "pago", "cliente", "tienda",
        "compra", "venta", "caro", "barato", "muy", "poco",
        "tengo", "tiene", "quiero", "quiere", "necesito",
        "el", "la", "los", "las", "un", "una", "unas",
        "unos", "de", "en", "con", "para", "por", "a",
        "y", "o", "pero", "que", "como", "cuándo",
    },
}


# ---------------------------------------------------------------------------
# Language-switch command patterns
#
# When a customer explicitly asks to change language, the session
# immediately locks to the requested language regardless of the detection
# window.  Each entry is a ``(compiled_regex, target_lang)`` pair.
# ---------------------------------------------------------------------------

_SWITCH_PATTERNS: list[tuple[re.Pattern, str]] = [
    # → Portuguese
    (re.compile(
        r"\b(falar?\s*(em\s*)?portugu[êe]s|"
        r"mudar\s*para\s*portugu[êe]s|"
        r"em\s*portugu[êe]s|"
        r"fale\s*portugu[êe]s)\b", re.IGNORECASE
    ), "pt"),
    # → English
    (re.compile(
        r"\b(speak\s*(in\s*)?english|"
        r"switch\s*to\s*english|"
        r"in\s*english(?!\s*please)|"
        r"can\s*(you\s*)?speak\s*english)\b", re.IGNORECASE
    ), "en"),
    # → Chinese
    (re.compile(
        r"(说中文|用中文|讲中文|请说中文|请用中文|中文回答)", re.IGNORECASE
    ), "zh"),
    # → Japanese
    (re.compile(
        r"(日本語|日本語で|にほんご|日本語で話)", re.IGNORECASE
    ), "ja"),
    # → Spanish
    (re.compile(
        r"\b(habla(?:r)?\s*(en\s*)?español|"
        r"en\s*español|"
        r"cambiar\s*a\s*español)\b", re.IGNORECASE
    ), "es"),
]


# ===================================================================
# LangManager
# ===================================================================


class LangManager:
    """Multi-language template manager.

    Loads JSON template files from a domain-level *template_dir* and
    provides template filling as well as LLM language instructions.

    Template files are named ``<lang>.json`` and are loaded on first
    access, then cached.  Missing keys fall back to *default_lang*.

    Typical usage::

        _lang = LangManager("my_module/templates", default_lang="pt")

        # One-shot get + fill
        reply = _lang.t("greeting", "pt", default="Hello!")

        # With placeholders
        reply = _lang.t(
            "stock_check_result", "pt",
            default="Product {{product}}: {{status}}",
            product="X200", status="in stock",
        )

        # LLM language instruction (soft suggestion)
        instruction = _lang.get_llm_instruction("pt")

        # LLM language instruction (hard lock — no switching allowed)
        lock = _lang.get_lock_instruction("pt")

        # Heuristic language detection
        lang = _lang.detect_language("Olá, bom dia!")

        # Language-switch command detection
        switched, target = _lang.is_language_switch("Fale português")
    """

    # Already has LANGUAGES, __init__, template methods, etc.

    LANGUAGES: dict[str, dict[str, str]] = {
        "pt": {
            "name": "Português (Brasil)",
            "llm_instruction": "Responda em português (PT-BR), de forma "
                               "educada e profissional.",
        },
        "en": {
            "name": "English",
            "llm_instruction": "Respond in English, politely and "
                               "professionally.",
        },
        "zh": {
            "name": "中文",
            "llm_instruction": "请用中文回答，保持友好和专业的态度。",
        },
        "ja": {
            "name": "日本語",
            "llm_instruction": "日本語で丁寧に答えてください。",
        },
        "es": {
            "name": "Español",
            "llm_instruction": "Responda en español, de manera educada y "
                               "profesional.",
        },
    }

    def __init__(
        self,
        template_dir: str,
        default_lang: str = "en",
        extra_languages: Optional[dict[str, dict[str, str]]] = None,
        extra_signatures: Optional[dict[str, set[str]]] = None,
        extra_switch_patterns: Optional[list[tuple[str, str]]] = None,
    ):
        self.template_dir = template_dir
        self.default_lang = default_lang
        self._cache: dict[str, dict[str, str]] = {}

        if extra_languages:
            self.LANGUAGES = {**self.LANGUAGES, **extra_languages}

        # Merge language signatures
        self._signatures = {
            k: set(v) for k, v in _LANG_SIGNATURES.items()
        }
        if extra_signatures:
            for lang, words in extra_signatures.items():
                if lang in self._signatures:
                    self._signatures[lang].update(words)
                else:
                    self._signatures[lang] = set(words)

        # Merge switch patterns
        self._switch_patterns = list(_SWITCH_PATTERNS)
        if extra_switch_patterns:
            for regex_str, target in extra_switch_patterns:
                self._switch_patterns.append((re.compile(regex_str, re.IGNORECASE), target))

    # ------------------------------------------------------------------
    # Template loading & caching
    # ------------------------------------------------------------------

    def load_templates(self, lang: str) -> dict[str, str]:
        """Load templates for *lang*, falling back to *default_lang*."""
        if lang in self._cache:
            return self._cache[lang]

        templates: dict[str, str] = {}
        for code in (lang, self.default_lang):
            path = os.path.join(self.template_dir, f"{code}.json")
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    templates.update(json.load(f))
                break

        self._cache[lang] = templates
        return templates

    def get(self, key: str, lang: str, default: str = "") -> str:
        """Get a single template string for *key* in *lang*."""
        templates = self.load_templates(lang)
        return templates.get(key, default)

    def get_all(self, lang: str) -> dict[str, str]:
        """Return the full template dict for *lang* (loaded & cached)."""
        return self.load_templates(lang)

    # ------------------------------------------------------------------
    # Template filling
    # ------------------------------------------------------------------

    @staticmethod
    def fill(template: str, **kwargs: object) -> str:
        """Replace ``{{placeholder}}`` tokens with keyword values."""
        def _replacer(match: re.Match) -> str:
            key = match.group(1).strip()
            return str(kwargs.get(key, match.group(0)))
        return re.sub(r"\{\{(\w+)\}\}", _replacer, template)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def t(self, key: str, lang: str, default: str = "", **kwargs: object) -> str:
        """One-shot: get template + fill placeholders."""
        template = self.get(key, lang, default)
        return self.fill(template, **kwargs) if kwargs else template

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def detect_language(self, text: str) -> str:
        """Heuristic language detection based on high-signal vocabulary.

        Scores each known language by counting word / character matches
        and returns the language with the highest score.  Returns
        *default_lang* when the score is tied or no matches are found.
        """
        if not text or not text.strip():
            return self.default_lang

        text_lower = text.lower().strip()
        scores: dict[str, int] = {lang: 0 for lang in self._signatures}

        # Latin-script languages: tokenize by whitespace
        for lang in ("pt", "en", "es"):
            sig = self._signatures[lang]
            for word in text_lower.split():
                # Check individual words (single tokens)
                if word in sig:
                    scores[lang] += 3
                # Check multi-word signatures (e.g. "bom dia", "por favor")
                # by scanning the text for each phrase
            for phrase in sig:
                if " " in phrase and phrase in text_lower:
                    scores[lang] += 5

        # CJK languages: character/substring matching
        for lang in ("zh", "ja"):
            sig = self._signatures[lang]
            for token in sig:
                if token in text_lower:
                    # Longer matches get higher weight
                    scores[lang] += len(token) * 2

        # Pick the highest score
        best_lang = self.default_lang
        best_score = 0
        for lang, score in scores.items():
            if score > best_score:
                best_score = score
                best_lang = lang
            elif score == best_score and score > 0:
                # Tie — keep the earlier one (stable)
                pass

        return best_lang

    # ------------------------------------------------------------------
    # Language-switch detection
    # ------------------------------------------------------------------

    def is_language_switch(self, text: str) -> tuple[bool, str]:
        """Check whether *text* contains an explicit language-switch command.

        Returns ``(True, target_lang)`` if a switch is detected, or
        ``(False, "")`` otherwise.
        """
        if not text:
            return False, ""

        for pattern, target in self._switch_patterns:
            if pattern.search(text):
                logger.debug("Language switch detected → '%s' in: %.80s", target, text)
                return True, target

        return False, ""

    # ------------------------------------------------------------------
    # LLM language instructions
    # ------------------------------------------------------------------

    def get_llm_instruction(self, lang: str) -> str:
        """Return the LLM language instruction for *lang* (soft suggestion).

        Falls back to *default_lang* if *lang* is not defined.
        """
        entry = self.LANGUAGES.get(lang) or self.LANGUAGES.get(self.default_lang)
        return entry["llm_instruction"] if entry else ""

    def get_lock_instruction(self, lang: str) -> str:
        """Return a **hard-lock** instruction for *lang*.

        The model MUST NOT switch languages under any circumstance.
        Use this after the language has been confirmed (window filled or
        explicit switch).
        """
        name = self.get_language_name(lang)
        return (
            f"IMMUTABLE LANGUAGE RULE: The conversation language is "
            f"{name} ({lang.upper()}). "
            f"You MUST respond in {name} ONLY — regardless of the "
            f"language the customer writes in. Never switch to another "
            f"language, never translate, never repeat this rule. Simply "
            f"respond in {name}."
        )

    def get_language_name(self, lang: str) -> str:
        """Return the human-readable name for *lang*."""
        entry = self.LANGUAGES.get(lang)
        return entry["name"] if entry else lang

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def clear_cache(self) -> None:
        self._cache.clear()


# ===================================================================
# LangSession — per-sender language state machine
# ===================================================================


class LangSession:
    """Per-sender language state machine with detection window and locking.

    Collects up to *window_size* messages to determine the customer's
    language, then locks the session.  Explicit language-switch commands
    (e.g. "Fale português") override immediately at any point.

    Typical usage::

        _lang = LangManager(...)
        session = LangSession(_lang, default_lang="pt", window_size=3)

        # In message handler:
        lang, is_locked = session.advance(sender, message_text)
    """

    # ── State schema ────────────────────────────────────────────────
    #   {
    #       "locked": bool,        # True once language is finalised
    #       "lang": str,           # Resolved language code
    #       "samples": [str, ...], # Collected messages (window)
    #   }
    # ────────────────────────────────────────────────────────────────

    def __init__(
        self,
        manager: LangManager,
        default_lang: str = "en",
        window_size: int = 3,
    ):
        self.manager = manager
        self.default_lang = default_lang
        self.window_size = window_size
        self._states: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def advance(self, sender: str, message: str) -> tuple[str, bool]:
        """Process one message from *sender*.

        Returns ``(language_code, is_locked)``.

        - While in the detection window the returned language is a
          best-effort guess; ``is_locked`` is ``False``.
        - Once the window is filled (or an explicit switch is detected),
          ``is_locked`` is ``True`` — the caller should use
          :meth:`LangManager.get_lock_instruction` instead of
          :meth:`LangManager.get_llm_instruction`.
        """
        state = self._states.setdefault(sender, {
            "locked": False,
            "lang": self.default_lang,
            "samples": [],
        })

        # 1. Explicit language-switch takes priority
        switched, target = self.manager.is_language_switch(message)
        if switched:
            self._states[sender] = {
                "locked": True,
                "lang": target,
                "samples": [],
            }
            return target, True

        # 2. Already locked — fast path
        if state["locked"]:
            return state["lang"], True

        # 3. Detection window: collect and evaluate
        state["samples"].append(message)

        if len(state["samples"]) >= self.window_size:
            # Window full — lock to the majority language
            combined = " ".join(state["samples"])
            detected = self.manager.detect_language(combined)
            self._states[sender] = {
                "locked": True,
                "lang": detected,
                "samples": [],
            }
            return detected, True

        # Window not yet full — return best guess (not locked)
        combined = " ".join(state["samples"])
        best_guess = self.manager.detect_language(combined)
        state["lang"] = best_guess
        return best_guess, False

    def get_state(self, sender: str) -> dict:
        """Return the raw state dict for *sender*."""
        return self._states.get(sender, {
            "locked": False,
            "lang": self.default_lang,
            "samples": [],
        })

    def is_locked(self, sender: str) -> bool:
        """Check whether *sender*'s language is locked."""
        state = self._states.get(sender)
        return state["locked"] if state else False

    def get_lang(self, sender: str) -> str:
        """Return the current resolved language for *sender*.

        Returns *default_lang* if no messages have been processed yet.
        """
        state = self._states.get(sender)
        return state["lang"] if state else self.default_lang

    def reset(self, sender: str) -> None:
        """Reset *sender*'s session (clear window and unlock)."""
        self._states.pop(sender, None)

    def reset_all(self) -> None:
        """Reset all sessions."""
        self._states.clear()
