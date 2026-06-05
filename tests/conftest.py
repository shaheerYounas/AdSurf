import os
import sys
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")

# Ensure repo root is on sys.path so `from apps.api.app...` imports work
# regardless of whether PYTHONPATH is set by the caller.
_repo_root = str(Path(__file__).parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
