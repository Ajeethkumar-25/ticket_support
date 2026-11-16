"""Unit tests for the Dutch reply verifier (src/dutch_verifier.py).

Tests cover the updated verify_reply() that handles nl, en, and de language codes.
No network calls — pure logic.
"""

import pytest
from src.dutch_verifier import verify_reply, verify_dutch_reply


class TestDutchReply:
    def test_valid_dutch_reply_passes(self):
        dutch = (
            "Bedankt voor uw bericht! U kunt uw wachtwoord opnieuw instellen via "
            "de knop 'Wachtwoord vergeten' op het inlogscherm van app.roosterly.nl/login."
        )
        is_valid, issues = verify_reply(dutch, language="nl")
        assert is_valid, issues

    def test_empty_reply_fails(self):
        is_valid, issues = verify_reply("", language="nl")
        assert not is_valid
        assert any("empty" in i.lower() for i in issues)

    def test_very_short_reply_fails(self):
        is_valid, issues = verify_reply("Ok", language="nl")
        assert not is_valid

    def test_reply_with_payment_details_fails(self):
        reply = "Uw IBAN NL91 ABNA 0417 1643 00 is verwerkt."
        is_valid, issues = verify_reply(reply, language="nl")
        assert not is_valid
        assert any("payment" in i.lower() or "redacted" in i.lower() for i in issues)

    def test_dutch_reply_with_english_leakage_fails(self):
        """2+ English words in a Dutch reply should be flagged."""
        leaky = "Hello, please use the settings and invoices page to fix this."
        is_valid, issues = verify_reply(leaky, language="nl")
        assert not is_valid
        assert any("leakage" in i.lower() for i in issues)

    def test_single_english_word_does_not_flag_dutch(self):
        """One English word (e.g. 'app') is fine in Dutch text."""
        mixed = "U kunt de app downloaden in de App Store voor uw apparaat."
        is_valid, issues = verify_reply(mixed, language="nl")
        assert is_valid, issues


class TestEnglishReply:
    def test_valid_english_reply_passes(self):
        english = (
            "Thank you for reaching out! Please update your iOS to version 16 or later "
            "to use the Roosterly app."
        )
        is_valid, issues = verify_reply(english, language="en")
        assert is_valid, issues

    def test_english_check_does_not_flag_english_words_in_en_ticket(self):
        """E01-style ticket: English ticket should not raise Dutch leakage errors."""
        reply = "Please update to iOS 16 or later. The app requires iOS 16 to run."
        is_valid, issues = verify_reply(reply, language="en")
        assert is_valid, issues

    def test_empty_english_reply_fails(self):
        is_valid, issues = verify_reply("   ", language="en")
        assert not is_valid


class TestAliasBackwardsCompat:
    def test_verify_dutch_reply_alias_works(self):
        """verify_dutch_reply is an alias — must behave identically to verify_reply."""
        dutch = "U kunt het wachtwoord opnieuw instellen via de knop op het inlogscherm."
        r1 = verify_reply(dutch, language="nl")
        r2 = verify_dutch_reply(dutch, language="nl")
        assert r1 == r2
