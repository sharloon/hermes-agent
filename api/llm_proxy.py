"""LLM Proxy Service - Secure API Key handling for containerized agents.

This service runs on the host machine and holds the LLM API keys.
Containerized agents call this proxy instead of directly calling the LLM API,
ensuring API keys never enter the container.

Architecture:
┌─────────────────────────────────────────────────────┐
│  Host Machine                                        │
│                                                      │
│  LLM Proxy Service (this module)                    │
│  ├── Holds API Keys                                 │
│  ├── Receives requests from containers              │
│  └── Calls actual LLM API                           │
│                                                      │
├─────────────────────────────────────────────────────┤
│  Container                                           │
│                                                      │
│  Hermes Agent                                        │
│  └── Calls http://host:internal/llm-proxy          │
│      (No API Key inside container)                  │
└─────────────────────────────────────────────────────┘
"""

import json
import logging
import os
import time
import threading
from typing import Dict, Any, Optional, List

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()

# ── Configuration ─────────────────────────────────────────────────────────────

# Proxy authentication token (shared between host and containers)
# Set via environment variable or generate random
PROXY_SECRET = os.getenv("HERMES_LLM_PROXY_SECRET", "change-me-in-production")

# API Key sources
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

# ── Rate limiting (simple per-user tracking) ───────────────────────────────────

_request_counts: Dict[str, List[float]] = {}
_request_counts_lock = threading.Lock()
MAX_REQUESTS_PER_MINUTE = 60  # Per user


def _check_rate_limit(user_id: str) -> bool:
    """Check if user is within rate limit."""
    now = time.time()
    with _request_counts_lock:
        requests = _request_counts.get(user_id, [])
        # Filter to last minute
        requests = [t for t in requests if now - t < 60]
        _request_counts[user_id] = requests

        if len(requests) >= MAX_REQUESTS_PER_MINUTE:
            return False

        _request_counts[user_id].append(now)
        return True


# ── Request/Response Models ────────────────────────────────────────────────────

class LLMProxyRequest(BaseModel):
    """Request from container to call LLM."""
    provider: str = "anthropic"  # anthropic, openai, dashscope
    model: str
    messages: List[Dict[str, Any]]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    system: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Dict[str, Any]] = None
    stream: bool = False  # Streaming not supported via proxy (safety)
    user_id: str  # For rate limiting and auditing
    # Additional provider-specific options
    extra: Optional[Dict[str, Any]] = None


class LLMProxyResponse(BaseModel):
    """Response from LLM proxy."""
    success: bool
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    stop_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    error: Optional[str] = None
    provider: str
    model: str


# ── Proxy Authentication ──────────────────────────────────────────────────────

