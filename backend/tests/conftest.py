import sys
from pathlib import Path

# Ensure the backend root is importable so tests can use package paths like
# `assignment.assignment_parser`, `planning.plan_resolver`, `db.database_service`, etc.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
