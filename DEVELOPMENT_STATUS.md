# Development status — FATE AI 0.1.0

Last updated: 2026-11-26. This file is kept honest: nothing is marked complete unless it is implemented, and
"tested" means an automated test actually ran (environment noted).

## Test environment used for this version
Linux x86-64 container, Python 3.13, PySide6 6.12 (offscreen Qt), Docker Engine 29 with `python:3.12-slim`.
**No Windows machine, GPU, Ollama model weights, or cloud API keys were available**, so the Windows-only paths
below are implemented but not yet executed. The CI workflow (`.github/workflows/build.yml`) runs the suite on
`windows-latest`, builds the exe + installer, and performs a silent install → launch → uninstall test.

## Completed (implemented and tested)
| Feature | Tests |
|---|---|
| SQLite schema, migrations, repositories, search, export/import, branching, cascade delete, SQL-injection safety | `tests/unit/test_database.py` |
| Settings (Pydantic, atomic save, corrupt-file recovery, validation) | `test_hardware_resources_updater.py` |
| Credential manager (vault-backed, never in DB/files/logs, masking, validation), redaction filter | `tests/security/` |
| Path safety (traversal, absolute paths, Windows reserved names), zip-slip protection | `tests/security/`, `tests/unit/` |
| OpenAI / Anthropic / Ollama / OpenAI-compatible adapters: model lists (incl. pagination), SSE/NDJSON streaming, usage, error mapping (401/429/5xx), key redaction in errors, temperature retry | `tests/integration/test_providers.py` (wire-protocol mocks) |
| Chat service: stream, persist, auto-title, regenerate, edit-and-resend, failures recorded, per-chat provider/model | `tests/integration/test_chat_service.py` |
| Chat UI end-to-end over real HTTP (Ollama protocol server): send, stream, persist, restart & reopen | `tests/ui/test_ui_workflows.py` |
| Usage tracking + cost estimates from editable pricing table | `test_chat_service.py` |
| Level 1 process sandbox: run project, scrubbed env, timeout kill, output cap, memory limit (rlimit), reset/delete/export | `tests/integration/test_sandbox.py` |
| Level 2 container sandbox: real Docker — no network, memory limit (OOM), read-only root, timeout, outputs written back | `tests/virtualization/test_docker_backend.py` |
| Container environments (Docker backend): create, start, exec, resize, pause/resume, snapshot (commit), emergency stop | `test_docker_backend.py` |
| VM manager: capability model, resource validation (host reserve), emergency stop, audit | `tests/virtualization/test_vm_manager.py` |
| Hardware detection & live metrics (no fabricated values) | `test_hardware_resources_updater.py` |
| Local model catalogue + hardware fit / tier recommendation | same |
| Resource presets | same |
| Document parsing: TXT/MD/JSON/CSV/code/DOCX/PDF, binary rejection, prompt-injection flagging + untrusted wrapper | `test_documents_projects_agents.py` |
| Projects: create, write-requires-confirmation, diff, backups, zip export/import | same |
| Agents: permission guard, path confinement, user rejection, tool-call parsing | same |
| Updater: release check, SHA-256 verification, deletion on mismatch | `test_hardware_resources_updater.py` |
| Delete-all-local-data; "don't store chat history" | `test_chat_service.py` |
| All 16 pages + onboarding build; models page, provider test, sandbox page run, onboarding skip-everything | `tests/ui/` |
| Local document index (BM25) with cited, untrusted-wrapped context; used by Project agents | `tests/unit/test_structure_modules.py` |
| Snapshot manager (validated names, clean-snapshot revert, audit), resource-limit module, local engine manager, metrics summary/CSV export, input validation, migrations package | same |
| PyInstaller spec builds and the frozen app passes `--smoke-test` | run manually on Linux |

Result of the last full run: **91 passed, 0 failed, 0 skipped** (Docker available).

