"""
containment/

Natural-Language Query Containment Checking (SpiderSQL feature).

Step 1 scope: build the backend foundation only. The service runs the existing
NL->SQL pipeline for two natural-language questions, reports both generated
SQLs with their confidence/validation signals, and returns a NON-committal
containment verdict ("not_checked_yet" when both SQLs are clearly safe,
"unknown" otherwise). No EXCEPT execution, no randomized test databases, and no
symbolic proof are performed yet — those arrive in later steps.
"""

from .models import (
    ContainmentRequest,
    ContainmentQueryResult,
    ContainmentResponse,
)
from .service import check_containment

__all__ = [
    "ContainmentRequest",
    "ContainmentQueryResult",
    "ContainmentResponse",
    "check_containment",
]
