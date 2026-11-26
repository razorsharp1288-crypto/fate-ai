# Security model

## Credentials
- Stored with `keyring` → Windows Credential Manager (service `FateAI`, key `provider:<id>:api_key`).
- Never written to SQLite, `settings.json`, logs or diagnostics. Tests assert the raw key bytes appear in no file
  under the data folder.
- Every loaded key is registered with the redactor; a logging filter and the diagnostics exporter redact known
  secrets and common key patterns (OpenAI, Anthropic, GitHub, Hugging Face, Bearer tokens…).
- Keys are only sent to the provider host configured for them. Plain-HTTP endpoints for key-bearing providers
  require explicit confirmation. FATE AI never scans the computer for keys.

## Least privilege
- The app and installer run as a standard user (`uac_admin=False`, `PrivilegesRequired=lowest`). Nothing silently
  elevates. Hyper-V operations require the user to be in *Hyper-V Administrators*.
- FATE AI never disables antivirus, Defender, firewall, updates or system services, and never touches system processes.

## Sandboxes
| Level | Isolation | Not isolated |
|---|---|---|
| 1 Process | private folder, allow-listed environment (no secrets), timeout, output cap, Windows Job Object: memory, CPU-rate hard cap, process count, kill-on-close; POSIX rlimits | filesystem and network — **not a security boundary**; explicit consent required each run |
| 2 Container | `--network=none` by default, `--cap-drop=ALL`, `no-new-privileges`, read-only root, tmpfs `/tmp`, only the sandbox folder mounted, CPU/memory/PID limits | kernel shared with the Docker VM |
| 3 VM | separate OS; optional revert to a clean snapshot after each run | depends on VM network config |

## Agents
Capabilities (`read_files`, `write_files`, `run_sandbox`, `network`, `system_info`) are opt-in per agent. File access
is confined to the open project and folders explicitly approved; paths are resolved with `realpath` to block `..`
and symlink escapes. Writes and sandbox runs always prompt. Every decision is written to the audit log.

## Documents & prompt injection
Documents are parsed locally (no macros executed; DOCX parsed with a non-entity-resolving XML parser; size and
character caps). Content is wrapped in an explicit *untrusted data* envelope and suspicious instruction-like text is
flagged. The user is asked before a document is sent to a cloud provider.

## Model output
Markdown from models is rendered with raw HTML escaped and non-http(s) links neutralised.

## Updates
`updater/updater.py` downloads only from the configured GitHub repository's releases, requires `SHA256SUMS.txt`,
verifies the hash (and an Ed25519 signature when `FATE_UPDATE_PUBKEY` is set), deletes mismatching files and never
runs an installer without user confirmation.

## Reporting
Please open a private security advisory on the repository rather than a public issue.
