from config import Settings


def test_default_execution_pool_contains_every_configured_market():
    settings = Settings()
    assert settings.qualified_symbols == settings.symbols
    assert settings.qualified_symbols == (
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "XAUUSD"
    )


def test_qualified_market_allowlist_can_be_explicitly_changed(monkeypatch):
    monkeypatch.setenv("BOT_QUALIFIED_SYMBOLS", "EURUSD,XAUUSD")
    assert Settings.from_env().qualified_symbols == ("EURUSD", "XAUUSD")
