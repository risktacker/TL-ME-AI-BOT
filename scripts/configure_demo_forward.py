"""Merge the order-enabled demo profile into .env without losing local secrets."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import secrets
import shutil


ASSIGNMENT = re.compile(r"^([A-Z][A-Z0-9_]*)=")


def values(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = ASSIGNMENT.match(raw.strip())
        if match:
            result[match.group(1)] = raw.split("=", 1)[1]
    return result


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    target = root / ".env"
    profile = values(root / "experiments" / "demo_fast_forward.env")
    original = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = root / f".env.before-demo-forward-{stamp}"
        shutil.copy2(target, backup)
        print(f"Backup: {backup}")

    existing = values(target) if target.exists() else {}
    token = existing.get("DASHBOARD_TOKEN", "").strip()
    if not token or token == "replace-with-a-long-random-secret":
        token = secrets.token_urlsafe(24)
    profile["DASHBOARD_TOKEN"] = token

    pending = dict(profile)
    output: list[str] = []
    for line in original:
        match = ASSIGNMENT.match(line.strip())
        if match and match.group(1) in pending:
            key = match.group(1)
            output.append(f"{key}={pending.pop(key)}")
        else:
            output.append(line)
    if output and output[-1].strip():
        output.append("")
    output.append("# GOLIDE fast demo-forward profile")
    output.extend(f"{key}={value}" for key, value in pending.items())
    target.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    print(f"Configured: {target}")
    print(f"Dashboard control token: {token}")
    print("LIVE_TRADING remains false and VALIDATION_PASSED remains false.")


if __name__ == "__main__":
    main()