## Implemented, not yet executed (needs Windows / external software)
- Windows Credential Manager backend (via `keyring`; falls back to session memory with a visible warning).
- Windows Job Object limits for Level 1 sandboxes (memory, CPU hard cap, process count) — ctypes code paths.
- Hyper-V backend (PowerShell): create/start/stop/pause/clone/snapshots/CPU cap/console, GPU-P detection.
- VirtualBox backend (VBoxManage): full lifecycle, snapshots, headless background start, CPU execution cap.
- WSL2 backend: list/install/start/terminate/unregister/exec.
- Level 3 VM sandbox (VirtualBox guestcontrol / Hyper-V PowerShell Direct) with snapshot revert.
- Windows GPU detection from the display-driver registry (VRAM via `qwMemorySize`); NVIDIA via `nvidia-smi`.
- Inno Setup installer + silent install/uninstall test (in CI workflow; runs when pushed to GitHub).
- Autostart at sign-in (HKCU Run key), tray behaviour on Windows.
- Real OpenAI/Anthropic calls (protocol verified with mocks; needs a user key to verify live).
- Real Ollama model download + local inference (protocol verified; model hosts were unreachable from the build sandbox).

## Partially complete
- **Agents** run a single-tool-per-turn loop (max 6 steps) in the Projects page; no parallel tool calls or
  network tool yet (the `network` permission exists but no tool uses it).
- **Model comparison** quality check is a simple "answer contains text" assertion.
- **Updater** signature verification is wired but no public key is configured (`FATE_UPDATE_PUBKEY`).
- **llama.cpp**: chat via `llama-server` works through the OpenAI-compatible adapter; FATE AI does not start the
  server or download GGUF files itself.
- **Theme**: "midnight" is selectable but currently identical to "dark". Only English UI.
- **VM console** for Docker/Podman is not provided (use `docker exec` / the Exec support in code).

## Missing / not started
- Code signing of the executable and installer (documented in `docs/DEVELOPER.md`; requires a certificate).
- Image/vision inputs and tool-calling with cloud providers.
- Embedding-based (semantic) retrieval; current indexing is keyword/BM25.
- Live per-VM GPU assignment UI (GPU-P is detected, not configured — by design, see GPU notes in the app).

## Known issues
- Ollama does not report per-request token usage when generation is cancelled; such requests are recorded with
  estimated tokens (marked ≈).
- On Windows, if another thread holds the database open during "Delete all local data", remaining files are
  deleted on next launch (`.delete_pending` marker).
- Container sandbox timeout allows +30 s for container start-up.

## Required dependencies
Runtime (bundled): PySide6, pydantic, httpx, psutil, keyring, Markdown, Pygments, pypdf, cryptography.
Optional external: Ollama, llama.cpp, Docker Desktop/Podman, VirtualBox, WSL2, Hyper-V, Git.

## Final acceptance checklist
| # | Requirement | Status |
|---|---|---|
| 1 | Install the Windows application | Installer script + CI build/install test written; not yet run on Windows |
| 2 | Launch independently | Frozen build smoke-tested (Linux); Windows in CI |
| 3 | Complete onboarding | ✔ tested (skip-everything path) |
| 4 | Detect hardware | ✔ tested |
| 5 | Add own OpenAI key | ✔ (vault + UI); Windows Credential Manager path untested |
| 6 | Test connection | ✔ protocol-tested; needs a real key for live check |
| 7 | Retrieve models | ✔ protocol-tested |
| 8 | Start a conversation | ✔ |
| 9 | Stream a real response | ✔ via local Ollama-protocol server; live provider not verified here |
| 10 | Save and reopen conversations | ✔ tested across restart |
| 11 | Install/connect a local model | Implemented; model hosts unreachable in build sandbox |
| 12 | Run a local conversation | Implemented; see 11 |
| 13 | Create a sandbox | ✔ |
| 14 | Execute a test project in the sandbox | ✔ Level 1 and Level 2 |
| 15 | Monitor CPU and RAM | ✔ |
| 16 | Configure supported resource limits | ✔ (sandbox/container enforced & tested; VM caps untested on Windows) |
| 17 | Create and manage a VM | ✔ containers (Docker); Hyper-V/VirtualBox untested |
| 18 | Run a VM in the background | ✔ containers keep running after app exit; VirtualBox headless implemented |
| 19 | Stop and restore test environments | ✔ stop/reset/snapshot (containers); VM snapshot revert untested |
| 20 | Export/import projects and conversations | ✔ tested |

## Next implementation tasks
1. Run CI on Windows; fix any Windows-specific failures; record results here.
2. Live-verify OpenAI/Anthropic with real keys and Ollama with a small model on Windows.
3. Exercise Hyper-V and VirtualBox backends on a Windows Pro machine.
4. Code-sign builds; configure update signing key.
5. Document indexing (RAG) and image inputs.
