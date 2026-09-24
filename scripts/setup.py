"""Cross-platform dependency setup. Network is needed only for this setup step."""

import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command, cwd=ROOT):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=cwd, check=True)


def main():
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required")
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("Install Node.js 20.19+ and npm before running setup")
    if not (ROOT / ".venv").exists():
        venv.create(ROOT / ".venv", with_pip=True)
    python = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    uv = shutil.which("uv")
    if uv:
        run([uv, "sync", "--frozen", "--extra", "dev"])
    else:
        run([python, "-m", "pip", "install", "-r", ROOT / "requirements.lock"])
        run([python, "-m", "pip", "install", "--no-deps", "-e", "."])
    run([npm, "ci"], ROOT / "frontend")
    run([npm, "run", "build"], ROOT / "frontend")
    run([python, "-m", "backend.datasets.bootstrap"])
    print("Setup complete. Launch with ./start_demo.sh or python scripts/start.py")


if __name__ == "__main__":
    main()
