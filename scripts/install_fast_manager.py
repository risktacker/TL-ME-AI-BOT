"""Install and compile the demo-only GOLIDE MQL5 manager on Windows."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import MetaTrader5 as mt5


def main() -> None:
    if not mt5.initialize():
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        account = mt5.account_info()
        terminal = mt5.terminal_info()
        if account is None or terminal is None:
            raise SystemExit("MT5 account or terminal information is unavailable")
        if int(account.trade_mode) != 0:
            raise SystemExit("Refused: log MT5 into an Exness demo account first")
        root = Path(__file__).resolve().parents[1]
        source = root / "mt5" / "GolideFastManager.mq5"
        target_dir = Path(terminal.data_path) / "MQL5" / "Experts" / "GOLIDE"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        shutil.copy2(source, target)

        terminal_path = Path(terminal.path)
        install_dir = terminal_path if terminal_path.is_dir() else terminal_path.parent
        metaeditor = install_dir / "metaeditor64.exe"
        if not metaeditor.exists():
            metaeditor = install_dir / "metaeditor.exe"
        if not metaeditor.exists():
            raise SystemExit(f"EA copied to {target}, but MetaEditor was not found in {install_dir}")
        log = target.with_suffix(".compile.log")
        completed = subprocess.run(
            [str(metaeditor), f"/compile:{target}", f"/log:{log}"],
            check=False, timeout=60,
        )
        ex5 = target.with_suffix(".ex5")
        if completed.returncode != 0 or not ex5.exists():
            details = log.read_text(errors="replace") if log.exists() else "No compiler log"
            raise SystemExit(f"EA compilation failed.\n{details}")
        print(f"Installed: {ex5}")
        print("In MT5: refresh Navigator, attach GOLIDE/GolideFastManager to ONE chart,")
        print("leave InpDemoOnly=true, and enable Algo Trading. Do not attach a second copy.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
