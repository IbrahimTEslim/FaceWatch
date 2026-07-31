import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils", "facewatch"))
os.chdir(os.path.dirname(__file__))

from engine import run

if __name__ == "__main__":
    run()
