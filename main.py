import os
import sys

# When output is redirected (python main.py > log.txt, Task Scheduler, ...)
# Windows uses the ANSI code page, and deepface's import-time warning (emoji)
# raised UnicodeEncodeError before startup. Escape unencodable characters.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="backslashreplace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils", "facewatch"))
os.chdir(os.path.dirname(__file__))

from engine import run

if __name__ == "__main__":
    run()
