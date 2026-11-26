r"""
Run every tests/test_*.py script and summarise. Exits non-zero if any fail.
Run from project root:
    venv\Scripts\python.exe tests\run_all.py
"""
import os
import pathlib
import subprocess
import sys
import time

TESTS_DIR = pathlib.Path(__file__).resolve().parent


def main() -> int:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")  # deepface logs emoji
    scripts = sorted(TESTS_DIR.glob("test_*.py"))
    failed = []
    for script in scripts:
        t0 = time.time()
        proc = subprocess.run([sys.executable, str(script)], cwd=TESTS_DIR.parent, env=env,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = [l for l in proc.stdout.splitlines() if "tests passed" in l]
        summary = lines[-1].strip() if lines else "no summary (crashed?)"
        status = "PASS" if proc.returncode == 0 else "FAIL"
        print(f"{status}  {script.name:<40} {summary:<22} {time.time() - t0:5.1f}s")
        if proc.returncode != 0:
            failed.append(script.name)
            out = [l for l in proc.stdout.splitlines() if "[FAIL]" in l]
            tail = out or (proc.stderr.strip().splitlines()[-5:] if proc.stderr else [])
            for line in tail:
                print(f"        {line.strip()}")
    print(f"\n{len(scripts) - len(failed)}/{len(scripts)} test files passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
