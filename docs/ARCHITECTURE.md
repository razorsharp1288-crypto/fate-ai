# Architecture

```
run_fate_ai.py ─► fate_ai.main ─► bootstrap.build_context()  (composition root / DI)
                                   │
   ┌───────────────────────────────┼──────────────────────────────────────────┐
   │ UI (PySide6)                  │ Services                                  │
   │ ui/main_window.py             │ ai/chat/service.py      ChatService       │
   │ ui/pages/*  (16 pages, lazy)  │ ai/providers/*          Provider adapters │
   │ ui/dialogs/* onboarding,agents│ ai/agents/service.py    Agents + tools    │
   │ ui/components/* widgets,      │ sandbox/*               3 isolation levels│
   │   worker (thread→GUI bridge)  │ virtualization/*        5 backends        │
   └───────────────────────────────┤ hardware/, monitoring/  detection/metrics │
                                   │ projects/, documents/, resources/, updater│
                                   ├──────────────────────────────────────────┤
                                   │ security/ credentials, redaction, paths,  │
                                   │           permissions, audit             │
                                   │ database/ SQLite + migrations + repos     │
                                   │ core/ settings (pydantic), event bus,     │
                                   │       task manager, exceptions           │
                                   └──────────────────────────────────────────┘
```

## Package layout
```
fate_ai/
  main.py  bootstrap.py  config.py
  ui/            main_window.py, components/, pages/ (16), dialogs/ (onboarding, agents), themes/
  core/          event_bus.py, task_manager.py, settings.py, exceptions.py
  ai/            providers/ (OpenAI, Anthropic, Ollama, llama.cpp, compatible), local_engine/ (engine status &
                 lifecycle), model_manager/ (catalogue & hardware fit), agents/, chat/, pricing.py, comparison.py
  virtualization/ backends/ (hyperv, virtualbox, wsl, container), vm_manager.py, snapshots.py, resource_limits.py
  sandbox/       process_sandbox.py, container_sandbox.py, vm_sandbox.py, execution_manager.py
  hardware/      detection.py (facade), cpu.py, memory.py, gpu.py, storage.py
  security/      credential_manager.py, permissions.py, audit.py, redaction.py, paths.py
  database/      db.py, models.py, repository.py, migrations/ (v001_initial.py, …)
  documents/     parsers/ (base, docx, pdf), indexing.py (local BM25 search)
  monitoring/    metrics.py, collector.py
  projects/      manager.py, versioning.py (git)
  resources/     manager.py (presets, enforcement table)
  updater/       updater.py
  utilities/     logging.py, paths.py, validation.py, proc.py
```

## Key decisions
- **Threads, not asyncio.** Providers use synchronous `httpx` streaming in a `QThreadPool`. `ui/components/worker.py`
  delivers progress/results through a GUI-thread `QObject` with queued connections, so callbacks can touch widgets
  safely. Cancellation is cooperative via `CancelToken`.
- **Provider interface** (`ai/providers/base.py`): `list_models()`, `stream_chat()` yielding `StreamChunk`s,
  `test_connection()`. HTTP errors map to typed exceptions (`AuthenticationError`, `RateLimitError`,
  `ProviderUnavailableError`). Transport is injectable, which is how the tests exercise each wire protocol.
- **Repositories** are the only SQL. All queries are parameterised; updatable columns are whitelisted.
  Migrations are an ordered list applied via `PRAGMA user_version`.
- **Settings** are a Pydantic model persisted atomically as JSON; invalid files are quarantined, not fatal.
- **Virtualization backends** implement one ABC and declare capabilities (`Cap`). The UI only enables actions a
  backend supports. `VMManager.validate_spec` reserves 1 CPU and 2 GB RAM for Windows.
- **Sandboxes** return `ExecutionResult.enforced` / `not_enforced` so the UI can state precisely which limits applied.
- **Pages are built lazily** on first navigation; a failing page shows an error label instead of crashing the app.

## Data locations
| What | Where |
|---|---|
| Database (chats, prompts, projects, usage, audit) | `%LOCALAPPDATA%\FateAI\fate.db` |
| Settings | `%LOCALAPPDATA%\FateAI\settings.json` |
| Pricing table (editable) | `%LOCALAPPDATA%\FateAI\pricing.json` |
| Sandboxes / projects / exports | `%LOCALAPPDATA%\FateAI\{sandboxes,projects,exports}` |
| API keys | Windows Credential Manager, service `FateAI` |
| Logs | `%LOCALAPPDATA%\FateAI\logs` |