def verify_proxy_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify the proxy authentication token."""
    if credentials.credentials != PROXY_SECRET:
        raise HTTPException(status_code=401, detail="Invalid proxy token")
    return True


# ── LLM Provider Implementations ───────────────────────────────────────────────

def _call_anthropic(req: LLMProxyRequest) -> LLMProxyResponse:
    """Call Anthropic Claude API."""
    if not ANTHROPIC_API_KEY:
        return LLMProxyResponse(
            success=False,
            error="Anthropic API key not configured on host",
            provider="anthropic",
            model=req.model,
        )

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    payload = {
        "model": req.model,
        "messages": req.messages,
        "max_tokens": req.max_tokens or 4096,
    }

    if req.system:
        payload["system"] = req.system
    if req.tools:
        payload["tools"] = req.tools
    if req.tool_choice:
        payload["tool_choice"] = req.tool_choice
    if req.temperature:
        payload["temperature"] = req.temperature

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=120,
        )

        if response.status_code != 200:
            return LLMProxyResponse(
                success=False,
                error=f"Anthropic API error: {response.status_code} - {response.text}",
                provider="anthropic",
                model=req.model,
            )

        data = response.json()
        content_blocks = data.get("content", [])

        # Extract text content
        text_content = ""
        tool_calls = []
        for block in content_blocks:
            if block.get("type") == "text":
                text_content = block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input"),
                })

        return LLMProxyResponse(
            success=True,
            content=text_content,
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=data.get("stop_reason"),
            usage=data.get("usage"),
            provider="anthropic",
            model=req.model,
        )

    except Exception as e:
        return LLMProxyResponse(
            success=False,
            error=f"Anthropic API call failed: {str(e)}",
            provider="anthropic",
            model=req.model,
        )


def _call_openai(req: LLMProxyRequest) -> LLMProxyResponse:
    """Call OpenAI API."""
    if not OPENAI_API_KEY:
        return LLMProxyResponse(
            success=False,
            error="OpenAI API key not configured on host",
            provider="openai",
            model=req.model,
        )

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": req.model,
        "messages": req.messages,
        "max_tokens": req.max_tokens or 4096,
    }

    if req.temperature:
        payload["temperature"] = req.temperature
    if req.tools:
        payload["tools"] = req.tools
    if req.tool_choice:
        payload["tool_choice"] = req.tool_choice

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )

        if response.status_code != 200:
            return LLMProxyResponse(
                success=False,
                error=f"OpenAI API error: {response.status_code} - {response.text}",
                provider="openai",
                model=req.model,
            )

        data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        return LLMProxyResponse(
            success=True,
            content=message.get("content"),
            tool_calls=message.get("tool_calls"),
            stop_reason=choice.get("finish_reason"),
            usage=data.get("usage"),
            provider="openai",
            model=req.model,
        )

    except Exception as e:
        return LLMProxyResponse(
            success=False,
            error=f"OpenAI API call failed: {str(e)}",
            provider="openai",
            model=req.model,
        )


def _call_dashscope(req: LLMProxyRequest) -> LLMProxyResponse:
    """Call Alibaba DashScope API."""
    if not DASHSCOPE_API_KEY:
        return LLMProxyResponse(
            success=False,
            error="DashScope API key not configured on host",
            provider="dashscope",
            model=req.model,
        )

    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }

    # DashScope uses OpenAI-compatible format
    payload = {
        "model": req.model,
        "messages": req.messages,
        "max_tokens": req.max_tokens or 4096,
    }

    if req.temperature:
        payload["temperature"] = req.temperature
    if req.tools:
        payload["tools"] = req.tools

    base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )

        if response.status_code != 200:
            return LLMProxyResponse(
                success=False,
                error=f"DashScope API error: {response.status_code} - {response.text}",
                provider="dashscope",
                model=req.model,
            )

        data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        return LLMProxyResponse(
            success=True,
            content=message.get("content"),
            tool_calls=message.get("tool_calls"),
            stop_reason=choice.get("finish_reason"),
            usage=data.get("usage"),
            provider="dashscope",
            model=req.model,
        )

    except Exception as e:
        return LLMProxyResponse(
            success=False,
            error=f"DashScope API call failed: {str(e)}",
            provider="dashscope",
            model=req.model,
        )


# ── API Endpoints ───────────────────────────────────────────────────────────────

@router.post("/invoke", response_model=LLMProxyResponse)
def invoke_llm(
    req: LLMProxyRequest,
    _: bool = Depends(verify_proxy_token),
):
    """Invoke LLM API through the proxy.

    Container agents call this endpoint to interact with LLMs
    without having direct access to API keys.

    Authentication: Bearer token matching HERMES_LLM_PROXY_SECRET
    """
    # Log incoming request for debugging
    logger.info(f"LLM Proxy request: provider={req.provider}, model={req.model}, user_id={req.user_id}, messages_count={len(req.messages)}")

    # Rate limiting
    if not _check_rate_limit(req.user_id):
        logger.warning(f"Rate limit exceeded for user {req.user_id}")
        return LLMProxyResponse(
            success=False,
            error=f"Rate limit exceeded: {MAX_REQUESTS_PER_MINUTE} requests per minute",
            provider=req.provider,
            model=req.model,
        )

    # Route to appropriate provider
    provider = req.provider.lower()

    if provider == "anthropic":
        return _call_anthropic(req)
    elif provider == "openai":
        return _call_openai(req)
    elif provider in ("dashscope", "alibaba", "qwen"):
        return _call_dashscope(req)
    else:
        return LLMProxyResponse(
            success=False,
            error=f"Unknown provider: {provider}",
            provider=req.provider,
            model=req.model,
        )


@router.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "providers": {
            "anthropic": bool(ANTHROPIC_API_KEY),
            "openai": bool(OPENAI_API_KEY),
            "dashscope": bool(DASHSCOPE_API_KEY),
        },
    }


# ── Helper for container-side usage ─────────────────────────────────────────────

def get_proxy_url(host_ip: str = "172.17.0.1", port: int = 8000) -> str:
    """Get the URL for containers to reach the LLM proxy.

    Args:
        host_ip: Host IP accessible from container (default: Docker bridge gateway)
        port: Port where the API server runs

    Returns:
        URL string for containers to use
    """
    return f"http://{host_ip}:{port}/internal/llm-proxy"


def get_proxy_token() -> str:
    """Get the proxy authentication token."""
    return PROXY_SECRET