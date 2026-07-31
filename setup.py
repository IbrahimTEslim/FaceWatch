import os
import sys
import subprocess
from pathlib import Path

ROOT    = Path(__file__).parent
VENV    = ROOT / "venv"
PYTHON  = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
PIP     = VENV / ("Scripts/pip.exe"    if sys.platform == "win32" else "bin/pip")
REQS    = ROOT / "requirements.txt"
MAIN    = ROOT / "main.py"


def run(cmd: list, **kwargs) -> None:
    subprocess.run(cmd, check=True, **kwargs)


if __name__ == "__main__":
    if not VENV.exists():
        print("Creating virtual environment...")
        run([sys.executable, "-m", "venv", str(VENV)])

    print("Installing requirements...")
    run([str(PIP), "install", "-r", str(REQS)])

    print("Launching FaceWatch...\n")
    os.execv(str(PYTHON), [str(PYTHON), str(MAIN)] + sys.argv[1:])
