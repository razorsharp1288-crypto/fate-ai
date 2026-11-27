# FATE AI

**A local-first Windows desktop AI platform** — chat with cloud and local models, manage Ollama / llama.cpp
models, run code in isolated sandboxes, manage virtual machines and containers, and monitor your hardware, all
in one native PySide6 application.

- **No FATE servers.** Conversations, settings and projects live in `%LOCALAPPDATA%\FateAI`. Cloud AI is billed
  by each provider directly to *your* account.
- **Keys in Windows Credential Manager** — never in the database, settings or logs.
- **Honest about limits.** Every resource control is labelled *enforced* or *estimate*; sandbox levels say exactly
  what they isolate; missing hardware data is shown as "unavailable", never guessed.

![icon](assets/fate_ai.png)

## Features

| Area | What it does |
|---|---|
| Chat | Multiple chats, search, rename, delete, branch, export/import (JSON/Markdown), streaming, stop, regenerate, edit-and-resend, per-chat provider/model/system prompt/temperature/max tokens, Markdown + code highlighting, document attachments (parsed locally) |
| Any AI provider | 30-service catalog — OpenAI, Anthropic Claude, Google Gemini, xAI Grok, Mistral, DeepSeek, Groq, Cerebras, Perplexity, Cohere, Moonshot, Qwen, GLM, AI21, Azure OpenAI, OpenRouter, Together, Fireworks, DeepInfra, Hugging Face, NVIDIA NIM, SambaNova, Novita, plus local Ollama, llama.cpp, LM Studio, vLLM, LocalAI, Jan — and **any custom endpoint** with any auth header |
| API Keys | "Paste any key" auto-detects the service; keys live in Windows Credential Manager; per-service test; readiness assistant (never scans your PC for keys) |
| Blueprints | Describe anything (armor suit, drone, robot arm, rover, mech, cabin…) → AI writes a full design spec (specs, subsystems, materials, bill of materials, build steps, safety) **and** a 3D concept model; **Auto 3D** builds one instantly offline; interactive 3D viewer; edit parts; export STL (3D printing), OBJ+MTL (Blender), Markdown, PNG |
| Auto-update | Checks GitHub Releases on start and every few hours; one-click verified download, silent install and relaunch |
| Navigation | Grouped sidebar, Ctrl+K command palette, Ctrl+1…9 page shortcuts, toast notifications |
| AI Models | Ollama: list, download with progress/cancel, delete, load/unload, details; curated catalogue with Lightweight/Balanced/High tiers and RAM/VRAM fit checks |
| Virtual Machines | Hyper-V, VirtualBox, WSL2, Docker, Podman backends with capability detection; create wizard with safe resource limits; start/stop/force/pause/resume/restart/clone/delete; snapshots; console; CPU caps; background operation; emergency stop |
| Sandbox | Level 1 restricted process (Windows Job Object limits), Level 2 container (no network, dropped caps, read-only root, CPU/RAM/PID limits), Level 3 VM with snapshot revert; import/export, reset, live CPU/RAM, emergency stop |
| Projects & Agents | Workspaces, embedded editor with diff-before-write, Git history, agents with least-privilege tool permissions and confirmation prompts |
| Prompt Library | Categories, tags, favourites, `{{variables}}`, usage history, import/export |
| Model Comparison | Same prompt on several models; measured latency, first-token time, tokens/s — kept separate from published specs |
| Usage Dashboard | Requests, tokens, latency, failures, local vs cloud, estimated cost from an editable pricing table |
| Hardware Monitor | Live CPU/RAM/GPU/VRAM/disk/network charts, detected hardware, running models/VMs/tasks |
| Security Center | Credential status, privilege check, data flow, agent permissions, audit log |

## Install (Windows 10 1809+ / Windows 11, x64)

Download `FateAI-<version>-setup.exe` from the Releases page (or from the **FateAI-windows** artifact of the
*Test and build Windows installer* GitHub Actions run) and run it. It installs per-user — no administrator rights —
and bundles its own Python runtime. Verify the download against `SHA256SUMS.txt`.

For local models also install [Ollama](https://ollama.com/download). For VMs/containers install any of: Docker
Desktop, Podman, VirtualBox, WSL2 (`wsl --install`), or enable Hyper-V (Windows Pro/Enterprise).

See [docs/INSTALL.md](docs/INSTALL.md) and [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Run from source

```powershell
py -3.12 -m venv .venv; .venv\Scripts\activate
pip install -r requirements-dev.txt
python run_fate_ai.py
python -m pytest -q          # test-suite
./scripts/build_windows.ps1  # exe + installer (needs Inno Setup 6)
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) · [Security](docs/SECURITY.md) · [Developer guide](docs/DEVELOPER.md)
- [Development status](DEVELOPMENT_STATUS.md) — what is done, partial, missing and tested

## License

MIT — see [LICENSE](LICENSE).
