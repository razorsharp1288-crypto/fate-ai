# Developer guide

## Layout
`fate_ai/` application package · `tests/{unit,integration,security,virtualization,ui}` · `installer/` Inno Setup
script · `scripts/` icon, version-info and Windows build scripts · `fate_ai.spec` PyInstaller spec ·
`.github/workflows/build.yml` CI (tests on Ubuntu + Windows, Windows exe + installer, silent install/uninstall test).

## Running
```bash
pip install -r requirements-dev.txt
python run_fate_ai.py --data-dir ./.devdata        # isolated data folder
python run_fate_ai.py --reset-onboarding
python run_fate_ai.py --smoke-test                 # builds every page and exits (used in CI)
QT_QPA_PLATFORM=offscreen python -m pytest -q
```
Docker-dependent tests run when a Docker engine and `python:3.12-slim` are available, otherwise they skip.

## Adding a provider
Subclass `Provider` (or `OpenAICompatibleProvider`), implement `list_models` and `stream_chat`, and register a
`ProviderKind` in `ai/providers/registry.py`. Add wire-protocol tests with `httpx.MockTransport`.

## Adding a virtualization backend
Subclass `VirtualizationBackend`, declare `caps`, implement `status/list/create/start/stop/delete`, and add it in
`VMManager.__init__`. Raise `VirtualizationError` with user-readable messages; never interpolate user input into
PowerShell — use `ps_quote`.

## Adding a page
Create a `Page` subclass in `ui/pages/`, implement `on_show()` for refreshes, register it in `NAV` and
`_page_factories` in `ui/main_window.py`. Do blocking work with `run_async`.

## Releases
1. Bump `fate_ai/__init__.py: __version__`.
2. Tag `vX.Y.Z` and push; CI builds `FateAI-X.Y.Z-setup.exe` + `SHA256SUMS.txt` and attaches them to a release.
3. Optional code signing: sign `dist\FateAI\FateAI.exe` and the setup exe with `signtool sign /fd SHA256 /tr <tsa> /td SHA256 /f cert.pfx`
   (keep the certificate in a CI secret). Optional update signatures: sign `SHA256SUMS.txt` with Ed25519 and set
   `FATE_UPDATE_PUBKEY` in `updater/updater.py`.
