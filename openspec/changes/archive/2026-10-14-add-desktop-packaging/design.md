# Design

## Context

See proposal.md for why, and `docs/research/desktop-platform.md` for the survey. PaperDaemon today runs as
`uv run paperdaemon`, with pywebview showing the UI in WebView2 inside the engine's own process.

## Goals / Non-Goals

**Goals:**
- A shell that owns the window and the tray, and an engine that keeps running when the window closes.
- An install a non-developer can do.

**Non-Goals:**
- Choosing for the maintainer. The survey recommends; the maintainer decides.

## Decisions

**Tauri 2 is the shell, the engine its own process.** From the survey: the existing
HTML, CSS and JS UI moves over nearly unchanged; the tray, single instance, installers and an
updater come built in; closing the window frees WebView2 while the engine keeps the daemon running; a
window crash cannot take the daemon down; the same frontend can build for Android later. The cost is a
Rust toolchain for development and a few hundred lines to supervise the engine process. It saves disk,
not memory, since WebView2 is Chromium either way.

**Not chosen: staying on pywebview,** which would have meant building the tray, single instance and
updater. It stays the development window until the Tauri shell exists.

**One installer.** Tauri's bundler makes a single setup file holding the shell, the frozen engine and
the WebView2 bootstrapper; an update replaces the whole bundle.

**The window is dark from its first frame.** The window configuration sets a dark title bar and
background, so it never flashes white; PaperDaemon is dark only.

**The engine is frozen as a one-folder build.** One-file builds unpack to a temporary folder on every
start and trip antivirus heuristics; a signed one-folder build avoids both. uvicorn needs
`log_config=None` in a windowed build. The engine's size is set by its libraries (charts, numpy,
Pillow), not by the shell.

**Updates are opt-in.** An updater calls a release endpoint, which PaperDaemon does not do by
default; the switch is off until the user turns it on.

**Signing through a free open-source signing service** is the survey's suggestion for release builds.

## Risks / Trade-offs

- [Tauri 3 is in alpha] → Build on 2.x; the shell is thin, so a later migration is small.
- [A phone app over the tunnel meets Android's block on plain HTTP] → The engine will need TLS on the
  tunnel address, or the phone app a network-security exception; this belongs to the phone app's change.

## Open Questions

Decide before building:
- Whether closing the window keeps PaperDaemon in the tray or quits it. The survey recommends the tray.

Can wait:
- macOS and Linux packages, and their signing.
- The tray menu's items beyond Open, Pause daemon and Quit.
