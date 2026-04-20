"""
Hermes Agent API server entry point.

Usage:
    python -m api.main
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
"""

from api import app  # noqa: F401 — import triggers app creation

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
