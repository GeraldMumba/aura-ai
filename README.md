# AURA AI

A local-first desktop AI assistant built with **Python**, **PySide6**, and **Ollama**.

AURA is designed to help developers understand projects, work with source files, and get coding assistance while keeping project files under the user's control.

## Current milestone

The repository is being built incrementally. The first milestone establishes the desktop application, local Ollama chat, persistent conversations, and a hardware-friendly foundation. File editing and other advanced features will be added only after their safety and tests are in place.

## Features planned

- PySide6 desktop interface with a dark, readable theme
- Local Ollama chat with background execution
- SQLite-backed conversation history and settings
- Project workspace browsing and read-only source inspection
- Safe file-change proposals with diff preview and explicit approval
- Coding assistance: explain, generate, debug, refactor, and document code
- System resource monitor
- Document reading and summarization
- Activity and change history

## Requirements

- Python 3.10+
- Linux, Windows, or macOS
- Ollama installed locally
- A model available in Ollama (for example, `llama3.2:3b`)

## Setup on Pop!_OS / Ubuntu

```bash
git clone https://github.com/GeraldMumba/aura-ai.git
cd aura-ai

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

ollama pull llama3.2:3b
ollama serve
```

In another terminal, start AURA:

```bash
python main.py
```

If Ollama is already running as a service, do not start a second server. AURA defaults to `http://127.0.0.1:11434`.

## Configuration

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `AURA_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama server URL |
| `AURA_MODEL` | `llama3.2:3b` | Model name |
| `AURA_DATA_DIR` | `~/.local/share/aura-ai` | Application data directory |

## Safety principles

- Reading and searching files should be deterministic and read-only.
- AI-generated changes must be shown as proposals before they are applied.
- Writing, moving, renaming, or deleting project files requires explicit user approval.
- File operations must be confined to the selected workspace.
- Backups, recoverable deletion, and change history are required for destructive operations.
- AURA must never execute arbitrary AI-generated shell commands.

## Development

Run tests with:

```bash
python -m pytest
```

See [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) for the implementation roadmap and current status.
