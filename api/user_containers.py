"""User Container Management Module - Direct API Key Mode.

This module manages Docker containers that run complete Hermes Agent instances.
Each user gets a dedicated container with:
- Full Hermes Agent code
- User-specific data directories (workspace, memories, sessions)
- Direct LLM API access (API Key passed via mounted .env)
- Shared skills directories (private + public)

Architecture (Simplified):
┌─────────────────────────────────────────────────────┐
│  Host Machine                                        │
│                                                      │
│  ~/.hermes/                                          │
│  ├── config.yaml        ← Mounted to container      │
│  ├── .env               ← Mounted to container      │
│  ├── skills/                                         │
│  │   ├── private/       ← Mounted to container      │
│  │   └── public/        ← Mounted to container      │
│  └── user-workspaces/{user_id}/                     │
│      ├── workspace/     ← Mounted to /workspace      │
│      ├── memories/      ← Mounted to container      │
│      └── sessions.db    ← Mounted to container      │
│                                                      │
├─────────────────────────────────────────────────────┤
│  Container (per-user)                                │
│                                                      │
│  /opt/hermes-agent/      → Hermes code              │
│  /workspace/             → User files               │
│  /root/.hermes/                                      │
│  ├── config.yaml         → Provider/model config    │
│  ├── .env                → API keys                 │
│  ├── memories/           → User memories            │
│  ├── skills/                                         │
│  │   ├── private/        → User private skills      │
│  │   └── public/         → Public/builtin skills    │
│  └── sessions.db         → Conversation history     │
│                                                      │
│  Hermes Agent                                        │
│  └── Direct LLM API call (API Key from .env)        │
└─────────────────────────────────────────────────────┘
"""

import json
import logging
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Any

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────────────────

DEFAULT_IMAGE = "hermes-user-agent-full:latest"
DEFAULT_CPU = 1.0
DEFAULT_MEMORY = 2048  # MB
DEFAULT_TIMEOUT = 300  # seconds
IDLE_TIMEOUT = 300  # 5 minutes

# ── Global State ─────────────────────────────────────────────────────────────────

_USER_CONTAINERS: Dict[str, "UserContainer"] = {}
_CONTAINER_LOCK = threading.Lock()
_LAST_ACTIVITY: Dict[str, float] = {}
_cleanup_thread_started = False

# ── User Container Class ──────────────────────────────────────────────────────────


