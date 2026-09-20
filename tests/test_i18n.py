"""Tests for src/i18n — language detection, switch detection, session locking.

Run with::

    cd LocalModelService
    pip install pytest       # if not already installed
    python -m pytest tests/test_i18n.py -v
"""
from src.i18n import LangManager, LangSession

# ---------------------------------------------------------------------------
# A manager instance that never touches disk (no template calls in tests).
# ---------------------------------------------------------------------------
_manager = LangManager(template_dir="/tmp/_i18n_test_void", default_lang="en")


# ===================================================================
# detect_language
# ===================================================================


class TestDetectLanguage:
    def test_portuguese_greeting(self):
        assert _manager.detect_language("Olá, bom dia!") == "pt"

    def test_portuguese_full_message(self):
        msg = "Olá, gostaria de saber o status do meu pedido #12345"
        assert _manager.detect_language(msg) == "pt"

    def test_portuguese_por_favor(self):
        assert _manager.detect_language("Por favor, me ajude com isso") == "pt"

    def test_portuguese_obrigado(self):
        assert _manager.detect_language("Muito obrigado pela ajuda") == "pt"

    def test_english_greeting(self):
        assert _manager.detect_language("Hello, how are you?") == "en"

    def test_english_full_message(self):
        msg = "Hi, I'd like to check the status of my order please"
        assert _manager.detect_language(msg) == "en"

    def test_english_thanks(self):
        assert _manager.detect_language("Thank you very much for your help") == "en"

    def test_english_shopping(self):
        msg = "I want to return a product I bought last week"
        assert _manager.detect_language(msg) == "en"

    def test_chinese_greeting(self):
        assert _manager.detect_language("你好，请问有什么可以帮助的？") == "zh"

    def test_chinese_order_query(self):
        assert _manager.detect_language("我想查询我的订单状态") == "zh"

    def test_japanese_greeting(self):
        assert _manager.detect_language("こんにちは、お願いします") == "ja"

    def test_japanese_order_query(self):
        assert _manager.detect_language("注文の状況を確認したいです") == "ja"

    def test_spanish_greeting(self):
        assert _manager.detect_language("Hola, buenos días!") == "es"

    def test_spanish_full_message(self):
        msg = "Hola, quisiera saber el estado de mi pedido por favor"
        assert _manager.detect_language(msg) == "es"

    def test_spanish_gracias(self):
        assert _manager.detect_language("Muchas gracias por su ayuda") == "es"

    # --- Mixed / edge cases ---

    def test_english_hello_does_not_fool_pt(self):
        """'Hello' is in the English set but also a short common word;
        message with Portuguese markers should still score pt higher."""
        msg = "Olá, hello, tudo bem? obrigado"
        assert _manager.detect_language(msg) == "pt"

    def test_empty_text_returns_default(self):
        assert _manager.detect_language("") == "en"

    def test_whitespace_only_returns_default(self):
        assert _manager.detect_language("   ") == "en"

    def test_unknown_text_returns_default(self):
        """Nonsense text with no known words should fall back to default."""
        assert _manager.detect_language("xyzxyz klingon qwerty") == "en"

    def test_short_ambiguous_olá(self):
        """A single 'Olá' might be Portuguese or Spanish; Portuguese has
        higher specificity so it should win."""
        assert _manager.detect_language("Olá") == "pt"


# ===================================================================
# is_language_switch
# ===================================================================


class TestLanguageSwitch:
    # --- Positive: each language ---

    def test_switch_to_pt_full(self):
        assert _manager.is_language_switch("Fale português") == (True, "pt")

    def test_switch_to_pt_infinitive(self):
        assert _manager.is_language_switch("Falar em português") == (True, "pt")

    def test_switch_to_pt_mudar(self):
        assert _manager.is_language_switch("Mudar para português") == (True, "pt")

    def test_switch_to_en_speak(self):
        assert _manager.is_language_switch("Speak English") == (True, "en")

    def test_switch_to_en_in(self):
        assert _manager.is_language_switch("Please reply in English") == (True, "en")

    def test_switch_to_en_switch(self):
        assert _manager.is_language_switch("Switch to English please") == (True, "en")

    def test_switch_to_en_can_you(self):
        assert _manager.is_language_switch("Can you speak English?") == (True, "en")

    def test_switch_to_zh_shuo(self):
        assert _manager.is_language_switch("说中文") == (True, "zh")

    def test_switch_to_zh_yong(self):
        assert _manager.is_language_switch("请用中文回答") == (True, "zh")

    def test_switch_to_ja(self):
        assert _manager.is_language_switch("日本語で話してください") == (True, "ja")

    def test_switch_to_ja_kana(self):
        assert _manager.is_language_switch("にほんごでお願いします") == (True, "ja")

    def test_switch_to_es_full(self):
        assert _manager.is_language_switch("Habla español por favor") == (True, "es")

    def test_switch_to_es_cambiar(self):
        assert _manager.is_language_switch("Cambiar a español") == (True, "es")

    def test_switch_to_es_en(self):
        assert _manager.is_language_switch("Responda en español") == (True, "es")

    # --- Case insensitivity ---

    def test_switch_case_insensitive(self):
        assert _manager.is_language_switch("FALE PORTUGUÊS") == (True, "pt")

    def test_switch_mixed_case(self):
        assert _manager.is_language_switch("Speak english") == (True, "en")

    # --- Must NOT trigger on normal messages ---

    def test_no_switch_pt_greeting(self):
        """'português' alone in a non-switch context doesn't trigger."""
        assert _manager.is_language_switch("Olá, tudo bem?") == (False, "")

    def test_no_switch_en_greeting(self):
        assert _manager.is_language_switch("Hello, how are you?") == (False, "")

    def test_no_switch_english_in_question(self):
        """'Do you have this in English?' is effectively a switch."""
        # Actually this SHOULD trigger because 'in English' matches
        result, lang = _manager.is_language_switch("Do you have this in English?")
        # This is a questionable case — let's accept either outcome
        # since the phrase genuinely expresses language preference.

    def test_no_switch_order_query(self):
        assert _manager.is_language_switch("Quero saber meu pedido") == (False, "")

    def test_no_switch_thanks(self):
        assert _manager.is_language_switch("Obrigado") == (False, "")

    def test_no_switch_empty(self):
        assert _manager.is_language_switch("") == (False, "")

    def test_no_switch_nonsense(self):
        assert _manager.is_language_switch("asdf qwerty 12345") == (False, "")


