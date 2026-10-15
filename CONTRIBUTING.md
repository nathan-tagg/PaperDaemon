# Contributing

## Setting up

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/), Node (for OpenSpec, the checks and the Tauri CLI), and
for the desktop app Rust with a Windows linker: Visual Studio's C++ build tools, or Rust's
`x86_64-pc-windows-gnullvm` target with [llvm-mingw](https://github.com/mstorsjo/llvm-mingw) on `PATH`.

```sh
uv sync
cd shell && npm ci && cd ..
uv run python paperdaemon/pipeline/decompose/fastdecomp/build.py   # the C decomposer, for this machine
uv run paperdaemon                                                 # the desktop window
uv run paperdaemon --headless                                      # the engine only
```

The engine keeps its settings and data in `%APPDATA%\PaperDaemon`; set `PAPERDAEMON_HOME` to work with another
data folder.

## How work is done

- **Specs first.** A feature starts as an [OpenSpec](https://github.com/Fission-AI/OpenSpec) change in
  `openspec/changes/<name>/`: a proposal, spec deltas, a design and tasks. Run
  `openspec validate --all --strict --no-interactive` before calling a change done.
- **Checks.** These must pass:
  - `uv run pytest`: the tests use their own data folder and ports, never yours.
  - `node tools/check.mjs`: American spelling, no secrets in files.
  - `uv run python tools/publish_check.py`: no private term, UUID, absolute user path or dated attribution in a
    publishable file. Its denylist is private and kept outside the repository (see the script's docstring).
- **Rules.** American spelling everywhere. No secret in any file. No prices, cost meters or usage counts. A
  user's own prompts are used as written. Runaway model output is stopped by tokens and repetition, never by a
  clock. The decomposer's output must stay identical to its reference (`tests/test_decompose_identity.py`).

## Building

`uv run python tools/build_app.py` builds the C decomposer, the icons, the frozen engine, Stockfish (downloaded
once and checked against its SHA-256), the Tauri shell and the NSIS installer. The app lands in `dist/app/`
and the installer under `shell/target/release/bundle/nsis/`. Quit a running copy of the app first, or pass
`--stage <folder>` to assemble it elsewhere. Without `--repo` and `--update-key` it is a local build with no
update bundle.

## Releasing

1. Set the version in `pyproject.toml`, `paperdaemon/__init__.py`, `shell/Cargo.toml` and
   `shell/tauri.conf.json`, and add the release's entry to `CHANGELOG.md`.
2. Run the checks above; `tools/publish_check.py` must exit 0.
3. Once per project: `cd shell && npx tauri signer generate -w <path outside the repository>`. It writes the
   private key (keep it, and its password, safe and off the repository: losing it means installed copies
   can't verify later updates) and the public key (`.pub`).
4. Set `TAURI_SIGNING_PRIVATE_KEY` (the private key's text or path) and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`,
   then build: `uv run python tools/build_app.py --repo OWNER/NAME --update-key <the .pub file>`.
5. Make a GitHub release tagged `v<version>` and attach the installer and `latest.json` from
   `shell/target/release/bundle/nsis/`. **Check for updates** reads `latest.json` from the latest release; the
   installer's signature is inside it, so the `.sig` file is not attached.

The installer is not code-signed (Authenticode); only the update bundle is signed, with the key above.