class UserContainer:
    """Represents a user's dedicated Hermes Agent container."""

    def __init__(
        self,
        user_id: str,
        container_id: str,
        docker_exe: str,
    ):
        self.user_id = user_id
        self.container_id = container_id
        self.docker_exe = docker_exe
        self._cwd = "/workspace"

    def execute_agent(
        self,
        message: str,
        session_id: Optional[str] = None,
        skill_id: Optional[str] = None,
        file_ids: Optional[list] = None,
        timeout: int = DEFAULT_TIMEOUT,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute Hermes Agent in the container.

        Args:
            message: User message
            session_id: Session ID for conversation history
            skill_id: Skill to use
            file_ids: Files to attach
            timeout: Execution timeout
            model: Model to use (e.g., "qwen-plus", "gpt-4o")

        Returns:
            Dict with response content and metadata
        """
        # Build command to run Hermes Agent in container
        # Agent reads config.yaml and .env from mounted /root/.hermes/
        cmd_args = [
            "--message", message,
            "--platform", "api",
            "--user-id", self.user_id,
        ]

        if model:
            cmd_args.extend(["--model", model])

        if session_id:
            cmd_args.extend(["--session-id", session_id])

        if skill_id:
            cmd_args.extend(["--skill-id", skill_id])

        # Build the command string
        cmd = f"cd /opt/hermes-agent && python -m run_agent {self._build_args(cmd_args)}"

        logger.info(f"Executing agent for user {self.user_id}: {cmd[:100]}...")

        try:
            result = subprocess.run(
                [self.docker_exe, "exec", self.container_id, "bash", "-c", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                logger.error(f"Agent execution failed: {result.stderr}")
                return {
                    "success": False,
                    "error": result.stderr or "Unknown error",
                    "content": None,
                }

            # Log both stdout and stderr for debugging
            logger.info(f"Agent stdout: {result.stdout[:500]}...")
            if result.stderr:
                logger.warning(f"Agent stderr: {result.stderr[:500]}...")

            # Parse the result (Agent outputs JSON)
            try:
                response = json.loads(result.stdout.strip())
                logger.info(f"Parsed response: content={response.get('content')[:100] if response.get('content') else None}...")
                return {
                    "success": True,
                    "content": response.get("content"),
                    "session_id": response.get("session_id"),
                    "tool_calls": response.get("tool_calls"),
                    "raw_stdout": result.stdout,  # Include raw output for debugging
                }
            except json.JSONDecodeError as e:
                # If not JSON, return raw output
                logger.warning(f"JSON decode error: {e}, raw output: {result.stdout[:200]}...")
                return {
                    "success": True,
                    "content": result.stdout.strip(),
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Execution timed out after {timeout}s",
                "content": None,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": None,
            }

    def execute_command(self, command: str, timeout: int = 60) -> str:
        """Execute a raw shell command in the container.

        Args:
            command: Shell command to execute
            timeout: Command timeout

        Returns:
            Command output
        """
        try:
            result = subprocess.run(
                [self.docker_exe, "exec", self.container_id, "bash", "-c", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.stdout + result.stderr
        except Exception as e:
            return f"Error: {e}"

    def upload_file(self, host_path: str, container_path: str) -> bool:
        """Upload a file from host to container.

        Args:
            host_path: Path on host machine
            container_path: Destination path in container

        Returns:
            True if successful
        """
        try:
            result = subprocess.run(
                [self.docker_exe, "cp", host_path, f"{self.container_id}:{container_path}"],
                capture_output=True,
                timeout=60,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            return False

    def download_file(self, container_path: str, host_path: str) -> bool:
        """Download a file from container to host.

        Args:
            container_path: Path in container
            host_path: Destination path on host

        Returns:
            True if successful
        """
        try:
            result = subprocess.run(
                [self.docker_exe, "cp", f"{self.container_id}:{container_path}", host_path],
                capture_output=True,
                timeout=60,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to download file: {e}")
            return False

    def cleanup(self):
        """Stop and remove the container."""
        try:
            subprocess.run(
                [self.docker_exe, "stop", self.container_id],
                timeout=60, capture_output=True,
            )
            subprocess.run(
                [self.docker_exe, "rm", self.container_id],
                timeout=10, capture_output=True,
            )
        except Exception as e:
            logger.warning(f"Failed to cleanup container: {e}")

    def _build_args(self, args: list) -> str:
        """Build shell-safe argument string."""
        result = []
        for arg in args:
            # Escape quotes and wrap in quotes
            escaped = arg.replace('"', '\\"')
            result.append(f'"{escaped}"')
        return " ".join(result)


# ── Container Management Functions ────────────────────────────────────────────────


def get_or_create_user_container(
    user_id: str,
    image: str = None,
    cpu: float = None,
    memory: int = None,
    api_port: int = 8000,
) -> UserContainer:
    """Get existing or create new user container.

    Args:
        user_id: User identifier
        image: Docker image (default: hermes-user-agent-full:latest)
        cpu: CPU limit
        memory: Memory limit in MB
        api_port: Host API port for LLM proxy

    Returns:
        UserContainer instance
    """
    from tools.environments.docker import find_docker

    docker_exe = find_docker() or "docker"
    container_key = f"user-{user_id}"

    with _CONTAINER_LOCK:
        # Check for existing container (in cache or in Docker)
        existing = _USER_CONTAINERS.get(container_key)
        if existing and existing.container_id:
            # Verify container is running
            status = _get_container_status(docker_exe, existing.container_id)
            if status == "running":
                _LAST_ACTIVITY[container_key] = time.time()
                return existing
            elif status in ("exited", "paused"):
                # Restart the stopped container
                logger.info(f"Restarting container {existing.container_id[:12]}")
                _restart_container(docker_exe, existing.container_id)
                _LAST_ACTIVITY[container_key] = time.time()
                return existing
            else:
                # Container gone, remove from cache
                _USER_CONTAINERS.pop(container_key, None)
                _LAST_ACTIVITY.pop(container_key, None)

        # Check for container by name in Docker (Dashboard restart case)
        container_name = f"hermes-{container_key}"
        existing_id = _find_container_by_name(docker_exe, container_name)
        if existing_id:
            status = _get_container_status(docker_exe, existing_id)
            if status == "running":
                logger.info(f"Found running container {existing_id[:12]}")
                container = _create_container_wrapper(
                    user_id, existing_id, docker_exe
                )
                _USER_CONTAINERS[container_key] = container
                _LAST_ACTIVITY[container_key] = time.time()
                return container
            elif status in ("exited", "paused"):
                logger.info(f"Found stopped container {existing_id[:12]}, restarting")
                _restart_container(docker_exe, existing_id)
                container = _create_container_wrapper(
                    user_id, existing_id, docker_exe
                )
                _USER_CONTAINERS[container_key] = container
                _LAST_ACTIVITY[container_key] = time.time()
                return container

        # Need to create new container
        _ensure_docker_running(docker_exe)

        # Initialize user data directory
        user_data_dir = _init_user_data_dir(user_id)

        # Ensure host skills directories exist
        private_skills_dir = get_hermes_home() / "skills" / "private"
        public_skills_dir = get_hermes_home() / "skills" / "public"
        private_skills_dir.mkdir(parents=True, exist_ok=True)
        public_skills_dir.mkdir(parents=True, exist_ok=True)

        # Build volume mounts
        # ── User-specific data (isolated per user) ─────────────────────────────────────
        volumes = [
            f"{user_data_dir / 'workspace'}:/workspace:rw",
            f"{user_data_dir / 'memories'}:/root/.hermes/memories:rw",
            f"{user_data_dir / 'sessions.db'}:/root/.hermes/sessions.db:rw",
        ]

        # ── Mount host's skills directories (shared across all users) ────────────────
        # Private skills: ~/.hermes/skills/private/ → contains all users' private skills
        # We mount the entire private skills directory (user's skills are isolated by skill_id)
        private_skills_dir = get_hermes_home() / "skills" / "private"
        if private_skills_dir.exists():
            volumes.append(f"{private_skills_dir}:/root/.hermes/skills/private:rw")
            logger.info(f"Mounting host private skills directory")

        # Public skills: ~/.hermes/skills/public/ → builtin + published skills
        public_skills_dir = get_hermes_home() / "skills" / "public"
        if public_skills_dir.exists():
            volumes.append(f"{public_skills_dir}:/root/.hermes/skills/public:ro")
            logger.info(f"Mounting host public skills directory")

        # Mount host config files for LLM provider configuration
        # config.yaml: provider/model settings
        host_config = get_hermes_home() / "config.yaml"
        if host_config.exists():
            volumes.append(f"{host_config}:/root/.hermes/config.yaml:ro")
            logger.info(f"Mounting host config.yaml for container")

        # .env: API keys (for direct LLM access)
        host_env = get_hermes_home() / ".env"
        if host_env.exists():
            volumes.append(f"{host_env}:/root/.hermes/.env:ro")
            logger.info(f"Mounting host .env for container")

        # Ensure host files are readable (fix permission issues)
        try:
            if host_config.exists():
                os.chmod(host_config, 0o644)
            if host_env.exists():
                os.chmod(host_env, 0o644)
            # Make hermes home directory traversable
            os.chmod(get_hermes_home(), 0o755)
        except Exception as e:
            logger.warning(f"Could not fix file permissions: {e}")

        # Create the container
        img = image or DEFAULT_IMAGE
        cpu_limit = cpu or DEFAULT_CPU
        mem_limit = memory or DEFAULT_MEMORY

        container_name = f"hermes-{container_key}"

        logger.info(f"Creating container for user {user_id} with image {img}")

        run_args = [
            docker_exe, "run", "-d",
            "--name", container_name,
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "256",
            "--cpus", str(cpu_limit),
            "--memory", f"{mem_limit}m",
            "-w", "/workspace",
        ]

        # Add volume mounts
        for vol in volumes:
            run_args.extend(["-v", vol])

        # Network: bridge mode (default)
        # No need for host network access - container calls LLM directly
        run_args.append("--network=bridge")

        run_args.append(img)
        run_args.extend(["sleep", "infinity"])

        try:
            result = subprocess.run(
                run_args,
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
            container_id = result.stdout.strip()

            logger.info(f"[OK] Container created: {container_id[:12]} for user {user_id}")
            print(f"[OK] Container created: {container_id[:12]} for user {user_id}")

            container = _create_container_wrapper(
                user_id, container_id, docker_exe
            )
            _USER_CONTAINERS[container_key] = container
            _LAST_ACTIVITY[container_key] = time.time()

            # Start cleanup thread
            _start_cleanup_thread()

            return container

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create container: {e.stderr}")
            print(f"[ERROR] Failed to create container: {e.stderr}")
            raise RuntimeError(f"Failed to create user container: {e.stderr}")
        except Exception as e:
            logger.error(f"Failed to create container: {e}")
            print(f"[ERROR] Failed to create container: {e}")
            raise RuntimeError(f"Failed to create user container: {e}")


def _create_container_wrapper(
    user_id: str,
    container_id: str,
    docker_exe: str,
) -> UserContainer:
    """Create a UserContainer wrapper for an existing container."""
    return UserContainer(
        user_id=user_id,
        container_id=container_id,
        docker_exe=docker_exe,
    )


def _init_user_data_dir(user_id: str) -> Path:
    """Initialize user data directory structure.

    Creates:
        ~/.hermes/user-workspaces/{user_id}/
        ├── workspace/    ← User files (mounted to /workspace)
        ├── memories/     ← User memories (mounted to /root/.hermes/memories)
        └── sessions.db   ← Conversation history database
    """
    user_dir = get_hermes_home() / "user-workspaces" / user_id

    # Create directories
    (user_dir / "workspace").mkdir(parents=True, exist_ok=True)
    (user_dir / "memories").mkdir(parents=True, exist_ok=True)

    # Create empty sessions.db if not exists
    sessions_db = user_dir / "sessions.db"
    if not sessions_db.exists():
        # Touch the file - container will create proper schema
        sessions_db.touch()

    return user_dir


def _get_container_status(docker_exe: str, container_id: str) -> Optional[str]:
    """Get container status."""
    try:
        result = subprocess.run(
            [docker_exe, "inspect", "--format", "{{.State.Status}}", container_id],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip().lower()
    except Exception:
        pass
    return None


def _restart_container(docker_exe: str, container_id: str) -> bool:
    """Restart a stopped container."""
    try:
        result = subprocess.run(
            [docker_exe, "start", container_id],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Failed to restart container: {e}")
        return False


def _find_container_by_name(docker_exe: str, name: str) -> Optional[str]:
    """Find container ID by name."""
    try:
        result = subprocess.run(
            [docker_exe, "ps", "-a", "--filter", f"name={name}", "--format", "{{.ID}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split()[0]
    except Exception:
        pass
    return None


def _ensure_docker_running(docker_exe: str):
    """Ensure Docker daemon is running."""
    try:
        result = subprocess.run(
            [docker_exe, "version"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            raise RuntimeError("Docker daemon not running")
    except Exception as e:
        raise RuntimeError(f"Docker not available: {e}")


def cleanup_user_container(user_id: str) -> bool:
    """Clean up user container and optionally data."""
    container_key = f"user-{user_id}"

    with _CONTAINER_LOCK:
        container = _USER_CONTAINERS.pop(container_key, None)
        _LAST_ACTIVITY.pop(container_key, None)

        if container:
            container.cleanup()
            logger.info(f"Container cleaned up for user {user_id}")
            return True

    return False


def delete_user_data(user_id: str, delete_data: bool = False) -> bool:
    """Delete user container and optionally all data.

    Args:
        user_id: User identifier
        delete_data: If True, also delete the data directory

    Returns:
        True if successful
    """
    # Clean up container first
    cleanup_user_container(user_id)

    if delete_data:
        user_dir = get_hermes_home() / "user-workspaces" / user_id
        if user_dir.exists():
            import shutil
            shutil.rmtree(user_dir, ignore_errors=True)
            logger.info(f"Data deleted for user {user_id}")

    return True


def list_user_containers() -> Dict[str, Dict[str, Any]]:
    """List all active user containers."""
    with _CONTAINER_LOCK:
        now = time.time()
        result = {}
        for key, container in _USER_CONTAINERS.items():
            user_id = key.replace("user-", "")
            last_activity = _LAST_ACTIVITY.get(key, 0)
            idle_seconds = int(now - last_activity)
            result[user_id] = {
                "container_id": container.container_id[:12] if container.container_id else "unknown",
                "idle_seconds": idle_seconds,
            }
        return result


def _start_cleanup_thread():
    """Start background thread for idle container cleanup."""
    global _cleanup_thread_started
    if _cleanup_thread_started:
        return

    def cleanup_loop():
        while True:
            time.sleep(60)  # Check every minute
            now = time.time()

            with _CONTAINER_LOCK:
                keys_to_cleanup = []
                for key, last_time in list(_LAST_ACTIVITY.items()):
                    if now - last_time > IDLE_TIMEOUT:
                        keys_to_cleanup.append(key)

                for key in keys_to_cleanup:
                    container = _USER_CONTAINERS.pop(key, None)
                    _LAST_ACTIVITY.pop(key, None)
                    if container:
                        try:
                            # Stop container but keep data (only stop, not rm)
                            from tools.environments.docker import find_docker
                            docker_exe = find_docker() or "docker"
                            subprocess.run(
                                [docker_exe, "stop", container.container_id],
                                timeout=60, capture_output=True,
                            )
                            logger.info(f"Stopped idle container for {key}")
                        except Exception as e:
                            logger.warning(f"Failed to stop idle container: {e}")

    thread = threading.Thread(target=cleanup_loop, daemon=True, name="user-container-cleanup")
    thread.start()
    _cleanup_thread_started = True
    logger.info("Cleanup thread started")


# Register cleanup on exit
import atexit


def _cleanup_on_exit():
    """Clean up all containers on process exit."""
    with _CONTAINER_LOCK:
        for container in list(_USER_CONTAINERS.values()):
            try:
                container.cleanup()
            except Exception:
                pass


atexit.register(_cleanup_on_exit)