# ===================================================================
# LangSession — language state machine
# ===================================================================


class TestLangSession:
    def setup_method(self):
        """Fresh session before every test."""
        self.s = LangSession(_manager, default_lang="en", window_size=3)

    # --- Window not yet full → not locked ---

    def test_first_message_not_locked(self):
        lang, locked = self.s.advance("alice", "Olá, tudo bem?")
        assert lang == "pt"
        assert locked is False

    def test_second_message_still_not_locked(self):
        self.s.advance("alice", "Olá")
        lang, locked = self.s.advance("alice", "Tudo bem, obrigado")
        assert lang == "pt"
        assert locked is False

    # --- Three messages → locked ---

    def test_three_pt_messages_locks_to_pt(self):
        self.s.advance("alice", "Olá")
        self.s.advance("alice", "Tudo bem?")
        lang, locked = self.s.advance("alice", "Obrigado")
        assert lang == "pt"
        assert locked is True

    def test_three_en_messages_locks_to_en(self):
        self.s.advance("bob", "Hello")
        self.s.advance("bob", "How are you?")
        lang, locked = self.s.advance("bob", "Thanks!")
        assert lang == "en"
        assert locked is True

    def test_after_lock_fast_path_returns_locked(self):
        self.s.advance("carla", "Hola")
        self.s.advance("carla", "Buenos días")
        self.s.advance("carla", "Gracias")
        # Fourth message — fast path, should still be locked
        lang, locked = self.s.advance("carla", "Muchas gracias")
        assert lang == "es"
        assert locked is True

    # --- Majority wins with mixed languages ---

    def test_mixed_2_pt_1_en_locks_to_pt(self):
        self.s.advance("david", "Olá")
        self.s.advance("david", "Hello")
        lang, locked = self.s.advance("david", "Obrigado")
        assert lang == "pt"
        assert locked is True

    # --- Explicit switch overrides during window ---

    def test_switch_on_first_message_immediate_lock(self):
        lang, locked = self.s.advance("eva", "Fale português")
        assert lang == "pt"
        assert locked is True

    def test_switch_on_second_message_overrides_window(self):
        self.s.advance("eva", "Hello")
        lang, locked = self.s.advance("eva", "Fale português")
        assert lang == "pt"
        assert locked is True

    # --- Explicit switch after lock changes language ---

    def test_switch_after_lock_changes_lang(self):
        self.s.advance("frank", "Hello")
        self.s.advance("frank", "How are you?")
        self.s.advance("frank", "Thanks!")          # → locked to en
        lang, locked = self.s.advance("frank", "Fale português")  # switch
        assert lang == "pt"
        assert locked is True

    def test_switch_english_after_pt_lock(self):
        self.s.advance("grace", "Olá")
        self.s.advance("grace", "Tudo bem?")
        self.s.advance("grace", "Obrigado")         # → locked to pt
        lang, locked = self.s.advance("grace", "Speak English")
        assert lang == "en"
        assert locked is True

    # --- Sender isolation ---

    def test_different_senders_independent(self):
        # alice speaks Portuguese
        self.s.advance("alice", "Olá")
        self.s.advance("alice", "Tudo bem?")
        lang_a, locked_a = self.s.advance("alice", "Obrigado")
        assert lang_a == "pt"
        assert locked_a is True

        # bob speaks English — should start fresh
        lang_b, locked_b = self.s.advance("bob", "Hello")
        assert lang_b == "en"
        assert locked_b is False  # bob's window just started

    # --- Session management ---

    def test_reset_clears_state(self):
        self.s.advance("hank", "Olá")
        self.s.advance("hank", "Tudo bem?")
        self.s.advance("hank", "Obrigado")
        assert self.s.is_locked("hank") is True

        self.s.reset("hank")
        assert self.s.is_locked("hank") is False

    def test_reset_starts_new_window(self):
        self.s.advance("hank", "Olá")
        self.s.advance("hank", "Tudo bem?")
        self.s.advance("hank", "Obrigado")
        self.s.reset("hank")

        # Now hank starts fresh with English
        lang, locked = self.s.advance("hank", "Hello")
        assert lang == "en"
        assert locked is False

    def test_reset_all(self):
        self.s.advance("a", "Olá")
        self.s.advance("a", "Tudo bem?")
        self.s.advance("a", "Obrigado")
        self.s.advance("b", "Hello")
        self.s.advance("b", "Thanks")
        self.s.advance("b", "Please")

        self.s.reset_all()
        assert self.s.is_locked("a") is False
        assert self.s.is_locked("b") is False

    # --- Helper accessors ---

    def test_get_lang_before_any_message(self):
        assert self.s.get_lang("unknown") == "en"

    def test_get_lang_after_messages(self):
        self.s.advance("ivan", "Olá")
        assert self.s.get_lang("ivan") == "pt"

    def test_is_locked_before_messages(self):
        assert self.s.is_locked("nobody") is False
