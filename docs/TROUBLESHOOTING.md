# Troubleshooting

| Symptom | Fix |
|---|---|
| "Ollama is not running" | Install Ollama and start it (tray icon). Check *Settings → Local models → Ollama URL* (default `http://127.0.0.1:11434`). |
| "No models found" in chat | Download one on *AI Models → Discover & download*, or add an API key for a cloud provider. |
| "Authentication failed (401)" | The API key is wrong or revoked. Re-paste it on *API Keys* and click *Test*. |
| "Rate limited" (429) | Your provider account hit a limit or has no credit. Check the provider's billing page. |
| Model download fails | Ollama's error is shown verbatim — usually a mistyped tag or no disk space. |
| Model is very slow | It's running on CPU. Pick a smaller model (Lightweight tier) or one that fits your VRAM. |
| Keys forgotten after restart | No OS credential vault was available; the API Keys page shows a warning. On Windows ensure the *Credential Manager* service is running. |
| Container sandbox: "engine is not running" | Start Docker Desktop / Podman machine. First run pulls the image (needs internet). |
| Level 1 sandbox can't find Python | The packaged app does not ship a general Python for user code. Install Python or use a container sandbox. |
| Hyper-V "not in Hyper-V Administrators" | Run `Add-LocalGroupMember -Group "Hyper-V Administrators" -Member $env:USERNAME` as admin, then sign out/in. |
| VirtualBox VM sandbox: copy fails | Install Guest Additions in the VM and provide a valid guest user/password in the sandbox settings. |
| GPU not shown | Only NVIDIA exposes live utilization (nvidia-smi). Other GPUs show name/VRAM from the driver registry when available. |
| App doesn't close | It minimises to the tray by default. Right-click the tray icon → *Quit*, or disable this in *Settings → General*. |

Logs: *Developer Tools → Logs* or `%LOCALAPPDATA%\FateAI\logs\fate.log` (secrets are redacted).
Diagnostics: *Developer Tools → Diagnostics → Generate* produces a redacted JSON report you can share.
