# Proposal

## Why

Before PaperDaemon can answer a single page it needs a home: settings the user can change, a safe place
for secrets, one local API that the desktop window (and later a phone over WireGuard) talks to, and
its own connection to the reMarkable cloud with its own copy of the library. Every later change
builds on these.

## What Changes

- A settings file with defaults, validation and atomic saves, in PaperDaemon's own data folder.
- Secrets (the reMarkable device token, API keys, the pairing token) kept in the operating system's
  credential store and never returned by the API.
- A local HTTP API, versioned under `/api/v1`, that refuses every request without the pairing token.
  It listens on 127.0.0.1 and on any further addresses the user adds, such as a WireGuard address.
- A desktop window that shows PaperDaemon's UI from that API, with no web browser involved.
- A reMarkable connection made from a pasted device token, with a connection check. The README
  explains how to get a token.
- PaperDaemon's own mirror of the library: a full first pull, then incremental pulls, change
  notifications from the cloud, and cloud writes that record the previous state first and never
  delete anything permanently.

## Capabilities

### New Capabilities
- `engine/settings`: where settings live, their defaults, validation and saving.
- `engine/secrets`: how secrets are stored, set, replaced and removed.
- `engine/local-api`: the versioned local API, its pairing token and the addresses it listens on.
- `engine/desktop-shell`: the desktop window that hosts the UI.
- `tablet/connection`: connecting to the reMarkable cloud with a device token.
- `tablet/sync`: PaperDaemon's own mirror of the library, pulls, change notifications and safe writes.

### Modified Capabilities
None.

## Non-goals

- No daemon, job host, drawing tools or model handling. Those are later changes.
- No sign-in flow inside the app: the user pastes a device token they got as the README describes.
- No installer or auto-update (see add-desktop-packaging).
- No pricing, cost display or usage metering, ever.

## Impact

- New Python package `paperdaemon` (Python 3.12, managed with uv): settings, secrets, the local API, the
  desktop entry point, and the reMarkable auth and sync modules.
- Dependencies: FastAPI and uvicorn (the API), keyring (the credential store), and a desktop shell
  library (pywebview for now, pending the platform decision in design.md).
- Data under `%APPDATA%\PaperDaemon` on Windows and `~/.local/share/paperdaemon` elsewhere.
- Talks to the reMarkable cloud's sync API, which is unofficial and can change without notice.
