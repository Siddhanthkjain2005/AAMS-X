"""Start the complete offline application as one local process."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    python = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists() or not (ROOT / "frontend" / "dist" / "index.html").exists():
        raise SystemExit("Dependencies or frontend build are missing. Run: python3 scripts/setup.py")
    port = os.getenv("PORT", "8000")
    print(f"AAMS-X · local research workbench\nDashboard: http://127.0.0.1:{port}\nAPI docs:  http://127.0.0.1:{port}/docs\nOffline artifacts and recorded replay are available locally. Ctrl+C to stop.", flush=True)
    os.execv(str(python), [str(python), "-m", "uvicorn", "backend.api:app", "--app-dir", str(ROOT), "--host", "127.0.0.1", "--port", port])


if __name__ == "__main__":
    main()
