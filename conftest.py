"""Lets the tests do `from telecominsight import ...` no matter where pytest is started from."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))