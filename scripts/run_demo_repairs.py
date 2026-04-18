"""Option B: repair demo data on Postgres without seed.py drop_all.

Runs, in order:
1. backfill_presenter_demo_graph.py - presenter <-> every @gymlink.demo user + Tom
2. backfill_tom_for_real_users.py - Tom link for each real (non-demo) account

From repo root with DATABASE_URL set (e.g. Railway shell):

  python scripts/run_demo_repairs.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(script_name: str) -> None:
    path = ROOT / "scripts" / script_name
    print(f"--- {script_name} ---")
    subprocess.check_call([sys.executable, str(path)], cwd=str(ROOT))


def main() -> None:
    _run("backfill_presenter_demo_graph.py")
    _run("backfill_tom_for_real_users.py")
    print("All demo repair scripts finished.")


if __name__ == "__main__":
    main()
