"""cli.py — CLI entry point for mcp-memory.

Supports:
  mcp-memory         -> Launches the FastMCP HTTP server.
  mcp-memory check   -> Runs environment diagnostics (FTS5, db_path).
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path

from mcp_memory.server import main as server_main
from mcp_memory.shared.config import get_settings


async def run_diagnostics() -> bool:
    settings = get_settings()
    print("==================================================")
    print(" MCP Memory Diagnostics (mcp-memory check)")
    print("==================================================")
    print("Config:")
    print(f"  · DB_PATH:            {settings.db_path}")
    print(f"  · MCP_HOST/PORT:      {settings.mcp_host}:{settings.mcp_port}")
    print(f"  · DEFAULT_NAMESPACE:  {settings.default_namespace}")
    print("--------------------------------------------------")

    all_ok = True

    # 1. FTS5 compiled in this Python's sqlite3 module.
    print("\n[1/2] Checking SQLite FTS5 support...")
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
            print("  ✓ FTS5 is compiled in this Python's sqlite3 module.")
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        print(f"  ❌ FTS5 not available: {exc}")
        print(
            "     Tip: use Homebrew/python.org Python (macOS/Windows), or install "
            "libsqlite3-dev before compiling Python (Linux, pyenv/asdf)."
        )
        all_ok = False

    # 2. db_path resolved, parent dir writable, current row count.
    print("\n[2/2] Checking DB_PATH...")
    if settings.db_path == ":memory:":
        print("  [i] DB_PATH is ':memory:' — ephemeral, nothing to check on disk.")
    else:
        db_path = Path(settings.db_path)
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"  ✓ Parent directory is writable: {db_path.parent}")
        except OSError as exc:
            print(f"  ❌ Cannot create/write parent directory '{db_path.parent}': {exc}")
            all_ok = False
        else:
            if db_path.exists():
                try:
                    conn = sqlite3.connect(str(db_path))
                    try:
                        cursor = conn.execute("SELECT COUNT(*) FROM memories")
                        count = cursor.fetchone()[0]
                        print(f"  ✓ Database exists at '{db_path}' — {count} memories stored.")
                    finally:
                        conn.close()
                except sqlite3.OperationalError as exc:
                    print(
                        f"  ⚠️  Database file exists at '{db_path}' but could not be read: {exc}"
                    )
                    print("     It will be initialized on next server start (ensure_schema()).")
            else:
                print(f"  [i] Database file does not exist yet at '{db_path}'.")
                print("     A fresh DB with 0 memories will be created on server start.")

    print("\n--------------------------------------------------")
    if all_ok:
        print(" RESULT: All checks passed! Ready to start mcp-memory. 🚀")
    else:
        print(" RESULT: Diagnostics found issues. Please check the recommendations above.")
    print("==================================================\n")
    return all_ok


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("check", "--check", "-c"):
        success = asyncio.run(run_diagnostics())
        sys.exit(0 if success else 1)
    else:
        server_main()


if __name__ == "__main__":
    main()
