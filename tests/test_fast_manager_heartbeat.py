from datetime import datetime, timezone
from types import SimpleNamespace

from core.mt5_client import MT5Gateway


def test_fast_manager_heartbeat_requires_matching_fresh_identity(monkeypatch, tmp_path):
    path = tmp_path / "Files" / "GOLIDE"
    path.mkdir(parents=True)
    heartbeat = path / "fast_manager_heartbeat.csv"
    heartbeat.write_text(
        f"{datetime.now(timezone.utc).timestamp()},123,260909", encoding="ascii")
    fake = SimpleNamespace(
        terminal_info=lambda: SimpleNamespace(commondata_path=str(tmp_path)),
        account_info=lambda: SimpleNamespace(login=123),
    )
    monkeypatch.setattr("core.mt5_client.mt5", fake)
    assert MT5Gateway().fast_manager_heartbeat(260909)["ready"]
    assert not MT5Gateway().fast_manager_heartbeat(999)["ready"]


def test_fast_manager_heartbeat_rejects_stale_file(monkeypatch, tmp_path):
    path = tmp_path / "Files" / "GOLIDE"
    path.mkdir(parents=True)
    (path / "fast_manager_heartbeat.csv").write_text("1,123,260909", encoding="ascii")
    fake = SimpleNamespace(
        terminal_info=lambda: SimpleNamespace(commondata_path=str(tmp_path)),
        account_info=lambda: SimpleNamespace(login=123),
    )
    monkeypatch.setattr("core.mt5_client.mt5", fake)
    result = MT5Gateway().fast_manager_heartbeat(260909)
    assert not result["ready"] and result["reason"] == "heartbeat_stale"
