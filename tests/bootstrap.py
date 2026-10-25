"""Import setup shared by fixture tests and tests of the live FindIt release."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "findit" / "scripts" / "findit_query.py"
sys.path.insert(0, str(SCRIPT.parent))

import findit_notes as notes  # noqa: E402

__all__ = ["ROOT", "SCRIPT", "notes"]
