from config import Settings


def test_production_defaults_to_independently_validated_market_only():
    settings = Settings()
    assert "XAUUSD" in settings.symbols
    assert settings.qualified_symbols == ("XAUUSD",)


def test_qualified_market_allowlist_can_be_explicitly_changed(monkeypatch):
    monkeypatch.setenv("BOT_QUALIFIED_SYMBOLS", "EURUSD,XAUUSD")
    assert Settings.from_env().qualified_symbols == ("EURUSD", "XAUUSD")
