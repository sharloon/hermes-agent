# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Environment

```bash
source venv/bin/activate          # Always activate first
uv pip install -e ".[all,dev]"    # Install all extras for development
```

## Commands

```bash
# Tests
python -m pytest tests/ -q                           # Full suite (~3000 tests, ~3 min)
python -m pytest tests/gateway/ -q                   # Specific module
python -m pytest tests/ -q -m integration            # Integration tests (requires API keys)

# Run
hermes                    # Interactive CLI
hermes gateway            # Start messaging gateway
hermes setup              # Configuration wizard
```

## Architecture

Hermes is a self-improving AI agent framework (Nous Research). The same agent loop (`run_agent.py:AIAgent`) powers both the interactive CLI and all messaging platforms (Telegram, Discord, Slack, WhatsApp, Signal, etc.).

### Data flow

```
User input (CLI / gateway platform)
  → hermes_cli/main.py or gateway/run.py
  → run_agent.py:AIAgent.run_conversation()
      → agent/prompt_builder.py  (assemble system prompt: identity, skills, memory, context)
      → LLM API call (anthropic_adapter.py or openai client)
      → tool call loop → model_tools.py:handle_function_call() → tools/registry.py → tool handler
      → repeat until stop_reason="end_turn"
  → render response (KawaiiSpinner in CLI, platform adapter in gateway)
```

### File dependency chain

```
tools/registry.py  (no deps — base layer)
  ↑  imported by
tools/*.py  (each calls registry.register() at import time — auto-discovered)
  ↑  imported by
model_tools.py  (discover_builtin_tools, handle_function_call)
  ↑  imported by
run_agent.py, cli.py, batch_runner.py
```

### Key subsystems

| File/Dir | Role |
|---|---|
| `run_agent.py` | `AIAgent` — synchronous conversation loop |
| `cli.py` | `HermesCLI` — interactive TUI (prompt_toolkit + rich) |
| `model_tools.py` | Tool orchestration and dispatch |
| `toolsets.py` | Toolset groupings (`_HERMES_CORE_TOOLS` and others) |
| `hermes_state.py` | SQLite session store with FTS5 full-text search |
| `agent/prompt_builder.py` | System prompt assembly |
| `agent/prompt_caching.py` | Anthropic prompt caching (no-op for other providers) |
| `hermes_cli/commands.py` | Central slash command registry (`COMMAND_REGISTRY`) |
| `hermes_cli/config.py` | `DEFAULT_CONFIG`, `OPTIONAL_ENV_VARS`, config migration |
| `tools/registry.py` | Central tool registry — schemas, handlers, dispatch |
| `tools/environments/` | Terminal backends: local, docker, ssh, modal, daytona, singularity |
| `gateway/platforms/` | Messaging adapters: telegram, discord, slack, whatsapp, signal, email |

### Slash command registry

`COMMAND_REGISTRY` in `hermes_cli/commands.py` is the single source of truth. All consumers derive from it automatically: CLI help, Telegram BotCommand menu, Slack subcommands, autocomplete, gateway dispatch. Adding an alias only requires updating the `aliases` tuple on the `CommandDef`.

**To add a slash command:**
1. Add `CommandDef(...)` to `COMMAND_REGISTRY` in `hermes_cli/commands.py`
2. Add handler in `HermesCLI.process_command()` in `cli.py`
3. If gateway-available, add handler in `gateway/run.py`

### Tool registration

Any `tools/*.py` file with a top-level `registry.register()` is auto-discovered — no import list to maintain.

**To add a tool:**
1. Create `tools/your_tool.py` with `registry.register(name, toolset, schema, handler, check_fn, requires_env)`
2. Add the tool name to `_HERMES_CORE_TOOLS` in `toolsets.py` (or define a new toolset)
3. All handlers must return a JSON string

### Configuration

User config lives in `~/.hermes/config.yaml` (settings) and `~/.hermes/.env` (API keys). Two separate loaders exist: `load_cli_config()` in `cli.py` (interactive mode) and `load_config()` in `hermes_cli/config.py` (`hermes setup`, `hermes tools`).

**To add a config option:** add to `DEFAULT_CONFIG` in `hermes_cli/config.py` and bump `_config_version`.

**To add an env variable:** add to `OPTIONAL_ENV_VARS` in `hermes_cli/config.py` with `description`, `prompt`, `url`, `password`, and `category` fields.

## Critical Rules

### Profile-safe paths
All 119+ references to `HERMES_HOME` must go through `get_hermes_home()` from `hermes_constants`. **Never** hardcode `~/.hermes` or `Path.home() / ".hermes"` — this breaks profile isolation. Use `display_hermes_home()` for user-facing messages.

```python
# CORRECT
from hermes_constants import get_hermes_home
config_path = get_hermes_home() / "config.yaml"

# WRONG — breaks profiles
config_path = Path.home() / ".hermes" / "config.yaml"
```

### Prompt caching must not break
**Do not** alter past context mid-conversation, change toolsets mid-conversation, or reload memories/system prompts mid-conversation. The only permitted context change is during context compression (`agent/context_compressor.py`). Cache-breaking dramatically increases API costs.

### Tests must not write to `~/.hermes/`
The `_isolate_hermes_home` autouse fixture in `tests/conftest.py` redirects `HERMES_HOME` to a temp dir. For profile tests, also mock `Path.home()` — see `tests/hermes_cli/test_profiles.py` for the fixture pattern.

## Known Pitfalls

- **No `simple_term_menu`** for interactive menus — rendering bugs in tmux/iTerm2. Use `curses` instead (see `hermes_cli/tools_config.py`).
- **No `\033[K`** (ANSI erase-to-EOL) in spinner/display code — leaks as literal `?[K` under `prompt_toolkit`. Use space-padding: `f"\r{line}{' ' * pad}"`.
- **No cross-tool references in schema descriptions** — tool schemas must not mention tools from other toolsets by name (the model may call non-existent tools). Add dynamic references in `get_tool_definitions()` in `model_tools.py` if needed.
- **`_last_resolved_tool_names` is a process-global** in `model_tools.py` — temporarily stale during subagent runs; `delegate_tool.py` saves/restores it around child execution.