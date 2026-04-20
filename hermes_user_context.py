"""Per-request user context for the enterprise API.

Provides a ContextVar that the API conversation handler sets before running
the AIAgent. Tool handlers (e.g. user_files_tool) read from it to determine
which user is making the request, without modifying the existing tool dispatch
chain.

Usage in API layer:
    from hermes_user_context import user_id_var
    token = user_id_var.set(current_user["id"])
    try:
        # run agent ...
    finally:
        user_id_var.reset(token)

Usage in tools:
    from hermes_user_context import get_current_user_id
    user_id = get_current_user_id()  # None in CLI mode
"""

from contextvars import ContextVar
from typing import Optional

user_id_var: ContextVar[Optional[str]] = ContextVar("hermes_user_id", default=None)


def get_current_user_id() -> Optional[str]:
    """Return the user ID for the current request, or None in CLI mode."""
    return user_id_var.get()
