# Installing FATE AI

## Requirements
- Windows 10 version 1809 (build 17763) or later, or Windows 11 — 64-bit.
- ~600 MB disk for the app. Local models need additional space (0.4 GB – 40+ GB each).
- No Python installation is required; the installer bundles the runtime.

## Steps
1. Download `FateAI-<version>-setup.exe` and `SHA256SUMS.txt`.
2. Optional — verify: `Get-FileHash .\FateAI-<version>-setup.exe -Algorithm SHA256` and compare.
3. Run the installer. It installs to `%LOCALAPPDATA%\Programs\FATE AI` for the current user (no UAC prompt).
4. Launch FATE AI and follow onboarding. Cloud and local setup are both optional and can be skipped.

The installer is not code-signed unless you sign it (see `docs/DEVELOPER.md`), so Windows SmartScreen may warn on
first run: choose *More info → Run anyway* if you trust the source.

## Optional components
| Component | Needed for | Get it |
|---|---|---|
| Ollama | Local models | https://ollama.com/download |
| llama.cpp `llama-server` | GGUF models via llama.cpp | https://github.com/ggml-org/llama.cpp/releases |
| Docker Desktop or Podman | Level 2 sandboxes, container environments | docker.com / podman.io |
| WSL2 | Linux dev environments | `wsl --install` (admin terminal, once) |
| VirtualBox | VMs, Level 3 sandboxes | virtualbox.org |
| Hyper-V | VMs, Level 3 sandboxes (Windows Pro/Enterprise/Education) | *Turn Windows features on or off*; add yourself to *Hyper-V Administrators* |
| Git | Project version history | git-scm.com |

FATE AI detects each component and explains what is missing; it never installs drivers or enables Windows
features on its own.

## Unsupported configurations
- 32-bit or ARM64 Windows (x64 emulation on ARM64 is untested).
- Windows Home cannot use Hyper-V; use VirtualBox, WSL2 or Docker instead.
- Windows 10 builds before 1809.

## Uninstalling
Use *Settings → Apps → FATE AI → Uninstall*. Your data folder (`%LOCALAPPDATA%\FateAI`) and stored API keys are
kept so a reinstall keeps your chats. To remove everything, first use *Settings → Privacy → Delete all local data*.
